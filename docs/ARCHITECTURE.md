# Architecture — Student Journey

## Style
Modular monolith (FastAPI) with strict module boundaries, so high-load /
specialized modules (`study_material`, `interviews`) can later be split into
independent services without a rewrite. Deliberately lean infra for now: just
the app + Postgres. A queue/scheduler (Redis/Celery or similar) is added **only
when a real need appears** (daily/weekly test generation, email digests).

```
                       ┌────────────────────────┐
   client / API user ─▶│  FastAPI app (gateway)  │
                       │  auth · routing         │
                       └───────────┬────────────┘
            ┌──────────────┬───────┼─────────┬───────────────┐
            ▼              ▼       ▼         ▼               ▼
        profiles/     study_      assess-   courses      interviews
        preferences   material    ments     (+certs)     (separate)
            │            │          │          │             │
            └────────────┴────┬─────┴──────────┴─────────────┘
                              ▼
                  ai_core (Ollama client, prompts,
                  structured output, search abstraction, guardrails)
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
       PostgreSQL (raw SQL,            Ollama Cloud      Email provider
       psycopg3, no ORM)              (multi-model)      (later, Phase 5)
       + pgvector for RAG (Phase 2)
```

## Modules
| Module | Responsibility |
|---|---|
| `auth` | signup/login, JWT, sessions, email verification |
| `users` / `profiles` | user type, professional/student profile data |
| `preferences` | learning goals, cadence, notification prefs |
| `courses` | catalog, enrollment, certifications, certificates |
| `study_material` | query builder, search providers, LLM curation, library, RAG index |
| `assessments` | MCQ generation, quiz engine, scoring, test scheduling, mock tests |
| `interviews` | **separate** — interviewer agent, evaluator, sessions, transcripts |
| `notifications` | email templates, triggers, scheduled digests |
| `analytics` | progress, mastery, dashboards, leaderboard |
| `ai_core` | shared Ollama client, prompt templates, JSON-schema structured output, search abstraction, guardrails |
| `db` | psycopg connection pool + raw-SQL migration runner |

## Data access — raw SQL, no ORM
We use **psycopg3** directly. No SQLAlchemy/Alembic. Reasons: the queries stay
visible and easy to reason about, and there's no ORM layer to learn or fight.

- Connections come from a pool (`app/db/pool.py`) with `dict_row`, so rows are dicts.
- Migrations are plain, forward-only `.sql` files in `app/db/migrations/`
  (`NNNN_description.sql`), applied in order by `python -m app.db.migrate`, tracked
  in a `schema_migrations` table.

### ID convention (every table)
```sql
create table example (
  id         bigint generated always as identity primary key,  -- internal: FKs, joins, indexes
  public_id  uuid not null default uuidv7() unique,            -- external: APIs, URLs (time-ordered)
  -- ... domain columns ...
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
```
- **`id`** (bigint) is internal — compact joins/indexes, never exposed.
- **`public_id`** (UUIDv7) is what leaves the system. UUIDv7 is time-ordered, so it
  indexes well and sorts by creation. `uuidv7()` is a SQL function defined in the
  baseline migration (PG16 has no built-in one).
- Foreign keys reference internal `id`; request/response bodies use `public_id`.

## Data model (high level)
- **Identity**: `users`, `profiles_professional`, `profiles_student`, `preferences`
- **Courses**: `courses`, `enrollments`, `certificates`
- **Study material**: `study_resources`, `saved_resources`, `resource_chunks` (vector)
- **Assessments**: `questions`, `quizzes`, `quiz_questions`, `attempts`, `attempt_answers`,
  `test_schedules`, `mock_tests`
- **Interviews**: `interview_sessions`, `interview_turns`, `interview_evaluations`
- **Notifications**: `email_templates`, `email_events`
- **Progress**: `progress`, `badges`, `streaks`

## AI design (`ai_core`)
- **Provider: Ollama Cloud.** One `ollama.Client` built from `OLLAMA_HOST` +
  `OLLAMA_API_KEY`. Multiple models are tiered by size/cost:
  - `cheap`   — small model  : bulk MCQ generation, summaries
  - `default` — medium model : study-material curation, the interviewer agent
  - `smart`   — large model  : hard evaluation / final scoring
- **Key rotation:** the user has a key-rotation service that serves Ollama
  responses; it's merged in later by replacing `LLMClient._build_client()` — the
  `complete()` / `parse()` call sites don't change.
- **Structured output:** `parse()` passes a Pydantic model's JSON schema as
  Ollama's `format`, then validates the response into the typed model (MCQs,
  interview rubrics).
- **Search abstraction:** `SearchProvider` interface → `TavilyProvider`,
  `DuckDuckGoProvider`, (optional) `SerpApiProvider`. Swappable via config.
- **RAG (Phase 2):** chunk + embed saved study material into pgvector; assessments
  and a future "chat with your material" feature retrieve from it.
- **Guardrails:** schema validation, source citation for study material, safety
  filtering, token/cost logging per call.

## Scheduling & async — deferred
No queue or scheduler yet. When daily/weekly test generation and email digests
need background/cron work, add Redis + a worker (Celery/RQ/APScheduler) then.
Until then, keep flows request-driven.

## Cross-cutting
- Config via env (`.env` + pydantic-settings). Secrets never committed.
- Tests via pytest. Formatting via black.
- Observability: structured logging, LLM call + token logging.

## Service-extraction seams (future)
`interviews` (latency/voice) and `study_material` (search/RAG heavy) are the
first candidates to become standalone services. Keep their interfaces clean now.
