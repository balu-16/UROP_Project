# RAGnostic Implementation Plan — Hybrid Retrieval + Rerank + Un-upload

Reranker locked: `cross-encoder/ms-marco-MiniLM-L-6-v2`. No threshold calibration.
No redesign. Backend Python/FastAPI under `server/`; frontend delta in `client/`.
Background + verdicts: see `thinking.md`. Status: Stages 0–4 implemented (see
corrections below); Stage 5 verification pending.

## Stage 0 — Pin behavior, add config + schema (no behavior change)

1. `server/app/config/settings.py`: add `vector_top_k=50`, `keyword_top_k=50`,
   `rrf_k=60`, `reranker_enabled=True`, `reranker_model=L6 id`,
   `rerank_candidate_cap=100`, `rerank_top_k=5` (defaults per spec; extra=ignore
   keeps old `.env` files working). NOTE: `rerank_top_k=5 < top_k=6` by design.
2. `supabase/migrations/002_fts_keyword.sql`: GIN index on
   `to_tsvector('english', content)`, expression index on
   `(metadata->>'session_id')`, `match_chunks_fts(p_query, p_session_id,
   p_user_id, p_limit)` RPC (websearch_to_tsquery + ts_rank, session predicate,
   join documents for user check). Indexes `IF NOT EXISTS`; function
   `CREATE OR REPLACE`. Apply to live Supabase via SQL editor.
3. Regression test `test_confidence_gate.py`: pins gate on cosine (`0.8` →
   0-hop; `0.5` → 1-hop → 2-hop; empty → 0.0). Fused `vector_score + rrf_score`
   shapes covered in `test_hybrid_retrieval.py`. Must pass BEFORE and AFTER.
4. `server/.env.example` + READMEs document new vars.
5. Run: `python tests/run_all.py` from `server/` → green.

## Stage 1 — Keyword + RRF + gate-preserving integration

1. `server/app/retrieval/keyword.py`: `KeywordRetriever` ABC
   (`search(query, user_id, session_id, top_k) -> [{chunk_id, document_id, text,
   metadata, keyword_score}]`); `PostgresKeywordRetriever` (supa.rpc, client
   None → `[]` + warn); `FakeKeywordRetriever` (tests).
2. `server/app/retrieval/fusion.py`: `reciprocal_rank_fusion(vector, keyword,
   k)` → dedup by chunk_id, `retrieval_sources`, preserves `vector_score`,
   sets `score=rrf_score`. Pure function, no I/O.
3. `server/app/retrieval/confidence.py`: read `vector_score ?? score` (1 line,
   backward compatible).
4. `server/app/retrieval/adaptive.py`: embed → vector search (`vector_top_k`)
   + keyword search (`keyword_top_k`, session-scoped via SQL predicate mirroring
   the vector allow-list guarantee) → fuse →
   gate on vector confidence (unchanged policy) → seeds = top-`top_k` fused ids
   → existing hop branches (unchanged) → `diagnostics` gains
   semantic/keyword/fused/expanded/merged counts (no `keyword_results` list;
   `semantic_results` retained).
5. `server/app/main.py` lifespan: build retriever (extract supa client
   try/except, as ingestion does), pass as optional kwarg (sole construction
   site — backward compatible).
6. Tests: fusion unit (ranks, dedup, provenance, empty-either-side,
   both-empty); gate regression (Stage 0, still green); ordering test with
   recording fakes (fusion before policy before expansion); memory-DB safe.
   PG-gated integration test for RPC (skipped without PG).
7. Run full suite → green.

## Stage 2 — Reranker after hops + metadata + telemetry

1. `server/app/retrieval/reranking.py`: `Reranker` ABC
   (`rerank(query, candidates) -> scored+sorted`); `CrossEncoderReranker`
   (lazy load, `asyncio.to_thread` predict, raw logits, sorted desc);
   `NullReranker` (NEW — passthrough + reason); `build_reranker(settings)`:
   Null when disabled/`DISABLE_LOCAL_MODELS`/load-failure (warn, never raise).
