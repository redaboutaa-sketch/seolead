# PROSPECT 360 SEO LEAD FACTORY — Phase 2 Implementation Report

**Date:** 2026-08-12
**Workspace:** `/opt/seolead`, branch `main`
**Phase 1 discovery commit:** `30ce01e78afc74a808e70e6ebd352a5fa1231fcc`
**Outcome:** **PARTIAL** — the foundation and pipeline are complete, running and
tested; one acceptance criterion is met by design rather than by capability, and
one measured finding changes Phase 3.

---

## 1. Executive Summary

The Phase 2 foundation is built, deployed and exercised end to end against real
infrastructure. A dedicated database and least-privilege role exist, migrations are
applied, an isolated Last30Days runner is running, both provider abstractions are
implemented, the pipeline runs from a seed query through to a human approval gate,
and 187 tests pass without a single credential or network call.

**The headline is a measured finding, not a feature.** Phase 1 left one genuine
open question: does the Last30Days engine expose SERP structure usable for SEO? It
was run three times against the real engine and the answer is **no**.

For `prix panneaux solaires Belgique` the engine returned one "supported fact" — a
Hacker News post about *the making of a Grand Prix Circuit game mod*. Its web
source (which engine 3.18.4 calls `grounding`, not `web`) returned `no-results`
because no `SERPER_API_KEY` or `TAVILY_API_KEY` is provisioned. The same engine
returned 12 genuinely relevant results for the English query `AI agents` via Hacker
News. It is a tech-community discussion engine, and it is not a research provider
for French-language consumer commercial SEO.

This is a good outcome for the architecture and a real constraint on the plan. The
pipeline behaved exactly as designed under bad input: it recorded honestly that one
source was never configured, marked the single fact `OBSERVED` but noted only one
supported fact existed, built a complete deterministic brief anyway, and stopped
cleanly at `LLM_NOT_CONFIGURED`. Had a draft been generated, QA would have blocked
it with `REQUIRED_FACTS_UNUSED`. Nothing invented anything.

**Phase 3 cannot deliver a useful opportunity engine for Solar Belgium without a
real search/SERP provider.** That is now an evidenced budget decision rather than
an open question.

Two smaller findings worth the owner's attention: the engine renames `web` to
`grounding` between the pinned runner's whitelist and its own output (handled), and
it reports the same unconfigured state inconsistently as `no-results` in one run and
`unreachable` in another — the former being the more misleading of the pair, since
it claims a clean empty answer where the truth is that the source could not be used.

No production system was modified. Prospect 360 still holds 7 prospects and 2
tenants, `acquisition_platform` still has 156 tables, n8n still has its single
inactive workflow, Traefik is untouched, and ChainPilot's Last30Days runner has
still never been started.

---

## 2. Scope Delivered

| Mission section | Delivered |
|---|---|
| §4 components | ✅ API, database, ResearchProvider, LLMProvider, orchestration, persistence, CLI + API, QA, approval |
| §7 domain model | ✅ 11 tables |
| §8 migrations | ✅ Alembic `0001_initial`, hand-written; idempotent seed command |
| §9 database creation | ✅ `seolead` + `seolead_app`, password never printed, privileges verified |
| §10 isolated Last30Days | ✅ built, running, healthy, ChainPilot untouched |
| §11–13 research + package | ✅ port, adapter, normalizer, deterministic package builder |
| §14–16 LLM | ✅ port, OpenAI-compatible adapter, null provider; Hermes seam only |
| §17–19 brief + draft | ✅ hybrid brief, LLM draft with anti-fabrication prompt |
| §20 QA | ✅ deterministic (blocking) + LLM advisory (never blocking) |
| §21 approval gate | ✅ CLI + authenticated API, 4 states, terminal decisions |
| §22 entry point | ✅ `POST /internal/v1/research-jobs` and `seolead research run` |
| §23 idempotency | ✅ day-scoped key, unique constraint, verified by test |
| §24–26 status/failure/observability | ✅ explicit states, 13 error codes, JSON logs + redaction, `/health` + `/ready` |
| §27 docker | ✅ private network, no Traefik, loopback-only port |
| §28 n8n | ✅ documented, deferred, production untouched |
| §29 Prospect 360 contract | ✅ documentation only |
| §30–31 multi-vertical | ✅ YAML profiles, second vertical proves isolation |
| §32 tests | ✅ 187 tests, 10 suites, no credentials needed |
| §33 first Solar research | ✅ executed; result below |
| §36 documentation | ✅ all nine documents |

