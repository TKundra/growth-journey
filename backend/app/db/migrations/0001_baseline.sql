-- Baseline migration: ID convention helper.
--
-- SCHEMA CONVENTION (every domain table follows this):
--   id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY  -- internal int, FKs/joins
--   public_id uuid   NOT NULL DEFAULT uuidv7() UNIQUE          -- external id used in URLs/APIs
--   created_at / updated_at timestamptz
--
-- Internal integer ids keep joins/indexes compact; the UUIDv7 public_id is what
-- leaves the system (APIs, URLs) and is time-ordered so it indexes well too.
--
-- Table template (copy for Phase 1+ tables):
--   create table example (
--     id         bigint generated always as identity primary key,
--     public_id  uuid not null default uuidv7() unique,
--     -- ... domain columns ...
--     created_at timestamptz not null default now(),
--     updated_at timestamptz not null default now()
--   );

-- UUIDv7 generator (time-ordered UUIDs). PG16 has no built-in uuidv7(), so we
-- define one. gen_random_uuid() is in core since PG13.
create or replace function uuidv7() returns uuid as $$
  select encode(
    set_bit(
      set_bit(
        overlay(
          uuid_send(gen_random_uuid())
          placing substring(int8send(floor(extract(epoch from clock_timestamp()) * 1000)::bigint) from 3)
          from 1 for 6
        ),
        52, 1
      ),
      53, 1
    ),
    'hex'
  )::uuid;
$$ language sql volatile;
