# PHASE 3.2 — AUTHORITATIVE RESEARCH FOR HIGH-RISK CLAIMS

**Date:** 2026-08-12
**Workspace:** `/opt/seolead`, branch `main`
**Baseline:** `d1af54ee057407c5eca9afec2099380f084cae49`
**Outcome:** PARTIAL — official evidence retrieved and HIGH-risk claims resolved for
the first time; one precision problem got materially worse and is the blocker.

---

## 1. Executive Summary

Phase 3.1 ended with a plan nobody had run and zero official Belgian evidence. This
phase executed it.

**Four targeted queries against 17 configured official domains returned 40 pages,
all 40 on-domain, and put real regulators into the evidence set for the first
time** — the Walloon energy portal, CREG, CWaPE, ORES, Bruxelles Environnement and
BRUGEL. Thirteen survived the relevance gate.

**Four HIGH-risk claims are now SUPPORTED, up from zero**, each citing 8–18 official
sources with an explicit regional scope:

```
SUBSIDY   / BE-BRU   18 OFFICIAL sources (UNDATED_CURRENT)
SUBSIDY   / BE-BRU    8 OFFICIAL sources (UNDATED_CURRENT)
GRID_RULE / BE-WAL   14 OFFICIAL sources (DATED_CURRENT)
GRID_RULE / BE-BRU   11 OFFICIAL sources (UNDATED_CURRENT)
```

That is the mechanism working end to end: a claim about the Walloon prosumer tariff
is established by CWaPE and ORES, scoped `BE-WAL`, and refused for anywhere else.

**No authority requirement was relaxed and no threshold was touched.** Sixty
HIGH-risk claims remain blocked, which per §16 is a correct outcome rather than a
failure.

**The blocker is conflict precision.** `TRUE_CONFLICT` rose from 11 to 163. The
refinement works — 28 disagreements were correctly reclassified as regional,
temporal or scope differences — but adding thirteen dense official documents
multiplied spurious numeric collisions faster than the classifier removes them. The
cause is in `passage_supports_claim`, not in the conflict logic: a two-word overlap
is too loose a bar across a 23-source corpus, so unrelated figures are compared.

**The optional draft was deliberately not generated.** With 163 TRUE_CONFLICTs in
the ledger, a QA verdict on a draft would be measuring an artefact rather than the
writer, and §19 gates generation on a clean ledger.

Two real bugs were found by the live run and fixed: page text was overriding an
authority's own jurisdiction (`energie.wallonie.be` tagged `BE-BRU`), and a validity
period was being read as an archival marker.

**485 tests pass**, no credentials, no network.

---

## 2. Baseline

```
commit  d1af54ee057407c5eca9afec2099380f084cae49   (clean tree, branch main)
Tavily  CONFIGURED     OpenAI  CONFIGURED     Internal API  CONFIGURED
```

---

## 3. DataForSEO Availability

**`CONFIGURED_BUT_ACCOUNT_BLOCKED`**

One authenticated no-cost probe (`GET /v3/serp/google/locations/be`):

```
HTTP 403 · status_code 40104
"Please verify your account before using the API."
cost: 0
```

Not retried. Authoritative research ran entirely through Tavily and did not depend
on DataForSEO, as §2 requires.

---

## 4. Unresolved HIGH-risk Claims Before the Run

From the commercial-only pass: 122 atomic claims, 27 HIGH-risk, **all 27 blocked**.

| Category | Unresolved |
|---|---:|
| SUBSIDY | 8 |
| ENERGY_PRICE | 8 |
| ROI | 5 |
| GRID_RULE | 4 |
| TAX | 1 |
| REGULATION | 1 |

---

## 5. Authority Policy

Each domain now carries what it is authoritative *about* and *for whom* —
`authority_type`, `region`, `market`, `languages`, `claim_categories`, `priority` —
all in `config/verticals/solar_be.yaml`. A flat list could not express that the
Walloon portal establishes Walloon premiums and says nothing about Flemish grid
rules.

17 entries: 4 GOVERNMENT, 4 REGULATOR, 5 GRID_OPERATOR, 3 PUBLIC_AGENCY,
1 OFFICIAL_PROGRAM; 4 each for BE-WAL / BE-BRU / BE-VLG and 5 federal.

`AuthorityType.source_quality` maps every recognised type to `OFFICIAL`, and a
commercial installer is never in the registry — so it cannot acquire `OFFICIAL`
through this path. A test asserts it.

---

## 6. Official Domains Used

