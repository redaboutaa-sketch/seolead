# PHASE 3.1 — EVIDENCE MODEL HARDENING

**Date:** 2026-08-12
**Workspace:** `/opt/seolead`, branch `main`
**Baseline:** `f09a9d8b49b85c685970fa79ad0662d1fe3b6222`
**Outcome:** the structural defect is fixed and measured against live data.

---

## 1. The old model

Phase 3 mapped one provider result to one "fact":

```
Tavily result  →  content (≈2 000 chars)  →  one ResearchEvidence row
                                          →  claim_risk(entire excerpt)
                                          →  supported = OBSERVED
                                                       AND relevance eligible
                                                       AND source quality ≥ bar
```

Support was a single boolean, and `OBSERVED` — a statement about publication
metadata — was one of its conditions.

## 2. The defect

The Phase 3 live run made both halves visible.

**A page excerpt is not a claim.** Tavily's `content` arrives as ~2 KB of page
text including navigation, cookie banners and AI-tool menus:

```
"Aller au contenu\n\nEnergy Village\n\n# Prix Panneaux Solaires 2026 …"
"La boutique ne fonctionnera pas correctement dans le cas où les cookies …"
"ChatGPTClaudePerplexityGoogle AI Mode\n\nVous souhaitez installer …"
```

Handing that to a risk classifier is document scanning, not claim classification:
**9 of 10 live excerpts came out HIGH risk** because each contained the word
`prime` or `TVA` somewhere in 2 KB. Relevance was equally degraded — a page titled
`"| Blog Webflow"` scored 1.00 on the strength of its body.

**Support required a publication date that Tavily never supplies.** `supported`
required `OBSERVED`; Tavily's general search returns no `published_date`; every
web fact was therefore `ESTIMATED`. The live measurement:

```
10 sources retrieved · 10 relevant · 0 rejected · 10 facts · 0 SUPPORTED
```

Zero, and not just for that query — **for any query, forever.** The web-research
path could not produce usable evidence at all.

The two are linked. Fixing the date rule alone would have let 2 KB page excerpts
become "supported facts", which is worse than producing none.

## 3. The new model

```
source
  → passage extraction        strip furniture, cut into quotable passages
  → atomic claim extraction   one materially testable proposition per claim
  → evidence mapping          claim ↔ passages, many-to-many
  → claim category            SUBSIDY · TAX · GRID_RULE · MARKET_PRICE · …
  → requirements              risk · authority · freshness · corroboration
  → EvidenceStatus            SUPPORTED / PARTIAL / UNSUPPORTED / CONFLICTING
```

Four dimensions, kept independent:

| Dimension | Question | Type |
|---|---|---|
| Relevance | is the source about the query? | `RelevanceStatus` |
| Authority | is this source entitled to establish it? | `SourceQuality` |
| Freshness | does this claim's truth depend on when? | `ObservationStatus` |
| Support | does a passage materially state it? | `EvidenceStatus` |

`ObservationStatus` (renamed from `Observability`, with the old name aliased so
stored rows and existing code keep working) says **when**. `EvidenceStatus` says
**whether**. Phase 3 asked the first and recorded the answer as the second.

### Freshness now binds only where the claim needs it

| Requirement | Meaning | Example category |
|---|---|---|
| `REQUIRED` | undated evidence cannot fully support it | SUBSIDY, TAX, GRID_RULE |
| `PREFERRED` | undated downgrades, does not disqualify | MARKET_PRICE, VENDOR_PRICE |
| `NOT_REQUIRED` | timeless | PRODUCT_SPEC, GENERAL |

"Panels are usually mounted facing south" needs no date. "The regional premium is
€1,750" is worthless without one. Treating both the same way is what broke Phase 3.

**HIGH-risk strictness is unchanged.** A subsidy claim still needs an OFFICIAL,
dated source. Nothing was relaxed where consequence is high.

## 4. Migrations

`0003_claims`, additive, applied and verified reversible against the live database
with prior data present (downgrade → upgrade → 19 tables, existing package still
readable and correctly marked `package_version = 1`).

`research_evidence` becomes **one row per atomic claim**:

```
passage · claim_category · evidence_status · authority_requirement
freshness_requirement · corroborating_sources · extraction_method
evaluation_reason
```

