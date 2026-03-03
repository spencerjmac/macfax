# CBB Analytics Backend - Documentation Index

Welcome to the CBB Analytics Backend! Use this index to navigate the documentation.

## 🚀 Getting Started (Pick One)

### I have 5 minutes
👉 Read **[QUICK_START.md](QUICK_START.md)** - Quick overview and setup steps

### I have 15 minutes  
👉 Read **[DEVELOPMENT.md](DEVELOPMENT.md)** - Detailed guide with troubleshooting

### I have 30 minutes
👉 Read **[README.md](README.md)** - Complete documentation with API endpoints

---

## 📚 Documentation Files

### Setup & Configuration
| Document | Purpose | Read Time |
|----------|---------|-----------|
| **[QUICK_START.md](QUICK_START.md)** | 5-step quick start | 5 min |
| **[DEVELOPMENT.md](DEVELOPMENT.md)** | Detailed local setup guide | 15 min |
| **[SETUP_SUMMARY.md](SETUP_SUMMARY.md)** | Technical reference | 10 min |
| **[SETUP_COMPLETE.txt](SETUP_COMPLETE.txt)** | What was completed | 5 min |

### Project Documentation
| Document | Purpose | Read Time |
|----------|---------|-----------|
| **[README.md](README.md)** | Main project documentation | 20 min |
| **[pyproject.toml](pyproject.toml)** | Python project config | 5 min |
| **[.env.example](.env.example)** | Environment template | 2 min |

---

## 🎯 Use Cases

### "I'm new to this project"
1. Start with **QUICK_START.md** - 5 minutes
2. Set up local environment - 10 minutes
3. Read **README.md** - 20 minutes
4. Try first task

### "I need to set up locally"
1. Follow **QUICK_START.md** steps 1-5
2. Refer to **DEVELOPMENT.md** if issues arise
3. Bookmark **DEVELOPMENT.md** for reference

### "I want to understand the tech stack"
1. Read **SETUP_SUMMARY.md** - Architecture section
2. Skim **pyproject.toml** - Dependencies
3. Check **README.md** - API endpoints
4. Review **config/settings.py** - Django config

### "I'm deploying to Docker"
1. Check **README.md** - Docker section
2. Review **docker-compose.yml** in root
3. Set up **REDIS_URL** and **DATABASE_URL**
4. Run `docker compose up --build`

### "I hit an error"
1. Check **DEVELOPMENT.md** - Troubleshooting section
2. Search for your error message
3. Follow suggested solution
4. Check Django docs if needed

---

## 📋 Quick Commands

```bash
# Setup (first time)
cd backend
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
cp .env.local .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver

# Daily development
source .venv/bin/activate
python manage.py runserver

# Before committing
black . && isort . && pytest

# Deploy with Docker
docker compose up --build
```

---

## 🔍 Quick Reference

### Project Structure
```
backend/
├── config/           # Django settings and URLs
├── core/            # Main app with models
├── api/             # REST API views and serializers
├── scripts/         # Data pipeline scripts
├── templates/       # Django templates
├── pyproject.toml   # Python project config
├── requirements.txt # Docker dependencies
├── .env.local       # Local dev settings
└── manage.py        # Django management
```

### Technology Stack
- **Framework:** Django 5.0.1
- **API:** Django REST Framework 3.14
- **Database:** SQLite (dev) / PostgreSQL (prod)
- **Job Queue:** Redis 7 + django-rq 2.8.1
- **Server:** Gunicorn 21.2
- **Package Manager:** uv (Python)

### Key Features
- Real-time job monitoring dashboard
- Background job queue for long operations
- Parallel task execution
- Game log ingestion pipeline
- Team metrics computation
- Admin interface for data management

---

## 📞 Getting Help

### Common Questions

**Q: How do I set up locally?**  
A: Follow the 5 steps in **QUICK_START.md**

**Q: Where are the API endpoints documented?**  
A: See **README.md** section "API Endpoints"

**Q: How do I add a new dependency?**  
A: Edit **pyproject.toml**, then run `uv pip install -e ".[dev]"`

**Q: How do I deploy to production?**  
A: See **README.md** section "Docker Deployment"

**Q: My command is not found**  
A: See **DEVELOPMENT.md** troubleshooting section

### Documentation Resources

- **Django Docs:** https://docs.djangoproject.com/
- **DRF Docs:** https://www.django-rest-framework.org/
- **uv Docs:** https://docs.astral.sh/uv/
- **redis-py Docs:** https://github.com/redis/redis-py

---

## 📊 What You Have

✅ Local development environment ready (SQLite, uv, pyproject.toml)  
✅ Docker deployment configured (PostgreSQL, Redis, Gunicorn)  
✅ Background job queue system (django-rq)  
✅ Real-time admin dashboard for job monitoring  
✅ Complete API with 10+ endpoints  
✅ Comprehensive documentation  
✅ Code quality tools (black, flake8, pytest)  
✅ Database migrations system  

---

## 🚀 Next Steps

1. **Right now:** Read [QUICK_START.md](QUICK_START.md)
2. **In 5 minutes:** Start the 5-step setup
3. **In 30 minutes:** Have a local server running
4. **Today:** Make your first code change
5. **This week:** Deploy to Docker

---

## 📝 Notes

- All `.env` files are **git-ignored** for security
- Use `.env.local` for local development
- Use `.env.docker` for Docker variables
- Migrations are auto-applied in Docker
- Tests run with `pytest`
- Code formatted with `black`

---

**Last updated:** 2025-03-02  
**Backend version:** 0.1.0  
**Python version:** 3.11+  
**Django version:** 5.0.1

---

**Ready to get started?** → Open [QUICK_START.md](QUICK_START.md) now! 🎉
