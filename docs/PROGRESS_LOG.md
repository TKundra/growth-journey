# Progress Log — Student Journey

Newest entries on top. One entry per working session: what was decided/built,
and what's next.

---

## 2026-06-29 — Phase 4: Courses & certifications
- **What:** a first-class course subsystem — three-level catalog, enrolment, deterministic
  progress, auto-issued certificates, an admin authoring surface, and a topic seam that
  grounds study material + quizzes in a course's syllabus.
- **Data model (`0007_phase4_courses.sql`):** `courses` → `course_modules` → `course_lessons`
  (topics live on the leaf lesson); `enrollments` (denormalized `progress`/`status`),
  `lesson_progress`, `certificates` (`serial` JNY-YYYY-NNNNNN, `revoked_at`). Added
  `users.role` (learner|admin) — the first permission concept (distinct from `user_type`).
  `courses.(source, external_ref)` partial-unique index = the **ETL idempotency seam**:
  org courses import via the same write path, matched on external_ref instead of slug.
- **Strategy:** build our own catalog now so the model is concrete; the admin authoring
  payload (`CourseUpsertIn`, nested modules+lessons) IS the contract a future ETL job
  targets. Recommendations already work against our own catalog (topic/tag overlap) — no
  org data required.
- **Backend (`app/modules/courses/`):** `repository.py` (catalog, recommend, detail tree,
  enroll, `mark_lesson_complete` → recompute progress DB-side → issue cert at 100% on
  conflict-skip, topic aggregation, admin upsert/publish/delete, cert lookup/revoke);
  learner `router.py` + public `certificates_router` (unauthenticated HTML verify page);
  admin `admin_router.py` gated by new `require_admin`. Wired into `main.py`.
- **Linking:** `course_id`/`module_id` added to `POST /study-material/generate` and
  `POST /assessments/quizzes/generate`; the course's lesson topics enter `resolve_topics`
  as overrides. No engine internals changed.
- **Auth:** `role` added to `_PUBLIC_COLS` + `UserOut` (so the SPA can gate the admin UI),
  and `require_admin` dependency (403 for non-admins, 401 anonymous).
- **Seed (`app/db/seed_phase4.py`):** idempotent — an admin (`admin@journey.app`/`admin12345`)
  + 3 of our own published courses (Python for Data, System Design, Quant Aptitude).
- **Frontend:** Courses tab (Discover / For-you / My-courses + cards with progress/completed),
  course detail (syllabus, enrol, per-lesson complete, "Study this"/"Quiz me", certificate
  card → verify link), minimal admin section (JSON authoring = ETL shape, publish/delete),
  dashboard Courses panel. New CSS for course/syllabus/lesson/admin components.
- **Certificate:** styled standalone HTML at `/certificates/verify/{public_id}` (shareable,
  print-to-PDF); admin revoke flips a banner. Real server-side PDF deferred.
- **Verified:** 56 pytest green (+5: role gate, idempotent upsert, full enrol→progress→
  certificate, recommendations exclude enrolled, course→quiz topic seam); full UI driven
  headless (puppeteer-core + system Chrome) end-to-end against the live API — 13 steps,
  **zero console errors**. One bug found+fixed in the process: `UserOut` was missing `role`
  so the admin UI couldn't gate.
- **Docs:** `docs/PHASE4_COURSES.md` — text diagrams (data model, flows, topic seam, ETL
  contract, module layout).
- **Deferred:** server-rendered PDF certificates; re-authoring a live enrolled course
  rebuilds its lesson tree (cascades `lesson_progress`) — fine pre-enrolment, revisit later.

## 2026-06-28 — Phase 3: Quiz / MCQ engine (backend)
- **What:** new `assessments` module — generate a quiz from the learner's topics, take it, submit for
  deterministic scoring, review results with explanations, and see per-topic accuracy.
- **Data model (`0006_phase3_assessments.sql`):** `questions` (MCQ bank: `options text[]` +
  `correct_index`, with CHECK constraints for ≥2 options and an in-range answer), `quizzes`,
  `quiz_questions` (ordered membership), `attempts` (denormalized score/total), `attempt_answers`
  (per-question choice + snapshotted `is_correct`).