**Not delivered, by instruction:** website, simulator, Prospect 360 writes, domain,
Search Console, n8n deployment, SERP provider.

---

## 3. Git State Before Phase 2

```
pwd                       /opt/seolead
git branch --show-current main
git status --short        (clean)
git log -3 --oneline      30ce01e docs: add SEO Lead Factory discovery report
                          eeadefa chore: initialise SEO Lead Factory workspace…
```

Working tree clean. Precondition satisfied.

---

## 4. Architecture Implemented

```
                    ┌──────────────────────────────────────────┐
  operator ───────▶ │  CLI  `seolead …`   (primary interface)  │
                    │  API  127.0.0.1:8100 (X-Internal-Key)    │
                    └───────────────────┬──────────────────────┘
                                        │
┌───────────────────────────────────────▼───────────────────────────────────┐
│  seolead_api                                    network: seolead_backend  │
│                                                                           │
│   ┌──────────────────────────────────────────────────────────────────┐   │
│   │  PIPELINE  (inline; no queue, no broker)                         │   │
│   │                                                                  │   │
│   │  seed query                                                      │   │
│   │      ↓  classify_intent          deterministic, vertical config  │   │
│   │  ResearchProvider ──────────────────────────────▶ (port)         │   │
│   │      ↓  normalize                10 source states preserved      │   │
│   │  ResearchPackage                 DETERMINISTIC — no LLM          │   │
│   │      ↓                           provenance fixed here           │   │
│   │  ContentBrief                    HYBRID:                         │   │
│   │      │                             facts/sources/cautions = code │   │
│   │      │                             title/outline       = LLM opt │   │
│   │      ↓  LLMProvider ────────────────────────────▶ (port)         │   │
│   │  ContentDraft                    LLM required; no fake fallback  │   │
│   │      ↓                                                           │   │
│   │  QA  ├─ deterministic  ── BLOCKS                                 │   │
│   │      └─ LLM advisory   ── never blocks                           │   │
│   │      ↓                                                           │   │
│   │  Approval = PENDING              ← a human, always               │   │
│   └──────────────────────────────────────────────────────────────────┘   │
└──────────┬──────────────────────────────┬────────────────────────────────┘
           │                              │
   ┌───────▼─────────────┐   ┌────────────▼──────────────────────────────┐
   │ seolead_last30days  │   │ seolead database  (in platform_postgres)   │
   │ no ports, no auth,  │   │ role seolead_app — least privilege,        │
   │ read-only rootfs,   │   │ zero rights on acquisition_platform        │
   │ engine pinned       │   │ reached via techformanord_backend          │
   └─────────────────────┘   └───────────────────────────────────────────┘

   ╔═════════════════════════════════════════════════════════════════════╗
   ║ UNTOUCHED: Prospect 360 · TechFormaNord · ChainPilot ·              ║
   ║            Hermes gateway · n8n · Traefik                           ║
   ╚═════════════════════════════════════════════════════════════════════╝
```

Layer separation, as the mission requires:

| Layer | Owns | Never |
|---|---|---|
| Orchestration | order, retries, idempotency, persistence, state | judges content |
| Reasoning (LLM) | synthesis, drafting, advisory review | triggers a side effect, decides a gate |
| External I/O | talking outward | schedules, judges |
| Human gate | the publish decision | reads a QA result |

`approval_service.py` imports nothing from QA, and `test_approval.py` asserts it.

---

## 5. Database

**Owner Decision 3 honoured: no new PostgreSQL container.**

```
engine     platform_postgres — PostgreSQL 16.14, pgvector available
database   seolead           — owner seolead_app, PUBLIC CONNECT revoked
role       seolead_app       — LOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE,
                               NOREPLICATION, NOBYPASSRLS
migration  0001_initial      — applied
```

No password appears in this report, in git, in a log, or in any command line. It
was generated by `scripts/create_database.sh`, delivered to `psql` on stdin, and
written to `.env` (mode 600, git-ignored) by a script that never echoes it. Server
statement logging was verified off (`log_statement=none`) before the role was
created.

**Tables** (11): `vertical`, `site`, `seed_keyword`, `research_run`,
`research_source`, `research_evidence`, `research_package`, `content_brief`,
`content_draft`, `qa_review`, `approval`.

