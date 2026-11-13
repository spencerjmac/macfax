-- Task 6c: team identity fixes (local macfax DB). One transaction; every step asserts its expected count.
-- Run: psql -d macfax -v ON_ERROR_STOP=1 -v final=ROLLBACK|COMMIT -f fix_team_identity.sql
\set QUIET on
BEGIN;

-- ── Step 2: mappings ─────────────────────────────────────────────────────────────────────────
DO $$ BEGIN
  IF (SELECT count(*) FROM core_teamexternalid WHERE id = 1018 AND source = 'espn' AND external_id = '103' AND team_id = 28) <> 1
    THEN RAISE EXCEPTION 'TeamExternalId 1018 is not espn:103 -> 28'; END IF;
  IF EXISTS (SELECT 1 FROM core_teamexternalid WHERE source = 'espn' AND (team_id IN (27, 779, 791) OR external_id IN ('104','2402','6760','2637','130189')))
    THEN RAISE EXCEPTION 'unexpected existing ESPN mapping for 27/779/791 or 104/2402/6760/2637/130189'; END IF;
  IF EXISTS (SELECT 1 FROM core_team WHERE slug = 'missouri-s-and-t' OR name = 'Missouri S&T') THEN RAISE EXCEPTION 'Missouri S&T exists'; END IF;
  IF (SELECT count(*) FROM core_team WHERE (id, name, is_d1) IN ((779, 'Texas Col.', false), (791, 'VTSU Randolph', false))) <> 2
    THEN RAISE EXCEPTION 'teams 779/791 not as expected'; END IF;
END $$;

UPDATE core_teamexternalid SET team_id = 27, external_name = 'Boston College', confidence = 1.0,
       is_manual_override = true, updated_at = now() WHERE id = 1018;
INSERT INTO core_team (slug, name, aliases, is_d1, created_at) VALUES ('missouri-s-and-t', 'Missouri S&T', '[]'::jsonb, false, now());
INSERT INTO core_teamexternalid (source, external_id, external_name, confidence, is_manual_override, created_at, updated_at, team_id)
SELECT 'espn', x.eid, x.ename, 1.0, true, now(), now(), x.tid FROM (VALUES
  ('104',    'Boston University',        28),
  ('2402',   'Missouri S&T',             (SELECT id FROM core_team WHERE slug = 'missouri-s-and-t')),
  ('2637',   'Texas College',            779),
  ('130189', 'Vermont State - Randolph', 791)) x(eid, ename, tid);
-- ESPN 6760 (also Missouri S&T) goes in mappings/team_alias_overrides.yml: one ESPN row per team.

-- ── Step 3: side map from the raw ESPN competitors (2005-2025 ESPN-sourced games) ─────────────
CREATE TEMP TABLE side_map ON COMMIT DROP AS
SELECT g.id game_id, c->>'homeAway' side, c->'team'->>'id' espn,
       CASE WHEN c->>'homeAway' = 'home' THEN g.home_team_id ELSE g.away_team_id END old_team,
       CASE c->'team'->>'id'
         WHEN '103' THEN 27 WHEN '104' THEN 28
         WHEN '2402' THEN (SELECT id FROM core_team WHERE slug = 'missouri-s-and-t')
         WHEN '6760' THEN (SELECT id FROM core_team WHERE slug = 'missouri-s-and-t')
         WHEN '2637' THEN 779 WHEN '130189' THEN 791 END new_team,
       c->'team'->>'id' IN ('104', '2402', '6760', '2637', '130189') unmapped_side   -- player rows on this side have no team
FROM core_game g, jsonb_array_elements(g.raw_json->'_raw'->'competitions'->0->'competitors') c
WHERE g.season_year <= 2025
  AND ((c->'team'->>'id' IN ('103', '104') AND CASE WHEN c->>'homeAway' = 'home' THEN g.home_team_id ELSE g.away_team_id END = 28)
    OR (c->'team'->>'id' IN ('2402', '6760') AND CASE WHEN c->>'homeAway' = 'home' THEN g.home_team_id ELSE g.away_team_id END = 182)
    OR (c->'team'->>'id' = '2637' AND CASE WHEN c->>'homeAway' = 'home' THEN g.home_team_id ELSE g.away_team_id END = 300)
    OR (c->'team'->>'id' = '130189' AND CASE WHEN c->>'homeAway' = 'home' THEN g.home_team_id ELSE g.away_team_id END = 341));

