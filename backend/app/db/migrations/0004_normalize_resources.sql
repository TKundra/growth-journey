-- Phase 2 — normalize study material to kill cross-user duplication.
--
-- 0003 stored one `study_resources` row PER USER (unique (user_id, url)), so a
-- popular URL was duplicated across every user who had it curated — and, worse,
-- `resource_chunks` hung off that per-user row, so the same URL was re-embedded
-- and its 768-dim vectors re-stored once per user. Embeddings are the expensive
-- part, so that was the costliest duplication.
--
-- This migration splits the table in two:
--   * `resources`  — canonical, URL-unique, shared across all users. The
--                    URL-intrinsic fields (title, summary, tags, …) live here,
--                    and `resource_chunks` now hangs off it → each URL is
--                    embedded EXACTLY ONCE and reused by everyone.
--   * `feed_items` — the per-user feed: which user saw a resource, the topic it
--                    served them, and its rank for them.
-- `saved_resources` and `resource_chunks` are repointed at the canonical id.
-- Existing data is preserved (deduped by URL).

-- ── canonical resources (URL-unique, global) ─────────────────────────────────
create table resources (
  id            bigint generated always as identity primary key,
  public_id     uuid not null default uuidv7() unique,
  url           text not null unique,
  title         text not null,
  source_domain text,
  summary       text,
  tags          text[] not null default '{}',
  difficulty    text check (difficulty in ('beginner', 'intermediate', 'advanced')),
  kind          text,
  est_minutes   integer,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create trigger resources_set_updated_at
  before update on resources for each row execute function set_updated_at();

-- ── per-user feed entries ────────────────────────────────────────────────────
create table feed_items (
  id          bigint generated always as identity primary key,
  public_id   uuid not null default uuidv7() unique,
  user_id     bigint not null references users(id) on delete cascade,
  resource_id bigint not null references resources(id) on delete cascade,
  topic       text,                                          -- which of THIS user's topics it serves
  relevance   integer check (relevance between 0 and 100),   -- LLM rank for THIS user
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (user_id, resource_id)
);

create index feed_items_user_idx on feed_items (user_id, created_at desc);

create trigger feed_items_set_updated_at
  before update on feed_items for each row execute function set_updated_at();

-- ── backfill: one canonical resource per URL ─────────────────────────────────
-- Pick a representative row per URL (best relevance, then newest) for the shared
-- metadata. created_at carries over so the canonical row keeps its first-seen feel.
insert into resources (url, title, source_domain, summary, tags, difficulty, kind, est_minutes, created_at)
select distinct on (url)
       url, title, source_domain, summary, tags, difficulty, kind, est_minutes, created_at
from study_resources
order by url, relevance desc nulls last, created_at desc;

-- ── backfill: every old per-user row becomes a feed_item ─────────────────────
insert into feed_items (user_id, resource_id, topic, relevance, created_at)
select sr.user_id, r.id, sr.topic, sr.relevance, sr.created_at
from study_resources sr
join resources r on r.url = sr.url
on conflict (user_id, resource_id) do nothing;  -- a user had at most one row per url anyway

-- ── repoint saved_resources at the canonical resource ────────────────────────
alter table saved_resources drop constraint saved_resources_resource_id_fkey;
update saved_resources s
set resource_id = r.id
from study_resources sr
join resources r on r.url = sr.url
where s.resource_id = sr.id;
alter table saved_resources
  add constraint saved_resources_resource_id_fkey
  foreign key (resource_id) references resources(id) on delete cascade;

-- ── repoint resource_chunks at the canonical resource ────────────────────────
-- Two old (per-user) resources can share a URL and each carry chunks; after
-- remapping they'd collide on (resource_id, chunk_index). Keep one chunk set per
-- URL (the lowest-id resource that ACTUALLY has chunks) and drop the equivalent rest.
delete from resource_chunks c
using study_resources sr
where c.resource_id = sr.id
  and exists (
    select 1 from study_resources sr2
    join resource_chunks c2 on c2.resource_id = sr2.id
    where sr2.url = sr.url and sr2.id < sr.id
  );

alter table resource_chunks drop constraint resource_chunks_resource_id_fkey;
update resource_chunks c
set resource_id = r.id
from study_resources sr
join resources r on r.url = sr.url
where c.resource_id = sr.id;
alter table resource_chunks
  add constraint resource_chunks_resource_id_fkey
  foreign key (resource_id) references resources(id) on delete cascade;

-- ── drop the old per-user table (its index + trigger go with it) ─────────────
drop table study_resources;
