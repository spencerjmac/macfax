# 🏀 College Basketball Analytics Dashboard

A full-stack web application for advanced college basketball analytics with live game data and KenPom-style adjusted efficiency ratings.

## 🎯 Overview

This is a production-ready analytics platform featuring:
- **Live game data** from NCAA API (5,000+ games ingested)
- **Adjusted efficiency ratings** using iterative opponent-adjustment methodology
- **Four Factor analysis** with z-score normalization
- **Interactive web interface** built with Next.js 14 and TypeScript
- **Django REST API** backend with SQLite database

### Quick Links
- **Documentation**: [docs/](docs/)
- **Quick Start**: [docs/QUICK_START.md](docs/QUICK_START.md)
- **API Documentation**: [backend/docs/](backend/docs/)
- **Deployment Guide**: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

---

## 🚀 Key Features

### Web Application (`/web`)
Next.js 14 application with TypeScript and Tailwind CSS:

**Core Pages:**
1. **Rankings** - Sortable table with 365 D1 teams + advanced metrics
2. **Team Profiles** - Detailed multi-tab team pages
3. **Game Logs** - Complete season schedules with box scores
4. **Four Factors** - eFG%, TOV%, REB%, FTR analysis
5. **Glossary** - Metric definitions and methodology

**Visualizations:**
- Trapezoid of Excellence (Four Factors)
- Efficiency ratings and tempo analysis
- Win-loss records with strength metrics

### Django Backend (`/backend`)
Django 6.0 REST API with comprehensive data models:

**Data Pipeline:**
1. **`ingest_gamelogs`** - NCAA API scraper with box scores (5,000+ games)
2. **`compute_team_metrics`** - Aggregate season statistics
3. **`compute_adjusted_ratings`** - Iterative opponent-adjustment (correct method)
4. **`compute_four_factor_index`** - Z-score normalized four factors

**Key Models:**
- `Game` - Game results with scores
- `TeamGameStats` - Box score statistics (FG, 3PT, FT, rebounds, etc.)
- `TeamSeasonMetrics` - Aggregate raw metrics (eFG%, TOV%, etc.)
- `TeamSeasonRatings` - Adjusted efficiency ratings (AdjO, AdjD, AdjEM)

### Data Coverage
- **365 NCAA Division I teams**
- **2025-26 season** (Nov 2025 - Feb 2026)
- **5,327 games** (5,260 final, 67 scheduled)
- **Updated through:** February 26, 2026

## 🚀 Quick Start

### Prerequisites

- **Python 3.14** (or compatible version)
- **Node.js 18+** and npm
- **Git** for version control

### Setup (5 minutes)

**1. Clone and setup virtual environment:**
```powershell
cd "CBB Analytical Dashboard"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**2. Backend setup:**
```powershell
cd backend
pip install -r requirements.txt
copy .env.example .envpy
python manage.py migrate
```

**3. Frontend setup:**
```powershell
cd ..\web
npm install
copy .env.local.example .env.local
```

**4. Start servers:**
```powershell
# Terminal 1 - Backend (Django)
cd backend
python manage.py runserver

