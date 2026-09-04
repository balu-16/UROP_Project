# RAGnostic Retrieval Upgrade — Thinking & Design Record

Scope: hybrid vector+keyword retrieval (RRF), cross-encoder reranking (after hops),
document delete + frontend un-upload. No threshold calibration, no architecture redesign.
Reranker locked: `cross-encoder/ms-marco-MiniLM-L-6-v2`. All facts verified against the repo.

## 1. How retrieval works today (as-built)

```
query → embeddings.embed_query → Chroma search(top_k=6, session-scoped)
  → confidence = max cosine → policy (≥0.75 → 0-hop else expand)
  → 1-hop: graph.expand_chunks(seeds, hops=1) → resolve → merge → re-evaluate
  → 2-hop: same with hops=2 → context_builder.build(merged)
  → chat.py streams SSE: metadata (retrieval{depth,confidence,strategy}) → tokens → done
```

Key files: `server/app/retrieval/adaptive.py` (orchestrator, sole `AdaptiveRetrievalService(`
construction site is `main.py:99`), `policy.py` (pure thresholds), `confidence.py`
(max-score gate), `services/context.py` (sorts by `score`, token-budget 3500),
`services/chat.py:207-242` (SSE metadata envelope + `retrieval_logs` insert).

## 2. Verified quirks you must not "fix" in passing

* **Terminal 1-hop is unreachable with defaults.** Entering expansion requires
  `initial_conf < 0.75`; post-expansion confidence is `max(<0.75 seeds, 0.55 graph
  default)`, so `decide_after_one_hop` always falls to TWO_HOP (max_hops=2).
  Preserve this traversal exactly — tests pin `0→1→2`, not terminal depths.
* **Three score scales coexist, never mix them:** cosine [0,1] (gate),
  graph default 0.55 (legacy display), RRF ~0–0.03 (ordering only),
  rerank logits (raw, possibly negative; sort-only). The 0.75 gate must only
  ever see cosine.
* **Session isolation is allow-list based** (`_session_chunk_ids`, Chroma
  metadata, cap 100k IDs). PG `chunks` has no `session_id` column, but
  `chunks.metadata` **does** carry `session_id` (ingestion.py:124) — use it.
* **DB layer is Mongo-like** (`AppDatabase`: find/insert/update/delete, no raw
  SQL). PG full-text goes through `supa.rpc()` (same pattern ingestion uses
  `supa.table()`), so FTS needs a **stored function in migration 002**.
  `MEMORY://` test DB cannot run SQL → keyword/rerank tests use fakes.
* **Strict boot fails on embeddings/LLM, never on the reranker.** Lifespan must
  degrade to NullReranker with a warning, or offline/test boots break.
* **Existing suite** (`run_all.py`: memory DB, MOCK_LLM, DISABLE_LOCAL_MODELS)
  asserts SSE event presence and shapes, not exact dicts → additive keys are safe.

## 3. Investigation verdicts (evidence-backed)

