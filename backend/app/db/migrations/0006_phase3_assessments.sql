-- Phase 3 — Quiz / MCQ engine.
--
-- A learner generates a quiz from their topics (and, when available, the study
-- material they've been reading). The LLM produces MCQs which we persist as a
-- question bank (`questions`), bundle into a `quizzes` row, and order via the
-- `quiz_questions` join. Taking a quiz creates an `attempt`; each chosen option
-- is an `attempt_answers` row. Scoring is deterministic (selected vs correct
-- index) — single source of truth is the DB, not the model.
--
-- Mock tests / mock interviews are SEPARATE subsystems (later phases); this is
-- the lightweight quiz engine only.

-- ── questions ─────────────────────────────────────────────────────────────────
-- One MCQ. Options are an ordered text[]; `correct_index` points into it (0-based).
-- `created_by` is the user who generated it (questions aren't shared across users
-- in v1 — generation is cheap and per-learner). `topic`/`difficulty` mirror the
-- study-material vocabulary so progress can be rolled up per topic later.
create table questions (
  id           bigint generated always as identity primary key,
  public_id    uuid not null default uuidv7() unique,
  created_by   bigint not null references users(id) on delete cascade,
  topic        text not null default '',
  difficulty   text not null default 'beginner',
  stem         text not null,
  options      text[] not null,
  correct_index smallint not null,
  explanation  text not null default '',
  created_at   timestamptz not null default now(),
  -- keep the data honest: a real MCQ has >= 2 options and the answer is in range
  constraint questions_options_len  check (cardinality(options) between 2 and 6),
  constraint questions_answer_range check (correct_index >= 0 and correct_index < cardinality(options))
);
create index questions_created_by_idx on questions (created_by, created_at desc);

-- ── quizzes ─────────────────────────────────────────────────────────────────
-- A generated bundle of questions for one user.
create table quizzes (
  id           bigint generated always as identity primary key,
  public_id    uuid not null default uuidv7() unique,
  user_id      bigint not null references users(id) on delete cascade,
  title        text not null default 'Quiz',
  difficulty   text not null default 'beginner',
  topics       text[] not null default '{}',
  created_at   timestamptz not null default now()
);
create index quizzes_user_idx on quizzes (user_id, created_at desc);

-- ── quiz_questions ────────────────────────────────────────────────────────────
-- Ordered membership of questions in a quiz (a question could be reused across
-- quizzes; `position` fixes the display order within one quiz).
create table quiz_questions (
  quiz_id     bigint not null references quizzes(id) on delete cascade,
  question_id bigint not null references questions(id) on delete cascade,
  position    integer not null,
  primary key (quiz_id, question_id),
  unique (quiz_id, position)
);

-- ── attempts ────────────────────────────────────────────────────────────────
-- One take of a quiz. Scored at submit time; `score`/`total` are denormalized so
-- listing history doesn't have to re-aggregate answers. A quiz may be re-attempted.
create table attempts (
  id           bigint generated always as identity primary key,
  public_id    uuid not null default uuidv7() unique,
  quiz_id      bigint not null references quizzes(id) on delete cascade,
  user_id      bigint not null references users(id) on delete cascade,
  score        integer not null default 0,
  total        integer not null default 0,
  submitted_at timestamptz not null default now()
);
create index attempts_quiz_idx on attempts (quiz_id, submitted_at desc);
create index attempts_user_idx on attempts (user_id, submitted_at desc);

-- ── attempt_answers ───────────────────────────────────────────────────────────
-- The learner's chosen option per question for one attempt. `is_correct` is
-- snapshotted at scoring time (cheap reads; immune to later question edits).
create table attempt_answers (
  id             bigint generated always as identity primary key,
  attempt_id     bigint not null references attempts(id) on delete cascade,
  question_id    bigint not null references questions(id) on delete cascade,
  selected_index smallint,
  is_correct     boolean not null default false,
  unique (attempt_id, question_id)
);