Queried per category, filtered by the categories each domain speaks for:

| Category | Domains queried |
|---|---:|
| SUBSIDY | 6 |
| ENERGY_PRICE | 6 |
| ROI | 3 |
| GRID_RULE | 8 |

Accepted pages came from `energie.wallonie.be` (16), `creg.be` (10), `cwape.be` (7),
`environnement.brussels` (4), `ores.be` (2), `brugel.brussels` (1).

---

## 7. Queries Executed

Four, from the Phase 3.1 planner's templates — one per unresolved category, capped
by `max_queries: 4`:

```
SUBSIDY       prime panneaux photovoltaiques Wallonie Bruxelles Flandre conditions officielles
ENERGY_PRICE  prix electricite tarif regule menages
ROI           rentabilite installation photovoltaique etude officielle
GRID_RULE     tarif prosumer injection compteur photovoltaique regulateur reseau
```

Executed via Tavily's documented `include_domains`, which the contract confirms and
the run honoured.

---

## 8. Official Sources Returned

```
returned 40 · accepted 40 · rejected 0 · errors 0
```

Zero rejections means Tavily honoured the restriction completely. The registry
check still ran on every URL — a provider that honoured it loosely could not have
smuggled a commercial page through, and a test covers that path.

| Authority type | Region | Pages |
|---|---|---:|
| GOVERNMENT | BE-WAL | 16 |
| REGULATOR | BE | 10 |
| REGULATOR | BE-WAL | 7 |
| PUBLIC_AGENCY | BE-BRU | 4 |
| GRID_OPERATOR | BE-WAL | 2 |
| REGULATOR | BE-BRU | 1 |

**Only 13 of 40 survived the relevance gate.** Official pages are judged like any
other: being a regulator does not make a page about the query, and titles such as
*"CHAPITRE 4 ANALYSE DU BÂTI"* were correctly excluded.

---

## 9. Passage Extraction

The Phase 3.1 pipeline applied unchanged. Official pages carry the same furniture
as commercial ones — navigation, PEB menus, publication lists — and it is stripped
the same way, with drop reasons recorded per passage.

---

## 10. Atomic Claim Extraction

122 → **222 atomic claims** after enrichment. The 100 additional claims come from
the 13 newly eligible official pages.

---

## 11. Regional Scope

`Region` supports `BE`, `BE-WAL`, `BE-BRU`, `BE-VLG` (plus `FR`, `NL`), with an
asymmetric coverage rule: **national evidence covers a regional claim; regional
evidence never covers a national one.** A Walloon premium cannot become Belgian
law, and one region never covers another.

Enforced for HIGH-risk claims, where over-generalising is a false statement of law.
All four resolved claims carry an explicit scope (`BE-WAL` or `BE-BRU`), and none
was generalised to `BE`.

### Bug found and fixed

The first run tagged `energie.wallonie.be` as `BE-BRU` because one of its pages
mentioned Brussels, and `environnement.brussels` as `BE-WAL` for the mirror reason.
Page-text detection was overriding the authority's own jurisdiction — which would
let the Walloon portal establish a Brussels rule, precisely what regional scoping
exists to prevent.

Fixed: a registered authority's declared region is definitive; text detection
applies only to unregistered sources. After the fix every domain maps to its own
jurisdiction. Three regression tests.

---

## 12. Freshness Handling

`FreshnessStatus` replaces the single date bit:

```
DATED_CURRENT · DATED_EXPIRED · UNDATED_CURRENT · UNDATED · HISTORICAL
```

`UNDATED_CURRENT` is the distinction the mission asked for — an official portal
describing a scheme in the present tense is not the same as a page with no date and
no signal. `HISTORICAL` and `DATED_EXPIRED` can never support a present-tense claim.

Observed across the 40 official pages: **32 UNDATED, 7 UNDATED_CURRENT, 1
DATED_EXPIRED**. Belgian official portals largely do not publish machine-readable
dates, so `UNDATED_CURRENT` is doing real work — without it, two of the four
resolved claims would have failed the freshness bar.

`effective_from` / `effective_until` are persisted verbatim when a page states them.
No date is ever fabricated.

### Bug found and fixed

`"jusqu'au 31 decembre"` was listed as an archival marker, so a scheme valid until
31 December 2027 would have been classified `HISTORICAL`. Removed; expiry is decided
by comparing the stated end year. Three regression tests.

---

## 13. Evidence Resolution

