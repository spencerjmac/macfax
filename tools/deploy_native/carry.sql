-- Carry prod-only NBA values from the live public tables into nba_stage (before the swap).
-- Writes only nba_stage. One transaction: any error leaves nba_stage as loaded.
\set ON_ERROR_STOP 1
\pset footer off
BEGIN;

\echo '== 1. outlook fields entered on prod (text, publish state) that differ from local'
CREATE TEMP TABLE outlook_diff AS
SELECT ns.year, n.id AS stage_id, o.team_slug,
       o.season_headline, o.macfax_take, o.development_spotlight_player, o.development_spotlight_text,
       o.season_defining_variable, o.is_published, o.snapshot_frozen_at,
       n.season_headline AS local_headline, n.is_published AS local_published, n.snapshot_frozen_at AS local_frozen
FROM public.nba_teamseasonoutlook o
JOIN public.nba_nbaseason ps ON ps.id = o.season_id
JOIN nba_stage.nba_nbaseason ns ON ns.year = ps.year
JOIN nba_stage.nba_teamseasonoutlook n ON n.season_id = ns.id AND n.team_slug = o.team_slug
WHERE (o.season_headline, o.macfax_take, o.development_spotlight_player, o.development_spotlight_text,
       o.season_defining_variable, o.is_published, o.snapshot_frozen_at)
      IS DISTINCT FROM
      (n.season_headline, n.macfax_take, n.development_spotlight_player, n.development_spotlight_text,
       n.season_defining_variable, n.is_published, n.snapshot_frozen_at);
SELECT year, team_slug, season_headline, local_headline, is_published, local_published,
       snapshot_frozen_at, local_frozen FROM outlook_diff ORDER BY 1, 2;
UPDATE nba_stage.nba_teamseasonoutlook n
SET season_headline = d.season_headline, macfax_take = d.macfax_take,
    development_spotlight_player = d.development_spotlight_player,
    development_spotlight_text = d.development_spotlight_text,
    season_defining_variable = d.season_defining_variable,
    is_published = d.is_published, snapshot_frozen_at = d.snapshot_frozen_at
FROM outlook_diff d WHERE n.id = d.stage_id;
\echo '   prod outlooks with no local outlook (must be 0):'
SELECT count(*) AS unmatched FROM public.nba_teamseasonoutlook o JOIN public.nba_nbaseason ps ON ps.id = o.season_id
WHERE NOT EXISTS (SELECT 1 FROM nba_stage.nba_teamseasonoutlook n JOIN nba_stage.nba_nbaseason ns ON ns.id = n.season_id
                  WHERE ns.year = ps.year AND n.team_slug = o.team_slug);

\echo '== 2. manual moves on prod missing from local'
WITH ins AS (
  INSERT INTO nba_stage.nba_teamoutseasonmove
        (move_type, player_name, detail, impact_rating, created_at, team_id, round_number, overall_pick,
         mps_score, season_id, source, transaction_date)
  SELECT m.move_type, m.player_name, m.detail, m.impact_rating, m.created_at, nt.id, m.round_number, m.overall_pick,
         m.mps_score, ns.id, m.source, m.transaction_date
  FROM public.nba_teamoutseasonmove m
  JOIN public.nba_nbaseason ps ON ps.id = m.season_id
  JOIN public.nba_teamseasonoutlook po ON po.id = m.team_id
  JOIN nba_stage.nba_nbaseason ns ON ns.year = ps.year
  JOIN nba_stage.nba_teamseasonoutlook nt ON nt.season_id = ns.id AND nt.team_slug = po.team_slug
  WHERE m.source = 'manual'
    AND NOT EXISTS (SELECT 1 FROM nba_stage.nba_teamoutseasonmove x
                    WHERE x.season_id = ns.id AND x.team_id = nt.id AND x.source = 'manual'
                      AND x.move_type = m.move_type AND x.player_name = m.player_name AND x.detail = m.detail)
  RETURNING season_id, team_id, move_type, player_name, detail)
SELECT ns.year, nt.team_slug, ins.move_type, ins.player_name, ins.detail FROM ins
JOIN nba_stage.nba_nbaseason ns ON ns.id = ins.season_id JOIN nba_stage.nba_teamseasonoutlook nt ON nt.id = ins.team_id;

\echo '== 3. injury reports (availability): prod rows missing from local, or newer on prod'
CREATE TEMP TABLE avail AS
SELECT a.*, np.id AS s_player, ns.id AS s_season, nt.id AS s_team
FROM public.nba_nbaplayeravailability a
JOIN public.nba_nbaplayer pp ON pp.id = a.player_id
JOIN public.nba_nbaseason ps ON ps.id = a.season_id
JOIN public.nba_nbateam pt ON pt.id = a.team_id
LEFT JOIN nba_stage.nba_nbaplayer np ON np.player_id = pp.player_id
LEFT JOIN nba_stage.nba_nbaseason ns ON ns.year = ps.year
LEFT JOIN nba_stage.nba_nbateam nt ON nt.nba_team_id = pt.nba_team_id;
SELECT count(*) AS prod_rows, count(*) FILTER (WHERE s_player IS NULL OR s_season IS NULL OR s_team IS NULL) AS unmapped_must_be_0
FROM avail;
WITH up AS (
  INSERT INTO nba_stage.nba_nbaplayeravailability
        (game_date, status, injury_reason, notes, source, report_timestamp, expected_minutes_pct,
         created_at, updated_at, player_id, season_id, team_id)
  SELECT game_date, status, injury_reason, notes, source, report_timestamp, expected_minutes_pct,
         created_at, updated_at, s_player, s_season, s_team
  FROM avail WHERE s_player IS NOT NULL AND s_season IS NOT NULL AND s_team IS NOT NULL
  ON CONFLICT (player_id, game_date, source) DO UPDATE
  SET status = EXCLUDED.status, injury_reason = EXCLUDED.injury_reason, notes = EXCLUDED.notes,
      report_timestamp = EXCLUDED.report_timestamp, expected_minutes_pct = EXCLUDED.expected_minutes_pct,
      updated_at = EXCLUDED.updated_at, team_id = EXCLUDED.team_id, season_id = EXCLUDED.season_id
  WHERE nba_stage.nba_nbaplayeravailability.updated_at < EXCLUDED.updated_at
  RETURNING (xmax = 0) AS inserted)
SELECT count(*) FILTER (WHERE inserted) AS inserted, count(*) FILTER (WHERE NOT inserted) AS updated FROM up;

\echo '== 4. report only: prod games missing from local or different (the catch-up run syncs these)'
SELECT p.game_id, ps.year, p.date, p.status, p.home_score, p.away_score,
       n.status AS local_status, n.home_score AS local_home, n.away_score AS local_away
FROM public.nba_nbagame p JOIN public.nba_nbaseason ps ON ps.id = p.season_id
LEFT JOIN nba_stage.nba_nbagame n ON n.game_id = p.game_id
WHERE n.id IS NULL OR (p.status, p.home_score, p.away_score) IS DISTINCT FROM (n.status, n.home_score, n.away_score)
ORDER BY p.date LIMIT 50;
\echo '   prod players missing from local (must be 0):'
SELECT count(*) AS missing FROM public.nba_nbaplayer p
WHERE NOT EXISTS (SELECT 1 FROM nba_stage.nba_nbaplayer n WHERE n.player_id = p.player_id);

COMMIT;
