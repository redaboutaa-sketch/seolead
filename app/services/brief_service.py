"""ContentBrief construction — hybrid by design.

The split is deliberate and is the mission's rule made concrete: **provenance is
deterministic, synthesis is optional.**

Deterministic, always:
  required_facts, required_sources, cautionary_claims, missing_information,
  content type, intent, slug, CTA choice.

LLM, only if configured, and only ever additive:
  a better title, a richer outline.

The consequence is that a brief built with no LLM at all is still complete and
still honest, and that an LLM cannot delete an unresolved fact by rewriting around
it — the unresolved list is assembled after synthesis, from the package, not from
the model's output.
"""
from __future__ import annotations

import json
import logging

from app.core.enums import ContentType, SearchIntent
from app.core.errors import SeoLeadError
from app.providers.llm.base import (LLMCapability, LLMProvider, LLMRequest)
from app.services.intent import select_content_type, slugify
from app.verticals.profile import VerticalProfile

logger = logging.getLogger(__name__)

_MAX_REQUIRED_FACTS = 12
_MAX_OUTLINE_SECTIONS = 9


# Categories whose SUPPORTED claims can answer a price question. MARKET_PRICE is
# the residual bucket and is included because a figure it carries is still a
# figure — the wording rules downstream are what keep it from being called an
# average.
_PRICE_ANSWER_CATEGORIES = ("OBSERVED_PRICE_RANGE", "MARKET_AVERAGE",
                            "MARKET_PRICE", "VENDOR_PRICE")
_MAX_CORE_EVIDENCE = 6


def _core_question(query: str, intent: SearchIntent, profile: VerticalProfile,
                   supported: list[dict]) -> dict:
    """What this page must answer, and whether the evidence lets it.

    Phase 3.4's live draft was titled "Prix des panneaux solaires en Belgique" and
    contained no price. Factual QA passed because it asserted nothing checkable —
    a vacuous pass. Recording the core question and its answerability separately is
    what makes that state visible instead of silently acceptable.

    Two outcomes only, and both are honest. Either the evidence answers the
    question and the page must say so, or it does not and the page must say *that*.
    There is no third branch where the writer fills the gap.
    """
    from app.services.price_normalization import (extract_price_context,
                                                  observed_range)

    policy = profile.price_policy or {}
    required = {i.upper() for i in policy.get("answer_required_intents") or ()}
    terms = [t.casefold() for t in policy.get("price_query_terms") or ()]
    normalized = query.casefold()
    # A price question is one the vertical's own vocabulary recognises. Nothing
    # here knows that "prix" is French or that solar panels have a price.
    if (not policy.get("enabled") or intent.value not in required
            or not any(term in normalized for term in terms)):
        return {"question": None, "status": "NOT_APPLICABLE",
                "must_answer_directly": False, "evidence": [], "range": None}

    question = query.strip()
    answers, contexts = [], []
    for claim in supported:
        if claim.get("category") not in _PRICE_ANSWER_CATEGORIES:
            continue
        context = extract_price_context(_claim_text(claim))
        if context is None or not context.is_usable:
            # A bare amount with no stated basis is not an answer: €6 000 could be
            # a total, a per-kWc rate or a per-m² figure.
            continue
        contexts.append(context)
        answers.append({
            "claim": _claim_text(claim),
            "category": claim.get("category"),
            "price_context": context.as_dict(),
            "qualification": ("a figure this source reports"
                              if claim.get("category") != "MARKET_AVERAGE"
                              else "an average this source reports"),
            "sources": [e.get("url") for e in claim.get("evidence") or []
                        if e.get("supports")],
        })

    if not answers:
        return {
            "question": question, "status": "CORE_QUESTION_UNRESOLVED",
            "must_answer_directly": False, "evidence": [], "range": None,
            "note": ("The core question of this page is unresolved: no price claim "
                     "reached SUPPORTED with a stated basis. The page must say so "
                     "plainly rather than imply an answer the research did not "
                     "produce."),
        }

    minimum = int(policy.get("observed_range_min_sources", 2) or 2)
    return {
        "question": question, "status": "EVIDENCE_AVAILABLE",
        "must_answer_directly": True,
        "evidence": answers[:_MAX_CORE_EVIDENCE],
        # None when the observations are not comparable — different bases or VAT
        # treatments are not a range, and stating one would invent a figure.
        "range": observed_range(contexts, minimum=minimum),
    }