New `evidence_passage` table carries the many-to-many link between a claim and the
passages supporting it, with `supports` and `agrees_numerically` per pair.
`agrees_numerically` is nullable on purpose: NULL means "the claim carries no
figure", which is a different fact from "states a different figure" — and that
difference is what makes CONFLICTING detectable at all.

`observability` and `evidence_status` are **separate columns**, pinned by a
regression test.

## 5. Claim extraction

`passage_extraction.py` → `claim_extraction.py`, both deterministic. No model
participates: an LLM splitting claims would be an LLM deciding what counts as a
fact.

**Passage extraction** drops navigation, cookie banners, footers, share widgets,
AI-tool menus, price tiles (low alpha ratio) and unpunctuated menu lists —
conservatively, because discarding real evidence is worse than carrying noise into
a stage that can still reject it. Drop reasons are recorded per passage.

**Claim extraction** splits sentences, and splits *within* a sentence when it
carries several independently testable propositions. A paragraph mixing pricing, a
subsidy and an ROI figure becomes several claims. Questions and calls to action
("Vous souhaitez un devis ?") are not assertions and are skipped. Repeated
sentences are deduplicated, because counting one twice would fake corroboration.

Every claim keeps its **exact supporting passage**, its source ref and its
extraction method, so QA and a human reviewer can quote the text without refetching
the page.

## 6. Authority policy

Per category, from vertical configuration:

| Category | Authority | Freshness | Corroboration |
|---|---|---|---|
| SUBSIDY, TAX, REGULATION, GRID_RULE, ELIGIBILITY | OFFICIAL | REQUIRED | 1 |
| GUARANTEED_SAVINGS, ROI | INSTITUTIONAL | REQUIRED | 2 |
| ENERGY_PRICE | INSTITUTIONAL | REQUIRED | 1 |
| MARKET_PRICE | SPECIALIST | PREFERRED | **3** (SOLAR_BE) |
| VENDOR_PRICE | ANY | PREFERRED | 1 |
| PRODUCT_SPEC, GENERAL | SPECIALIST / ANY | NOT_REQUIRED | 1 |

Two distinctions the mission asked for, made concrete:

- **A vendor is the authority on its own displayed price**, and establishes that
  price only — never a market average. `VENDOR_PRICE` and `MARKET_PRICE` are
  separate categories with different bars.
- **Commercial and specialist sources inform market context but cannot establish
  official rules.** A commercial page quoting a premium is reporting, not
  establishing.

Nothing solar-specific is in the core. `claim_categories`, `authority_policy` and
`official_source_policy` all live in `config/verticals/solar_be.yaml`, and a test
asserts no Belgian domain appears in the planner's code.

### Targeted authoritative research

When a HIGH-risk claim is unresolved, `research_planner.py` proposes narrow
searches restricted to the vertical's authoritative domains — one query per
*category*, not per claim, bounded by `max_queries` and a hard ceiling of 5.

The live run produced:

```
SUBSIDY   → "prix panneaux solaires Belgique prime officielle BE"    (14 domains)
GRID_RULE → "prix panneaux solaires Belgique tarif prosumer regulateur BE"
```

The plan is generated, not executed — executing it is a paid call and belongs to
the next live run.

## 7. Support semantics

`SUPPORTED` now means: **a specific eligible passage materially states this
atomic claim, from a source of sufficient authority, with enough corroboration,
and dated if this category needs a date.**

| Status | When |
|---|---|
| `SUPPORTED` | all requirements met |
| `PARTIALLY_SUPPORTED` | stated, but corroboration or a required date is missing |
| `UNSUPPORTED` | nothing states it, or authority is insufficient |
| `CONFLICTING` | eligible sources disagree on the figure |

An OFFICIAL source satisfies corroboration alone — a regulator speaks for itself; a
market average does not.

### Writer contract

`writer_payload()` returns exactly four keys and nothing else:

```
supported_claims · partially_supported_claims (labelled, opt-in)
unresolved_facts · forbidden_claims
```

No raw excerpts, no rejected sources, no eligible-evidence dump. Tests assert the
racing-game source cannot appear anywhere in the writer's view.

## 8. Live validation

Same query, same providers, no thresholds changed. **Tavily only** — DataForSEO is
still `40104` (see §10), so this measures the evidence model, not a full pipeline.

