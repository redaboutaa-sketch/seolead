# PHASE 3.4 — WHY DOES THE "PRICE" PAGE CONTAIN NO PRICE?

**Date:** 2026-08-13
**Workspace:** `/opt/seolead`, branch `main`
**Baseline:** `ab02affe54ed98e511dbffb8f8ecbb4fe7f4b13a`
**Outcome:** Root cause found and fixed. The regenerated page answers the price
question from evidence, and both QA layers pass.

---

## 1. Executive Summary

**The price evidence was there the whole time.** 36 quantified price claims with
real Belgian figures — "Entre 4.000 € et 14.000 € TVAC pour une installation de 3 à
10 kWc", "1 200 à 1 800 €/kWc, pose comprise" — sat in the Phase 3.3 evidence set.
None reached the writer. The page was not cautious; it was starved by two defects
and one misapplied policy.

**Root cause: B, with C as its consequence.** Price claims existed and matched, but
`MARKET_PRICE` policy demanded three corroborating SPECIALIST sources — a bar
designed for the sentence *"the average Belgian installation costs X"* — and applied
it to sourced ranges that assert no average at all. 17 of 34 quantified price claims
died on corroboration and 10 more on authority. With no price claim SUPPORTED, the
brief's 12 `required_facts` were all `[GENERAL]`, and the writer was never given a
figure to state.

**Two defects sat underneath that.** First, region over-scoping: a claim naming no
region was defaulted to `BE`, while 16 of 27 live sources were detected `BE-WAL`
(any page mentioning Wallonia once), so a claim was refused by the very passage it
had been extracted from. Fixing it took `MARKET_PRICE` SUPPORTED from 17 to 31.
Second — found only once the draft finally contained numbers — the SEO numeric check
read `fact` keys from a package whose builder writes `claim`, so **every figure in a
V3 package was invisible to it** and a correctly sourced price read as "in no
retrieved source". Phase 3.3's figure-free draft hid that bug perfectly.

**The vacuous pass is now impossible in both directions.** `NO_QUANTIFIED_ANSWER`
blocks when the brief supplied eligible price evidence and the page states no
figure; it stays advisory when there was nothing to state. A page with no price
evidence must now say so, and one with price evidence must answer.

**The regenerated draft answers the question.** Same model (`gpt-4o-mini`), same
thresholds, no weakened gate: five sourced price statements in the opening section,
each carrying its basis, no outbound links, Factual QA `PASSED` (score 100), SEO QA
`PASSED` (score 100). Nothing was lowered to get there — the matcher thresholds,
authority requirements, relevance gate, HIGH-risk rules and conflict policy are all
byte-identical to Phase 3.3.

**One honest limitation stands out:** all five figures trace to a single SPECIALIST
source. That is the `OBSERVED_PRICE_RANGE` policy working as designed (a range
reported *by* a source needs that source), but the page's price answer currently
rests on one domain. §23 states what would fix it.

---

## 2. Exact Draft Trace

The Phase 3.3 draft, traced backwards from the missing price:

| Stage | What it produced | Verdict |
|---|---|---|
| Research | 27 eligible sources, 36 quantified price claims present in text | evidence existed |
| Passage → claim | price sentences extracted correctly, verbatim | not the defect |
| Claim ↔ passage matching | region default `BE` vs source region `BE-WAL` → **0 candidates** for most price claims | **defect 1** |
| Claim policy | surviving claims classed `MARKET_PRICE` → SPECIALIST + **3 sources** | **root cause** |
| Evidence status | 1 SUPPORTED / 17 PARTIALLY / 16 UNSUPPORTED (of 34) | starved |
| Package → brief | `supported_claims` carried no price → 12 `required_facts`, all `[GENERAL]` | **consequence** |
| Writer | given no figure; told to be useful anyway | wrote around the gap |
| Factual QA | asserted nothing checkable → PASS | **vacuous pass** |
| SEO QA | `NO_QUANTIFIED_ANSWER` advisory only | did not block |

The competitor link in that draft came from the same place: `"Pour en savoir plus,
découvrez notre article sur les panneaux Plug and Play !"` reached the brief as a
`required_fact`. The writer was **given** the link, not inventing it.

---

## 3. Price Evidence Inventory

Measured on the Phase 3.3 corpus after the region fix, before the taxonomy split.

**34 quantified price claims:**

| Evidence status | Count |
|---|---|
| SUPPORTED | 1 |
| PARTIALLY_SUPPORTED | 17 |
| UNSUPPORTED | 16 |

