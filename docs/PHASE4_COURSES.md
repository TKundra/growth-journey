# Phase 4 — Courses & Certifications (visual guide)

> Text diagrams for the courses subsystem. Pairs with `ARCHITECTURE.md` (system
> design) and `ROADMAP.md` (status). Code lives in `backend/app/modules/courses/`.

---

## 1. Where it sits

```
                       ┌────────────────────────┐
   client / API user ─▶│  FastAPI app (gateway) │
                       │  auth · routing        │
                       └───────────┬────────────┘
        ┌──────────────┬───────────┼───────────┬──────────────┐
        ▼              ▼           ▼           ▼              ▼
   profiles/      study_       assess-      COURSES        interviews
   preferences    material     ments       (+certs)       (separate)
        │              ▲           ▲           │
        │              │  topics   │  topics   │   ← course syllabus feeds
        │              └───────────┴───────────┘     study_material + assessments
        ▼
   PostgreSQL (raw SQL, psycopg3)        ← courses, modules, lessons, enrollments,
                                            lesson_progress, certificates
```

The courses module is the new box. Its only outward pull on other modules is the
**topic seam** (§4): a course's lesson topics are handed to the existing study /
quiz generators. Nothing in those engines had to change beyond accepting a
`course_id`.

---

## 2. Data model

Three-level content tree on the left; per-learner progress on the right. Lines
show foreign keys (child → parent). Every table also has the standard
`id bigint` + `public_id uuid` (uuidv7) pair.

```
   CONTENT (authored once)                 PER-LEARNER (one row per enrollment)

   ┌──────────────────────────┐
   │ courses                  │            ┌──────────────────────────┐
   │  slug (unique)           │            │ users                    │
   │  title, subtitle, descr  │            │  role: learner | admin   │◀──┐
   │  level, category, tags[] │            └──────────────────────────┘   │
   │  source: internal|import │                        ▲                  │
   │  external_ref  ──────────┼── ETL idempotency      │ user_id          │
   │  is_published            │   (source,external_ref)│                  │
   └────────────┬─────────────┘            ┌───────────┴───────────────┐  │
                │ course_id                │ enrollments               │  │
                ▼                          │  status: active|completed │  │
   ┌──────────────────────────┐            │  progress: 0..100         │  │
   │ course_modules           │            │  completed_at             │  │
   │  position (ordered)      │            │  UNIQUE(user_id,course_id)│  │
   │  title, summary          │            └───────────┬───────────────┘  │
   └────────────┬─────────────┘                        │ enrollment_id    │
                │ module_id                            │                  │
                ▼                          ┌───────────▼───────────────┐  │
   ┌──────────────────────────┐            │ lesson_progress           │  │
   │ course_lessons           │◀───────────│  lesson_id  ──────────────┼──┘
   │  position (ordered)      │ lesson_id  │  completed_at             │
   │  title, content (md)     │            │  UNIQUE(enrollment,lesson)│
   │  topics[]  ◀── the seam  │            └───────────────────────────┘
   │  est_minutes             │
   └──────────────────────────┘           ┌──────────────────────────┐
                                          │ certificates             │
   topics[] lives on the LEAF (lesson).   │  enrollment_id (UNIQUE)  │
   A module/course's topic set is the     │  serial (JNY-YYYY-NNNNNN)│
   DISTINCT union of its lessons' topics. │  issued_at, revoked_at   │
                                          └──────────────────────────┘
                                          (one cert per completed enrollment)
```

Why progress is denormalized onto `enrollments.progress`/`status`: listing "my
courses" never has to re-aggregate `lesson_progress`. It is **recomputed DB-side
on every mark-complete** — the single source of truth, same philosophy as quiz
scoring.

### 2.1 Table definitions (DDL)

Verbatim shape from `app/db/migrations/0007_phase4_courses.sql` (comments trimmed).
Every table carries the project convention: internal `id bigint … identity` PK +
external `public_id uuid default uuidv7()`, plus `created_at`/`updated_at` where it
makes sense (with the shared `set_updated_at()` trigger).

