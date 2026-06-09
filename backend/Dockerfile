FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy full backend first so "pip install -e ." in requirements.txt finds pyproject.toml
COPY backend /app
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy data files that management commands expect relative to project root
# (SCRIPT_DIR in commands resolves 5 levels above /app/nba/management/commands/ = /)
COPY data/nba/ /data/nba/
COPY metrics_output/ /metrics_output/

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
