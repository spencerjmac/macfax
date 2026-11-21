-- Post-swap checks (read-only).
SET default_transaction_read_only = on;
\pset footer off
\echo '== schemas'
SELECT nspname, (SELECT count(*) FROM pg_tables t WHERE t.schemaname = n.nspname) AS tables
FROM pg_namespace n WHERE nspname IN ('public', 'nba_stage', 'nba_old', 'nba_failed') ORDER BY 1;
\echo '== migrations'
SELECT app, max(name) FROM django_migrations WHERE app = 'nba' GROUP BY app;
\echo '== sequences ahead of max(id) (every row must be ok)'
SELECT 'SELECT t, max_id, seq, called, CASE WHEN called THEN seq >= max_id ELSE seq > max_id END AS ok FROM ('
       || string_agg(format('SELECT %L AS t, (SELECT coalesce(max(id), 0) FROM public.%I) AS max_id, '
                            'last_value AS seq, is_called AS called FROM %s',
                            c.relname, c.relname, pg_get_serial_sequence(format('public.%I', c.relname), 'id')),
                     ' UNION ALL ' ORDER BY c.relname) || ') q ORDER BY t'
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname LIKE 'nba\_%' \gexec
\echo '== NBA per season'
SELECT s.year,
       (SELECT count(*) FROM nba_nbagame g WHERE g.season_id = s.id) AS games,
       (SELECT count(*) FROM nba_nbaplayergamestint t JOIN nba_nbagame g ON g.id = t.game_id WHERE g.season_id = s.id) AS stints,
       count(p.id) FILTER (WHERE p.season_type = 'regular') AS reg,
       count(p.id) FILTER (WHERE p.bpr_model = 'native-1') AS native,
       count(p.id) FILTER (WHERE p.obpr_raw IS NOT NULL) AS raw,
       count(p.id) FILTER (WHERE p.season_type = 'regular' AND p.baseline_obpr IS NOT NULL) AS rapm,
       count(p.id) FILTER (WHERE p.season_type = 'regular' AND p.projection_value IS NOT NULL) AS pv,
       count(p.id) FILTER (WHERE p.season_type = 'playoffs' AND (p.box_bpr IS NOT NULL OR coalesce(p.nba_archetype, '') <> '')) AS po_box,
       (SELECT count(*) FROM nba_nbaseasonratingscale r WHERE r.season_id = s.id) AS scale
FROM nba_nbaseason s LEFT JOIN nba_nbaplayerseasonstats p ON p.season_id = s.id
GROUP BY s.id, s.year ORDER BY s.year;
\echo '== players with career BPR'
SELECT count(*), count(*) FILTER (WHERE career_bpr IS NOT NULL) AS with_career FROM nba_nbaplayer;
\echo '== 2027 top 10 (minutes >= 18 x team games)'
WITH tg AS (SELECT t.id AS team_id, count(*) AS g FROM nba_nbateam t JOIN nba_nbagame x ON (x.home_team_id = t.id OR x.away_team_id = t.id)
            JOIN nba_nbaseason s ON s.id = x.season_id WHERE s.year = 2027 AND x.status = 'Final' AND x.counts_toward_regular_season GROUP BY 1)
SELECT pl.name, t.abbreviation, round(p.bpr::numeric, 2) AS bpr, round((p.mpg * p.gp)::numeric) AS minutes
FROM nba_nbaplayerseasonstats p JOIN nba_nbaseason s ON s.id = p.season_id JOIN nba_nbaplayer pl ON pl.id = p.player_id
JOIN nba_nbateam t ON t.id = p.team_id JOIN tg ON tg.team_id = p.team_id
WHERE s.year = 2027 AND p.season_type = 'regular' AND p.mpg * p.gp >= 18 * tg.g AND p.bpr IS NOT NULL
ORDER BY p.bpr DESC LIMIT 10;
\echo '== non-NBA tables (compare with the pre-swap snapshot: must be identical)'
SELECT string_agg(format('SELECT %L AS t, count(*) AS n FROM public.%I', c.relname, c.relname), ' UNION ALL ' ORDER BY c.relname) || ' ORDER BY t'
FROM pg_class c JOIN pg_namespace s ON s.oid = c.relnamespace
WHERE s.nspname = 'public' AND c.relkind = 'r' AND c.relname NOT LIKE 'nba\_%' \gexec