# Terminal 2 - Frontend (Next.js)
cd web
npm run dev
```

`npm run dev` in `web` now auto-runs the data build first, so `web/public/data/teams.json` is refreshed from the latest backend data before the frontend starts.

Visit **http://localhost:3000** to see the dashboard!

### Updating Data

**Ingest latest games:**
```powershell
cd backend
python manage.py ingest_gamelogs --start-date 2026-02-21 --end-date 2026-02-26
python manage.py compute_team_metrics --season 2025-26
python manage.py compute_adjusted_ratings --season 2025-26
python manage.py compute_four_factor_index --season 2025-26
```

**Or use the complete pipeline script:**
```powershell
cd backend
python scripts/complete_pipeline.py
```

See [docs/QUICK_START.md](docs/QUICK_START.md) for detailed setup instructions.

## 📁 Project Structure

```
CBB Analytical Dashboard/
├── README.md                          # This file
├── .gitignore                        # Git ignore rules
├── .venv/                            # Python virtual environment
│
├── backend/                          # Django REST API
│   ├── scripts/                      # Utility scripts
│   │   ├── complete_pipeline.py      # Full data pipeline
│   │   ├── backfill_season.py        # Weekly backfill utility
│   │   ├── validate_pipeline.py      # Validation script
│   │   ├── export_rankings_to_json.py # Export utility
│   │   ├── update_logos_fixed.py     # Logo updater
│   │   ├── preflight_check.py        # System validation
│   │   └── create_external_ids.py    # Setup utility
│   │
│   ├── core/                         # Main Django app
│   │   ├── models.py                 # Data models (Game, TeamStats, etc.)
│   │   ├── management/commands/      # Django commands
│   │   │   ├── ingest_gamelogs.py    # NCAA API scraper
│   │   │   ├── compute_team_metrics.py # Season aggregation
│   │   │   ├── compute_adjusted_ratings.py # Efficiency ratings ✅
│   │   │   ├── compute_four_factor_index.py # Four Factors
│   │   │   └── compute_national_averages.py # League averages
│   │   └── ...
│   │
│   ├── api/                          # REST API endpoints
│   │   ├── views.py                  # API views
│   │   ├── serializers.py            # JSON serializers
│   │   └── urls.py                   # API routes
│   │
│   ├── config/                       # Django settings
│   ├── docs/                         # API documentation
│   ├── manage.py                     # Django CLI
│   ├── db.sqlite3                    # Database (5,327 games)
│   ├── requirements.txt              # Python dependencies
│   ├── ncaa_team_name_mappings.yml   # Team name mappings
│   └── team_alias_overrides.yml      # Name overrides
│
├── web/                              # Next.js frontend
│   ├── src/
│   │   ├── app/                      # Next.js App Router
│   │   │   ├── page.tsx              # Home page
│   │   │   ├── rankings/             # Rankings page
│   │   │   ├── teams/                # Team profiles
│   │   │   └── ...
│   │   ├── components/               # React components
│   │   │   ├── RankingsTable.tsx     # Sortable table
│   │   │   ├── FourFactorsTrapezoid.tsx # Trapezoid viz
│   │   │   └── ...
│   │   └── lib/                      # Utilities
│   ├── public/                       # Static assets
│   ├── package.json                  # Node dependencies
│   └── next.config.js                # Next.js config
│
├── docs/                             # Documentation
│   ├── QUICK_START.md                # Setup guide
│   ├── GAME_LOG_QUICK_START.md       # Game log pipeline guide
│   ├── FOUR_FACTOR_INDEX_GUIDE.md    # FFI methodology
│   ├── DEPLOYMENT.md                 # Production deployment
│   └── PROJECT_README.md             # Detailed project overview
│
└── [Data Folders]                    # Historical data sources
    ├── Bart Torvik/                  # Torvik data
    ├── KenPom Data/                  # KenPom data
    ├── Evan Miya/                    # Evan Miya data
    └── ESPN AP Poll/                 # AP Poll data
