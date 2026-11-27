"""
Fabric deployment tasks for Macfax.

Server  : sands.usu.edu:42222
User    : macfax (SSH key auth)
App dir : /opt/macfax

Usage
-----
  fab deploy              # git pull + build + restart + prune old macfax images (refuses while a manage.py command runs)
  fab deploy --force      # deploy even if a manage.py command is running in the backend container
  fab pull                # git pull only
  fab build               # docker compose build only
  fab up                  # docker compose up -d only
  fab restart             # up -d (recreate changed containers, no rebuild)
  fab migrate             # run Django migrations inside the backend container
  fab logs                # tail all service logs
  fab logs --service=backend  # tail a specific service
  fab ps                  # show container status
  fab pipeline-log        # last update_* runs (steps, rc, timings) from the pipeline run log
  fab pipeline-log -n 20
  fab shell               # open a bash shell in the backend container
  fab db-push             # DESTRUCTIVE: overwrite prod db with local (backs up prod first)
  fab lock-status         # who holds the prod write lock, if anyone
  fab lock-break --yes    # remove a stale prod lock (prints what it removes)

Prod write lock: every task that changes prod (pull, build, up, deploy, restart, migrate, manage,
shell, db-push) takes the lock in ops/prod-lock.sh and refuses to run while another session holds it.
Set PROD_LOCK_HOLDER to name your session (default user@host:pid). Ad-hoc writes on the server take
the same lock: /opt/macfax/ops/prod-lock.sh run "<holder>" -- <command...>
"""

import getpass
import io
import os
import shlex
import socket
import time
from contextlib import contextmanager

from fabric import Connection, task

HOST = "sands.usu.edu"
USER = "macfax"
PORT = 42222
APP_DIR = "/opt/macfax"
COMPOSE = "docker compose"

# Prod postgres (docker-compose db service)
DB_SERVICE = "db"
DB_USER = "cbb_user"
DB_NAME = "cbb_analytics"
BACKUP_DIR = f"{APP_DIR}/backups"
BACKUP_KEEP = 5

# Local dev postgres — NATIVE (not docker); see backend/.env.local
#   DATABASE_URL=postgres://spencer@/macfax?host=/var/run/postgresql
LOCAL_DB_USER = "spencer"
LOCAL_DB_NAME = "macfax"


def _conn():
    """Return a Connection to the production server."""
    return Connection(host=HOST, user=USER, port=PORT)


# ---------------------------------------------------------------------------
# Prod write lock (ops/prod-lock.sh)
# ---------------------------------------------------------------------------

LOCK_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ops", "prod-lock.sh")
# Under .locks/ so the scheduler container can mount the parent (the nightly takes the same lock)
LOCK_DIR = f"{APP_DIR}/.locks/prod"


def _lock_holder() -> str:
    return os.environ.get("PROD_LOCK_HOLDER") or f"{getpass.getuser()}@{socket.gethostname()}:{os.getpid()}"


def _lock_run(conn, args: str, **kw):
    """Run ops/prod-lock.sh on the server from the local copy (works before it is deployed)."""
    with open(LOCK_SCRIPT) as f:
        script = f.read()
    return conn.run(f"PROD_LOCK_DIR={shlex.quote(LOCK_DIR)} bash -s -- {args}",
                    in_stream=io.StringIO(script), hide=True, warn=True, **kw)


@contextmanager
def _prod_lock(conn, command: str):
    """
    Hold the prod write lock for the block, or refuse (SystemExit) when another session holds it.
    Released on the way out, also on errors and Ctrl-C.
    """
    r = _lock_run(conn, f"acquire {shlex.quote(_lock_holder())} {shlex.quote(command)}")
    if r.exited != 0:
        print(r.stderr.rstrip())
        raise SystemExit(f"Refused: the prod write lock is held by another session (see above). "
                         f"Wait for it, or if it is stale: fab lock-break --yes")
    token = r.stdout.strip().splitlines()[-1]
    print(f"── prod lock taken ({_lock_holder()})")
    try:
        yield token
    finally:
        rel = _lock_run(conn, f"release {shlex.quote(token)}")
        print("── prod lock released" if rel.exited == 0 else f"── prod lock NOT released: {rel.stderr.strip()}")


# ---------------------------------------------------------------------------
# Individual steps
# ---------------------------------------------------------------------------

