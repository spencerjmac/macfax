-- Step P9a: ANALYZE every nba_stage table while the site is still up, so the swapped-in tables
-- have planner statistics from their first query. Writes only statistics for nba_stage.
-- Run: $PSQL -f - < backups/analyze_stage.sql > backups/analyze_stage_$TS.log 2>&1; echo rc=$?
-- Errors out unless all 18 nba_stage tables were analyzed.
\set ON_ERROR_STOP 1
\timing on
SELECT now() AS started;
SELECT format('ANALYZE VERBOSE nba_stage.%I', tablename) FROM pg_tables
WHERE schemaname = 'nba_stage' ORDER BY tablename \gexec
\timing off
SELECT relname AS table, n_live_tup AS est_rows, last_analyze
FROM pg_stat_user_tables WHERE schemaname = 'nba_stage' ORDER BY relname;
SELECT count(*) FILTER (WHERE last_analyze IS NOT NULL) AS analyzed,
       count(*) FILTER (WHERE last_analyze IS NOT NULL) = 18 AND count(*) = 18 AS analyze_ok
FROM pg_stat_user_tables WHERE schemaname = 'nba_stage' \gset
\if :analyze_ok
\echo 'ANALYZE OK: 18 nba_stage tables analyzed'
\else
\echo 'ANALYZE INCOMPLETE: ' :analyzed ' of 18 nba_stage tables: stop here'
SELECT 1/0;
\endif
