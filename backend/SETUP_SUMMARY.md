# Backend Setup Summary

## ✅ What's Been Set Up

Your Django backend is now fully organized for both local development and Docker deployment.

### Files Created/Modified

#### 1. **pyproject.toml** - Python Project Configuration
- Defines project metadata and dependencies
- Supports `uv` package manager
- Includes dev tools: black, flake8, isort, pytest-django
- Standardizes dependency management across team

**Key sections:**
- `[build-system]` - Uses hatchling build backend
- `[project]` - Name, version, description, Python requirement (>=3.11)
- `[project.optional-dependencies]` - Dev tools grouped separately
- `[tool.*]` - Configuration for black, isort, pytest, coverage

#### 2. **requirements.txt** - Docker Dependencies
- Pinned versions of all packages for reproducible Docker builds
- Auto-generated from pyproject.toml using `uv pip compile`
- Comment header explains how to regenerate if needed

**Usage:**
```bash
# Docker uses this:
pip install -r requirements.txt

# Developers use this:
uv pip install -e ".[dev]"
```

#### 3. **.env.local** - Local Development Environment
- SQLite database by default (no PostgreSQL setup needed)
- DEBUG=True for development
- REDIS_URL for optional job queue testing
- CORS configured for localhost:3000

**Key settings:**
```
DATABASE_URL=sqlite:///db.sqlite3  # No external DB needed
DEBUG=True
SECRET_KEY=dev-key-only
```

#### 4. **.env.example** - Template for Environment
- Shows all available environment variables
- Includes helpful comments
- Copy to .env to customize

#### 5. **DEVELOPMENT.md** - Complete Local Setup Guide
- Step-by-step installation instructions
- Virtual environment setup with uv
- Database migration commands
- Testing and code quality workflow
- Troubleshooting common issues
- Advanced setup (PostgreSQL, VS Code, etc.)

#### 6. **0019_dataprocessingjob.py** - Database Migration
- Creates `core_dataprocessingjob` table for job tracking
- Fields: job_id, job_type, status, progress_percent, logs, etc.
- Automatically applied when running migrations

#### 7. **Updated README.md** - Main Documentation
- Quick start section updated for uv/pyproject.toml
- Local dev instructions with SQLite
- Docker Compose deployment guide
- API endpoints and management commands
- Environment variable configuration
- Testing and code quality sections

---

## 🚀 Quick Start

### First Time Setup (5 minutes)

```bash
cd backend

# Install uv (if not already installed)
# See DEVELOPMENT.md for platform-specific instructions

# Set up virtual environment
uv venv
source .venv/bin/activate

# Install dependencies
uv pip install -e ".[dev]"

# Configure environment
cp .env.local .env

# Initialize database
python manage.py migrate

# Create admin account
python manage.py createsuperuser

# Start development server
python manage.py runserver
```

Access:
- **Django Admin:** http://localhost:8000/admin/
- **API:** http://localhost:8000/api/

### Ongoing Development

```bash
# Activate environment each session
source .venv/bin/activate

# Start server
python manage.py runserver

# Make changes
# - Models: Create migrations
# - Code: Auto-reloads on save
# - Tests: Run pytest

# Before committing
black . && isort . && flake8 .
pytest
git push
```

---

## 📦 Dependency Management

### Adding New Packages

```bash
# Add to pyproject.toml [project.dependencies] section

# Update requirements.txt
uv pip compile pyproject.toml -o requirements.txt

# Install in virtual environment
uv pip install -e ".[dev]"
```

### Core Dependencies Included

| Package | Version | Purpose |
|---------|---------|---------|
| Django | 5.0.1 | Web framework |
| djangorestframework | 3.14.0 | REST API |
| psycopg2-binary | 2.9.9 | PostgreSQL driver |
| pandas | 2.2.0 | Data processing |
| gunicorn | 21.2.0 | WSGI server |
| whitenoise | 6.6.0 | Static files in production |
| dj-database-url | 2.1.0 | Database URL parsing |
| django-cors-headers | 4.3.1 | CORS support |

### Dev Dependencies Included

| Package | Purpose |
|---------|---------|
| black | Code formatting |
| flake8 | Linting |
| isort | Import sorting |
| pytest | Testing framework |
| pytest-django | Django test support |
| coverage | Test coverage reports |

---

## 🗄️ Database Configuration

### Local Development
- **Database:** SQLite (file-based, no setup needed)
- **Location:** `backend/db.sqlite3` (auto-created)
- **Migrations:** Apply with `python manage.py migrate`

### Docker
- **Database:** PostgreSQL 16 (in docker-compose.yml)
- **Connection:** Via `DATABASE_URL` environment variable
- **Migrations:** Applied automatically on container start

### Using PostgreSQL Locally

Want to test PostgreSQL locally? Update `.env`:

```bash
DATABASE_URL=postgres://user:password@localhost:5432/cbb_analytics
```

Then run migrations:
```bash
python manage.py migrate
```

---

## 🔄 Migration Workflow

