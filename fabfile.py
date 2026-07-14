"""
Fabric deployment tasks for Macfax.

Server  : sands.usu.edu:42222
User    : macfax (SSH key auth)
App dir : /opt/macfax

Usage
-----
  fab deploy              # git pull + build + restart
  fab pull                # git pull only
  fab build               # docker compose build only
  fab up                  # docker compose up -d only
  fab restart             # up -d (recreate changed containers, no rebuild)
  fab migrate             # run Django migrations inside the backend container
  fab logs                # tail all service logs
  fab logs --service=backend  # tail a specific service
  fab ps                  # show container status
  fab shell               # open a bash shell in the backend container
  fab db-push             # DESTRUCTIVE: overwrite prod db with local (backs up prod first)
"""

import os
import time

from fabric import Connection, task

HOST = "sands.usu.edu"
USER = "macfax"
PORT = 42222
APP_DIR = "/opt/macfax"
COMPOSE = "docker compose"

# Postgres (same in local and prod docker-compose)
DB_SERVICE = "db"
DB_USER = "cbb_user"
DB_NAME = "cbb_analytics"
BACKUP_DIR = f"{APP_DIR}/backups"
BACKUP_KEEP = 5


def _conn():
    """Return a Connection to the production server."""
    return Connection(host=HOST, user=USER, port=PORT)


# ---------------------------------------------------------------------------
# Individual steps
# ---------------------------------------------------------------------------

@task
def pull(c):
    """Pull latest code from git on the server."""
    with _conn() as conn:
        with conn.cd(APP_DIR):
            print("── git pull ──────────────────────────────")
            conn.run("git fetch origin && git reset --hard origin/main", pty=True)


@task
def build(c):
    """Build Docker images on the server."""
    with _conn() as conn:
        with conn.cd(APP_DIR):
            print("── docker compose build ──────────────────")
            conn.run(f"{COMPOSE} build", pty=True)


@task
def up(c):
    """Start / recreate containers in detached mode."""
    with _conn() as conn:
        with conn.cd(APP_DIR):
            print("── docker compose up -d ──────────────────")
            conn.run(f"{COMPOSE} up -d", pty=True)


# ---------------------------------------------------------------------------
# Composite tasks
# ---------------------------------------------------------------------------

@task
def deploy(c):
    """Full deploy: git pull → docker compose build → up -d."""
    with _conn() as conn:
        with conn.cd(APP_DIR):
            print("── git pull ──────────────────────────────")
            conn.run("git fetch origin && git reset --hard origin/main", pty=True)

            print("── docker compose build ──────────────────")
            conn.run(f"{COMPOSE} build", pty=True)

            print("── docker compose up -d ──────────────────")
            conn.run(f"{COMPOSE} up -d", pty=True)

            print("✓ Deploy complete")


@task
def restart(c):
    """Recreate containers without rebuilding images (fast restart)."""
    with _conn() as conn:
        with conn.cd(APP_DIR):
            conn.run(f"{COMPOSE} up -d --force-recreate", pty=True)


# ---------------------------------------------------------------------------
# Ops helpers
# ---------------------------------------------------------------------------

@task
def migrate(c):
    """Run Django database migrations inside the running backend container."""
    with _conn() as conn:
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
def ps(c):
    """Show running container status."""
    with _conn() as conn:
        with conn.cd(APP_DIR):
            conn.run(f"{COMPOSE} ps", pty=True)


@task
def shell(c):
    """Open an interactive bash shell inside the backend container."""
    with _conn() as conn:
        with conn.cd(APP_DIR):
            conn.run(f"{COMPOSE} exec backend bash", pty=True)


@task
def manage(c, cmd):
    """Run a manage.py command inside the backend container."""
    with _conn() as conn:
        with conn.cd(APP_DIR):
            conn.run(f"{COMPOSE} exec backend python manage.py {cmd}", pty=True)


# ---------------------------------------------------------------------------
# Database push (local docker postgres  →  prod docker postgres)
# ---------------------------------------------------------------------------

@task
def db_push(c, yes=False):
    """
    DESTRUCTIVE: replace the production database with a full dump of the local
    docker postgres.

      fab db-push            # prompts for typed confirmation
      fab db-push --yes      # skip the typed-confirm prompt (still backs up first)

    Steps:
      1. pg_dump the LOCAL docker db  (custom format -Fc)
      2. upload the dump to the server
      3. pg_dump the PROD db to /opt/macfax/backups/ (safety backup, keep last 5)
      4. stop backend + web (release db connections)
      5. DROP + CREATE the prod database and pg_restore the local dump
      6. bring all containers back up

    Local docker stack must be running (`docker compose up -d db`).
    """
    ts = time.strftime("%Y%m%d-%H%M%S")
    local_dump = f"/tmp/macfax-local-{ts}.dump"
    remote_dump = f"/tmp/macfax-local-{ts}.dump"
    prod_backup = f"{BACKUP_DIR}/prod-{ts}.dump"

    # --- confirmation -----------------------------------------------------
    if not yes:
        print("⚠  This OVERWRITES the production database with your LOCAL data.")
        print(f"   A prod backup will be saved to {prod_backup} first.")
        reply = input('   Type "PROD" to continue: ').strip()
        if reply != "PROD":
            print("Aborted.")
            return

    # --- 1. dump local db -------------------------------------------------
    print("── pg_dump local db ──────────────────────")
    c.run(
        f"{COMPOSE} exec -T {DB_SERVICE} "
        f"pg_dump -U {DB_USER} -Fc {DB_NAME} > {local_dump}"
    )
    size = os.path.getsize(local_dump)
    if size == 0:
        print("✗ Local dump is empty — is the local docker db running? Aborting.")
        os.remove(local_dump)
        return
    print(f"   local dump: {local_dump} ({size:,} bytes)")

    with _conn() as conn:
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