**Constraints that carry meaning, not just typing:**

| Constraint | Guarantees |
|---|---|
| `ck_research_source_state` | only the ten upstream Last30Days states are storable |
| `ck_research_evidence_observability` | no claim stored without OBSERVED/ESTIMATED/UNKNOWN |
| `uq_approval_draft` | one approval history per draft — a rejection cannot be overwritten |
| `uq_research_run_idempotency` | durable idempotency, independent of the runner's in-memory cache |
| `research_source.published_at` nullable | an unknown date stays unknown |

### Security model, verified not asserted

`scripts/verify_db_privileges.sh` runs against the live catalogue:

```
PASS  not superuser / no createdb / no createrole / no replication
PASS  database 'seolead' is owned by seolead_app
PASS  no SELECT on any acquisition_platform public table
PASS  no INSERT on any acquisition_platform public table
PASS  no UPDATE on any acquisition_platform public table
PASS  no DELETE on any acquisition_platform public table
PASS  can create and write a table in 'seolead'
```

**Residual, disclosed:** `acquisition_platform` still allows `PUBLIC` to CONNECT — a
PostgreSQL default this project deliberately did **not** change, because doing so
modifies another team's production database. `seolead_app` can therefore open a
connection to it and read nothing at all. Closing that right is the platform
owner's decision, not this project's.

---

## 6. Last30Days

### Isolated runtime

| | ChainPilot | SEO Lead Factory |
|---|---|---|
| Container | `last30days_runner` — **never started** | `seolead_last30days` — running, healthy |
| Image | `chainpilot/last30days-runner` | `seolead/last30days-runner:52f5331…` (333 MB) |
| Network | `chainpilot_network` | `seolead_backend` |
| Volume | `last30days_memory` | `seolead_last30days_memory` |
| Keys | ChainPilot `.env` | `/opt/seolead/.env` |

No mutable state is shared. Nothing of ChainPilot's was modified, started or read
at runtime.

### Reused components

Two files were vendored **byte-identically** with recorded SHA-256 checksums
(`infra/last30days/PROVENANCE.md`): the runner `app.py` and its `requirements.txt`.
The build context is `/opt/seolead`, so nothing outside this repository is read at
build time.

The alternative — pointing a build context at `/opt/l30d-build` — was rejected: it
would make this project's build depend on another team's working tree, where a
change would silently change what we build. The *real* reuse is preserved exactly:
the same engine at the same pinned commit, the same wire contract, the same
security posture.

### Version and health

```
engine commit   52f53312ff2f272e16bbc1785e1c04f9d9c19b31   (pin verified at build)
engine version  3.18.4
runner          healthy; /readyz 200
```

The build fails closed if the pinned commit cannot be fetched and verified, and
rejects a branch or tag outright.

### Resource footprint

`seolead_last30days` ~40 MiB RSS against a 768 MiB limit, 1.0 CPU cap,
`L30D_MAX_CONCURRENT_RUNS=1` (below ChainPilot's 2, because this host now runs 40
containers). A research call takes 3–6 s.

### Live test — the Phase 1 open question, answered

| Topic | Sources | Outcome |
|---|---|---|
| `prix panneaux solaires Belgique` | web, reddit, youtube, hackernews | `grounding: no-results`, `reddit: partial` (0 items), `youtube: skipped-unconfigured`, `hackernews: ok` (1 item, irrelevant) |
| `solar panel cost Belgium` | web | `grounding: no-results`, 0 results |
| `AI agents` | web, hackernews | `grounding: unreachable`, `hackernews: ok` — **12 relevant results** |

**Conclusions:**

1. The engine renames `web` → `grounding`. Handled: the normalizer reads the source
   names the report contains rather than the ones requested.
2. `grounding` is non-functional without `SERPER_API_KEY` / `TAVILY_API_KEY`,
   neither of which exists on this host.
3. **No SERP structure is returned at all** — no ranked results, no People Also
   Ask, no features. It is not a keyword or SERP tool and does not try to be.
4. It is a tech-community discussion engine: strong on English technical topics via
   Hacker News, useless for French consumer commercial queries.

**Therefore Last30Days is not a viable primary research provider for the Solar
Belgium pilot.** It remains wired in as the first `ResearchProvider` implementation
and it proved the entire contract end to end — which is exactly what Phase 2 needed
it to do.

