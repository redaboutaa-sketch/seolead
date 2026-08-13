# Staging

## What is deployed

`seolead_web` — Next.js standalone, bound to **127.0.0.1:3100 only**. No Traefik
label, no public hostname, no DNS record. Traefik configuration was not touched.

## Reaching it

From the VPS:

```bash
curl -s http://127.0.0.1:3100/robots.txt          # expect: Disallow: /
```

From a workstation, over SSH:

```bash
ssh -L 3100:127.0.0.1:3100 <user>@<vps>
# then open http://localhost:3100
```

## Two secrets, two purposes

| Variable | Gates |
|---|---|
| `SEOLEAD_INTERNAL_API_KEY` | every factory API call, including paid research |
| `SEOLEAD_SITE_PREVIEW_TOKEN` | unpublished content only |

They are separate because the preview token is shared with whoever reviews a page,
which is a wider audience than whoever may trigger spend. Unset preview token ⇒
the preview routes refuse to serve rather than falling back to open.

Neither reaches the browser. `web/lib/api.ts` imports `server-only`, so a client
component that tried to read them fails the build.

## Making the site public — the gate

Publication requires **all** of:

1. `domain` set in `config/sites/solar_be.yaml`
2. `staging: false`
3. `seo.allow_indexing: true`
4. a Traefik route (a deliberate, separately-approved change)
5. per page: `seolead content publish <content-id>`

Steps 1–3 are refused in combination by the config validator unless they are
coherent; step 4 has not been made and must not be made without the owner's
decision.

## What must NOT be done before that decision

- adding a DNS record
- adding a Traefik router or label
- setting `allow_indexing: true`
- submitting a sitemap to Search Console
- publishing content in bulk
