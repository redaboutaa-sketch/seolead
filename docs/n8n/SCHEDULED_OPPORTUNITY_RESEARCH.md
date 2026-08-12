# Future n8n workflow — Scheduled Opportunity Research

**Status: DESIGN ONLY. Deferred to a later phase. Nothing was deployed, and the
production n8n instance was not modified.**

## Why it is deferred

Phase 1 verified the production n8n holds exactly one workflow, named
"My workflow", and it is inactive. There is therefore no existing convention to
inherit, and `docs/ai-sales/N8N_MIGRATION_MATRIX.md` in the platform tree suggests
automation was deliberately migrated *out* of n8n into Celery.

Phase 2 uses application code instead, for three reasons: workflow logic in n8n is
not unit-testable, not code-reviewable, and not stored in `/opt/seolead` — which
the mission requires for everything belonging to this project.

## Where n8n would genuinely earn its place

Not orchestration — **notification and human routing**. The approval queue is the
one place where a visual editor beats code, because the business owner may want to
change who gets notified and how without a deploy.

## Proposed workflow

```
┌─────────────┐
│  Schedule   │  cron, e.g. weekly
└──────┬──────┘
       │
┌──────▼──────────────────────────────────────────────┐
│  HTTP Request → SEO Lead Factory internal API       │
│  POST http://seolead_api:8000/internal/v1/research-jobs
│  Header: X-Internal-Key: {{$credentials.seolead}}   │
│  Body:  {"vertical":"SOLAR_BE","query":"...",       │
│          "market":"BE","language":"fr"}             │
└──────┬──────────────────────────────────────────────┘
       │  response carries every artefact id
┌──────▼──────────────────────────────────────────────┐
│  Switch on `stopped_at` / `error_code`              │
├─────────────────────────────────────────────────────┤
│  approval + qa PASSED  → notify: draft ready        │
│  approval + QA_FAILED  → notify: blocking issues    │
│  LLM_NOT_CONFIGURED    → notify: package ready only │
│  research failed       → alert operator             │
└──────┬──────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────┐
│  Notify (email / Slack) with the draft id and the   │
│  approval command:                                  │
│    seolead content approve <draft-id> --by "<name>" │
└─────────────────────────────────────────────────────┘
```

## Prerequisites before this can be built

1. **Network.** `platform_n8n` is on `techformanord_backend`, `techformanord_frontend`,
   `techformanord_n8n-internal` and `traefik-public`. `seolead_api` is on
   `seolead_backend` and `techformanord_backend`. They already share
   `techformanord_backend`, so `http://seolead_api:8000` is reachable — but relying
   on that couples us to another stack's network. Prefer attaching n8n to
   `seolead_backend`, which is a change to the platform's compose and therefore an
   owner decision.
2. **Credential.** `SEOLEAD_INTERNAL_API_KEY` stored as an n8n credential, never
   inline in a node.
3. **Isolation.** A separate workflow, clearly named (`seolead-scheduled-research`),
   touching no existing workflow. The instance is effectively empty, so the risk is
   low — but "low" is not "zero" and this is production.
4. **Owner decision.** Whether n8n is adopted at all, or whether a cron entry
   calling the CLI is sufficient. For a weekly job, cron is simpler and stays in
   this repository.

## Hard constraints

- n8n must **never** hold business logic. It schedules and notifies; the API does
  the work.
- n8n must **never** hold database credentials. It has no access to the `seolead`
  database and does not need any.
- The existing `POST /webhooks/n8n/{slug}` endpoint on the Prospect 360 API is an
  unauthenticated stub that logs and discards. It is not part of this design.

## The simpler alternative, recommended for now

```cron
0 7 * * 1  docker exec seolead_api seolead research run \
             --vertical SOLAR_BE --query "prix panneaux solaires Belgique" \
             --market BE --language fr >> /var/log/seolead-research.log 2>&1
```

Version-controlled, testable, no new dependency, no production change. Revisit n8n
when a human actually needs to edit the notification flow.
