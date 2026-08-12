# PROSPECT 360 SEO LEAD FACTORY — Phase 3 Implementation Report

**Date:** 2026-08-12
**Workspace:** `/opt/seolead`, branch `main`
**Phase 2 commit:** `4b9230f6a83ea09740a2484b6551adb4106b57e4`
**Outcome:** implementation complete and tested. Live validation run 2026-08-12.
**STOP B — PARTIAL.** Two of three providers verified live; DataForSEO is blocked
by an unverified account, and the live run exposed a genuine evidence-model flaw.

---

## 1. Executive Summary

Phase 3 replaces the research layer, adds the search-intelligence layer, and fixes
the defect Phase 2's live run exposed. Everything is built, migrated and tested,
and the live validation of 2026-08-12 has now been run.

**Live outcome: PARTIAL.** Two of three providers are verified against their real
APIs. The third, DataForSEO, is blocked by an account state — and the run surfaced
an evidence-model flaw that no amount of mock testing could have found.

**Tavily and OpenAI: verified.** Tavily returned 10 Belgian sources in 3.3 s,
matching the adapter field for field, and confirming the prediction in this
report's earlier draft that **no source would carry a publication date** (0 of 10).
OpenAI's contract matches and the brief generated live.

**DataForSEO: blocked, credentials valid.** HTTP 403 with `status_code 40104`,
"Please verify your account before using the API." Bad credentials return 401;
this is a business state the owner clears in the DataForSEO panel in a few minutes.
Cost incurred: $0.00. Without a SERP there is no competitor view, no PAA and no gap
analysis, so the pipeline stopped — by design, and that design was not weakened to
manufacture a green result.

**The relevance gate passed its real test.** Ten live sources, ten judged RELEVANT,
zero rejected, mean relevance 0.965 — every one genuinely about Belgian solar
pricing. After the racing-game incident the worry was over-rejection; on live data
it does not over-reject. The Phase 2 regression still holds in the suite.

**Source quality and claim risk behaved correctly, and told us something useful:**
no Belgian regulator or public authority appears in the top web results
(SPECIALIST 5, COMMERCIAL 5, `has_official: false`). All nine HIGH-risk claims were
therefore refused — the system declining to let a commercial installer page stand
up a claim about a Belgian subsidy, which is exactly the intended behaviour.

**The finding that matters most is an evidence-model flaw.** `supported` requires
`OBSERVED`, and Tavily's general search never returns dates, so every web fact is
`ESTIMATED`. **The web-research path therefore yields zero supported facts for any
query, ever.** Underneath it sits a deeper modelling error: Tavily's `content` is a
~2 000-character page excerpt including navigation and cookie banners, and the
system treats one excerpt as one "claim" — which is why 9 of 10 were classified
HIGH risk (the classifier is scanning documents, not claims).

Neither was "fixed" here. Both are evidence-model design decisions, the mandate was
to validate rather than redesign, and fixing the date rule without fixing the
excerpt modelling would treat the symptom. **This is the one item needing an owner
decision** (§20b, §28).

Three code corrections were made, each justified by something the live run exposed,
none touching gate or QA semantics: DataForSEO's structured error was being
discarded; the test suite was silently reading the operator's real credentials from
`.env`; and CLI logs shared stdout with the JSON result, so `seolead … | jq` failed.

**345 tests pass with no credentials and no network.** Nothing in production was
touched.

---

## 2. Phase 2 Baseline

Phase 2 ended PARTIAL with one measured finding: three live probes showed
Last30Days returns no SERP structure, that its `grounding` (web) source is
non-functional without a paid key, and that for `prix panneaux solaires Belgique`
it returned exactly one irrelevant fact.

Phase 3 acts on that: Last30Days is repositioned as a community/discussion
provider, off by default, and DataForSEO + Tavily take the primary path.

---

## 3. Scope Delivered

| Mission section | Delivered |
|---|---|
| §2–3 provider categories and capability model | ✅ `ProviderCapability`, `plan_providers()` |
| §4 DataForSEO provider | ✅ contract verified against official docs |
| §5 search location | ✅ `SearchContext`, 5 markets, nothing hard-coded |
| §6 Tavily provider | ✅ dates never invented, score ≠ confidence |
| §7 Last30Days repositioning | ✅ policy-gated, existing provider and tests intact |
| §8–10 relevance gate | ✅ two levels, hard rejection, regression test |
| §11 source quality | ✅ 6 classes, ranking excluded structurally |
| §12 claim risk | ✅ LOW/MEDIUM/HIGH with evidence bars |
| §13 ResearchPackage V2 | ✅ eligible + rejected + provenance, V1 compatible |
| §14 SERP competitor analysis | ✅ derived structure, no competitor copy |
| §15 PAA / related searches | ✅ persisted, feed the brief |
| §16 keyword metrics | ✅ with provenance; absent ⇒ UNKNOWN |
| §17 Opportunity Score v1 | ✅ components, confidence, missing_inputs |
| §18 OpenAI live provider | ✅ configurable model, no hard-coding |
| §19–20 generation contract | ✅ eligible evidence only, quality over length |
| §21 Factual QA V2 | ✅ 4 support statuses; HIGH+UNSUPPORTED blocks |
| §22 SEO QA V2 | ✅ layered, actionable findings |
| §23 approval unchanged | ✅ still mandatory, still PENDING |
| §24 cost control | ✅ per-job ceilings, unknown ≠ free |
| §25 cache / freshness | ✅ per-kind TTL, forced refresh |
| §26 API / CLI + rejection inspection | ✅ `package rejected`, `/rejected` |
| §27 credential gate | ✅ reached, then cleared by the owner |
| §28 live validation | ⚠️ **PARTIAL** — Tavily + OpenAI verified; DataForSEO account unverified |
| §29 regression tests | ✅ all five, plus the stemmer |
| §30 Prospect 360 preparation | ✅ documentation only, 4 new attribution ids |
| §32 tests | ✅ 345, no credentials |
| §34 documentation | ✅ all eleven documents |

