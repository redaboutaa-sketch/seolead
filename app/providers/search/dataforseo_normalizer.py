"""DataForSEO v3 → provider-neutral SERP types.

Contract verified against https://docs.dataforseo.com/v3/ during implementation,
not guessed:

* POST body is a JSON **array** of task objects; a live call carries exactly one.
* Results live at `tasks[].result[].items[]`.
* Every level carries its own `status_code` / `status_message`, and a 200 at the
  envelope does **not** mean the task succeeded — DataForSEO returns 20000 at the
  top while an individual task failed. Both levels are checked.
* Organic items: `type`, `rank_group`, `rank_absolute`, `domain`, `title`, `url`,
  `description`, `breadcrumb`.
* `people_also_ask` and `related_searches` are items in the same array, each with
  a nested `items` list.

Defensive throughout: DataForSEO omits fields freely and adds new SERP feature
types without notice. An unrecognised type is recorded as OTHER with its raw name
kept, because an unknown SERP feature is information about the result page, not a
parse failure.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from app.core.errors import ResearchContractError
from app.providers.search.location import SearchContext
from app.schemas.serp import (OrganicResult, SerpFeature, SerpItemType,
                              SerpQuestion, SerpSnapshot)

logger = logging.getLogger(__name__)

# DataForSEO signals success with 20000 at the envelope and 20000 per task.
STATUS_OK = 20000

_TYPE_MAP = {
    "organic": SerpItemType.ORGANIC,
    "paid": SerpItemType.PAID,
    "featured_snippet": SerpItemType.FEATURED_SNIPPET,
    "people_also_ask": SerpItemType.PEOPLE_ALSO_ASK,
    "related_searches": SerpItemType.RELATED_SEARCHES,
    "local_pack": SerpItemType.LOCAL_PACK,
    "video": SerpItemType.VIDEO,
    "images": SerpItemType.IMAGES,
    "shopping": SerpItemType.SHOPPING,
    "knowledge_graph": SerpItemType.KNOWLEDGE_GRAPH,
}


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_dt(value: Any) -> datetime | None:
    """Parse DataForSEO's timestamp, or return None.

    Their format is `2026-08-12 09:00:00 +00:00`. A failure returns None rather
    than `now()`: a retrieval time we did not observe is not a retrieval time.
    """
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace(" +00:00", "+00:00")
    for candidate in (text, text.replace(" ", "T", 1)):
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    logger.warning("unparseable DataForSEO timestamp discarded: %r", value[:40])
    return None


def _extract_questions(item: Mapping[str, Any], raw_type: str) -> list[SerpQuestion]:
    """PAA and related searches both nest their payload under `items`."""
    nested = item.get("items")
    rank = _as_int(item.get("rank_absolute"))
    questions: list[SerpQuestion] = []

    if raw_type == "people_also_ask" and isinstance(nested, Sequence):
        for entry in nested:
            if not isinstance(entry, Mapping):
                continue
            text = _as_str(entry.get("title")) or _as_str(entry.get("question"))
            if text:
                questions.append(SerpQuestion(text=text, kind="PAA",
                                              rank_absolute=rank))

    elif raw_type == "related_searches":
        # Related searches are plain strings, not objects.
        if isinstance(nested, Sequence):
            for entry in nested:
                text = _as_str(entry) if not isinstance(entry, Mapping) else \
                    _as_str(entry.get("title"))
                if text:
                    questions.append(SerpQuestion(text=text, kind="RELATED",
                                                  rank_absolute=rank))

    return questions


def normalize_serp(
    payload: Mapping[str, Any], *, context: SearchContext, query: str,
) -> SerpSnapshot:
    """Map one DataForSEO live-advanced response into a SerpSnapshot."""
    envelope_status = _as_int(payload.get("status_code"))
    if envelope_status is not None and envelope_status != STATUS_OK:
        raise ResearchContractError(
            f"DataForSEO envelope status {envelope_status}: "
            f"{_as_str(payload.get('status_message')) or 'no message'}"
        )

    tasks = payload.get("tasks")
    if not isinstance(tasks, Sequence) or not tasks:
        raise ResearchContractError("DataForSEO response carries no tasks")

    task = tasks[0]
    if not isinstance(task, Mapping):
        raise ResearchContractError("DataForSEO task is not an object")

    task_status = _as_int(task.get("status_code"))
    if task_status is not None and task_status != STATUS_OK:
        # A failed task under a successful envelope. Treating the 200 as success
        # here would produce a confidently empty SERP.
        raise ResearchContractError(
            f"DataForSEO task status {task_status}: "
            f"{_as_str(task.get('status_message')) or 'no message'}"
        )

    results = task.get("result")
    if not isinstance(results, Sequence) or not results:
        # A task can legitimately succeed with no result block.
        return SerpSnapshot(
            provider="dataforseo", query=query,
            location_code=context.location_code,
            location_name=context.location_name,
            language_code=context.language_code, device=context.device,
            se_domain=context.se_domain, retrieved_at=datetime.now(timezone.utc),
            total_items=0,
            provider_cost=_as_float(payload.get("cost")),
            provider_metadata={"dataforseo": {"empty_result": True,
                                              "task_id": _as_str(task.get("id"))}},
        )

    result = results[0]
    items = result.get("items") if isinstance(result, Mapping) else None
    items = items if isinstance(items, Sequence) else []

    organic: list[OrganicResult] = []
    features: list[SerpFeature] = []
    questions: list[SerpQuestion] = []
    feature_counts: dict[str, tuple[SerpItemType, int | None, int]] = {}

    for item in items:
        if not isinstance(item, Mapping):
            continue
        raw_type = _as_str(item.get("type")) or "unknown"
        mapped = _TYPE_MAP.get(raw_type, SerpItemType.OTHER)

        if mapped is SerpItemType.ORGANIC:
            organic.append(OrganicResult(
                rank_group=_as_int(item.get("rank_group")),
                rank_absolute=_as_int(item.get("rank_absolute")),
                domain=_as_str(item.get("domain")),
                url=_as_str(item.get("url")),
                title=_as_str(item.get("title")),
                description=_as_str(item.get("description")),
                breadcrumb=_as_str(item.get("breadcrumb")),
                metadata={"dataforseo": {
                    "is_featured_snippet": item.get("is_featured_snippet"),
                    "website_name": _as_str(item.get("website_name")),
                }},
            ))

        questions.extend(_extract_questions(item, raw_type))

        previous = feature_counts.get(raw_type)
        rank = _as_int(item.get("rank_absolute"))
        if previous is None:
            feature_counts[raw_type] = (mapped, rank, 1)
        else:
            feature_counts[raw_type] = (previous[0], previous[1], previous[2] + 1)

    for raw_type, (mapped, rank, count) in sorted(feature_counts.items()):
        features.append(SerpFeature(item_type=mapped, raw_type=raw_type,
                                    rank_absolute=rank, count=count))

    unknown = sorted(t for t, (m, _, _) in feature_counts.items()
                     if m is SerpItemType.OTHER)
    if unknown:
        # Not an error. Google adds features; we record what we saw.
        logger.info("unmapped SERP item types recorded as OTHER: %s",
                    ", ".join(unknown))

    retrieved = _parse_dt(result.get("datetime") if isinstance(result, Mapping)
                          else None) or datetime.now(timezone.utc)

    return SerpSnapshot(
        provider="dataforseo",
        query=query,
        location_code=context.location_code,
        location_name=context.location_name,
        language_code=context.language_code,
        device=context.device,
        se_domain=context.se_domain,
        retrieved_at=retrieved,
        total_items=len(items),
        organic=organic,
        features=features,
        questions=questions,
        provider_cost=_as_float(payload.get("cost")),
        provider_metadata={"dataforseo": {
            "task_id": _as_str(task.get("id")),
            "se_results_count": _as_int(result.get("se_results_count"))
            if isinstance(result, Mapping) else None,
            "check_url": _as_str(result.get("check_url"))
            if isinstance(result, Mapping) else None,
            "unmapped_item_types": unknown,
        }},
    )


def normalize_keyword_metrics(
    payload: Mapping[str, Any], *, provider: str = "dataforseo",
) -> dict[str, list[dict]]:
    """Map a Google Ads search-volume response into per-keyword metric dicts.

    Returns `{keyword: [metric, ...]}`. A metric absent from the response is simply
    not returned — the caller records UNKNOWN. Nothing here invents a value.
    """
    envelope_status = _as_int(payload.get("status_code"))
    if envelope_status is not None and envelope_status != STATUS_OK:
        raise ResearchContractError(
            f"DataForSEO envelope status {envelope_status}"
        )

    tasks = payload.get("tasks")
    if not isinstance(tasks, Sequence) or not tasks:
        return {}

    task = tasks[0]
    if not isinstance(task, Mapping):
        return {}
    if (_as_int(task.get("status_code")) or STATUS_OK) != STATUS_OK:
        raise ResearchContractError(
            f"DataForSEO keyword task status {task.get('status_code')}"
        )

    results = task.get("result")
    if not isinstance(results, Sequence):
        return {}

    retrieved = datetime.now(timezone.utc)
    out: dict[str, list[dict]] = {}

    for entry in results:
        if not isinstance(entry, Mapping):
            continue
        keyword = _as_str(entry.get("keyword"))
        if not keyword:
            continue
        metrics: list[dict] = []

        for field, kind, currency in (
            ("search_volume", "search_volume", None),
            ("cpc", "cpc", "USD"),
            ("competition_index", "competition_index", None),
        ):
            value = entry.get(field)
            if value is None:
                continue
            numeric = _as_float(value)
            if numeric is None:
                continue
            metrics.append({
                "metric_type": kind, "value": numeric, "value_text": None,
                "currency": currency, "provider": provider,
                "retrieved_at": retrieved,
            })

        competition = _as_str(entry.get("competition"))
        if competition:
            metrics.append({
                "metric_type": "competition", "value": None,
                "value_text": competition, "currency": None,
                "provider": provider, "retrieved_at": retrieved,
            })

        if metrics:
            out[keyword] = metrics

    return out


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
