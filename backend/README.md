# CBB Analytics - Django Backend

Django + Django REST Framework backend for College Basketball Analytics application.

## 🏗️ Architecture

- **Django 5.0** - Web framework
- **Django REST Framework** - API layer
- **SQLite** (dev) / **PostgreSQL** (production) - Database
- **Pandas** - Data ingestion from CSVs

## 📊 Database Schema

### Core Models

**Season** - Basketball seasons (e.g., 2025-26)
- year, display_name, is_current

**Conference** - NCAA conferences
- code (B10, ACC), name

**Team** - D1 basketball teams (365 teams)
- slug, name, aliases, logo_url

**TeamSeasonStats** - Main stats table
- Relations: team, season, conference
- Core metrics: adj_em, adj_o, adj_d, adj_tempo
- Four Factors: eFG%, TOV%, ORB%, FTR (offense + defense)
- Shooting splits: 2P%, 3P%, 3P rate
- Resume: WAB, SOR, Barthag, Luck, SOS
- Precomputed margins

**DataIngestionRun** - Audit log for data imports

## 🚀 Quick Start (Local Development)

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (fast Python package installer)
- SQLite (default, no setup needed)
- Redis (optional, for background job queue)

### Installation

```bash
# 1. Install uv (macOS/Linux)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or with Homebrew:
brew install uv

# 2. Clone and navigate to backend
cd backend

# 3. Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 4. Install project dependencies
uv pip install -e .  # Install from pyproject.toml

# Or for development with testing tools:
uv pip install -e ".[dev]"

# 5. Set up environment
cp .env.local .env  # Or create .env with your settings
```

### Database Setup

```bash
# Run migrations (creates SQLite database)
python manage.py migrate

# Create superuser (for Django admin)
python manage.py createsuperuser

# Load initial data (optional)
python manage.py ingest_gamelogs --season 2026 --source ncaa
```

### Run Development Server

```bash
# Start the development server
python manage.py runserver

# Server runs on http://localhost:8000
# API available at http://localhost:8000/api/
# Admin at http://localhost:8000/admin/

# Or specify a different port:
python manage.py runserver 8001
```

### Run Background Job Worker (Optional)

## 📡 API Endpoints

### Seasons
```
GET /api/seasons/
```

Returns list of all available seasons.

### Rankings
```
GET /api/rankings/?season=2026&sort=adj_em&dir=desc&conference=B10&search=mich
```

Query params:
- `season` - Season year (default: current)
- `sort` - Field to sort by (default: rank)
- `dir` - `asc` or `desc` (default: asc)
- `conference` - Conference code filter
- `search` - Team name search

### Teams
```
GET /api/teams/
GET /api/teams/{slug}/
GET /api/teams/{slug}/stats/?season=2026
GET /api/teams/{slug}/profile/?season=2026
```

### Matchup
```
GET /api/matchup/?season=2026&teamA=michigan&teamB=duke&site=neutral
```

Query params:
- `season` - Season year
- `teamA` - Team A slug
- `teamB` - Team B slug
- `site` - `neutral`, `home`, or `away`

Returns win probability, predicted margin, and key edges.

## 🧪 Testing

### Run Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest core/tests/test_models.py

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=core --cov=api
```

### Test Configuration

Tests are configured in `pyproject.toml`:
- Settings: `DJANGO_SETTINGS_MODULE = 'config.settings'`
- Database: SQLite test database
- Coverage: Generates HTML report in `htmlcov/`

## 🎨 Code Quality

Format and lint code before committing:

```bash
# Format code with Black (100 char line length)
black .

# Sort imports with isort (Django profile)
isort .

# Lint with Flake8 (ignore E501 line length, checked by Black)
flake8 . --max-line-length=100

# Run all checks
black . && isort . && flake8 . --max-line-length=100
```

## 🔧 Management Commands

### update_all

Runs complete data pipeline: ingest gamelogs → compute all metrics in parallel.

```bash
# Run with default settings (current season)
python manage.py update_all