**Why they were blocked:**

| Blocking family | Count |
|---|---|
| corroboration (needs 3 sources) | 17 |
| authority (needs SPECIALIST) | 10 |
| no candidate passage at all | 6 |

**Quality of the sources that did support them:** SPECIALIST 18, COMMERCIAL 11,
OFFICIAL 1.

Representative claims, all real and all refused:

```
Entre 4.000 € et 14.000 € TVAC pour une installation de 3 à 10 kWc
Une installation standard de 5 kWc coûte environ 6.500 € à 8.500 €
1 200 à 1 800 €/kWc, pose comprise
Le panneau seul revient à 130 € – 170 €/m²
```

---

## 4. Root Cause Classification

**Primary: B — price evidence existed and matched, but the policy applied to it was
the wrong policy.**
**Secondary: C — the brief therefore carried no price, so the writer could not
answer.**

Not A (evidence was retrieved). Not D in the general case, though two matching
defects contributed (§15 and the region fix). Not E.

Evidence for the diagnosis:

1. 36 quantified price claims present in the retrieved text — the figures existed.
2. Debug of a claim against its **own source passage** showed `supports=true,
   agrees=true` yet `candidates=0` — proof of the region over-scoping defect.
3. After the region fix, the blocking reasons were explicitly *corroboration* (17)
   and *authority* (10), not "no evidence" — proof the policy, not the retrieval,
   was refusing them.
4. `MARKET_PRICE`'s three-source rule exists for the sentence *"the average is X"*.
   27 of 34 blocked claims assert no average whatsoever.

---

## 5. Existing MARKET_PRICE Semantics

Before this phase, `MARKET_PRICE` meant everything with a currency symbol in it,
and carried one policy: `SPECIALIST` authority, `PREFERRED` freshness, **3**
corroborating sources. That is the correct bar for a claim about a whole market and
much too strong for a figure attributed to a named source.

Three genuinely different assertions were sharing it:

* "The average Belgian installation costs €6 000" — a claim about the market.
* "Source S reports €4 000–14 000 for 3–10 kWc" — a claim about what S observed.
* "Our 5 kWc package is €4 400" — a claim about one vendor's own price.

A further finding: 17 claims classified `MARKET_PRICE` and marked SUPPORTED were
regulatory or electricity-contract statements that merely contained a euro figure.
The residual bucket was absorbing anything numeric.

---

## 6. Price Normalization

New module `app/services/price_normalization.py`. It extracts what the source
**actually stated** and infers nothing:

* `PriceBasis` — `TOTAL`, `PER_WP`, `PER_KWP`, `PER_M2`, `PER_PANEL`, `PER_KWH`,
  `PER_YEAR`, `UNKNOWN`.
* `VatStatus` — `INCLUDED` (TVAC/TTC), `EXCLUDED` (HTVA), `UNKNOWN`.
* System size in kWc, battery inclusion, installation inclusion — each `None` when
  the text does not say.
* `is_usable` — a bare amount with `UNKNOWN` basis is **not** an answer. €6 000
  could be a total, a per-kWc rate or a per-m² figure; the three differ by an order
  of magnitude.
* `comparable_key()` — basis, VAT, currency, battery and installation inclusion.
  Two prices may only be ranged together when this key matches.

`TOTAL` is only assumed when the sentence names an installation, a budget or an
investment — never as a fallback for "could not tell".

---

## 7. Taxonomy Changes

`ClaimCategory` price members, with their policies:

| Category | Authority | Min sources | Meaning |
|---|---|---|---|
| `MARKET_AVERAGE` | SPECIALIST | **3** | "the average Belgian installation costs X" |
| `OBSERVED_PRICE_RANGE` | SPECIALIST | **1** | "source S reports X–Y" |
| `VENDOR_PRICE` | ANY | 1 | a vendor's own displayed price |
| `MARKET_PRICE` | SPECIALIST | 3 | unqualified residual, unchanged |

Classification order is VENDOR → AVERAGE → RANGE → residual, so "nos tarifs" wins
over a range pattern and "prix moyen" wins over an incidental range.

**The market-average bar was not lowered.** A claim asserting an average still needs
three corroborating specialist sources. What changed is that a claim asserting a
*sourced range* is no longer forced to meet the average's bar — because a range
reported by S is a statement about S's observation, and S is the authority for it.

---

## 8. Observed Price Range