```sql
-- 0. NEW permission column on the existing users table
alter table users
  add column role text not null default 'learner'
    check (role in ('learner', 'admin'));

-- 1. courses — the catalog entry (authored once, shared by all learners)
create table courses (
  id           bigint generated always as identity primary key,
  public_id    uuid   not null default uuidv7() unique,
  slug         text   not null unique,
  title        text   not null,
  subtitle     text   not null default '',
  description  text   not null default '',
  level        text   not null default 'beginner'
                 check (level in ('beginner','intermediate','advanced')),
  category     text   not null default '',
  tags         text[] not null default '{}',
  emoji        text   not null default '📘',
  est_minutes  integer,
  source       text   not null default 'internal'
                 check (source in ('internal','import')),
  external_ref text,                                              -- org's id (imports)
  is_published boolean not null default false,
  created_by   bigint references users(id) on delete set null,   -- FK → users
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create unique index courses_source_ref_idx                       -- ETL idempotency
  on courses (source, external_ref) where external_ref is not null;
create index courses_published_idx on courses (is_published, created_at desc);

-- 2. course_modules — ordered sections of a course
create table course_modules (
  id         bigint generated always as identity primary key,
  public_id  uuid   not null default uuidv7() unique,
  course_id  bigint not null references courses(id) on delete cascade,   -- FK → courses
  position   integer not null,
  title      text   not null,
  summary    text   not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (course_id, position)                                   -- no two modules share a slot
);

-- 3. course_lessons — the leaf unit; topics[] is the study/quiz seam
create table course_lessons (
  id          bigint generated always as identity primary key,
  public_id   uuid   not null default uuidv7() unique,
  module_id   bigint not null references course_modules(id) on delete cascade, -- FK → modules
  position    integer not null,
  title       text   not null,
  content     text   not null default '',                        -- markdown body
  topics      text[] not null default '{}',                      -- ← feeds resolve_topics()
  est_minutes integer,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (module_id, position)
);

-- 4. enrollments — one learner ↔ one course (denormalized progress/status)
create table enrollments (
  id           bigint generated always as identity primary key,
  public_id    uuid   not null default uuidv7() unique,
  user_id      bigint not null references users(id)   on delete cascade,  -- FK → users
  course_id    bigint not null references courses(id) on delete cascade,  -- FK → courses
  status       text   not null default 'active' check (status in ('active','completed')),
  progress     smallint not null default 0 check (progress between 0 and 100),
  enrolled_at  timestamptz not null default now(),
  completed_at timestamptz,
  unique (user_id, course_id)                                    -- can't enrol twice
);

-- 5. lesson_progress — one row per lesson a learner has finished
create table lesson_progress (
  id            bigint generated always as identity primary key,
  enrollment_id bigint not null references enrollments(id)   on delete cascade, -- FK → enrollments
  lesson_id     bigint not null references course_lessons(id) on delete cascade,-- FK → lessons
  completed_at  timestamptz not null default now(),
  unique (enrollment_id, lesson_id)                             -- presence = done (idempotent)
);

-- 6. certificates — issued once per completed enrollment
create table certificates (
  id            bigint generated always as identity primary key,
  public_id     uuid   not null default uuidv7() unique,        -- shareable verify id
  enrollment_id bigint not null unique references enrollments(id) on delete cascade, -- FK, 1:1
  serial        text   not null unique,                         -- JNY-YYYY-NNNNNN
  issued_at     timestamptz not null default now(),
  revoked_at    timestamptz
);
```

### 2.2 Connections (foreign keys & cascade)

| Child table | Column | → References | On delete | Why |
|---|---|---|---|---|
| `courses` | `created_by` | `users(id)` | `set null` | keep the course if the authoring admin is removed |
| `course_modules` | `course_id` | `courses(id)` | `cascade` | a module belongs to one course |
| `course_lessons` | `module_id` | `course_modules(id)` | `cascade` | a lesson belongs to one module |
| `enrollments` | `user_id` | `users(id)` | `cascade` | drop enrolments when a user is deleted |
| `enrollments` | `course_id` | `courses(id)` | `cascade` | drop enrolments when a course is deleted |
| `lesson_progress` | `enrollment_id` | `enrollments(id)` | `cascade` | progress is meaningless without its enrolment |
| `lesson_progress` | `lesson_id` | `course_lessons(id)` | `cascade` | progress points at a real lesson |
| `certificates` | `enrollment_id` | `enrollments(id)` | `cascade` (`unique`) | exactly one certificate per enrolment |

