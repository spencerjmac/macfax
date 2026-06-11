# Quick Start Guide

## Option A: Docker (Recommended)

The fastest way to get the full stack running. Requires Docker and Docker Compose.

### Prerequisites

- Docker 24+
- Docker Compose v2
- An existing external Docker network named `macfax_web`:
  ```bash
  docker network create macfax_web
  ```

### 1. Configure environment

All backend environment variables are set directly in `docker-compose.yml`. Review and update:

```yaml
environment:
  SECRET_KEY: change-me          # ← change this before first run
  ALLOWED_HOSTS: "localhost,127.0.0.1,macfax.usu.edu"
  CORS_ALLOWED_ORIGINS: "http://localhost:7001,http://macfax.usu.edu,https://macfax.usu.edu"
```

Generate a strong secret key:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 2. Build and start

```bash
docker compose up -d --build
```

On first start, the backend automatically:
- Runs `migrate`
- Runs `collectstatic`
- Runs `ensure_ncaa_teams` (creates all 365 D1 team rows)
- Starts gunicorn on port 7001

### 3. Create a superuser

```bash
docker compose exec backend python manage.py createsuperuser
```

### 4. Seed conferences

```bash
docker compose exec backend python manage.py seed_conferences
```

### 5. Run the data pipeline

```bash
docker compose exec backend python manage.py update_ncaa_all --season 2026
```

This fetches all games from the NCAA API and computes all metrics. First run takes ~5–15 minutes depending on how many games exist.

### 6. Import team logos

```bash
docker compose exec backend python manage.py import_logos
```

### Access

| Service | URL |
|---|---|
| Web app | http://localhost:7000 |
| Django API | http://localhost:7001/api/ |
| Django admin | http://localhost:7001/admin/ |

---

## Option B: Local Development

Run backend and frontend separately without Docker.

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)
- Node.js 20+ and npm
- PostgreSQL (or adjust `.env.local` to use SQLite)

### Backend setup

```bash
cd backend

# Install dependencies
uv sync

# Create local environment file
cp .env.example .env.local
# Edit .env.local: set DATABASE_URL, SECRET_KEY, etc.

# Run migrations
uv run python manage.py migrate

# Seed required data
uv run python manage.py seed_conferences
uv run python manage.py ensure_ncaa_teams

# Start dev server
uv run python manage.py runserver
```

Backend runs on **http://localhost:8000**.

### Frontend setup

```bash
cd web

# Install dependencies
npm install

# Start dev server
npm run dev
```

Frontend runs on **http://localhost:3000**.

The frontend reads `NEXT_PUBLIC_API_BASE_URL` from environment. For local dev, the default fallback `http://localhost:8000` is used automatically.

### Ingest data

```bash
cd backend
uv run python manage.py update_ncaa_all --season 2026
```

---

## Verify the stack

**API:**
```bash
curl http://localhost:8000/api/rankings/?season=2026
```

**Admin:**
Visit http://localhost:8000/admin/ and log in with your superuser credentials.

**Frontend:**
Visit http://localhost:3000 — the rankings table should show all 365 D1 teams.

---

## Daily update workflow

After the initial setup, keeping data current is one command:

```bash
# Docker
docker compose exec backend python manage.py update_ncaa_all --season 2026

# Local
cd backend && uv run python manage.py update_ncaa_all --season 2026
```

`update_ncaa_all` is idempotent — it only ingests games not yet in the database and recomputes all metrics.

To skip ingestion and only recompute metrics (faster):
```bash
python manage.py update_ncaa_all --season 2026 --skip-ingest
```

---

## Troubleshooting

**Team mapping warnings during ingest**
> `NCAA mapping 'X' not found in Team table`

Run `ensure_ncaa_teams` to create any missing team rows:
```bash
python manage.py ensure_ncaa_teams
```

**Missing box scores after ingest**
Some games may be recorded without box score stats if the NCAA API returned 428/502 errors. Re-fetch only the missing ones:
```bash
python manage.py backfill_missing_game_stats --season 2026
```

**Logos not showing**
Logos are served from the Django backend at `/static/logos/`. Run:
```bash
python manage.py import_logos
python manage.py collectstatic --noinput
```

**CORS errors in browser**
Verify `CORS_ALLOWED_ORIGINS` in `docker-compose.yml` (or `.env.local`) includes your frontend origin.
