# Phase 6 — Mock tests (formal) (visual guide)

> Text diagrams for the mock-test subsystem. Pairs with `ARCHITECTURE.md` (system
> design) and `ROADMAP.md` (status). Code lives in `backend/app/modules/assessments/`
> alongside the Phase 3 quiz engine — a mock test is the quiz's "exam" sibling, not
> a new module.
>
> **Mock test ≠ mock interview** (CLAUDE.md). This doc is only the *mock test*:
> objective MCQ, deterministic DB-side scoring, **single submission**. The mock
> *interview* (stateful, conversational, rubric-scored) is Phase 7 — a separate
> subsystem with its own data model.

---

## 1. Where it sits

```
                       ┌────────────────────────┐
   client / API user ─▶│  FastAPI app (gateway) │
                       │  auth · routing        │
                       └───────────┬────────────┘
        ┌──────────────┬───────────┼───────────┬──────────────┐
        ▼              ▼           ▼           ▼              ▼
   profiles/      study_       ASSESSMENTS   courses        interviews
   preferences    material     ├ quizzes     (+certs)       (Phase 7,
        │              │        └ MOCK TESTS                  separate)
        │              │  context │  (new) │
        │              │  (studied│        │ reuses ┌─────────────────┐
        ▼              └ material)└────────┴────────│ questions  bank │
   PostgreSQL (raw SQL, psycopg3)                   │ generator (MCQ) │
     mock_tests · mock_sections · mock_questions ·  │ resolve_topics  │
     mock_answers   (+ shared `questions`)          └─────────────────┘
```

The mock-test box lives **inside** the `assessments` module. It pulls on three
things that already existed for quizzes and changes none of them:

