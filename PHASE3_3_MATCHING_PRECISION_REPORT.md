# PHASE 3.3 — CLAIM↔PASSAGE MATCHING PRECISION & LIVE REVALIDATION

**Date:** 2026-08-12
**Workspace:** `/opt/seolead`, branch `main`
**Baseline:** `c4578d404117cac725c824fccca44e57ea8fffba`
**Outcome:** SUCCESS on the objective; the draft is correctly blocked, not approved.

---

## 1. Executive Summary

**`TRUE_CONFLICT` went from 163 to 0**, and nothing downstream was weakened to
achieve it. Conflict classification, authority requirements, relevance thresholds,
claim-risk rules and the writer contract are all unchanged; the defect was fixed
where the Phase 3.2 report said it was — in claim↔passage candidate matching.

The old matcher accepted a two-content-word overlap. Across one topical corpus that
paired a prosumer-tariff claim with a market-price passage on `photovoltaique` +
`installation`, then compared their unrelated numbers and recorded a disagreement.
The new staged matcher requires the claim's semantic head, discriminative rather
than generic terms, compatible region and category, and **comparable numeric types**
before any figure is compared. €5 000 and 5 ans are no longer commensurable.

**Flanders was reached for the first time.** Phase 3.2 returned no Flemish authority
because a French tri-regional query cannot reach Dutch-language sources. A Dutch
regional query variant returned 10 pages from `vlaanderen.be`, and the four Belgian
jurisdictions are now all represented.

**Three HIGH-risk claims are supported, down from four** — and that is the correct
result. Phase 3.2's four each cited 8–18 "corroborating" official sources; under the
loose matcher most of those pairings were false, so the corroboration was inflated.
The three that survive cite one source each, honestly. §11 anticipated exactly this:
*"If it was accidentally supported under the old matcher, it SHOULD lose support."*

**The draft gate passed and the draft was blocked.** One draft was generated with
the configured model. Factual QA passed — and that pass turned out to be vacuous:
the page states no figure at all, so there was nothing to check. Meanwhile the
writer emitted an outbound link to a commercial competitor. Two QA checks were
added for those, and on a fresh generation the draft is correctly **FAILED**, not
`PENDING_APPROVAL`. Per §21 the reason is reported rather than the state forced.

**523 tests pass**, no credentials, no network.

---

## 2. Baseline

```
commit  c4578d404117cac725c824fccca44e57ea8fffba   clean tree, branch main
```

---

## 3. Root Cause

`passage_supports_claim` required two overlapping content words and nothing else:

```python
if len(claim_words & passage_words) < 2: return False, None
```

With 23 sources about Belgian solar, almost any two statements clear that bar —
`photovoltaique`, `installation`, `prix` appear on every page. The pairing was then
handed to numeric comparison, which found different figures and recorded a
disagreement. 163 of them.

Conflict classification was never at fault. Its input was.

---

## 4. Matcher Before

Two content words, then compare every number against every number. No notion of
which words carry topic, what the claim is *about*, what kind of quantity it
states, or which jurisdiction it applies to.

---

## 5. Matcher After

`app/services/claim_matching.py`, five stages, each with reason codes:

| Stage | Question | Refusal |
|---|---|---|
| D · region | does the passage's jurisdiction cover the claim's? | `REGION_MISMATCH` |
| E · category | may this kind of page establish this kind of claim? | `CATEGORY_MISMATCH` |
| B · head concept | is the claim's semantic head present? | `HEAD_CONCEPT_ABSENT` |
| A · topic | enough *discriminative* overlap? | `INSUFFICIENT_TOPIC_ALIGNMENT`, `GENERIC_OVERLAP_ONLY` |
| C · numeric type | are the quantities even comparable? | `NUMERIC_TYPE_MISMATCH` |

Region and category are checked first so a refusal names the strongest reason.
Numeric comparison happens **last**, only once the two statements are established
as being about the same proposition — which is the whole fix.