- **Generation (`generator.py`):** `cheap` tier, schema-constrained via `llm.parse`. Cheap models
  (gpt-oss:20b) ignore the strict schema in practice — they return a **bare array**, rename `stem`→
  `question`, and answer by **letter/option-text** instead of index. `schemas.py` now normalizes all of
  that (unwrap array/alternate wrapper key, map alias fields, resolve the answer to a 0-based index;
  option-text match wins over a numeric reading so `"4"` ∈ `["3","4"]` → index 1). Unresolvable answers
  become index -1 and the question is dropped rather than mis-scored. Generation is grounded in the
  user's studied material (`repository.topic_material`, best-effort).
- **API:** `POST /assessments/quizzes/generate`, `GET /assessments/quizzes`, `GET .../{id}` (taker view —
  **no answer key**), `POST .../{id}/submit` (scores + reveals correct index/explanations), `GET
  .../{id}/result`, `GET /assessments/stats`. Scoring is server-side/deterministic; blank answers are
  wrong, never errors.
- **Frontend (`frontend/app.js` + `styles.css`):** quizzes flow added to the zero-build SPA — `#/quizzes`
  (generate control + history cards with best-score pills + per-topic progress bars), `#/quiz/<id>` (timed
  take view with radio options + live answered-count), `#/quiz/<id>/result` (score ring + per-question
  correct/wrong marking + explanations). Sidebar + dashboard now link to it. Verified headless
  (puppeteer-core + system Chrome) end-to-end against the live API: generate → answer → submit → result →
  history/stats, **zero console errors**.
- **Verified:** live gpt-oss:20b run produced 3 well-formed MCQs (load balancing / caching) with answers
  spread across positions; 50 pytest green (+17: generator validation, LLM-output tolerance, full
  generate→take→submit→result→stats flow incl. 404s and blank submissions); full UI flow driven headless.
- **Deferred:** `test_schedules` + scheduler/queue (roadmap says introduce only when first needed);
  accuracy **trend** over time.

## 2026-06-28 — Fix: semantic library search returned zero results (ivfflat → HNSW)
- **Bug:** searching the library (e.g. "load balancing") returned **0 hits** even with a clearly relevant
  saved resource. Root cause was the vector **index**, not the data: `resource_chunks.embedding` used an
  IVFFlat index (`lists=100`) and IVFFlat probes only **one** cell per query by default, so the
  `ORDER BY <=> … LIMIT` (which uses the index) visited a cell holding none of the saved rows. A seq scan
  returned all rows; `set ivfflat.probes=100` returned all rows — confirming the index.
- **Fix (`0005_fix_chunk_vector_index.sql`):** swap IVFFlat → **HNSW** (`vector_cosine_ops`). HNSW has
  near-exact recall at any corpus size with no per-query knob, so search works from the first saved row.
  Verified: all three test queries return ranked hits with the right resource first.
- **Docs:** updated `JOURNEY.md` to reflect SearXNG as the default search provider (was still describing
  Tavily-primary/DDG-fallback) across the flow diagram, search-abstraction listing, config keys, and the
  compose/infra summary.

## 2026-06-28 — SearXNG search + multi-format material (YouTube videos)
- **Why:** DuckDuckGo (the old default) is rate-limited/flaky and articles-only. Goal: better, free,
  reliable search + richer material (videos).
- **SearXNG provider:** added `app/ai_core/search/searxng.py` (`SearxngProvider`) hitting a self-hosted
  SearXNG JSON API — aggregates many engines, no API key. New docker-compose `searxng` service +
  `searxng/settings.yml` (JSON format enabled, limiter off for local). `SEARCH_PROVIDER=searxng` is the
  new default; DuckDuckGo stays as the keyless fallback, Tavily optional. Config: `SEARXNG_URL`.
