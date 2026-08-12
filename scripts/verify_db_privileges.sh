#!/usr/bin/env bash
#
# Prove the least-privilege claims rather than asserting them.
#
# Checks, in order:
#   1. seolead_app is not a superuser and cannot create databases or roles.
#   2. seolead_app can connect to `seolead` and create a table there.
#   3. seolead_app holds NO privilege on any Prospect 360 table.
#
# Check 3 is the important one. `acquisition_platform` still allows PUBLIC to
# CONNECT (a PostgreSQL default that this project deliberately did not change,
# because changing it is a production modification to another team's database).
# So the meaningful guarantee is not "cannot connect" — it is "can connect and
# still cannot read anything", which this verifies against real tables.
#
# Read-only. Creates and drops one temporary table inside `seolead` only.
set -euo pipefail

PG_CONTAINER="${PG_CONTAINER:-platform_postgres}"
DB_NAME="${SEOLEAD_DB_NAME:-seolead}"
DB_ROLE="${SEOLEAD_DB_ROLE:-seolead_app}"

psql_super() {
  docker exec -i "$PG_CONTAINER" \
    sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -tA'
}

fail=0
check() {
  local label="$1" expected="$2" actual="$3"
  if [[ "$actual" == "$expected" ]]; then
    printf '  PASS  %s\n' "$label"
  else
    printf '  FAIL  %s (expected %q, got %q)\n' "$label" "$expected" "$actual"
    fail=1
  fi
}

echo "Role attributes:"
# Booleans concatenated with `||` render as 'true'/'false', not 't'/'f'.
attrs=$(printf "SELECT rolsuper||'/'||rolcreatedb||'/'||rolcreaterole||'/'||rolreplication FROM pg_roles WHERE rolname='%s';\n" "$DB_ROLE" | psql_super)
check "not superuser / no createdb / no createrole / no replication" "false/false/false/false" "$attrs"

echo
echo "Ownership:"
owner=$(printf "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='%s';\n" "$DB_NAME" | psql_super)
check "database '$DB_NAME' is owned by $DB_ROLE" "$DB_ROLE" "$owner"

echo
echo "Privileges on Prospect 360 tables (expect 0 for every mode):"
for mode in SELECT INSERT UPDATE DELETE; do
  count=$(printf "SELECT count(*) FROM information_schema.tables t WHERE t.table_schema='public' AND has_table_privilege('%s', quote_ident(t.table_schema)||'.'||quote_ident(t.table_name), '%s');\n" "$DB_ROLE" "$mode" | psql_super)
  check "no $mode on any acquisition_platform public table" "0" "$count"
done

echo
echo "Write access inside its own database:"
own=$(docker exec -i "$PG_CONTAINER" sh -c "psql -U \$POSTGRES_USER -d $DB_NAME -v ON_ERROR_STOP=1 -tA" <<SQL
SET ROLE $DB_ROLE;
CREATE TEMP TABLE _seolead_privilege_probe(x int);
INSERT INTO _seolead_privilege_probe VALUES (1);
SELECT count(*) FROM _seolead_privilege_probe;
SQL
)
check "can create and write a table in '$DB_NAME'" "1" "$(printf '%s' "$own" | tail -1)"

echo
if [[ "$fail" == "0" ]]; then
  echo "All privilege checks passed."
else
  echo "PRIVILEGE CHECKS FAILED — do not proceed."
fi
exit "$fail"