| | Phase 3 | Phase 3.1 |
|---|---:|---:|
| Sources retrieved | 10 | 10 |
| Sources eligible / rejected | 10 / 0 | 10 / 0 |
| Sources dated | 0 | 0 |
| Passages kept / dropped | — | **78 / 125** |
| "Facts" or atomic claims | 10 excerpts | **121 claims** |
| **SUPPORTED** | **0** | **54** |
| PARTIALLY_SUPPORTED | — | 22 |
| UNSUPPORTED | 10 | 22 |
| CONFLICTING | — | 23 |
| Multi-source claims | 0 | **82** |
| HIGH-risk claims | 9 of 10 | 18 of 121 |
| HIGH-risk blocked | 9 | **18** |

**The blocker is gone**: 54 supported claims from sources that carry no dates at
all. **The protection is intact**: every one of the 18 HIGH-risk claims is still
refused, each with a readable reason —

```
SUBSIDY / UNSUPPORTED
  "Les primes régionales : en Région Bruxelles-Capitale, une prime à l'ins…"
  SUBSIDY claims require an OFFICIAL source; the best supporting source is
  SPECIALIST. Belgian premiums differ by region and change annually.

GRID_RULE / UNSUPPORTED
  "Le tarif prosumer : en Wallonie, les propriétaires de panneaux photovo…"
  GRID_RULE claims require an OFFICIAL source; the best supporting source is
  SPECIALIST.
```

Writer view: 54 supported claims, 0 partial (opt-in, off), and 5 forbidden
categories — `SUBSIDY`, `REGULATION`, `ENERGY_PRICE`, `GRID_RULE`, `ROI`.

### A precision bug the live run exposed, and fixed

The first measurement classified 9 claims as `TAX` — including
*"Entre 4.000 € et 14.000 € TVAC"* and *"1 000 € par kWc hors TVA"*. Substring
matching found `tva` inside `TVAC`, so **VAT-inclusive pricing was being treated
as a claim about the tax rate**, pushing ordinary price claims to HIGH risk and
blocking them.

Fixed two ways: category terms now match on **word boundaries** (so `primeur` no
longer matches `prime`), and VAT-as-price-qualifier forms (`TVAC`, `hors TVA`,
`HTVA`, `TVA comprise`) are excluded unless the claim names an actual rate. Result:

```
TAX claims  9 → 0        HIGH-risk  28 → 18        SUPPORTED  51 → 54
```

Nine tests pin it.

## 9. Regression results

**433 tests pass**, no credentials, no network. Every case the mission listed:

| Required regression | Test |
|---|---|
| Missing publication date does not invalidate timeless support | `test_an_undated_source_can_still_support_a_timeless_claim` |
| A 2 KB excerpt becomes multiple atomic claims | `test_a_page_excerpt_becomes_several_atomic_claims` |
| Cookie / navigation text never becomes a claim | `test_cookie_and_navigation_text_never_becomes_a_claim` |
| Commercial subsidy claim cannot satisfy OFFICIAL | `test_a_commercial_page_cannot_establish_a_subsidy` |
| Vendor price supports itself, not a market average | `test_a_vendor_price_supports_itself_but_not_a_market_average` |
| One source supports multiple claims | `test_one_source_can_support_multiple_claims` |
| One claim has multiple sources | `test_one_claim_can_have_multiple_sources` |
| Racing-game source remains IRRELEVANT | `TestRacingGameRegression` (unchanged) |
| Unsupported numeric claim remains blocked | `test_draft_claim_with_no_matching_supported_claim_blocks` |

Plus: observation and evidence status are separate columns; a rejected source never
becomes a candidate; repeated sentences do not fake corroboration; the planner
hard-codes no domain; VAT-as-price-qualifier is not a tax claim.

New suites: `test_evidence_model.py` (58), `test_writer_contract_and_qa.py` (20),
`TestPhase31EvidenceModelRegression` (6).

**RelevanceGate thresholds were not touched.** All Phase 2 and Phase 3 tests pass
unchanged except one assertion updated from `package_version == 2` to `== 3`.

## 10. DataForSEO status

`CONFIGURED` — **not** `CONFIGURED_AND_AVAILABLE`.

A real authenticated minimal call (`GET /v3/serp/google/locations/be`, not a paid
task) returned:

