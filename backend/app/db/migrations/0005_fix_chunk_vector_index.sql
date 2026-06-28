-- Fix: semantic library search returned zero results for relevant queries.
--
-- The original index on resource_chunks.embedding was IVFFlat with lists=100.
-- IVFFlat partitions vectors into `lists` cells and, by default, probes only ONE
-- cell per query (ivfflat.probes = 1). With our small corpus the saved vectors
-- scatter across cells, so an ORDER BY <=> ... LIMIT (which uses the index)
-- typically visits a cell holding none of the relevant rows and returns 0 hits —
-- e.g. searching "load balancing" missed the resource literally titled
-- "...Load Balancing...". A plain seq-scan returned all rows, proving the data
-- was fine and the index was the culprit.
--
-- HNSW gives near-exact recall at any corpus size with no per-query knob to tune
-- (no probes), so it behaves correctly from the first saved row onward and still
-- scales. Cosine ops match the <=> operator used in search_saved_chunks.
drop index if exists resource_chunks_embedding_idx;

create index resource_chunks_embedding_idx
  on resource_chunks using hnsw (embedding vector_cosine_ops);