---

## 7. ResearchProvider

```python
class ResearchProvider(Protocol):
    code: str
    async def research(self, *, query, market, language,
                       correlation_id, idempotency_key=None) -> ResearchProviderResult
    async def health(self) -> dict          # never raises
```

`Last30DaysProvider` maps the wire format into provider-neutral types
(`NormalizedSource`, `NormalizedFact`, `SourceOutcome`). Nothing downstream sees a
Last30Days shape; provider extras live namespaced under `provider_metadata`.

The normalizer honours the two upstream rules that make the evidence model work:

- **Unknown fields are omitted, not nulled.** Nothing indexes; everything uses
  `.get()`. An unparseable date is dropped rather than replaced with `now()`.
- **Only `no-results` is a clean empty.** The other nine states are preserved
  distinctly, and an unrecognised state becomes `schema-drift` — explicitly *not*
  clean-empty, so drift can never masquerade as "nothing found".

Freshness maps onto knowledge: `contradicted`/`unsupported` → `UNKNOWN`,
`stale` → `ESTIMATED`, undated → `ESTIMATED`, `current` + dated → `OBSERVED`.

---

## 8. LLMProvider

Capability-routed (`RESEARCH_SYNTHESIS`, `CONTENT_BRIEF`, `LONG_FORM_WRITING`,
`CLASSIFICATION`, `SEO_QA`), never model-named in business code. Every response
carries `usage` with token counts, persisted on the draft — the KPI is *profitable*
leads, and a factory that cannot report its own cost cannot report profit.

`OpenAICompatibleProvider` serves OpenAI, DeepSeek, Together or a local vLLM via
base-URL configuration. Retries 429/5xx with backoff; a non-429 4xx is **not**
retried, because a 400 will not become a 200.

`NullLLMProvider` refuses rather than fabricating. There is deliberately no
template fallback: a stitched-together article would read like content and be
written by nobody, from no evidence.

`HermesGatewayProvider` is a documented seam, not an implementation. Phase 1
verified the existing gateway is read-only and belongs to another product's stack;
the pattern was adopted, the coupling was not.

**No hidden model reasoning is stored anywhere.**

---

## 9. ResearchPackage

Deterministic. `package_builder.py` never calls a model — if it did, the guarantee
that every fact traces to a retrieved source would rest on a model's good behaviour
instead of on code.

Each fact carries `observability`, `confidence`, `source_ref` and a computed
`supported` flag, which is true only when the fact is `OBSERVED` **and** its source
reference resolves inside the package. A dangling reference is not support.

`confidence_summary` is the honest accounting:

```
facts_total · facts_observed · facts_estimated · facts_unknown · facts_supported
sources_total · source_types_with_items · source_types_clean_empty
source_types_degraded · source_types_unconfigured · partial_observation
```

`source_types_with_items` counts sources that **actually returned an item**, not
sources whose state permits items. This was corrected during Phase 2: a real run
showed `reddit: partial` with zero items, which the state-based count reported as a
source "with items" — overstating coverage in precisely the direction that matters.

---

## 10. ContentBrief

Hybrid, with the split the mission asks for: **provenance deterministic, synthesis
optional.**

Always deterministic: `required_facts` (supported only), `required_sources`,
`cautionary_claims`, `missing_information`, content type, intent, slug, CTA.

LLM, only when configured and only additive: a better title, a richer outline. Any
failure returns the deterministic payload unchanged.

An LLM cannot delete an unresolved fact by rewriting around it: the unresolved list
is assembled from the package after synthesis, not from the model's output.

Content-type selection follows intent, and `ARTICLE` is the residual rather than
the default — comparison → `COMPARISON`, commercial → `LANDING_PAGE`,
informational → `GUIDE`. `LOCAL_PAGE` is deliberately unreachable in Phase 2
because a local page needs locally-specific verified facts and nothing enforces
that yet.

---

## 11. Draft Generation

Requires an LLM; there is no fallback. The system prompt is built from the brief,
so its prohibitions are specific to this vertical and this evidence: use only
supplied facts; never invent a statistic, price, subsidy, regulation, study or
testimonial; never present an estimate as a measurement; do not write around the
listed limitations; no keyword stuffing; no manufactured urgency or guaranteed
outcomes. Restricted topics with no supporting evidence are named explicitly in the
prompt.

