# Runbook — previewing the site

## Reach the staging site

```bash
# on the VPS
curl -s http://127.0.0.1:3100/robots.txt        # expect: Disallow: /

# from a workstation
ssh -L 3100:127.0.0.1:3100 <user>@<vps>
open http://localhost:3100
```

## Review a draft that is not approved

```bash
seolead content list --status PENDING            # shows the gate per draft
seolead site preview-draft <draft-id>            # the DTO, writes nothing
```

In a browser: `http://localhost:3100/preview/draft/<draft-id>`

The banner names every remaining blocker. Viewing changes nothing.

## Review a staged page

```bash
seolead site preview <slug> --locale fr
```

Browser: `http://localhost:3100/preview/fr/<slug>`

## If a preview returns 404

| Cause | Check |
|---|---|
| `SEOLEAD_SITE_PREVIEW_TOKEN` unset | `seolead credentials` → `SITE_PREVIEW` |
| nothing staged at that address | `seolead content list --status APPROVED` |
| the site row is missing | `seolead site seed --site solar_be` |

## Restart

```bash
docker compose up -d seolead_web
docker compose logs --tail 50 seolead_web
```
