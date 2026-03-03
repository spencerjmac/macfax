# Local Development Setup

This guide will help you set up the CBB Analytics Django backend for local development.

## Prerequisites

- **Python 3.11+** - [Download](https://www.python.org/downloads/)
- **uv** - Fast Python package installer from Astral
- **Git** - [Download](https://git-scm.com/)
- **Redis** (optional) - For background job queue testing

## Step 1: Install uv

### macOS/Linux

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then add uv to your PATH:
```bash
export PATH="$HOME/.cargo/bin:$PATH"
```

### Windows

```bash
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Homebrew (macOS)

```bash
brew install uv
```

### Verify Installation

```bash
uv --version
# Should output something like: uv 0.1.0
```

## Step 2: Clone Repository

```bash
git clone https://github.com/your-repo/cbb-analytics.git
cd CBB-Analytical-Dashboard
```

## Step 3: Set Up Virtual Environment

```bash
cd backend

# Create virtual environment with uv
uv venv

# Activate it
source .venv/bin/activate  # macOS/Linux
# or
.venv\Scripts\activate  # Windows
```

## Step 4: Install Dependencies

### Option A: Development Setup (with testing tools)

```bash
uv pip install -e ".[dev]"
```

This installs:
- Core dependencies: Django, DRF, pandas, etc.
- Dev tools: pytest, pytest-django, black, flake8, isort

### Option B: Production-like Setup

```bash
uv pip install -e .
```

## Step 5: Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Or copy the local development version
cp .env.local .env
```

Edit `.env` if needed (defaults work for local dev):

```bash
DEBUG=True
SECRET_KEY=django-insecure-local-dev-key
DATABASE_URL=sqlite:///db.sqlite3
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:3000
```

## Step 6: Initialize Database

```bash
# Run migrations
python manage.py migrate

# Create superuser account for admin panel
python manage.py createsuperuser

# (Optional) Load sample data
# python manage.py ingest_gamelogs --season 2026
```

## Step 7: Start Development Server

```bash
# Start Django dev server
python manage.py runserver

# Server will be available at:
# - Development: http://localhost:8000/
# - Admin panel: http://localhost:8000/admin/
# - API: http://localhost:8000/api/
```

## Development Workflow

### 1. Make Code Changes

Edit files as needed, changes auto-reload on save.

### 2. Create Database Migrations

If you modify models:

```bash
python manage.py makemigrations
python manage.py migrate
```

### 3. Run Tests

```bash
# All tests
pytest

# Specific file
pytest core/tests/test_models.py

# With coverage
pytest --cov=core --cov=api
```

### 4. Format Code

Before committing, format your code:

```bash
# Format with Black
black .

# Sort imports
isort .

# Lint with Flake8
flake8 . --max-line-length=100
```

### 5. Commit and Push

```bash
git add .
git commit -m "Your commit message"
git push origin feature/branch-name
```

## Common Commands

### Django Management

```bash
# Run migrations
python manage.py migrate

# Create new migration
python manage.py makemigrations

# Django shell
python manage.py shell

# Create superuser
python manage.py createsuperuser

# Check for issues
python manage.py check

# Collect static files
python manage.py collectstatic --noinput
```

### Data Pipeline

```bash
# Ingest game logs for a season
python manage.py ingest_gamelogs --season 2026

# Run full update (parallel with Redis, serial without)
python manage.py update_all --season 2026

# Force serial execution
python manage.py update_all --season 2026 --serial
```

### Useful Django Admin URLs

```
http://localhost:8000/admin/              # Admin home
http://localhost:8000/admin/core/season/  # Manage seasons
http://localhost:8000/admin/core/team/    # Manage teams
http://localhost:8000/admin/core/dataprocessingjob/  # Monitor jobs
```

## Troubleshooting

### Virtual Environment Issues

**Problem:** `command not found: python`

**Solution:** Make sure virtual environment is activated:
```bash
source .venv/bin/activate
```

### Database Errors

**Problem:** `no such table: core_team`

**Solution:** Run migrations:
```bash
python manage.py migrate
```

### Port 8000 Already in Use

**Problem:** `Address already in use`

**Solution:** Use different port:
```bash
python manage.py runserver 8001
```

### Redis Connection Errors

**Problem:** Jobs run in serial mode instead of parallel

**Solution:** Redis is optional. Either:
1. Install and start Redis (see above)
2. Use `--serial` flag to explicitly run serially
3. Check REDIS_URL in .env matches your setup

### Import Errors

**Problem:** `ModuleNotFoundError: No module named 'django'`

**Solution:** Virtual environment not activated or dependencies not installed:
```bash
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### Black/Flake8 Not Found

**Problem:** `command not found: black`

**Solution:** Install dev dependencies:
```bash
uv pip install -e ".[dev]"
```

## Advanced Setup

### Using PostgreSQL Locally

To use PostgreSQL instead of SQLite:

1. Install PostgreSQL: [Download](https://www.postgresql.org/download/)

2. Create database:
```bash
createdb cbb_analytics
```

3. Update `.env`:
```bash
DATABASE_URL=postgres://postgres:password@localhost:5432/cbb_analytics
```

4. Run migrations:
```bash
python manage.py migrate
```

### Using VS Code

**Recommended Extensions:**
- Python
- Django
- REST Client
- SQLite Viewer

**Launch Debug Configuration** (`.vscode/launch.json`):
```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Django Runserver",
            "type": "python",
            "request": "launch",
            "program": "${workspaceFolder}/backend/manage.py",
            "args": ["runserver"],
            "django": true
        }
    ]
}
```

### Updating Dependencies

Update `pyproject.toml`, then:

```bash
# Refresh requirements
uv pip compile pyproject.toml -o requirements.txt

# Reinstall
uv pip install -e ".[dev]"
```

## Next Steps

1. ✅ Complete setup above
2. 📖 Read [Django Docs](https://docs.djangoproject.com/)
3. 📚 Read [DRF Docs](https://www.django-rest-framework.org/)
4. 🔨 Start building features
5. 🧪 Write tests as you go
6. 📤 Commit and push to GitHub

## Getting Help

- Check [Django Documentation](https://docs.djangoproject.com/)
- Check project README.md
- Open an issue on GitHub
- Ask in project discussions

Happy coding! 🚀