Output is `{title, meta_title, meta_description, body}` as JSON. A non-JSON
response is a provider error, not something to salvage with a regex — salvaging
risks persisting a half-parsed body.

---

## 12. QA

**Deterministic (blocking):** presence of title/meta/body; body length; heading
structure; placeholder leakage; vertical forbidden phrases; **numeric claims absent
from the evidence**; quantified restricted topics; required-facts actually used;
source traceability; keyword-stuffing density; duplicate title; CTA present.

**LLM advisory (never blocking):** intent alignment, usefulness, repetition, CTA
fit. Stored as a separate `QAReview` with `blocking` forced false on every finding.
A model asked "is this accurate?" answers confidently either way; treating that as
proof would be the failure this pipeline exists to prevent.

The numeric check compares digit-only forms, so `6 000`, `6.000` and `6,000` are one
quantity across fr-BE, nl-BE and en. Years (1900–2100) and figures already in the
query are excluded as noise rather than risk.

24 QA tests, including: an unsupported price blocks; the same price blocks *not* when
present in the evidence; an unsupported percentage blocks; a year does not; a
quantified subsidy claim blocks; a draft ignoring every supported fact blocks; and a
high score with one blocking issue still fails, because **the score is not the gate**.

---

## 13. Human Approval

`PENDING → APPROVED | REJECTED | NEEDS_REVISION`. `APPROVED` and `REJECTED` are
terminal; reopening means `NEEDS_REVISION`, a deliberate decision that leaves the
prior state in the record. The deciding actor and timestamp are always recorded.

Three structural guarantees:

1. Approval is a **separate table**, not a nullable column on the draft.
2. `uq_approval_draft` means a rejection cannot be overwritten by inserting an
   approving row.
3. `approval_service.py` imports nothing from QA, asserted by test. A draft that
   passes QA sits at `PENDING` exactly like one that failed.

Verified by `test_pipeline.py::test_qa_success_never_becomes_approval` and
`test_qa_failure_still_creates_a_pending_approval` — a failed draft is not silently
discarded; a human still sees it.

---

## 14. API / CLI

```bash
# Setup
./scripts/create_database.sh
./scripts/verify_db_privileges.sh
docker compose build && docker compose up -d
docker exec seolead_api seolead seed

# Health
curl -s http://127.0.0.1:8100/health
curl -s http://127.0.0.1:8100/ready | python3 -m json.tool
docker exec seolead_api seolead health

# Run the pipeline
docker exec seolead_api seolead research run \
  --vertical SOLAR_BE --query "prix panneaux solaires Belgique" \
  --market BE --language fr
docker exec seolead_api seolead research run --vertical SOLAR_BE \
  --query "..." --stop-after package

# Inspect
docker exec seolead_api seolead package show <id>
docker exec seolead_api seolead brief   show <id>
docker exec seolead_api seolead draft   show <id> --body

# Approve
docker exec seolead_api seolead content pending
docker exec seolead_api seolead content approve <draft-id> --by "Reda" --note "ok"
docker exec seolead_api seolead content reject  <draft-id> --by "Reda"
docker exec seolead_api seolead content request-revision <draft-id> --by "Reda"
```

API equivalent (all routes behind `X-Internal-Key`):

```
POST /internal/v1/research-jobs
GET  /internal/v1/research-runs/{id}   GET /internal/v1/research-packages/{id}
GET  /internal/v1/briefs/{id}          GET /internal/v1/drafts/{id}
GET  /internal/v1/drafts               GET /internal/v1/verticals
POST /internal/v1/content/{id}/approve | /reject | /request-revision
```

CLI exit codes: `0` complete · `2` ran correctly but stopped at a gate · `1` error.

---

## 15. Tests

**187 passed, 0 failed, 0 skipped**, in 8.1 s. No network, no credentials.

| Suite | Tests | Covers |
|---|---:|---|
| `test_security.py` | 34 | auth on every route, fail-closed, input validation, secret redaction, no secrets in repo |
| `test_persistence.py` | 25 | every CHECK and UNIQUE constraint, nullable domain, nullable `published_at` |
| `test_qa.py` | 24 | blocking logic, fabricated numbers, forbidden phrases, stuffing, duplicates |
| `test_normalizer.py` | 21 | ten source states, observability mapping, contract versioning, drift |
| `test_pipeline.py` | 19 | end-to-end, LLM-absent path, idempotency, failure propagation, approval gate |
| `test_approval.py` | 19 | state machine, terminal states, QA independence |
| `test_intent.py` | 17 | intent, content-type selection, slugs, market-vs-local terms |
| `test_llm_provider.py` | 12 | retries, non-retryable 4xx, key handling, JSON mode |
| `test_package_builder.py` | 8 | confidence accounting, supported flags, dangling refs |
| `test_multi_vertical.py` | 8 | pipeline runs identically for an unrelated second vertical |