**Not delivered, by instruction:** website, domain, simulator,
Search Console, GA4, Ads, Prospect 360 implementation, n8n deployment.

---

## 4. Architecture

```
  operator ─▶ CLI `seolead research run`  /  POST /internal/v1/research-jobs
                              │
┌─────────────────────────────▼──────────────────────────────────────────────┐
│ PROVIDER POLICY (deterministic)   plan_providers(query, intent, profile)    │
│   SERP: always · WEB: always · COMMUNITY: per-vertical, off for SOLAR_BE    │
└─────────────┬──────────────────────────┬───────────────────────────────────┘
   ┌──────────▼─────────┐    ┌───────────▼──────────┐   ┌───────────────────┐
   │ DataForSEO         │    │ Tavily               │   │ Last30Days        │
   │ SERP·KEYWORD_METRIC│    │ WEB_RESEARCH·EXTRACT │   │ RECENT_DISCUSSION │
   │ cost: reported     │    │ cost: unknown        │   │ (policy-gated)    │
   └──────────┬─────────┘    └───────────┬──────────┘   └─────────┬─────────┘
              │              ┌───────────▼────────────────────────▼───────┐
              │              │ RELEVANCE GATE                             │
              │              │  A: topic vs modifier vs market tokens     │
              │              │     zero topic match ⇒ IRRELEVANT (hard)   │
              │              │  B: semantic, LOW_RELEVANCE only, never    │
              │              │     overturns a hard rejection             │
              │              │  rejected sources KEPT with their reason   │
              │              └───────────┬────────────────────────────────┘
    ┌─────────▼──────────┐   ┌───────────▼───────────────────────────────┐
    │ SERP ANALYSIS      │   │ SOURCE QUALITY  ×  CLAIM RISK             │
    │ shapes · gap · PAA │   │ OFFICIAL…COMMUNITY   LOW/MEDIUM/HIGH      │
    │ no competitor copy │   │ HIGH-risk needs INSTITUTIONAL or better   │
    └─────────┬──────────┘   └───────────┬───────────────────────────────┘
              └──────────┬───────────────┘
                         ▼
              ResearchPackage V2   eligible + rejected + provenance
                         ▼
              Opportunity Score v1  unknown ≠ zero; confidence = measured weight
                         ▼
              ContentBrief  →  OpenAI draft  →  Factual QA V2  →  SEO QA V2
                                                (HIGH+UNSUPPORTED blocks)
                         ▼
                  HUMAN APPROVAL (PENDING)

   ╔═══════════════════════════════════════════════════════════════════════╗
   ║ UNTOUCHED: Prospect 360 · TechFormaNord · ChainPilot ·                ║
   ║            Hermes gateway · n8n · Traefik                             ║
   ╚═══════════════════════════════════════════════════════════════════════╝
```

Determinism now covers more ground than in Phase 2: relevance Stage A, package
assembly, source quality, claim risk, factual QA and SEO QA are all code. The model
contributes synthesis, one narrow classification, and advisory review that never
blocks.

---

## 5. DataForSEO Integration

Contract read from the official v3 documentation during implementation. Nothing
guessed.

```
POST https://api.dataforseo.com/v3/serp/google/organic/live/advanced
POST https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live
Authorization: Basic base64(login:password)
body: JSON ARRAY, exactly one task per live call
results: tasks[].result[].items[]
```

**Two-level status.** DataForSEO returns `status_code` at the envelope *and* per
task, and a 20000 envelope can carry a failed task. Trusting the envelope alone
produces a confidently empty SERP — a result claiming Google shows nothing when the
request was malformed. Both are checked; a failed task raises.

**Unknown SERP features are recorded, not dropped.** Google adds features without
notice; an unmapped type becomes `OTHER` with its raw name kept in
`provider_metadata.dataforseo.unmapped_item_types`.

Normalised: organic results (rank_group, rank_absolute, domain, url, title,
description, breadcrumb), People Also Ask, related searches, feature inventory,
provider cost, retrieval timestamp.

Keyword metrics: `search_volume`, `cpc`, `competition`, `competition_index`, each
stored with provider, retrieval time and a CHECK-constrained `observability`. An
absent metric is omitted and scores as UNKNOWN, never zero.

Errors: 401 and 402 are not retryable (an operator action, not a transient fault);
429 is. The 401 message is asserted by test never to echo the credential.

---

## 6. Tavily Integration

