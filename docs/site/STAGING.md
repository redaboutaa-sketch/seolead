# Staging

## What is deployed

`seolead_web` — Next.js standalone, bound to **127.0.0.1:3100 only**. No Traefik
label, no public hostname. Traefik configuration was not touched.

## Domain state (2026-08-13)

The production domain `monprojetsolaire.be` is **configured but not routed**.

| Item | State |
|---|---|
| domain in `SiteConfig` | `monprojetsolaire.be` |
| canonical origin | `https://monprojetsolaire.be` |
| DNS | **not delegated** — no NS, no SOA, no A/AAAA |
| Traefik routing | prepared in `infra/traefik/docker-compose.public.yml`, **not applied** |
| TLS certificate | not requested |
| indexable | **no** — `staging: true`, `allow_indexing: false` |

The routing lives in a separate overlay so that a routine `docker compose up -d`
cannot publish the site. Applying it is the deliberate act described in
`docs/runbooks/MONPROJETSOLAIRE_DEPLOYMENT.md`, and it is blocked on DNS
(`docs/runbooks/MONPROJETSOLAIRE_DNS.md`).

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

## Two different gates, deliberately separate

**Reachability** — can a browser load the site?

1. DNS pointing at this host — *pending*
2. the Traefik overlay applied — *prepared, not applied*
3. a certificate issued — *not requested*

**Indexability** — may a crawler keep it?

1. `domain` set — ✅ done
2. `staging: false` — *no*
3. `seo.allow_indexing: true` — *no*
4. `SEOLEAD_ALLOW_INDEXING=true` at build time, removing the fail-closed
   `X-Robots-Tag` — *no*
5. per page: `seolead content publish <content-id>` — *not called*

Completing the first gate does **not** touch the second. The site can be publicly
reachable for owner validation while remaining entirely non-indexable, which is
exactly the current target state.

## What must NOT be done before that decision

- adding a DNS record
- adding a Traefik router or label
- setting `allow_indexing: true`
- submitting a sitemap to Search Console
- publishing content in bulk
