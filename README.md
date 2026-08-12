# Prospect 360 SEO Lead Factory

A reusable, multi-vertical engine that turns a search intent into an
evidence-backed, human-approved content asset — and, in later phases, into an
attributable qualified lead.

Workspace: `/opt/seolead`. All documentation, architecture, configuration and code
live here and nowhere else.

## Status — Phase 3 implementation complete, waiting for credentials

```
seed query → provider policy → DataForSEO (SERP) + Tavily (web research)
           → RELEVANCE GATE → source quality × claim risk
           → ResearchPackage V2 → Opportunity Score → ContentBrief
           → OpenAI draft → factual QA → SEO QA → HUMAN APPROVAL
```

Everything is built and tested against mock transports. **No external provider
credential is configured, so no live run has happened.** See
`PHASE3_IMPLEMENTATION_REPORT.md` and `docs/runbooks/PROVIDER_CREDENTIALS.md`.

The headline change is the **relevance gate**. Phase 2's live run offered a Hacker
News post about a racing-game mod as the sole evidence for a Belgian solar pricing
query, because nothing asked whether a source was about the query. It now does —
and the trap is subtler than it looks, because "prix" appears in "Grand Prix".
`docs/RELEVANCE_GATE.md` explains the fix.

No website, no domain, no simulator, no Prospect 360 writes. Those are Phases 5–6.

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
| [`PHASE3_IMPLEMENTATION_REPORT.md`](PHASE3_IMPLEMENTATION_REPORT.md) | Phase 3 — search intelligence, relevance gate, credential gate |
| [`docs/RELEVANCE_GATE.md`](docs/RELEVANCE_GATE.md) | The Phase 2 failure and how it is fixed |
| [`docs/RESEARCH_PACKAGE_V2.md`](docs/RESEARCH_PACKAGE_V2.md) | Evidence assembly, eligibility, traceability |
| [`docs/SEO_OPPORTUNITY_SCORE.md`](docs/SEO_OPPORTUNITY_SCORE.md) | Scoring, and why unknown never becomes zero |
| [`docs/providers/DATAFORSEO.md`](docs/providers/DATAFORSEO.md) | SERP contract, search context, cost |
| [`docs/providers/TAVILY.md`](docs/providers/TAVILY.md) | Web research contract, dates, scores |
| [`docs/providers/OPENAI.md`](docs/providers/OPENAI.md) | The live writer and what it may touch |
| [`docs/providers/LAST30DAYS.md`](docs/providers/LAST30DAYS.md) | Community research, and what it actually returns |
| [`docs/runbooks/LIVE_RESEARCH.md`](docs/runbooks/LIVE_RESEARCH.md) | Running a live job and reading the result |
| [`docs/runbooks/PROVIDER_CREDENTIALS.md`](docs/runbooks/PROVIDER_CREDENTIALS.md) | Adding credentials without ever echoing them |
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
source is a blocking QA failure. A HIGH-risk claim — a subsidy, a tax rate, a legal
obligation, a guarantee — additionally needs an official or institutional source,
not merely any source.

**Relevance, quality and risk are three separate questions.** A forum thread can be
perfectly relevant and a poor authority for a tax rate; a government page can be
authoritative and off-topic. Ranking is not authority: nothing in source
classification can see a SERP position.

## Boundaries

Read-only and never modified by this project: Prospect 360, TechFormaNord,
ChainPilot, the existing Hermes gateway, existing n8n workflows, Traefik.

This project keeps its own `.env` and never reads `/opt/techformanord/.env`.