```
POST https://api.tavily.com/search
Authorization: Bearer tvly-...
```

`include_answer: false` on purpose — we want sources, not a synthesised answer. An
answer would be a second model's summary presented as evidence.

**Two contract facts drive the mapping, and both are load-bearing:**

`published_date` is **not** a standard field; it appears for `topic="news"`. A
general search returns undated sources. The adapter leaves `published_at` as `None`
rather than inventing one, and an undated source becomes `ESTIMATED` rather than
`OBSERVED`. **Expect most Phase 3 web evidence to be ESTIMATED** — which is honest,
and which means HIGH-risk claims will mostly need an official source rather than a
general web result.

`score` is retrieval relevance, not factual confidence. It is carried in metadata
and used by the gate; `confidence` stays `None`. Conflating the two is how a
well-matched wrong page becomes a supported fact.

Results with no URL are dropped: a source we cannot cite is not usable evidence.
An empty result set from a healthy call is a **clean empty** (`no-results`), not a
failure.

---

## 7. Last30Days Repositioning

Kept, with its provider and all Phase 2 tests intact. Reclassified as
`RECENT_DISCUSSION` / `COMMUNITY_SIGNAL` and made opt-in per vertical.

`SOLAR_BE` sets `community_research_enabled: false`, with the reasoning in the YAML:
a Belgian homeowner researching installation costs is not on Hacker News. Even in
an enabled vertical it is skipped for COMMERCIAL and TRANSACTIONAL intent, because
discussion rarely carries purchase-stage facts.

An operator can override per job with `--community` / `--no-community`, and the
decision and its reason appear in `provider_plan`.

---

## 8. Provider Capability Routing

```
DataForSEO  SERP · KEYWORD_METRICS
Tavily      WEB_RESEARCH · CONTENT_EXTRACTION
Last30Days  RECENT_DISCUSSION · COMMUNITY_SIGNAL
```

Downstream code asks for a capability, never a provider by name. `plan_providers()`
is deterministic and returns a reason per provider, so **an LLM cannot switch on a
paid provider**.

The test vertical deliberately enables community research where SOLAR_BE disables
it, which is what proves the policy is read from configuration rather than
hard-coded.

---

## 9. RelevanceGate

Full reasoning in `docs/RELEVANCE_GATE.md`.

```
prix panneaux solaires Belgique
 │      └── topic ──┘      └─ market name, no topical signal
 └─ commercial modifier
```

**Hard rule:** zero topic-token overlap ⇒ IRRELEVANT, regardless of modifiers.

| Status | Eligible | Meaning |
|---|---|---|
| `RELEVANT` | **yes** | covers enough of the query's topic |
| `LOW_RELEVANCE` | no | partial match below threshold |
| `IRRELEVANT` | no | no topical overlap, or below the floor |
| `UNKNOWN` | no | query has no topic tokens to judge against |

`LOW_RELEVANCE` is deliberately not eligible — a weak match is exactly the kind of
source that reads plausible in a draft and cannot be defended.

Two levels: source relevance, then claim relevance. A claim can never outrank its
source.

Stage B (semantic) runs only for LOW_RELEVANCE and never overturns a hard
rejection. A model that disagrees with "shares no topic with the query" is wrong,
and asking invites it to be.

**Rejections are kept** — on the `research_source` row and in
`research_package.rejected_evidence` — with status, score, reason and signals.
Phase 2 could not answer "why was this dropped", which is the first question anyone
asks when a gate misbehaves.

Thresholds are configurable and **openly arbitrary**: chosen so the Phase 2 failure
is rejected and obvious cases pass, not validated against a labelled corpus. The
docs and `.env.example` both say so.

---

## 10. Source Quality

`OFFICIAL` › `INSTITUTIONAL` › `SPECIALIST` › `COMMERCIAL` › `COMMUNITY` ›
`UNKNOWN`, classified from the domain, with a per-vertical `authoritative_domains`
override (11 Belgian regulators, grid operators and public authorities for
SOLAR_BE).

Two rules the mission is explicit about, both structural:

- **Ranking is not authority.** `classify_domain` takes only `url` and
  `source_type`; it has no way to learn a SERP position. A #1 commercial result
  still classifies below a #10 official one, and a test asserts it.
- **Commercial is not disqualifying.** An installer's pricing page is often the
  best source on installer pricing. It is classified so QA can reason about it, not
  rejected.

---

## 11. Claim Risk

| Risk | Requires | Examples |
|---|---|---|
| `HIGH` | OFFICIAL or INSTITUTIONAL | subsidy, tax rate, legal obligation, guaranteed return |
| `MEDIUM` | SPECIALIST or better | any quantified claim |
| `LOW` | any relevant source | unquantified explanation |

HIGH categories come from the vertical's `restricted_claims` plus a cross-vertical
list of legal, fiscal and guarantee vocabulary — so this carries no solar-specific
knowledge, and the AI Training vertical's funded-eligibility rules get the same
treatment from its own profile.

---

## 12. ResearchPackage V2

`supported` now requires four things, where V1 required one:

```
observability == OBSERVED
  AND claim relevance is eligible
  AND source quality clears the claim's risk bar
  AND the source reference resolves inside the package
```