`observed_range(contexts, minimum=N)` groups observations by `comparable_key()` and
returns the largest comparable group, or `None`.

It **refuses rather than normalises**. Per-kWc and whole-installation figures are
not merged. VAT-inclusive and VAT-unknown figures are not merged. No arithmetic
converts one basis into another, because that would manufacture a number no source
stated.

The result is labelled in its own payload: `"observed across the retrieved sample —
not a market average"`. `minimum` comes from `price_policy.observed_range_min_sources`
in the vertical profile (Solar BE: 2), never from code.

In the final live run the range was `4 000–10 000 EUR, basis TOTAL, VAT UNKNOWN,
2 observations` — and it was correctly *not* presented as an average anywhere.

---

## 9. ContentBrief Changes

Migration `0004_core_q`, all columns additive and nullable, so Phase 3.3 briefs
remain readable:

| Column | Purpose |
|---|---|
| `core_question` | the one question the page exists to answer |
| `core_answer_status` | `EVIDENCE_AVAILABLE` / `CORE_QUESTION_UNRESOLVED` / `NOT_APPLICABLE` |
| `core_answer_evidence` | `{"answers": [...], "observed_range": {...}\|null}` |
| `must_answer_directly` | whether the writer owes the reader a figure |

`core_answer_status` is **stored**, not derived at read time: "was this question
answerable when this page was written?" is a fact about that run's evidence, and
re-deriving it later against a changed evidence set would silently rewrite history.

When evidence exists, the price answers are inserted at the **front** of
`required_facts` — a price page that buries its price under six sections of context
has not answered the query. When it does not, the unresolved note is inserted at the
front of `missing_information`.

**No Solar logic reached core orchestration.** A new `price_policy` block in the
vertical profile supplies `enabled`, `answer_required_intents`,
`price_query_terms` and `observed_range_min_sources`. A vertical that declares none
has no core price question by definition.

---

## 10. Writer Contract Changes

Added to the system prompt:

* **CORE QUESTION — YOU MUST ANSWER IT DIRECTLY** (when `must_answer_directly`):
  answer in the opening section, before any context, using only the supplied price
  evidence, carrying each figure's basis and VAT status; do not defer the answer to
  a CTA or tell the reader to ask a professional instead of giving the figures.
* **CORE QUESTION — EVIDENCE INSUFFICIENT** (when unresolved): say so plainly and
  early, explain what determines the cost, state no number. "Inventing one would be
  worse than the gap."
* **PRICE AND QUANTITY WORDING**: a figure reported by one source is what that
  source reports; an observed range is an observed range, never an average or "the"
  price in Belgium; never turn an observed sample into a national average; always
  carry the basis; never combine figures on different bases.
* **VAT belongs to one figure, never to a list.**

The user payload gained `core_question`, `core_answer_status`, `price_evidence`
(each with its extracted `price_context`) and `observed_price_range`.

---

## 11. External Link Prevention

Defence in depth, three layers:

1. **Prompt** — an explicit LINKS section: no markdown link or URL in the body,
   never to another company, comparison site or installer; sources are recorded
   separately and are not citations in the copy.
2. **Claim extraction** — promotional sentences no longer become claims. The
   Phase 3.3 link arrived via `"Pour en savoir plus, découvrez notre article…"`
   reaching the brief as a fact to state; the old check was anchored to the start of
   the sentence, and the opening clause moved the verb past it.
3. **QA** — `EXTERNAL_LINK_IN_BODY` remains blocking (added in Phase 3.3).

The final draft contains zero outbound links.

---

## 12. NO_QUANTIFIED_ANSWER Policy

| Brief state | Body states a figure? | Finding |
|---|---|---|
| `must_answer_directly=true` | no | **BLOCKING** |
| `must_answer_directly=true` | yes | none |
| unresolved / not applicable | no | advisory, still reported |

Whether silence is a failure depends entirely on whether the evidence could have
spoken. Blocking a page that genuinely had no price evidence would only pressure the
next run into inventing a figure — the opposite of the mission.

A related check was added: **`VAT_STATUS_GENERALISED`** (blocking). The first
regenerated draft wrote "Ces prix incluent la TVA" about six figures of which one
was marked TVAC — restating five prices by up to 21%. An explicitly hedged form
("…lorsque cela est spécifié") is correct qualification and is not flagged.

---

## 13. Targeted Research

Stage 5b previously fired only for unresolved **HIGH-risk** claims. Price claims are
MEDIUM and LOW risk, so for a price query it never fired at all — the pipeline never
took a second look at exactly the thing the page was about.

