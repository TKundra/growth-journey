-- Phase 4 — Courses & certifications.
--
-- Our own course catalog so the platform has a first-class course model now;
-- org-provided courses are folded in later by an ETL pipeline that writes the
-- SAME tables (see `source`/`external_ref` below) — the admin authoring API and
-- the import path share one contract.
--
-- Shape is three levels: courses → course_modules → course_lessons. Topics live
-- on the LESSON (finest grain); a module/course's topic set is the aggregate.
-- Those topics are the seam into Phase 2/3: they feed query_builder.resolve_topics
-- as overrides so "study this" / "quiz me on this" ground in the syllabus.
--
-- A learner `enrolls`, marks lessons complete (`lesson_progress`), and when every
-- lesson is done the enrollment flips to 'completed' and a `certificate` is issued.
-- Completion is deterministic and DB-side, like quiz scoring.

-- ── users.role ────────────────────────────────────────────────────────────────
-- First permission concept in the system. 'learner' is everyone; 'admin' may
-- author the catalog (and, later, run imports). Distinct from user_type, which is
-- a profile discriminator, not a permission.
alter table users
  add column role text not null default 'learner'
    check (role in ('learner', 'admin'));

-- ── courses ─────────────────────────────────────────────────────────────────
-- Catalog entry. `source`+`external_ref` make imports traceable and idempotent:
-- internal courses are hand-authored (source='internal', external_ref null); an
-- ETL job upserts org courses on (source, external_ref). Only `is_published`
-- courses are visible to learners.
create table courses (
  id           bigint generated always as identity primary key,
  public_id    uuid not null default uuidv7() unique,
  slug         text not null unique,                 -- url-friendly handle
  title        text not null,
  subtitle     text not null default '',
  description  text not null default '',
  level        text not null default 'beginner'
                 check (level in ('beginner', 'intermediate', 'advanced')),
  category     text not null default '',             -- e.g. "Data", "Web", "Aptitude"
  tags         text[] not null default '{}',         -- coarse discovery/recommendation signal
  emoji        text not null default '📘',            -- lightweight card art (no asset pipeline)
  est_minutes  integer,                              -- nullable; rolled up from lessons when known
  source       text not null default 'internal'
                 check (source in ('internal', 'import')),
  external_ref text,                                 -- org's course id, for import idempotency
  is_published boolean not null default false,
  created_by   bigint references users(id) on delete set null,  -- null for imported courses
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
-- one row per imported course; internal courses (external_ref null) are unconstrained here
create unique index courses_source_ref_idx
  on courses (source, external_ref) where external_ref is not null;
create index courses_published_idx on courses (is_published, created_at desc);

create trigger courses_set_updated_at
  before update on courses for each row execute function set_updated_at();

-- ── course_modules ──────────────────────────────────────────────────────────
-- Ordered sections within a course. `position` fixes display order.
create table course_modules (
  id         bigint generated always as identity primary key,
  public_id  uuid not null default uuidv7() unique,
  course_id  bigint not null references courses(id) on delete cascade,
  position   integer not null,
  title      text not null,
  summary    text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (course_id, position)
);
create index course_modules_course_idx on course_modules (course_id, position);

create trigger course_modules_set_updated_at
  before update on course_modules for each row execute function set_updated_at();

-- ── course_lessons ──────────────────────────────────────────────────────────
-- The leaf unit: what a learner reads and marks complete. `topics` is the link
-- into study material + quiz generation (aggregated up to module/course).
create table course_lessons (
  id          bigint generated always as identity primary key,
  public_id   uuid not null default uuidv7() unique,
  module_id   bigint not null references course_modules(id) on delete cascade,
  position    integer not null,
  title       text not null,
  content     text not null default '',              -- markdown lesson body
  topics      text[] not null default '{}',          -- feeds resolve_topics(overrides=...)
  est_minutes integer,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (module_id, position)
);
create index course_lessons_module_idx on course_lessons (module_id, position);

create trigger course_lessons_set_updated_at
  before update on course_lessons for each row execute function set_updated_at();

-- ── enrollments ─────────────────────────────────────────────────────────────
-- One learner ↔ one course. `progress` (0–100) and `status` are denormalized so
-- listing "my courses" never has to re-aggregate lesson_progress. Recomputed on
-- every mark-complete; flips to 'completed' (and issues a certificate) at 100%.
create table enrollments (
  id           bigint generated always as identity primary key,
  public_id    uuid not null default uuidv7() unique,
  user_id      bigint not null references users(id) on delete cascade,
  course_id    bigint not null references courses(id) on delete cascade,
  status       text not null default 'active'
                 check (status in ('active', 'completed')),
  progress     smallint not null default 0
                 check (progress between 0 and 100),
  enrolled_at  timestamptz not null default now(),
  completed_at timestamptz,
  unique (user_id, course_id)
);
create index enrollments_user_idx on enrollments (user_id, enrolled_at desc);

-- ── lesson_progress ─────────────────────────────────────────────────────────
-- A completed lesson for one enrollment. Presence = done (manual mark-complete).
create table lesson_progress (
  id           bigint generated always as identity primary key,
  enrollment_id bigint not null references enrollments(id) on delete cascade,
  lesson_id    bigint not null references course_lessons(id) on delete cascade,
  completed_at timestamptz not null default now(),
  unique (enrollment_id, lesson_id)
);

-- ── certificates ────────────────────────────────────────────────────────────
-- Issued once per enrollment on completion. `public_id` is the shareable id in
-- the public verify URL (/certificates/verify/{public_id}); `serial` is the
-- human-facing certificate number. `revoked_at` supports admin revocation.
create table certificates (
  id            bigint generated always as identity primary key,
  public_id     uuid not null default uuidv7() unique,
  enrollment_id bigint not null unique references enrollments(id) on delete cascade,
  serial        text not null unique,
  issued_at     timestamptz not null default now(),
  revoked_at    timestamptz
);