| | Before | After |
|---|---:|---:|
| Eligible sources | 10 | 23 (13 official + 10 commercial) |
| Atomic claims | 122 | 222 |
| SUPPORTED | 51 | 109 |
| PARTIALLY_SUPPORTED | 13 | 10 |
| UNSUPPORTED | 47 | 59 |
| CONFLICTING | 11 | 44 |
| HIGH-risk total | 27 | 64 |
| HIGH-risk blocked | 27 | 60 |
| **HIGH-risk SUPPORTED** | **0** | **4** |

Unresolved HIGH-risk by category, after:

| Category | Before | After |
|---|---:|---:|
| SUBSIDY | 8 | 17 |
| GRID_RULE | 4 | 15 |
| ENERGY_PRICE | 8 | 10 |
| REGULATION | 1 | 9 |
| ROI | 5 | 8 |
| TAX | 1 | 1 |

**The rise in blocked claims is not a regression.** Thirteen official documents
produced 100 new atomic claims, many of them themselves HIGH-risk regulatory
statements that nothing yet corroborates. More evidence surfaced more claims; the
denominator grew faster than the numerator.

---

## 14. Conflict Refinements

`ConflictKind` distinguishes `TRUE_CONFLICT`, `REGIONAL_DIFFERENCE`,
`TIME_DIFFERENCE`, `SCOPE_DIFFERENCE` and `WORDING_VARIATION`. Only
`TRUE_CONFLICT` blocks; the rest are recorded and say the claim needs narrowing.

Detection was **not** weakened — everything previously flagged is still flagged,
now with a reason.

Observed:

```
TRUE_CONFLICT        163
TIME_DIFFERENCE       14
SCOPE_DIFFERENCE       9
REGIONAL_DIFFERENCE    5
```

28 disagreements correctly reclassified as non-blocking — Wallonia vs Brussels
premiums, 2021 vs 2026 prices, per-Wc vs total cost.

**But 163 TRUE_CONFLICTs, up from 11, is the headline problem.** The refinement is
sound; the input is not. `passage_supports_claim` treats a two-content-word overlap
as "this passage is about this claim", and across 23 sources that pairs claims with
passages discussing something else entirely, then compares their unrelated numbers.
The fix belongs in claim↔passage matching, not in conflict classification, and
weakening the latter to compensate would hide real disagreements.

---

## 15. ResearchPackage Version

`PACKAGE_VERSION = 4`. The enriched package records
`supersedes_package_version` and carries the full `authority_registry` snapshot in
its provenance, so a package can be read months later against the policy that
produced it.

Evidence is split by provenance:

```
official_evidence     13
commercial_evidence   10
rejected_evidence     (with per-source reasons)
authoritative_run     queries, domains, accepted, rejected, errors
```

Phase 3 and 3.1 packages are untouched and still readable at their own versions.

---

## 16. Writer-Eligible Evidence

```
writer-eligible (SUPPORTED)     109
partially supported (opt-in)      0
forbidden categories              SUBSIDY · TAX · GRID_RULE · REGULATION ·
                                  ENERGY_PRICE · ROI
```

Every HIGH-risk category remains forbidden as a topic even though four individual
claims within two of them are supported — the forbidden list is category-level and
deliberately conservative.

The writer still receives only claims, never raw excerpts or rejected sources.

---

## 17. Optional Draft Result

**Not generated, deliberately.**

§19 gates generation on "no HIGH-risk blocker contaminates required facts". With 163
TRUE_CONFLICTs — most of them artefacts of loose claim↔passage matching (§14) — a
factual QA verdict would measure the matching bug rather than the writer. Generating
anyway would produce a result nobody could interpret, and spending on a model to
obtain it would be worse.

The condition to lift this is in §25.

## 18. Factual QA

Not run — no draft. The claim ledger it would evaluate is reported in §13.

## 19. SEO QA

Not run — no draft.

---

## 20. Provider Usage / Cost

```
tavily   5 requests   (1 search · 4 search_restricted)   50 results
cost_usd null — Tavily bills in credits and returns no monetary figure
DataForSEO  1 probe, HTTP 403, cost 0.00
```

Unknown is not rendered as free: `total_cost_usd` is `null`, not `0.0`. The per-job
ceiling was never approached, and no broad crawling or unbounded loop ran — four
bounded queries, one per unresolved category.

---

## 21. Tests

**485 passed, 0 failed, 0 skipped**, ~12 s, no credentials, no network. Up from 436.

New suite `test_authoritative_research.py` (49). Coverage for every item §20 lists:

