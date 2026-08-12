# Tavily — Web Research provider

Capabilities: `WEB_RESEARCH`, `CONTENT_EXTRACTION`.

This is where the factual evidence comes from. DataForSEO tells us what the SERP
looks like; Tavily supplies the sources a claim can be bound to.

## Contract

Verified against the official documentation during implementation.

```
POST https://api.tavily.com/search
Authorization: Bearer tvly-...
```

Request fields used:

```json
{"query": "...", "search_depth": "advanced", "topic": "general",
 "max_results": 10, "include_answer": false, "include_raw_content": false,
 "country": "belgium"}
```

`include_answer` is false on purpose: we want sources, not a synthesised answer.
An answer would be a second model's summary presented as evidence, which is exactly
what the evidence model exists to prevent. `include_raw_content` is false because
excerpts are sufficient and far cheaper.

Response: `{query, answer?, results[{title, url, content, score, raw_content?,
favicon?, id}], response_time, request_id, usage?}`.

## Two contract facts that shape everything downstream

### `published_date` is not a standard field

It appears for `topic="news"`. A general search returns sources with **no date**.

The adapter leaves `published_at` as `None` rather than inventing one, and an
undated source becomes `ESTIMATED` rather than `OBSERVED` — we saw it, we cannot
place it in time. For a pilot about prices and subsidies that distinction matters:
an undated claim about a tariff is not something a reader can rely on.

Consequence to expect in practice: **most Phase 3 web evidence will be ESTIMATED,
not OBSERVED.** That is honest, not pessimistic, and it means HIGH-risk claims will
mostly need an official source rather than a general web result.

The count of undated sources is reported in `unresolved_data`.

### `score` is relevance, not confidence

Tavily's `score` says "this matched your query well". It says nothing about whether
the content is true. It is carried in `metadata.tavily.relevance_score` and used by
the relevance gate; `NormalizedSource.confidence` and `NormalizedFact.confidence`
stay `None`, because conflating retrieval quality with factual confidence is how a
well-matched wrong page becomes a supported fact.

## Results without a URL are dropped

A source we cannot cite is not usable evidence. The drop is silent by design — it
is not a failure, just an unusable row.

## Cost

Tavily bills in credits and returns no monetary cost. Usage is recorded with
`cost_usd = None` and `cost_is_actual = false`.

A job whose providers report no cost has an **unknown** spend, not a free one, and
`total_cost_usd` returns `None` rather than `0.0` to say so.

## Errors

| Condition | Behaviour |
|---|---|
| No key | `PROVIDER_NOT_CONFIGURED`, no request attempted |
| 401 / 403 | Not retryable |
| 429 | Retryable |
| Timeout | `LAST30DAYS_TIMEOUT` (timeout family), retryable |
| Missing `results` array | Contract error |
| Empty `results` | **Clean empty** — `no-results`, not a failure |

That last row matters: an empty result set from a healthy call is a genuine
observation ("we looked and found nothing"), and it is recorded distinctly from a
call that could not be made.

## Credentials

```
TAVILY_API_KEY=
TAVILY_BASE_URL=https://api.tavily.com
TAVILY_MAX_RESULTS=10
TAVILY_SEARCH_DEPTH=advanced
```

## Caching

`SEOLEAD_WEB_RESEARCH_TTL_HOURS`, default 168 (7 days). Explanatory pages change
slowly, so a weekly refresh is enough; `--force-refresh` overrides.