DO $$ DECLARE n_bc int; n_bu int; n_nd int; n_left int; BEGIN
  SELECT count(*) FILTER (WHERE espn = '103'), count(*) FILTER (WHERE espn = '104'),
         count(*) FILTER (WHERE espn NOT IN ('103', '104')) INTO n_bc, n_bu, n_nd FROM side_map;
  RAISE NOTICE 'side_map: BC sides %, BU sides %, non-D1 sides %', n_bc, n_bu, n_nd;
  IF n_bc <> 672 OR n_bu <> 628 OR n_nd <> 38 THEN RAISE EXCEPTION 'side counts differ (672/628/38 expected)'; END IF;
  -- every 2005-2025 team-28 side is in the map
  SELECT count(*) INTO n_left FROM core_game g CROSS JOIN LATERAL (VALUES ('home', g.home_team_id), ('away', g.away_team_id)) s(side, tid)
   WHERE g.season_year <= 2025 AND s.tid = 28 AND NOT EXISTS (SELECT 1 FROM side_map m WHERE m.game_id = g.id AND m.side = s.side);
  IF n_left <> 0 THEN RAISE EXCEPTION '% team-28 sides not covered by ESPN 103/104', n_left; END IF;
END $$;

-- Per affected game: old and new home/away.
CREATE TEMP TABLE game_map ON COMMIT DROP AS
SELECT g.id game_id, g.home_team_id old_home, g.away_team_id old_away,
       coalesce(h.new_team, g.home_team_id) new_home, coalesce(a.new_team, g.away_team_id) new_away,
       coalesce(h.unmapped_side, false) home_unmapped, coalesce(a.unmapped_side, false) away_unmapped
FROM core_game g LEFT JOIN side_map h ON h.game_id = g.id AND h.side = 'home' LEFT JOIN side_map a ON a.game_id = g.id AND a.side = 'away'
WHERE g.id IN (SELECT game_id FROM side_map);

-- Box rows: side by team id; in self games (home = away) by home_away H/A.
CREATE TEMP TABLE tgs_map ON COMMIT DROP AS
SELECT t.id tgs_id, t.team_id old_team, t.opponent_id old_opp, m.game_id,
       CASE WHEN m.old_home <> m.old_away THEN CASE WHEN t.team_id = m.old_home THEN 'home' WHEN t.team_id = m.old_away THEN 'away' END
            ELSE CASE t.home_away WHEN 'H' THEN 'home' WHEN 'A' THEN 'away' END END side, m.new_home, m.new_away
FROM core_teamgamestats t JOIN game_map m ON m.game_id = t.game_id;

DO $$ DECLARE n_null int; n_self int; BEGIN
  SELECT count(*) INTO n_null FROM tgs_map WHERE side IS NULL;
  IF n_null <> 0 THEN RAISE EXCEPTION '% box rows in affected games have no side', n_null; END IF;
  SELECT count(*) INTO n_self FROM game_map WHERE old_home = old_away;
  RAISE NOTICE 'affected games %, self games %', (SELECT count(*) FROM game_map), n_self;
  IF n_self <> 4 THEN RAISE EXCEPTION 'expected 4 self games, got %', n_self; END IF;
  IF (SELECT count(*) FROM game_map WHERE home_unmapped AND away_unmapped) <> 0 THEN RAISE EXCEPTION 'game with two unmapped sides'; END IF;
END $$;

-- Player rows and stints: team = old team of a changed side -> new; NULL team -> the unmapped side's team.
CREATE TEMP TABLE row_rule ON COMMIT DROP AS
SELECT m.game_id, s.old_team, s.new_team, s.unmapped
FROM game_map m CROSS JOIN LATERAL (VALUES (m.old_home, m.new_home, m.home_unmapped), (m.old_away, m.new_away, m.away_unmapped)) s(old_team, new_team, unmapped)
WHERE m.old_home <> m.old_away;   -- self games handled below (only Missouri St. ones have player rows)

DO $$ DECLARE n_pg_move int; n_pg_null int; n_st_move int; n_st_null int; BEGIN
  SELECT count(*) INTO n_pg_move FROM core_playergamestats p JOIN row_rule r ON r.game_id = p.game_id AND p.team_id = r.old_team AND r.new_team <> r.old_team;
  SELECT count(*) INTO n_pg_null FROM core_playergamestats p JOIN game_map m ON m.game_id = p.game_id WHERE p.team_id IS NULL;
  SELECT count(*) INTO n_st_move FROM core_playergamestint p JOIN row_rule r ON r.game_id = p.game_id AND p.team_id = r.old_team AND r.new_team <> r.old_team;
  SELECT count(*) INTO n_st_null FROM core_playergamestint p JOIN game_map m ON m.game_id = p.game_id WHERE p.team_id IS NULL;
  RAISE NOTICE 'player rows to move %, null player rows to fill %, stints to move %, null stints to fill %', n_pg_move, n_pg_null, n_st_move, n_st_null;
  IF n_pg_move <> 3152 OR n_pg_null <> 3425 + 187 OR n_st_move <> 3845 OR n_st_null <> 309 THEN
    RAISE EXCEPTION 'player/stint counts differ (3152 / 3612 / 3845 / 309 expected)'; END IF;