Carries: eligible evidence, **rejected evidence with reasons**, competitor page
structure, SERP observations, content gap, PAA, related searches, keyword metrics
with provenance, source-quality and claim-risk summaries, unresolved questions,
per-provider provenance.

Traceability is `claim → evidence → source → provider`. A dangling `source_ref`
makes a fact unsupported.

`package_version` distinguishes V1 from V2; `version` remains the per-keyword
revision. Conflating them would make "which builder produced this" unanswerable.

---

## 13. SERP Intelligence

Deterministic first-pass analysis of the organic results: page shapes (calculator,
comparison, guide, price-focused, listing), Belgian-domain presence, domain
concentration, dominant framing, SERP features, and a **content gap** listing the
shapes the SERP is *not* serving.

**No competitor copy is reproduced and the writer is never told to imitate a
page.** Titles are used as signals to derive structure; the brief receives
observations and questions, not competitor text.

PAA and related searches are persisted and feed the brief's key questions and SEO
QA's coverage check. They do **not** generate one page per question — that is
programmatic SEO spam, which the mission forbids.

---

## 14. Opportunity Score V1

| Component | Weight |
|---|---|
| commercial intent | 0.25 |
| business relevance | 0.20 |
| conversion potential | 0.15 |
| content gap | 0.15 |
| SERP opportunity | 0.10 |
| search demand | 0.10 |
| competition | 0.05 |

Three rules keep it honest: **unknown never becomes zero** (dropped from the
weighted mean and named in `missing_inputs`); components are stored separately with
a rationale each; and `confidence` is the share of weight actually measured, so a
high score with low confidence reads as "promising, poorly evidenced".

`overall_score` is `null` when nothing could be measured — not 0. The output
carries an explicit `interpretation` string stating it is a heuristic, not a
prediction.

A test pins the mission's central claim: a 300-search transactional keyword
outscores a 10 000-search informational one.

---

## 15. OpenAI Integration

Uses the Phase 2 `LLMProvider` abstraction unchanged. Model is configuration
(`SEOLEAD_LLM_MODEL`), never hard-coded. Key is runtime-only, sent as a Bearer
header, asserted by test never to appear in a URL or body.

The writer receives vertical configuration, the brief, **eligible** evidence,
unresolved facts, claim restrictions and the CTA objective. It does not receive
rejected evidence or competitor text.

Usage (`input_tokens`, `output_tokens`, `total_tokens`, `latency_ms`) is persisted
per draft. `cost_cents` stays `None` until a price table exists — unpriced and free
are different facts. No hidden chain-of-thought is stored.

---

## 16. Factual QA V2

Extracts the draft's factual sentences and binds each to eligible evidence:

| Status | Meaning |
|---|---|
| `SUPPORTED` | bound to evidence clearing its risk bar |
| `PARTIALLY_SUPPORTED` | bound, but the evidence is weaker than the risk demands |
| `UNSUPPORTED` | nothing in the evidence set backs it |
| `CONFLICTING` | evidence exists on the topic and states a different figure |

**Only HIGH-risk and not SUPPORTED blocks.** A wrong sentence about panel
orientation is a quality problem; a wrong sentence about a subsidy is a legal one,
and only the second should stop a draft reaching a human. Everything else is
reported for the reviewer.

`CONFLICTING` is distinguished from `UNSUPPORTED` because "evidence exists and
disagrees" is a stronger signal than "nothing found".

The full per-claim ledger is persisted on the QA review.

---

## 17. SEO QA V2

Layered on the Phase 2 checks rather than folded into them — altering their
behaviour would have meant editing the tests that pin them, which is how a
regression suite quietly stops being one.

Adds: PAA coverage (the clearest available statement of what searchers also want to
know), intent alignment (a COMMERCIAL brief whose body never mentions cost blocks),
title topicality, content-type fit, near-verbatim repetition, and the SERP content
gap as an opportunity note.

Findings are actionable — they name the uncovered questions and the missing shapes,
not just a score.

---

## 18. Credential State

At the live run, all three were configured by the owner:

```
DATAFORSEO      CONFIGURED      (valid — authenticated, account unverified)
TAVILY          CONFIGURED      (verified live)
OPENAI          CONFIGURED      (verified live)
INTERNAL_API    CONFIGURED
ready_for_live_test: true
```

Reported by `seolead credentials` and `GET /internal/v1/credentials`. **Statuses
only** — no value, no prefix, no length.

A test-isolation defect was found here and fixed: `Settings` reads `.env` by
default, so once real keys landed on the box the `settings_no_llm` fixture stopped
meaning "nothing configured", and tests asserting unconfigured behaviour began
passing or failing by machine state rather than by code. All fixtures now pass
`_env_file=None`, with `TestSuiteIsHermetic` pinning it.

`PROVIDER_NOT_CONFIGURED` remains a distinct code from `RESEARCH_FAILED`: nothing
went wrong, a key is absent, and the fix is an operator action rather than a retry.

Procedure: `docs/runbooks/PROVIDER_CREDENTIALS.md`.

---

## 19. Test Results

**345 passed, 0 failed, 0 skipped**, ~11 s. No network, no credentials.

Nine tests were added during live validation: 5 for DataForSEO error
surfacing, 3 for suite hermeticity, 1 for CLI stream separation.

