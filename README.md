# College Basketball Analytics Dashboard

A full-stack web application for advanced college basketball analytics, serving live game data and KenPom-style adjusted efficiency ratings for NCAA Division I and NBA via a self-hosted Docker deployment.

**Production:** [macfax.usu.edu](https://macfax.usu.edu)

---

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│  Docker (macfax_web network)                                   │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌────────┐  ┌──────┐ │
│  │  Next.js 14  │───▶│  Django 5    │───▶│ Postgres│  │Redis │ │
│  │  :7000       │    │  :7001       │    │  :5432  │  │:6379 │ │
│  │  (web)       │    │  (backend)   │    │  (db)   │  │(cache)│ │
│  └──────────────┘    └──────────────┘    └────────┘  └──────┘ │
└───────────────────────────────────────────────────────────────┘
```

- **Web** (`/web`) — Next.js 14, TypeScript, Tailwind CSS. Fetches all data from the Django REST API at runtime; no static data files.
- **Backend** (`/backend`) — Django 5 REST API. Ingests game data from NCAA and NBA APIs, computes adjusted efficiency ratings, serves team/game/rankings data.
- **Database** — PostgreSQL 16 (Docker) / local dev uses `.env.local` settings.
- **Cache** — Redis for caching API responses and improving performance.
- **Static files** — Served by WhiteNoise on the Django backend at `/static/`. Team logos live in `backend/static/logos/` and are proxied through Next.js at `/static/logos/`.

---

## Quick Start

See **[docs/QUICK_START.md](docs/QUICK_START.md)** for full setup instructions.

**Docker (production-style):**
```bash
docker compose up -d
```

**Local development:**
```bash
# Backend
cd backend && uv run python manage.py runserver

# Frontend (separate terminal)
cd web && npm run dev
```

---

## Data Pipeline

Data flows from both NCAA and NBA APIs through the Django backend. There are no CSV files or static data builds.

```
NCAAA Stats API / NBA API
    └── ingest_gamelogs          # fetch game results + box scores
        └── compute_team_metrics # aggregate raw four-factor stats
            └── compute_national_averages
                └── compute_adjusted_ratings  # iterative AdjO/AdjD/AdjEM
                    └── compute_adjusted_four_factors
                        └── compute_four_factor_index
                            └── fetch_net_rankings
                                └── compute_sor
                                    └── compute_game_value
                                        └── compute_sos
```

Run the entire pipeline:
```bash
python manage.py update_all --season 2026
```

See **[docs/DATA_PIPELINE.md](docs/DATA_PIPELINE.md)** for the full management command reference.

---

## Key Features

- **Rankings** — Sortable table with all 365 D1 teams and advanced metrics
- **Team Profiles** — Detailed pages with tabs: Overview, Four Factors, Off/Def, Resume, Charts
- **Matchup Tool** — Head-to-head win probability with Four Factor breakdown
- **Visualizations** — Efficiency landscape, Trapezoid of Excellence, scatter builder
- **Glossary** — Metric definitions with LaTeX formulas

---

## Project Structure

```
CBB-Analytical-Dashboard/
├── README.md
├── docker-compose.yml            # Production Docker services
│
├── backend/                      # Django REST API
│   ├── config/                   # Django settings, URLs, WSGI
│   ├── core/                     # Main app: models, management commands
│   │   ├── models.py
│   │   ├── management/commands/  # Pipeline commands (update_all, ingest_gamelogs, etc.)
│   │   └── utils/                # NCAA API client, team mapping
│   ├── api/                      # REST endpoints, serializers, views
│   ├── static/logos/             # Team logo PNG files (served via WhiteNoise)
│   ├── mappings/                 # Team name/alias YAML files
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── manage.py
│
├── web/                          # Next.js 14 frontend
│   ├── src/
│   │   ├── app/                  # App Router pages
│   │   ├── components/           # React components
│   │   └── lib/                  # API client (api.ts), data layer (data.ts), types
│   ├── public/brand/             # MacFax brand assets (logo, marks)
│   ├── next.config.js            # Includes /static/* proxy rewrite to backend
│   ├── Dockerfile
│   └── package.json
│
└── docs/                         # Documentation
    ├── QUICK_START.md
    ├── DEPLOYMENT.md
    ├── DATA_PIPELINE.md
    ├── FOUR_FACTOR_INDEX_GUIDE.md
    └── ADJUSTED_RATINGS.md
```

---

## API Endpoints

Base URL: `https://macfax.usu.edu/api/` (production) | `http://localhost:8000/api/` (local)

| Endpoint | Description |
|---|---|
| `GET /rankings/?season=2026` | All teams with ratings, metrics, and rankings |
| `GET /teams/` | Team list |
| `GET /teams/{slug}/` | Team detail |
| `GET /games/?season=2026` | Game results |
| `GET /conferences/` | Conference list |
| `GET /matchup/?teamA=duke&teamB=kansas&site=neutral` | Win probability |
| `GET /viz/stats/` | Stat catalog for viz builder |
| `GET /viz/scatter/?x=adj_em&y=efg_pct` | Scatter plot data |
| `GET /viz/landscape/` | Efficiency landscape data |
| `GET /viz/trapezoid/` | Four Factors trapezoid data |
| `GET /jobs/` | Data processing job status |

Django admin: `/admin/`

---

## Technology Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 14, React 18, TypeScript, Tailwind CSS |
| Backend | Django 5.0.1, Django REST Framework |
| Database | PostgreSQL 16 |
| Cache | Redis |
| Static files | WhiteNoise 6.6 |
| Team matching | rapidfuzz |
| Containerization | Docker, Docker Compose |
| Python tooling | uv |

---

## Documentation

- **[docs/QUICK_START.md](docs/QUICK_START.md)** — Local dev and Docker setup
- **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** — Production Docker deployment
- **[docs/DATA_PIPELINE.md](docs/DATA_PIPELINE.md)** — Management commands reference
- **[docs/FOUR_FACTOR_INDEX_GUIDE.md](docs/FOUR_FACTOR_INDEX_GUIDE.md)** — Four Factor Index methodology
- **[docs/ADJUSTED_RATINGS.md](docs/ADJUSTED_RATINGS.md)** — Adjusted ratings methodology
