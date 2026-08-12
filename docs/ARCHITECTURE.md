# Architecture

## The one idea

Everything external sits behind a port. Last30Days is *a* `ResearchProvider`, not
*the* research layer. OpenAI is *an* `LLMProvider`. Solar Belgium is *a* vertical
profile, not a branch in the code.

That is not architectural taste — Phase 2 immediately needed it. The first real
research run proved Last30Days cannot serve the Solar pilot, and replacing it means
adding one adapter, not rewriting the factory.

## Phase 2 as built

```
                    ┌──────────────────────────────────────────┐
  operator ───────▶ │  CLI  `seolead …`   (primary interface)  │
                    │  API  127.0.0.1:8100 (X-Internal-Key)    │
                    └───────────────────┬──────────────────────┘
                                        │
┌───────────────────────────────────────▼───────────────────────────────────┐
│  seolead_api                                    network: seolead_backend  │
│                                                                           │
│   ┌─────────────────────────────────────────────────────────────────┐    │
│   │  PIPELINE  (inline; no queue, no broker — one operator, one job) │    │
│   │                                                                  │    │
│   │  seed query                                                      │    │
│   │      ↓  classify_intent          deterministic, vertical config  │    │
│   │  ResearchProvider ──────────────────────────────▶ (port)         │    │
│   │      ↓  normalize                10 source states preserved      │    │
│   │  ResearchPackage                 DETERMINISTIC — no LLM          │    │
│   │      ↓                           provenance fixed here           │    │
│   │  ContentBrief                    HYBRID:                         │    │
│   │      │                             facts/sources/cautions = code │    │
│   │      │                             title/outline       = LLM opt │    │
│   │      ↓  LLMProvider ────────────────────────────▶ (port)         │    │
│   │  ContentDraft                    LLM required; no fallback       │    │
│   │      ↓                                                           │    │
│   │  QA  ├─ deterministic  ── BLOCKS ────────────────────────┐       │    │
│   │      └─ LLM advisory   ── never blocks                   │       │    │
│   │      ↓                                                   │       │    │
│   │  Approval = PENDING              ← a human, always       │       │    │
│   └─────────────────────────────────────────────────────────┼───────┘    │
│                                                             │            │
│   ports: ResearchProvider · LLMProvider                     │            │
└──────────┬──────────────────────────────┬───────────────────┴────────────┘
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

## Layer separation

The mission requires AI reasoning to be separable from deterministic automation.
Concretely:

| Layer | Owns | Never does |
|---|---|---|
| Orchestration (`services/pipeline.py`) | order, retries, idempotency, persistence, state | judge content |
| Reasoning (`providers/llm/`) | synthesis, drafting, advisory review | trigger a side effect, decide a gate |
| External I/O (`providers/research/`) | talking to the outside | schedule, judge |
| Human gate (`services/approval_service.py`) | the publish decision | read a QA result |

The rule that keeps it honest: **an LLM never causes a side effect directly.** It
returns a proposal; deterministic code validates, applies policy and persists.

`approval_service.py` imports nothing from QA, and a test asserts it — the moment
it can see QA, "QA passed, therefore approved" is one line away.

## Where determinism is non-negotiable

Provenance. `package_builder.py` never calls a model. If an LLM assembled the
package, the guarantee that every fact traces to a retrieved source would rest on a
model's good behaviour instead of on code.

Consequences visible in the data model:
- `ck_research_evidence_observability` — no claim can be stored without saying how
  much is known about it.
- `ck_research_source_state` — the ten upstream states, no eleventh.
- `published_at` nullable and never back-filled.
- `uq_approval_draft` — one approval history per draft, so a rejection cannot be
  papered over by a second row.

## Multi-vertical

`config/verticals/<code>.yaml` carries languages, audience, objective, CTA options,
preferred content types, restricted claims, forbidden phrases and the classification
vocabulary. `vertical` in the database carries identity only.

Adding AI_TRAINING_FR = one YAML file + one row. No Python.

`tests/test_multi_vertical.py` runs the same code path over SOLAR_BE and a
deliberately unrelated TEST_GENERIC profile that shares no market, language,
vocabulary or restricted claims. If someone writes `if vertical == "SOLAR_BE"`,
those tests fail.

One subtlety found while building: `market_terms` is separate from `local_terms`.
"Belgique" is the market's own name, and treating it as a locality made *every*
Belgian query classify as LOCAL intent — which routed the whole vertical to the
wrong content type and the wrong CTA.

## Idempotency

`sha256(normalized_query | market | language | YYYY-MM-DD)[:64]`, enforced by
`uq_research_run_idempotency`.

| Situation | Behaviour |
|---|---|
| Same query, same day | reuse the run and the package; a note says so |
| Same query, next day | new run — research goes stale |
| Case/spacing/accent variants | same seed (normalized) |
| Re-run after reuse | new brief, same package |

Deliberately day-scoped: re-running twice in an afternoon should not pay twice;
re-running next week should get fresh observations.

## Status vocabularies

Explicit columns, never inferred from a nullable timestamp.

```
ResearchRun   PENDING → RUNNING → SUCCEEDED | PARTIAL | FAILED
Content       BRIEF_CREATED → DRAFT_CREATED → QA_PASSED | QA_FAILED
                            → PENDING_APPROVAL → APPROVED | REJECTED | NEEDS_REVISION
Approval      PENDING → APPROVED | REJECTED | NEEDS_REVISION
              APPROVED and REJECTED are terminal
```

`PARTIAL` is its own status because "some sources could not be observed" is neither
success nor failure, and flattening it either way would lose the distinction the
whole evidence model depends on.

## Deliberately absent

| Not built | Why |
|---|---|
| Redis / Celery | one operator, one job. A broker would carry no weight. |
| Public route | the API approves content and triggers spend |
| Website, simulator | Phase 5 |
| Prospect 360 writes | Phase 6; contract documented only |
| n8n workflow | deferred; app orchestration is simpler and testable |
| SERP / keyword metrics | no provider exists; inventing volume data is forbidden |
| Hermes integration | read-only, another product's stack; pattern adopted, coupling not |

## Known architectural gaps

1. **No topical relevance check.** A Hacker News post about a racing-game mod was
   scored as a supported fact for a solar query. QA catches the symptom
   (`REQUIRED_FACTS_UNUSED`) but nothing scores query↔fact relevance. Phase 3.
2. **No embeddings yet.** `pgvector` is available in the engine but unused; needed
   for clustering and near-duplicate detection.
3. **Advisory QA is unproven against a real model.** Exercised only with a stub.
4. **One provider per port.** The registries are simple `if` statements; they
   become tables when a second implementation lands.