Persistence tests run the production models on SQLite, which is what proves the
schema depends on no PostgreSQL-only feature.

**Three real defects were found by these tests during Phase 2**, each fixed in the
code rather than papered over in the test:

1. **Market name treated as a locality.** "Belgique" is in the market's own name,
   so *every* Belgian query classified as `LOCAL` intent and routed to the wrong
   content type and CTA. Fixed by separating `market_terms` from `local_terms`.
2. **Redactor missed JSON-quoted keys.** The pattern matched `api_key=value` but
   not `"api_key": "value"` — the shape this application actually logs. Fixed.
3. **Coverage overstated.** `source_types_with_items` counted states that *permit*
   items rather than sources that *returned* them, so `reddit: partial` with zero
   items read as coverage. Fixed.

A fourth, in the tests themselves: a session-scoped fixture was shared by
reference, so contract-drift mutations leaked across tests and the suite passed or
failed by ordering. Fixed with a deep copy.

---

## 16. First Solar Research Test

```
vertical            SOLAR_BE
query               prix panneaux solaires Belgique
market / language   BE / fr
correlation_id      a33020358f37438c881ce43e263c0b34
duration            3 642 ms research, 5.7 s wall clock
```

| Artefact | Id |
|---|---|
| keyword | `91877ca5-0b33-4fa8-9a75-7637e5710cea` |
| research_run | `4518ac0b-16d5-4ff0-9998-b659ad8677a0` (SUCCEEDED) |
| research_package | `1e1b6fed-a13e-4bc0-b7b9-a86e0dc03a2e` |
| content_brief | `7f4cf12d-c32c-4c84-9beb-c47165f9cd0a` |
| content_draft | — not generated |
| qa_review | — |
| approval | — |

**Provider outcome**

```
grounding    no-results             items=0
hackernews   ok                     items=1
reddit       partial                items=0
youtube      skipped-unconfigured   items=0

engine_commit 52f53312ff2f272e16bbc1785e1c04f9d9c19b31   engine_version 3.18.4
```

**Package**

```
sources: 1 · facts: 1 · supported: 1 · observed: 1 · estimated: 0 · unknown: 0
partial_observation: false
unresolved: "Source 'youtube' was not configured and was never queried."
```

The single supported fact is *"The making of Don Matrelli's Legacy, a mod for Grand
Prix Circuit (part I)"* — a Hacker News post with no relationship to Belgian solar
pricing. The pipeline recorded it faithfully and did not pretend otherwise.

**Brief** (deterministic, produced despite the poor research)

```
content_type LANDING_PAGE   intent COMMERCIAL
title        Prix panneaux solaires Belgique
slug         prix-panneaux-solaires-belgique
cta          quote_request — "Demander un devis personnalisé" (matches COMMERCIAL)
required_facts 1 · required_sources 1 · cautionary_claims 16 · outline 7 sections
```

The 16 cautionary claims are the Solar profile's restricted topics — subsidies,
green certificates, prosumer tariffs, guaranteed returns — every one flagged as
having no supporting evidence and therefore unassertable.

**Pipeline outcome**

```
stopped_at   draft
error_code   LLM_NOT_CONFIGURED
error_detail "No LLM provider configured. Research package and deterministic brief
              were produced and persisted."
```

Exactly the designed behaviour. And note what *would* have happened with a
credential: an LLM asked to write about solar prices could not have echoed a
racing-game fact, so QA would have blocked the draft with `REQUIRED_FACTS_UNUSED`.
The gate works even when the research does not.

---

## 17. Resource Usage

Before Phase 2 — 39 containers, 6.6 GiB used, 9.0 GiB available, swap 1.9/2.0 GiB,
83 GB disk free.

After — **40 containers** (two added, one pre-existing service unchanged):

| | Memory | Limit | CPU |
|---|---|---|---|
| `seolead_api` | 59 MiB | 512 MiB | 0.22% |
| `seolead_last30days` | 40 MiB | 768 MiB | 0.21% |