def _claim_text(item: dict) -> str:
    """Claim text from a V3 claim or a V2 fact, whichever shape arrived."""
    return str(item.get("claim") or item.get("fact") or "")


def _default_outline(
    query: str, content_type: ContentType, profile: VerticalProfile,
    user_questions: list[str],
) -> list[dict]:
    """A structurally sound outline that needs no model.

    Shaped by content type rather than by vertical, so it holds for any vertical.
    """
    heading = {
        ContentType.COMPARISON: [
            "Ce que compare cette page", "Critères de comparaison",
            "Comparaison détaillée", "Quel choix selon votre situation",
            "Questions fréquentes", "Prochaine étape",
        ],
        ContentType.LANDING_PAGE: [
            "Le besoin auquel cette page répond", "Ce qui est inclus",
            "Comment se déroule la démarche", "Ce qu'il faut vérifier avant",
            "Questions fréquentes", "Prochaine étape",
        ],
        ContentType.GUIDE: [
            "Ce que vous saurez à la fin", "Les notions de base",
            "Les facteurs qui comptent vraiment", "Les erreurs fréquentes",
            "Ce qui dépend de votre situation", "Questions fréquentes",
            "Prochaine étape",
        ],
    }.get(content_type, [
        "Introduction", "Points essentiels", "Ce qu'il faut savoir",
        "Questions fréquentes", "Prochaine étape",
    ])

    sections = [{"heading": h, "purpose": "", "source_refs": []} for h in heading]

    # Observed themes become real sections rather than decoration.
    for question in user_questions[:3]:
        sections.insert(-1, {"heading": question, "purpose": "Observed theme",
                             "source_refs": []})
    return sections[:_MAX_OUTLINE_SECTIONS]


def _select_cta(intent: SearchIntent, profile: VerticalProfile) -> dict:
    for option in profile.cta_options:
        if intent.value in option.intents:
            return {"code": option.code, "label": option.label,
                    "reason": f"matches {intent.value} intent"}
    if profile.cta_options:
        fallback = profile.cta_options[0]
        return {"code": fallback.code, "label": fallback.label,
                "reason": "vertical default"}
    # A brief with no conversion strategy is a brief for a page that exists only to
    # rank. The mission forbids that, so this is surfaced rather than defaulted.
    return {"code": None, "label": None,
            "reason": "no CTA configured for this vertical — must be resolved before publication"}


