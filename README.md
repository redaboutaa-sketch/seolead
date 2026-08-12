# SEO Lead Factory

Workspace: `/opt/seolead`. All documentation, architecture, configuration and source code
for this project live here and nowhere else.

## Status

**Discovery phase.** No product code yet. The product definition is still open — see the
open questions at the end of [`docs/discovery/VPS_DISCOVERY.md`](docs/discovery/VPS_DISCOVERY.md).

## Contents

- `docs/discovery/VPS_DISCOVERY.md` — read-only survey of the host: Traefik routing, ports,
  data stores, existing applications, Prospect 360, n8n, provisioned credentials.
- `docs/architecture/` — empty, awaiting the product definition.
- `config/`, `src/` — empty scaffolding.

## Boundaries

Read-only on this VPS during discovery, and not to be modified by this project:
TechFormaNord, Prospect 360, Last30Days, existing Hermes services, existing n8n workflows,
Traefik configuration, and any production Docker service.

This project keeps its own `.env` under `/opt/seolead` and does not read or write
`/opt/techformanord/.env`.

## Environment facts that constrain design

- Traefik v3.2 owns 80/443 with `exposedbydefault=false`; a routed service must join the
  external `traefik-public` network and set `traefik.enable=true`. No new host ports.
- 4 CPU / 15 GiB RAM with swap ~95% consumed across 39 containers — size new services
  conservatively and set explicit memory limits.
- Free loopback ports start at 8100.
- `platform_postgres` (pgvector) already holds `prospects`, `companies`, `events`,
  `consent_records` and the rest of the sales model.
- n8n is deployed but holds only one inactive placeholder workflow.