2. `adaptive.py`: per hop-branch, before `context_builder.build`: final set =
   order-preserving dedup(fused + graph) → cap `RERANK_CANDIDATE_CAP` →
   rerank (try/except → fallback to pre-rerank order, logged) → slice
   `RERANK_TOP_K` → build (`preserve_order=True` when reranker did not run,
   so RRF order survives the 0.55 graph default). Reranked items: `score` =
   logit + `rerank_score` preserved. `diagnostics` unified keys
   (semantic/keyword/fused/expanded/merged/graph_nodes/confidence/depth/
   strategy + rerank counts/model/latency).
   `retrieval` += `retrieval_mode: "hybrid"` + `candidate_count/reranked_count/
   reranker_model/initial_confidence` (strategy enum untouched).
3. `services/chat.py` metadata dict: add the 5 additive keys
   (`initial_confidence, retrieval_mode, candidate_count, reranked_count,
   reranker_model`; diagnostics merge already carries telemetry to
   `retrieval_logs` — no other change). Assistant message persists full
   `retrieval` for history badge.
4. Frontend badge: render `retrieval_mode` + `candidate→top` counts + short
   model name alongside depth/confidence/strategy (no score/logit display).
5. Tests: sort/top-K/dupes, failure fallback, cap respected, ordering
   (rerank never precedes expansion — assert via call recorder),
   NullReranker paths. Suite green.

## Stage 3 — Document delete (backend)

1. `server/app/api/ingestion.py`: `DELETE /documents/{id}` +
   `DELETE /api/documents/{id}` + `GET /documents?session_id=` +
   `GET /api/documents?session_id=` (dual-router convention; list is
   session-scoped + ownership-checked, server truth for the strip).
2. `IngestionService.delete_document(user_id, session_id, ulid)`:
   indexed row lookup (404 → clear not-found) → resolve PG chunks via
   `metadata.pg_document_id` (legacy rows without link: vectors unaddressable,
   indexed row still removed, zeros reported — documented limitation) →
   Chroma `delete(chunk_ids=[ULIDs])` (best-effort) → delete PG documents row
   (SQL cascades chunks/chunk_entities; explicit deletes cover memory DB) →
   closure orphan-entity prune (shared entities survive; incident edges of
   pruned entities removed) → delete indexed row last.
   Response `{ok, deleted:{...}}`; repeat → 404.
3. Tests (memory DB + fake vector/graph stores): full cleanup, Chroma IDs
   correct, shared entity survives, 404, idempotent repeat, cross-session
   forbidden. Suite green.

## Stage 4 — Frontend un-upload delta

1. `client/src/lib/api.ts`: types `UploadedDocument {_id, filename?, metadata?.source}`
   + `SessionDocument`; `listDocuments(sessionId)` (`GET /documents?session_id=`);
   `deleteDocument(documentId, sessionId)` (single bare path; backend serves both
   prefixes).
2. Attachment state gains `documentId?`; upload response zipped by index
   (by-`_id`, not by filename — duplicate names safe; per-name queue fallback).
   Strip hydrates from `GET /documents` on session change; localStorage stays as
   offline cache.
3. Ingested-chip × → `confirm()` → status `deleting` → DELETE → remove chip +
   session strip entry; failure → restore + error toast. Pending × stays local,
   no API call. Strip entries deletable where `documentId` known.
4. `npm run build` clean; manual E2E per plan §5 of thinking record.

## Stage 5 — Verify

`python tests/run_all.py` from `server/` → green; `tsc` + client build → green;
live (Vercel frontend + container backend):
health → preflight → signup/login/refresh cookie → SSE chat shows
`retrieval_mode` → upload → strip hydration → un-upload → delete persistence →
keyword query returns exact chunk → latency sane in `diagnostics`.

## Out of scope (paused)

Threshold calibration/values, bandits/RL, Neo4j/NetworkX, custom reranker
training, terminal-1-hop quirk (preserved as-is), backfilling old "New chat"
titles.