def build_brief_payload(
    package: dict,
    *,
    profile: VerticalProfile,
    query: str,
) -> dict:
    """The deterministic core. Never calls a model."""
    intent = SearchIntent(package["intent"])
    content_type = select_content_type(query, intent, profile)

    sources = package.get("sources") or []

    # V3 packages carry evaluated atomic claims; V2 carried page-level facts.
    # Reading `supported_claims` first means the brief gets propositions rather
    # than excerpts wherever the newer builder ran.
    supported_facts = package.get("supported_claims")
    if supported_facts is None:
        supported_facts = [f for f in (package.get("facts") or [])
                           if f.get("supported")]

    required_facts = [
        {"fact": _claim_text(f), "source_ref": f.get("source_ref"),
         "observability": f.get("observability")
         or f.get("evidence_status"),
         "category": f.get("category"),
         "evidence_status": f.get("evidence_status")}
        for f in supported_facts[:_MAX_REQUIRED_FACTS]
    ]

    used_refs = {f["source_ref"] for f in required_facts}
    required_sources = [
        {"ref": s["ref"], "url": s["url"], "title": s["title"],
         "published_at": s["published_at"]}
        for s in sources if s["ref"] in used_refs and s.get("url")
    ]

    # Restricted topics are cautionary unless a supported claim carries them.
    cautionary: list[dict] = []
    for claim in profile.restricted_claims:
        supported_here = any(
            claim.casefold() in _claim_text(f).casefold() for f in supported_facts
        )
        cautionary.append({
            "topic": claim,
            "rule": "may_not_be_asserted_without_dated_source",
            "has_supported_evidence": supported_here,
        })

    missing = list(package.get("unresolved_questions") or [])
    summary = package.get("confidence_summary") or {}
    if summary.get("partial_observation"):
        missing.append(
            "Research was partial: at least one source could not be observed. "
            "Coverage gaps must not be presented as absence of information."
        )

    core = _core_question(query, intent, profile, list(supported_facts))
    if core["status"] == "EVIDENCE_AVAILABLE":
        # The answer leads. A price page that buries its price under six sections
        # of context has not answered the query.
        for answer in reversed(core["evidence"][:3]):
            required_facts.insert(0, {
                "fact": answer["claim"], "source_ref": None,
                "observability": None, "category": answer["category"],
                "evidence_status": "SUPPORTED",
                "price_context": answer["price_context"]})
        required_facts = required_facts[:_MAX_REQUIRED_FACTS]
    elif core["status"] == "CORE_QUESTION_UNRESOLVED":
        missing.insert(0, core["note"])

    title = query.strip()
    title = title[0].upper() + title[1:] if title else "Untitled"

    return {
        "core_question": core["question"],
        "core_answer_status": core["status"],
        "core_answer_evidence": {"answers": core["evidence"],
                                 "observed_range": core.get("range")},
        "must_answer_directly": core["must_answer_directly"],
        "content_type": content_type.value,
        "primary_query": query,
        "search_intent": intent.value,
        "target_audience": profile.target_audience,
        "objective": profile.business_objective,
        "recommended_title": title,
        "recommended_slug": slugify(query),
        "outline": _default_outline(
            query, content_type, profile, package.get("user_questions") or []
        ),
        "key_questions": list(package.get("user_questions") or [])[:10],
        "required_facts": required_facts,
        "required_sources": required_sources,
        "cautionary_claims": cautionary,
        "cta_strategy": _select_cta(intent, profile),
        "internal_linking_notes": (
            "No sibling content exists yet in this vertical; revisit once a second "
            "asset is published."
        ),
        "missing_information": missing,
        "generated_by": "deterministic",
    }


_SYNTHESIS_SYSTEM = (
    "You are an SEO content strategist. You improve the TITLE and OUTLINE of a "
    "content brief. You must not invent facts, statistics, prices, subsidies or "
    "regulations. You must not remove or soften any listed limitation. "
    "Reply with JSON only: {\"recommended_title\": str, \"outline\": "
    "[{\"heading\": str, \"purpose\": str}]}."
)


async def enrich_brief_with_llm(
    payload: dict, *, llm: LLMProvider, correlation_id: str,
) -> dict:
    """Optionally improve title and outline. Never touches provenance fields.

    Any failure returns the deterministic payload unchanged — a brief is more
    useful than an exception, and the deterministic version was already complete.
    """
    if not llm.configured:
        return payload

    prompt = json.dumps({
        "primary_query": payload["primary_query"],
        "content_type": payload["content_type"],
        "search_intent": payload["search_intent"],
        "target_audience": payload["target_audience"],
        "key_questions": payload["key_questions"],
        "supported_facts": [f["fact"] for f in payload["required_facts"]],
        "current_outline": [s["heading"] for s in payload["outline"]],
    }, ensure_ascii=False)

    try:
        response = await llm.generate(LLMRequest(
            capability=LLMCapability.CONTENT_BRIEF,
            system=_SYNTHESIS_SYSTEM,
            prompt=prompt,
            response_format="json",
            temperature=0.3,
            max_tokens=1200,
            correlation_id=correlation_id,
        ))
        parsed = json.loads(response.content)
    except (SeoLeadError, json.JSONDecodeError, TypeError) as exc:
        logger.warning("brief synthesis skipped: %s", type(exc).__name__,
                       extra={"correlation_id": correlation_id})
        return payload

    enriched = dict(payload)
    title = parsed.get("recommended_title")
    if isinstance(title, str) and title.strip():
        enriched["recommended_title"] = title.strip()[:300]

    outline = parsed.get("outline")
    if isinstance(outline, list) and outline:
        rebuilt = [
            {"heading": str(s.get("heading", "")).strip()[:200],
             "purpose": str(s.get("purpose", "")).strip()[:300],
             "source_refs": []}
            for s in outline if isinstance(s, dict) and s.get("heading")
        ]
        if rebuilt:
            enriched["outline"] = rebuilt[:_MAX_OUTLINE_SECTIONS]

    enriched["generated_by"] = "hybrid"
    return enriched
