# Last30Days research provider

## Relationship to the ChainPilot instance

Two runners now exist on this host. They share an engine and nothing else.

| | ChainPilot | SEO Lead Factory |
|---|---|---|
| Container | `last30days_runner` (defined, never started) | `seolead_last30days` |
| Compose | `/opt/l30d-build/docker-compose.last30days.yml` | `/opt/seolead/docker-compose.yml` |
| Image | `chainpilot/last30days-runner:<ref>` | `seolead/last30days-runner:<ref>` |
| Network | `chainpilot_network` | `seolead_backend` |
| Volume | `last30days_memory` | `seolead_last30days_memory` |
| Engine commit | `52f53312ff2f272e16bbc1785e1c04f9d9c19b31` | same |
| API keys | ChainPilot's `.env` | `/opt/seolead/.env` |

**Nothing belonging to ChainPilot was modified, started or read at runtime.** Two
files were copied at build time; see `infra/last30days/PROVENANCE.md` for the
checksums and the reasoning.

No mutable state is shared. Separate volumes are not a formality: the engine keeps
a memory directory, and two engines writing to one directory would make either
one's results unexplainable.

## What it actually is — measured, not assumed

Phase 1 left one open question: does the `web` source expose SERP structure usable
for SEO? **It was run and the answer is no.**

Three real probes against engine `3.18.4` at the pinned commit:

| Topic | Sources requested | Result |
|---|---|---|
| `prix panneaux solaires Belgique` | web, reddit, youtube, hackernews | `grounding: no-results`, `reddit: partial` (0 items), `youtube: skipped-unconfigured`, `hackernews: ok` (1 item — a post about a racing-game mod) |
| `solar panel cost Belgium` | web | `grounding: no-results`, 0 results |
| `AI agents` | web, hackernews | `grounding: unreachable`, `hackernews: ok` — **12 relevant results** |

Four conclusions, all load-bearing for Phase 3:

1. **The engine renames `web` to `grounding`.** The runner's whitelist (pinned
   from an older engine) accepts `web`; engine 3.18.4 reports the outcome under
   `grounding`. The normalizer handles this because it reads whatever source names
   the report contains rather than assuming the requested set.

2. **`grounding` does not work without a paid key.** `SERPER_API_KEY` and
   `TAVILY_API_KEY` are unset, and the source returns `no-results` or
   `unreachable` accordingly. Note the inconsistency between those two outcomes
   for the same configuration — `no-results` is the more misleading of the pair,
   because it claims a clean empty answer where the truth is that the source could
   not be used.

3. **It returns no SERP structure at all.** No ranked results, no People Also Ask,
   no SERP features. It is not, and does not try to be, a keyword or SERP tool.

4. **It is a tech-community discussion engine.** It works well on English technical
   topics via Hacker News, and returns nothing useful for French-language consumer
   commercial queries.

### What this means

Last30Days is **not** a viable primary research provider for the Solar Belgium
pilot. It stays wired in as the first `ResearchProvider` implementation, and it
proved the whole contract end to end, but Phase 3 needs a real search provider
before content generation on this vertical is worth doing.

This is a finding, not a failure. The pipeline behaved exactly as designed: it
retrieved almost nothing, said so honestly in `confidence_summary`, marked the one
irrelevant fact as supported-but-present, and would have been blocked by QA
(`REQUIRED_FACTS_UNUSED`) had a draft been generated from it.

**Known limitation:** nothing yet checks that a retrieved fact is *topically
relevant* to the query. A racing-game post scored as a supported fact. QA catches
the downstream symptom, not the cause. See Phase 3 recommendations.

## Wire contract

```
POST http://seolead_last30days:8080/v1/research
Idempotency-Key: sha256(normalized_query|market|language|YYYY-MM-DD)[:64]
X-Correlation-Id: <correlation id>
X-Requested-By: seolead

{ "topic": str(3..300), "sources": [...], "window_days": 1..30,
  "verify_freshness": true, "max_results": 1..1000, "correlation_id": str }
```

Response envelope: `run_id`, `correlation_id`, `engine_version`, `engine_commit`,
`runner_version`, `duration_ms`, `warnings[]`, `report{}`, `idempotent_replay`.

Also `GET /healthz`, `GET /readyz`, `GET /doctor`.

**No authentication.** The runner publishes no port and lives on
`seolead_backend`; network isolation is the entire access-control story. It must
never be exposed through Traefik or bound to a host port.

## Source states — the rule that matters

The engine reports one of ten states per source. They are preserved distinctly all
the way into the database (`ck_research_source_state` enforces the vocabulary).

| State | Meaning | Counted as |
|---|---|---|
| `ok` | completed, produced items | observation |
| `partial` | completed with degradation, may produce items | observation |
| `no-results` | **completed cleanly, found nothing** | the only clean empty |
| `rate-limited` / `auth-failed` / `unreachable` / `timeout` / `schema-drift` / `error` | could not be observed | non-observation |
| `skipped-unconfigured` | never queried — no key | not attempted |

> Only `no-results` means a source completed cleanly with zero matches.

Everything else that produced nothing is a gap in *our knowledge*, not a fact
about the world. Collapsing `auth-failed` into "no discussion found" would let a
missing API key become a published claim.

`partial` deserves a note: the real run showed `reddit: partial` with **zero
items**. A state that permits items does not guarantee items, so
`confidence_summary.source_types_with_items` counts sources that actually returned
something.

## Contract versioning

Major `1` required; minor ≥ `2` (`candidate_id` arrived in 1.2 and freshness
verdicts join on it); unknown fields ignored; a different major is refused and
never retried, because a retry cannot change the engine's version.

## Freshness → observability

| Verdict | Observability | Why |
|---|---|---|
| `current` + dated | `OBSERVED` | retrieved, dated, checked |
| `stale` | `ESTIMATED` | real but out of date |
| no verdict, no `published_at` | `ESTIMATED` | seen, but cannot be placed in time |
| `contradicted` | `UNKNOWN` | actively checked and refuted |
| `unsupported` | `UNKNOWN` | checked and could not be stood up |

`published_at` is **never** back-filled. Upstream omits unknown fields rather than
nulling them, and a manufactured date is worse than an absent one.

## Operating limits

`L30D_MAX_CONCURRENT_RUNS=1` (below ChainPilot's 2 — this host runs 40 containers),
`L30D_TIMEOUT_SECONDS=600`, output cap 64 MiB, in-memory idempotency cache of 256
entries. Durable idempotency is the `uq_research_run_idempotency` constraint in our
database, not the runner's cache.

Measured footprint: ~40 MiB RSS idle against a 768 MiB limit; a research call takes
3–6 s wall clock.
