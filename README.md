# Student Journey — EdTech Platform

Personalized learning platform: onboarding journey → AI-curated study material →
AI quizzes/tests → courses & certifications → emails → mock tests & (separately)
mock interviews. See [`docs/`](docs/) for the full plan.

- [docs/PRODUCT.md](docs/PRODUCT.md) — the complete user journey & feature spec
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system design
- [docs/ROADMAP.md](docs/ROADMAP.md) — phased plan (Phases 1–3 done; courses/email next)
- [docs/PROGRESS_LOG.md](docs/PROGRESS_LOG.md) — dated build log

## Stack
FastAPI (Python) · PostgreSQL + pgvector (raw SQL via psycopg3, no ORM) · Ollama Cloud (multi-model) ·
SearXNG search (DuckDuckGo fallback). No Redis/queue yet — added when we actually need one.
Frontend is intentionally minimal for now (API-first; may be re-developed against
the company website later).

## Quick start (local)

### Prerequisites
- **Python 3.10+** (`python3 --version`)
- **Docker** + Docker Compose (runs the API + SearXNG)
- **PostgreSQL 16** reachable via `DATABASE_URL` (hosted externally — not in compose)
- An **Ollama Cloud API key** (for AI features). The app boots without it, but
  any LLM call will fail until it's set.

### Run it (copy-paste)

