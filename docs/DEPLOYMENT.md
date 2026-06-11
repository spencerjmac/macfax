# Deployment Guide

This project is deployed as a Docker Compose stack on a Linux server at **macfax.usu.edu**.

## Stack Overview

| Service | Image | Internal host | External port |
|---|---|---|---|
| `db` | postgres:16-alpine | `macfax_db` | — (internal only) |
| `backend` | custom (Django 5 + gunicorn) | `macfax_api` | 7001 |
| `web` | custom (Next.js 14) | `macfax_web` | 7000 |

All services share an **external** Docker network named `macfax_web`, which allows an upstream reverse proxy (nginx, Caddy, etc.) on the same host to route traffic.

---

## First-Time Server Setup

### 1. Prerequisites on the server

- Docker 24+
- Docker Compose v2
- A reverse proxy (nginx or Caddy) for SSL termination

### 2. Create the shared Docker network

```bash
docker network create macfax_web
```

This only needs to be done once per server.

### 3. Clone the repository

```bash
git clone <repo-url> /opt/macfax
cd /opt/macfax
```

### 4. Configure environment variables

Open `docker-compose.yml` and update the backend `environment` block:

```yaml
environment:
  SECRET_KEY: "<generate a strong secret key>"
  ALLOWED_HOSTS: "localhost,127.0.0.1,macfax.usu.edu"
  CORS_ALLOWED_ORIGINS: "https://macfax.usu.edu"
```

Generate a secret key:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

### 5. Build and start

```bash
docker compose up -d --build
```

The backend startup command automatically runs:
- `python manage.py migrate`
- `python manage.py collectstatic --noinput`
- `python manage.py ensure_ncaa_teams`

### 6. One-time data setup

```bash
# Create Django admin superuser
docker compose exec backend python manage.py createsuperuser

# Seed conference data
docker compose exec backend python manage.py seed_conferences

# Import team logos into DB
docker compose exec backend python manage.py import_logos

# Run the full data pipeline (first run takes 5–15 minutes)
docker compose exec backend python manage.py update_ncaa_all --season 2026
```

---

## Reverse Proxy (nginx)

Example nginx config routing to the Docker containers:

```nginx
server {
    listen 443 ssl;
    server_name macfax.usu.edu;

    ssl_certificate     /etc/ssl/certs/macfax.crt;
    ssl_certificate_key /etc/ssl/private/macfax.key;

    # Next.js web app
    location / {
        proxy_pass http://localhost:7000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Django backend API (includes /api/admin/) + static
    location ~ ^/(api|static)/ {
        proxy_pass http://localhost:7001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 80;
    server_name macfax.usu.edu;
    return 301 https://$host$request_uri;
}
```

---

## Updating the Deployment

### Code updates

```bash
cd /opt/macfax
git pull
docker compose up -d --build
```

The build uses `--no-cache` implicitly when source files change. To force a full rebuild:
```bash
docker compose build --no-cache
docker compose up -d
```

### Data updates (daily)

```bash
docker compose exec backend python manage.py update_ncaa_all --season 2026
```

Set this up as a cron job for automatic updates:
```bash
crontab -e
```
```cron
0 6 * * * docker compose -f /opt/macfax/docker-compose.yml exec -T backend python manage.py update_ncaa_all --season 2026
```

---

## Environment Variables Reference

All variables are set in the `environment` block of each service in `docker-compose.yml`.

### Backend

| Variable | Description | Example |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgres://cbb_user:pass@db:5432/cbb_analytics` |
| `SECRET_KEY` | Django secret key | 50+ random chars |
| `DEBUG` | Django debug mode | `False` |
| `ALLOWED_HOSTS` | Comma-separated allowed hosts | `localhost,macfax.usu.edu` |
| `CORS_ALLOWED_ORIGINS` | Comma-separated CORS origins | `https://macfax.usu.edu` |
| `LOGOS_DIR` | Path to logos inside container | `/app/static/logos` (optional, auto-detected) |

### Web

| Variable | Where used | Value |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Browser client bundle (baked at build time) | `https://macfax.usu.edu` |
| `API_INTERNAL_URL` | Server-side Next.js fetches only | `http://macfax_api:7001` |
| `PORT` | Next.js listen port | `7000` |

> **Note:** `NEXT_PUBLIC_API_BASE_URL` must be passed as a Docker build **arg** (not just env) to be baked into the client-side bundle. See `web/Dockerfile` and the `build.args` in `docker-compose.yml`.

---

## Security Checklist

- [ ] `SECRET_KEY` is a unique random value (not `change-me`)
- [ ] `DEBUG=False`
- [ ] `ALLOWED_HOSTS` contains only your domain(s)
- [ ] `CORS_ALLOWED_ORIGINS` contains only your frontend origin(s)
- [ ] HTTPS enabled via reverse proxy
- [ ] Django admin has a strong password
- [ ] Database is not exposed externally (no ports mapping on `db` service)

---

## Useful Commands

```bash
# View logs
docker compose logs -f backend
docker compose logs -f web

# Shell into backend
docker compose exec backend bash

# Django shell
docker compose exec backend python manage.py shell

# Check service status
docker compose ps

# Restart a service
docker compose restart backend

# Stop everything
docker compose down

# Stop and remove volumes (WARNING: deletes database)
docker compose down -v
```
