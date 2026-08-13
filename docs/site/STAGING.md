# Staging

## What is deployed

`seolead_web` — Next.js standalone, bound to **127.0.0.1:3100 only**. No Traefik
label, no public hostname. Traefik configuration was not touched.

## Domain state (2026-08-13) — LIVE, and not indexable

`https://monprojetsolaire.be` is reachable over HTTPS and remains entirely
non-indexable. Those are two different things, and keeping them apart is the point.

| Item | State |
|---|---|
| domain | `monprojetsolaire.be` |
| canonical origin | `https://monprojetsolaire.be` |
| DNS | delegated to `dns-parking.com`; apex + www → this VPS, A and AAAA |
| Traefik routing | **applied** — `infra/traefik/docker-compose.public.yml` |
| TLS | Let's Encrypt, both hostnames, valid to 2026-11-11 |
| www | 308 permanent → apex |
| indexable | **no** — `staging: true`, `allow_indexing: false` |
| publication | `allow_publication: true` — published pages are served |
| price page | **PUBLISHED** 2026-08-13, `noindex` retained, public route 200 |

The routing lives in a separate overlay so a routine `docker compose up -d` cannot
publish the site. Re-applying it is the documented act in
`docs/runbooks/MONPROJETSOLAIRE_DEPLOYMENT.md`.

### Preview access on a public hostname

`/preview/*` is behind HTTP Basic auth at Traefik. The application's preview token
authenticates the *server* to the API and says nothing about who holds the browser;
on loopback that was harmless, on a public domain it would have served unpublished
content to anyone who guessed the path.

- public: `https://monprojetsolaire.be/preview/...` — credentials required
- operator: `http://127.0.0.1:3100/preview/...` over the SSH tunnel — no credentials

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

**Publishability** — may a page be served at its real URL?

1. `domain` set — ✅ done
2. `seo.allow_publication: true` — ✅ done (owner decision, 2026-08-13)
3. per page: `seolead content publish <content-id>` — ✅ done for the price page only

**Indexability** — may a crawler keep it?

1. `domain` set — ✅ done
2. `staging: false` — *no*
3. `seo.allow_indexing: true` — *no*
4. `SEOLEAD_ALLOW_INDEXING=true` at build time, removing the fail-closed
   `X-Robots-Tag` — *no*

The three gates are independent. The site currently serves one published page at
its real URL while remaining entirely non-indexable — a soft launch. Opening the
publication gate did not touch the indexing gate, and a page published under it
keeps `noindex`.

## What must NOT be done before that decision

- adding a DNS record
- adding a Traefik router or label
- setting `allow_indexing: true`
- submitting a sitemap to Search Console
- publishing content in bulk