Host after: 6.6 GiB used, **9.1 GiB available**, swap 2.0/2.0 GiB, 84 GB free.
Images: 301 MB + 333 MB.

Net effect ≈ 100 MiB RSS. Swap remains near-full — a pre-existing condition
unchanged by this work, and the reason both services declare hard limits well below
what they use.

No unrelated container was stopped, restarted or resource-constrained.

---

## 18. Security Review

| Control | State |
|---|---|
| Secrets in git | none — `.env` git-ignored, mode 600, scanned before commit |
| `.env.example` | placeholders only; a test asserts nothing key-shaped is in it |
| Generated DB password | never printed, never in argv, delivered on stdin; statement logging verified off first |
| DB role | least privilege, verified against the live catalogue |
| Internal API | `X-Internal-Key` with `hmac.compare_digest`; **fails closed 503 when unset** |
| Public exposure | none — no Traefik labels, loopback-only host binding |
| Research runner | no port, no auth, network-isolated by design |
| Containers | non-root (10001/10002), `read_only`, `cap_drop: ALL`, `no-new-privileges`, tmpfs `noexec,nosuid` |
| Docker socket | not mounted anywhere |
| Health endpoints | expose no secret — booleans and self-reported versions only |
| Log redaction | `key=value`, `"key": "value"`, bare `sk-`/`ghp_`; applied to message and exception |
| Test fixtures | no real credentials; suite passes with none |

34 security tests, including that every internal route rejects a missing or wrong
key, that **approval specifically** cannot be reached anonymously, and that an
unset key produces 503 rather than open access.

**Disclosed residual:** `seolead_app` can open a connection to
`acquisition_platform` because that database allows `PUBLIC` to CONNECT — a
PostgreSQL default. It holds no privilege on any object there, verified. Revoking
`PUBLIC CONNECT` is a production change to another team's database and was
therefore not made.

---

## 19. Prospect 360 Future Integration Contract

Documented only, in `docs/integrations/PROSPECT360_INGEST_CONTRACT.md`. Nothing was
implemented on either side; Phase 2 holds no credential for Prospect 360 and writes
nothing to it.

The contract covers a `POST /api/v1/tenant-leads` ingest endpoint (path proposed,
not required) with identity, consent, a full attribution envelope and an
idempotency key; outcome callbacks from Prospect 360 covering `QUALIFIED` through
`WON`/`LOST`; and a mapping onto existing `prospects` columns.

Three Phase-1 findings make platform-side work unavoidable: host-bound cookie-JWT
auth fails closed for a machine on a new domain; `tenant_service_accounts` has 0
rows and no backend code; and `ProspectCreate` accepts no UTM fields at all (and
silently discards `company_name`, `sector`, `city`). `utm_term` does not exist as a
column.

**Owner action:** this work must be scheduled with whoever owns the TechFormaNord
repository. It cannot be delivered from `/opt/seolead`, and it is the longest-lead
item in the roadmap.

---

## 20. Known Limitations

1. **No topical relevance scoring.** A racing-game post scored as a supported fact
   for a solar query. QA catches the downstream symptom, nothing scores query↔fact
   relevance. **Highest-priority Phase 3 gap.**
2. **Research quality is provider-limited.** Last30Days cannot serve this vertical
   without a paid search key, and returns no SERP structure with one.
3. **The draft path is unproven against a real model.** Exercised only with a stub;
   no LLM credential exists. The prompt's anti-fabrication rules are untested
   against a real model's behaviour.
4. **Advisory QA likewise unproven.**
5. **`pgvector` unused.** Available in the engine; no embeddings, so no clustering
   and no near-duplicate detection yet.
6. **No cost pricing.** `cost_cents` stays `None` until a price table is configured.
7. **Inline pipeline.** A long research call blocks the request. Fine for one
   operator; not for scheduled fan-out.
8. **One provider per port.** The registries are `if` statements; they become
   tables when a second implementation lands.
9. **No metrics endpoint.** Structured logs only; Prometheus scraping is Phase 3.
10. **Idempotency is day-scoped.** Two runs in one day reuse; there is no explicit
    "force refresh" flag yet.
11. **`utm_term` has no home** on either side of the future contract.
12. **Engine source-name drift** (`web` → `grounding`) is handled but not pinned;
    a future engine could rename again.

---

