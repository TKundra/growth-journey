# Student Journey — EdTech Platform

> Context file for AI assistants. Read this first every session, then `docs/ROADMAP.md`
> for current state and `docs/PROGRESS_LOG.md` for what changed recently.

## What this is
An EdTech platform that takes a learner through a personalized journey:
sign up → tell us about yourself (working professional OR student) → state
preferences → get AI-curated study material → take AI-generated quizzes /
daily-weekly tests → (optionally) enroll in our courses & certifications →
receive emails (reminders, results, digests) → practice with **mock tests**
and, as a **separate flow**, **mock interviews**.

## Key product decisions
- **Two user types**, profiling branches by type:
  - Working professional → experience, role, industry, skills, goal.
  - Student → schooling level, stream, subjects, target exams, preferred colleges.
- **Mock test ≠ Mock interview.** They are two different subsystems:
  - Mock test = objective MCQ, deterministic scoring, single submission.
  - Mock interview = stateful multi-turn conversational agent + rubric-based
    qualitative evaluation (separate data model, separate agents, latency-sensitive).
- **v1 scope** = Onboarding journey + AI study material + Quiz/MCQ engine.
  Courses, email, mock test, mock interview come in later phases.

## Tech stack (locked)
- Backend: **FastAPI (Python)**, modular monolith with clear module boundaries.
- Frontend: minimal/deferred for now (API-first; may be re-developed for the company website). Next.js recommended when needed.
- DB: **PostgreSQL** accessed with **raw SQL via psycopg3 — NO ORM** (no SQLAlchemy/Alembic). pgvector image is used so RAG can be added in Phase 2.
  - **ID convention**: every table has internal `id bigint generated always as identity` PK + external `public_id uuid not null default uuidv7() unique`. `public_id` is what APIs/URLs expose. `uuidv7()` is defined in `app/db/migrations/0001_baseline.sql`.
  - Migrations are plain `.sql` files in `app/db/migrations/`, applied by `python -m app.db.migrate`.
- Async/queue/scheduler: **none yet** — deliberately deferred. Add Redis + a queue/scheduler only when daily/weekly tests & email digests actually need it.
- LLM: **Ollama Cloud**, multi-model, size/cost-tiered (cheap/default/smart in settings). One `OLLAMA_API_KEY` for now; user's **key-rotation service** is merged in later by swapping `LLMClient._build_client()`.
- Web search: provider abstraction — **Tavily** primary, **DuckDuckGo** fallback, SerpAPI optional.

## Working agreement
- This is the source of truth for *intent*. The code is the source of truth for *state*.
- After any meaningful change, append to `docs/PROGRESS_LOG.md` and tick boxes in `docs/ROADMAP.md`.
- Keep modules decoupled so `interviews` and `study_material` can later be extracted to services.

## Docs map
- `docs/PRODUCT.md` — full user journey & feature spec.
- `docs/ARCHITECTURE.md` — system design, modules, data model, AI design.
- `docs/PHASE4_COURSES.md` — text diagrams of the courses & certifications subsystem.
- `docs/ROADMAP.md` — phased execution plan with task checkboxes.
- `docs/PROGRESS_LOG.md` — dated log of what was built/decided each session.
