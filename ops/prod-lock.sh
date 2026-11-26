#!/usr/bin/env bash
# Prod write lock: one session at a time may change prod (deploys, migrations, data fixes, backfills).
#
# Why: on 2026-11-26 one session's `fab deploy` recreated the containers 13 s after another session
# started a data backfill in the backend container, killing it mid-run. The deploy's guard only looks
# for manage.py commands already running, so two sessions starting together both pass it.
#
# The lock is a directory (mkdir is atomic) holding an `info` file: holder, command, start time, host
# and a token. Only the token's owner releases it.
#
#   prod-lock.sh acquire <holder> <command...>   take it; prints the token (exit 3 + holder if held)
#   prod-lock.sh release <token>                 release it (exit 4 if another holder has it)
#   prod-lock.sh status                          "free", or "HELD" and the info
#   prod-lock.sh run <holder> -- <cmd...>        take it, run cmd (stdin passes through), release on exit
#   prod-lock.sh break --yes                     remove a stale lock (prints what it removes)
#
# fab sends this file over SSH (`bash -s`), so the fab tasks work before it is deployed. On the server,
# wrap a write: /opt/macfax/ops/prod-lock.sh run "spencer/session-A" -- docker compose exec -T backend ...
# PROD_LOCK_DIR overrides the location (default /opt/macfax/.prod-lock).
set -u
LOCK_DIR="${PROD_LOCK_DIR:-/opt/macfax/.prod-lock}"

show_info() {
  if [ -f "$LOCK_DIR/info" ]; then cat "$LOCK_DIR/info"; else echo "(lock directory without info: just taken, or left by a crash)"; fi
}

acquire() {  # acquire <holder> <command>
  local holder=$1 cmd=$2 token
  mkdir -p "$(dirname "$LOCK_DIR")" 2>/dev/null
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "prod lock is held:" >&2
    show_info | sed 's/^/  /' >&2
    return 3
  fi
  token="$(date -u +%Y%m%dT%H%M%SZ)-$$-$RANDOM$RANDOM"
  {
    echo "holder=$holder"
    echo "command=$cmd"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "host=$(hostname)"
    echo "token=$token"
  } > "$LOCK_DIR/info.tmp" && mv "$LOCK_DIR/info.tmp" "$LOCK_DIR/info"
  echo "$token"
}

release() {  # release <token>
  local token=$1 cur
  if [ ! -d "$LOCK_DIR" ]; then
    echo "prod lock was not held" >&2
    return 0
  fi
  cur=$(sed -n 's/^token=//p' "$LOCK_DIR/info" 2>/dev/null)
  if [ -n "$token" ] && [ "$cur" = "$token" ]; then
    rm -rf "$LOCK_DIR"
    return 0
  fi
  echo "not releasing: the prod lock belongs to another holder:" >&2
  show_info | sed 's/^/  /' >&2
  return 4
}

case "${1:-}" in
  acquire)
    [ $# -ge 2 ] || { echo "usage: $0 acquire <holder> <command...>" >&2; exit 2; }
    holder=$2; shift 2
    acquire "$holder" "$*"; exit $?
    ;;
  release)
    [ $# -eq 2 ] || { echo "usage: $0 release <token>" >&2; exit 2; }
    release "$2"; exit $?
    ;;
  status)
    if [ -d "$LOCK_DIR" ]; then echo "HELD"; show_info; else echo "free"; fi
    ;;
  run)
    [ $# -ge 3 ] || { echo "usage: $0 run <holder> -- <cmd...>" >&2; exit 2; }
    holder=$2; shift 2
    [ "${1:-}" = "--" ] && shift
    [ $# -ge 1 ] || { echo "usage: $0 run <holder> -- <cmd...>" >&2; exit 2; }
    token=$(acquire "$holder" "$*") || exit 3
    trap 'release "$token" >/dev/null' EXIT
    trap 'exit 130' INT TERM
    "$@"
    exit $?
    ;;
  break)
    [ "${2:-}" = "--yes" ] || { echo "usage: $0 break --yes   (removes the lock whoever holds it)" >&2; exit 2; }
    if [ -d "$LOCK_DIR" ]; then echo "removing prod lock:"; show_info | sed 's/^/  /'; rm -rf "$LOCK_DIR"; else echo "free"; fi
    ;;
  *)
    sed -n '2,20p' "$0" 2>/dev/null || true
    echo "usage: $0 {acquire|release|status|run|break} ..." >&2
    exit 2
    ;;
esac