```

## 📊 Data Pipeline

### NCAA Game Log Ingestion

**Primary Data Source:** NCAA.com Stats API  
**Status:** ✅ Working reliably  
**Coverage:** All 365 D1 teams, full season  
**Update Frequency:** Run after each game day

**Pipeline Flow:**
```
NCAA API → ingest_gamelogs → compute_team_metrics → compute_adjusted_ratings
```

**What's Captured:**
- Game results (scores, dates, locations)
- Complete box scores (FG, 3PT, FT, rebounds, assists, turnovers, etc.)
- Play-by-play events (scoring runs, etc.)
- Team identification with fuzzy name matching
- Automatic handling of duplicates via `update_or_create()`

### Key Metrics Calculated

**Adjusted Efficiency Ratings** (KenPom-style):
- **AdjO** - Adjusted Offensive Efficiency (points per 100 possessions)
- **AdjD** - Adjusted Defensive Efficiency (points allowed per 100 possessions)
- **AdjEM** - Adjusted Efficiency Margin (AdjO - AdjD)
- **AdjT** - Adjusted Tempo (possessions per 40 minutes)
- **Methodology:** Iterative opponent-adjustment (15 iterations to convergence)

**Four Factors** (Dean Oliver):
- **eFG%** - Effective Field Goal Percentage: `(FGM + 0.5 * 3PM) / FGA`
- **TOV%** - Turnover Percentage: `TOV / (FGA + 0.44 * FTA + TOV)`
- **ORB%** - Offensive Rebound Percentage: `ORB / (ORB + Opp DRB)`
- **FTR** - Free Throw Rate: `FT / FGA`
- **Z-Score Normalized:** Standardized to league averages

**Raw Season Metrics:**
- Offensive/Defensive Ratings (per 100 possessions)
- Pace (possessions per game)
- Win-Loss records
- Conference standings

### Data Quality

**Validation Checks:**
- ✅ All 365 D1 teams mapped with NCAA IDs
- ✅ Fuzzy name matching with 95%+ accuracy
- ✅ Conference alignments verified
- ✅ Historical game data retained
- ✅ No duplicate games (unique on `ncaa_game_id`)

**Current Database Status:**
- **Total Games:** 5,327
- **Final Games:** 5,260 (98.7%)
- **Scheduled:** 67 (1.3%)
- **Season:** 2025-26 (Nov 4, 2025 - Feb 26, 2026)
- **Teams with Ratings:** 365/365 (100%)

## � Technology Stack

### Backend
- **Framework:** Django 6.0 (Python 3.14)
- **Database:** SQLite (5,327 games, 365 teams)
- **API:** Django REST Framework
- **Scraping:** Requests + BeautifulSoup4 (NCAA API)
- **Team Matching:** FuzzyWuzzy (Levenshtein distance)

### Frontend
- **Framework:** Next.js 14 (React 18)
- **Language:** TypeScript
- **Styling:** Tailwind CSS
- **UI Components:** Headless UI
- **Charts:** Recharts (coming soon)
- **Deployment:** Vercel-ready

### Data Processing
- **Pandas** - Data manipulation
- **NumPy** - Numerical computations
- **SciPy** - Statistical analysis (z-scores)
- **YAML** - Configuration files

## 🔗 API Endpoints

Base URL: `http://localhost:8000/api/`

**Teams:**
- `GET /teams/` - List all 365 teams
- `GET /teams/{id}/` - Team details
- `GET /teams/{id}/ratings/` - Season ratings
- `GET /teams/{id}/metrics/` - Season metrics
- `GET /teams/{id}/games/` - Game log

**Games:**
- `GET /games/` - List games (filterable by date, team, status)
- `GET /games/{id}/` - Game details with box scores

**Rankings:**
- `GET /rankings/` - Current rankings with all metrics
- Query params: `?season=2025-26&order_by=-adj_em`

**Stats:**
- `GET /national-averages/` - League-wide averages
- `GET /four-factors/` - Four Factors for all teams

See [backend/docs/](backend/docs/) for detailed API documentation.

## ⚙️ Django Management Commands

### Essential Commands

**Data Ingestion:**
```powershell
# Ingest games for date range
python manage.py ingest_gamelogs --start-date 2026-02-21 --end-date 2026-02-26

# Force refresh (re-scrape existing games)
python manage.py ingest_gamelogs --start-date 2026-02-21 --end-date 2026-02-26 --refresh
```

**Metrics Computation:**
```powershell
# Compute raw season metrics (eFG%, TOV%, etc.)
python manage.py compute_team_metrics --season 2025-26

# Compute national averages (required for Four Factors)
python manage.py compute_national_averages --season 2025-26

# Compute adjusted ratings (AdjO, AdjD, AdjEM) ✅ USE THIS ONE
python manage.py compute_adjusted_ratings --season 2025-26

# Compute Four Factor Index (z-scores)
python manage.py compute_four_factor_index --season 2025-26
```

**⚠️ Important:** Always use `compute_adjusted_ratings` (iterative method). Do NOT use `compute_game_adjusted_ratings` (ridge regression) - it has scaling issues.

### Utility Scripts

Located in `backend/scripts/`:

