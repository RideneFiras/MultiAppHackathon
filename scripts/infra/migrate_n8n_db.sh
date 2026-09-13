#!/usr/bin/env bash
# Runs inside a postgres:18 container in Azure.
# Copies n8n's schema + data from Neon (schema public) into Supabase (schema n8n, which PostgREST does not expose).
set -euo pipefail
: "${SRC_URL:?}" "${DST_URL:?}"
export PGCONNECT_TIMEOUT=30
q() { psql "$1" -X -At -v ON_ERROR_STOP=1 -c "$2"; }

echo "== source (neon):          $(q "$SRC_URL" 'show server_version')"
echo "== destination (supabase): $(q "$DST_URL" 'show server_version')"

existing=$(q "$DST_URL" "select count(*) from information_schema.tables where table_schema='n8n'")
if [ "$existing" != "0" ]; then echo "ABORT: destination schema n8n already has $existing tables"; exit 3; fi

echo "== dump + restore in ONE transaction (any error rolls back everything)"
q "$DST_URL" "create schema if not exists n8n" >/dev/null
pg_dump "$SRC_URL" --schema=public --no-owner --no-privileges --no-comments --no-publications --no-subscriptions --format=plain \
  | perl -ne 'if ($in) { print; $in = 0 if $_ eq "\\.\n"; next }
              next if /^SET transaction_timeout/ || /^CREATE SCHEMA public;/;
              if (/^COPY /) { s/\bpublic\./n8n./g; print; $in = 1; next }
              s/\bpublic\./n8n./g; print' \
  | psql "$DST_URL" -X -q -v ON_ERROR_STOP=1 --single-transaction
echo "== restore committed"

echo "== row-count verification, every table"
tmpl=$(q "$SRC_URL" "select string_agg(format('select %L as t, count(*) as n from __S__.%I', table_name, table_name), ' union all ') from information_schema.tables where table_schema='public' and table_type='BASE TABLE'")
src=$(psql "$SRC_URL" -X -At -F'|' -v ON_ERROR_STOP=1 -c "${tmpl//__S__/public} order by 1")
dst=$(psql "$DST_URL" -X -At -F'|' -v ON_ERROR_STOP=1 -c "${tmpl//__S__/n8n} order by 1")
ntab=$(printf '%s\n' "$src" | wc -l)
nrows=$(printf '%s\n' "$src" | awk -F'|' '{s+=$2} END {print s}')
if [ "$src" != "$dst" ]; then
  echo "MISMATCH:"
  diff <(printf '%s\n' "$src") <(printf '%s\n' "$dst") || true
  exit 4
fi
echo "== all $ntab tables match ($nrows rows)"

echo "== lock schema n8n away from Supabase's public API roles"
psql "$DST_URL" -X -q -v ON_ERROR_STOP=1 -c "revoke all on schema n8n from public, anon, authenticated" \
  -c "revoke all on all tables in schema n8n from public, anon, authenticated" \
  -c "revoke all on all sequences in schema n8n from public, anon, authenticated" \
  -c "revoke all on all functions in schema n8n from public, anon, authenticated"
echo "MIGRATION_OK"