# Specify season and parameters
python manage.py update_all --season 2026 --iterations 10 --sor-trials 5

# Run in serial mode (no Redis needed)
python manage.py update_all --serial
```

Jobs are tracked in `DataProcessingJob` model. Check admin panel or API for status.

### ingest_gamelogs

Ingests game logs for a season from CSV sources.

```bash
# Ingest NCAA games for season
python manage.py ingest_gamelogs --season 2026 --source ncaa

# Refresh existing data
python manage.py ingest_gamelogs --season 2026 --refresh
```

### Database Migrations

```bash
# Create migrations for model changes
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Check migration status
python manage.py showmigrations

# Rollback to specific migration
python manage.py migrate core 0001
```

## 🗄️ Django Admin

Access Django admin panel at `http://localhost:8000/admin/`

Features:
- **Seasons** - Create/edit basketball seasons
- **Teams** - View teams and their metadata
- **DataProcessingJob** - Monitor job execution (read-only)
- **TeamSeasonStats** - View computed team statistics

The job monitoring feature allows you to:
- Track long-running background jobs
- View progress percentage
- Read execution logs in real-time
- See error messages if jobs fail

## � Docker Deployment

### Build and Run with Docker Compose

```bash
# From root directory
docker compose up --build

# Run migrations in Docker
docker compose exec backend python manage.py migrate

# Create superuser in Docker
docker compose exec backend python manage.py createsuperuser

# View logs
docker compose logs -f backend

# Stop containers
docker compose down
```

### Services

- **db** - PostgreSQL 16 database
- **backend** - Django + Gunicorn
- **web** - Next.js frontend

Access:
- Admin: http://localhost:8000/admin/
- API: http://localhost:8000/api/
- Frontend: http://localhost:3000/

## ⚙️ Environment Configuration

### Local Development (.env.local)

```env
DEBUG=True
SECRET_KEY=django-insecure-dev-key-change-in-production
DATABASE_URL=sqlite:///db.sqlite3
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:3000
API_BASE_URL=http://localhost:8000
```

### Docker (.env.docker)

```env
DEBUG=False
SECRET_KEY=your-long-random-production-secret-key
DATABASE_URL=postgres://cbb:password@db:5432/cbb_analytics
ALLOWED_HOSTS=localhost,yourdomain.com
CORS_ALLOWED_ORIGINS=https://yourdomain.com
API_BASE_URL=https://yourdomain.com/api
```

### Key Settings

- **DEBUG** - Set to `False` in production
- **SECRET_KEY** - Use `django-insecure-*` prefix only in development
- **DATABASE_URL** - SQLite for local, PostgreSQL for production
- **REDIS_URL** - Optional; jobs run serially if unavailable
- **ALLOWED_HOSTS** - Comma-separated list of allowed domains
- **CORS_ALLOWED_ORIGINS** - Frontend URL for API requests

## 📁 Project Structure

```
backend/
├── config/              # Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── core/                # Core models
│   ├── models.py
│   ├── admin.py
│   └── management/
│       └── commands/
│           └── ingest_data.py
├── api/                 # DRF API
│   ├── serializers.py
│   ├── views.py
│   └── urls.py
├── manage.py
├── requirements.txt
└── .env
```

## 🔍 Troubleshooting

**CORS errors:**
- Check `CORS_ALLOWED_ORIGINS` in `.env`
- Ensure frontend URL is included

**Data not loading:**
- Check CSV paths in `ingest_data` command
- Verify season year matches CSV data
- Check Django admin for ingestion logs

**Database errors:**
- Run `python manage.py migrate`
- Check DATABASE_URL in `.env`

## 🛠️ Development

### Run tests
```bash
python manage.py test
```

### Create new migration
```bash
python manage.py makemigrations
python manage.py migrate
```

### Shell access
```bash
python manage.py shell
```

## 📝 License

See root LICENSE file.