`_price_answer_missing()` now also triggers it: price policy enabled, query matches
the vertical's price vocabulary, and no SUPPORTED price claim with a usable basis.
Query templates `MARKET_AVERAGE`, `MARKET_AVERAGE_VLG` and `OBSERVED_PRICE_RANGE`
were added, and `MARKET_AVERAGE` was added to the `claim_categories` of the three
configured bodies that publish cost guidance (`energie.wallonie.be`,
`energiesparen.be`, `apere.org`).

In the live runs the price gap evaluated `False` — the commercial corpus already
carried usable price evidence once the region and taxonomy defects were fixed — so
the price queries correctly did not fire and no money was spent on them. The
mechanism is exercised by the code path, not by this run's data.

---

## 14. DataForSEO State

`CONFIGURED_BUT_ACCOUNT_BLOCKED`, unchanged.

```
HTTP 403 — DataForSEO status_code 40104:
"Please verify your account before using the API."
```

Cost incurred: **$0**. Checked once per phase, not retried.

**Consequence discovered this phase:** the SERP stage is a deliberate hard stop
("SERP is the backbone… this stops rather than degrading"), and there is no longer a
SERP snapshot within the 24 h TTL, so `seolead research run` now halts at
`stopped_at: "serp"` with `RESEARCH_FAILED`. The Phase 3.4 draft was therefore
generated through the same service functions the pipeline calls — research →
package → brief → draft → factual QA → SEO QA — with the SERP stage absent. Every
layer this phase changed was exercised; SERP-derived inputs (`content_gap`, PAA
coverage) were not. Nothing was persisted to the database.

---

## 15. Page-Title Claim Fix

`CREG : Commission de Régulation de l'Électricité et du Gaz` was a supported factual
claim. It is a label; nothing about it is true or false. Worse, such fragments
corroborate each other across pages and inflate support counts.

The test is a **predicate**. A fragment with no verb and the shape of a heading is a
label. A verb anywhere keeps it — a real claim with an unusual verb must not be lost
to a heuristic about capitalisation. Verbless fragments are rejected when they carry
site-title furniture (`|`, `–`, a leading `ACRONYM :`), are mostly capitalised, or do
not end a sentence.

The inflection matcher excludes `-ment` (gouvernement) and `-ité` (électricité),
the noun endings French shares with its verb forms — without those exclusions
"Électricité" reads as a participle and every title looks like a sentence.

---

## 16. Regenerated Draft

`SOLAR_BE` / `prix panneaux solaires Belgique` / BE / fr, `gpt-4o-mini-2024-07-18`
unchanged, temperature unchanged, **not published, not persisted**.

Three generations were run, each after a distinct pipeline fix — no prose iteration,
no model change, no threshold change:

| Run | Change since previous | Blocking result |
|---|---|---|
| 1 | region fix + taxonomy + core question + writer contract | `UNSUPPORTED_NUMERIC_CLAIM` (6), `UNSUPPORTED_DRAFT_CLAIM` (1) — both **defects in QA**, §17 |
| 2 | numeric corpus fix + paraphrase mapping fix | `VAT_STATUS_GENERALISED` — a real overstatement in the copy |
| 3 | hedged-VAT false positive corrected | **none** |

Run 3, 355 words:

```
# Prix des Panneaux Solaires en Belgique

En Belgique, le prix des panneaux solaires varie selon plusieurs facteurs.
Voici les prix observés :

- Entre 4.000 € et 14.000 € TVAC pour une installation de 3 à 10 kWc.
- Entre 320 € et 430 € par m² pour une installation complète (monocristallins).
- Le panneau seul coûte entre 130 € et 170 €/m².
- Pour une installation de 5 à 6 kWc (12 à 15 panneaux), le budget est estimé
  entre 7.000 € et 9.500 €.
- Un panneau de 400 Wc coûte environ 220 € à 280 €.
...
## Comprendre le Besoin d'Installation de Panneaux Solaires
## Détails des Coûts d'Installation
## Processus d'Installation des Panneaux Solaires
## Vérifications Préliminaires Avant l'Installation
## Questions Fréquemment Posées sur les Panneaux Solaires
## Prochaines Étapes pour Votre Projet Photovoltaïque
```

The answer leads, each figure carries its basis, nothing is called an average, and
there are no links.

---

## 17. Quantified Claims Audit

