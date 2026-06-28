# FastAPI backend image. PostgreSQL is external (set DATABASE_URL); this image
# runs only the API. SearXNG runs as a sibling docker-compose service.
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies from project metadata. `app` is copied first because the
# setuptools build needs the package present to install it.
COPY pyproject.toml ./
COPY app ./app
RUN pip install .

EXPOSE 8000

# Apply migrations (idempotent, tracked in schema_migrations) then serve.
# Override `command` in compose to skip the migration step if you prefer.
CMD ["sh", "-c", "python -m app.db.migrate && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