END $$;

UPDATE core_playergamestats p SET team_id = r.new_team
FROM row_rule r WHERE r.game_id = p.game_id AND p.team_id = r.old_team AND r.new_team <> r.old_team;
UPDATE core_playergamestats p SET team_id = CASE WHEN m.home_unmapped THEN m.new_home ELSE m.new_away END
FROM game_map m WHERE m.game_id = p.game_id AND p.team_id IS NULL AND (m.home_unmapped OR m.away_unmapped);
UPDATE core_playergamestint p SET team_id = r.new_team
FROM row_rule r WHERE r.game_id = p.game_id AND p.team_id = r.old_team AND r.new_team <> r.old_team;
UPDATE core_playergamestint p SET team_id = CASE WHEN m.home_unmapped THEN m.new_home ELSE m.new_away END
FROM game_map m WHERE m.game_id = p.game_id AND p.team_id IS NULL AND (m.home_unmapped OR m.away_unmapped);
UPDATE core_scoringevent e SET scoring_team_id = r.new_team
FROM row_rule r WHERE r.game_id = e.game_id AND e.scoring_team_id = r.old_team AND r.new_team <> r.old_team;
-- core_gamelog has no game id (season/team/date only) and is empty; checked below.

-- Box rows: team and opponent from the row's side.
UPDATE core_teamgamestats t SET team_id = CASE x.side WHEN 'home' THEN x.new_home ELSE x.new_away END,
                                opponent_id = CASE x.side WHEN 'home' THEN x.new_away ELSE x.new_home END, updated_at = now()
FROM tgs_map x WHERE x.tgs_id = t.id
  AND (t.team_id, t.opponent_id) IS DISTINCT FROM (CASE x.side WHEN 'home' THEN x.new_home ELSE x.new_away END,
                                                   CASE x.side WHEN 'home' THEN x.new_away ELSE x.new_home END);
-- Games.
UPDATE core_game g SET home_team_id = m.new_home, away_team_id = m.new_away, updated_at = now()
FROM game_map m WHERE m.game_id = g.id AND (g.home_team_id, g.away_team_id) IS DISTINCT FROM (m.new_home, m.new_away);

DO $$ BEGIN
  IF (SELECT count(*) FROM core_gamelog) <> 0 THEN RAISE EXCEPTION 'core_gamelog not empty; needs its own re-point'; END IF;
  IF EXISTS (SELECT 1 FROM core_game g JOIN game_map m ON m.game_id = g.id WHERE g.home_team_id = g.away_team_id)
    THEN RAISE EXCEPTION 'self games remain'; END IF;
END $$;

\echo 'step 3 box rows changed / games changed:'
SELECT (SELECT count(*) FROM tgs_map WHERE (old_team, old_opp) IS DISTINCT FROM
          (CASE side WHEN 'home' THEN new_home ELSE new_away END, CASE side WHEN 'home' THEN new_away ELSE new_home END)) box_rows_changed,
       (SELECT count(*) FROM game_map WHERE (old_home, old_away) IS DISTINCT FROM (new_home, new_away)) games_changed;
\echo 'former team-28-vs-team-28 games (second box score needs a re-fetch in 6g):'
SELECT g.id, g.season_year, g.source_game_id, g.game_date, h.name home, a.name away, g.home_score, g.away_score,
       (SELECT string_agg(t.team_id || ' vs ' || t.opponent_id || ' (' || t.home_away || ', ' || t.pts || ' pts)', '; ') FROM core_teamgamestats t WHERE t.game_id = g.id) box_rows
FROM core_game g JOIN core_team h ON h.id = g.home_team_id JOIN core_team a ON a.id = g.away_team_id
WHERE g.id IN (SELECT game_id FROM game_map WHERE old_home = old_away) ORDER BY g.id;

-- ── Step 4: Georgia's opponents' box rows (opponent 714 -> 100), 2005-2008 ─────────────────────
CREATE TEMP TABLE georgia_fix ON COMMIT DROP AS
SELECT t.id FROM core_teamgamestats t JOIN core_game g ON g.id = t.game_id
WHERE t.opponent_id = 714 AND t.team_id <> 100 AND g.season_year BETWEEN 2005 AND 2008
  AND 100 IN (g.home_team_id, g.away_team_id) AND 714 NOT IN (g.home_team_id, g.away_team_id);