| Suite | Tests |
|---|---:|
| `test_phase3_services.py` | 63 |
| `test_search_providers.py` | 42 |
| `test_security.py` | 38 |
| `test_persistence.py` | 25 |
| `test_qa.py` | 24 |
| `test_normalizer.py` | 21 |
| `test_approval.py` | 19 |
| `test_pipeline.py` | 19 |
| `test_relevance.py` | 19 |
| `test_intent.py` | 17 |
| `test_pipeline_v2.py` | 16 |
| `test_regressions.py` | 14 |
| `test_llm_provider.py` | 12 |
| `test_multi_vertical.py` | 8 |
| `test_package_builder.py` | 8 |

All Phase 2 tests preserved and passing.

### Named regressions (§29)

`tests/test_regressions.py` names each incident rather than a module, so a change
that reintroduces one fails against a test whose name says what broke:

- **Racing game** — irrelevant source rejected, never eligible, rejection explained
- **Belgium intent** — market name does not force LOCAL; a real locality still does
- **Restricted solar claims** — unverified subsidy figure blocked; every restricted
  topic reaches the brief as cautionary
- **Source accounting** — `partial` with zero items is not counted as coverage
- **Secret redaction** — JSON-shaped secret fields stay redacted
- **Stemmer** (new) — `panneaux → panneau`, `chevaux → cheval`

### Three further bugs found during live validation

1. **DataForSEO's structured error was discarded.** HTTP 403 carrying
   `status_code 40104` and the exact remedy was reported as "returned 403". Fixed;
   5 regression tests using the real body.
2. **The test suite read the operator's real credentials.** `Settings` reads `.env`
   by default, so `settings_no_llm` silently stopped meaning "nothing configured"
   the moment keys landed on the box. Fixed with `_env_file=None`; 3 regression
   tests.
3. **CLI logs shared stdout with the JSON result**, so `seolead … | jq` failed on
   "Extra data" — defeating the point of a machine-readable CLI. Logs moved to
   stderr; 1 regression test.

### Three real bugs found while building

1. **The stemmer broke the gate.** `panneaux` stemmed to `panneal` because the
   French `-aux → -al` rule (cheval/chevaux) fired before the `-eaux → -eau` case
   (panneau/panneaux). `panneau` is a topic token for the pilot query, so a
   one-line bug silently disabled the relevance gate's central check.
2. **The cost ledger depended on adapters remembering.** Adapters record their own
   usage because only they know the provider's reported cost — which made the
   ledger silently incomplete for any adapter that forgot, invisible exactly where
   money is involved. The orchestrator now backstops it.
3. **A brittle security test.** `.env.example` was validated against a hand-written
   allowlist of every legal value, so it failed for the wrong reason on each new
   setting. Rewritten to assert the *shape* of a credential instead.

A fourth, smaller: a domain-only match was hard-rejected because scoring ignored
the domain. Fixed with a domain bonus capped below the RELEVANT threshold — a
matching domain says what the *site* is about, not the page.

---

## 20. Live Solar Test

**Run:** 2026-08-12, `vertical SOLAR_BE`, `query "prix panneaux solaires Belgique"`,
`market BE`, `language fr`. Provider policy as implemented — no forcing, no
threshold changes, no QA weakening.

**Result: PARTIAL.** The pipeline stopped at the SERP stage. Two of the three
providers were verified live and behave exactly as their adapters expect; the third
is blocked by an account state only the owner can clear. Beyond that, the live data
exposed a real flaw in the evidence model that no test could have caught.

### Provider plan (as selected, not forced)

```
selected: ["dataforseo", "tavily"]
last30days: skipped — "vertical SOLAR_BE does not enable community research
            (its audience is not the technical community this provider indexes)"
```

The policy behaved correctly and unprompted.

### 1. DataForSEO — BLOCKED, credentials valid

```
POST /v3/serp/google/organic/live/advanced  →  HTTP 403
{"status_code": 40104,
 "status_message": "Please verify your account before using the API.
                    You can complete verification in the user panel:
                    https://app.dataforseo.com/ ."}
```

**This is not a credential failure.** Bad credentials return 401; DataForSEO
authenticated the request and returned a business state. The account needs
verification in the DataForSEO panel — an operator action of a few minutes.

Cost incurred: **$0.00** (the response reports `cost: 0`).

Consequence: no SERP snapshot, so items 3 and 4 of the verification list (organic
results, PAA / related searches) are **not verified**, and the pipeline stopped by
design. SERP is the backbone — without it there is no competitor view, no PAA and
no gap analysis — and that stop was not weakened to produce a green result.

### 2. Belgium / French search context — verified as far as the request

The request carried `location_code 2056`, `language_code "fr"`, `device "desktop"`,
`se_domain "google.be"`. DataForSEO accepted the shape and rejected on account
state, not on parameters. Full verification awaits a successful call.

### 5. Tavily — VERIFIED, contract matches exactly

```
10 sources returned, status SUCCEEDED, 3 344 ms
result fields: title, url, content, score, id, raw_content
```

Belgian `.be` domains dominate, so the `country: belgium` boost works. Two extra
top-level fields appeared (`follow_up_questions`, `images`) which the adapter
ignores as designed.

