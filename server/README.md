# RAGnostic Backend

FastAPI backend for adaptive Retrieval-Augmented Generation: deterministic
threshold retrieval over Supabase Postgres (truth) + local ChromaDB
(vector index), with NVIDIA NIM (OpenAI-compatible) answer generation.

## Stack

- Python 3.11, FastAPI `0.115.6`, Uvicorn `0.34.0`
- Supabase Postgres (truth) via `supabase==2.10.0` + `asyncpg==0.30.0` (migrations)
- ChromaDB `PersistentClient` `0.5.23` (rebuildable vector index, collection `ragnostic`)
- Embeddings `Snowflake/snowflake-arctic-embed-s` (dim 384) via `sentence-transformers==3.3.1` / `transformers==4.46.3`
- LLM: NVIDIA NIM OpenAI-compatible endpoint via `openai==1.54.0`
- Entity extraction: spaCy `en_core_web_sm` (regex fallback when disabled)

## Local Setup

```bash
cd server
/usr/local/bin/python3.11 -m venv .venv   # or: python3.11 -m venv .venv
source .venv/bin/activate

# CPU-only torch first (avoids huge CUDA wheels), then everything else:
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python -m spacy download en_core_web_sm

cp .env.example .env   # then fill SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, DATABASE_URL, LLM_API_KEY, JWT_SECRET
```

Everything must live under `server/`: the venv (`.venv/`), HuggingFace cache
(`.hf_cache/` via `HF_HOME`/`SENTENCE_TRANSFORMERS_HOME`), torch cache
(`.torch_cache/` via `TORCH_HOME`), and pip cache (`.cache/` via
`XDG_CACHE_HOME`). Never install packages globally or with `--user`.

Run:

