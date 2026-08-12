# Phase 3 — implementation notes

Design decisions and their reasoning. The narrative is
`/opt/seolead/PHASE3_IMPLEMENTATION_REPORT.md`; this is the reference.

## What changed and why

Phase 2 ended with a measured finding: Last30Days is a tech-community discussion
engine and cannot serve a French consumer commercial vertical. Phase 3 replaces it
as the primary research path and fixes the deeper defect that finding exposed —
that nothing was checking whether a source was about the query at all.

## Provider categories

Three providers with genuinely different jobs, not three interchangeable search
APIs:

| Provider | Capabilities | Job |
|---|---|---|
| DataForSEO | `SERP`, `KEYWORD_METRICS` | what the searcher sees |
| Tavily | `WEB_RESEARCH`, `CONTENT_EXTRACTION` | the factual evidence |
| Last30Days | `RECENT_DISCUSSION`, `COMMUNITY_SIGNAL` | what a community is saying |

Downstream code asks for a capability. `plan_providers()` decides which run, from
the vertical profile and the classified intent — deterministically, so an LLM
cannot switch on a paid provider.

Community research is off for SOLAR_BE (`community_research_enabled: false`) and on
for the test vertical, which is how the routing tests prove the policy is read from
configuration rather than hard-coded. Even in an enabled vertical it is skipped for
COMMERCIAL and TRANSACTIONAL intent, because discussion rarely carries
purchase-stage facts.

## API contracts, verified not guessed

Both were read from the official documentation during implementation.

**DataForSEO:** `POST /v3/serp/google/organic/live/advanced`, HTTP Basic, body is a
JSON **array** with exactly one task, results at `tasks[].result[].items[]`. The
subtlety that matters: status codes exist at **both** the envelope and the task, and
a 20000 envelope can carry a failed task. Trusting the envelope alone produces a
confidently empty SERP — a result claiming "Google shows nothing" when the request
was malformed. Both are checked.

**Tavily:** `POST /search`, Bearer auth. Two contract facts shape everything
downstream — `published_date` is **not** a standard field (news topic only), and
`score` is retrieval relevance, not factual confidence. Neither is papered over: an
undated source becomes ESTIMATED, and `confidence` stays `None`.

## Search context

Belgium is not a generic global Google search, and BE/fr and BE/nl are different
SERPs for the same product. Nothing Belgian is in the provider: it takes a
`SearchContext`, and `location.py` maps (market, language, device) onto one.
Location codes are DataForSEO's Google geo-targeting codes; Belgium is 2056.

An unconfigured market raises rather than defaulting to a global search — a silent
fallback would return a SERP nobody in that market sees.

## The relevance gate

Full reasoning in `docs/RELEVANCE_GATE.md`. The core is that a query's words are not
equally about its subject:

```
prix panneaux solaires Belgique
 │      └── topic ──┘      └─ market name, no topical signal
 └─ commercial modifier
```

Zero topic overlap is a hard rejection. That is what stops "Grand Prix Circuit"
scoring on `prix` — the trap that naive token overlap walks into.

Stage B (semantic) runs only for LOW_RELEVANCE and never overturns a hard rejection.

## Three independent axes

Relevance ("is this about the query"), quality ("how much weight") and risk ("how
bad if wrong") are separate and must not be conflated. Two rules are structural:

- **Ranking is not authority.** `classify_domain` is never given a rank, so it
  cannot use one.
- **Commercial is not disqualifying.** An installer's pricing page is often the
  best source on installer pricing; it is classified, not rejected.

Risk raises the evidence bar: HIGH needs OFFICIAL or INSTITUTIONAL, MEDIUM needs
SPECIALIST or better, LOW accepts any relevant source. HIGH categories come from
the vertical's `restricted_claims`, so this carries no solar-specific knowledge.

## `supported` now means four things

```
observability == OBSERVED
  AND claim relevance is eligible
  AND source quality clears the claim's risk bar
  AND the source reference resolves inside the package
```

In Phase 2 it meant only the first.

## Factual QA V2

Walks the draft's factual sentences and binds each to eligible evidence:
`SUPPORTED` / `PARTIALLY_SUPPORTED` / `UNSUPPORTED` / `CONFLICTING`.

Only **HIGH-risk and not SUPPORTED** blocks. A wrong sentence about panel
orientation is a quality problem; a wrong sentence about a subsidy is a legal one,
and only the second should stop a draft reaching a human. `CONFLICTING` is reported
distinctly because "evidence exists and disagrees" is a stronger signal than
"nothing found".

## SEO QA V2

Layered on top of the Phase 2 checks rather than folded into them — changing their
behaviour to add new ones would have meant editing the tests that pin them, which
is how a regression suite quietly stops being one.

Adds: PAA coverage (the clearest statement of what searchers also want to know),
intent alignment, title topicality, content-type fit, repetition, and the SERP
content gap as an opportunity note.

## Cost and freshness

Every provider call is recorded with `cost_usd` **nullable** and `cost_is_actual`
separate. DataForSEO returns its own billing figure; Tavily and OpenAI do not.
`total_cost_usd` returns `None` rather than `0.0` for an unpriced job — unknown
spend and free are different facts.

The orchestrator backstops adapters that do not record themselves
(`usage.ensure_recorded`). Adapters record their own usage because only they know
the provider's cost, but that made the ledger depend on every adapter remembering,
and one that forgets is invisible exactly where money is involved.

TTLs: SERP 24 h, web research 168 h, community 72 h. One TTL for everything would
be wrong in both directions.

Per-job ceilings are checked **before** the request, so a runaway loop raises
`PROVIDER_BUDGET_EXCEEDED` rather than producing an invoice.

## Migration 0002

Additive. Six new tables (`serp_snapshot`, `serp_result`, `serp_question`,
`keyword_metric`, `seo_opportunity`, `provider_usage`), relevance columns on
`research_source`, risk columns on `research_evidence`, V2 fields on
`research_package`. Every new column is nullable or defaulted, so Phase 2 rows
remain valid — verified by a downgrade/upgrade round-trip against the live database
with Phase 2 data present, which came back intact and marked `package_version = 1`.

`version` (revision for one keyword) and `package_version` (which builder produced
it) are separate fields; conflating them would make "which builder was this"
unanswerable.
