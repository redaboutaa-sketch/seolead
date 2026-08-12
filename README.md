# Prospect 360 SEO Lead Factory

A reusable, multi-vertical engine that turns a search intent into an
evidence-backed, human-approved content asset — and, in later phases, into an
attributable qualified lead.

Workspace: `/opt/seolead`. All documentation, architecture, configuration and code
live here and nowhere else.

## Status — Phase 2 complete

The foundation and the first automated research pipeline are built and running.

```
seed query → ResearchProvider → ResearchPackage → ContentBrief
           → LLM draft → QA → HUMAN APPROVAL
```

No website, no domain, no simulator, no Prospect 360 writes. Those are Phases 5–6.

**Read `PHASE2_IMPLEMENTATION_REPORT.md` first.** It contains one finding that
changes the plan: the Last30Days engine returns no SERP structure and cannot serve
the Solar Belgium vertical without a paid search key. Phase 3 needs a real search
provider.

## Quick start

```bash
cd /opt/seolead
./scripts/create_database.sh          # dedicated DB + least-privilege role
./scripts/verify_db_privileges.sh     # prove the privilege claims
# generate SEOLEAD_INTERNAL_API_KEY into .env — see the runbook
docker compose build && docker compose up -d
docker exec seolead_api seolead seed

docker exec seolead_api seolead research run \
  --vertical SOLAR_BE --query "prix panneaux solaires Belgique" \
  --market BE --language fr
```

Full instructions: [`docs/runbooks/LOCAL_PIPELINE.md`](docs/runbooks/LOCAL_PIPELINE.md).

## Documentation

| Document | What it covers |
|---|---|
| [`SEO_LEAD_FACTORY_DISCOVERY_REPORT.md`](SEO_LEAD_FACTORY_DISCOVERY_REPORT.md) | Phase 1 — infrastructure, Prospect 360, Last30Days, Hermes, n8n, Traefik |
| [`PHASE2_IMPLEMENTATION_REPORT.md`](PHASE2_IMPLEMENTATION_REPORT.md) | Phase 2 — what was built, what was measured, what is blocked |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Ports, layer separation, idempotency, known gaps |
| [`docs/PHASE2_IMPLEMENTATION.md`](docs/PHASE2_IMPLEMENTATION.md) | Design decisions and their reasoning |
| [`docs/providers/LAST30DAYS.md`](docs/providers/LAST30DAYS.md) | The research provider, and what it actually returns |
| [`docs/providers/LLM_PROVIDERS.md`](docs/providers/LLM_PROVIDERS.md) | LLM abstraction, capability routing, running without a key |
| [`docs/integrations/PROSPECT360_INGEST_CONTRACT.md`](docs/integrations/PROSPECT360_INGEST_CONTRACT.md) | Proposed Phase 6 contract — documentation only |
| [`docs/runbooks/LOCAL_PIPELINE.md`](docs/runbooks/LOCAL_PIPELINE.md) | Setup, running, approving, troubleshooting, rollback |
| [`docs/runbooks/LAST30DAYS_RUNTIME.md`](docs/runbooks/LAST30DAYS_RUNTIME.md) | Build, pin, security posture, diagnostics |
| [`docs/n8n/SCHEDULED_OPPORTUNITY_RESEARCH.md`](docs/n8n/SCHEDULED_OPPORTUNITY_RESEARCH.md) | Future workflow design — deferred |

## Principles

**Evidence before prose.** Every fact carries `OBSERVED` / `ESTIMATED` / `UNKNOWN`,
enforced by a database constraint. A publication date that is unknown stays
unknown; nothing is back-filled.

**A gap in observation is not a fact about the world.** The ten Last30Days source
states are preserved distinctly. Only `no-results` means a source completed cleanly
with nothing to report — the other nine are gaps in our knowledge.

**Approval is a human act.** QA success never becomes approval. The approval module
imports nothing from QA, and a test enforces it.

**One engine, many verticals.** Solar Belgium is a YAML profile. Adding a vertical
is a config file and a database row, not a code change — proven by a test suite
that runs the whole pipeline over an unrelated second vertical.

**No invented numbers.** A numeric value in a draft that appears in no retrieved
source is a blocking QA failure.

## Boundaries

Read-only and never modified by this project: Prospect 360, TechFormaNord,
ChainPilot, the existing Hermes gateway, existing n8n workflows, Traefik.

This project keeps its own `.env` and never reads `/opt/techformanord/.env`.
