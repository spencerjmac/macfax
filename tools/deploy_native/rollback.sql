-- Roll back the swap: the swapped-in tables go to schema nba_failed, nba_old comes back to public.
-- Backend, web and scheduler must be stopped.
\set ON_ERROR_STOP 1
BEGIN;
SET LOCAL lock_timeout = '30s';
CREATE SCHEMA nba_failed;
ALTER TABLE public.nba_nbabprmodelartifact SET SCHEMA nba_failed;
ALTER TABLE public.nba_nbagame SET SCHEMA nba_failed;
ALTER TABLE public.nba_nbamodelcalibration SET SCHEMA nba_failed;
ALTER TABLE public.nba_nbaplayer SET SCHEMA nba_failed;
ALTER TABLE public.nba_nbaplayeravailability SET SCHEMA nba_failed;
ALTER TABLE public.nba_nbaplayercontract SET SCHEMA nba_failed;
ALTER TABLE public.nba_nbaplayergamestats SET SCHEMA nba_failed;
ALTER TABLE public.nba_nbaplayergamestint SET SCHEMA nba_failed;
ALTER TABLE public.nba_nbaplayerseasonstats SET SCHEMA nba_failed;
ALTER TABLE public.nba_nbaprojectedrosterslot SET SCHEMA nba_failed;
ALTER TABLE public.nba_nbaseason SET SCHEMA nba_failed;
ALTER TABLE public.nba_nbaseasonratingscale SET SCHEMA nba_failed;
ALTER TABLE public.nba_nbateam SET SCHEMA nba_failed;
ALTER TABLE public.nba_nbateamgamestats SET SCHEMA nba_failed;
ALTER TABLE public.nba_nbateamseasonratings SET SCHEMA nba_failed;
ALTER TABLE public.nba_projectedstarter SET SCHEMA nba_failed;
ALTER TABLE public.nba_teamoutseasonmove SET SCHEMA nba_failed;
ALTER TABLE public.nba_teamseasonoutlook SET SCHEMA nba_failed;
ALTER TABLE nba_old.nba_nbabprmodelartifact SET SCHEMA public;
ALTER TABLE nba_old.nba_nbagame SET SCHEMA public;
ALTER TABLE nba_old.nba_nbamodelcalibration SET SCHEMA public;
ALTER TABLE nba_old.nba_nbaplayer SET SCHEMA public;
ALTER TABLE nba_old.nba_nbaplayeravailability SET SCHEMA public;
ALTER TABLE nba_old.nba_nbaplayercontract SET SCHEMA public;
ALTER TABLE nba_old.nba_nbaplayergamestats SET SCHEMA public;
ALTER TABLE nba_old.nba_nbaplayergamestint SET SCHEMA public;
ALTER TABLE nba_old.nba_nbaplayerseasonstats SET SCHEMA public;
ALTER TABLE nba_old.nba_nbaprojectedrosterslot SET SCHEMA public;
ALTER TABLE nba_old.nba_nbaseason SET SCHEMA public;
ALTER TABLE nba_old.nba_nbaseasonratingscale SET SCHEMA public;
ALTER TABLE nba_old.nba_nbateam SET SCHEMA public;
ALTER TABLE nba_old.nba_nbateamgamestats SET SCHEMA public;
ALTER TABLE nba_old.nba_nbateamseasonratings SET SCHEMA public;
ALTER TABLE nba_old.nba_projectedstarter SET SCHEMA public;
ALTER TABLE nba_old.nba_teamoutseasonmove SET SCHEMA public;
ALTER TABLE nba_old.nba_teamseasonoutlook SET SCHEMA public;
-- reset every NBA identity sequence to max(id) + 1
\o /dev/null
SELECT format('SELECT setval(%L, (SELECT coalesce(max(id), 0) + 1 FROM public.%I), false)',
              pg_get_serial_sequence(format('public.%I', c.relname), 'id'), c.relname)
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname LIKE 'nba\_%' ORDER BY c.relname \gexec
\o
SELECT (SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'nba\_%') = 18 AS ok18 \gset
\if :ok18
\else
\echo 'public does not hold exactly 18 nba_ tables: rolling back'
SELECT 1/0;
\endif
DROP SCHEMA nba_old;
COMMIT;
