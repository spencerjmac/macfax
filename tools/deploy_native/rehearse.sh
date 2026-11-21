#!/usr/bin/env bash
# Rehearse the staging load, carry-over, swap and rollback in a throwaway postgres:16-alpine
# container (no network, removed at the end), on a sample of an NBA dump (stints cut to 20,000).
# Usage: rehearse.sh NBA_DUMP.sql.gz COUNTS.txt OUT_DIR
#   NBA_DUMP / COUNTS: step L3 of docs/deploy_native_bpr.md; OUT_DIR receives run.log-style output files.
set -uo pipefail
DUMP=$1; COUNTS=$2; R=$3; X=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$R"; bash $X/make_check_counts.sh "$COUNTS" > $R/check_counts.sql
C=d2-rehearsal
docker rm -f $C >/dev/null 2>&1
docker run -d --rm --name $C --network none -e POSTGRES_USER=cbb_user -e POSTGRES_PASSWORD=x -e POSTGRES_DB=cbb_analytics postgres:16-alpine >/dev/null
until docker exec $C pg_isready -U cbb_user -d cbb_analytics -q; do sleep 1; done; sleep 2
P() { docker exec -i $C psql -X -U cbb_user -d cbb_analytics -v ON_ERROR_STOP=1 "$@"; }
zcat $DUMP | awk '/^COPY public.nba_nbaplayergamestint /{s=1; n=0; print; next} s&&$0=="\\."{s=0; print; next} s{if (++n <= 20000) print; next} {print}' | gzip -1 > $R/sample.sql.gz
zcat $R/sample.sql.gz | awk '/^COPY /{t=$2;n=0;inb=1;next} inb&&/^\\\.$/{print t, n; inb=0; next} inb{n++}' > $R/sample_counts.txt
bash $X/make_check_counts.sh $R/sample_counts.txt > $R/check_counts_sample.sql

echo "== fake prod: same schema + sample data in public, plus prod-only edits"
P -q -c "CREATE TABLE django_migrations (id serial, app text, name text); INSERT INTO django_migrations (app, name) VALUES ('nba', '0033_rating_scale'); CREATE TABLE favorites_favoriteteam (id serial, slug text); INSERT INTO favorites_favoriteteam (slug) VALUES ('kansas');"
zcat $R/sample.sql.gz | P -q -1 > /dev/null
P -q <<'SQL'
UPDATE nba_teamseasonoutlook SET season_headline = 'Prod headline', macfax_take = 'Prod take' WHERE team_slug = 'boston-celtics';
UPDATE nba_teamseasonoutlook SET is_published = false WHERE team_slug = 'utah-jazz';
INSERT INTO nba_teamoutseasonmove (move_type, player_name, detail, impact_rating, created_at, team_id, season_id, source)
SELECT 'signed', 'Prod Only Guy', 'entered on prod', 0, now(), o.id, o.season_id, 'manual' FROM nba_teamseasonoutlook o WHERE team_slug = 'utah-jazz';
INSERT INTO nba_nbaplayeravailability (game_date, status, injury_reason, notes, source, created_at, updated_at, player_id, season_id, team_id)
SELECT game_date + 1, 'out', 'prod-only report', '', 'espn', now(), now(), player_id, season_id, team_id FROM nba_nbaplayeravailability ORDER BY game_date DESC, id DESC LIMIT 1;
UPDATE nba_nbaplayeravailability SET status = 'questionable', updated_at = now() + interval '1 day' WHERE id = (SELECT min(id) FROM nba_nbaplayeravailability);
SQL

echo "== 1. load staging"; t0=$(date +%s)
zcat $R/sample.sql.gz | awk -f $X/to_stage.awk | P -q -1 > /dev/null; echo "rc=$? $(( $(date +%s) - t0 ))s"
echo "== 2a. count check with the REAL expected counts (must fail: sample has 20,000 stints)"
P -q -v schema=nba_stage -f - < $R/check_counts.sql 2>&1 | tail -3; echo "rc=${PIPESTATUS[0]}"
echo "== 2b. count check with sample counts (must pass)"
P -q -v schema=nba_stage -f - < $R/check_counts_sample.sql 2>&1 | tail -2; echo "rc=${PIPESTATUS[0]}"
echo "== 3. carry"; P -f - < $X/carry.sql; echo "rc=$?"
P -q -At -c "SELECT 'public ids before swap', min(id), max(id) FROM public.nba_nbagame" -c "SELECT 'stage ids', min(id), max(id) FROM nba_stage.nba_nbagame"
echo "== 4. swap"; P -q -f - < $X/swap.sql; echo "rc=$?"
echo "== 5. verify"; P -f - < $X/verify.sql > $R/verify_after_swap.txt 2>&1; echo "rc=$?"; sed -n '/schemas/,/migrations/p;/sequences/,/per season/p' $R/verify_after_swap.txt | grep -v "^$"
P -At <<'SQL'
SELECT 'carried headline', season_headline, macfax_take FROM nba_teamseasonoutlook WHERE team_slug = 'boston-celtics';
SELECT 'carried unpublished', is_published FROM nba_teamseasonoutlook WHERE team_slug = 'utah-jazz';
SELECT 'carried manual moves', count(*) FROM nba_teamoutseasonmove WHERE source = 'manual';
SELECT 'carried availability', count(*), count(*) FILTER (WHERE status = 'questionable' AND id = (SELECT min(id) FROM nba_nbaplayeravailability)) FROM nba_nbaplayeravailability;
SELECT 'favorites untouched', count(*) FROM favorites_favoriteteam;
-- new rows get fresh ids and FKs resolve to the swapped-in tables
BEGIN;
INSERT INTO nba_teamoutseasonmove (move_type, player_name, detail, impact_rating, created_at, team_id, season_id, source)
SELECT 'signed', 'Id Test', '', 0, now(), id, season_id, 'manual' FROM nba_teamseasonoutlook LIMIT 1
RETURNING 'insert ok, new id', id, (SELECT max(id) FROM nba_teamoutseasonmove) AS prior_max;
ROLLBACK;
SELECT 'FK stint->game targets', confrelid::regclass FROM pg_constraint WHERE conrelid = 'public.nba_nbaplayergamestint'::regclass AND contype = 'f' ORDER BY 2;
SQL
echo "== 6. rollback"; P -q -f - < $X/rollback.sql; echo "rc=$?"
P -At -c "SELECT 'after rollback: public games, stints, headline', (SELECT count(*) FROM nba_nbagame), (SELECT count(*) FROM nba_nbaplayergamestint), (SELECT season_headline FROM nba_teamseasonoutlook WHERE team_slug = 'boston-celtics')" \
      -c "SELECT 'schemas', string_agg(nspname, ',') FROM pg_namespace WHERE nspname LIKE 'nba%'"
docker rm -f $C >/dev/null; rm -f $R/sample.sql.gz