@task
def pull(c):
    """Pull latest code from git on the server."""
    with _conn() as conn:
        with _prod_lock(conn, "fab pull"):
            with conn.cd(APP_DIR):
                print("── git pull ──────────────────────────────")
                conn.run("git fetch origin && git reset --hard origin/main", pty=True)


@task
def build(c):
    """Build Docker images on the server."""
    with _conn() as conn:
        with _prod_lock(conn, "fab build"):
            with conn.cd(APP_DIR):
                print("── docker compose build ──────────────────")
                conn.run(f"{COMPOSE} build", pty=True)


@task
def up(c):
    """Start / recreate containers in detached mode."""
    with _conn() as conn:
        with _prod_lock(conn, "fab up"):
            with conn.cd(APP_DIR):
                print("── docker compose up -d ──────────────────")
                conn.run(f"{COMPOSE} up -d", pty=True)


def _running_manage_commands(conn):
    """manage.py commands running in the backend container (e.g. a `docker compose exec backend python
    manage.py ...` job), as "pid args" lines. The container's own start command (migrate, collectstatic,
    ... then gunicorn) is not one. Read with `docker top` on the host, so the image needs no ps.
    None if the container is not running."""
    cid = conn.run(f"{COMPOSE} ps -q backend", hide=True, warn=True).stdout.strip()
    if not cid:
        return None
    top = conn.run(f"docker top {cid} -eo pid,args", hide=True, warn=True)
    if not top.ok:
        return None
    return [line.strip() for line in top.stdout.splitlines()[1:]
            if "manage.py" in line and "gunicorn" not in line]


# ---------------------------------------------------------------------------
# Composite tasks
# ---------------------------------------------------------------------------

@task
def deploy(c, force=False):
    """Full deploy: git pull → docker compose build → up -d → prune old macfax images and build cache.

    Refuses while a manage.py command runs in the backend container: `up -d` recreates the container
    when its image changes, which kills that command. --force deploys anyway.
    """
    with _conn() as conn:
        with _prod_lock(conn, "fab deploy"):
            with conn.cd(APP_DIR):
                running = _running_manage_commands(conn)
                if running is None:
                    print("── guard: backend container not running, nothing to check")
                elif running:
                    print("── guard: manage.py commands running in the backend container:")
                    for line in running:
                        print(f"     {line}")
                    if not force:
                        raise SystemExit("Deploy refused: wait for them to finish, or pass --force.")
                    print("── guard: --force given, deploying anyway")
                else:
                    print("── guard: no manage.py commands running")

                print("── git pull ──────────────────────────────")
                conn.run("git fetch origin && git reset --hard origin/main", pty=True)

                print("── docker compose build ──────────────────")
                conn.run(f"{COMPOSE} build", pty=True)

                print("── docker compose up -d ──────────────────")
                conn.run(f"{COMPOSE} up -d", pty=True)

                print("✓ Deploy complete")
                _prune_after_deploy(conn)


# After a successful deploy (a failed step raises first, so these never run): old macfax images only
# (the other services on the server keep theirs; images in use are never removed), and build cache
# older than a week, so the next build stays fast. Volumes are never touched.
PRUNE_AFTER_DEPLOY = (
    "docker image prune -f --filter label=com.docker.compose.project=macfax",
    "docker builder prune -f --filter until=168h",
)


def _prune_after_deploy(conn):
    """A failed prune is reported and never fails the deploy, which has already succeeded."""
    print("── prune old macfax images and build cache ──")
    for cmd in PRUNE_AFTER_DEPLOY:
        r = conn.run(cmd, hide=True, warn=True)
        lines = (r.stdout or "").strip().splitlines()
        if r.exited == 0:
            print(f"   {cmd.split(' -f')[0]}: {lines[-1] if lines else 'done'}")
        else:
            print(f"   WARNING: `{cmd}` exited {r.exited}: {(r.stderr or '').strip()[-300:]}")


@task
def restart(c):
    """Recreate containers without rebuilding images (fast restart)."""
    with _conn() as conn:
        with _prod_lock(conn, "fab restart"):
            with conn.cd(APP_DIR):
                conn.run(f"{COMPOSE} up -d --force-recreate", pty=True)


# ---------------------------------------------------------------------------
# Ops helpers
# ---------------------------------------------------------------------------

