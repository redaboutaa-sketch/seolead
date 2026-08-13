# Runbook — deploying monprojetsolaire.be

Everything in the repository is ready. This runbook is the deliberate act that
makes the hostname live, and it is separate from ordinary deployment for exactly
that reason.

**Making the site reachable does not make it indexable.** After this runbook the
domain answers over HTTPS and every page still says `noindex`. Indexing is a
separate owner decision, described at the end.

---

## 0. Preconditions

```bash
dig +short @1.1.1.1 monprojetsolaire.be A        # expect 76.13.44.177
dig +short @1.1.1.1 www.monprojetsolaire.be A    # expect 76.13.44.177
```

If either is empty or different, **stop** and finish
`docs/runbooks/MONPROJETSOLAIRE_DNS.md`. Applying the overlay with wrong DNS
consumes Let's Encrypt failure budget on both hostnames.

Also confirm the site is healthy locally:

```bash
curl -s http://127.0.0.1:3100/robots.txt      # expect: Disallow: /
docker ps --filter name=seolead_web --format '{{.Status}}'
```

---

## 1. Apply the routing overlay

```bash
cd /opt/seolead
docker compose \
  -f docker-compose.yml \
  -f infra/traefik/docker-compose.public.yml \
  up -d seolead_web
```

This joins `seolead_web` to the existing `traefik-public` network and adds the
router labels. It creates no Traefik instance, touches no other application, and
modifies nothing in `/opt/traefik`.

`127.0.0.1:3100` stays bound for operator diagnostics.

## 2. Watch the certificate being issued

```bash
docker logs -f traefik 2>&1 | grep -iE "monprojetsolaire|acme|certificate"
```

Issuance normally completes in under a minute. Two hostnames means two
certificates.

## 3. Verify

```bash
# HTTP redirects to HTTPS (global entrypoint redirect)
curl -sI http://monprojetsolaire.be | head -1          # expect 301/308
curl -sI http://monprojetsolaire.be | grep -i location # expect https://

# apex serves the site
curl -sI https://monprojetsolaire.be | head -1         # expect 200

# certificate is valid and for the right name
echo | openssl s_client -connect monprojetsolaire.be:443 \
  -servername monprojetsolaire.be 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates

# www redirects permanently to the apex
curl -sI https://www.monprojetsolaire.be | head -1     # expect 301
curl -sI https://www.monprojetsolaire.be | grep -i location

# the indexing gate is still shut — all three mechanisms
curl -s  https://monprojetsolaire.be/robots.txt        # expect: Disallow: /
curl -sI https://monprojetsolaire.be | grep -i x-robots-tag
curl -s  https://monprojetsolaire.be | grep -o 'name="robots" content="[^"]*"'

# sitemap contains no URLs
curl -s https://monprojetsolaire.be/sitemap.xml

# the staged price page is still NOT on the public route
curl -sI https://monprojetsolaire.be/prix-panneaux-solaires-belgique | head -1
#   expect 404 — it is APPROVED and STAGED, not PUBLISHED
```

## 4. Owner validation

The staged page is reachable through the preview path with the preview token, or
locally over the SSH tunnel:

```bash
ssh -L 3100:127.0.0.1:3100 <user>@<vps>
open http://localhost:3100/preview/fr/prix-panneaux-solaires-belgique
```

---

## Rolling back

```bash
cd /opt/seolead
docker compose up -d --force-recreate seolead_web
```

The base compose file carries no Traefik labels and does not join
`traefik-public`, so recreating from it alone removes the public route. Issued
certificates remain in Traefik's `acme.json` and are reused if you re-apply.

---

## Later, and separately: enabling indexing

This is **not** part of deployment. It requires three coordinated changes, and it
is close to irreversible in the sense that matters — once a page is indexed, its
having been indexed is a fact about the internet.

1. `config/sites/solar_be.yaml`: `staging: false` **and**
   `seo.allow_indexing: true`. The validator refuses either alone in a way that
   would produce an inconsistent state.
2. Rebuild `seolead_web` with `SEOLEAD_ALLOW_INDEXING=true` so the fail-closed
   `X-Robots-Tag` header stops being emitted.
3. Remove the `X-Robots-Tag` custom response header from
   `infra/traefik/docker-compose.public.yml` and re-apply.

Then, and only then, publish content:

```bash
seolead content publish <content-id> --site solar_be
```

Publishing is per page and still refuses while the site is not indexable, so the
order above cannot be short-circuited.

**Search Console, sitemap submission, IndexNow and GA4 remain out of scope until
the owner asks for them.**