- the shared **`questions` bank** (each generated MCQ is stored there, just like a quiz's),
- the **MCQ `generator`** (called once per section),
- **`resolve_topics()`** + **`topic_material()`** (topics + the learner's studied
  material used to ground generation).

What's new is only the *container* (a sectional, timed, single-submission test) and
the *richer report* (section scores, percentile, time analysis, weak areas).

---

## 2. Data model

A test → ordered sections → ordered membership of question-bank rows on the left;
the **single attempt's** answers on the right. There is no separate `attempts`
table — a mock test is taken exactly once, so the answers and the submission stamp
live directly on the test.

```
   CONTAINER (generated once per take)        THE SINGLE ATTEMPT

   ┌──────────────────────────────┐
   │ mock_tests                   │           ┌──────────────────────────┐
   │  user_id  ───────────────────┼──────────▶│ users                    │
   │  title, difficulty           │  user_id  └──────────────────────────┘
   │  topics[] (union, listing)   │
   │  duration_seconds (0=untimed)│           ┌──────────────────────────┐
   │  total_questions (denorm)    │           │ mock_answers             │
   │  started_at  (lazy, on open) │◀──────────│  mock_test_id            │
   │  submitted_at (null = open)  │ mock_test │  question_id  ───────────┼─┐
   │  score (denorm at submit)    │   _id     │  selected_index (null=∅) │ │
   └──────────────┬───────────────┘           │  is_correct (snapshotted)│ │
                  │ mock_test_id              │  time_ms (optional)      │ │
                  ▼                           │  UNIQUE(test, question)  │ │
   ┌──────────────────────────────┐           └──────────────────────────┘ │
   │ mock_sections                │                                        │
   │  position (ordered)          │           ┌──────────────────────────┐ │
   │  title, topics[]             │           │ questions  (Phase 3 bank)│◀┘
   │  duration_seconds (0=none)   │           │  stem, options[]         │
   │  UNIQUE(test, position)      │           │  correct_index  ◀── key  │
   └──────────────┬───────────────┘           │  explanation, topic      │
                  │ mock_section_id           └────────────┬─────────────┘
                  ▼                                        ▲ question_id
   ┌──────────────────────────────┐                        │
   │ mock_questions               │────────────────────────┘
   │  (membership / ordering)     │  position-ordered slice of the bank
   │  PK(section, question)       │  per section (mirrors quiz_questions)
   │  UNIQUE(section, position)   │
   └──────────────────────────────┘
```

`mock_tests`, `mock_sections` carry the standard `id bigint` + `public_id uuid`
(uuidv7) pair. `mock_questions` is a pure join/ordering table (composite PK, no
public id). `mock_answers` has an `id` but is never addressed by `public_id` — it's
reached only through its test.

Why `score`/`total_questions` are **denormalized** onto `mock_tests`: listing "my
mock tests" and computing a percentile never re-aggregate `mock_answers`. They're
stamped once, DB-side, at submit — same philosophy as quiz scoring and course
progress.

### 2.1 Table definitions (DDL)

Verbatim shape from `app/db/migrations/0009_phase6_mock_tests.sql` (comments trimmed).

```sql
-- 1. mock_tests — the test container + its single submission stamps
create table mock_tests (
  id               bigint generated always as identity primary key,
  public_id        uuid not null default uuidv7() unique,
  user_id          bigint not null references users(id) on delete cascade,  -- FK → users
  title            text not null default 'Mock Test',
  difficulty       text not null default 'intermediate',
  topics           text[] not null default '{}',     -- union of section topics (listing)
  duration_seconds integer not null default 0,        -- overall limit (0 = untimed)
  total_questions  integer not null default 0,        -- denormalized count across sections
  started_at       timestamptz,                       -- stamped when taker first opens it
  submitted_at     timestamptz,                       -- null until submitted (single submission)
  score            integer,                           -- correct count, denormalized at submit
  created_at       timestamptz not null default now()
);
create index mock_tests_user_idx on mock_tests (user_id, created_at desc);
-- the cohort a percentile is computed against: submitted tests of a difficulty
create index mock_tests_cohort_idx on mock_tests (difficulty, submitted_at)
  where submitted_at is not null;

-- 2. mock_sections — ordered, optionally per-section-timed parts of a test
create table mock_sections (
  id               bigint generated always as identity primary key,
  public_id        uuid not null default uuidv7() unique,
  mock_test_id     bigint not null references mock_tests(id) on delete cascade,  -- FK → tests
  position         integer not null,
  title            text not null,
  topics           text[] not null default '{}',
  duration_seconds integer not null default 0,        -- optional per-section limit (0 = none)
  unique (mock_test_id, position)                      -- no two sections share a slot
);

-- 3. mock_questions — ordered membership of question-bank rows in a section
create table mock_questions (
  mock_section_id bigint not null references mock_sections(id) on delete cascade, -- FK → sections
  question_id     bigint not null references questions(id) on delete cascade,     -- FK → bank
  position        integer not null,
  primary key (mock_section_id, question_id),
  unique (mock_section_id, position)
);

-- 4. mock_answers — the single attempt's chosen option per question
create table mock_answers (
  id             bigint generated always as identity primary key,
  mock_test_id   bigint not null references mock_tests(id) on delete cascade,  -- FK → tests
  question_id    bigint not null references questions(id) on delete cascade,   -- FK → bank
  selected_index smallint,                            -- null = left blank
  is_correct     boolean not null default false,      -- snapshotted at scoring time
  time_ms        integer check (time_ms is null or time_ms >= 0),  -- per-question time (optional)
  unique (mock_test_id, question_id)                   -- one answer row per question
);
create index mock_answers_test_idx on mock_answers (mock_test_id);
```

### 2.2 Connections (foreign keys & cascade)

| Child table | Column | → References | On delete | Why |
|---|---|---|---|---|
| `mock_tests` | `user_id` | `users(id)` | `cascade` | drop a learner's tests when the learner is deleted |
| `mock_sections` | `mock_test_id` | `mock_tests(id)` | `cascade` | a section belongs to one test |
| `mock_questions` | `mock_section_id` | `mock_sections(id)` | `cascade` | membership is meaningless without its section |
| `mock_questions` | `question_id` | `questions(id)` | `cascade` | points at a real bank question |
| `mock_answers` | `mock_test_id` | `mock_tests(id)` | `cascade` | the attempt belongs to one test |
| `mock_answers` | `question_id` | `questions(id)` | `cascade` | the answer points at a real bank question |

Uniqueness that enforces the rules: `(mock_sections.mock_test_id, position)`,
`mock_questions` PK `(section, question)` **and** `(section, position)`,
`(mock_answers.mock_test_id, question_id)`.

Because FKs cascade, deleting a test tidies its whole subtree — no orphans:

```
delete mock_test ──► mock_sections ──► mock_questions   (membership only)
                 └─► mock_answers
delete user      ──► mock_tests ──► (sections, questions-membership, answers)
```

> Note the **asymmetry with courses**: `mock_questions`/`mock_answers` cascade-delete
> on a bank `question` being removed, but the generated `questions` rows are
> effectively owned by the test (created at generation time), so this is expected,
> not a shared-catalog hazard.

### 2.3 Worked example (sample rows)

Learner **Rohan** (`user_id = 5`) auto-generates a 2-section mock from his
preference topics `["python", "sql"]`, 2 questions per section. Internal `id`s
shown for clarity (APIs only ever expose `public_id`).

**Generated once (one MCQ-generator call per section; each MCQ lands in the bank):**

```
mock_tests
 id │ user_id │ title                 │ difficulty   │ topics        │ dur_s │ total │ started │ submitted │ score
 ───┼─────────┼───────────────────────┼──────────────┼───────────────┼───────┼───────┼─────────┼───────────┼──────
 80 │ 5       │ python & more — mock… │ intermediate │ {python, sql} │ 240   │ 4     │ NULL    │ NULL      │ NULL

mock_sections                                   (mock_test_id = 80)
 id │ test │ position │ title  │ topics    │ duration_seconds
 ───┼──────┼──────────┼────────┼───────────┼──────────────────
 90 │ 80   │ 0        │ python │ {python}  │ 120     (2 q × 60s)
 91 │ 80   │ 1        │ sql    │ {sql}     │ 120

questions  (shared bank — 4 new rows, correct_index hidden from taker)
 id  │ topic  │ stem        │ options                     │ correct_index
 ────┼────────┼─────────────┼─────────────────────────────┼───────────────
 501 │ python │ python Q0   │ {right, wrong, nope, no}    │ 0
 502 │ python │ python Q1   │ {...}                       │ 0
 503 │ sql    │ sql Q0      │ {...}                       │ 0
 504 │ sql    │ sql Q1      │ {...}                       │ 0

mock_questions                                  (ordered membership)
 mock_section_id │ question_id │ position
 ────────────────┼─────────────┼──────────
 90              │ 501         │ 0
 90              │ 502         │ 1
 91              │ 503         │ 0
 91              │ 504         │ 1
```

**Step A — Rohan opens the test to take it** (`GET /assessments/mock-tests/{pub-of-80}`).
First open of an unstarted, unsubmitted test lazily **starts the clock**:

```
update mock_tests set started_at = now() where id = 80;   -- only if started_at IS NULL and not submitted
→ mock_tests(80).started_at = 2026-06-29 10:00:00
```

The taker view returns sections + questions with **`options` but no `correct_index`/
`explanation`** — the answer key stays server-side until submit.

**Step B — he submits** (`POST /assessments/mock-tests/{pub-of-80}/submit`), getting
the python section right (index 0) and the sql section wrong (index 1), 5 s each:

```
-- the router scores each question against the server-side key, then:
insert into mock_answers (mock_test_id, question_id, selected_index, is_correct, time_ms) values
 (80, 501, 0, true,  5000),
 (80, 502, 0, true,  5000),
 (80, 503, 1, false, 5000),
 (80, 504, 1, false, 5000);

update mock_tests set score = 2, submitted_at = now() where id = 80;
→ score=2 / total=4 ⇒ 50.0%
```

A **second** submit is rejected with `409` (`submitted_at` is already set).

**Step C — the report** (returned by submit, re-fetchable at `…/report`) rolls the
answers up per section and per topic in one pass:

```
sections:  python → 2/2 = 100.0% (avg 5.0s/q)
           sql    → 0/2 =   0.0% (avg 5.0s/q)
weak_areas: [{topic: sql, answered: 2, correct: 0, accuracy: 0.0}]   (< 60% threshold)
next_steps: ["sql"]                                                   (top-3 weakest)
percentile: % of submitted intermediate tests scoring ≤ 50%          (incl. this one)
time:      duration 240s · time_taken = submitted_at − started_at · avg 5.0s/q
```

**The percentile query** (`_percentile`) — cohort = submitted tests of the same
difficulty; "at or below" includes this test, so a lone test → 100:

```sql
select count(*) as n,
       count(*) filter (where total_questions > 0 and 100.0*score/total_questions <= 50.0) as le
from mock_tests
where difficulty = 'intermediate' and submitted_at is not null;
-- percentile = round(100.0 * le / n, 1)
```

---

## 3. Generation: request → sections → MCQ generator → persist

Two input modes, one persistence path. `mock.generate()` resolves the section
specs, calls the existing MCQ generator **once per section** (grounded in that
section's studied material), then hands the assembled sections to
`mock_repository.create_mock_test()` to persist in one transaction.

```
  POST /assessments/mock-tests/generate
    body: GenerateMockTestIn
          { title?, difficulty?, duration_minutes?,
            sections?[ {title, topics[], num_questions, duration_minutes?} ],
            topics?[], num_sections, questions_per_section }   ← auto-mode knobs
            │
            ▼
   resolve_topics(overrides=body.topics, preference_topics, profile, user_type)
            │   (only needed for AUTO mode; explicit sections carry own topics)
            ▼
   _section_specs(body, default_topics)
     ├─ EXPLICIT  body.sections → one spec each (topics fall back to default_topics)
     └─ AUTO      one spec per resolved topic, capped at num_sections,
                  questions_per_section each
            │
            ▼   for each spec:
   ┌────────────────────────────────────────────────────┐
   │ context  = quiz_repo.topic_material(user, topics)  │  ← studied material (grounding)
   │ questions= generator.generate(topics, difficulty,  │  ← the SAME Phase-3 MCQ generator
   │              num_questions, context)               │
   │ duration = duration_minutes×60                     │
   │            else len(questions) × 60s   (1 min/q)   │  ← _SECONDS_PER_QUESTION
   │ section produced 0 questions?  → DROP it (logged)  │
   └────────────────────────────────────────────────────┘
            │
            ▼   no section survived?  → return None → router 502 (_NO_MOCK_Q)
   overall duration = body.duration_minutes×60  else  Σ section durations
   topics_union     = order-preserving de-duped union of section topics
            │
            ▼
   create_mock_test(...)  → INSERT test + sections + bank questions + membership
                            (one transaction) → returns the taker view
```

Guard: if auto mode resolves **no** topics *and* no section carries its own topics,
the router returns `422` before calling the LLM.

> **Scheduled** (daily/weekly) generation is deferred until a scheduler/queue is
> introduced — same deferral as Phase 3 daily/weekly tests. On-demand is the v1
> surface; the scheduled path will reuse this exact `mock.generate()` call.

---

## 4. Take → submit → report (single submission)

```
  OPEN / RESUME          SUBMIT (once)                   REPORT
  ─────────────          ─────────────                   ──────
  GET /mock-tests/{id}   POST /mock-tests/{id}/submit    (returned by submit, and)
       │                      body: {answers:[           GET /mock-tests/{id}/report
       ▼                        {question_id,                  │
  taker view              selected_index?, time_ms?} ]}        ▼
  (sections+questions,         │                          submitted?  no → 404
   NO answer key)              ▼                                │ yes
       │               already submitted? ──yes──► 409          ▼
   first open of an            │ no                       per-section + per-topic
   unstarted test:             ▼                          rollups, percentile,
   started_at = now()    score each answer vs the         time analysis, weak
   (clock starts)        server-side correct_index;       areas, next_steps,
                         insert mock_answers;             revealed answer key
                         score + submitted_at = now()
```

Scoring is deterministic and entirely server-side: the client never sees
`correct_index` until the report. `is_correct = (selected_index is not None and
selected_index == correct_index)`; blanks (`null`) are wrong. The `409` on a second
submit is the single-submission guarantee.

The **frontend** (zero-build SPA) mirrors this: a hub (`#/mock-tests`) to generate +
see history, a sectional **timed taker** (`#/mock/{id}`) with a live countdown that
**auto-submits at 0** and keeps the key hidden, and a report view
(`#/mock/{id}/report`) with per-section bars, time analysis, and weak areas that
deep-link "Quiz me on this" back into the Phase 3 quiz generator.

---

## 5. The report — what makes a mock more than a quiz

`mock_repository.report()` reads every question with its answer in one join, then
derives, in a single pass:

```
  ┌─ score / total / percentage ── round(100·score/total, 1)
  │
  ├─ percentile ───────────────── vs submitted tests of the SAME difficulty
  │                                (% scoring at-or-below; lone test → 100)
  │
  ├─ sections[] ──────────────── per-section {total, correct, accuracy,
  │                                avg_seconds_per_question, duration_seconds}
  │
  ├─ time ────────────────────── duration_seconds (limit),
  │                                time_taken = submitted_at − started_at,
  │                                avg/q: summed per-q timings, else clock÷total
  │
  ├─ weak_areas[] ─────────────── per-topic accuracy < 60% (_WEAK_THRESHOLD),
  │                                sorted worst-first
  │
  ├─ next_steps[] ────────────── the 3 weakest topics (→ "study/quiz these next")
  │
  └─ answers[] ────────────────── full key revealed: selected, correct_index,
                                   is_correct, explanation  (per question)
```

`time_ms` per question is **optional** — when the client doesn't track per-question
timing, section `avg_seconds_per_question` is `null` and the overall average falls
back to `time_taken ÷ total`.

---

## 6. Mock test vs quiz — the deliberate differences

Both reuse the `questions` bank, the MCQ generator, and DB-side scoring. The
container and lifecycle differ on purpose (CLAUDE.md: "Mock test = objective MCQ,
deterministic scoring, single submission").

```
                    QUIZ (Phase 3)                 MOCK TEST (Phase 6)
  ────────────────  ────────────────────────────   ────────────────────────────────
  structure         flat list of questions         sections → questions (ordered)
  timing            untimed                         overall + optional per-section limits
  attempts          re-attemptable (quiz_attempts)  SINGLE submission (no attempts table)
  answers live in   quiz_attempt_answers            mock_answers (directly on the test)
  clock             —                               started_at lazily set on first open
  report            score + per-topic accuracy      + section scores, percentile,
                                                       time analysis, weak areas, next steps
  table family      quizzes/quiz_questions/…        mock_tests/mock_sections/mock_questions/…
  shared            questions bank · generator · resolve_topics() · topic_material()
```

---

## 7. API surface (all under `/assessments`, learner-auth)

```
  POST   /assessments/mock-tests/generate        GenerateMockTestIn → MockTestOut (taker view)
  GET    /assessments/mock-tests                 → [MockTestSummary]  (history; derived status)
  GET    /assessments/mock-tests/{public_id}     → MockTestOut  (taker view; first open starts clock)
  POST   /assessments/mock-tests/{public_id}/submit  SubmitMockTestIn → MockReport  (once; else 409)
  GET    /assessments/mock-tests/{public_id}/report  → MockReport     (404 until submitted)
```

Status / error codes: `422` no topics (auto mode, nothing to generate from) ·
`502` model returned no usable questions for any section · `503` LLM not configured ·
`404` unknown id or report-before-submit · `409` second submit.

---

## 8. Module layout

```
  backend/app/modules/assessments/        (mock test lives beside the quiz engine)
    schemas.py          + GenerateMockTestIn / MockSectionSpec (generation contract)
                        + MockTestOut / MockSectionOut (taker views, no key)
                        + MockTestSummary (history), SubmitMockTestIn / MockAnswerIn
                        + MockReport / SectionScore / TimeAnalysis (report)
    mock.py             orchestration: _section_specs (explicit|auto), per-section
                        generate + ground + drop-empty, assemble + persist
    mock_repository.py  raw SQL: create_mock_test (1 txn), get_mock_test (taker view +
                        lazy start), list_mock_tests, answer_key, record_submission,
                        report (+ _percentile)
    router.py           + /mock-tests/* routes (generate/list/get/submit/report)

  reused unchanged:
    assessments/generator.py        the MCQ generator (called once per section)
    assessments/repository.py       topic_material() (grounding context)
    study_material/query_builder.py resolve_topics()
    db/migrations …/questions       the shared question bank

  touched elsewhere:
    db/migrations/0009_phase6_mock_tests.sql   schema (tests/sections/questions/answers)
    frontend/app.js, styles.css                hub + timed taker + report SPA views
    backend/tests/test_mock_tests_flow.py      auto/explicit gen, take→submit→report, guards
```
