-- Phase 2 — AI study material engine.
--
-- The journey: profile + preferences → search queries → web search → LLM
-- curation (dedupe, rank, summarize, tag, cite) → a per-user feed of
-- `study_resources`. Users promote items into their library (`saved_resources`).
-- Saved items can be chunked + embedded into `resource_chunks` for RAG (pgvector),
-- which Phase 3 (assessments) and a future "chat with your material" will retrieve.
--
-- Follows the ID convention from 0001 (internal bigint id + external uuidv7 public_id)
-- and reuses set_updated_at() defined in 0002.

-- pgvector — the compose image ships it; enable so resource_chunks can store embeddings.
create extension if not exists vector;

-- ── study_resources ──────────────────────────────────────────────────────────
-- One row per curated resource, owned by the user it was generated for. The feed
-- is append-only across regenerations; (user_id, url) is unique so re-running the
-- generator dedupes against what the user already has instead of piling up copies.
create table study_resources (
  id               bigint generated always as identity primary key,
  public_id        uuid not null default uuidv7() unique,
  user_id          bigint not null references users(id) on delete cascade,
  title            text not null,
  url              text not null,
  source_domain    text,                                   -- e.g. "developer.mozilla.org"
  summary          text,                                   -- LLM 1-2 sentence why-it-matters
  topic            text,                                   -- which preference topic it serves
  tags             text[] not null default '{}',
  difficulty       text check (difficulty in ('beginner', 'intermediate', 'advanced')),
  kind             text,                                   -- article | docs | video | course | tutorial | other
  est_minutes      integer,                                -- estimated read/watch time
  relevance        integer check (relevance between 0 and 100),  -- LLM rank score
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  unique (user_id, url)
);

create index study_resources_user_idx on study_resources (user_id, created_at desc);

create trigger study_resources_set_updated_at
  before update on study_resources for each row execute function set_updated_at();

-- ── saved_resources ──────────────────────────────────────────────────────────
-- The user's library: a promotion of a feed item. Kept as a join so the feed and
-- the library stay distinct concepts; cascade keeps it consistent if a resource goes.
create table saved_resources (
  id          bigint generated always as identity primary key,
  public_id   uuid not null default uuidv7() unique,
  user_id     bigint not null references users(id) on delete cascade,
  resource_id bigint not null references study_resources(id) on delete cascade,
  note        text,
  created_at  timestamptz not null default now(),
  unique (user_id, resource_id)
);

create index saved_resources_user_idx on saved_resources (user_id, created_at desc);

-- ── resource_chunks ──────────────────────────────────────────────────────────
-- RAG index for saved material. Populated lazily when a resource is saved (only
-- if an embedding model is configured); retrieval is cosine similarity over the
-- embedding. Dimension 768 matches the default embed model (nomic-embed-text).
create table resource_chunks (
  id          bigint generated always as identity primary key,
  public_id   uuid not null default uuidv7() unique,
  resource_id bigint not null references study_resources(id) on delete cascade,
  chunk_index integer not null,
  content     text not null,
  embedding   vector(768),
  created_at  timestamptz not null default now(),
  unique (resource_id, chunk_index)
);

-- IVFFlat needs ANALYZE + data to be effective; for v1 volumes a plain cosine scan
-- is fine, but the index is here so retrieval scales without a schema change.
create index resource_chunks_embedding_idx
  on resource_chunks using ivfflat (embedding vector_cosine_ops) with (lists = 100);