```bash
# from the repository root
cd /home/tarun/Desktop/student-journey

# 1. Configure environment (then open ../.env and set DATABASE_URL + keys)
cp .env.example .env

# 2. Start the stack — API + SearXNG (PostgreSQL is external; set DATABASE_URL)
docker compose up -d --build
```
That's the whole runtime: the `api` container applies migrations on start and serves
at `http://localhost:8000`; `searxng` runs at `:8080`. **PostgreSQL is not in compose** —
point `DATABASE_URL` at your hosted instance. If the DB runs on the *same host* as Docker,
use `host.docker.internal` (containers can't reach it via `localhost`):
```bash
DATABASE_URL=postgresql://USER:PASS@host.docker.internal:5432/DB docker compose up -d --build
# API_PORT=8010 docker compose up -d   # if host port 8000 is taken
```

#### Or run the API on the host (without Docker)
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m app.db.migrate            # apply migrations
uvicorn app.main:app --reload       # serves http://localhost:8000
```
(`docker compose up -d searxng` still gives you search at `:8080`.)

### Required config (`.env`)
Edit `.env` (created in step 1) and set at least:
```ini
OLLAMA_API_KEY=your-ollama-cloud-key   # required for any cloud AI feature (curation, MCQ, …)
```
Model tiers (`LLM_MODEL_CHEAP/DEFAULT/SMART`) and `DATABASE_URL` already have
sensible defaults in `.env.example` — override only if needed.

**Web search** defaults to **SearXNG** (`SEARCH_PROVIDER=searxng`, `SEARXNG_URL=http://localhost:8080`),
the self-hosted metasearch started by `docker compose up -d` — free, no API key, and it supplies
**YouTube videos/playlists** alongside articles. Falls back to DuckDuckGo (keyless) on error; set
`TAVILY_API_KEY` + `SEARCH_PROVIDER=tavily` for paid LLM-grade extraction instead.

**Embeddings (RAG) run on a separate host.** Ollama Cloud does not serve embedding
models, so embeddings target a local/self-hosted Ollama via `OLLAMA_EMBED_HOST`
(default `http://localhost:11434`). Pull the model once: `ollama pull nomic-embed-text`.
Without a reachable embed host, saving still works — RAG indexing is just skipped.

### Verify it's working
- http://localhost:8000/health      — liveness (process is up)
- http://localhost:8000/health/db   — readiness (database reachable)
- http://localhost:8000/docs        — interactive API docs (Swagger UI)

### Frontend (optional UI)
A minimal, zero-build SPA lives in [`frontend/`](frontend/) — signup, signin, the
student/professional profile branch, preferences, a dashboard, the AI study-material
feed/library, and the **quizzes** flow (generate → take a timed quiz → scored results
with explanations → per-topic progress). With the API running, serve it:
```bash
cd frontend
python3 -m http.server 3000   # then open http://localhost:3000
```
See [frontend/README.md](frontend/README.md) for details.

### Stopping
```bash
docker compose down            # stop & remove the api + searxng containers
```
(PostgreSQL is external, so there's no DB volume to wipe — your data lives in your
hosted Postgres regardless.)

## Docker commands (this project)

The compose stack is just two services: **`api`** (FastAPI, built from `./backend`)
and **`searxng`** (search). Postgres is external. Run all of these from the repo root.

```bash
# ── start / stop ───────────────────────────────────────────────────────────
docker compose up -d --build        # build + start everything (first run / after deps change)
docker compose up -d                # start without rebuilding
docker compose down                 # stop & remove both containers
docker compose restart api          # restart just the API
docker compose ps                   # what's running + which ports

# ── ⚠ after changing backend code or adding a migration ─────────────────────
# The api image BAKES the source (no bind-mount), so edits aren't live. Rebuild:
docker compose up -d --build api    # rebuild + restart only the api container
docker compose build --no-cache api # full clean rebuild if a build seems stale

# ── logs ─────────────────────────────────────────────────────────────────────
docker compose logs -f api          # follow API logs (Ctrl+C to stop following)
docker compose logs --tail 50 api   # last 50 lines
docker compose logs -f searxng      # search engine logs

# ── database migrations ────────────────────────────────────────────────────
# The api container runs migrations on start; to apply new ones without a restart:
docker compose exec api python -m app.db.migrate

# ── run tests / a shell inside the container ─────────────────────────────────
docker compose exec api pytest      # run the test suite in-container (needs DB reachable)
docker compose exec api sh          # poke around the container filesystem

# ── ports / external DB overrides (env vars compose reads) ───────────────────
API_PORT=8010 docker compose up -d                                   # if host :8000 is taken
DATABASE_URL=postgresql://USER:PASS@host.docker.internal:5432/DB \
  docker compose up -d --build                                       # Postgres on the same host

# ── quick health / search checks ─────────────────────────────────────────────
curl -s http://localhost:8000/health/db                              # DB readiness
curl -s 'http://localhost:8080/search?q=test&format=json' | head -c 200   # SearXNG JSON API
```

## API overview (Phase 1)
Full interactive docs at `/docs`. The onboarding journey in order:

| Step | Method & path | Auth | Purpose |
|---|---|---|---|
| Sign up | `POST /auth/signup` | — | Create account (returns a `email_verification_token` until the email engine lands in Phase 5) |
| Verify email | `POST /auth/verify-email` | — | Confirm with the token from signup |
| Log in | `POST /auth/login` | — | Returns a Bearer JWT — send it as `Authorization: Bearer <token>` on the calls below |
| Who am I | `GET /auth/me` | Bearer | Current user |
| Set profile | `PUT /users/me/profile` | Bearer | Pick type & fill it in: `{"user_type":"student", ...}` or `{"user_type":"professional", ...}` |
| Set preferences | `PUT /preferences/me` | Bearer | Topics, goal, cadence (`none`/`daily`/`weekly`), difficulty, notifications |
| Dashboard | `GET /users/me/profile` | Bearer | Aggregate: user + profile + preferences in one call |

### API overview (Phase 2 — AI study material)
Curation needs `OLLAMA_API_KEY` (cloud); embeddings need a reachable `OLLAMA_EMBED_HOST`
(local Ollama). Search falls back to DuckDuckGo without a Tavily key.

| Step | Method & path | Auth | Purpose |
|---|---|---|---|
| Generate feed | `POST /study-material/generate` | Bearer | Profile+prefs → search → LLM-curated resources (dedup, ranked, tagged) |
| Browse feed | `GET /study-material` | Bearer | The curated feed, each item flagged `is_saved` |
| One resource | `GET /study-material/{id}` | Bearer | A single resource |
| Save / unsave | `POST` / `DELETE /study-material/{id}/save` | Bearer | Promote to (or remove from) your library; saving indexes it for RAG |
| Library | `GET /study-material/library` | Bearer | Your saved reading list |
| Semantic search | `GET /study-material/library/search?q=` | Bearer | Cosine search over your saved material (pgvector) |

### API overview (Phase 3 — quizzes / MCQ engine)
MCQ generation needs `OLLAMA_API_KEY` (cloud); scoring is deterministic and server-side.

| Step | Method & path | Auth | Purpose |
|---|---|---|---|
| Generate quiz | `POST /assessments/quizzes/generate` | Bearer | Topics (override/prefs/profile) → LLM MCQs, grounded in your studied material |
| List quizzes | `GET /assessments/quizzes` | Bearer | Your quiz history with attempt count + best score |
| Get quiz | `GET /assessments/quizzes/{id}` | Bearer | Questions + options for taking — **answer key hidden** |
| Submit | `POST /assessments/quizzes/{id}/submit` | Bearer | Score + reveal correct answers and explanations |
| Result | `GET /assessments/quizzes/{id}/result` | Bearer | Your latest graded attempt |
| Progress | `GET /assessments/stats` | Bearer | Per-topic + overall accuracy |

## Tests & formatting
```bash
cd backend
pytest
black .            # format code (use `black --check .` to only verify)
```

## Project layout
```
backend/app/
  core/        config, logging
  db/          psycopg pool + raw-SQL migration runner + migrations/*.sql
  ai_core/     Ollama client (tiered), structured output, search providers (SearXNG/Tavily/DDG)
  api/         cross-cutting routes (health)
  modules/     auth · users · preferences · courses · study_material ·
               assessments · interviews · notifications · analytics
```

## Conventions
- **No ORM** — write raw SQL with psycopg3; rows come back as dicts.
- **IDs**: every table has an internal `id bigint` PK and an external
  `public_id uuid` (UUIDv7, time-ordered) — `public_id` is what APIs/URLs use.
  See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and `app/db/migrations/0001_baseline.sql`.