## 21. Deferred Items

| Item | Reason |
|---|---|
| Public website, sitemap, hreflang | Phase 5 |
| Solar simulator | Phase 5; needs dated, sourced reference data |
| Prospect 360 writes | Phase 6; needs platform-side work |
| Search Console, Analytics, Ads | Phases 6–7; need a verified domain |
| SERP / keyword provider | needs an owner budget decision |
| n8n workflow | designed and documented; cron is simpler for now |
| Hermes provider | seam only, by instruction |
| Traefik routing | not wanted — this API approves content and triggers spend |
| Redis / Celery | no weight in Phase 2 |
| Embeddings and clustering | Phase 3 |

---

## 22. Phase 3 Recommendation

The measured Last30Days result reorders the plan. Building an opportunity engine on
a research provider that returns nothing relevant for the pilot vertical would
produce confidently-scored noise.

**Recommended Phase 3 sequence:**

1. **Procure a search/SERP provider and add `SerpProvider`.** Serper is already
   referenced by the Last30Days engine (`SERPER_API_KEY`) and is the cheapest way
   to make `grounding` work; a dedicated SERP API (DataForSEO, SEMrush) is needed
   for ranked results, People Also Ask and competitor analysis. **This is now an
   evidenced budget decision, not an open question.**
2. **Add topical relevance scoring** between retrieval and package assembly, using
   `pgvector` embeddings of query and fact. Limitation 1 is the most consequential
   thing in this report after the provider finding.
3. **Add a `FirecrawlProvider`** — `FIRECRAWL_API_KEY` already exists on this host
   (though it belongs to another product's account; an owner decision).
4. **Keyword clustering and the SEO Opportunity Score**, with every metric carrying
   `OBSERVED`/`ESTIMATED`/`UNKNOWN` and an `unknown_dimension_count` shown beside
   the score.
5. **Prove the draft path against one real model** on a single query, and measure
   whether the anti-fabrication prompt plus QA actually holds.
6. **Start the platform-side Prospect 360 conversation now**, in parallel — it has
   the longest lead time of anything remaining.

Keep Last30Days wired in. It is genuinely useful for the AI Automation and AI
Training verticals, where the audience *is* the technical community it indexes.

---

## 23. Files Changed

79 files, +8 712 / −26.

| Area | Files |
|---|---|
| `app/` | 25 — api (4), core (5), db (3), models (4), providers (8), schemas, services (8), verticals, cli, main |
| `tests/` | 12 — 10 suites, conftest, fixture |
| `docs/` | 9 — architecture, implementation, 2 providers, integration, 2 runbooks, n8n |
| `migrations/` | 3 — env, template, `0001_initial` |
| `infra/last30days/` | 4 — Dockerfile, vendored runner + requirements, PROVENANCE |
| `config/verticals/` | 2 — `solar_be.yaml`, `test_generic.yaml` |
| `scripts/` | 2 — create database, verify privileges |
| root | 7 — README, this report, Dockerfile, compose, pyproject, alembic.ini, .env.example, .gitignore |

Modified from Phase 1: `README.md`, `.gitignore`.

---

## 24. Git Diff Summary

```
 79 files changed, 8712 insertions(+), 26 deletions(-)
```

`.env` excluded and verified absent from the change set. A pre-commit scan for
`sk-*`, `ghp_*` and populated connection URLs returned only an f-string template in
`scripts/create_database.sh` and deliberately fake tokens in `test_security.py`.

---

## 25. Exact Recommended Next Action

**Decide on a search/SERP provider.** Everything else in Phase 3 is downstream of
it, and the decision is now evidenced rather than speculative: the pipeline works,
and it is being starved of input.

Concretely, in order:

1. Approve a provider and budget — Serper (cheapest; makes the existing
   `grounding` source functional) or a dedicated SERP API (needed for ranked
   results, PAA and competitor analysis). Both, most likely.
2. Add the key to `/opt/seolead/.env`, restart `seolead_last30days`, and re-run the
   same Solar query to measure the difference against the baseline recorded above.
3. In parallel, open the Prospect 360 platform-side conversation (service accounts,
   ingest endpoint, outcome callbacks).
4. Then run Phase 3.

Optionally, if an LLM credential can be provided, run one draft end to end to prove
the generation path and the anti-fabrication prompt against a real model. Not a
blocker — but it is the one significant path exercised only by a stub.