DO $$ DECLARE n int; BEGIN
  SELECT count(*) INTO n FROM georgia_fix; RAISE NOTICE 'Georgia rows to repoint: %', n;
  IF n <> 123 THEN RAISE EXCEPTION 'Georgia: expected 123 rows, got %', n; END IF;
END $$;
UPDATE core_teamgamestats t SET opponent_id = 100, updated_at = now() FROM georgia_fix f WHERE f.id = t.id;

-- ── Step 5: duplicate games 2012-2013 (same teams, same Eastern date, different ESPN ids) ──────
-- Rule: keep the copy whose two box rows both have FGA > 0; delete the stub copy (box rows with FGA 0)
-- with its box rows. Every pair has exactly one complete copy (asserted).
CREATE TEMP TABLE dup_pairs ON COMMIT DROP AS
WITH g AS (
  SELECT id, season_year, source_game_id sid, least(home_team_id, away_team_id) t1, greatest(home_team_id, away_team_id) t2,
         (((raw_json->>'date')::timestamptz) AT TIME ZONE 'America/New_York')::date ed, home_score, away_score,
         (SELECT count(*) FROM core_teamgamestats t WHERE t.game_id = core_game.id AND t.fga > 0) box_ok
  FROM core_game WHERE season_year IN (2012, 2013))
SELECT a.season_year, a.ed, a.t1, a.t2,
       CASE WHEN a.box_ok = 2 THEN a.id ELSE b.id END keep_id, CASE WHEN a.box_ok = 2 THEN b.id ELSE a.id END drop_id,
       a.box_ok a_ok, b.box_ok b_ok
FROM g a JOIN g b ON a.t1 = b.t1 AND a.t2 = b.t2 AND a.ed = b.ed AND a.id < b.id AND a.sid <> b.sid;
DO $$ DECLARE n int; bad int; BEGIN
  SELECT count(*), count(*) FILTER (WHERE NOT ((a_ok = 2 AND b_ok = 0) OR (a_ok = 0 AND b_ok = 2))) INTO n, bad FROM dup_pairs;
  RAISE NOTICE 'duplicate pairs %, pairs without exactly one complete copy %', n, bad;
  IF n <> 46 OR bad <> 0 THEN RAISE EXCEPTION 'duplicates: expected 46 pairs each with one complete copy'; END IF;
  IF EXISTS (SELECT 1 FROM core_playergamestats WHERE game_id IN (SELECT drop_id FROM dup_pairs))
     OR EXISTS (SELECT 1 FROM core_playergamestint WHERE game_id IN (SELECT drop_id FROM dup_pairs))
     OR EXISTS (SELECT 1 FROM core_scoringevent WHERE game_id IN (SELECT drop_id FROM dup_pairs))
     OR EXISTS (SELECT 1 FROM validation_predictionsnapshot WHERE game_id IN (SELECT drop_id FROM dup_pairs))
     OR EXISTS (SELECT 1 FROM validation_gamevalidationresult WHERE game_id IN (SELECT drop_id FROM dup_pairs))
    THEN RAISE EXCEPTION 'a dropped duplicate has player/stint/event/validation rows'; END IF;
END $$;
\echo 'duplicate pairs (kept / deleted):'
SELECT p.season_year, p.ed, h.name || ' vs ' || w.name teams,
       k.id keep_id, k.source_game_id keep_espn, k.home_score || '-' || k.away_score keep_score,
       d.id drop_id, d.source_game_id drop_espn, d.home_score || '-' || d.away_score drop_score
FROM dup_pairs p JOIN core_game k ON k.id = p.keep_id JOIN core_game d ON d.id = p.drop_id
JOIN core_team h ON h.id = k.home_team_id JOIN core_team w ON w.id = k.away_team_id ORDER BY p.season_year, p.ed, teams;
DELETE FROM core_teamgamestats WHERE game_id IN (SELECT drop_id FROM dup_pairs);
DELETE FROM core_game WHERE id IN (SELECT drop_id FROM dup_pairs);

\echo 'row totals after:'
SELECT 'core_game' t, count(*) n FROM core_game UNION ALL SELECT 'core_teamgamestats', count(*) FROM core_teamgamestats
UNION ALL SELECT 'pgs_null_team', count(*) FROM core_playergamestats WHERE team_id IS NULL
UNION ALL SELECT 'stint_null_team', count(*) FROM core_playergamestint WHERE team_id IS NULL
UNION ALL SELECT 'core_team', count(*) FROM core_team UNION ALL SELECT 'core_teamexternalid', count(*) FROM core_teamexternalid;

:final;