Three thresholds replace the single `>= 2`:

```
_MIN_TOPIC_OVERLAP        3    discriminative terms shared
_MIN_TOPIC_COVERAGE       0.5  of the claim's discriminative terms
_MIN_PREDICATE_COVERAGE   0.34 of the claim's substance beyond its head
```

The last one exists because a head match alone is too permissive: *"La batterie
réduit le temps de retour"* and *"La batterie augmente l'autoconsommation"* share
their subject and assert different things.

A short-claim path handles the opposite failure. *"Nos tarifs pour une installation
de 5 kWc sont de 4 400 €"* is almost entirely generic vocabulary in this vertical
and leaves two discriminative terms; demanding three would refuse a passage that
restates it verbatim. Such claims instead need **full** coverage of what little they
carry — proportionally stricter — and still face the numeric stage.

---

## 6. Concept Extraction

`Concepts` carries `topic_terms`, `generic_terms`, `head_phrase`, `phrases`,
`region`, `numerics`, `category`.

**Generic terms are per-vertical**, from `config/verticals/solar_be.yaml`:
`prix`, `solaire`, `photovoltaique`, `panneau`, `installation`, `energie`,
`belgique`, `euro`. They are context, not topic. `solaire` is generic here and
would be highly discriminative in a roofing vertical, so a global list would break
the second vertical the moment one exists — a test asserts the same word is
discriminative for `TEST_GENERIC`.

**Head phrases** come from configured `concept_phrases` (`tarif prosumer`,
`retour sur investissement`, `certificat vert`, `compteur bidirectionnel`, …). The
**earliest** phrase wins, not the longest: in *"Le tarif prosumer dépend de la
puissance installée"* the head is the subject, and longest-string would have picked
the object.

Tokens are stemmed with the same stemmer as the relevance gate, so a configured
generic term masks its own plural.

---

## 7. Numeric-Type Handling

Nine types: `MONEY`, `PERCENT`, `YEAR`, `DATE`, `DURATION`, `ENERGY`, `POWER`,
`RATE`, `COUNT`. Patterns are ordered and consumed positions are masked, so
`1,5 € par Wc` types as `RATE` and is not re-read as `MONEY`.

Only quantities of the **same type** are compared. A passage that is on-topic but
silent about that kind of quantity returns `agrees_numerically = None` — not a
disagreement. "€5 000" versus "5 ans" says nothing either way, and treating it as
contradiction is a large part of how 163 arose.

---

## 8. Region Handling

Stage D reuses the Phase 3.2 model unchanged: `BE`, `BE-WAL`, `BE-BRU`, `BE-VLG`,
asymmetric coverage. A Walloon passage cannot support a Brussels claim; a federal
passage can support either. The jurisdiction protections fixed in Phase 3.2 are
preserved and now also apply at candidate selection, before evidence is assembled.

---

## 9. Category Handling

A compatibility table, not equality. `SUBSIDY` accepts `ELIGIBILITY` and
`REGULATION`; `GRID_RULE` accepts `TARIFF` and `GRID_FEE`.

**`MARKET_PRICE` deliberately does not accept `VENDOR_PRICE`** — one installer's own
price is not evidence of a market average, and a market claim earns its figure
through corroboration across market-level statements instead. That is regression
test G.

`TARIFF` and `GRID_FEE` were added to `ClaimCategory` this phase. They were already
referenced in `solar_be.yaml` and were being silently discarded, and the live run
justifies them: CWaPE and ORES publish exactly those.

---

## 10. Matching Diagnostics

Ten reason codes, always populated, never hidden behind a score alone:

```
MATCHED_HEAD_CONCEPT · MATCHED_TOPIC_TERMS · NUMERIC_AGREES · NUMERIC_DISAGREES
INSUFFICIENT_TOPIC_ALIGNMENT · GENERIC_OVERLAP_ONLY · HEAD_CONCEPT_ABSENT
NUMERIC_TYPE_MISMATCH · REGION_MISMATCH · CATEGORY_MISMATCH
```

