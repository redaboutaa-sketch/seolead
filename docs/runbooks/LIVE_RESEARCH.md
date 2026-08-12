# Runbook — live research

Everything here costs money. Read `docs/runbooks/PROVIDER_CREDENTIALS.md` first.

## Preconditions

```bash
docker exec seolead_api seolead credentials
```

`ready_for_live_test` must be `true` (DataForSEO, Tavily and OpenAI all
`CONFIGURED`). Without DataForSEO the pipeline stops at the SERP stage with
`PROVIDER_NOT_CONFIGURED` — SERP is the backbone, and there is no competitor view,
no People Also Ask and no gap analysis without it.

Partial credentials still do useful work:

| Configured | You get |
|---|---|
| none | provider plan, then a clean stop |
| DataForSEO only | SERP snapshot, competitor structure, PAA, content gap, opportunity score |
| + Tavily | eligible evidence, ResearchPackage V2, deterministic brief |
| + OpenAI | draft, factual QA, SEO QA, `PENDING_APPROVAL` |

## The pilot run

```bash
docker exec seolead_api seolead research run \
  --vertical SOLAR_BE \
  --query "prix panneaux solaires Belgique" \
  --market BE --language fr
```

Useful flags:

```
--engine v1|v2        v2 is the default (SERP + relevance gate)
--device desktop|mobile
--force-refresh       bypass the freshness cache and pay again
--community           override the vertical policy and call Last30Days
--no-community        force it off
--stop-after package|brief
```

Exit codes: `0` complete · `2` ran correctly but stopped at a gate · `1` error.

## Reading the result

Work through it in this order.

**1. Provider plan** — which providers ran and why. For SOLAR_BE, expect
`community: false` with the reason naming the vertical policy.

**2. SERP** — `organic_count`, `paa_count`, `features`, `dominant_framing`,
`content_gap`. If `reused: true`, a cached snapshot inside the 24 h TTL was used.

**3. Relevance** — `evaluated`, `eligible`, `rejected`, `by_status`. A high
rejection count is not automatically wrong; inspect it:

```bash
docker exec seolead_api seolead package rejected <research_package_id>
```

Each entry carries the status, the reason and the signals behind it. This is the
first thing to check when the gate looks wrong in either direction.

**4. Package** — `sources_eligible` vs `sources_retrieved`, `facts_supported`,
`high_risk_unsupported`, `partial_observation`.

**5. Opportunity** — `overall_score` with `confidence` and `missing_inputs`. A
score with low confidence is a prompt to get more data, not a verdict.

**6. QA** — factual first (claim → evidence binding), then SEO. Only HIGH-risk
unsupported claims block factually.

**7. Approval** — expect `PENDING`. Nothing auto-approves, ever.

## Inspection commands

```bash
docker exec seolead_api seolead serp show <serp_snapshot_id>
docker exec seolead_api seolead package show <research_package_id>
docker exec seolead_api seolead package rejected <research_package_id>
docker exec seolead_api seolead opportunity show <seo_opportunity_id>
docker exec seolead_api seolead brief show <content_brief_id>
docker exec seolead_api seolead draft show <draft_id> --body
docker exec seolead_api seolead usage <correlation_id>
```

API equivalents exist under `/internal/v1/`, all behind `X-Internal-Key`.

## Approval

```bash
docker exec seolead_api seolead content pending
docker exec seolead_api seolead content approve <draft-id> --by "Reda" --note "ok"
docker exec seolead_api seolead content reject <draft-id> --by "Reda"
docker exec seolead_api seolead content request-revision <draft-id> --by "Reda"
```

`APPROVED` and `REJECTED` are terminal. QA success is never approval.

## Controlling spend

- Per-job ceiling: `SEOLEAD_MAX_CALLS_PER_PROVIDER` (default 3), enforced **before**
  each request. A runaway loop raises `PROVIDER_BUDGET_EXCEEDED`, not an invoice.
- Freshness caching: SERP 24 h, web research 168 h, community 72 h.
- `seolead usage <correlation_id>` reports per-provider spend.
  `total_cost_usd: null` means unknown, **not** free — only DataForSEO returns a
  monetary cost.

## Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| stops at `serp`, `PROVIDER_NOT_CONFIGURED` | no DataForSEO credentials | add them; see the credentials runbook |
| `402` from DataForSEO | prepaid balance exhausted | top up; not a retryable fault |
| every source rejected | query has unusual vocabulary, or thresholds too strict | read `package rejected`; consider profile vocabulary or `SEOLEAD_RELEVANCE_RELEVANT_AT` |
| nothing rejected but evidence looks off-topic | thresholds too loose | tighten `SEOLEAD_RELEVANCE_RELEVANT_AT` |
| factual QA blocks on HIGH-risk claims | the draft asserted a subsidy or tariff without an official source | correct behaviour — the evidence set needs a regulator source |
| `PROVIDER_BUDGET_EXCEEDED` | per-job ceiling hit | raise it deliberately, or check for a loop |
| SERP reused when you wanted fresh | inside the 24 h TTL | `--force-refresh` |