* **Arctic-v2-s rejected.** The whole Arctic Embed 2.0 family are bi-encoders
  (SentenceTransformer/CLS); `CrossEncoder()` requires a sequence-classification
  head and raises. **L6 it is:** 22.7M params, ~90 MB download, NDCG 74.30
  (== L12's 74.31, i.e. free), ~2× L12's speed. CPU estimate on c7i-flex:
  ~50–150 pairs/s → 100 capped candidates ≈ 1–2 s worst case.
* **MiniLM returns raw logits** — sorting key only, never display as %.
* **Delete linkage:** `indexed_documents.metadata.pg_document_id` exists only
  when the PG insert succeeded (conditional write). Delete prefers it, falls
  back to `(session_id, filename)` match with a warning. Cascades
  `documents→chunks→chunk_entities` are free in SQL; entities/relationships need
  explicit `NOT EXISTS` prune; Chroma vectors delete by ULID `where` clause.
* **Telemetry is free:** `retrieval_logs.diagnostics` (jsonb) auto-merges
  whatever `adaptive.retrieve()` puts in `diagnostics` (chat.py:234) — no schema
  change, no migration for metrics.

## 4. Design decisions (locked)

1. **Gate reads `vector_score ?? score`** (1-line `confidence.py` change,
   backward compatible). Fusion preserves each candidate's cosine in
   `vector_score`; fused ordering lives in `rrf_score` + list order.
2. **Fused item contract:** `{chunk_id, document_id, text, metadata,
   vector_score?, keyword_score?, rrf_score, retrieval_sources: [vector|keyword|both],
   score=rrf_score}`. `score` remains the "current ordering key" so
   `ContextBuilder` (sorts by `score`) needs no changes in any path.
3. **Expansion seeds = top-`top_k` fused chunk_ids.** Preserves today's
   expansion breadth; keyword influence enters via RRF order + final pool.
4. **Final set = order-preserving dedup(fused seeds… + graph chunks…)**,
   then cap to `RERANK_CANDIDATE_CAP`, rerank, slice `RERANK_TOP_K` → build.
   Reranked items get `score = rerank logit` (+`rerank_score` preserved).
5. **NullReranker** (new, not existing) when `DISABLE_LOCAL_MODELS`,
   `RERANKER_ENABLED=false`, load failure, or per-request exception —
   passthrough + reason logged, request continues.
6. **Keyword via `match_chunks_fts` RPC** (websearch_to_tsquery + ts_rank,
   GIN index, metadata session predicate, join documents for user check).
   `supa` client extracted in lifespan with try/except → None degrades to `[]`.
7. **DELETE `/documents/{id}` + `/api/documents/{id}`** (dual-router convention),
   ordered deletes (vectors → PG doc → prune entities → indexed row), response
   `{ok, deleted:{...}}`, repeat call → 404 (documented idempotency).
8. **Frontend delta only:** `documents[]._id` into attachment state,
   ingested-chip × → confirm → DELETE → remove/rollback; pending × stays local.
   Statuses gain `deleting`.

## 5. Latency budget (c7i-flex.large, worst case)

Vector(50) ~50ms + keyword RPC ~30ms + RRF ~1ms + hops (unchanged) +
rerank 100 pairs ~1–2s + LLM (unchanged). Rerank dominates: acceptable behind
streaming (metadata event already yielded), watched via `rerank_latency_ms`.

## 6. Stage 3 delete design (as implemented)

* `IngestionService.delete_document`: indexed-row lookup (404 → None) →
  PG chunk rows (ULIDs + entity links) → Chroma `delete(ids=[ULIDs])` →
  PG documents row (SQL cascades chunks/chunk_entities; explicit cleanup covers
  memory DB) → closure prune → indexed row last (repeats → clean 404).
* Closure prune: prune an entity iff it has no chunk refs AND no incident edge
  reaches live/shared knowledge; remove all incident edges of pruned entities
  (matches PG cascade semantics exactly — verified against the orphan-pair
  trap where two dead entities would otherwise keep each other alive).
* Legacy rows without `metadata.pg_document_id`: vectors unaddressable —
  indexed row still removed, counts report zeros, limitation logged.
* Memory DB has no cascades: every step runs explicitly (no-ops on PG).
  `$or` never used in queries (Supabase find ignores it) — separate equality
  queries only. `delete_many` counts are authoritative on PG, best-effort on
  Chroma (which swallows errors internally and rebuilds from PG anyway).
* Frontend: `documentId` flows upload-response → pending chip → message
  snapshot/strip; ingested × → confirm → DELETE → remove/rollback;
  pending × stays local; strip persists `{name, documentId}` (legacy
  string[] parsed).

## 7. Risks → mitigations

Slow home/ECR push → layers cached after first. FTS migration on live Supabase
→ run in SQL editor, `IF NOT EXISTS` everywhere. Logit scale leaking into UI →
`score` documented per-stage; badge shows counts, never scores. Memory-DB tests
can't do SQL → fakes + PG-gated integration (skipped without PG).