Each result also carries a human-readable `detail` naming the terms involved, and
the reasons are persisted on `EvidenceRef.note` so a stored package can be audited
long after the run.

---

## 11. Regression Tests

All eight named cases, plus supporting coverage — 31 tests in
`tests/test_claim_matching.py`:

| | Case | Result |
|---|---|---|
| A | prosumer-tariff claim vs market-price passage | NO SUPPORT, `HEAD_CONCEPT_ABSENT` |
| B | price claim vs Grand Prix racing page | NO SUPPORT |
| C | €5 000 vs 5 ans | NO SUPPORT, and **not** recorded as a disagreement |
| D | Brussels claim vs Wallonia passage | NO SUPPORT, `REGION_MISMATCH` |
| E | Brussels claim vs Brussels official passage | SUPPORT |
| F | Wallonia grid claim vs Wallonia grid passage | SUPPORT |
| G | market average vs one vendor's price | vendor SUPPORT, market NO SUPPORT |
| H | battery reduces payback vs battery raises self-consumption | NO SUPPORT |

Plus numeric typing (8 quantity forms), generic-token control, concept extraction,
diagnostics reaching the persisted note, and two recall-sanity tests confirming
genuine paraphrases still match.

---

## 12. Live Revalidation

Same query, same providers, no thresholds changed.

| | Phase 3.1 | Phase 3.2 | **Phase 3.3** |
|---|---:|---:|---:|
| Eligible sources | 10 | 23 | 23 |
| Official evidence | 0 | 13 | 13 |
| Atomic claims | 121 | 222 | 231 |
| Candidate support pairs | — | (unmeasured, inflated) | **104** |
| Eligible support pairs | — | — | **104** |
| SUPPORTED | 54 | 109 | 54 |
| PARTIALLY_SUPPORTED | 22 | 10 | 21 |
| UNSUPPORTED | 22 | 59 | 156 |
| CONFLICTING | 23 | 44 | **0** |
| **TRUE_CONFLICT** | **11** | **163** | **0** |
| REGIONAL / TIME / SCOPE differences | — | 5 / 14 / 9 | 0 |
| HIGH-risk total | 18 | 64 | 56 |
| HIGH-risk supported | 0 | 4 | **3** |

Regions reached by the authoritative pass:

```
Phase 3.2   BE-WAL · BE-BRU · BE
Phase 3.3   BE-WAL · BE-BRU · BE · BE-VLG      ← Flanders, for the first time
```

`SUPPORTED` falling from 109 to 54 is the precision cost, and §5 explicitly accepts
it: *"It is acceptable to miss some valid support candidates initially. It is NOT
acceptable to manufacture false conflicts."* Of the 54, **35 are backed by an
OFFICIAL source** — a far better ratio than Phase 3.2's 109.

**An honest caveat about the zero.** Candidate pairs equal eligible pairs (104 =
104), meaning the live corpus produced no numeric disagreements of any kind. So
conflict detection is *unexercised* on live data rather than *validated* by it. It
remains intact in code and is covered by unit test
(`test_same_type_different_value_disagrees`), but this run cannot demonstrate it
fires when it should.

---

## 13. The Four Previously Resolved HIGH-risk Claims

| Phase 3.2 claim | Sources then | Status now |
|---|---:|---|
| SUBSIDY / BE-BRU — regional premium | 18 | **lost** |
| SUBSIDY / BE-BRU — green certificates | 8 | **lost** |
| GRID_RULE / BE-WAL — prosumer tariff | 14 | **lost** |
| GRID_RULE / BE-BRU — inverter threshold | 11 | **lost** |

All four lost support, and three new claims gained it:

```
SUBSIDY / BE-WAL   "certains travaux ne faisant pas l'objet d'une prime…"   1 source
SUBSIDY / BE-WAL   "Pour toutes les primes, il y a un montant de base…"     1 source
REGULATION / BE    (a CREG page title)                                      1 source
```

