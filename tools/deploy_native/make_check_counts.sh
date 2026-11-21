#!/usr/bin/env bash
# Usage: make_check_counts.sh nba_full_counts_<TS>.txt > check_counts.sql
# Builds the count check (psql -v schema=nba_stage) from the "public.<table> <rows>" lines counted in the dump.
set -euo pipefail
echo '-- Compare row counts in schema :schema with the counts in the local dump. Errors out on any mismatch.'
echo '\set ON_ERROR_STOP 1'
echo 'CREATE TEMP TABLE expected (t text PRIMARY KEY, n bigint);'
echo 'INSERT INTO expected VALUES'
awk '{sub(/^public\./, "", $1); printf "%s  (%c%s%c, %s)", (NR > 1 ? ",\n" : ""), 39, $1, 39, $2}' "$1"; echo ';'
cat <<'EOF'
CREATE TEMP TABLE cmp AS
SELECT e.t, e.n AS expected,
       (xpath('/row/n/text()', query_to_xml(format('SELECT count(*) AS n FROM %I.%I', :'schema', e.t), false, true, '')))[1]::text::bigint AS actual
FROM expected e
WHERE to_regclass(format('%I.%I', :'schema', e.t)) IS NOT NULL;
SELECT t, expected, actual, expected = actual AS ok FROM cmp ORDER BY t;
SELECT (SELECT count(*) FROM cmp WHERE expected = actual) = 18
   AND (SELECT count(*) FROM pg_tables WHERE schemaname = :'schema' AND tablename LIKE 'nba\_%') = 18 AS all_ok \gset
\if :all_ok
\echo 'COUNTS OK: 18 tables, every count matches local'
\else
\echo 'COUNT MISMATCH: stop here'
SELECT 1/0;
\endif
EOF
