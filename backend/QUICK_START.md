# 🚀 CBB Analytics Backend - Local Development Checklist

## ✅ Setup Complete!

Your Django backend is now fully configured for local development and Docker deployment.

---

## 📋 What You Have Now

### Configuration Files
- ✅ **pyproject.toml** - Project metadata with uv support
- ✅ **requirements.txt** - Pinned dependencies for Docker
- ✅ **.env.local** - Local development settings (SQLite)
- ✅ **.env.example** - Template for environment variables

### Documentation
- ✅ **README.md** - Main project documentation (updated)
- ✅ **DEVELOPMENT.md** - Complete local setup guide (7 sections)
- ✅ **SETUP_SUMMARY.md** - Overview and next steps

### Database
- ✅ **0019_dataprocessingjob.py** - Migration for job tracking model

---

## 🏃 Get Started in 5 Steps

### Step 1: Install uv (if not already installed)

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# macOS with Homebrew
brew install uv

# Verify
uv --version
```

### Step 2: Set Up Virtual Environment

```bash
cd backend
uv venv
source .venv/bin/activate  # macOS/Linux
# or
.venv\Scripts\activate  # Windows
```

### Step 3: Install Dependencies

```bash
# Development setup (with testing tools)
uv pip install -e ".[dev]"

# Or production-like setup
uv pip install -e .
```

### Step 4: Initialize Database

```bash
# Apply migrations
python manage.py migrate

# Create admin account
python manage.py createsuperuser
```

### Step 5: Start Server

```bash
python manage.py runserver
```

Access at http://localhost:8000/admin/

---

## 📚 Documentation Guide

Read these in order:

1. **This file (QUICK_START.md)** - You are here - 5 min overview
2. **DEVELOPMENT.md** - Detailed setup with troubleshooting - 15 min
3. **SETUP_SUMMARY.md** - Technical details and reference - as needed
4. **README.md** - API endpoints and features - as needed

---

## 💻 Common Commands

### Development

```bash
# Activate environment (every session)
source .venv/bin/activate

# Start server
python manage.py runserver

# Make database migrations
python manage.py makemigrations
python manage.py migrate

# Run tests
pytest

# Format code
black . && isort .

# Lint code
flake8 . --max-line-length=100
```

### Django Admin

```bash
# Create superuser
python manage.py createsuperuser

# Django shell (interactive Python)
python manage.py shell

# Check for issues
python manage.py check
```

### Data Management

```bash
# Ingest game logs for a season
python manage.py ingest_gamelogs --season 2026

# Run full update pipeline (with Redis)
python manage.py update_all --season 2026

# Run without Redis (serial execution)
python manage.py update_all --season 2026 --serial
```

---

## 🔧 Key Files Overview

### pyproject.toml (Project Config)

Defines:
- Project metadata (name, version, description)
- Dependencies (Django, DRF, pandas, etc.)
- Dev dependencies (pytest, black, flake8, isort)
- Tool configurations (black, isort, pytest)

**Usage:**
```bash
uv pip install -e ".[dev]"  # Install from this file
```

### requirements.txt (Docker Dependencies)

- Pinned versions of all packages
- Auto-generated from pyproject.toml
- Used by Docker: `pip install -r requirements.txt`

**To regenerate:**
```bash
uv pip compile pyproject.toml -o requirements.txt
```

### .env.local (Local Settings)

```
DATABASE_URL=sqlite:///db.sqlite3  # No external DB needed
DEBUG=True
SECRET_KEY=dev-key
```

**Copy to .env to use:**
```bash
cp .env.local .env
```

### DEVELOPMENT.md (Setup Guide)

Complete guide including:
- uv installation (all platforms)
- Virtual environment setup
- Database configuration
- Testing and linting
- Troubleshooting
- Advanced setup (PostgreSQL, VS Code)

---

## 🐳 Docker Deployment

When you're ready to deploy with PostgreSQL:

```bash
# From root directory
docker compose up --build

# In another terminal
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser
```

Services:
- PostgreSQL 16 on port 5432
- Redis 7 on port 6379
- Django on port 8000
- Frontend on port 3000

---

## 🎯 Next Tasks

### Immediate (Now)
1. Follow Step 1-5 above to get running
2. Access Django admin at http://localhost:8000/admin/
3. Create a Season entry in admin
4. Verify the setup works

### Short Term (Today/Tomorrow)
1. Read DEVELOPMENT.md for detailed reference
2. Try creating a database migration
3. Run tests with `pytest`
4. Format code with `black` and `isort`

### Medium Term (This Week)
1. Make your first code change
2. Create migrations for new models
3. Write tests for your changes
4. Commit and push to git

### Long Term (As Needed)
1. Add new dependencies to pyproject.toml
2. Set up PostgreSQL locally if preferred
3. Configure Django admin customizations
4. Deploy with Docker Compose

---

## 🚨 Common Issues & Solutions

### Command "python" not found

**Solution:** Virtual environment not activated
```bash
source .venv/bin/activate
```

### "No module named django"

**Solution:** Dependencies not installed
```bash
uv pip install -e ".[dev]"
```

### Port 8000 already in use

**Solution:** Use a different port
```bash
python manage.py runserver 8001
```

### Database errors

**Solution:** Run migrations
```bash
python manage.py migrate
```

### Redis connection errors

**Solution:** Redis is optional. Either:
1. Install Redis locally
2. Use `--serial` flag for jobs
3. Ignore warnings if not using job queue

---

## 📖 Learn More

### Official Documentation
- [Django Docs](https://docs.djangoproject.com/)
- [Django REST Framework](https://www.django-rest-framework.org/)
- [uv Documentation](https://docs.astral.sh/uv/)

### Project Files
- **README.md** - Main documentation
- **DEVELOPMENT.md** - Detailed setup
- **SETUP_SUMMARY.md** - Technical reference
- **config/settings.py** - Django configuration
- **api/views.py** - API endpoints

---

## ✨ You're Ready!

Everything is set up for:
- ✅ Local development with SQLite
- ✅ Fast package management with uv
- ✅ Testing with pytest
- ✅ Code quality with black/flake8
- ✅ Admin-triggered data jobs (synchronous)
- ✅ Docker deployment with PostgreSQL
- ✅ Real-time admin job monitoring

**Next step:** Run the commands in "Get Started in 5 Steps" above!

Questions? Check DEVELOPMENT.md troubleshooting section.

Happy coding! 🎉