**This is the correct outcome, not a regression.** Phase 3.2's counts of 8–18
corroborating sources were the loose matcher pairing one claim with every official
page that shared two words. Under typed, head-anchored matching the honest count is
one. §11 says plainly that a claim accidentally supported under the old matcher
should lose support, and these did.

The third is a known defect surfacing: *"CREG : Commission de Régulation de
l'Électricité et du Gaz"* is a page title, not a proposition. That is the Phase 3.1
"page furniture becomes a claim" limitation, still open.

---

## 14. Flemish Research Result

Phase 3.2's tri-regional French query returned no Flemish authority, so `BE-VLG`
claims had no official evidence and never could — `energiesparen.be` and
`vlaanderen.be` publish in Dutch.

A regional query-variant mechanism was added to the planner (`SUBSIDY_VLG`), and
`solar_be.yaml` now carries:

```
SUBSIDY_VLG: "premie zonnepanelen Vlaanderen voorwaarden officieel"
```

Result: **10 pages from `vlaanderen.be`, all scoped `BE-VLG`.** No Flemish rule was
generalised — the authority's own jurisdiction is definitive (Phase 3.2 fix).

The variant initially displaced `GRID_RULE` from the four-query budget, which
silently removed CWaPE and ORES from the evidence set. `max_queries` was raised from
4 to 5 (the absolute ceiling) so six unresolved categories plus one regional variant
fit. That is a capacity correction, not a metric tune — without it the comparison
against Phase 3.2 would not have been like-for-like.

---

## 15. DataForSEO State

**`CONFIGURED_BUT_ACCOUNT_BLOCKED`** — one probe, `403 / 40104`, cost $0. Not
retried, and nothing in this phase depended on it.

---

## 16. Claim Ledger Quality

```
231 atomic claims
 54 SUPPORTED      (35 backed by an OFFICIAL source)
 21 PARTIALLY_SUPPORTED
156 UNSUPPORTED
  0 CONFLICTING

writer-eligible   54
forbidden topics  SUBSIDY · TAX · GRID_RULE · REGULATION · ENERGY_PRICE · ROI
```

Structurally much cleaner than Phase 3.2: no conflict noise, and the supported set
is majority official-backed. The remaining weakness is that some claims are page
titles and headings rather than propositions.

---

## 17. Draft Gate

All five conditions in §17 assessed:

1. matching precision materially improved — **yes**, 163 → 0
2. no systemic false-conflict issue — **yes**, none remain
3. enough writer-eligible claims — **yes**, 54 with 12 reaching the brief
4. unresolved HIGH-risk excluded from the writer contract — **yes**, all six
   categories forbidden
5. OpenAI configured — **yes**, `gpt-4o-mini` unchanged

Gate **passed**. One draft generated.

---

## 18. Draft Result

```
model            gpt-4o-mini-2024-07-18   (unchanged, as §17 requires)
tokens           2 485 in / 527 out
latency          5.5 s
content type     LANDING_PAGE  (from the brief, not forced)
title            "Prix des Panneaux Solaires en Belgique : Guide Complet"
body             306 words
```

The draft is coherent, on-topic, structured, and invents nothing. It is also **not
useful**, for two reasons the QA layers initially missed.

---

## 19. Factual QA

```
status PASSED · score 100 · blocking 0
ledger 231 claims — 54 SUPPORTED · 21 PARTIAL · 156 UNSUPPORTED · 0 CONFLICTING
```

**The pass is vacuous.** Factual QA extracts sentences carrying a quantity and binds
each to the ledger. This draft contains **zero such sentences** — a page titled
*"Prix des panneaux solaires en Belgique"* that states no price. Nothing was
checked, so nothing failed.

That is worth stating precisely: passing factual QA means *"asserted nothing
false"*, which is not the same as *"answered the question"*. The distinction had no
representation before this run.

