# PROSPECT 360 SEO LEAD FACTORY — Phase 3 Implementation Report

**Date:** 2026-08-12
**Workspace:** `/opt/seolead`, branch `main`
**Phase 2 commit:** `4b9230f6a83ea09740a2484b6551adb4106b57e4`
**Outcome:** implementation complete and tested. **STOP A — WAITING_FOR_CREDENTIALS.**

---

## 1. Executive Summary

Phase 3 replaces the research layer, adds the search-intelligence layer, and fixes
the defect Phase 2's live run exposed. Everything is built, migrated and tested.
**No live external call has been made**, because DataForSEO, Tavily and OpenAI are
all `NOT_CONFIGURED` — the credential gate in §27 of the mission, reached
deliberately.

The centre of the work is the **relevance gate**. Phase 2 offered a single
"supported fact" for `prix panneaux solaires Belgique`: a Hacker News post titled
*"The making of Don Matrelli's Legacy, a mod for Grand Prix Circuit (part I)"*.
Nothing asked whether the source was about the query.

The fix is less obvious than it first appears, and the reason is worth stating:
**"prix" appears in "Grand Prix"**. A gate scoring bare token overlap gives that
source a third of the query and calls it partially relevant. So the gate splits a
query into three kinds of token using the vertical profile — *topic* (`panneau`,
`solaire`), *modifier* (`prix`), *market* (`belgique`) — and applies one hard rule:
a source matching zero topic tokens is IRRELEVANT however many modifiers it
matches. That rejects the racing-game post deterministically, with a reason an
operator can read, before any model is consulted.

Three further structural changes matter. **Relevance, source quality and claim risk
are separate axes** — a forum thread can be perfectly relevant and a poor authority
for a tax rate. **Ranking is not authority**: `classify_domain` is never given a
SERP position, so it cannot use one. And **`supported` now requires four conditions
rather than one**, including that the evidence clears the bar the claim's risk
level demands.

Building this surfaced three real bugs, each fixed in code rather than in the test:
a French stemmer that turned `panneaux` into `panneal` and thereby silently
disabled the gate's central check; a cost ledger that depended on every adapter
remembering to record itself; and a security test whose hand-written allowlist
would fail for the wrong reason on every new setting.

**336 tests pass with no credentials and no network.** Migration `0002` is applied
and was verified reversible against the live database with Phase 2 data present.
Nothing in production was touched: 7 prospects, 1 n8n workflow, 156 tables in
`acquisition_platform`, ChainPilot's Last30Days runner still never started.

**What is not proven:** every provider is exercised against mock transports only.
The wire contracts were read from official documentation rather than guessed, but a
contract read is not a contract exercised.

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
| §27 credential gate | ✅ **reached — stopped here** |
| §29 regression tests | ✅ all five, plus the stemmer |
| §30 Prospect 360 preparation | ✅ documentation only, 4 new attribution ids |
| §32 tests | ✅ 336, no credentials |
| §34 documentation | ✅ all eleven documents |

**Not delivered, by instruction:** live testing (§28), website, domain, simulator,
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

```
DATAFORSEO      NOT_CONFIGURED
TAVILY          NOT_CONFIGURED
OPENAI          NOT_CONFIGURED
INTERNAL_API    CONFIGURED
ready_for_live_test: false
```

Reported by `seolead credentials` and `GET /internal/v1/credentials`. **Statuses
only** — no value, no prefix, no length. A report that leaks four characters of a
key is still a leak, and a test asserts the report contains no fixture value.

Verified graceful behaviour with none configured: the pipeline builds the provider
plan (correctly skipping community research for SOLAR_BE), then stops at the SERP
stage with `PROVIDER_NOT_CONFIGURED` and **no request attempted**.

`PROVIDER_NOT_CONFIGURED` was added as a distinct code during this phase. It had
been reporting as generic `RESEARCH_FAILED`, which is the operator's most
actionable failure and deserved to say so: nothing went wrong, a key is absent, and
the fix is an operator action rather than a retry.

Exact secure procedure: `docs/runbooks/PROVIDER_CREDENTIALS.md`, summarised in §20.

---

## 19. Test Results

**336 passed, 0 failed, 0 skipped**, ~12 s. No network, no credentials.

| Suite | Tests |
|---|---:|
| `test_phase3_services.py` | 63 |
| `test_search_providers.py` | 37 |
| `test_security.py` | 34 |
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

**WAITING_FOR_CREDENTIALS.**

Not run. All three external providers are `NOT_CONFIGURED`, and §27 requires
stopping here rather than substituting providers or requesting keys in chat.

Once credentials are in place, the run is:

```bash
docker exec seolead_api seolead research run \
  --vertical SOLAR_BE --query "prix panneaux solaires Belgique" \
  --market BE --language fr
```

Expected shape of the result — DataForSEO organic count, SERP features, PAA and
related counts, metric availability; Tavily sources returned and how many pass the
gate; Last30Days **skipped** by policy; package eligible/rejected/supported/
unresolved counts; draft with model and token usage; factual and SEO QA status;
final state `PENDING_APPROVAL`.

Reading guide and troubleshooting: `docs/runbooks/LIVE_RESEARCH.md`.

### Exact operator procedure

