-- Prod: ESPN team ids behind the 2027 D1 membership bug. One transaction; every step asserts first.
--
-- ESPN group 50 (D1) for 2027 lists Boston College (103), Boston University (104), New Haven (2441),
-- West Florida (2697) and Southern Indiana (88). On prod, 103 is attached to Boston University and the
-- other four ids have no TeamExternalId, so sync_team_season_membership gave BU a D1 row through BC's
-- id and marked BC, New Haven, West Florida and Southern Indiana non-D1 (derived_games). Local was
-- fixed on 2026-11-12 (Task 6c mappings + Task 6f.1 ids); this applies only the mappings to prod.
-- Historical BC/BU game attribution on prod is NOT touched here (prod history merge).
--
-- Run (prod): docker compose exec -T db psql -U cbb_user -d cbb_analytics -v ON_ERROR_STOP=1 \
--               -v final=ROLLBACK < backend/data_fixes/2026-11-24_prod_espn_ids_2027_membership.sql
--             then the same with -v final=COMMIT.
\set QUIET on
BEGIN;

DO $$ BEGIN
  IF (SELECT count(*) FROM core_team WHERE slug IN
        ('boston-college', 'boston-university', 'new-haven', 'west-florida', 'southern-indiana')) <> 5
    THEN RAISE EXCEPTION 'expected the five team slugs'; END IF;
  IF (SELECT count(*) FROM core_teamexternalid e JOIN core_team t ON t.id = e.team_id
        WHERE e.source = 'espn' AND e.external_id = '103') <> 1
     OR (SELECT t.slug FROM core_teamexternalid e JOIN core_team t ON t.id = e.team_id
        WHERE e.source = 'espn' AND e.external_id = '103') <> 'boston-university'
    THEN RAISE EXCEPTION 'ESPN 103 is not on boston-university (already fixed?)'; END IF;
  IF EXISTS (SELECT 1 FROM core_teamexternalid e JOIN core_team t ON t.id = e.team_id WHERE e.source = 'espn'
        AND (t.slug IN ('boston-college', 'new-haven', 'west-florida', 'southern-indiana')
             OR e.external_id IN ('104', '2441', '2697', '88')))
    THEN RAISE EXCEPTION 'unexpected existing ESPN mapping for the target teams or ids'; END IF;
END $$;

-- 103 back to Boston College (frees BU's one ESPN row: unique team+source)
UPDATE core_teamexternalid
   SET team_id = (SELECT id FROM core_team WHERE slug = 'boston-college'),
       external_name = 'Boston College', confidence = 1.0, is_manual_override = true, updated_at = now()
 WHERE source = 'espn' AND external_id = '103';

INSERT INTO core_teamexternalid
       (source, external_id, external_name, confidence, is_manual_override, created_at, updated_at, team_id)
SELECT 'espn', x.eid, x.ename, 1.0, true, now(), now(), t.id
  FROM (VALUES ('104',  'Boston University', 'boston-university'),
               ('2441', 'New Haven',         'new-haven'),
               ('2697', 'West Florida',      'west-florida'),
               ('88',   'Southern Indiana',  'southern-indiana')) x(eid, ename, slug)
  JOIN core_team t ON t.slug = x.slug;

DO $$ BEGIN
  IF (SELECT count(*) FROM core_teamexternalid e JOIN core_team t ON t.id = e.team_id WHERE e.source = 'espn'
        AND (e.external_id, t.slug) IN (('103', 'boston-college'), ('104', 'boston-university'),
             ('2441', 'new-haven'), ('2697', 'west-florida'), ('88', 'southern-indiana'))) <> 5
    THEN RAISE EXCEPTION 'mappings not as expected after the fix'; END IF;
END $$;

\set QUIET off
SELECT e.external_id AS espn_id, t.slug, e.external_name FROM core_teamexternalid e JOIN core_team t ON t.id = e.team_id
 WHERE e.source = 'espn' AND e.external_id IN ('103', '104', '2441', '2697', '88') ORDER BY t.slug;
:final;