**`published_date` was absent on 10 of 10 sources** — exactly as the Phase 3 report
predicted and as `docs/providers/TAVILY.md` documents. All 10 facts were therefore
`ESTIMATED`, none `OBSERVED`.

### 6. Relevance gate — VERIFIED, and it did not over-reject

```
returned = 10    relevant = 10    rejected = 0    mean relevance = 0.965
```

Nine sources scored 1.00 and one 0.65. Every one is genuinely about Belgian solar
pricing, so **zero false rejections on live data** — the gate is not too strict.
The racing-game regression continues to pass in the suite.

One observation worth recording: a source titled `"| Blog Webflow"` scored 1.00 on
the strength of its 2 KB body. That is not a gate failure, but it is a symptom of
finding **B** below.

### 7. Source quality — VERIFIED

```
SPECIALIST 5 · COMMERCIAL 5 · has_official: false · has_institutional: false
```

Correct classification, and the honest result for this SERP: **no Belgian regulator
or public-authority source appeared in the top web results.** That matters directly
for item 10.

### 8. Claim risk — VERIFIED, and it revealed finding B

```
HIGH 9 · MEDIUM 1 · high_risk_unsupported 9
```

### 9. ResearchPackage V2 provenance — VERIFIED

`package_version: 2`, provider list `["tavily"]`, per-fact `source_ref`,
`source_quality`, `claim_risk`, `evidence_sufficient` and `supported` all populated;
`serp` provenance correctly `null`.

### 10. Unsupported / high-risk Solar claims — VERIFIED as blocked

All 9 HIGH-risk claims were `evidence_sufficient: false` and `supported: false`,
because HIGH risk requires an OFFICIAL or INSTITUTIONAL source and the best
available was SPECIALIST. **This is the system working correctly**: it refuses to
let a commercial installer page stand up a claim about a Belgian subsidy.

### 11–14. OpenAI, factual QA, SEO QA, approval — NOT REACHED

The brief was generated (live OpenAI call succeeded, `generated_by: hybrid`,
content type `LANDING_PAGE`, intent `COMMERCIAL`, CTA `quote_request`, 16
cautionary claims) but carried **0 required facts**, so drafting stopped.

OpenAI's contract was verified separately with a minimal probe: HTTP 200,
`choices[0].message.content`, `usage.{prompt,completion,total}_tokens`, model
`gpt-4o-mini-2024-07-18`. The adapter matches.

Final approval state: **none — no draft exists.** `PENDING_APPROVAL` was not
reached and was not forced.

---

## 20b. Contract discrepancies discovered

### A. DataForSEO error detail was discarded — FIXED

The 403 carried `status_code 40104` and a message naming the exact remedy. The
handler reported only `"DataForSEO returned 403"`, throwing away the one piece of
information the operator needed. An HTTP status alone is not actionable.

**Minimum fix:** `_error_detail()` extracts DataForSEO's own `status_code` and
`status_message` from any error body, bounded to 300 characters, reading only those
two named fields so a provider quoting the request back cannot leak it. Applied to
the 401, 402, 429 and generic branches.

The live error now reads:

```
DataForSEO returned HTTP 403. DataForSEO status_code 40104: Please verify your
account before using the API. You can complete verification in the user panel:
https://app.dataforseo.com/ .
```

Regression: `TestDataForSEOErrorSurfacing`, 5 tests, using the real 40104 body.

### B. Tavily returns page excerpts, not claims — REPORTED, NOT FIXED

Each Tavily `content` field is a ~2 000-character page excerpt, and the model treats
one excerpt as one "fact". The live excerpts contain navigation furniture
(`"Aller au contenu"`), cookie banners (`"La boutique ne fonctionnera pas..."`) and
AI-tool menus (`"ChatGPTClaudePerplexityGoogle AI Mode"`).

Two consequences, both visible in the run:

1. **Claim risk degenerates into document scanning.** A 2 KB excerpt containing
   `prime`, `TVA` or `garantie` anywhere is classified HIGH risk. That is why 9 of
   10 "claims" came out HIGH — the classifier is being handed documents, not claims.
2. **Relevance becomes trivially easy to satisfy.** 2 KB of on-topic text will
   almost always cover the query's topic tokens, which is why a page titled
   `"| Blog Webflow"` scored 1.00.

### C. No web evidence can ever be `supported` — REPORTED, NOT FIXED

`supported` requires `observability == OBSERVED`. Tavily's general search returns
no dates, so every web fact is `ESTIMATED`. **The web-research path therefore
yields zero supported facts for any query, ever** — not just this one.

The live run makes the interaction concrete: 10 relevant sources, 10 facts, **0
supported**, an empty `required_facts`, and a brief that cannot support a draft.

**Why this was not "fixed" here.** The obvious change — scaling the date
requirement by claim risk, so HIGH still needs a dated official source while LOW
and MEDIUM explanatory facts may rest on an undated specialist one — is defensible
and would leave HIGH-risk protection byte-for-byte unchanged. It was deliberately
not made, for three reasons:

- The mandate is to validate Phase 3, not redesign it, and this is an evidence-model
  decision rather than a threshold.
- It would not have unblocked this run anyway: the 9 HIGH-risk items also fail the
  *quality* bar, and the MEDIUM one fails it too.