```powershell
# Run complete pipeline (ingest → metrics → ratings)
python scripts/complete_pipeline.py

# Backfill entire season in weekly chunks
python scripts/backfill_season.py

# Validate pipeline execution
python scripts/validate_pipeline.py

# Export rankings to JSON
python scripts/export_rankings_to_json.py
```

## 🎓 Use Cases

- **Live Game Tracking:** Ingest and display games in real-time
- **Team Performance Analysis:** Compare efficiency metrics across all teams
- **Four Factors Analysis:** Identify team strengths/weaknesses
- **Conference Strength:** Aggregate team metrics by conference
- **Historical Trends:** Track team performance over time
- **Tournament Predictions:** Multi-factor models using adjusted ratings
- **Recruiting Analytics:** Identify undervalued programs

## 🐛 Known Issues & Notes

### Data Pipeline
- **NCAA API Reliability:** Generally stable, occasional timeouts (retry recommended)
- **Fuzzy Matching:** 95%+ accuracy, manual overrides in `team_alias_overrides.yml`
- **Duplicate Prevention:** All games use `update_or_create()` - safe to re-run
- **Incremental Updates:** Just ingest new dates and re-compute metrics

### Performance
- **Low RAM Systems:** Next.js dev mode uses 500MB-1GB (use production build if needed)
- **Large API Responses:** 365 teams = ~500KB JSON (consider pagination for production)
- **Database Size:** SQLite ~100-200MB for full season

### Deployment
- **Database:** SQLite OK for single-user, consider PostgreSQL for production
- **Static Files:** Serve via CDN in production
- **Environment Variables:** Set `DEBUG=False` and `SECRET_KEY` in production

## 📅 Development Workflow

**Daily Update Workflow:**
```powershell
# 1. Activate virtual environment
.\.venv\Scripts\Activate.ps1

# 2. Ingest yesterday's games
cd backend
python manage.py ingest_gamelogs --start-date 2026-02-26 --end-date 2026-02-26

# 3. Update metrics and ratings
python manage.py compute_team_metrics --season 2025-26
python manage.py compute_adjusted_ratings --season 2025-26
python manage.py compute_four_factor_index --season 2025-26

# 4. Verify on website
# Backend: http://localhost:8000
# Frontend: http://localhost:3000
```

**Adding New Features:**
1. Update Django models in `backend/core/models.py`
2. Create/update management commands as needed
3. Add API endpoints in `backend/api/views.py`
4. Update frontend components in `web/src/components/`
5. Test locally before deploying

## 🚢 Deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for production deployment guide.

**Quick Deploy:**
- **Backend:** Railway, Render, or DigitalOcean App Platform
- **Frontend:** Vercel (recommended), Netlify, or AWS Amplify
- **Database:** PostgreSQL (Railway/Render) or keep SQLite and copy file

## 📚 Documentation

- **[Quick Start Guide](docs/QUICK_START.md)** - Complete setup instructions
- **[Game Log Guide](docs/GAME_LOG_QUICK_START.md)** - Data pipeline details
- **[Four Factor Guide](docs/FOUR_FACTOR_INDEX_GUIDE.md)** - Calculation methodology
- **[Project Overview](docs/PROJECT_README.md)** - Detailed architecture
- **[Deployment Guide](docs/DEPLOYMENT.md)** - Production deployment
- **[Backend Scripts](backend/scripts/README.md)** - Utility script documentation

## 🤝 Contributing

This is an active college basketball analytics project. Key areas for contribution:
- Additional visualizations (efficiency landscape, shot charts, etc.)
- Advanced metrics (BPR, RAPM, etc.)
- Matchup predictor tool
- Historical season comparison
- Conference tournament simulations

## 📧 Support

For issues or questions:
- **Data Pipeline:** See [GAME_LOG_QUICK_START.md](docs/GAME_LOG_QUICK_START.md)
- **API Endpoints:** Check [backend/docs/](backend/docs/)
- **Frontend Components:** See [web/README.md](web/README.md)
- **General Setup:** See [QUICK_START.md](docs/QUICK_START.md)

---

**Last Updated:** February 26, 2026  
**Python Version:** 3.14  
**Django Version:** 6.0.2  
**Next.js Version:** 14.2.35  
**Database:** SQLite (5,327 games, 365 teams)