### Create New Migrations

```bash
# After modifying models.py
python manage.py makemigrations

# Review the generated migration file
# Apply to database
python manage.py migrate
```

### Check Status

```bash
# See which migrations have been applied
python manage.py showmigrations

# Check for issues
python manage.py check
```

### Included Migrations

Your backend already has 19 migrations:
1. Initial schema
2. Adjusted ratings fields
3. Margin z-scores and other stats
4. Game log pipeline
5. National averages
6. Team ratings enhancements
7. Metrics and derived fields
8. Matchup prediction fields
9. Four factor coefficients
10. WAB (Wins Above Bubble)
11. SOR and NET rankings
12. Game value metrics
13. Strength of Schedule ranks
14. **NEW:** DataProcessingJob model for job tracking

---

## 🧪 Testing

### Run Tests

```bash
# All tests
pytest

# Specific file
pytest core/tests/test_models.py

# With verbose output
pytest -v

# Coverage report
pytest --cov=core --cov=api --cov-report=html
```

### Write Tests

Create `backend/core/tests/test_yourmodule.py`:

```python
import pytest
from django.test import TestCase
from core.models import Team, Season

class TeamTestCase(TestCase):
    def setUp(self):
        Season.objects.create(year=2026)
        Team.objects.create(name="Michigan", slug="michigan")

    def test_team_creation(self):
        team = Team.objects.get(slug="michigan")
        self.assertEqual(team.name, "Michigan")
```

Run with:
```bash
pytest core/tests/test_yourmodule.py
```

---

## 📋 Code Quality

### Format Code

```bash
# Format with Black (100 char lines)
black .

# Sort imports with isort
isort .

# Check with Flake8
flake8 . --max-line-length=100
```

### Pre-commit

Before pushing:
```bash
black . && isort . && flake8 . --max-line-length=100 && pytest
```

---

## 🐳 Docker Deployment

### Build and Run

```bash
# From root directory (not backend/)
docker compose up --build

# In another terminal
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser
```

### Services

- **db** - PostgreSQL 16 (port 5432)
- **backend** - Django + Gunicorn (port 8000)
- **web** - Next.js frontend (port 3000)

### View Logs

```bash
docker compose logs -f backend
docker compose logs -f web
docker compose logs -f db
```

### Stop Containers

```bash
docker compose down
```

---

## 📚 Documentation Files

| File | Purpose |
|------|---------|
| **README.md** | Main documentation, API endpoints, quick start |
| **DEVELOPMENT.md** | Detailed local setup guide with troubleshooting |
| **pyproject.toml** | Project metadata and dependency definitions |
| **.env.example** | Template showing all configuration options |
| **.env.local** | Actual local development settings (git-ignored) |
| **requirements.txt** | Pinned dependencies for Docker builds |

---

## 🔐 Security Notes

### Local Development
- `SECRET_KEY` - Safe local value, never commit
- `DEBUG=True` - OK for local development only
- `ALLOWED_HOSTS` - Set to localhost/127.0.0.1
- `.env` file is git-ignored, never committed

### Production (Docker)
- `SECRET_KEY` - Use strong random value
- `DEBUG=False` - Always for production
- `ALLOWED_HOSTS` - Specific domains only
- Store `.env.docker` securely (not in git)

Generate a production SECRET_KEY:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

## 🛠️ Common Tasks

### Create a New App

```bash
python manage.py startapp myapp

# Add to INSTALLED_APPS in config/settings.py
# Create models, views, urls, admin
```

### Access Django Shell

```bash
python manage.py shell

# Now you can interact with models
from core.models import Team, Season
teams = Team.objects.all()
season = Season.objects.current()
```

### Dump Database

```bash
# Export data
python manage.py dumpdata > dump.json

# Load data
python manage.py loaddata dump.json
```

### Collect Static Files

```bash
# For production builds
python manage.py collectstatic --noinput
```

---

## 📖 Next Steps

1. ✅ **Review this summary** - You are here
2. 📖 **Read DEVELOPMENT.md** - Detailed setup guide
3. 🚀 **Run setup commands** - Follow quick start above
4. 🧪 **Try making a change** - Modify a model, create migration
5. 📝 **Write a test** - Add test for your change
6. 📤 **Commit and push** - Follow git workflow

---

## 💬 Need Help?

- **Setup issues?** → Check DEVELOPMENT.md Troubleshooting section
- **Django questions?** → [Django Docs](https://docs.djangoproject.com/)
- **DRF questions?** → [DRF Docs](https://www.django-rest-framework.org/)
- **Project specific?** → Check README.md

---

## 🎉 You're All Set!

Your backend is ready for:
- ✅ Local development with SQLite
- ✅ Python package management with uv
- ✅ Testing with pytest
- ✅ Code quality with black/flake8
- ✅ Admin-triggered data jobs (synchronous)
- ✅ Docker deployment with PostgreSQL
- ✅ Real-time admin dashboard for job monitoring

Happy coding! 🚀