- **Videos:** `SearchProvider.search_videos()` (SearXNG `videos` category → YouTube; DDG `videos()`
  fallback). Results carry `kind="video"`; the curator gathers article + video candidates and the LLM
  keeps a format mix (videos tagged `kind=video`).
- **Quality polish:** multi-angle article queries per topic (`build_queries`: learn + practice angles) +
  video queries (`build_video_queries`); all searches run **concurrently** (ThreadPoolExecutor) so added
  angles don't add latency; per-domain diversity cap (`_MAX_PER_DOMAIN=3`, videos exempt).
- **Robustness fix:** `CuratedItem.kind` loosened from a `Literal` to `str` + coerced onto the allowed set
  in `curate()` — gpt-oss was echoing the candidate's display tag into `kind` and failing the parse.
- **Verified:** live SearXNG run returns a stable mixed feed (e.g. Google/Kaggle/MLMastery + 3 YouTube
  incl. a 6-hr course), ~2s, no fallback; 33 pytest green (added video-tagging, domain-diversity,
  gather-dedup, and SearXNG-parsing tests). DDG flakiness confirmed as the prior root cause.
- **Next (optional):** page-content fetch for RAG depth; per-topic query angle tuning.

## 2026-06-28 — Normalize study material (kill cross-user duplication)
- **Problem:** `study_resources` was keyed **per user** (`unique (user_id, url)`), so a popular
  URL got a separate row — with duplicated title/summary/tags — for every user. Worse,
  `resource_chunks` hung off that per-user row, so the same URL was **re-embedded and its
  768-dim vectors re-stored once per user** (embeddings are the expensive part).
- **Fix (migration `0004_normalize_resources.sql`):** split into
  - `resources` — canonical, **URL-unique**, shared across users; holds the URL-intrinsic
    fields. `resource_chunks` now hangs off this → **each URL is embedded exactly once** and
    reused by everyone.
  - `feed_items` — the per-user feed (which user saw it, the `topic` it served them, their
    `relevance` rank). `saved_resources` + `resource_chunks` repointed at the canonical id.
  - Existing data preserved & deduped: 36 per-user rows → 22 canonical resources (14 dup URLs
    collapsed), feed/saved rows intact.
