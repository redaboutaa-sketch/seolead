# ResearchPackage V2

## What changed from V1

V1 took whatever a provider returned and marked it supported. That is how a
racing-game post became the sole evidence for a solar pricing query.

V2 makes every source pass three independent checks before the writer sees it:

| Check | Question | Module |
|---|---|---|
| Relevance | is this about the query? | `services/relevance.py` |
| Quality | how much weight does it carry? | `services/source_quality.py` |
| Risk | how bad if this claim is wrong? | `services/claim_risk.py` |

Only sources passing **relevance** become eligible evidence. Everything else is
kept in `rejected_evidence` with its reason.

`supported` now requires four things, not one:

```
observability == OBSERVED
  AND claim relevance is eligible
  AND source quality clears the claim's risk bar
  AND the source reference resolves inside the package
```

## Shape

```
query · market · language · intent · summary

serp_observations      derived structure, not competitor copy
competitor_pages       rank, domain, url, title, page shape
content_gap            page shapes the SERP is NOT serving
serp_features          what competes for attention
user_questions         People Also Ask
related_searches

eligible_evidence[]    sources that passed the gate
rejected_evidence[]    sources that did not, WITH the reason
sources[]              everything retrieved, gate decision attached
facts[]                claim → source_ref → provider, with risk and support

keyword_metrics[]      value + provider + retrieved_at + observability
source_quality_summary counts, has_official, best
claim_risk_summary     counts, high_risk_count
unresolved_questions   what we could not stand up
confidence_summary     the honest accounting
provider_provenance    per provider: status, outcomes, engine build, metadata
```

## Traceability

```
claim → evidence → source → provider
```

Every fact carries `source_ref`; every source carries `provider`, `url`,
`published_at` (absent when unknown, never invented) and its relevance decision.
A dangling `source_ref` makes the fact unsupported — a reference that does not
resolve is not support.

## confidence_summary

| Field | Meaning |
|---|---|
| `sources_retrieved` / `sources_eligible` / `sources_rejected` | the gate's ledger |
| `facts_supported` | passed all four conditions above |
| `facts_observed` / `facts_estimated` / `facts_unknown` | provenance split |
| `high_risk_claims` / `high_risk_unsupported` | the claims that can block a draft |
| `mean_relevance` | feeds the opportunity score's business-relevance component |
| `partial_observation` | true ⇒ gaps are not evidence of absence |
| `serp_available` | whether SERP intelligence was part of this package |

## Backwards compatibility

`package_version` distinguishes the two shapes. Phase 2 packages remain valid and
readable as V1; the migration is additive and every new column is nullable or
defaulted. `version` (revision for one keyword) and `package_version` (which
builder produced it) are separate fields — conflating them would make "which
builder was this" unanswerable.

## What the writer receives

The brief, the eligible evidence, the unresolved facts and the claim restrictions.
**Not** the rejected evidence, and **not** competitor page text. Competitor titles
are used to derive structural observations and are never forwarded as material to
imitate.
