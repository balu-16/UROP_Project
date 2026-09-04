-- 003: badge hydration for assistant messages.
-- The chat service persists the full `retrieval` object
-- ({depth, confidence, strategy, retrieval_mode, candidate_count,
-- reranked_count, reranker_model}) on assistant rows; 001 only created
-- retrieval_diagnostics. Idempotent; safe to run in the Supabase SQL editor.
alter table if exists messages
  add column if not exists retrieval jsonb;