@task
def migrate(c):
    """Run Django database migrations inside the running backend container."""
    with _conn() as conn:
        with _prod_lock(conn, "fab migrate"):
            with conn.cd(APP_DIR):
                conn.run(
                    f"{COMPOSE} exec backend python manage.py migrate",
                    pty=True,
                )


@task
def logs(c, service=""):
    """
    Tail logs for all services, or a specific one.

      fab logs
      fab logs --service=backend
    """
    target = service if service else ""
    with _conn() as conn:
        with conn.cd(APP_DIR):
            conn.run(f"{COMPOSE} logs -f --tail=100 {target}", pty=True)


@task
def pipeline_log(c, n=5):
    """
    Show the last n update_* runs from the pipeline run log (read-only): fab pipeline-log -n 20

    The log (ncaa/pipeline_log.py) is one JSON line per run on the macfax_pipeline_logs volume,
    so it survives container recreation. Read through the scheduler container, which mounts it.
    """
    script = (
        "import json\n"
        "try:\n"
        "    lines = open('/var/log/macfax/pipeline_runs.jsonl').read().splitlines()\n"
        "except FileNotFoundError:\n"
        "    lines = []\n"
        "    print('no runs logged yet')\n"
        "for line in lines[-%d:]:\n"
        "    r = json.loads(line)\n"
        "    print(f\"{r['started'][:19]}  {r['command']:<22} rc={r['rc']}  {r['seconds']:>7.0f}s  {r.get('options', {}).get('season', '')}\")\n"
        "    if r.get('lock_holder'):\n"
        "        print(f\"    lock: {r['lock_holder']}, waited {r.get('lock_wait_seconds')}s\")\n"
        "    if r.get('reason'):\n"
        "        print(f\"    {r['reason']}\")\n"
        "    for st in r['steps']:\n"
        "        sec = '' if st['seconds'] is None else f\"{st['seconds']:.0f}s\"\n"
        "        print(f\"    rc={st['rc']}  {sec:>7}  {st['name']}\" + (f\"  ({st['note']})\" if st['note'] else ''))\n"
    ) % int(n)
    with _conn() as conn:
        with conn.cd(APP_DIR):
            conn.run(f"{COMPOSE} exec -T scheduler python -c {_shquote(script)}", pty=False)


def _shquote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


@task
def lock_status(c):
    """Show who holds the prod write lock (read-only)."""
    with _conn() as conn:
        print(_lock_run(conn, "status").stdout.rstrip())


@task
def lock_break(c, yes=False):
    """Remove a stale prod write lock (e.g. left by a dropped SSH session). Needs --yes."""
    if not yes:
        raise SystemExit("lock-break removes the lock whoever holds it; check `fab lock-status`, then pass --yes")
    with _conn() as conn:
        r = _lock_run(conn, "break --yes")
        print(r.stdout.rstrip() or r.stderr.rstrip())


@task
def ps(c):
    """Show running container status."""
    with _conn() as conn:
        with conn.cd(APP_DIR):
            conn.run(f"{COMPOSE} ps", pty=True)


@task
def shell(c):
    """Open an interactive bash shell inside the backend container."""
    with _conn() as conn:
        with _prod_lock(conn, "fab shell"):
            with conn.cd(APP_DIR):
                conn.run(f"{COMPOSE} exec backend bash", pty=True)


@task
def manage(c, cmd):
    """Run a manage.py command inside the backend container."""
    with _conn() as conn:
        with _prod_lock(conn, f"fab manage {cmd}"):
            with conn.cd(APP_DIR):
                conn.run(f"{COMPOSE} exec backend python manage.py {cmd}", pty=True)


# ---------------------------------------------------------------------------
# Database push (local docker postgres  →  prod docker postgres)
# ---------------------------------------------------------------------------