- **Code:** `repository.py` rewritten around `resources`+`feed_items` (new `_USER_RESOURCE_COLS`
  join; `_feed_resource_id` authorizes save/unsave to the user's feed). `rag.index_saved_resource`
  now **reuses existing chunks** (`chunks_exist`) instead of re-embedding a shared URL, and
  dropped its `user_id` param. **Wire API (`StudyResourceOut`) unchanged** — canonical
  `resources.public_id` is the resource's external id.
- **Verified:** new `test_resources_are_shared_across_users` proves two users curating the same
  URLs share one canonical row + the same `public_id` while keeping separate feed entries; 28
  pytest green.

## 2026-06-28 — Fix: embeddings 401 (RAG indexing silently skipped)
- **Bug:** Saving a resource never indexed it — `client.embed()` returned `401 Unauthorized`
  from `https://ollama.com/api/embed`, caught by `rag.index_saved_resource`'s broad `except`,
  so the save succeeded but no chunks were embedded/stored.
- **Root cause:** the API key is valid (chat works), but **Ollama Cloud serves only
  generative/chat models — there is no embedding model in its catalog**, so `/api/embed`
  returns 401 for *every* model (`nomic-embed-text`, `mxbai-embed-large`, `bge-m3`, …).
  Verified against the live cloud `list()` — all chat models, zero embedding models.
- **Fix:** embeddings now run on a **separate host** (`OLLAMA_EMBED_HOST`, default
  `http://localhost:11434`) via a dedicated `LLMClient._build_embed_client()`; chat/curation
  stay on the cloud. Added `OLLAMA_EMBED_HOST` / `OLLAMA_EMBED_API_KEY` settings (embed auth
  optional — local Ollama needs none) and a guard that raises `LLMNotConfigured` if the embed
  host is mistakenly pointed at `ollama.com`. Updated `.env.example` + `ARCHITECTURE.md`.
- **Verified:** `get_llm().embed([...])` returns 768-dim vectors against local Ollama
  (`nomic-embed-text` already pulled); 27 pytest green.
- **Next:** ensure deploy/dev environments run a local Ollama with `nomic-embed-text` pulled
  (`ollama pull nomic-embed-text`), or set `OLLAMA_EMBED_HOST` to a self-hosted embed endpoint.

## 2026-06-27 — Fix: tolerant structured-output parsing (Generate 500)
- **Bug:** `POST /study-material/generate` returned 500 against live Ollama Cloud — the
  `gpt-oss:120b` model ignored the JSON-schema `format` constraint and wrapped the object in prose +
  a ```json fence, so `model_validate_json()` raised `json_invalid` on the leading `**Recommended…`.
- **Fix 1 (shape):** `LLMClient.parse()` now falls back to `_extract_json()` (strips code fences /
  slices the first `{`…`}` or `[`…`]`) and re-validates; tightened the curator system prompt to demand
  JSON-only.
- **Fix 2 (fields):** the model also omitted `summary`/`topic` (and sometimes `title`). Made those
  optional in `CuratedItem` (only `url` is hard-required) and **backfill** them from the originating
  candidate in `curator.curate()` (topic/title from the candidate, summary from its snippet). The
  anti-hallucination guardrail still drops any non-candidate URL.
- Both fixes benefit every structured call (future MCQ gen, rubrics).
- **Verified:** reproduced both failing payloads in unit tests; 27 pytest green. Live server picks it
  up on `--reload`.

## 2026-06-27 — Phase 2: AI study material engine ⭐ v1
Built the full study-material journey: profile + preferences → search → LLM curation → per-user
feed → save-to-library → semantic search.
- **DB (`0003_phase2_study_material.sql`):** `study_resources` (per-user curated feed, `(user_id, url)`
  unique so regeneration dedupes), `saved_resources` (library promotion), `resource_chunks`
  (pgvector `vector(768)` + IVFFlat cosine index). Enabled the `vector` extension. Reuses
  `set_updated_at()` and the int-id/uuidv7 convention.
- **`ai_core`:** added `LLMClient.embed()` (Ollama embeddings) + `llm_model_embed` setting
  (nomic-embed-text, 768-d — kept in sync with the vector column).
- **`study_material` module:**
  - `query_builder.py` — pure functions: resolve topics (overrides → preferences → profile-derived)
    and build per-topic search queries with a difficulty hint.
  - `curator.py` — search with **Tavily-primary / DuckDuckGo-fallback** resilience, then LLM curation
    (dedupe, rank, summarize, tag) with an **anti-hallucination guardrail** (drops any URL not in the
    candidate set).
  - `rag.py` — word-boundary chunking + best-effort embed/index on save; cosine semantic search over
    the library. Degrades gracefully with no `OLLAMA_API_KEY` (indexing no-ops, search → 503).
  - `repository.py` (raw SQL) + `router.py`: `POST /study-material/generate`, `GET /study-material`
    (feed w/ `is_saved`), `GET /{id}`, `POST|DELETE /{id}/save`, `GET /library`, `GET /library/search`.
- **Frontend:** new **Study material** view (now a real sidebar tab) — Discover/My-library sub-tabs,
  ✦ Generate, resource cards (kind, relevance, domain, time, tags) with Save/Saved toggle, library
  semantic search box, glassy empty states. Dashboard "What's next" → live "Browse study material".
- **Verified:** 23 `pytest` green (11 new: query-builder/curation/chunk unit tests + a monkeypatched
  generate→feed→save→library→unsave integration flow against Postgres); `black` clean; migration
  applied; routes confirmed via OpenAPI; repository smoke-tested end-to-end against Postgres.
- **Note:** RAG retrieval consumers (Phase 3 MCQ gen, "chat with your material") will read from
  `resource_chunks`. Curation/embeddings need a live `OLLAMA_API_KEY`; everything else runs without it.
- **Next:** Phase 3 — Quiz / MCQ engine + daily/weekly tests.

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