```
HTTP 403  status_code 40104
"Please verify your account before using the API."
cost: 0
```

Credentials are valid — bad ones return 401. The account still needs verification
in the provider panel. Cost incurred: **$0.00**. No live rerun was required and
none was performed.

## 11. Remaining limitations

1. **Some page furniture still becomes a claim.** Live output included
   *"Prix Panneaux Solaires 2026 en Belgique : Coûts par kWc, m² & Devis"* (a page
   title) and *"Toggle [...] ## Questions fréquentes"* (markdown residue).
   Passage extraction is conservative by design; heading and UI-residue detection
   is the next increment.
2. **CONFLICTING over-triggers** — 23 of 121. Numeric comparison across a 10-source
   corpus flags figures that are on-topic but measuring different things (a price
   per kWc against a total installation cost). It errs toward blocking, which is
   the safe direction, but it will frustrate a reviewer.
3. **MARKET_PRICE is a catch-all** — 62 of 121. Any unqualified price mention lands
   there. Splitting price-per-unit from total-cost claims would sharpen both
   categories and reduce (2).
4. **Extraction is lexical.** Sentence and clause splitting with regex; no syntactic
   parsing. Claims spanning two sentences ("Il en existe trois. Le premier coûte…")
   are not joined.
5. **Passage↔claim matching is word-overlap.** A passage restating a claim in
   different vocabulary may not match it, understating corroboration.
6. **The authoritative research plan is generated but not executed.** Closing the
   HIGH-risk gaps needs the paid call the plan describes.
7. **No official source has ever been retrieved** for this query. Every HIGH-risk
   refusal so far is correct *and* unresolvable until targeted research runs.
8. **Corroboration counts sources, not independence.** Three pages owned by one
   group would count as three.
9. **DataForSEO remains unverified end to end**, so SERP-derived evidence and the
   SERP half of the opportunity score are still unexercised.

## 12. Files changed

| Area | Files |
|---|---|
| `app/core/enums.py` | `ObservationStatus`, `EvidenceStatus`, `FreshnessRequirement`, `AuthorityRequirement`, `ClaimCategory` |
| `app/services/` | `passage_extraction.py`, `claim_extraction.py`, `claim_policy.py`, `evidence_model.py`, `research_planner.py`, `package_builder_v3.py`, `factual_qa_v2.py` (new); `brief_service.py`, `pipeline_v2.py` (updated) |
| `app/models/` | `research.py` — atomic-claim columns + `EvidencePassage` |
| `migrations/` | `0003_claim_level_evidence.py` |
| `config/verticals/` | `solar_be.yaml`, `test_generic.yaml` — claim categories, authority policy, official-source policy |
| `tests/` | `test_evidence_model.py`, `test_writer_contract_and_qa.py` (new); `test_regressions.py`, `test_pipeline_v2.py` (updated) |
| root | this report |

## 13. Recommended live revalidation procedure

1. **Verify the DataForSEO account** at `https://app.dataforseo.com/`, then:

   ```bash
   docker exec seolead_api seolead credentials     # expect all CONFIGURED
   ```

2. **Run the full pipeline** — unchanged command, no flags:

   ```bash
   docker exec seolead_api seolead research run \
     --vertical SOLAR_BE --query "prix panneaux solaires Belgique" \
     --market BE --language fr
   ```

3. **Read the claim ledger first**, not the draft:

   ```bash
   docker exec seolead_api seolead package show <research_package_id>
   docker exec seolead_api seolead package rejected <research_package_id>
   ```

   Expect roughly: 10 eligible sources, ~120 atomic claims, ~50 supported, all
   HIGH-risk blocked, and an authoritative research plan naming SUBSIDY and
   GRID_RULE.

4. **Expect the draft to be blocked if it asserts a HIGH-risk claim.** That is the
   system working. Do not raise thresholds; the fix is step 5.

5. **Execute the authoritative research plan** — the one piece of new capability
   that has not been exercised. Until a regulator source enters the evidence set,
   no subsidy, tariff or grid-rule statement can be published, and the Solar pilot
   cannot say anything quantitative about Belgian public aid.

6. **Then judge a real draft.** Generation has still never produced a full article
   from a claim-level evidence set; whether the anti-fabrication prompt plus
   factual QA V2 holds against a real model remains the open question.