```bash
# from server/ with the venv active:
python main.py
# equivalent:
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Strict boot (fail-fast, no degraded mode): startup raises `RuntimeError` if

- `JWT_SECRET` is missing/placeholder **and** `ENVIRONMENT=production`,
- the Chroma path (repo-root `.chromadb/`) is not writable,
- `LLM_API_KEY` is empty while `MOCK_LLM=false`,
- the embedding model fails to load while `DISABLE_LOCAL_MODELS=false`,
- ChromaDB is missing/corrupt, or Supabase is unreachable.

For offline unit tests only: `MOCK_LLM=true` + `DISABLE_LOCAL_MODELS=true` with
a `memory://` database URL. With a missing `JWT_SECRET` outside production an
ephemeral secret is generated (tokens don't survive restart).

## Configuration

All settings come from `server/.env` (see `.env.example` for the full,
commented list): app/port/CORS, Supabase + `DATABASE_URL`, Chroma
(`CHROMA_PATH=.chromadb`, resolved to the repo root), JWT, LLM
(`LLM_BASE_URL`, `LLM_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b`,
`LLM_TEMPERATURE=0.7`, `LLM_MAX_TOKENS=2048`), embeddings
(`EMBEDDING_MODEL=Snowflake/snowflake-arctic-embed-s`, dim 384),
chunking/retrieval (`CHUNK_SIZE=400`, `CHUNK_OVERLAP=50`,
`CHUNK_MIN_TOKENS=320`, `MAX_CONTEXT_TOKENS=3500`, `TOP_K=6` seed breadth,
`HIGH_THRESHOLD=0.75`, `LOW_THRESHOLD=0.60` reserved, `MAX_HOPS=2`,
`MAX_GRAPH_NODES=40`), hybrid (`VECTOR_TOP_K=50`, `KEYWORD_TOP_K=50`,
`RRF_K=60`), reranking (`RERANKER_ENABLED=true`,
`RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2`,
`RERANK_CANDIDATE_CAP=100`, `RERANK_TOP_K=5`), storage (`STORAGE_DIR=storage`,
`UPLOAD_MAX_MB=25`), ops (`RATE_LIMIT_PER_MINUTE=90`, `DEBUG_RETRIEVAL`).

## Retrieval policy

Confidence = top vector cosine similarity (`RetrievalConfidenceEvaluator`
reads `vector_score`, falling back to `score` for legacy inputs — RRF scores
are never fed to the gate).

- `confidence >= HIGH_THRESHOLD (0.75)` → **ZERO_HOP** (hybrid candidates, no expansion, `graph_nodes=0`)
- `< 0.75` → expand 1 hop over the PG entity graph and re-score → `>= 0.75` stays **ONE_HOP**, else **TWO_HOP** (`MAX_HOPS=2`)

Hybrid retrieval: every query searches Chroma vectors (`VECTOR_TOP_K`) and
Postgres full-text (`KEYWORD_TOP_K`, `match_chunks_fts` RPC from migration
`002_fts_keyword.sql`, session-isolated) and fuses both lists with RRF
(`RRF_K`, provenance in `retrieval_sources`). Expansion seeds are the top-`TOP_K`
fused chunk IDs, so expansion breadth matches the old semantic-only flow.

Cross-encoder reranking runs strictly **after** 0/1/2-hop retrieval: the final
pool is capped (`RERANK_CANDIDATE_CAP`), scored as raw relevance logits
(sort-only, never percentages), sliced to `RERANK_TOP_K` for the context, with
graceful fallback to pre-rerank order on any failure. Disabled automatically
when `DISABLE_LOCAL_MODELS=true` or the model can't load (requests never crash).
First production boot downloads ~90 MB of weights; watch `rerank_latency_ms`.

- `confidence >= HIGH_THRESHOLD (0.75)` → **ZERO_HOP** (classical, semantic only, `graph_nodes=0`)
- `< 0.75` → expand 1 hop over the PG entity graph and re-score → `>= 0.75` stays **ONE_HOP**, else **TWO_HOP** (`MAX_HOPS=2`)

Graph-expansion chunks carry a fixed score of `0.55`
(`app/retrieval/adaptive.py`), so 1-hop only wins when expansion surfaces
fresh chunks scoring above the threshold. Frontend arm names map as
`depth 0/1/2 → standard_rag / graph_rag_1hop / graph_rag_2hop`.

## Main APIs

Every route exists with and without the `/api` prefix (e.g. `/chat` and
`/api/chat`). Auth routes use `Authorization: Bearer <access_token>`.

- `POST /auth/signup`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`
- `GET /sessions`, `POST /sessions`, `POST /sessions/{id}/truncate`
- `POST /index-documents` (aliases: `/api/index-documents`, `/ingestion`, `/api/ingestion`) — multipart `files`, max 20 files/request, 25 MB each; types `.pdf/.txt/.md/.markdown/.pptx` (PPTX slides extracted as `[Slide N]` text + tables + notes). Returns `{chunk_count, documents: [{_id, filename, ...}]}` — the `_id` drives frontend un-upload.
- `DELETE /documents/{id}?session_id=...` (alias: `/api/documents/{id}`) — un-upload: removes chunks, Chroma vectors (by ULID), graph links, prunes orphan-only entities (shared entities survive), deletes the indexed row. Repeat calls → `404` (idempotent).
- `GET /documents?session_id=...` (alias: `/api/documents`) — session-scoped, ownership-checked list `{documents: [{_id, filename, chunk_count}]}`; server truth for the frontend strip (localStorage is cache).
- `POST /chat` — `{message, session_id, reasoning}` → `text/event-stream` with `stage`, `metadata` (`retrieval{depth,confidence,strategy,retrieval_mode,candidate_count,reranked_count,reranker_model}`, `sources[]`), `token`, `reasoning`, `usage`, `reward`, `done`, `followups`, `error`
- `GET /chat-history/{session_id}`
- `GET /retrieval-debug?session_id&limit` (auth)
- `GET /metrics` (auth) — uptime, request counts, latency p50/p95, `arm_distribution`, `vector_index_size`, graph stats
- `POST /feedback` (auth) — `{message_id, session_id, rating 0-1}`
- `GET /health`, `GET /app-config`

## Storage layout

- ChromaDB: `<repo-root>/.chromadb/` (`PersistentClient`, collection `ragnostic`, cosine). Rebuildable from PG `chunks`. Tests isolate to `server/storage_test/.chromadb/`; Docker volume is `/app/.chromadb`.
- Truth: Supabase tables `users`, `auth_sessions`, `chat_sessions`, `messages`, `retrieval_logs`, `reward_logs`, `indexed_documents`, `documents`, `chunks`, `entities`, `chunk_entities`, `relationships` (`supabase/migrations/001_initial.sql`, plus `002_fts_keyword.sql` for the keyword-search GIN index, session expression index, and `match_chunks_fts` RPC — apply in the Supabase SQL editor, idempotent).
- Local: `server/storage/embedding_cache.json` (keyed `sha256(model:dim:text)`).

## Tests

```bash
cd server
source .venv/bin/activate
pytest -q tests/            # chunking unit tests + full API suite (memory DB, mock LLM)
python tests/run_all.py     # same suite with offline env forced
```

Tests use a `memory://` database, `MOCK_LLM=true`,
`DISABLE_LOCAL_MODELS=true`, and isolated `storage_test/` (deleted before
each case). Chroma 0-hop rarely triggers under hash embeddings (~0.28
scores); the real model restores threshold behavior.

Coverage beyond the API suite: `test_confidence_gate.py` (0.75 gate pins),
`test_hybrid_retrieval.py` (RRF fusion, gate-vs-RRF regression, fused-seed
ordering, keyword degradation), `test_reranking.py` (sort/cap/fallback,
rerank-after-expansion ordering proof), `test_delete_documents.py`
(cascade, shared-entity survival, isolation, idempotency, route registration).
PG-backed tests (live `match_chunks_fts`) are gated behind `RAG_TEST_PG=1`
and skipped by default.

## Docker

```bash
cd server
docker compose up --build
```

Backend on `8000:8000` (volumes `./storage:/app/storage`,
`chromadb_data:/app/.chromadb`), frontend on `3000:3000`.
