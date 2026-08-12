# Runbook — running the pipeline

Everything here runs on the VPS. Nothing needs a domain, DNS, TLS, Search Console
or an LLM credential.

## First-time setup

```bash
cd /opt/seolead

# 1. Database and least-privilege role inside the EXISTING PostgreSQL engine.
#    Idempotent. Writes the URL to .env (mode 600) without printing the password.
./scripts/create_database.sh

# 2. Prove the privilege claims rather than trusting them.
./scripts/verify_db_privileges.sh

# 3. Generate the internal API key. Do NOT leave the .env.example placeholder.
python3 - <<'PY'
import pathlib, re, secrets
p = pathlib.Path(".env"); t = p.read_text()
t = re.sub(r"^SEOLEAD_INTERNAL_API_KEY=.*$",
           f"SEOLEAD_INTERNAL_API_KEY={secrets.token_hex(32)}", t, flags=re.M)
p.write_text(t)
print("generated (not printed)")
PY
chmod 600 .env

# 4. Apply migrations. From the host, platform_postgres is on loopback, so the
#    container hostname in .env has to be swapped for 127.0.0.1.
HOSTURL=$(sed -n 's|^SEOLEAD_DATABASE_URL=\(.*\)|\1|p' .env | sed 's|@platform_postgres:|@127.0.0.1:|')
SEOLEAD_DATABASE_URL="$HOSTURL" .venv/bin/python -m alembic upgrade head

# 5. Build and start.
docker compose build
docker compose up -d

# 6. Seed the vertical and a placeholder site (no domain).
docker exec seolead_api seolead seed
```

## Health

```bash
curl -s http://127.0.0.1:8100/health
curl -s http://127.0.0.1:8100/ready | python3 -m json.tool
docker exec seolead_api seolead health
```

`/ready` returns 503 unless the database answers **and** the research runner is
reachable. A missing LLM key is reported as a capability, not a fault — the
pipeline is designed to run without one.

## Running research

```bash
docker exec seolead_api seolead research run \
  --vertical SOLAR_BE \
  --query "prix panneaux solaires Belgique" \
  --market BE --language fr
```

Returns every artefact id as JSON. Exit codes: `0` complete, `2` ran correctly but
stopped at a gate (no LLM, or QA failed), `1` error.

Stop early when you only want research:

```bash
docker exec seolead_api seolead research run --vertical SOLAR_BE \
  --query "..." --stop-after package
```

### Via the API instead

```bash
curl -s -X POST http://127.0.0.1:8100/internal/v1/research-jobs \
  -H "X-Internal-Key: $(sed -n 's/^SEOLEAD_INTERNAL_API_KEY=//p' .env)" \
  -H 'Content-Type: application/json' \
  -d '{"vertical":"SOLAR_BE","query":"prix panneaux solaires Belgique",
       "market":"BE","language":"fr"}' | python3 -m json.tool
```

## Inspecting output

```bash
docker exec seolead_api seolead package show <research_package_id>
docker exec seolead_api seolead brief   show <content_brief_id>
docker exec seolead_api seolead draft   show <draft_id> --body
```

Read `confidence_summary` on the package first. It tells you how much was actually
observed:

| Field | Meaning |
|---|---|
| `source_types_with_items` | sources that actually returned something |
| `source_types_clean_empty` | completed cleanly and found nothing (`no-results`) |
| `source_types_degraded` | **could not be observed** — absence here proves nothing |
| `source_types_unconfigured` | never queried; no API key |
| `partial_observation` | `true` ⇒ do not read gaps as absence |

## Approving content

```bash
docker exec seolead_api seolead content pending
docker exec seolead_api seolead content approve <draft-id> --by "Reda" --note "ok"
docker exec seolead_api seolead content reject  <draft-id> --by "Reda"
docker exec seolead_api seolead content request-revision <draft-id> --by "Reda"
```

`APPROVED` and `REJECTED` are terminal. Reopening means `NEEDS_REVISION`, which is
a deliberate decision that leaves the previous state in the record.

**QA success is never approval.** A draft that passes QA sits at `PENDING` until a
person decides, and the deciding actor is recorded.

## Tests

```bash
.venv/bin/python -m pytest -q          # no credentials, no network
```

## Shutdown and rollback

```bash
docker compose stop                    # stop, keep data
docker compose down                    # remove containers, keep volumes and DB
docker compose down -v                 # ALSO deletes the runner's memory volume

# Roll the schema back one revision:
SEOLEAD_DATABASE_URL="$HOSTURL" .venv/bin/python -m alembic downgrade -1
```

To remove the database entirely (destructive, and it touches a shared engine — be
certain):

```bash
docker exec -i platform_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
DROP DATABASE seolead;
DROP ROLE seolead_app;
SQL
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `/ready` 503, `database.ok:false` | wrong URL, or the container cannot reach `platform_postgres` | confirm `seolead_api` is on `techformanord_backend` |
| `/ready` 503, `research_provider.ok:false` | runner down | `docker compose logs seolead_last30days` |
| every `/internal` route returns 503 | `SEOLEAD_INTERNAL_API_KEY` unset | set it and restart — it fails closed by design |
| `LLM_NOT_CONFIGURED` | no key | expected; package and brief are still persisted |
| `grounding: no-results` on every query | no `SERPER_API_KEY` / `TAVILY_API_KEY` | expected today — see `docs/providers/LAST30DAYS.md` |
| research reuses an old run | same query/market/language, same day | intended; change the query or wait a day |
| `alembic` cannot resolve `platform_postgres` | running from the host | swap the host for `127.0.0.1` as in step 4 |

## Residual risk worth knowing

`acquisition_platform` allows `PUBLIC` to CONNECT — a PostgreSQL default this
project deliberately did **not** change, because changing it modifies another
team's production database. So `seolead_app` can open a connection to it. It holds
**zero privileges on every table there**, verified by
`scripts/verify_db_privileges.sh` against the real catalogue. Closing the
connection right itself is a change for the platform owner to make.
