# Roadmap — Student Journey

Status legend: `[ ]` todo · `[~]` in progress · `[x]` done.
**v1 = Phases 1–3.** Tick boxes and log changes in `PROGRESS_LOG.md` as we go.

---

## Phase 0 — Foundations & scaffolding ✅
- [x] Frontend: deferred/minimal (API-first; Next.js recommended later) — repo structure initialized
- [x] FastAPI project skeleton with module layout (`auth`, `users`, ... , `ai_core`)
- [x] PostgreSQL via docker-compose (pgvector image, ready for Phase 2 RAG) — **no Redis yet** (deferred)
- [x] Raw SQL via psycopg3 (no ORM): connection pool + plain-`.sql` migration runner (`python -m app.db.migrate`)
- [x] ID convention established: integer `id` PK + UUIDv7 `public_id` (`uuidv7()` in baseline migration)
- [x] Config (pydantic-settings), `.env.example`, secrets handling (.env gitignored)
- [x] Tooling: pytest, black, pre-commit
- [x] `ai_core` Ollama Cloud client (multi-model, tiered) + structured-output helper + token logging; rotation-service swap point
- [x] `SearchProvider` abstraction with Tavily + DuckDuckGo implementations
- [ ] CI pipeline (GitHub Actions) — deferred until first push
- _Verified: `pytest` and `black` green; app imports and health routes boot._

## Phase 1 — Onboarding & profiling journey  ⭐ v1
- [x] `auth`: signup, login, JWT, email verification (token-based; email *send* deferred to Phase 5)
- [x] User-type branch (professional vs student) — discriminated `PUT /users/me/profile`, switching replaces the branch
- [x] Profile data models + endpoints (professional & student variants) — `0002_phase1_identity.sql`
- [x] `preferences` model + endpoints (topics, goal, cadence, difficulty, notifications)
- [x] Multi-step onboarding wizard UI (branching) — minimal zero-build SPA in `frontend/` (signup, signin, profile branch, preferences, dashboard)
- [x] Persist & fetch full profile; basic dashboard shell (`GET /users/me/profile` aggregate + frontend dashboard)
- _Verified: full flow (signup→login→verify→profile→prefs) tested against Postgres; frontend journey verified incl. CORS; `pytest` (12) + `black` green._

## Phase 2 — AI study material engine  ⭐ v1
- [x] Query builder: profile + preferences → search queries (`study_material/query_builder.py`)
- [x] Search integration (Tavily primary, DuckDuckGo fallback) — resilient per-query fallback in `curator.py`
- [x] LLM curation: dedupe, rank, summarize, tag, cite sources (+ anti-hallucination URL guardrail)
- [x] Resource models + endpoints (`0003_…`, `study_material/router.py`); **normalized in `0004_…`** to
      canonical `resources` (URL-unique, shared) + per-user `feed_items` + `saved_resources` — kills
      cross-user row/embedding duplication, URLs embedded once & reused
- [x] Reading-list UI with save-to-library (Discover / My-library + semantic search in `frontend/`)
- [x] RAG: chunk + embed saved material into pgvector (`rag.py`, best-effort on save; reuses existing
      vectors for a shared URL; retrieval consumed in Phase 3)
- [x] Embeddings run on a **separate local Ollama host** (`OLLAMA_EMBED_HOST`) — Ollama Cloud serves
      no embedding model (`/api/embed` 401s); chat/curation stay on the cloud
- _Verified: 28 pytest green (unit + monkeypatched integration flow, incl. cross-user resource sharing);
  black clean; migrations applied; routes via OpenAPI._

## Phase 3 — Quiz / MCQ engine + daily/weekly tests  ⭐ v1
- [ ] MCQ generation (structured output, validated) from topics / saved material
- [ ] Difficulty levels + per-topic targeting
- [ ] `questions`, `quizzes`, `attempts`, `attempt_answers` models
- [ ] Test-taking UI (timed) + auto-scoring + explanations
- [ ] `test_schedules`: daily/weekly opt-in (introduce a scheduler/queue here if needed — first real use case)
- [ ] Per-topic progress analytics (accuracy, trend)
- [ ] **v1 release checkpoint**

## Phase 4 — Courses & certifications
- [ ] `courses` catalog + `enrollments` + `certificates` models
- [ ] Catalog & enrollment UI
- [ ] Link enrolled course syllabus into study material + quizzes
- [ ] Certificate generation on completion

## Phase 5 — Email / notification engine
- [ ] Email provider integration (SES/Resend) + `email_templates`
- [ ] Transactional triggers (welcome, results)
- [ ] Scheduled digests + test reminders (via the scheduler introduced in Phase 3)
- [ ] `email_events` log + unsubscribe / preferences

## Phase 6 — Mock test (formal) flow
- [ ] Full-length mock model (sectional, timed, larger sets)
- [ ] Scheduled + on-demand mock generation
- [ ] Detailed report: section scores, percentile, time analysis, weak areas

## Phase 7 — Mock interview flow  (SEPARATE subsystem)
- [ ] `interview_sessions`, `interview_turns`, `interview_evaluations` models
- [ ] Interviewer agent: role/JD-driven, adaptive multi-turn (text)
- [ ] Evaluator agent: rubric scoring + written feedback + improvement plan
- [ ] Interview UI (chat) + report view
- [ ] (Later) Voice: STT in + TTS out

## Phase 8 — Analytics, dashboards & gamification
- [ ] Mastery/skill graph per topic
- [ ] Strengths/weaknesses → recommended next material
- [ ] Streaks, badges, leaderboard

## Phase 9 — Hardening, observability, deployment & scale
- [ ] Structured logging, tracing, LLM cost dashboards
- [ ] Rate limiting, security review, load testing
- [ ] Containerized deploy + CI/CD
- [ ] Evaluate extracting `interviews` / `study_material` into services

---

## How to command this build
Point me at a phase or a specific checkbox, e.g.:
- "Start Phase 0" / "Scaffold the FastAPI project"
- "Do the auth signup+login in Phase 1"
- "Build the MCQ generator in Phase 3"
I'll implement, then update `ROADMAP.md` + `PROGRESS_LOG.md`.