Uniqueness that enforces the rules: `courses.slug`, `(courses.source, external_ref)`,
`(course_modules.course_id, position)`, `(course_lessons.module_id, position)`,
`(enrollments.user_id, course_id)`, `(lesson_progress.enrollment_id, lesson_id)`,
`certificates.enrollment_id`, `certificates.serial`.

Because FKs cascade, **deleting one row tidies the whole subtree** — no orphan rows:

```
delete course  ──► course_modules ──► course_lessons ─┐
                                                       ├─► lesson_progress
       └─► enrollments ──► lesson_progress             │   (also reachable via lesson)
                       └─► certificates                ┘
delete user    ──► enrollments ──► lesson_progress + certificates
```

### 2.3 Worked example (sample rows)

A learner **Aanya** takes a 2-lesson course "Python for Data Analysis". Internal
`id`s shown for clarity (real APIs only ever expose `public_id`).

**Authored once (admin / seed):**

```
users
 id │ public_id    │ email             │ role
 ───┼──────────────┼───────────────────┼────────
  1 │ 019f…0a01    │ admin@journey.app │ admin
  5 │ 019f…0a05    │ aanya@example.com │ learner

courses                         (created_by = 1, the admin)
 id │ slug             │ title                     │ is_published │ source   │ external_ref
 ───┼──────────────────┼───────────────────────────┼──────────────┼──────────┼──────────────
  7 │ python-for-data  │ Python for Data Analysis  │ true         │ internal │ NULL

course_modules                  (course_id = 7)
 id │ course_id │ position │ title
 ───┼───────────┼──────────┼───────────────────
 12 │ 7         │ 0        │ Python foundations

course_lessons                  (module_id = 12) — topics[] is the seam
 id │ module_id │ position │ title                  │ topics
 ───┼───────────┼──────────┼────────────────────────┼────────────────────────────
 30 │ 12        │ 0        │ Values, variables & …  │ {python basics, data types}
 31 │ 12        │ 1        │ Lists, dicts & …       │ {python collections}
```

**Step A — Aanya enrols** (`POST /courses/{public_id-of-7}/enroll`):

```
enrollments
 id │ user_id │ course_id │ status │ progress │ completed_at
 ───┼─────────┼───────────┼────────┼──────────┼──────────────
 40 │ 5       │ 7         │ active │ 0        │ NULL
```

**Step B — she finishes lesson 30** (`POST /courses/lessons/{public_id-of-30}/complete`).
A `lesson_progress` row is inserted, then progress is recomputed:

```
lesson_progress
 id │ enrollment_id │ lesson_id │ completed_at
 ───┼───────────────┼───────────┼──────────────
  1 │ 40            │ 30        │ 2026-06-29 …

recompute → total lessons in course 7 = 2, done = 1  ⇒  progress = round(1*100/2) = 50
enrollments(40): status=active, progress=50, completed_at=NULL     (not all done yet)
```

**Step C — she finishes lesson 31.** Second `lesson_progress` row; now done = total:

```
lesson_progress             (+1 row)
 id │ enrollment_id │ lesson_id
 ───┼───────────────┼───────────
  2 │ 40            │ 31

recompute → total = 2, done = 2  ⇒  progress = 100, completed = true
enrollments(40): status=completed, progress=100, completed_at=2026-06-29 …

certificates                (auto-issued, on conflict (enrollment_id) do nothing)
 id │ public_id │ enrollment_id │ serial          │ issued_at      │ revoked_at
 ───┼───────────┼───────────────┼─────────────────┼────────────────┼────────────
  1 │ 019f…ce01 │ 40            │ JNY-2026-000040 │ 2026-06-29 …   │ NULL
```

