"""The publication gate: approved content → a renderable snapshot.

One rule governs this module, and it is worth stating before the code: **QA passing
is not permission to publish, and human approval is not publication.** Three
independent conditions must hold before a draft may be staged — factual QA passed,
SEO QA passed, and a human recorded an approval — and a fourth, an explicit publish
action against a site allowed to serve published content, before it is live.

There are three gates, not two, and they are deliberately separate:

    reachable   the hostname resolves and Traefik routes it
    publishable `is_publishable` — a domain plus an explicit owner decision;
                content may be SERVED at its real URL
    indexable   `is_indexable` — additionally out of staging with indexing
                explicitly allowed; crawlers may KEEP it

A soft launch lives between the second and the third: real URL, real visitors, no
search engines. Collapsing publishable into indexable — as this module did before
the site had a domain — makes that state unreachable.

The snapshot is a copy, not a reference. `PublishedContent` stores the sanitized
sections that were approved, so re-running the pipeline, editing the draft, or
changing the renderer cannot alter a page a person signed off on. That costs some
duplication and buys the only property that matters here: what was approved is what
is served.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (ApprovalState, PublicationState, QALayer, QAStatus,
                            QAType)
from app.core.errors import SeoLeadError
from app.models import (Approval, ContentBrief, ContentDraft, PublishedContent,
                        QAReview, Site)
from app.site.config import SiteConfig
from app.db.base import utcnow
from app.site.content_sanitizer import (contains_external_link, parse_sections,
                                        section_text)

logger = logging.getLogger(__name__)


class PublicationRefused(SeoLeadError):
    """The gate said no. The message is the reason, and it is operator-facing."""

    code = "PUBLICATION_REFUSED"


# Transitions the gate permits. `PUBLISHED → PUBLISHED` is absent: republishing is
# a new version, not an idempotent no-op that silently keeps stale content live.
_ALLOWED: dict[PublicationState, frozenset[PublicationState]] = {
    PublicationState.DRAFT: frozenset({PublicationState.QA_FAILED,
                                       PublicationState.PENDING_APPROVAL,
                                       PublicationState.ARCHIVED}),
    PublicationState.QA_FAILED: frozenset({PublicationState.DRAFT,
                                           PublicationState.ARCHIVED}),
    PublicationState.PENDING_APPROVAL: frozenset({PublicationState.APPROVED,
                                                  PublicationState.QA_FAILED,
                                                  PublicationState.ARCHIVED}),
    PublicationState.APPROVED: frozenset({PublicationState.STAGED,
                                          PublicationState.ARCHIVED}),
    PublicationState.STAGED: frozenset({PublicationState.PUBLISHED,
                                        PublicationState.APPROVED,
                                        PublicationState.ARCHIVED}),
    PublicationState.PUBLISHED: frozenset({PublicationState.ARCHIVED}),
    PublicationState.ARCHIVED: frozenset(),
}

_SLUG_SAFE = re.compile(r"[^a-z0-9]+")


def can_transition(current: PublicationState, requested: PublicationState) -> bool:
    return requested in _ALLOWED.get(current, frozenset())


def assert_transition(current: PublicationState,
                      requested: PublicationState) -> None:
    if not can_transition(current, requested):
        raise PublicationRefused(
            f"{current.value} cannot become {requested.value}")


def slugify(text: str) -> str:
    import unicodedata
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_only = normalized.encode("ascii", "ignore").decode()
    return _SLUG_SAFE.sub("-", ascii_only.lower()).strip("-")[:255] or "page"


@dataclass(frozen=True)
class GateResult:
    """Why a draft may or may not be staged. Always fully populated.

    Reporting every condition rather than the first failure means an operator sees
    the whole distance to publishable in one look instead of fixing one blocker at
    a time.
    """

    factual_qa: bool
    seo_qa: bool
    approved: bool
    no_external_links: bool
    reasons: list[str]

    @property
    def passed(self) -> bool:
        return (self.factual_qa and self.seo_qa and self.approved
                and self.no_external_links)

    def as_dict(self) -> dict:
        return {"factual_qa": self.factual_qa, "seo_qa": self.seo_qa,
                "approved": self.approved,
                "no_external_links": self.no_external_links,
                "passed": self.passed, "reasons": list(self.reasons)}


async def evaluate_gate(session: AsyncSession, draft: ContentDraft) -> GateResult:
    """Check every publication precondition for a draft."""
    reviews = (await session.execute(
        select(QAReview).where(QAReview.content_draft_id == draft.id)
    )).scalars().all()

    deterministic = [r for r in reviews if r.qa_type == QAType.DETERMINISTIC.value]
    # Two deterministic reviews are recorded per draft — factual and SEO. Since
    # Phase 4 each row says which it is. Rows written before that carry no layer,
    # and are classified by their finding codes; that inference is why the column
    # exists, because a clean review has no codes to infer from.
    factual = [r for r in deterministic
               if (r.layer or (QALayer.FACTUAL.value if _is_factual(r)
                               else QALayer.SEO.value)) == QALayer.FACTUAL.value]
    seo = [r for r in deterministic
           if (r.layer or (QALayer.FACTUAL.value if _is_factual(r)
                           else QALayer.SEO.value)) == QALayer.SEO.value]

    # ── The verdict that governs is the latest one ───────────────────────────
    # A draft can carry several verdicts for one layer, because a re-judgement
    # appends rather than corrects: the row saying draft 8a1f6e46 failed on
    # 2026-08-30 is true of that day and stays readable for good. What it must
    # not do is govern publication after a later verdict superseded it.
    #
    # `revision` orders them; `created_at` breaks a tie only if two rows somehow
    # share a revision. Requiring ALL of them to pass — which is what this did —
    # meant the first refusal was permanent and the only way past it was to
    # rewrite history or pay for the whole run again.
    latest_factual = _governing(factual)
    latest_seo = _governing(seo)

    factual_ok = bool(latest_factual) and (
        latest_factual.status == QAStatus.PASSED.value
        and not latest_factual.blocking_issues)
    seo_ok = bool(latest_seo) and (
        latest_seo.status == QAStatus.PASSED.value
        and not latest_seo.blocking_issues)

    approval = (await session.execute(
        select(Approval).where(Approval.content_draft_id == draft.id)
    )).scalar_one_or_none()
    approved = bool(approval and approval.state == ApprovalState.APPROVED.value)

    clean_links = not contains_external_link(draft.body or "")

    reasons: list[str] = []
    if not factual:
        reasons.append("no factual QA review is recorded for this draft")
    elif not factual_ok:
        reasons.append("factual QA did not pass")
    if not seo:
        reasons.append("no SEO QA review is recorded for this draft")
    elif not seo_ok:
        reasons.append("SEO QA did not pass")
    if not approved:
        reasons.append(
            "no human approval recorded"
            if approval is None else
            f"approval state is {approval.state}, not APPROVED")
    if not clean_links:
        reasons.append("the draft body contains an outbound link")

    return GateResult(factual_qa=factual_ok, seo_qa=seo_ok, approved=approved,
                      no_external_links=clean_links, reasons=reasons)


def _governing(reviews: list[QAReview]) -> QAReview | None:
    """The verdict of a layer that decides, out of every verdict it carries."""
    if not reviews:
        return None
    return max(reviews, key=lambda r: (getattr(r, "revision", 1) or 1,
                                       r.created_at))


def _is_factual(review: QAReview) -> bool:
    """Legacy classifier for rows written before the `layer` column existed."""
    codes = {str(f.get("code")) for f in (review.findings or [])}
    codes |= {str(f.get("code")) for f in (review.blocking_issues or [])}
    factual_codes = {"UNSUPPORTED_DRAFT_CLAIM", "HIGH_RISK_CLAIM_ASSERTED",
                     "CONFLICTING_EVIDENCE_ASSERTED", "RESTRICTED_CLAIM_QUANTIFIED"}
    if codes & factual_codes:
        return True
    seo_codes = {"NO_QUANTIFIED_ANSWER", "EXTERNAL_LINK_IN_BODY", "MISSING_TITLE",
                 "META_TITLE_TOO_LONG", "WEAK_STRUCTURE", "SERP_CONTENT_GAP",
                 "UNSUPPORTED_NUMERIC_CLAIM", "VAT_STATUS_GENERALISED",
                 "META_DESCRIPTION_TOO_LONG", "BODY_TOO_SHORT"}
    if codes & seo_codes:
        return False
    # A clean review carries no codes at all. Fall back to the score field, which
    # the factual reviewer populates from the claim ledger.
    return bool((review.findings is not None) and review.score == 100
                and _has_ledger(review))


def _has_ledger(review: QAReview) -> bool:
    return isinstance(getattr(review, "findings", None), list)


async def stage_content(
    session: AsyncSession, *, draft: ContentDraft, brief: ContentBrief,
    site: Site, config: SiteConfig, locale: str | None = None,
    slug: str | None = None,
) -> PublishedContent:
    """Create a STAGED snapshot from an approved, QA-passed draft.

    Refuses on any failed precondition. Staging is not publication: the snapshot
    is reachable through the preview route only, and `noindex` is forced on for
    every site that is not explicitly indexable.
    """
    gate = await evaluate_gate(session, draft)
    if not gate.passed:
        raise PublicationRefused("; ".join(gate.reasons))

    locale = locale or config.default_language
    if locale not in (config.supported_languages or [config.default_language]):
        raise PublicationRefused(
            f"locale {locale!r} is not supported by site {config.site_id}")

    slug = slug or slugify(brief.recommended_slug or brief.primary_query)
    sections = parse_sections(draft.body or "")
    if contains_external_link(section_text(sections)):
        # Defence in depth: the raw body was checked above, the parsed output is
        # checked here, because the two could diverge if the parser changed.
        raise PublicationRefused("sanitized content still contains a link")

    next_version = (await session.execute(
        select(func.coalesce(func.max(PublishedContent.version), 0)).where(
            PublishedContent.site_id == site.id,
            PublishedContent.locale == locale,
            PublishedContent.slug == slug)
    )).scalar_one() + 1

    core_evidence = brief.core_answer_evidence or {}
    snapshot = PublishedContent(
        site_id=site.id, content_draft_id=draft.id, locale=locale, slug=slug,
        version=next_version, content_type=brief.content_type,
        search_intent=brief.search_intent,
        state=PublicationState.STAGED.value,
        title=draft.title, meta_title=draft.meta_title,
        meta_description=draft.meta_description,
        sections=sections,
        price_evidence={
            "core_question": brief.core_question,
            "core_answer_status": brief.core_answer_status,
            # Only the qualification a visitor may see. Claim identifiers, source
            # URLs and evidence internals stay in the research tables.
            "answers": [_public_answer(a)
                        for a in (core_evidence.get("answers") or [])],
            "observed_range": core_evidence.get("observed_range"),
        },
        cta=brief.cta_strategy or {},
        qa_provenance=gate.as_dict(),
        canonical_path=_canonical_path(config, locale, slug),
        noindex=not config.is_indexable,
        staged_at=utcnow(),
    )
    session.add(snapshot)
    await session.flush()
    logger.info("content staged", extra={"slug": slug, "locale": locale,
                                         "version": next_version})
    return snapshot


def _public_answer(answer: dict) -> dict:
    """Strip a price answer down to what a visitor may see.

    The claim text and its price context are public — they are the answer. The
    source URLs are not: Phase 3.3 shipped a competitor link, and a "sources"
    block in the page would reintroduce it by another route.
    """
    context = answer.get("price_context") or {}
    return {
        "claim": answer.get("claim"),
        "category": answer.get("category"),
        "qualification": answer.get("qualification"),
        "amounts": context.get("amounts") or [],
        "currency": context.get("currency"),
        "basis": context.get("basis"),
        "vat_status": context.get("vat_status"),
        "system_size_kwp": context.get("system_size_kwp") or [],
        "battery_included": context.get("battery_included"),
        "installation_included": context.get("installation_included"),
        "is_range": context.get("is_range"),
    }


def draft_preview_dto(draft: ContentDraft, brief: ContentBrief,
                      config: SiteConfig, gate: GateResult) -> dict:
    """Render an unapproved draft for owner review, without staging it.

    §38 of the Phase 4 brief allows exactly this: a page whose approval is still
    absent may be looked at through an explicit admin path, and may not be staged
    or published. Nothing is written — the DTO is built and discarded — so
    reviewing a draft cannot advance its state as a side effect.

    The content still goes through the same sanitizer, because "it is only a
    preview" is precisely when an unsanitized body would slip through.
    """
    locale = config.default_language
    slug = slugify(brief.recommended_slug or brief.primary_query)
    core_evidence = brief.core_answer_evidence or {}
    return {
        "slug": slug, "locale": locale, "type": brief.content_type,
        "search_intent": brief.search_intent, "title": draft.title,
        "meta": {"title": draft.meta_title or draft.title,
                 "description": draft.meta_description,
                 "canonical_path": _canonical_path(config, locale, slug),
                 "canonical_url": config.canonical_url(
                     _canonical_path(config, locale, slug)),
                 # An unapproved draft is never indexable, on any site.
                 "noindex": True},
        "sections": parse_sections(draft.body or ""),
        "price_evidence": {
            "core_question": brief.core_question,
            "core_answer_status": brief.core_answer_status,
            "answers": [_public_answer(a)
                        for a in (core_evidence.get("answers") or [])],
            "observed_range": core_evidence.get("observed_range"),
        },
        "cta": {"primary": config.conversion.primary_cta,
                "primary_label": config.conversion.primary_cta_label,
                "secondary": config.conversion.secondary_cta,
                "secondary_label": config.conversion.secondary_cta_label,
                "brief_cta": (brief.cta_strategy or {}).get("code")},
        "version": 0, "state": "DRAFT_PREVIEW",
        "updated_at": None, "preview": True,
        # The reviewer needs to see what is still missing. This is the one place
        # gate detail is shown, and it is behind the preview token.
        "gate": gate.as_dict(),
    }


def _canonical_path(config: SiteConfig, locale: str, slug: str) -> str:
    prefix = config.locale_prefix(locale)
    return f"{prefix}/{slug}".replace("//", "/")


async def publish_content(session: AsyncSession, *, snapshot: PublishedContent,
                          config: SiteConfig) -> PublishedContent:
    """Take a staged snapshot live. Requires the site to be publishable at all."""
    current = PublicationState(snapshot.state)
    assert_transition(current, PublicationState.PUBLISHED)

    if not config.is_publishable:
        raise PublicationRefused(
            f"site {config.site_id} may not serve published content: "
            f"domain={'set' if config.domain else 'missing'}, "
            f"allow_publication={config.seo.allow_publication}")

    # Supersede whatever is currently live at this address, so the partial unique
    # index never sees two live rows.
    live = (await session.execute(
        select(PublishedContent).where(
            PublishedContent.site_id == snapshot.site_id,
            PublishedContent.locale == snapshot.locale,
            PublishedContent.slug == snapshot.slug,
            PublishedContent.state == PublicationState.PUBLISHED.value)
    )).scalars().all()
    for row in live:
        row.state = PublicationState.ARCHIVED.value

    snapshot.state = PublicationState.PUBLISHED.value
    # Published is not the same as indexable. A page served on the public route
    # while the site is still noindex keeps its noindex — that is a soft launch,
    # not an oversight.
    snapshot.noindex = not config.is_indexable
    snapshot.published_at = utcnow()
    await session.flush()
    return snapshot


def to_dto(snapshot: PublishedContent, config: SiteConfig) -> dict:
    """The publication-safe DTO the site consumes.

    Deliberately narrow. No provider metadata, no QA notes, no rejected evidence,
    no claim identifiers, no cost data — the frontend cannot leak what it was
    never given.
    """
    return {
        "slug": snapshot.slug,
        "locale": snapshot.locale,
        "type": snapshot.content_type,
        "search_intent": snapshot.search_intent,
        "title": snapshot.title,
        "meta": {
            "title": snapshot.meta_title or snapshot.title,
            "description": snapshot.meta_description,
            "canonical_path": snapshot.canonical_path,
            # Absolute, built from the configured production origin — never from
            # the host that happens to be serving the request. A canonical is a
            # statement about where a page really lives, and the staging host is
            # not that place.
            "canonical_url": config.canonical_url(snapshot.canonical_path or "/"),
            "noindex": snapshot.noindex or not config.is_indexable,
        },
        "sections": snapshot.sections or [],
        "price_evidence": snapshot.price_evidence or {},
        "cta": {
            "primary": config.conversion.primary_cta,
            "primary_label": config.conversion.primary_cta_label,
            "secondary": config.conversion.secondary_cta,
            "secondary_label": config.conversion.secondary_cta_label,
            "brief_cta": (snapshot.cta or {}).get("code"),
        },
        "version": snapshot.version,
        "state": snapshot.state,
        # Both dates travel because the Article schema distinguishes them:
        # datePublished is the publication act, dateModified the last touch.
        "published_at": (snapshot.published_at.isoformat()
                         if snapshot.published_at else None),
        "updated_at": (snapshot.updated_at.isoformat()
                       if snapshot.updated_at else None),
    }
