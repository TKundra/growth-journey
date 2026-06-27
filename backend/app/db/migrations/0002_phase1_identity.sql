-- Phase 1 — Identity & profiling.
--
-- Tables: users, profiles_professional, profiles_student, preferences.
-- Follows the ID convention from 0001 (internal bigint id + external uuidv7 public_id).
-- Each user has AT MOST ONE profile row, matching users.user_type, plus one
-- preferences row. Profiles are split by type (the columns differ per branch).

-- Reusable trigger: keep updated_at fresh on every UPDATE (set once, attach below).
create or replace function set_updated_at() returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

-- ── users ───────────────────────────────────────────────────────────────────
create table users (
  id                       bigint generated always as identity primary key,
  public_id                uuid not null default uuidv7() unique,
  email                    text not null unique,                 -- stored lowercased by the app
  password_hash            text not null,
  full_name                text,
  user_type                text check (user_type in ('professional', 'student')),  -- null until onboarding
  is_email_verified        boolean not null default false,
  email_verification_token uuid,                                 -- cleared once verified
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

create trigger users_set_updated_at
  before update on users for each row execute function set_updated_at();

-- ── profiles_professional ───────────────────────────────────────────────────
create table profiles_professional (
  id               bigint generated always as identity primary key,
  public_id        uuid not null default uuidv7() unique,
  user_id          bigint not null unique references users(id) on delete cascade,
  experience_years integer,
  job_role         text,            -- "role" is a reserved SQL word; exposed as `role` in the API
  industry         text,
  skills           text[] not null default '{}',
  goal             text,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

create trigger profiles_professional_set_updated_at
  before update on profiles_professional for each row execute function set_updated_at();

-- ── profiles_student ────────────────────────────────────────────────────────
create table profiles_student (
  id                 bigint generated always as identity primary key,
  public_id          uuid not null default uuidv7() unique,
  user_id            bigint not null unique references users(id) on delete cascade,
  education_level    text,            -- e.g. high_school, undergraduate, postgraduate
  stream             text,            -- e.g. science, commerce, arts
  subjects           text[] not null default '{}',
  target_exams       text[] not null default '{}',
  preferred_colleges text[] not null default '{}',
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);

create trigger profiles_student_set_updated_at
  before update on profiles_student for each row execute function set_updated_at();

-- ── preferences ─────────────────────────────────────────────────────────────
create table preferences (
  id                    bigint generated always as identity primary key,
  public_id             uuid not null default uuidv7() unique,
  user_id               bigint not null unique references users(id) on delete cascade,
  topics                text[] not null default '{}',
  goal                  text,
  cadence               text not null default 'none'
                          check (cadence in ('none', 'daily', 'weekly')),
  difficulty            text check (difficulty in ('beginner', 'intermediate', 'advanced')),
  notifications_enabled boolean not null default true,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);

create trigger preferences_set_updated_at
  before update on preferences for each row execute function set_updated_at();