@task
def db_push(c, yes=False, docker=False):
    """
    DESTRUCTIVE: replace the production database with a full dump of the local
    postgres.

      fab db-push            # dump native local db (macfax), prompt to confirm
      fab db-push --yes      # skip the typed-confirm prompt (still backs up first)
      fab db-push --docker   # dump from a LOCAL docker db instead of native pg

    By default dumps the NATIVE local postgres (db `macfax`, user `spencer`) that
    `npm run dev` uses. Pass --docker to dump from a local docker-compose db.

    Steps:
      1. pg_dump the LOCAL db  (custom format -Fc)
      2. upload the dump to the server
      3. pg_dump the PROD db to /opt/macfax/backups/ (safety backup, keep last 5)
      4. stop backend + web (release db connections)
      5. DROP + CREATE the prod database and pg_restore the local dump
      6. bring all containers back up
    """
    ts = time.strftime("%Y%m%d-%H%M%S")
    local_dump = f"/tmp/macfax-local-{ts}.dump"
    remote_dump = f"/tmp/macfax-local-{ts}.dump"
    prod_backup = f"{BACKUP_DIR}/prod-{ts}.dump"
    src = "local docker db" if docker else f"native pg ({LOCAL_DB_NAME})"

    # --- confirmation -----------------------------------------------------
    if not yes:
        print(f"⚠  This OVERWRITES the PROD database with your LOCAL data [{src}].")
        print(f"   A prod backup will be saved to {prod_backup} first.")
        reply = input('   Type "PROD" to continue: ').strip()
        if reply != "PROD":
            print("Aborted.")
            return

    # --- 1. dump local db -------------------------------------------------
    print(f"── pg_dump {src} ──────────────────────")
    if docker:
        c.run(
            f"{COMPOSE} exec -T {DB_SERVICE} "
            f"pg_dump -U {DB_USER} -Fc {DB_NAME} > {local_dump}"
        )
    else:
        c.run(f"pg_dump -U {LOCAL_DB_USER} -Fc {LOCAL_DB_NAME} > {local_dump}")
    size = os.path.getsize(local_dump)
    if size == 0:
        print("✗ Local dump is empty — is the local db running? Aborting.")
        os.remove(local_dump)
        return
    print(f"   local dump: {local_dump} ({size:,} bytes)")

    with _conn() as conn:
        with _prod_lock(conn, "fab db-push"):
            # --- 2. upload dump ------------------------------------------------
            print("── upload dump to server ─────────────────")
            conn.put(local_dump, remote_dump)

            with conn.cd(APP_DIR):
                # --- 3. backup prod db ----------------------------------------
                print("── backup prod db ────────────────────────")
                conn.run(f"mkdir -p {BACKUP_DIR}")
                conn.run(
                    f"{COMPOSE} exec -T {DB_SERVICE} "
                    f"pg_dump -U {DB_USER} -Fc {DB_NAME} > {prod_backup}"
                )
                conn.run(f"ls -lh {prod_backup}")

                # --- 4. stop app (release connections) ------------------------
                print("── stop backend + web ────────────────────")
                conn.run(f"{COMPOSE} stop backend web", pty=True)

                try:
                    # --- 5. drop + recreate + restore -------------------------
                    print("── drop + create + restore prod db ───────")
                    conn.run(
                        f"{COMPOSE} exec -T {DB_SERVICE} "
                        f'psql -U {DB_USER} -d postgres -c '
                        f'"DROP DATABASE IF EXISTS {DB_NAME};"',
                        pty=True,
                    )
                    conn.run(
                        f"{COMPOSE} exec -T {DB_SERVICE} "
                        f'psql -U {DB_USER} -d postgres -c '
                        f'"CREATE DATABASE {DB_NAME} OWNER {DB_USER};"',
                        pty=True,
                    )
                    conn.run(
                        f"{COMPOSE} exec -T {DB_SERVICE} "
                        f"pg_restore -U {DB_USER} --no-owner --no-acl "
                        f"-d {DB_NAME} < {remote_dump}",
                        pty=True,
                    )
                finally:
                    # --- 6. always bring the app back up ----------------------
                    print("── docker compose up -d ──────────────────")
                    conn.run(f"{COMPOSE} up -d", pty=True)

                # --- cleanup: remote dump + prune old backups -----------------
                conn.run(f"rm -f {remote_dump}")
                conn.run(
                    f"ls -1t {BACKUP_DIR}/prod-*.dump 2>/dev/null "
                    f"| tail -n +{BACKUP_KEEP + 1} | xargs -r rm -f"
                )
                print(f"   kept last {BACKUP_KEEP} prod backups in {BACKUP_DIR}")

    os.remove(local_dump)
    print("✓ db-push complete — prod now mirrors local")