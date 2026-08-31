"""Site API — the only surface the public frontend may read from.

Two properties define this router.

**It never serves unpublished content on a public route.** `GET /content/{slug}`
returns PUBLISHED rows only. A staged page is reachable through `/preview/...`,
which carries a separate preview token, so "someone guessed the slug" and "someone
holds the preview key" are different events.

**It is authenticated, and the frontend authenticates server-side.** The web app
holds the key in its server runtime and proxies browser requests; the key never
reaches a client bundle. That keeps a browser from posting leads directly and keeps
the lead endpoint behind one server we control.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_internal_key
from app.core.enums import PublicationState, SiteEventType
from app.core.errors import SeoLeadError
from app.db.session import get_session
from app.models import (CapturedLead, ContentBrief, ContentDraft,
                        PublishedContent, Site, SiteEvent, Vertical)
from app.site.config import InvalidSite, SiteConfig, load_site
from app.site.lead_capture import (LeadRejected, LeadSubmission, capture_lead)
from app.site.lead_notification import notify_lead
from app.site.publication import draft_preview_dto, evaluate_gate, to_dto
from app.site.spam_protection import SubmissionSignals

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/site/v1", tags=["site"],
                   dependencies=[Depends(require_internal_key)])

_MAX_EVENT_DETAIL_KEYS = 8


def _config(site_id: str) -> SiteConfig:
    try:
        return load_site(site_id)
    except InvalidSite as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail={"code": exc.code, "message": exc.detail}) from exc


async def _site_row(session: AsyncSession, config: SiteConfig) -> Site:
    row = (await session.execute(
        select(Site).join(Vertical).where(
            Vertical.code == config.vertical,
            Site.name == config.site_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "SITE_NOT_SEEDED",
                    "message": f"site {config.site_id} has no database row; "
                               f"run `seolead site seed` first"})
    return row


class LeadRequest(BaseModel):
    """Everything the form may send. Field-level validation happens server-side
    in `lead_capture`; this layer only bounds sizes and shapes."""

    conversion_type: str = Field(..., max_length=32)
    email: str = Field(..., max_length=320)
    language: str = Field(..., max_length=8)
    first_name: str | None = Field(None, max_length=120)
    last_name: str | None = Field(None, max_length=120)
    phone: str | None = Field(None, max_length=40)
    postcode: str | None = Field(None, max_length=16)
    qualification: dict = Field(default_factory=dict)
    consent_processing: bool = False
    consent_marketing: bool = False
    # Per-case consent answers, keyed by consent field key. The configuration
    # decides which keys exist; unknown keys are dropped server-side.
    consents: dict = Field(default_factory=dict)
    attribution: dict = Field(default_factory=dict)
    # Spam signals. The decoy field carries a name with no meaning to an
    # autofill engine and none to a reader of the request body either — the
    # payload travels through a browser, and naming the trap in it is naming it
    # to whoever is watching. `honeypot` stays accepted because a page served
    # before this deploy is still posting it, and an alias that quietly stops
    # being read would disable the defence for those visitors without a trace.
    ref_token_2: str | None = Field(None, max_length=200)
    honeypot: str | None = Field(None, max_length=200)

    @property
    def decoy_value(self) -> str | None:
        # The form posts "" for an untouched field, under either key. Empty is
        # absent: a decoy nobody filled must not read as a decoy somebody did.
        return (self.ref_token_2 or "").strip() or (self.honeypot or "").strip() \
            or None
    elapsed_ms: int | None = Field(None, ge=0, le=86_400_000)
    client_key: str | None = Field(None, max_length=128)

    @field_validator("qualification", "attribution", "consents")
    @classmethod
    def _bounded(cls, value: dict) -> dict:
        if len(value) > 40:
            raise ValueError("too many keys")
        return value


class EventRequest(BaseModel):
    event_type: str = Field(..., max_length=32)
    page_path: str | None = Field(None, max_length=512)
    locale: str | None = Field(None, max_length=8)
    session_id: str | None = Field(None, max_length=64)
    detail: dict = Field(default_factory=dict)


@router.get("/sites/{site_id}")
async def get_site_config(site_id: str) -> dict:
    """Public-safe site configuration for the renderer.

    Contact and legal blocks are included because the site displays them, but
    nothing here is a secret: the whole payload is destined for a rendered page.
    """
    config = _config(site_id)
    return {
        "site_id": config.site_id, "vertical": config.vertical,
        "brand_name": config.brand_name,
        "brand_name_is_placeholder": config.brand_name_is_placeholder,
        "domain": config.domain, "market": config.market,
        "default_language": config.default_language,
        "supported_languages": config.supported_languages,
        "staging": config.staging, "indexable": config.is_indexable,
        "locale_paths": config.locale_paths,
        "contact": config.contact.model_dump(),
        "legal": config.legal.model_dump(),
        "conversion": config.conversion.model_dump(),
        "seo": config.seo.model_dump(),
        # The first-party offer, publication-gated at the source: `facts` only
        # ever carries values the owner validated AND the lawyer cleared
        # (`usable_facts` is empty otherwise), so the renderer cannot show an
        # unvalidated figure even by mistake. The flags travel so the landing
        # can hide itself and the sitemap can exclude it.
        "offer": {
            "version": config.offer.version,
            "status": config.offer.status,
            "pending_legal_review": config.offer.pending_legal_review,
            "publishable": config.offer.publishable,
            "facts": [
                {"id": f.id, "label": f.label, "value": f.value, "unit": f.unit}
                for f in config.offer.usable_facts
            ],
            "financing": config.offer.financing,
            "eligibility": config.offer.eligibility,
            "geography": config.offer.geography,
            "mandatory_disclosures": config.offer.legal.mandatory_disclosures,
        },
        # Identity for structured data. The readiness flags are computed here —
        # the renderer emits Organization/LocalBusiness only when they are true,
        # so a half-filled block can never become a half-true schema.
        "organization": {
            # `lead_destination_email` stays out: it is lead ROUTING, read by
            # the notification layer server-side — the renderer has no use for
            # it and operational values do not belong in page payloads.
            **config.organization.model_dump(exclude={"lead_destination_email"}),
            "registration_number": config.organization.registration_number,
            "organization_schema_ready":
                config.organization.organization_schema_ready,
            "local_business_schema_ready":
                config.organization.local_business_schema_ready,
        },
        "routes": config.routes,
    }


@router.get("/sites/{site_id}/content")
async def list_content(site_id: str, locale: str | None = None,
                       session: AsyncSession = Depends(get_session)) -> dict:
    """Every PUBLISHED page. This is what the sitemap is built from."""
    config = _config(site_id)
    site = await _site_row(session, config)
    query = select(PublishedContent).where(
        PublishedContent.site_id == site.id,
        PublishedContent.state == PublicationState.PUBLISHED.value)
    if locale:
        query = query.where(PublishedContent.locale == locale)
    rows = (await session.execute(query)).scalars().all()
    return {"items": [to_dto(row, config) for row in rows],
            "indexable": config.is_indexable}


@router.get("/sites/{site_id}/content/{locale}/{slug}")
async def get_content(site_id: str, locale: str, slug: str,
                      session: AsyncSession = Depends(get_session)) -> dict:
    """One PUBLISHED page. Staged and draft content is not reachable here."""
    config = _config(site_id)
    site = await _site_row(session, config)
    row = (await session.execute(
        select(PublishedContent).where(
            PublishedContent.site_id == site.id,
            PublishedContent.locale == locale,
            PublishedContent.slug == slug,
            PublishedContent.state == PublicationState.PUBLISHED.value)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail={"code": "NOT_PUBLISHED"})
    return to_dto(row, config)


@router.get("/sites/{site_id}/preview/{locale}/{slug}")
async def preview_content(site_id: str, locale: str, slug: str,
                          request: Request,
                          session: AsyncSession = Depends(get_session)) -> dict:
    """The staging path. Serves STAGED or PUBLISHED, newest version first.

    Requires `X-Preview-Token` in addition to the internal key. Two independent
    secrets, because the preview route is the one place unpublished content is
    readable and the internal key is shared with every other operator call.
    """
    _require_preview_token(request)
    config = _config(site_id)
    site = await _site_row(session, config)
    row = (await session.execute(
        select(PublishedContent).where(
            PublishedContent.site_id == site.id,
            PublishedContent.locale == locale,
            PublishedContent.slug == slug,
            PublishedContent.state.in_([PublicationState.STAGED.value,
                                        PublicationState.PUBLISHED.value]))
        .order_by(PublishedContent.version.desc())
    )).scalars().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail={"code": "NOT_STAGED"})
    dto = to_dto(row, config)
    # A preview is never indexable, whatever the site config says.
    dto["meta"]["noindex"] = True
    dto["preview"] = True
    return dto


def _require_preview_token(request: Request) -> None:
    """The second secret. Shared here so both preview routes enforce it alike."""
    import hmac

    from app.core.config import get_settings

    expected = getattr(get_settings(), "site_preview_token", None)
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "PREVIEW_DISABLED",
                    "message": "SEOLEAD_SITE_PREVIEW_TOKEN is not set"})
    token = request.headers.get("X-Preview-Token")
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail={"code": "PREVIEW_UNAUTHORIZED"})


@router.get("/sites/{site_id}/draft-preview/{draft_id}")
async def preview_draft(site_id: str, draft_id: uuid.UUID, request: Request,
                        session: AsyncSession = Depends(get_session)) -> dict:
    """Owner review of a draft that is not approved and therefore not staged.

    Read-only. Looking at a page must never be what advances its state.
    """
    _require_preview_token(request)
    config = _config(site_id)

    draft = (await session.execute(
        select(ContentDraft).where(ContentDraft.id == draft_id)
    )).scalar_one_or_none()
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail={"code": "NO_SUCH_DRAFT"})
    brief = (await session.execute(
        select(ContentBrief).where(ContentBrief.id == draft.content_brief_id)
    )).scalar_one_or_none()
    if brief is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail={"code": "DRAFT_HAS_NO_BRIEF"})

    gate = await evaluate_gate(session, draft)
    return draft_preview_dto(draft, brief, config, gate)


@router.post("/sites/{site_id}/leads", status_code=status.HTTP_201_CREATED)
async def create_lead(site_id: str, payload: LeadRequest,
                      session: AsyncSession = Depends(get_session)) -> dict:
    """Capture one lead. Writes to this database and nowhere else."""
    config = _config(site_id)
    site = await _site_row(session, config)

    submission = LeadSubmission(
        site_id=config.site_id, conversion_type=payload.conversion_type,
        email=payload.email, language=payload.language,
        first_name=payload.first_name, last_name=payload.last_name,
        phone=payload.phone, postcode=payload.postcode,
        qualification=payload.qualification,
        consent_processing=payload.consent_processing,
        consent_marketing=payload.consent_marketing,
        consents=payload.consents,
        attribution=payload.attribution,
        signals=SubmissionSignals(honeypot_value=payload.decoy_value,
                                  elapsed_ms=payload.elapsed_ms,
                                  client_key=payload.client_key),
    )
    try:
        result = await capture_lead(session, submission=submission, site=site,
                                    config=config, vertical_code=config.vertical)
    except LeadRejected as exc:
        # 422 rather than 400: the request was well-formed and the content was
        # refused. The message is safe — it names fields, never values.
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": exc.code, "message": exc.detail}) from exc
    except SeoLeadError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail={"code": exc.code, "message": exc.detail}) from exc

    await session.commit()

    # After commit, on purpose: the lead is safe in the database before anyone
    # is told about it, and no notification failure can turn a captured lead
    # into an error response. Destination = site configuration; transport =
    # environment; both absent are loud log lines, never exceptions.
    lead_row = await session.get(CapturedLead, uuid.UUID(result.lead_id))
    if lead_row is not None:
        await notify_lead(lead_row, config)

    return {"lead_id": result.lead_id, "state": result.state,
            "destination": result.destination}


@router.post("/sites/{site_id}/events", status_code=status.HTTP_202_ACCEPTED)
async def record_event(site_id: str, payload: EventRequest,
                       session: AsyncSession = Depends(get_session)) -> dict:
    """Record one funnel event. Unknown types are refused, not stored."""
    config = _config(site_id)
    if not config.analytics.first_party_events:
        return {"recorded": False, "reason": "first-party events are disabled"}

    # Validated before any database work: a malformed event is refused, not
    # investigated.
    try:
        event_type = SiteEventType(payload.event_type)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "UNKNOWN_EVENT_TYPE"})

    site = await _site_row(session, config)

    # Detail is bounded and stringified: an event payload is not a place to put
    # arbitrary visitor data, deliberately or accidentally.
    detail = {str(k)[:40]: str(v)[:120]
              for k, v in list(payload.detail.items())[:_MAX_EVENT_DETAIL_KEYS]}
    session.add(SiteEvent(site_id=site.id, event_type=event_type.value,
                          page_path=payload.page_path, locale=payload.locale,
                          session_id=payload.session_id, detail=detail))
    await session.commit()
    return {"recorded": True}
