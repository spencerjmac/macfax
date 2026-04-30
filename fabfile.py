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
"""

from fabric import Connection, task

HOST = "sands.usu.edu"
USER = "macfax"
PORT = 42222
APP_DIR = "/opt/macfax"
COMPOSE = "docker compose"


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
            conn.run("git pull", pty=True)


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
            conn.run("git pull", pty=True)

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