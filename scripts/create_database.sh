#!/usr/bin/env bash
#
# Create the dedicated `seolead` database and least-privilege `seolead_app` role
# inside the EXISTING PostgreSQL engine (container `platform_postgres`).
#
# Owner Decision 3: no new PostgreSQL container. This script therefore touches a
# shared engine, and everything it does is additive and scoped:
#
#   * It creates one role and one database. It alters no existing role, database,
#     schema or table.
#   * It does NOT revoke PUBLIC CONNECT on `acquisition_platform`. Doing so would
#     be a production change to another team's database. The residual is documented
#     in docs/runbooks/LOCAL_PIPELINE.md and verified by scripts/verify_db_privileges.sh:
#     `seolead_app` can open a connection to that database but holds no privilege
#     on any object in it.
#   * The generated password is written to ./.env (git-ignored) and is never
#     echoed, never passed as a command-line argument (it would appear in `ps`),
#     and never written to a shell history file. It reaches psql on stdin.
#
# Safe to re-run: existing role and database are detected and left alone.
#
# Usage:  ./scripts/create_database.sh
set -euo pipefail

PG_CONTAINER="${PG_CONTAINER:-platform_postgres}"
DB_NAME="${SEOLEAD_DB_NAME:-seolead}"
DB_ROLE="${SEOLEAD_DB_ROLE:-seolead_app}"
ENV_FILE="${ENV_FILE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.env}"

log() { printf '%s\n' "$*" >&2; }

if ! docker ps --format '{{.Names}}' | grep -qx "$PG_CONTAINER"; then
  log "ERROR: container '$PG_CONTAINER' is not running."
  exit 1
fi

psql_super() {
  # -v ON_ERROR_STOP=1 so a failed statement aborts instead of continuing.
  docker exec -i "$PG_CONTAINER" \
    sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -tA'
}

role_exists() {
  printf "SELECT 1 FROM pg_roles WHERE rolname = '%s';\n" "$DB_ROLE" \
    | psql_super | grep -q 1
}

db_exists() {
  printf "SELECT 1 FROM pg_database WHERE datname = '%s';\n" "$DB_NAME" \
    | psql_super | grep -q 1
}

# ── Password ─────────────────────────────────────────────────────────────────
# Reuse the one already in .env if present, so re-running does not orphan the
# application's credential.
DB_PASSWORD=""
if [[ -f "$ENV_FILE" ]] && grep -q '^SEOLEAD_DATABASE_URL=' "$ENV_FILE"; then
  DB_PASSWORD="$(sed -n 's|^SEOLEAD_DATABASE_URL=postgresql+asyncpg://[^:]*:\([^@]*\)@.*|\1|p' "$ENV_FILE")"
fi
if [[ -z "$DB_PASSWORD" ]]; then
  DB_PASSWORD="$(openssl rand -base64 33 | tr -d '/+=\n' | cut -c1-40)"
  GENERATED=1
fi

# ── Role ─────────────────────────────────────────────────────────────────────
if role_exists; then
  log "role '$DB_ROLE' already exists — leaving its password untouched."
else
  log "creating role '$DB_ROLE' (LOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE)..."
  # Password travels on stdin only. Server-side statement logging is off
  # (log_statement=none, verified during discovery), so it does not reach a log.
  printf "CREATE ROLE %s WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '%s';\n" \
    "$DB_ROLE" "$DB_PASSWORD" | psql_super > /dev/null
fi

# ── Database ─────────────────────────────────────────────────────────────────
if db_exists; then
  log "database '$DB_NAME' already exists."
else
  log "creating database '$DB_NAME' owned by '$DB_ROLE'..."
  printf "CREATE DATABASE %s OWNER %s;\n" "$DB_NAME" "$DB_ROLE" | psql_super > /dev/null
fi

# Nobody but the owner gets in. This is scoped to the new database only.
log "revoking PUBLIC CONNECT on '$DB_NAME'..."
printf "REVOKE ALL ON DATABASE %s FROM PUBLIC;\nGRANT CONNECT, TEMPORARY ON DATABASE %s TO %s;\n" \
  "$DB_NAME" "$DB_NAME" "$DB_ROLE" | psql_super > /dev/null

# ── .env ─────────────────────────────────────────────────────────────────────
if [[ "${GENERATED:-0}" == "1" ]]; then
  umask 077
  if [[ ! -f "$ENV_FILE" ]]; then
    cp "$(dirname "$ENV_FILE")/.env.example" "$ENV_FILE"
    log "created $ENV_FILE from .env.example"
  fi
  # In-place, without ever printing the value.
  python3 - "$ENV_FILE" "$DB_ROLE" "$DB_PASSWORD" "$DB_NAME" <<'PY'
import sys, pathlib, re
path, role, password, db = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
url = f"postgresql+asyncpg://{role}:{password}@platform_postgres:5432/{db}"
text = path.read_text(encoding="utf-8")
if re.search(r"^SEOLEAD_DATABASE_URL=", text, re.M):
    text = re.sub(r"^SEOLEAD_DATABASE_URL=.*$", f"SEOLEAD_DATABASE_URL={url}",
                  text, flags=re.M)
else:
    text += f"\nSEOLEAD_DATABASE_URL={url}\n"
path.write_text(text, encoding="utf-8")
PY
  chmod 600 "$ENV_FILE"
  log "database URL written to $ENV_FILE (mode 600). The password was not printed."
fi

log ""
log "done. database=$DB_NAME role=$DB_ROLE"
log "next: ./scripts/verify_db_privileges.sh, then alembic upgrade head"
