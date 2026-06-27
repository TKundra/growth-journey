# Progress Log — Student Journey

Newest entries on top. One entry per working session: what was decided/built,
and what's next.

---

## 2026-06-27 — Frontend fixes: scrolling + sidebar nav logic
- **Fixed broken scrolling.** The split card had been trapped at `max-height: 100vh` with internal
  `overflow` and `body{height:100%}`, which prevented natural scrolling. Switched to the standard
  "center-if-short, scroll-if-tall" pattern: `.auth`/`.layout` are flex with the card at `margin:auto`,
  no height cap, no internal overflow — short pages center, tall pages scroll the page normally.
- **Fixed sidebar nav.** Profile & Preferences are onboarding/edit screens, not permanent destinations,
  so they no longer appear as nav tabs once you're in. The sidebar now shows **Dashboard** (home) plus
  a "Coming soon" group (Study material, Quizzes) so it reads intentionally. Profile/preferences are
  edited via the dashboard's Edit buttons; those edit screens get a "← Dashboard" back link.
- **Verified:** `node --check app.js` clean, CSS balanced; re-ran the full professional journey
  (signup→verify→login→profile→preferences→dashboard) end-to-end against Postgres — all 200.

## 2026-06-27 — Frontend: typography hierarchy + consistent app shell
- **Fixed the "everything is bold" look.** Introduced a restrained weight scale (`--fw-regular/medium/
  semi/bold`): body 400, headings 700 (h1 700/800 display), supporting text 400–500, labels are now a
  600 uppercase eyebrow style, pills/kv/badges dialed down to 600. Slightly smaller base (15.5px),
  looser line-height (1.6), softer body color — much calmer against the glass.
- **After-login now matches login.** Replaced the old top-bar + `.shell` with the same floating
  split card: a gradient **sidebar** (brand + nav: Dashboard/Profile/Preferences + user + logout) on
  the left, frosted **content** on the right — `appShell(active, inner)` in `app.js`. ~88% width
  (max 1140px), card capped to viewport height with the content pane scrolling.
- Dashboard's full-gradient hero became a calm glass `welcome` header (the gradient now lives in the
  sidebar) with soft `badge--ok` / `badge--warn` verification pills; dropped the redundant step dots.
- Removed obsolete `.topbar/.shell/.steps/.hero` styles.
- **Verified:** `node --check app.js` clean; no leftover topbar/shell refs; CSS braces balanced (153/153).

## 2026-06-27 — Frontend: liquid-glass theme + typography
- **New typeface:** added **Plus Jakarta Sans** (Google Fonts, weights 400–800) with a system fallback;
  tightened heading letter-spacing for a more premium, display feel.
- **Liquid-glass redesign of `styles.css`** (class names unchanged, so `app.js` untouched):
  - A living gradient backdrop — soft indigo/teal/pink blobs that slowly drift (`body::before`,
    respects `prefers-reduced-motion`).
  - Frosted translucent surfaces (`backdrop-filter` blur+saturate) on cards, panels, the topbar
    (now a floating glass bar), inputs, segmented controls and chips, each with an inset top highlight.
  - Glossy gradient primary buttons + avatar/hero with colored glow shadows.
  - **Beautiful pills:** chips & tag pills are now jewel-like gradient capsules with a glass sheen;
    the audience pill and hero badge are frosted glass.
- **Auth layout:** replaced the full-bleed 50/50 split with one **floating split card** centered on the
  backdrop — ~88% viewport width (capped at 1140px), internally split brand | form. Collapses to a
  single column (brand hidden) under 980px.
- **Verified:** static assets only; `node --check app.js` still clean; API integration unaffected.

## 2026-06-27 — Frontend polish + inclusive branding
- **Neutral user-facing brand.** "Student Journey" alienated working professionals, so the UI brand is
  now **"Journey"** (single `BRAND` constant in `app.js`; repo/codename stays "Student Journey").
  Browser title + favicon updated to match.
- **New logo mark.** Replaced the 🎓 emoji with an inline-SVG growth-line mark (gradient square) used
  in the auth panel (light variant) and topbar (dark variant), plus a matching SVG favicon.
- **Inclusive copy.** Auth hero now reads "A learning path built around you" with a
  "✦ For students & working professionals" pill; feature blurbs reworded to fit both audiences.
- **Adaptive dashboard.** Greeting + tagline change by user type (upskilling vs study); "Welcome back"
  when a name is set.
- **Misc polish:** selected-state ✓ badge on the type-choice cards, second decorative blob in the auth
  panel, accessible `:focus-visible` rings.
- **Verified:** `node --check app.js` clean; no user-facing "Student Journey" strings remain.

## 2026-06-27 — Phase 1 frontend: minimal SPA ✅
Built a small but polished UI for the journey (signup, signin, profile, preferences, dashboard).
- **Zero-build, framework-free:** `frontend/index.html` + `styles.css` + `app.js` only. Talks to the
  FastAPI backend over `fetch` with a Bearer JWT in `localStorage`. No `node_modules`, no bundler —
  keeps the UI throwaway-cheap until a possible Next.js rebuild for the company website.
- **Screens:** split-screen auth (sign in / sign up), branching onboarding (Student 🎓 vs Working
  Professional 💼 with type-aware forms + a chips input for skills/subjects/exams/colleges),
  preferences (segmented cadence/difficulty + notifications toggle + topic chips), and a dashboard
  rendering the `GET /users/me/profile` aggregate. Hash router with auth guards; toast + button
  loading states; responsive.
- **Signup UX:** since email send is deferred to Phase 5, the app auto-verifies with the token the
  API returns and logs straight in, then routes to the first unfinished step.
- **Design:** one cohesive CSS system (indigo/violet gradient, soft cards), system-font stack (offline-
  friendly, no CDN). Appeals to both students and professionals via the type-choice cards.
- **Run:** `cd frontend && python3 -m http.server 3000` → http://localhost:3000 (backend on :8000).
- **Verified:** `node --check app.js` clean; booted uvicorn and replayed the exact request sequence
  the SPA makes — CORS preflight from `localhost:3000` returns correct headers, and
  signup→verify→login→profile→preferences→dashboard all 200. Test users cleaned up.
- **Next:** Phase 2 — AI study material engine (now has both API + a UI to surface results in).

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
