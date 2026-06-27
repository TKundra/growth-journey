# Progress Log — Student Journey

Newest entries on top. One entry per working session: what was decided/built,
and what's next.

---

## 2026-06-27 — Phase 1: Onboarding & profiling journey ✅ (v1)
Built the identity + profiling layer (auth, user-type branch, profiles, preferences).
- **Migration `0002_phase1_identity.sql`:** `users`, `profiles_professional`, `profiles_student`,
  `preferences` — all on the `id`/`public_id` convention. Added a reusable `set_updated_at()`
  trigger (attached to every table). Note: column is `job_role` (`role` is reserved SQL),
  aliased back to `role` in the API. Profiles split by type so the two branches never coexist.
- **Auth (`app/modules/auth/`):** `POST /auth/signup`, `/auth/login` (HS256 JWT, subject = `public_id`),
  `/auth/verify-email` (token-based; the actual *email send* lands in Phase 5 — for now the
  verification token is returned by signup), `GET /auth/me`. Bearer-token dependency in `deps.py`.
- **Security (`app/core/security.py`):** bcrypt hashing + JWT helpers. **Dropped `passlib`** — it's
  unmaintained and crashes against `bcrypt` 4.x; now using the `bcrypt` lib directly (72-byte cap
  handled explicitly). Added JWT settings to `core/config.py`.
- **Profiles (`app/modules/users/`):** `PUT /users/me/profile` takes a discriminated union on
  `user_type`; switching type deletes the other branch's row (upsert). `GET /users/me/profile`
  returns the dashboard aggregate (user + profile + preferences).
- **Preferences (`app/modules/preferences/`):** `PUT`/`GET /preferences/me` (topics, goal, cadence,
  difficulty, notifications), one row per user, upserted.
- **Onboarding wizard UI:** deferred (frontend intentionally minimal); the endpoints above are the
  API a wizard/dashboard would drive.
- Added `email-validator` (for `EmailStr`); swapped `passlib[bcrypt]` → `bcrypt` in `pyproject.toml`.
- **Verified against real Postgres:** ran `python -m app.db.migrate` (0002 applied), exercised the
  full flow end-to-end (signup → duplicate-reject → login → bad-login → verify → student profile →
  switch to professional with branch cleanup → preferences → dashboard). `pytest` 12 passed
  (5 DB-guarded integration + 5 security unit + 2 Phase-0 health), `black` clean.
- **Next:** Phase 2 — AI study material engine (query builder from profile+preferences → search →
  LLM curation → `study_resources`).

## 2026-06-27 — Phase 0 stack revision (per request)
Reworked the Phase 0 scaffold to match the desired stack:
- **Removed Redis & Celery entirely** (deferred until a real queue/scheduler need appears). Deleted `worker.py`; dropped redis/celery deps and the redis service from docker-compose.
- **Swapped Claude → Ollama Cloud.** `ai_core/llm.py` now builds an `ollama.Client` from `OLLAMA_HOST` + `OLLAMA_API_KEY`, with multi-model tiers (`cheap`/`default`/`smart`). Structured output via Ollama's `format` + Pydantic validation. `_build_client()` is the documented swap point for the key-rotation service.
- **Dropped SQLAlchemy/Alembic → raw SQL (psycopg3).** New `app/db/`: `pool.py` (pooled `dict_row` connections), `migrate.py` (forward-only `.sql` runner, `python -m app.db.migrate`), `migrations/0001_baseline.sql`. `/health/db` now runs a raw `select 1`.
- **Schema convention:** integer `id` PK + UUIDv7 `public_id` on every table; `uuidv7()` SQL function added in the baseline migration; table template documented in ARCHITECTURE.md and the migration file.
- Updated README, CLAUDE.md, ARCHITECTURE.md, ROADMAP.md to match.
- **Verified:** reinstalled deps, `pytest` green, `ruff`/`black` clean, app imports boot.

## 2026-06-27 — Phase 0: Foundations & scaffolding ✅
- **Built the runnable backend skeleton** under `backend/`:
  - FastAPI app (`app/main.py`) with `/`, `/health`, `/health/db` and Swagger at `/docs`.
  - `core/`: `config.py` (pydantic-settings), `database.py` (SQLAlchemy engine + `get_db`), `logging.py`.
  - `models/base.py`: `Base` with UUID PK + created/updated timestamps.
  - `ai_core/`: `LLMClient` (Claude, cost-tiered Haiku/Sonnet/Opus, `complete()` + `parse()` + token logging);
    `search/` provider abstraction with Tavily (primary) + DuckDuckGo (fallback) and a config-driven factory.
  - `modules/`: nine placeholder packages (auth, users, preferences, courses, study_material,
    assessments, interviews, notifications, analytics) so the layout exists for Phase 1+.
  - `worker.py`: Celery app wired to Redis with a `ping` task.
  - Alembic wired (`alembic.ini`, `env.py` pulling URL + `Base.metadata` from app); baseline migration lands with Phase 1 models.
- **Infra & tooling:** `docker-compose.yml` (pgvector/pg16 + redis:7), `.env.example`, `.gitignore`,
  root `README.md`, `pyproject.toml` (deps + ruff/black/pytest config), `.pre-commit-config.yaml`.
- **Frontend:** intentionally minimal — `frontend/README.md` placeholder only (API-first; may be re-developed for the company site).
- **Verified:** created `.venv`, installed deps, `pytest` (2 passed), `ruff` clean, `black` clean, all imports boot.
- **Git:** repo initialized (`git init`); left uncommitted for you to commit + branch + validate yourself.
- **Next:** Phase 1 — auth (signup/login/JWT), user-type branch, profile + preferences models, onboarding wizard.

## 2026-06-27 — Planning & docs
- Read the product brief; defined the complete user journey.
- Confirmed key insight: **mock interview is a separate subsystem** from mock tests
  (stateful multi-turn + rubric evaluation vs. objective MCQ scoring).
- **Decisions locked:**
  - Stack: Python-heavy — FastAPI, PostgreSQL + pgvector, Celery + Redis, Claude (Anthropic), Tavily+DuckDuckGo search.
  - v1 scope: Onboarding journey + AI study material + Quiz/MCQ engine (Phases 1–3).
  - Working style: living roadmap + this daily log + `CLAUDE.md` for session pickup.
- **Created:** `CLAUDE.md`, `docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, this log.
- **Next:** Phase 0 scaffolding when you give the word — and pick frontend (Next.js vs Vite).
