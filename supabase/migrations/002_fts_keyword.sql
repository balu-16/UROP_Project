-- 002: keyword search support for hybrid retrieval (RRF).
-- Adds full-text search over chunks.content plus a session-scoped RPC used by
-- PostgresKeywordRetriever. Supabase ships tsvector + pg_trgm natively.
-- All statements are idempotent; safe to run in the Supabase SQL editor.

-- GIN index for English full-text search over chunk content.
create index if not exists chunks_content_fts_idx
  on chunks using gin (to_tsvector('english', content));

-- Expression index for the session-isolation predicate
-- (chunks.metadata->>'session_id' = :sid). chunks has no session_id column;
-- ingestion always writes session_id into chunks.metadata (and
-- documents.metadata), verified in app/services/ingestion.py.
create index if not exists chunks_session_metadata_idx
  on chunks ((metadata->>'session_id'));

-- Session- + user-scoped keyword search. Returns chunk ULIDs so the caller can
-- merge with vector hits by chunk_id. Never searches across sessions.
create or replace function match_chunks_fts(
  p_query text,
  p_session_id text,
  p_user_id text,
  p_limit int
)
returns table (
  chunk_id text,
  document_id uuid,
  content text,
  metadata jsonb,
  rank real
)
language sql
stable
as $$
  select
    c.chunk_id,
    c.document_id,
    c.content,
    c.metadata,
    ts_rank(
      to_tsvector('english', c.content),
      websearch_to_tsquery('english', p_query)
    ) as rank
  from chunks c
  join documents d on d.id = c.document_id
  where c.metadata->>'session_id' = p_session_id
    and d.user_id = p_user_id
    and to_tsvector('english', c.content)
        @@ websearch_to_tsquery('english', p_query)
  order by rank desc
  limit p_limit;
$$;
