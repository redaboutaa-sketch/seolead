"""Draft generation.

There is no deterministic fallback here, and that is the point. If no LLM is
configured the pipeline raises LLMNotConfigured and stops. A template that stitched
the brief into prose would produce something that *looks* like an article and was
written by nobody — the exact failure mode the mission forbids.

The system prompt is the last line of defence before QA. It is built from the
brief, so its prohibitions are specific to this vertical and this evidence rather
than generic boilerplate a model can talk itself past.
"""
from __future__ import annotations

import json
import logging

from app.core.errors import LLMProviderError
from app.providers.llm.base import (LLMCapability, LLMProvider, LLMRequest,
                                    LLMResponse)

logger = logging.getLogger(__name__)

_BASE_RULES = """You are writing a page for a real business. Follow every rule.

EVIDENCE
- Use ONLY the supplied research facts. They are the only things you may state as fact.
- They are also the SUBSTANCE of the page, not merely a permitted vocabulary. Build
  the article on them: every supplied fact that belongs somewhere in the outline
  must appear, stated faithfully and in its own words. A page that states three of
  twelve researched facts tells the reader far less than was actually established,
  and padding the gap with generalities is exactly what makes a page worthless.
- Leave a fact out only when it genuinely fits nowhere in the outline. Never force
  one in, never restate the same fact in several sections to look thorough, and
  never turn a fact into a heading with no content under it.
- If something is not in the supplied facts, either omit it or mark it explicitly as
  something the reader should verify.
- Never invent a statistic, price, percentage, date, subsidy, tax rate, regulation,
  study, source or testimonial.
- Never present an estimate as a measurement.

LIMITATIONS
- The listed limitations describe real gaps in what was researched. You must not
  write around them as if they did not exist, and you must not resolve them from
  your own knowledge.

TONE AND STRUCTURE
- Write for the stated audience, in the stated language.
- Answer the reader's actual question first. Do not pad.
- No keyword stuffing: use the primary query naturally, a handful of times at most.
- No manufactured urgency, no guaranteed outcomes, no pressure tactics.
- Use markdown: a single H1, then H2 sections following the outline.

LINKS
- Do NOT output any markdown link or URL in the body. Never link to another
  company, comparison site or installer: a published page that sends its reader
  to a competitor has failed. Sources are recorded separately; they are not
  citations in the copy.

PRICE AND QUANTITY WORDING
- A figure reported by one source is what THAT SOURCE reports. Say so.
- A range observed across the supplied sources is an observed range. Never call
  it an average, a market price, or "the" price in Belgium.
- Never turn an observed sample into a national average.
- Always carry a price's stated basis: per watt-peak, per kWc, per m² or for the
  whole installation, with VAT status when it is given. A figure without its
  basis is misleading, and figures on different bases must never be combined.
- VAT status belongs to ONE figure, never to a list. If some supplied figures say
  VAT included and others say nothing, you may not write that "these prices
  include VAT" — say it only about the figures whose source said it.

CONVERSION
- Close with one clear, honest next step matching the stated CTA.
- The call to action must not promise anything the evidence does not support.

OUTPUT
Reply with JSON only:
{"title": str, "meta_title": str, "meta_description": str, "body": str}
- meta_title: <= 60 characters
- meta_description: <= 155 characters
- body: markdown, starting with "# "
"""


def build_generation_prompt(brief: dict, package: dict) -> tuple[str, str]:
    """Return (system, user) messages. Pure — unit-testable without a provider."""
    forbidden = [
        c["topic"] for c in brief.get("cautionary_claims", [])
        if not c.get("has_supported_evidence")
    ]

    system = _BASE_RULES

    # The core question, when the evidence supports answering it.
    core_evidence = brief.get("core_answer_evidence") or {}
    if brief.get("must_answer_directly") and core_evidence.get("answers"):
        system += (
            f"\nCORE QUESTION — YOU MUST ANSWER IT DIRECTLY\n"
            f"This page exists to answer: {brief.get('core_question')}\n"
            f"Answer it explicitly in the opening section, before any context, "
            f"using ONLY the supplied price evidence and carrying each figure's "
            f"basis and VAT status. Do not defer the answer to a call to action, "
            f"and do not tell the reader to ask a professional instead of giving "
            f"the figures you have.\n")
    elif brief.get("core_answer_status") == "CORE_QUESTION_UNRESOLVED":
        system += (
            f"\nCORE QUESTION — EVIDENCE INSUFFICIENT\n"
            f"This page targets: {brief.get('core_question')}\n"
            f"The research did not establish a defensible figure. Say so plainly "
            f"and early, explain what determines the cost, and do NOT state or "
            f"imply any number. Inventing one would be worse than the gap.\n")

    if forbidden:
        system += (
            "\nTOPICS YOU MAY NOT ASSERT (no dated source was found for any of "
            "them; mention them only as something to verify, never with a number "
            "or a promise): " + ", ".join(forbidden) + "\n"
        )

    user = json.dumps({
        "language": package.get("language"),
        "market": package.get("market"),
        "primary_query": brief["primary_query"],
        "content_type": brief["content_type"],
        "search_intent": brief["search_intent"],
        "target_audience": brief["target_audience"],
        "business_objective": brief["objective"],
        "working_title": brief["recommended_title"],
        "outline": brief["outline"],
        "questions_to_answer": brief["key_questions"],
        "facts_you_must_build_on": brief["required_facts"],
        "sources": brief["required_sources"],
        "limitations_you_must_respect": brief["missing_information"],
        "call_to_action": brief["cta_strategy"],
        "core_question": brief.get("core_question"),
        "core_answer_status": brief.get("core_answer_status"),
        "price_evidence": core_evidence.get("answers") or [],
        "observed_price_range": core_evidence.get("observed_range"),
    }, ensure_ascii=False)

    return system, user


def parse_draft_response(content: str) -> dict:
    """Parse the model's JSON, tolerating a fenced code block.

    A model that returns prose instead of JSON is a provider error, not something
    to salvage with a regex — salvaging would risk persisting a half-parsed body.
    """
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMProviderError(f"draft response is not JSON: {exc.msg}") from exc

    if not isinstance(parsed, dict):
        raise LLMProviderError("draft response is not a JSON object")

    title = str(parsed.get("title") or "").strip()
    body = str(parsed.get("body") or "").strip()
    if not title or not body:
        raise LLMProviderError("draft response is missing title or body")

    return {
        "title": title[:500],
        "body": body,
        "meta_title": (str(parsed.get("meta_title") or "").strip() or None),
        "meta_description": (str(parsed.get("meta_description") or "").strip() or None),
    }


async def generate_draft(
    brief: dict, package: dict, *, llm: LLMProvider, correlation_id: str,
) -> tuple[dict, LLMResponse]:
    """Generate one draft. Raises LLMNotConfigured when no provider is available."""
    system, user = build_generation_prompt(brief, package)

    response = await llm.generate(LLMRequest(
        capability=LLMCapability.LONG_FORM_WRITING,
        system=system,
        prompt=user,
        response_format="json",
        temperature=0.4,
        max_tokens=4000,
        correlation_id=correlation_id,
    ))

    draft = parse_draft_response(response.content)
    logger.info("draft generated", extra={
        "correlation_id": correlation_id, "provider": response.provider,
        "duration_ms": response.latency_ms,
    })
    return draft, response