- Fixing C without fixing B would be treating the symptom. The real defect is that
  a 2 KB page excerpt is being modelled as a single claim; sentence-level extraction
  with boilerplate stripping is the actual remedy, and it is Phase 4 design work.

**This is the one item that needs an owner decision**, and it is recorded in §28.

## 21. Provider Usage / Cost

Live run of 2026-08-12.

| Provider | Requests | Outcome | Cost |
|---|---:|---|---|
| DataForSEO | 3 | all HTTP 403 / 40104 | **$0.00** (response reports `cost: 0`) |
| Tavily | 3 | 200, 5–10 sources each | unknown — credits, no monetary figure returned |
| OpenAI | 2 | 200 | unknown — 1 probe (22 tokens) + 1 brief enrichment |

DataForSEO's 3 requests were 2 pipeline runs plus 1 diagnostic probe; none was
billable because none was served. Tavily's 3 were 1 contract probe and 2
component-validation searches. OpenAI's 2 were a 22-token contract probe and the
live brief enrichment.

**No `provider_usage` rows were persisted**, because both pipeline runs stopped at
the SERP stage before any usage was recorded — correct behaviour, and it confirms
the ledger records calls that happened rather than calls that were planned.

**Unknown is not rendered as free.** `total_cost_usd` was `null` for the component
validation, not `0.0`: Tavily bills in credits and returns no monetary figure.

Per-job ceilings (`SEOLEAD_MAX_CALLS_PER_PROVIDER = 3`) were never approached.

---

## 22. Resource Usage

No new container. DataForSEO, Tavily and OpenAI are external APIs.

| | Memory | Limit | CPU |
|---|---|---|---|
| `seolead_api` | 65 MiB | 512 MiB | 0.18% |
| `seolead_last30days` | 40 MiB | 768 MiB | 0.17% |

Host after: 40 containers, 8.8 GiB available, swap 2.0/2.0 GiB (pre-existing and
unchanged), 84 GB disk free.

Database: 18 tables (was 12), 6 added by migration `0002`.

---

## 23. Security Review

| Control | State |
|---|---|
| Secrets in git | none — `.env` ignored, scanned before commit |
| `.env.example` | credential keys empty or `CHANGE_ME`; asserted by shape, not allowlist |
| Credential reporting | statuses only; test asserts no fixture value appears |
| DataForSEO auth | `httpx auth=(login, password)`; never assembled into a logged string, never in a URL |
| Tavily auth | Bearer header; test asserts it is absent from URL and body |
| OpenAI auth | Bearer header; same assertion |
| Error messages | bounded; 401 handlers tested not to echo credentials |
| Log redaction | `key=value`, `"key": "value"`, bare `sk-` / `ghp_`; message and exception |
| Internal API | `X-Internal-Key`, `hmac.compare_digest`, fails closed 503 when unset |
| Public exposure | none — no Traefik labels, loopback-only binding |
| Containers | non-root, read-only, `cap_drop: ALL`, `no-new-privileges`, limits |
| DB privileges | re-verified: zero rights on every `acquisition_platform` table |

