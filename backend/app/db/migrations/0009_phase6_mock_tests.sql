-- Phase 6 — Formal mock tests.
--
-- A mock test is the "exam" sibling of the Phase 3 quiz: full-length, split into
-- timed SECTIONS, larger question sets, and SINGLE-SUBMISSION (taken once, then
-- reported on) — unlike quizzes which are re-attemptable. It reuses the Phase 3
-- `questions` bank and deterministic, DB-side scoring; only the container and the
-- richer report (section scores, percentile, time analysis, weak areas) are new.
--
-- Shape: mock_tests → mock_sections (ordered) → mock_questions (ordered membership
-- of `questions`). The single attempt's chosen options live directly on the test
-- as `mock_answers` (no separate attempts table — there is exactly one take).
--
-- Scheduling (daily/weekly auto-generation) is deliberately deferred until a
-- scheduler/queue is introduced; on-demand generation is the v1 surface.

-- ── mock_tests ────────────────────────────────────────────────────────────────
create table mock_tests (
  id               bigint generated always as identity primary key,
  public_id        uuid not null default uuidv7() unique,
  user_id          bigint not null references users(id) on delete cascade,
  title            text not null default 'Mock Test',
  difficulty       text not null default 'intermediate',
  topics           text[] not null default '{}',     -- union of section topics (for listing)
  duration_seconds integer not null default 0,        -- overall time limit (0 = untimed)
  total_questions  integer not null default 0,        -- denormalized count across sections
  started_at       timestamptz,                       -- stamped when the taker first opens it
  submitted_at     timestamptz,                       -- null until submitted (single submission)
  score            integer,                           -- correct count, denormalized at submit
  created_at       timestamptz not null default now()
);
create index mock_tests_user_idx on mock_tests (user_id, created_at desc);
-- the cohort a percentile is computed against: submitted tests of a difficulty
create index mock_tests_cohort_idx on mock_tests (difficulty, submitted_at)
  where submitted_at is not null;

-- ── mock_sections ───────────────────────────────────────────────────────────────
create table mock_sections (
  id               bigint generated always as identity primary key,
  public_id        uuid not null default uuidv7() unique,
  mock_test_id     bigint not null references mock_tests(id) on delete cascade,
  position         integer not null,
  title            text not null,
  topics           text[] not null default '{}',
  duration_seconds integer not null default 0,        -- optional per-section limit (0 = none)
  unique (mock_test_id, position)
);

-- ── mock_questions ────────────────────────────────────────────────────────────────
-- Ordered membership of question-bank rows in a section (mirrors quiz_questions).
create table mock_questions (
  mock_section_id bigint not null references mock_sections(id) on delete cascade,
  question_id     bigint not null references questions(id) on delete cascade,
  position        integer not null,
  primary key (mock_section_id, question_id),
  unique (mock_section_id, position)
);

-- ── mock_answers ────────────────────────────────────────────────────────────────
-- The single attempt's chosen option per question. `is_correct` is snapshotted at
-- scoring time; `time_ms` is the taker's time on that question (optional, for the
-- time-analysis report) — null when the client doesn't track per-question timing.
create table mock_answers (
  id             bigint generated always as identity primary key,
  mock_test_id   bigint not null references mock_tests(id) on delete cascade,
  question_id    bigint not null references questions(id) on delete cascade,
  selected_index smallint,
  is_correct     boolean not null default false,
  time_ms        integer check (time_ms is null or time_ms >= 0),
  unique (mock_test_id, question_id)
);
create index mock_answers_test_idx on mock_answers (mock_test_id);