The serial embeds the `enrollment_id` (40 → `…-000040`); the public verify URL is
`/certificates/verify/019f…ce01` (the certificate's `public_id`).

**The exact SQL behind Step B/C** (`repository.mark_lesson_complete`) — insert is
idempotent, recompute is one query, completion + certificate are conditional:

```sql
insert into lesson_progress (enrollment_id, lesson_id) values (40, 30)
on conflict (enrollment_id, lesson_id) do nothing;          -- re-clicking is a no-op

select
  (select count(*) from course_lessons l
     join course_modules m on m.id = l.module_id
     where m.course_id = 7)                       as total,  -- = 2
  (select count(*) from lesson_progress
     where enrollment_id = 40)                     as done;   -- = 1, then 2

update enrollments set
  progress = 50,                                              -- round(done*100/total)
  status   = case when <done>=<total> then 'completed' else 'active' end,
  completed_at = case when <done>=<total> then coalesce(completed_at, now()) else null end
where id = 40;

-- only when complete:
insert into certificates (enrollment_id, serial)
values (40, 'JNY-' || to_char(now(),'YYYY') || '-' || lpad(40::text,6,'0'))
on conflict (enrollment_id) do nothing;
```

**Reading it back** — the course-detail tree with Aanya's completion overlay
(`repository.get_course_detail` joins the three content tables and tests each lesson
against *her* `lesson_progress` via her `enrollment_id`):

```sql
select l.public_id, l.title, l.topics,
       exists (select 1 from lesson_progress lp
               where lp.lesson_id = l.id and lp.enrollment_id = 40) as is_completed
from course_lessons l
join course_modules m on m.id = l.module_id
where m.course_id = 7
order by m.position, l.position;
-- → lesson 30 is_completed=true, lesson 31 is_completed=true
```

**The topic seam** — aggregating the syllabus for "Quiz me on this course"
(`repository.course_topics`) just unions the lessons' `topics[]`:

```sql
select distinct unnest(l.topics) as topic
from course_lessons l
join course_modules m on m.id = l.module_id
where m.course_id = 7;
-- → {python basics, data types, python collections}
--   these become resolve_topics(overrides=[...]) for the study/quiz generators
```

---

## 3. Learner flow: enroll → complete → certificate

```
  BROWSE                ENROLL                 PROGRESS                  COMPLETE
  ──────                ──────                 ────────                  ────────
  GET /courses          POST /courses/{id}     POST /courses/lessons/    (last lesson)
  GET /courses/             /enroll                {id}/complete             │
      recommended            │                      │                        ▼
       │                     ▼                       ▼                 all lessons done?
       ▼              enrollments row         insert lesson_progress    ┌──────┴──────┐
  catalog cards       (status=active,         (idempotent)              │ yes         │ no
  ranked by topic      progress=0)                  │                   ▼             ▼
  overlap with the          │                       ▼            status=completed   progress
  learner's profile   GET /courses/{id}       recompute:         completed_at=now()  = done/
  + preferences       → full syllabus tree     done / total      issue certificate   total %
                        + per-lesson           = progress %      (on conflict: skip)
                          is_completed                                  │
                                                                        ▼
                                               GET /certificates/verify/{public_id}
                                               → public, unauthenticated HTML page
                                                 (shareable / print-to-PDF)
```

Completion is deterministic: `progress = round(done * 100 / total)`,
`completed = (total > 0 and done >= total)`. The certificate is inserted
`on conflict (enrollment_id) do nothing`, so re-completing never mints duplicates.

---

## 4. The topic seam — how a course feeds study material & quizzes

This is the integration point with Phase 2 & 3. No engine internals changed; the
generate endpoints just gained an optional `course_id` (+ optional `module_id`).

```
  course_lessons.topics[]
   (e.g. ["caching", "load balancing", "sharding", ...])
            │
            │  GET /courses/{id}/topics   (DISTINCT union across lessons)
            ▼
   ┌─────────────────────────┐
   │ resolve_topics(         │   priority: overrides → preference topics
   │   overrides = topics,   │             → profile-derived interests
   │   preference_topics=…,  │
   │   profile=… )           │   course topics enter as `overrides` (highest)
   └────────────┬────────────┘
                ▼
     ┌──────────┴───────────┐
     ▼                      ▼
  POST /study-material   POST /assessments/quizzes
       /generate              /generate
  {course_id, module_id}  {course_id, module_id}
     │                      │
     ▼                      ▼
  curated feed grounded   MCQs grounded in the
  in the syllabus         course's topics
  ("Study this")          ("Quiz me on this")
```

So "Study this module" / "Quiz me on this course" are just the existing generate
calls with a `course_id` (and optionally `module_id`) attached.

---

## 5. Two surfaces: learner vs admin

```
  ┌─────────────────────────────── ROLE = learner ───────────────────────────────┐
  │ GET    /courses                  catalog (published only) [?category=]       │
  │ GET    /courses/recommended      topic-overlap ranked, excludes enrolled     │
  │ GET    /courses/me               my enrollments (+ progress + certificate)   │
  │ GET    /courses/{id}             full syllabus tree + my progress overlay    │
  │ GET    /courses/{id}/topics      aggregated lesson topics [?module=]         │
  │ POST   /courses/{id}/enroll      idempotent                                  │
  │ POST   /courses/lessons/{id}/complete   recompute progress, maybe issue cert │
  │ GET    /certificates/me          my certificates                             │
  │ GET    /certificates/verify/{id} PUBLIC html page (no auth)                  │
  └──────────────────────────────────────────────────────────────────────────────┘

  ┌──────────────── ROLE = admin (require_admin → 403 otherwise) ──────────────────┐
  │ GET    /admin/courses            all courses incl. unpublished + counts        │
  │ POST   /admin/courses            CREATE or REPLACE a course tree (== ETL path) │
  │ GET    /admin/courses/{id}       full tree, any publish state                  │
  │ POST   /admin/courses/{id}/publish?published=                                  │
  │ DELETE /admin/courses/{id}                                                     │
  │ GET    /admin/enrollments        oversight [?course=]                          │
  │ POST   /admin/certificates/{id}/revoke?revoked=                                │
  └────────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Authoring == the ETL contract (build-our-own-now, import-later)

The admin "create a course" payload and the future org-data import use **one and
the same path**. That's the whole strategy: hand-author now to lock the model,
transform org data into the same shape later.

```
  TODAY (internal)                          LATER (org import)
  ───────────────                           ──────────────────
  admin / seed script                       ETL job (org DB / files / API)
        │                                          │  transform → CourseUpsertIn
        ▼                                          ▼  (source="import",
  CourseUpsertIn  ───────────┐      ┌───────────  external_ref=<org course id>)
  { slug, title, ...,        │      │
    modules:[ {title,        ▼      ▼
      lessons:[ {title,   repository.upsert_course()
        content, topics[] } ] } ] }      │
                                         │  match key:
                                         │   import → (source, external_ref)
                                         │   else   → slug
                                         ▼
                              create OR replace course + rebuild module/lesson tree
                              (idempotent; re-runnable)
```

`CourseUpsertIn` is nested — modules and lessons in one payload, `position`
derived from list order. Recommendations can already run against this catalog
today (topic/tag overlap with the learner's profile) — no org data required.

> Caveat noted in code: re-`upsert`-ing a course rebuilds its module tree, which
> cascade-deletes `lesson_progress`. Fine while courses are authored before
> learners join; revisit before editing live, enrolled courses.

---

## 7. Module layout

```
  backend/app/modules/courses/
    schemas.py         CourseUpsertIn / Lesson / Module (authoring + ETL contract)
                       CourseSummary / CourseDetail / EnrollmentOut / CertificateOut
    repository.py      raw SQL: catalog, recommend, detail tree, enroll,
                       mark_lesson_complete (recompute + issue cert), course_topics,
                       admin upsert/list/publish/delete, certificate lookup/revoke
    router.py          learner routes (/courses) + certificates_router
                       (/certificates, incl. the public HTML verify page)
    admin_router.py    /admin/* — gated by require_admin at the router level

  touched elsewhere:
    db/migrations/0007_phase4_courses.sql     schema + users.role
    db/seed_phase4.py                          admin user + our own courses
    modules/auth/deps.py                       require_admin
    modules/auth/repository.py                 role added to _PUBLIC_COLS
    modules/study_material/router.py           course_id → topic overrides
    modules/assessments/router.py              course_id → topic overrides
    main.py                                    include courses/cert/admin routers
```