| Required | Test |
|---|---|
| Official-domain enforcement | `test_off_domain_pages_are_rejected_even_in_the_official_pass` |
| Regional scope preservation | `test_a_walloon_source_cannot_support_a_belgium_wide_subsidy_claim` |
| Dated vs undated official evidence | `test_an_undated_page_presenting_as_in_force_is_distinguished` |
| Historical page not treated as current | `test_a_historical_page_cannot_support_a_current_claim` |
| Scope difference is not a true conflict | `test_different_units_are_a_scope_difference` |
| Regional difference is not a conflict | `test_a_regional_difference_does_not_block_the_claim` |
| Commercial cannot override official | `test_many_commercial_sources_do_not_add_up_to_an_official_one` |
| Official satisfies the requirement | `test_an_official_source_satisfies_the_requirement` |
| Writer forbidden from unresolved HIGH-risk | `test_forbidden_claims_are_named` |
| Provenance across versioning | `test_package_version_is_recorded_with_its_predecessor` |

Plus authority-region precedence (3), freshness validity periods (3), and the
authority registry's category and region routing.

---

## 22. Live Discrepancies

1. **Authority jurisdiction was overridden by page text** — `energie.wallonie.be`
   tagged `BE-BRU`. Fixed; 3 regression tests. Regulatory consequence: it would
   have let a Walloon source establish a Brussels rule.
2. **A validity period read as an archival marker** — a scheme valid until
   31 December 2027 would have been `HISTORICAL`. Fixed; 3 regression tests.
3. **Tavily honoured `include_domains` completely** (40/40 on-domain), which the
   contract documents but had never been exercised.
4. **Belgian official portals rarely carry dates** — 32 of 40 pages `UNDATED`. Two
   of the four resolutions depended on `UNDATED_CURRENT` existing.
5. **Only 13 of 40 official pages were on-topic.** The relevance gate handled it,
   but a domain-restricted query still returns institutional noise.

---

## 23. Known Limitations

1. **Conflict base rate (163 TRUE_CONFLICT).** The dominant problem, diagnosed in
   §14: claim↔passage matching is too loose, not conflict classification.
2. **Corroboration counts sources, not independence.** "18 OFFICIAL sources" for one
   Brussels subsidy claim mostly means several pages of the same portal.
3. **Claim extraction still admits page furniture** — headings and list residue,
   carried over from Phase 3.1.
4. **Regional scope is enforced only for HIGH-risk claims.** A MEDIUM market-price
   claim can still mix regions.
5. **`effective_from` / `effective_until` are stored as raw strings**, unparsed and
   uncompared beyond the end year.
6. **Flanders returned nothing.** The SUBSIDY query named all three regions but
   `energiesparen.be` and `vreg.be` produced no accepted page, so Flemish claims
   have no official evidence at all.
7. **DataForSEO remains blocked**, so no SERP evidence has ever entered a package.
8. **No draft has ever been generated from a claim-level ledger.**

---

## 24. Phase 4 Readiness

**Not ready.** Two things must land first.

The evidence machinery is now structurally complete — relevance, authority, region,
freshness, corroboration and conflict are all modelled and all exercised against
live official sources. What is not established is that the ledger it produces is
clean enough for a writer to use, and the 163 TRUE_CONFLICTs say it is not.

---

## 25. Exact Recommended Next Action

**Fix claim↔passage matching precision, then generate one draft.**

1. **Tighten `passage_supports_claim`.** It currently accepts a two-content-word
   overlap. Require a materially higher overlap, or require the claim's *head noun
   phrase* to appear, before a passage is treated as bearing on a claim. Measure
   against the same query: the target is TRUE_CONFLICT back near its 11-claim level
   without touching conflict classification.

2. **Re-run the authoritative pass** (`seolead research authoritative-run
   --package <id>`) and confirm the four resolved claims survive and the conflict
   count falls.

3. **Then generate one draft** for `prix panneaux solaires Belgique` and run
   factual and SEO QA. This is the measurement that has been deferred since Phase 2
   and remains the open question: whether the anti-fabrication prompt plus QA holds
   against a real model.

4. **Separately, verify the DataForSEO account.** It gates all SERP evidence and is
   an owner action of a few minutes.

5. **Consider a Flemish-specific SUBSIDY query.** The tri-regional query returned no
   Flemish authority, so `BE-VLG` claims cannot currently be resolved at all.

Do not raise thresholds, relax authority requirements or weaken conflict detection
to reach a cleaner-looking ledger. The four resolved claims are correct because
nothing was relaxed to obtain them.
