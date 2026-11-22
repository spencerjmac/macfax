#!/usr/bin/env bash
# Go 2, steps P10-P13 of docs/deploy_native_bpr.md, in one process, so that nothing (a permission
# prompt, a dropped ssh session) can land between stopping the site and starting it again:
#   P10  stop backend + web; check that no other client session is connected to the database.
#        Background workers (autovacuum) are listed but do not fail the check: they give way to the
#        swap's locks. Approved 2026-11-21.
#   P11  swap (backups/swap.sql: one transaction)
#   P12  clear the NBA redis keys (NCAA keys untouched)
#   P13  start backend + web, wait for the NBA health check to return 200
# Backend and web are started again on ANY exit: success, a failed step, or a signal (TERM, INT, HUP).
# The script never rolls data back. A failed step stops it, the site comes back up, and what to do
# next (section 7.5) is decided by hand.
#
# Kept in tools/deploy_native/ and uploaded to prod's backups/ (step L5 of docs/deploy_native_bpr.md).
# Usage, on prod in /opt/macfax:   bash backups/swap_window.sh TS
# Go 2 runs it detached, so a dropped ssh session cannot stop it:
#   setsid nohup bash backups/swap_window.sh $TS < /dev/null > /dev/null 2>&1 &
# Output: backups/swap_window_$TS.log (appended); the exit code is written to backups/swap_window_$TS.rc
# and the script's pid to backups/swap_window_$TS.pid.
# Exit codes: 0 ok | 10 stop failed | 11 another client session is connected, or the check failed |
#             12 swap failed (swap.sql rolls itself back) | 13 redis step failed |
#             14 backend/web not back: up -d failed or health not 200 within HEALTH_WAIT s |
#             129/130/143 HUP/INT/TERM.
#
# Rehearsal only: APP_DIR, HEALTH_URL, HEALTH_WAIT and TEST_PAUSE_BEFORE_SWAP override the prod
# defaults below. Go 2 sets none of them. Rehearsed 2026-11-21 in a throwaway compose project
# (another session -> 11, TERM -> 143, failed swap -> 12, success -> 0, no health -> 14).
set -uo pipefail   # no -e: each step checks its own status
TS=${1:?usage: swap_window.sh TS}
APP_DIR=${APP_DIR:-/opt/macfax}
HEALTH_URL=${HEALTH_URL:-http://127.0.0.1:7001/api/nba/health/}
HEALTH_WAIT=${HEALTH_WAIT:-300}
cd "$APP_DIR" || exit 2
LOG=backups/swap_window_$TS.log
RCF=backups/swap_window_$TS.rc
rm -f "$RCF"
exec >> "$LOG" 2>&1
echo $$ > "backups/swap_window_$TS.pid"
PSQL=(docker compose exec -T db psql -X -U cbb_user -d cbb_analytics -v ON_ERROR_STOP=1)
say() { echo "$(date '+%F %T') $*"; }
schemas() { "${PSQL[@]}" -Atc "SELECT coalesce(string_agg(nspname || '(' || (SELECT count(*) FROM pg_tables t WHERE t.schemaname = n.nspname) || ')', ', ' ORDER BY nspname), 'none') FROM pg_namespace n WHERE nspname LIKE 'nba%'"; }
STEP=start

finish() {
  local rc=$? up code=000 t=0
  trap '' TERM INT HUP   # the restart itself must not be interrupted
  say "== P13 start backend + web (leaving step $STEP with rc $rc)"
  docker compose up -d backend web; up=$?
  while [ "$t" -lt "$HEALTH_WAIT" ]; do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$HEALTH_URL")
    [ "$code" = 200 ] && break
    sleep 5; t=$((t + 5))
  done
  say "up -d rc $up; health $code after ${t}s ($HEALTH_URL)"
  if [ "$rc" -eq 0 ] && { [ "$up" -ne 0 ] || [ "$code" != 200 ]; }; then rc=14; fi
  say "nba schemas (tables): $(schemas)"
  docker compose ps --format '{{.Service}} {{.Status}}'
  say "== swap_window done rc=$rc"
  echo "$rc" > "$RCF"
  exit "$rc"
}
trap finish EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

say "== swap_window TS=$TS pid $$ in $APP_DIR"
say "nba schemas (tables): $(schemas)"

STEP=P10
say "== P10 stop backend + web"
docker compose stop backend web || exit 10
docker compose ps --format '{{.Service}} {{.Status}}'
say "other sessions on the database (any client backend fails the check):"
OTHER=$("${PSQL[@]}" -Atc "SELECT pid, application_name, state, backend_type FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid()") || exit 11
echo "${OTHER:-(none)}"
CLIENTS=$(printf '%s\n' "$OTHER" | awk -F'|' '$4 == "client backend"' | grep -c .)
say "client sessions: $CLIENTS"
[ "$CLIENTS" -eq 0 ] || exit 11

STEP=P11
if [ -n "${TEST_PAUSE_BEFORE_SWAP:-}" ]; then
  say "rehearsal pause ${TEST_PAUSE_BEFORE_SWAP}s"; sleep "$TEST_PAUSE_BEFORE_SWAP" & wait $!
fi
say "== P11 swap"
"${PSQL[@]}" -q -f - < backups/swap.sql; rc=$?
say "swap rc=$rc"
[ "$rc" -eq 0 ] || exit 12

STEP=P12
say "== P12 NBA cache keys"
say "NBA keys before: $(docker compose exec -T redis sh -c "redis-cli -n 1 --scan --pattern 'macfax:*:nba:*' | wc -l")"
docker compose exec -T redis sh -c "redis-cli -n 1 --scan --pattern 'macfax:*:nba:*' | xargs -r redis-cli -n 1 del" || exit 13
say "NBA keys after: $(docker compose exec -T redis sh -c "redis-cli -n 1 --scan --pattern 'macfax:*:nba:*' | wc -l"); all keys in db 1: $(docker compose exec -T redis redis-cli -n 1 dbsize)"

STEP=P13
exit 0
