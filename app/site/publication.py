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

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (ApprovalState, EvidenceStatus, PublicationState,
                            QALayer, QAStatus, QAType)
from app.core.errors import InvalidVertical, SeoLeadError
from app.models import (Approval, ContentBrief, ContentDraft, PublishedContent,
                        QAReview, ResearchPackage, SeedKeyword, Site, Vertical)
from app.services import factual_qa_v2, qa_service
from app.services.research_planner import (as_evaluated,
                                           plan_authoritative_research,
                                           unresolved_queries)
from app.site.config import SiteConfig
from app.db.base import utcnow
from app.site.content_sanitizer import (contains_external_link, parse_sections,
                                        section_text)
from app.verticals.profile import load_profile

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
    # ── Tranche structurelle du 2026-09-03 ──────────────────────────────────
    # Three more conditions, each one the absence of which let the article
    # 8a1f6e46 reach the public with a payback figure no source carried:
    #   advisory_qa       the model-assisted reviewer raised no HIGH finding
    #                     on SUBSIDY, ROI or GRID_RULE (it had, and it was
    #                     advisory by construction);
    #   research_resolved every authoritative search the planner proposed was
    #                     launched or abandoned with a written reason (five
    #                     were proposed for package f9534a41; none ran);
    #   approved_render   the approval names, by fingerprint, the render the
    #                     owner read — not an earlier revision, not an intent.
    # Defaults keep the older call sites readable; the gate always sets them.
    advisory_qa: bool = True
    research_resolved: bool = True
    approved_render: bool = True

    @property
    def passed(self) -> bool:
        return (self.factual_qa and self.seo_qa and self.approved
                and self.no_external_links and self.advisory_qa
                and self.research_resolved and self.approved_render)

    def as_dict(self) -> dict:
        return {"factual_qa": self.factual_qa, "seo_qa": self.seo_qa,
                "advisory_qa": self.advisory_qa,
                "research_resolved": self.research_resolved,
                "approved": self.approved,
                "approved_render": self.approved_render,
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

    # ── The model-assisted reviewer, on the categories where it blocks ──────
    # Its governing row is re-read under today's rule rather than trusted on
    # the `blocking` flag it was written with: the row for draft 8a1f6e46 says
    # PASSED and blocking=False on a HIGH finding about profitability without
    # public support, because in August nothing the model said could block.
    advisory = _governing([r for r in reviews
                           if r.qa_type == QAType.LLM_ASSISTED.value])

    brief = await session.get(ContentBrief, draft.content_brief_id)
    package = (await session.get(ResearchPackage, brief.research_package_id)
               if brief is not None else None)
    # The same rule the reviewer applies at judgement time, applied again
    # here on the stored row: a finding that unsources a sentence the ledger
    # carries does not block. Rows judged before the rule existed are read
    # under it, like every other rule of this gate.
    supported = [c for c in _claims_of(package)
                 if c.get("evidence_status") == EvidenceStatus.SUPPORTED.value]
    advisory_blocking = [
        f for f in ((advisory.findings if advisory else None) or [])
        if qa_service.llm_finding_blocks(f)
        and not qa_service.overruled_by_ledger(f, draft.body or "", supported)]
    advisory_ok = not advisory_blocking

    # ── Proposed research that nobody launched or gave up on ────────────────
    pending_searches, research_reason = await _pending_searches(session, package)
    research_ok = not pending_searches and research_reason is None

    # ── What was approved is what is rendered ───────────────────────────────
    current_fingerprint = (render_fingerprint(
        draft, brief, render_sources(draft.body or "", _claims_of(package)))
        if brief is not None else None)
    recorded = getattr(approval, "render_fingerprint", None) if approval else None
    render_ok = bool(approved and recorded and recorded == current_fingerprint)

    reasons: list[str] = []
    if not factual:
        reasons.append("no factual QA review is recorded for this draft")
    elif not factual_ok:
        reasons.append("factual QA did not pass")
    if not seo:
        reasons.append("no SEO QA review is recorded for this draft")
    elif not seo_ok:
        reasons.append("SEO QA did not pass")
    if not advisory_ok:
        reasons.append(
            f"model-assisted QA raised {len(advisory_blocking)} HIGH finding(s) "
            f"on a blocking category: "
            + "; ".join(
                f"[{str(f.get('category') or 'inferred')}] "
                f"{str(f.get('message', ''))[:120]}"
                for f in advisory_blocking[:3]))
    if research_reason:
        reasons.append(research_reason)
    elif pending_searches:
        reasons.append(
            f"{len(pending_searches)} proposed authoritative search(es) neither "
            f"executed nor abandoned with a reason: "
            + "; ".join(f"«{q['query']}»" for q in pending_searches[:5]))
    if not approved:
        reasons.append(
            "no human approval recorded"
            if approval is None else
            f"approval state is {approval.state}, not APPROVED")
    elif not recorded:
        reasons.append(
            "the approval names no render fingerprint: it approved an "
            "intention, not a render (re-approve with --fingerprint)")
    elif not render_ok:
        reasons.append(
            f"the approval names render {recorded[:12]}… but the current "
            f"render is {(current_fingerprint or '')[:12]}…: what was approved "
            f"is not what would be published")
    if not clean_links:
        reasons.append("the draft body contains an outbound link")

    return GateResult(factual_qa=factual_ok, seo_qa=seo_ok, approved=approved,
                      no_external_links=clean_links, reasons=reasons,
                      advisory_qa=advisory_ok, research_resolved=research_ok,
                      approved_render=render_ok)


def _claims_of(package: ResearchPackage | None) -> list[dict]:
    return list((package.facts or []) if package is not None else [])


async def _pending_searches(session: AsyncSession,
                            package: ResearchPackage | None
                            ) -> tuple[list[dict], str | None]:
    """The authoritative searches a package still owes, recomputed from its
    facts — the plan itself was never persisted before 2026-09-03, only a
    note saying « 5 targeted authoritative search(es) proposed »."""
    if package is None:
        return [], None
    keyword = await session.get(SeedKeyword, package.keyword_id)
    vertical = (await session.get(Vertical, keyword.vertical_id)
                if keyword is not None else None)
    if vertical is None:
        return [], "the package has no vertical: its research plan cannot be recomputed"
    try:
        profile = load_profile(vertical.code)
    except InvalidVertical as exc:
        return [], f"the package's vertical profile cannot be loaded: {exc}"
    plan = plan_authoritative_research(
        topic=package.query, market=package.market,
        unresolved=as_evaluated(package.facts or [], profile), profile=profile)
    return unresolved_queries(plan, package.authoritative_research), None


# ── The render, identified ───────────────────────────────────────────────────

def render_fingerprint(draft: ContentDraft, brief: ContentBrief,
                       sources: list[dict]) -> str:
    """SHA-256 of what a visitor would read: title, metas, sanitized
    sections, public price answers and rendered sources.

    Everything the fingerprint covers is derived from stored rows the same
    way the DTOs derive it, so the CLI, the preview and the gate compute the
    same value for the same render — and a different value for any other.
    """
    core_evidence = brief.core_answer_evidence or {}
    payload = {
        "title": draft.title,
        "meta_title": draft.meta_title,
        "meta_description": draft.meta_description,
        "sections": parse_sections(draft.body or ""),
        "answers": [_public_answer(a)
                    for a in (core_evidence.get("answers") or [])],
        "sources": sources,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def compute_fingerprint(session: AsyncSession,
                              draft: ContentDraft) -> tuple[str, list[dict]]:
    """The one entry point for « what is the fingerprint of this draft's
    render »: the CLI shows it, the approval records it, the gate checks it."""
    brief = await session.get(ContentBrief, draft.content_brief_id)
    if brief is None:
        raise PublicationRefused("the draft has no brief; nothing to render")
    package = await session.get(ResearchPackage, brief.research_package_id)
    sources = render_sources(draft.body or "", _claims_of(package))
    return render_fingerprint(draft, brief, sources), sources


# ── The sources a page shows ─────────────────────────────────────────────────

def render_sources(body: str, claims: list[dict]) -> list[dict]:
    """The sources behind the figures a body states, as the page may show them.

    The « méthode » block promises « chaque montant affiché provient d'une
    source publiée ». Until 2026-09-03 the page showed no source at all, so
    the promise was unverifiable by the reader. This lists, for every figure
    the body states (unit, range end, year), the SUPPORTED claims carrying it
    and the evidence behind them — name, tier, region, date, and the figures
    it carries. No URL: an official authority is named by its host as text;
    a commercial or specialist source is described, not advertised (Phase
    3.3 shipped a competitor link the one time a page carried references).
    """
    needed = factual_qa_v2.body_segments(body)
    ranges = factual_qa_v2.body_ranges(body)
    units = factual_qa_v2.body_units(body)
    if not needed:
        return []
    supported = [c for c in claims
                 if c.get("evidence_status") == EvidenceStatus.SUPPORTED.value]
    found: dict[str, dict] = {}
    for claim in supported:
        text = str(claim.get("claim", ""))
        labels = factual_qa_v2.quantity_labels(text)
        # The same coverage rule as the gate: one end of a range does not
        # source a figure, so it is not listed as its source either.
        figures = {s for s in needed
                   if s in labels
                   and factual_qa_v2.covers(claim, {s}, ranges, units)}
        if not figures:
            continue
        for evidence in claim.get("evidence") or []:
            if not evidence.get("supports"):
                continue
            url = str(evidence.get("url") or "")
            key = url or f"{evidence.get('source_ref')}"
            if not key:
                continue
            tier = str(evidence.get("source_quality") or "UNKNOWN").upper()
            entry = found.setdefault(key, {
                "name": _host_of(url) if tier == "OFFICIAL" else None,
                "tier": tier,
                "authority_type": evidence.get("authority_type"),
                "region": evidence.get("region") or claim.get("region"),
                "date": _source_date(evidence),
                "freshness": evidence.get("freshness_status"),
                "_figures": {},
            })
            for figure in figures:
                entry["_figures"].setdefault(figure, labels[figure])
    out = []
    for entry in found.values():
        figures = entry.pop("_figures")
        entry["figures"] = [figures[k] for k in sorted(figures)]
        out.append(entry)
    # Official first, then by name, then by date — stable across runs, which
    # the fingerprint depends on.
    out.sort(key=lambda e: (e["tier"] != "OFFICIAL", e["name"] or "~",
                            e["date"] or "~", e["figures"]))
    return out


def _host_of(url: str) -> str | None:
    host = urlsplit(url).hostname if url else None
    return host.removeprefix("www.") if host else None


def _source_date(evidence: dict) -> str | None:
    """The date a source is shown with: what it says about itself, else the
    day it was published, else nothing — never the day it was retrieved."""
    for key in ("effective_from", "published_at"):
        value = evidence.get(key)
        if value:
            return str(value)[:10]
    return None


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
    package = await session.get(ResearchPackage, brief.research_package_id)
    sources = render_sources(draft.body or "", _claims_of(package))
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
        # The sources behind the figures, frozen with the figures: a page
        # re-rendered after the research tables move on still shows what it
        # rested on the day it was approved.
        sources=sources,
        qa_provenance=gate.as_dict(),
        canonical_path=_canonical_path(config, locale, slug),
        # Forced on, whatever the site-wide gate says: a STAGED page is never
        # public (the preview route is its only surface, and that one forces
        # its own noindex too). Publication recomputes this from the site's
        # indexability — that is where the flag becomes real.
        noindex=True,
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
                      config: SiteConfig, gate: GateResult,
                      sources: list[dict] | None = None) -> dict:
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
    sources = list(sources or [])
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
        "sources": sources,
        "version": 0, "state": "DRAFT_PREVIEW",
        "updated_at": None, "preview": True,
        # The reviewer needs to see what is still missing. This is the one place
        # gate detail is shown, and it is behind the preview token.
        "gate": gate.as_dict(),
        # What the reviewer is looking at, named. An approval must quote it.
        "fingerprint": render_fingerprint(draft, brief, sources),
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
        "sources": list(getattr(snapshot, "sources", None) or []),
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