Full version with copy-paste blocks in `docs/runbooks/PROVIDER_CREDENTIALS.md`.
Each uses `read -s` so the value never reaches the terminal or shell history, and a
Python helper that writes into `.env` without printing it.

```bash
cd /opt/seolead

# DataForSEO — API password from https://app.dataforseo.com/api-access
read -r -p  "DataForSEO login: " DFS_LOGIN
read -r -s -p "DataForSEO API password: " DFS_PASS; echo
# → writes DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD (see runbook for the helper)
unset DFS_LOGIN DFS_PASS

# Tavily — https://app.tavily.com
read -r -s -p "Tavily API key: " TAVILY_KEY; echo    # → TAVILY_API_KEY
unset TAVILY_KEY

# OpenAI — https://platform.openai.com/api-keys
read -r -s -p "OpenAI API key: " OPENAI_KEY; echo    # → SEOLEAD_LLM_API_KEY
unset OPENAI_KEY

sed -i 's|^SEOLEAD_LLM_MODEL=.*|SEOLEAD_LLM_MODEL=gpt-4o|' .env   # not a secret
chmod 600 .env
docker compose up -d seolead_api
docker exec seolead_api seolead credentials    # expect ready_for_live_test: true
```

Do not paste any credential into chat, a ticket or a commit.

---

## 21. Provider Usage / Cost

No spend has occurred — no external call was made.

The accounting is built and tested:

| Provider | Billing | Recorded |
|---|---|---|
| DataForSEO | ~$0.002 / live advanced SERP, prepaid | its own `cost`, `cost_is_actual = true` |
| Tavily | credits | `cost_usd = None`, `cost_is_actual = false` |
| OpenAI | per token | tokens recorded; no price table |

**Unknown is never rendered as free.** `total_cost_usd` returns `None` rather than
`0.0` when nothing was priced.

Ceilings are checked **before** each request (`SEOLEAD_MAX_CALLS_PER_PROVIDER`,
default 3), so a runaway loop raises `PROVIDER_BUDGET_EXCEEDED` rather than
producing an invoice.

Freshness: SERP 24 h, web research 168 h, community 72 h, keyword metrics ≥168 h.
`--force-refresh` always overrides. A second identical job inside the TTL reuses
the snapshot — verified by test that the provider is called once, not twice.

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

1. **Nothing is proven against a live provider.** Contracts were read from official
   documentation, not exercised. Field-name drift, undocumented response shapes and
   real error bodies remain unverified. This is the single largest unknown.
2. **Relevance matching is lexical.** A source saying `photovoltaïque` where the
   query says `panneaux solaires` scores lower than it deserves. Embeddings over
   `pgvector` are the proper fix; the profile vocabulary lists are the interim
   mitigation.
3. **Thresholds are unvalidated.** Chosen so the Phase 2 failure is rejected and
   obvious cases pass. Not measured against a labelled corpus, and the docs say so.
4. **Opportunity weights are informed guesses.** Phase 7 replaces them with weights
   learned from conversion data.
5. **Most web evidence will be ESTIMATED, not OBSERVED**, because Tavily's general
   search returns no dates. HIGH-risk claims will therefore mostly need an official
   source — correct, but it means the pilot needs regulator sources in the evidence
   set to say anything quantitative about subsidies.
6. **Source quality is domain-based and coarse.** It cannot distinguish a careful
   trade publication from a careless one.
7. **Claim extraction is regex-based.** It catches quantified sentences; an
   unquantified false assertion passes factual QA and is left to the reviewer.
8. **No embeddings, no clustering, no cannibalisation detection.** `pgvector` is
   available and unused.
9. **The pipeline is still inline.** A long SERP + research + draft chain blocks
   the request.
10. **Keyword metrics cover one keyword per job.** The API accepts 1000; batching
    across a cluster is not implemented.
11. **SERP cache is per exact query.** Near-duplicate queries pay twice.

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

```
 46 files changed (see §26)
```

`.env` excluded and verified absent. Pre-commit scan for `sk-*`, `ghp_*`, `tvly-*`
and populated connection URLs returns only the f-string template in
`scripts/create_database.sh` and deliberately fake fixture tokens in tests.

---

## 28. Recommended Phase 4

**First, close the credential gate and run the live test.** Everything below is
downstream of what that measurement shows, and planning past it would be guessing
twice in a row.

Then, in order:

1. **Verify the contracts against reality.** Field drift, real error bodies, actual
   PAA availability for a French Belgian query, and whether DataForSEO's Google Ads
   metrics return anything for `location_code 2056` + `language_code fr`.
2. **Tune the relevance thresholds against real rejections**, using
   `seolead package rejected`. Expect the first live run to reject either too much
   or too little; the instrumentation exists precisely to find out which.
3. **Add embeddings** (`pgvector`) for semantic relevance and near-duplicate
   detection. Limitation 2 is the most consequential remaining gap in the gate.
4. **Keyword clustering and multi-keyword jobs** — batch metrics, cluster the PAA
   and related searches into a content plan rather than one page per query.
5. **Judge the first real draft.** The generation path has never met a real model.
   Whether the anti-fabrication prompt plus factual QA actually holds is the
   question Phase 4 should answer with evidence.
6. **Keep the Prospect 360 platform-side conversation moving** — still the longest
   lead time of anything remaining.