Every quantified sentence in the final draft, mapped to its ledger claim:

| Draft sentence | Category | Status | Risk | n | Quality |
|---|---|---|---|---|---|
| Entre 4.000 € et 14.000 € TVAC pour 3–10 kWc | `OBSERVED_PRICE_RANGE` | SUPPORTED | LOW | 1 | SPECIALIST |
| Entre 320 € et 430 € par m² | `OBSERVED_PRICE_RANGE` | SUPPORTED | LOW | 1 | SPECIALIST |
| Le panneau seul 130 € – 170 €/m² | `OBSERVED_PRICE_RANGE` | SUPPORTED | LOW | 1 | SPECIALIST |
| 7.000 € à 9.500 € pour 5–6 kWc | `OBSERVED_PRICE_RANGE` | SUPPORTED | LOW | 1 | SPECIALIST |
| Un panneau de 400 Wc ≈ 220 € à 280 € | `OBSERVED_PRICE_RANGE` | SUPPORTED | LOW | 1 | SPECIALIST |

Source: `energy-village.be/panneaux-photovoltaiques-prix` for all five.
**No invented numeric price.** Every figure appears verbatim in a SUPPORTED claim.

Ledger for this run: 176 claims — 77 SUPPORTED, 20 PARTIALLY_SUPPORTED,
79 UNSUPPORTED, 0 CONFLICTING. Price claims: 24 SUPPORTED, 15 PARTIALLY, 42
UNSUPPORTED.

**Two defects were found by this audit, not by a test:**

1. **The numeric check never saw a V3 package.** `_evidence_numbers()` read
   `f.get("fact")`; the V3 builder writes `claim`. The corpus was effectively empty,
   so all six prices read as unsupported. It now reads SUPPORTED claims — strictly
   narrower than the V2 rule it replaces for V3 packages, since V2 counted every
   fact regardless of support.
2. **An accurate paraphrase was blocked.** `"Le panneau seul coûte entre 130 € et
   170 €/m²"` against the ledger's `"Le panneau seul revient à 130 € – 170 €/m²"`
   shares one long content word and every figure, and the topic gate needed two.
   Reproducing all of a claim's figures on a shared topic term now carries the
   match — blocking that would teach the writer to avoid quoting evidence
   accurately.

---

## 18. Factual QA

**PASSED — score 100, 0 blocking, 0 findings.**

Ledger: 176 claims (77 SUPPORTED / 20 PARTIALLY / 79 UNSUPPORTED / 0 CONFLICTING).
Every factual sentence in the draft traces to a SUPPORTED claim. No HIGH-risk claim
is asserted; 41 of 42 remain unresolved and unused, which is a research gap, not a
draft defect.

This pass is **not vacuous**: the page makes five checkable quantified assertions
and each was checked.

---

## 19. SEO QA

**PASSED — score 100, 0 blocking, 0 findings.**

| Check | Result |
|---|---|
| core question answered? | **yes** — five sourced figures in the opening section |
| quantified answer present? | yes — `NO_QUANTIFIED_ANSWER` not raised |
| intent fit | COMMERCIAL → LANDING_PAGE, price answer first |
| external links | none |
| CTA fit | "demander un devis personnalisé", matches the configured CTA |
| structure | one H1, six H2, 355 words |
| keyword stuffing | under the 2.5% density ceiling |
| meta title | 31 chars (max 60) |
| meta description | 92 chars (max 155) |
| VAT qualification | no blanket VAT claim |

---

## 20. Approval State

The draft was **not persisted**, because the pipeline halts at the SERP stage
(§14) and the run was executed through the service layer. Had it been persisted, the
recorded state would be `PENDING_APPROVAL`: both QA layers passed with no blocking
finding, and `PENDING_APPROVAL` is what the pipeline creates.

**Nothing was auto-approved and no state was forced.** Approval remains a separate
table requiring a human actor.

---

## 21. Tests

**550 pass, 0 fail.** All 523 pre-existing tests preserved; 27 added.

Two existing assertions were updated to follow the intentional taxonomy split
(`MARKET_PRICE` → `MARKET_AVERAGE` for "le prix moyen…"). Both keep their original
intent — that a vendor's rate card cannot establish a national average.

The ten required regressions, in `tests/test_price_evidence.py`:

| # | Test | Guards |
|---|---|---|
| 1 | `test_1_eligible_price_evidence_makes_the_answer_mandatory` | brief requires a direct answer, figures lead |
| 2 | `test_2_no_eligible_evidence_leaves_the_core_question_unresolved` | explicit unresolved state, stated as a limitation |
| 3 | `test_3_vendor_advertised_price_is_not_a_belgian_market_average` | taxonomy separation |
| 4 | `test_4_comparable_observations_may_form_an_observed_range` | range construction + "not a market average" wording |
| 5 | `test_5_incomparable_observations_may_not_form_a_range` | per-kWc vs total refuses |
| 6 | `test_6_the_writer_is_told_not_to_link_to_competitors` | prompt prevention |
| 7 | `test_7_eligible_evidence_and_no_figure_is_blocking` | the vacuous pass cannot recur |
| 8 | `test_8_no_eligible_evidence_and_no_figure_is_not_blocked` | honesty is not punished |
| 9 | `test_9_a_page_title_alone_does_not_become_an_atomic_claim` | three real titles |
| 10 | `test_10_a_quantified_draft_claim_must_map_to_a_retrieved_number` | supported figure passes, altered figure blocks |

Plus regressions for every defect found during the phase: bare-amount rejection,
non-price query, single observation, VAT-treatment mismatch, external link at QA,
promotional sentence as a fact, real sentence surviving the title filter, V3 numeric
corpus, unsupported claim's numbers not counting, paraphrase mapping, and three VAT
generalisation cases.

Tests 7 and 9 were mutation-checked: reverting each fix fails exactly the tests that
name it.

---

## 22. Provider Usage / Cost

Per live run:

| Provider | Requests | Operations | Cost |
|---|---|---|---|
| Tavily | 6 | 1 search + 5 domain-restricted | not priced by the API |
| OpenAI | 2 | brief enrichment + draft (`gpt-4o-mini`) | ~4 000 in / ~600 out tokens per draft |
| DataForSEO | 1 | credential probe, 403 | **$0** |

Three live generations were run in total (§16). No community provider was called
(`community_research_enabled: false` for this vertical).

---

## 23. Remaining Limitations

1. **The price answer rests on one domain.** All five figures come from
   `energy-village.be`. `OBSERVED_PRICE_RANGE` requires one source by design — the
   source is the authority for its own observation — but a reader is being shown one
   company's view of the market. The fix is corroboration breadth, not a lower bar:
   more specialist domains, or a `MARKET_AVERAGE` claim from a body that publishes
   cost guidance.
2. **No `MARKET_AVERAGE` claim reached SUPPORTED.** The page states observed ranges,
   not "the average Belgian installation costs X". That is the correct outcome given
   the evidence, and it is also the gap worth closing.
3. **Navigation fragments still reach the claim set.** One price answer was
   `"Liens utiles [...] Le coût d'une installation…"` — a link-list fragment carrying
   a real sentence. The title filter catches labels, not concatenated navigation.
4. **41 of 42 HIGH-risk claims remain unresolved.** Subsidy and grid-rule claims
   still cannot be established; the page correctly says nothing about them.
5. **The pipeline cannot complete end-to-end** while DataForSEO is blocked (§14).
   SERP-derived inputs are untested this phase.
6. **`price_context` extraction is regex-based** and French/Dutch-tuned. A new
   language needs new patterns, and an unrecognised basis correctly yields `UNKNOWN`
   rather than a wrong guess.
7. **VAT status is `UNKNOWN` for five of six answers.** The sources did not state it.
   The page therefore cannot say whether most of its figures include VAT — a
   material gap for a Belgian buyer.

---

## 24. Phase 4 Readiness

Ready in the sense that matters: the pipeline now produces a page that answers its
query from evidence, and refuses when it cannot. The two failure modes Phase 4 would
have inherited — a vacuous factual pass and a brief that starves the writer — are
both closed and both regression-tested.

Blocking for a full end-to-end Phase 4 run: DataForSEO account verification. Without
it there is no SERP stage, so competitor analysis, PAA coverage and content-gap
scoring cannot be exercised.

---

## 25. Exact Recommended Next Action

**Verify the DataForSEO account at `app.dataforseo.com`** (owner action; no code
change). It is the single blocker on an end-to-end run, it costs nothing to resolve,
and every other layer is now validated against live data.

Immediately after that, and before Phase 4: re-run the pilot query through
`seolead research run` end to end and confirm the SERP-derived stages behave, then
address limitation 1 by widening the specialist domain set for price evidence so the
page's price answer does not rest on a single company.

---

**Commit:** `fix: require evidence-backed answers for price intent`