Added: `NO_QUANTIFIED_ANSWER`, advisory. A page can be honest and still not answer
its query — that is a usefulness problem for a reviewer, not grounds to refuse a
draft, so it does not block.

---

## 20. SEO QA

First generation: `PASSED`, score 100, zero findings.

After the additions, on a fresh generation:

```
status FAILED · score 70 · blocking 1

[BLOCK] EXTERNAL_LINK_IN_BODY
        The draft emits 1 outbound link(s). Sources belong in the evidence
        ledger, not in the copy.
[note ] NO_QUANTIFIED_ANSWER
        Brief targets COMMERCIAL intent but the body states no figure at all.
```

The first generation had emitted a markdown link to a **commercial competitor's**
page. Nothing caught it: the writer contract forbids reproducing competitor content
but said nothing about linking to it, and a published page that sends its reader to
a competitor is worse than one that quotes them. `EXTERNAL_LINK_IN_BODY` blocks.

Neither addition weakens anything — both make QA stricter, and four tests cover
them.

---

## 21. Provider Usage / Cost

```
tavily      6 requests   (1 general · 5 domain-restricted)   60 results
openai      2 draft generations + 2 brief enrichments        ~6 000 tokens
dataforseo  1 probe, HTTP 403, cost 0.00

total_cost_usd  null — Tavily bills in credits, OpenAI has no price table
```

Unknown is not rendered as free. The per-job ceiling was not approached; no broad
crawling and no unbounded loops.

---

## 22. Known Limitations

1. **Conflict detection is unexercised on live data.** Zero disagreements arose, so
   this run shows only that false ones are gone.
2. **Recall cost is real**: SUPPORTED fell 109 → 54. Explicitly accepted by §5, but
   some genuine support is being missed — paraphrases using different vocabulary
   will not match.
3. **Page titles still become claims.** One of the three resolved HIGH-risk claims
   is a CREG page title.
4. **Corroboration collapsed to one source per HIGH-risk claim.** Honest, but the
   `min_corroborating_sources` policy now rarely binds because multi-source
   agreement is rare under strict matching.
5. **Head-phrase extraction depends on configured vocabulary.** A claim whose head
   is not in `concept_phrases` falls back to a bigram, which is weaker.
6. **The draft states no price.** Whether that is the writer, the brief, or the fact
   that no price claim is SUPPORTED is not yet established.
7. **`NO_QUANTIFIED_ANSWER` is advisory**, so a vacuous page could still reach a
   human if it carried no outbound link.
8. **DataForSEO still blocked**; no SERP evidence has ever entered a package.

---

## 23. Phase 4 Readiness

**Closer, but not ready.** The evidence machinery is sound and the ledger is clean.
What the live run showed is that a clean ledger is necessary and not sufficient: the
first real draft passed factual QA by asserting nothing checkable, and linked to a
competitor.

The gap is now on the **generation** side, not the evidence side.

---

## 24. Exact Recommended Next Action

1. **Establish why the draft states no price.** Check whether any `MARKET_PRICE`
   claim is SUPPORTED and reaching `required_facts`; if none is, the brief is
   correctly withholding and the answer is more evidence, not a better prompt.
2. **Strengthen the writer contract against outbound links** in the prompt itself,
   not only in QA. QA blocking is the backstop; the writer should not be producing
   them.
3. **Re-generate and iterate once** — the loop of generate → read → adjust the
   contract has now run exactly once, and one iteration is not a validation.
4. **Recover recall selectively.** Embeddings over `pgvector` would match
   paraphrases the lexical matcher misses, without loosening the typed-numeric or
   region rules that produced the precision gain.
5. **Verify the DataForSEO account** — still an owner action, still gating all SERP
   evidence.

Do not lower `_MIN_TOPIC_OVERLAP`, `_MIN_PREDICATE_COVERAGE` or the numeric-type
rule to recover the 109 supported claims. That number was inflated, and the 163
false conflicts were its cost.
