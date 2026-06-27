# Student Journey — EdTech Platform

Personalized learning platform: onboarding journey → AI-curated study material →
AI quizzes/tests → courses & certifications → emails → mock tests & (separately)
mock interviews. See [`docs/`](docs/) for the full plan.

- [docs/PRODUCT.md](docs/PRODUCT.md) — the complete user journey & feature spec
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system design
- [docs/ROADMAP.md](docs/ROADMAP.md) — phased plan (we're past Phase 0)
- [docs/PROGRESS_LOG.md](docs/PROGRESS_LOG.md) — dated build log

## Stack
FastAPI (Python) · PostgreSQL (raw SQL via psycopg3, no ORM) · Ollama Cloud (multi-model) ·
Tavily/DuckDuckGo search. No Redis/queue yet — added when we actually need one.
Frontend is intentionally minimal for now (API-first; may be re-developed against
the company website later).

## Quick start (local)

### Prerequisites
- **Python 3.10+** (`python3 --version`)
- **Docker** + Docker Compose (for PostgreSQL) — or your own Postgres 16
- An **Ollama Cloud API key** (for AI features). The app boots without it, but
  any LLM call will fail until it's set.

### Run it (copy-paste)

```bash
# from the repository root
cd /home/tarun/Desktop/student-journey

# 1. Start infrastructure (PostgreSQL only — no Redis)
docker compose up -d

# 2. Set up the backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 3. Configure environment (then open ../.env and fill in your keys)
cp ../.env.example ../.env

# 4. Apply database migrations (creates uuidv7() + schema_migrations)
python -m app.db.migrate

# 5. Run the API (auto-reloads on code changes)
uvicorn app.main:app --reload
```

### What each step does
| Step | Command | Purpose |
|---|---|---|
| 1 | `docker compose up -d` | Starts Postgres on `localhost:5432` (user/pass/db = `student`) |
| 2 | `venv` + `pip install -e ".[dev]"` | Isolated env + installs the backend and dev tools |
| 3 | `cp ../.env.example ../.env` | Creates your local config — **edit it** (see below) |
| 4 | `python -m app.db.migrate` | Runs the `.sql` files in `app/db/migrations/` once each |
| 5 | `uvicorn app.main:app --reload` | Serves the API at `http://localhost:8000` |

### Required config (`.env`)
Edit `.env` (created in step 3) and set at least:
```ini
OLLAMA_API_KEY=your-ollama-cloud-key   # required for any AI feature
TAVILY_API_KEY=your-tavily-key         # optional; web search falls back to DuckDuckGo if empty
```
Model tiers (`LLM_MODEL_CHEAP/DEFAULT/SMART`) and `DATABASE_URL` already have
sensible defaults in `.env.example` — override only if needed.

### Verify it's working
- http://localhost:8000/health      — liveness (process is up)
- http://localhost:8000/health/db   — readiness (database reachable)
- http://localhost:8000/docs        — interactive API docs (Swagger UI)

### Stopping
```bash
# stop the API: Ctrl+C
docker compose down            # stop Postgres (keeps data)
docker compose down -v         # stop Postgres AND delete its data
```

## Tests & lint
```bash
cd backend
pytest
ruff check . && black --check .
```

## Project layout
```
backend/app/
  core/        config, logging
  db/          psycopg pool + raw-SQL migration runner + migrations/*.sql
  ai_core/     Ollama client (tiered), structured output, search providers (Tavily/DDG)
  api/         cross-cutting routes (health)
  modules/     auth · users · preferences · courses · study_material ·
               assessments · interviews · notifications · analytics
```

## Conventions
- **No ORM** — write raw SQL with psycopg3; rows come back as dicts.
- **IDs**: every table has an internal `id bigint` PK and an external
  `public_id uuid` (UUIDv7, time-ordered) — `public_id` is what APIs/URLs use.
  See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and `app/db/migrations/0001_baseline.sql`.
