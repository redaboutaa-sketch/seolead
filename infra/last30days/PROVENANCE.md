# Vendored Last30Days runner — provenance

`runner/app.py` and `requirements.txt` in this directory are **byte-identical
copies** of files owned by the ChainPilot/OntoAlpha project. They were copied, not
edited, so that the copy can be verified against the source at any time.

## Source

| File | Copied from | SHA-256 |
|---|---|---|
| `runner/app.py` | `/opt/l30d-build/services/last30days_runner/app.py` | `795b349f43797facf751795f0a66da69f937bf72958590cb0e3c908819082eb3` |
| `requirements.txt` | `/opt/l30d-build/infra/last30days/requirements.txt` | `43a7fbd08516290fc4582a04c457fdd7595e643608201250f773e58e1ff0ee99` |

Copied on 2026-08-12. Verify with:

```bash
diff /opt/l30d-build/services/last30days_runner/app.py \
     /opt/seolead/infra/last30days/runner/app.py
sha256sum -c <<<'795b349f43797facf751795f0a66da69f937bf72958590cb0e3c908819082eb3  infra/last30days/runner/app.py'
```

## Why copied rather than referenced

Owner Decision 2 requires a **second, isolated** runtime that must not modify or
depend on the ChainPilot one. Two options existed:

1. Point a Docker build context at `/opt/l30d-build`. Rejected: it makes this
   project's build depend on another team's working tree. A change there would
   silently change what we build, and a `docker compose build` here would read
   files we do not own.

2. Vendor the two files and own the Dockerfile. Chosen. The isolation is total,
   the copy is verifiable, and the *real* reuse — the research engine itself — is
   preserved exactly, because our Dockerfile fetches the same upstream engine at
   the same pinned commit.

"Prefer reuse over duplication" is honoured where it counts: the engine is
identical, the wire contract is identical, and the security posture is identical.
What is duplicated is 357 lines of well-written wrapper, which is a smaller cost
than a cross-project build dependency.

## What is NOT copied

- `docker-compose.last30days.yml` — our compose service is written fresh with our
  own names, network and volume. Copying it would have carried ChainPilot's
  network name and `COMPOSE_FILE` conventions into this project.
- The engine itself — fetched from GitHub at build time, pinned to commit
  `52f53312ff2f272e16bbc1785e1c04f9d9c19b31`, exactly as upstream does.

## Divergence policy

Do not edit these files in place. If a change is genuinely needed:

1. Record why here.
2. Update the checksum table.
3. Note that the copy is no longer verifiable against upstream.

Until then, an upstream security fix can be adopted by re-copying and re-checking.
