-- P7: nba_stage's tables and columns must match public's nba_* exactly. Reads the catalog only
-- (two temporary views, so it cannot run in a read-only transaction).
-- Compared per column: name, type (with modifiers), NOT NULL, identity and default
-- (with the schema name taken out of sequence defaults). Errors out on any difference.
-- Column order is listed too but does not fail the check: Django names every column.
\set ON_ERROR_STOP 1
\pset footer off
CREATE TEMP VIEW cols AS
SELECT n.nspname AS sch, c.relname AS t, a.attname AS col,
       row_number() OVER (PARTITION BY c.oid ORDER BY a.attnum) AS pos,
       format_type(a.atttypid, a.atttypmod) AS type, a.attnotnull AS notnull, a.attidentity AS ident,
       replace(coalesce(pg_get_expr(d.adbin, d.adrelid), ''), n.nspname || '.', '') AS dflt
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
WHERE n.nspname IN ('public', 'nba_stage') AND c.relkind = 'r' AND c.relname LIKE 'nba\_%'
  AND a.attnum > 0 AND NOT a.attisdropped;
CREATE TEMP VIEW diff AS
SELECT coalesce(p.t, s.t) AS t, coalesce(p.col, s.col) AS col,
       p.type AS public_type, s.type AS stage_type, p.notnull AS public_notnull, s.notnull AS stage_notnull,
       p.ident AS public_ident, s.ident AS stage_ident, p.dflt AS public_default, s.dflt AS stage_default
FROM (SELECT * FROM cols WHERE sch = 'public') p
FULL JOIN (SELECT * FROM cols WHERE sch = 'nba_stage') s ON s.t = p.t AND s.col = p.col
WHERE p.col IS NULL OR s.col IS NULL
   OR (p.type, p.notnull, p.ident, p.dflt) IS DISTINCT FROM (s.type, s.notnull, s.ident, s.dflt);
\echo '== tables and columns per schema'
SELECT sch, count(DISTINCT t) AS tables, count(*) AS columns FROM cols GROUP BY sch ORDER BY sch;
\echo '== column differences (must be empty)'
SELECT * FROM diff ORDER BY t, col;
\echo '== column order differences (informational)'
SELECT p.t, p.col, p.pos AS public_pos, s.pos AS stage_pos
FROM cols p JOIN cols s ON s.t = p.t AND s.col = p.col AND s.sch = 'nba_stage'
WHERE p.sch = 'public' AND p.pos <> s.pos ORDER BY 1, 3;
SELECT (SELECT count(*) FROM diff) = 0
   AND (SELECT count(DISTINCT t) FROM cols WHERE sch = 'public') = 18
   AND (SELECT count(DISTINCT t) FROM cols WHERE sch = 'nba_stage') = 18 AS cols_ok \gset
\if :cols_ok
\echo 'COLUMNS OK: 18 tables, every column matches public'
\else
\echo 'COLUMN MISMATCH: stop here'
SELECT 1/0;
\endif