34 security tests. Disclosed residual unchanged from Phase 2: `acquisition_platform`
allows `PUBLIC` CONNECT (a PostgreSQL default this project did not change, because
changing it modifies another team's production database); `seolead_app` can connect
and read nothing.

---

## 24. Known Limitations

1. **No web evidence can ever be `supported`.** `supported` requires `OBSERVED`;
   Tavily's general search returns no dates; therefore every web fact is
   `ESTIMATED` and the web-research path yields zero usable evidence for any query.
   **This blocks content generation entirely** and needs an owner decision (§20b C).
2. **Page excerpts are modelled as claims.** Tavily's `content` is ~2 000 characters
   of page text including navigation and cookie banners. Treating one excerpt as one
   claim makes claim-risk classification degenerate into document scanning (9 of 10
   live excerpts came out HIGH risk) and makes relevance trivially easy to satisfy.
   Sentence-level extraction with boilerplate stripping is the real fix (§20b B).
3. **DataForSEO is unverified end to end.** The account was not verified at the time
   of the run, so organic results, PAA, related searches, keyword metrics, SERP
   analysis and the SERP-fed parts of the opportunity score remain unexercised
   against the real API.
4. **Relevance matching is lexical.** A source saying `photovoltaïque` where the
   query says `panneaux solaires` scores lower than it deserves. Embeddings over
   `pgvector` are the proper fix; the profile vocabulary lists are the interim
   mitigation.
5. **Thresholds are only partly validated.** The live run showed no false
   rejections (10/10 relevant), which tests the lenient direction. The strict
   direction — whether genuinely off-topic sources are caught in the wild — was not
   exercised, because nothing off-topic was returned.
6. **Opportunity weights are informed guesses.** Phase 7 replaces them with weights
   learned from conversion data.
7. **No Belgian official source appears in the top web results.** The live SERP
   yielded SPECIALIST and COMMERCIAL sources only. Since HIGH-risk claims require
   OFFICIAL or INSTITUTIONAL evidence, the pilot cannot say anything quantitative
   about subsidies or tariffs until regulator domains are reached deliberately —
   `authoritative_domains` lists 11, but Tavily surfaced none of them.
8. **Source quality is domain-based and coarse.** It cannot distinguish a careful
   trade publication from a careless one.
9. **Claim extraction is regex-based.** It catches quantified sentences; an
   unquantified false assertion passes factual QA and is left to the reviewer.
10. **No embeddings, no clustering, no cannibalisation detection.**
11. **The pipeline is still inline.** A long SERP + research + draft chain blocks
   the request.
12. **Keyword metrics cover one keyword per job.** The API accepts 1000; batching
    across a cluster is not implemented.
13. **SERP cache is per exact query.** Near-duplicate queries pay twice.

---

## 25. Deferred Items

| Item | Reason |
|---|---|
| Live provider testing | credential gate — §27 |
| Public website, domain, simulator | Phase 5 |
| Prospect 360 implementation | Phase 6; contract documented, 4 new ids added |
| Search Console, GA4, Ads | Phases 6–7 |
| Embeddings / semantic relevance | Phase 4 |
| Keyword clustering | Phase 4 |
| n8n workflow | designed, deferred |
| Price table for LLM cost | needs a decision on model and tier |
| Programmatic pages from PAA | forbidden without differentiated substance |

---

## 26. Files Changed

46 changed or added.

| Area | Files |
|---|---|
| `app/providers/search/` | 5 — base, dataforseo, normalizer, location, init |
| `app/providers/research/` | 1 — tavily |
| `app/providers/` | 1 — capabilities |
| `app/services/` | 8 — relevance, source_quality, claim_risk, package_builder_v2, serp_analysis, opportunity_score, factual_qa, research_cache, provider_usage, pipeline_v2, qa_service (v2 layer) |
| `app/models/` | 2 — search.py (6 tables), research.py (relevance + risk columns) |
| `app/schemas/` | 1 — serp |
| `app/core/` | 2 — config (provider settings, credential report), errors |
| `app/api/` | 2 — deps, internal (5 new endpoints) |
| `app/cli.py` | 6 new commands |
| `migrations/` | 1 — `0002_search_intelligence` |
| `config/verticals/` | 2 — provider policy, authoritative domains |
| `tests/` | 5 new suites + conftest fixtures |
| `docs/` | 8 new/updated |
| root | README, `.env.example`, this report |

---

## 27. Git Diff

Phase 3 implementation commit `6a62723`: 51 files, +8 333 / −52.

Live-validation commit (this one): 5 files —
`app/providers/search/dataforseo.py` (error surfacing),
`app/core/logging.py` (stderr), `tests/conftest.py` (hermetic fixtures),
`tests/test_search_providers.py` and `tests/test_security.py` (9 new tests),
plus this report.

`.env` excluded and verified absent. Pre-commit scan for `sk-*`, `ghp_*`, `tvly-*`
and populated connection URLs returns only the f-string template in
`scripts/create_database.sh` and deliberately fake fixture tokens in tests.

---

## 28. Recommended Phase 4

Two things gate everything else, and the first is a five-minute owner action.

### Immediate — owner actions

1. **Verify the DataForSEO account** at `https://app.dataforseo.com/`. The
   credentials are correct and the code is ready; this is the only thing standing
   between here and a full end-to-end validation. Re-run:

   ```bash
   docker exec seolead_api seolead research run \
     --vertical SOLAR_BE --query "prix panneaux solaires Belgique" \
     --market BE --language fr
   ```

2. **Decide the evidence-model question** (§20b B and C). The web-research path
   currently produces nothing usable, and no amount of threshold tuning changes
   that. Three options, in the order I would recommend them:

   | Option | What it does | Cost |
   |---|---|---|
   | **A. Sentence-level claim extraction** | Split Tavily excerpts into sentences, strip boilerplate, classify each as a claim. Fixes B and C together and makes claim risk mean what it says. | Phase 4 work, ~1 focused change |
   | **B. Risk-scaled date requirement** | HIGH still needs a dated official source; LOW/MEDIUM may rest on an undated specialist one. Leaves HIGH-risk protection byte-for-byte unchanged. | Small, but treats the symptom without A |
   | **C. Reach official sources deliberately** | Query regulator domains directly (`include_domains`) so HIGH-risk claims have somewhere to land. | Small; complements A |

   My recommendation is **A + C**, with B as a consequence of A rather than a
   standalone change. Doing B alone would let 2 KB page excerpts become "supported
   facts", which is worse than the current state.

### Then

3. **Complete the DataForSEO verification** once the account is live: organic
   results, PAA availability for a French Belgian query, whether Google Ads metrics
   return anything for `location_code 2056` + `language_code fr`, and the
   SERP-fed components of the opportunity score.
4. **Test the strict direction of the relevance gate.** The live run showed no false
   rejections, but nothing off-topic was returned, so the rejection path is
   unexercised in the wild. A deliberately noisy query would test it.
5. **Judge a real draft.** Generation has still never produced a full article from
   real evidence, so the anti-fabrication prompt plus factual QA remains unproven
   end to end — which was the open question at the end of Phase 2 and remains open.
6. **Add embeddings** (`pgvector`) for semantic relevance and near-duplicate
   detection.
7. **Keep the Prospect 360 platform-side conversation moving** — still the longest
   lead time of anything remaining.
