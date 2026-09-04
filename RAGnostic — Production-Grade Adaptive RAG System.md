# RAGnostic — Adaptive RAG System (Python FastAPI + Supabase + ChromaDB)

> **Stack per implementation:** Python FastAPI • Supabase Postgres (truth) • ChromaDB `PersistentClient` at `.chromadb` (vector index) • JWT (HS256, custom) • NVIDIA NIM `nvidia/nemotron-3.5-lightning-30b-a3b` via `openai` SDK. No `pgvector`, no NetworkX file, no bandit in V1. Threshold policy is deterministic.

---

## 1. Goal & Non-Goals

**Goal:** Adaptive RAG that chooses retrieval depth by retrieval confidence:
```
0-Hop → Semantic only (Chroma)
1-Hop → Semantic + 1 graph expansion (Supabase PG)
2-Hop → Semantic + 2 graph expansions
```
LLM generates answer only after retrieval is fixed.

**Non-Goals V1:** No contextual bandit/RL/reranker/Neo4j/NetworkX file graph/Kubernetes/multi-service. Those are V2+ interfaces only. Keep thresholds deterministic (`HIGH=0.75`, `LOW=0.60`, `MAX_HOPS=2`).

---

## 2. Repo Layout

```
ragnostic/
├── client/               # Next.js (kept) + React, API client, chat UI
├── server/               # FastAPI modular monolith
│   ├── app/main.py       # lifespan, CORS, wiring
│   ├── app/config/       # Settings (validated at startup)
│   ├── app/database/     # Supabase adapter (Motor shim for tests)
│   ├── app/vectorstore/  # VectorStore interface → ChromaVectorStore
│   ├── app/graph_store/  # PGGraphStore (PG truth)
│   ├── app/retrieval/    # confidence + threshold policy + adaptive orchestrator
│   ├── app/ingestion/    # Document → chunk → PG → embed → Chroma → graph
│   ├── app/llm/          # LLMProvider (OpenAI-compatible)
│   ├── app/api/          # /api/chat, /api/ingestion, /health, metrics
│   └── supabase/migrations/ # 001_initial.sql (versioned)
├── .chromadb/            # Chroma PersistentClient (local, gitignored, rebuildable)
├── supabase/             # migrations + seed.sql
├── SPEC.md               # this file (Option B)
└── README.md
```

---

## 3. Data Model — PG Truth, Chroma Index

**Principle (§6):** Postgres is truth; Chroma is rebuildable index. If `.chromadb` is deleted, rebuild from `chunks` table.

**Supabase Postgres (truth):**
```sql
documents(id uuid pk, user_id text fk, title text, source text, content text, metadata jsonb)
chunks(id uuid pk, document_id uuid fk, chunk_index int, content text, chunk_id text unique, metadata jsonb)
entities(id uuid pk, name text unique, type text, metadata jsonb)
chunk_entities(chunk_id uuid fk, entity_id uuid fk, pk(chunk_id,entity_id))
relationships(id uuid pk, source_entity_id uuid, target_entity_id uuid, relation_type text, metadata jsonb)
```
Plus existing auth/chat tables preserved for JWT continuity:
```sql
users(_id text pk, email text unique, name text, password_hash text, token_invalid_before timestamptz)
auth_sessions(_id text pk, user_id text fk, refresh_hash text, expires_at timestamptz, revoked bool)
chat_sessions(_id text pk, user_id text, title, updated_at)
messages(_id text pk, session_id text, user_id text, role, content, selected_arm, sources jsonb, latency_ms int, retrieval_log_id text)
retrieval_logs(_id text pk, user_id, session_id, message_id, selected_arm, arm_scores jsonb, retrieved_chunks jsonb, diagnostics jsonb)
indexed_documents(_id text pk, user_id, filename, metadata jsonb, chunk_count int)
```
Indexes on `(user_id, updated_at)`, `(session_id, created_at)`, `lower(email)`, `(source_entity_id)`, `(target_entity_id)`.

**ChromaDB (index):** `PersistentClient(path=.chromadb)` collection `ragnostic` `hnsw:space=cosine`. Each point: `id=chunk_id`, `embedding`, `metadata={user_id, document_id, chunk_id, entity_ids, source, chunk_index}`, `document=text`. User-isolated via `where={"user_id": uid}` at query time.

---

## 4. Ingestion Pipeline

```
Document → Text Extraction (pypdf / pptx / utf8) → Text Cleaning → Chunking → PG (documents/chunks) → Embedding (Snowflake/snowflake-arctic-embed-s 384, cached) → Chroma add → GraphConstruction (entities + relationships) → Save
```

Modular services: `DocumentParser`, `Chunker(CHUNK_SIZE=400, CHUNK_OVERLAP=50)`, `EmbeddingService`, `ChromaVectorStore`, `PGGraphStore`. Each stage is replaceable via interface. Max `upload_max_mb=25`, `max 20 files/request`.

---

## 5. Embeddings

Abstraction `EmbeddingProvider { embedText, embedDocuments, embedQuery }`. Model from `EMBEDDING_MODEL` (`Snowflake/snowflake-arctic-embed-s`), batch `8`, dim `384`. Cache at `storage/embedding_cache.json` (`sha(model:dim:text)`). Falls back to deterministic `blake2b` hash embedding when `DISABLE_LOCAL_MODELS=true` (tests).

---

## 6. Vector Store

Interface `VectorStore { add, search, delete, rebuild, size }` → `ChromaVectorStore`. No direct Chroma access outside this module. `rebuild()` clears and re-adds from PG `chunks` (supports §6).

---

## 7. Graph Store

Interface `GraphStore { add_chunk, expand_chunks(hops), stats }` → `PGGraphStore`. Uses `chunk_entities` + `relationships` tables. Batch queries (`in` filter) to avoid N+1. Deduplicates, prevents cycles, respects `MAX_HOPS=2`, `MAX_GRAPH_NODES=40`.

---

## 8. Retrieval Pipeline (§13)

```
User Query → Validate → Embed Query → Chroma semantic TopK → Similarity scores → ConfidenceEvaluator → ThresholdPolicy → (0-hop? or 1-hop → evaluate → 2-hop?) → ContextBuilder → LLM → Answer
```

---

## 9. Retrieval Depth & Policy

Enum `RetrievalDepth {0=ZERO_HOP, 1=ONE_HOP, 2=TWO_HOP}`.

**Threshold Controller (§15-16):**
```python
if confidence >= HIGH_THRESHOLD (0.75):
    depth = 0  # semantic only
else:
    depth = 1
    # after 1-hop
    if confidence_after_1hop >= HIGH_THRESHOLD:
        depth = 1
    elif MAX_HOPS >= 2:
        depth = 2
```
Config: `HIGH_THRESHOLD=0.75`, `LOW_THRESHOLD=0.60` (reserved), `MAX_HOPS=2`, `MAX_GRAPH_NODES=40`, `TOP_K=6`. No LLM in decision.

**Decision object:** `{depth, reason, threshold, confidence, strategy}` (e.g., `ONE_HOP`).

---

## 10. Confidence (§17)

Abstraction `RetrievalConfidenceEvaluator`. V1: `confidence = max(scores)` (top cosine similarity). Future: `avg top-k`, `margin`, `distribution` without changing pipeline.

---

## 11. Graph Expansion (§18)

- 1-hop: `seed chunk_ids → seed entities → directly connected entities → chunks`
- 2-hop: `neighbors of neighbors`
- Dedup chunk IDs, preserve max score, `graph_boost` where applicable, enforce user isolation (`meta.user_id == query user`).

---

## 12. Context Builder (§19)

Dedup by `chunk_id`, skip `<CHUNK_MIN_TOKENS=320`, respect `MAX_CONTEXT_TOKENS=3500`, preserve `chunk_id/document_id/source/score`, produce `{context: "[1] source=...\\ntext ...", chunks, token_count}`.

No prompt building inside DB/vector layers.

---

## 13. Reranker & Bandit

**Reranker (implemented post-V1, see thinking.md + plan.md):** interface `Reranker { rerank }` with `CrossEncoderReranker (ms-marco-MiniLM-L-6-v2, raw logits, sort-only)` + `NullReranker` passthrough (disabled / `DISABLE_LOCAL_MODELS` / load failure). Runs AFTER 0/1/2-hop, never before; `RERANK_TOP_K=5 < TOP_K=6` by design; `Null` path preserves RRF order verbatim. **No bandit V1 (§21):** interface `RetrievalPolicy` with `ThresholdRetrievalPolicy` now, `BanditRetrievalPolicy` future without rewriting pipeline.

---

## 14. LLM (§22)

`LLMProvider { generate, stream }` • NVIDIA NIM via `openai.AsyncOpenAI(base_url="https://integrate.api.nvidia.com/v1")` • Model `nvidia/nemotron-3.5-lightning-30b-a3b` • `temperature 0.7, top_p 0.95, max_tokens 2048` • Structured output via `response_format={"type":"json_object"}` when needed • `extra_body={"chat_template_kwargs":{"thinking":True,"reasoning_effort":"high"}}` for reasoning. Mock mode when `MOCK_LLM=true` or key missing.

Prompt layer (§23) separate from retrieval; instructs to cite `[n]`, avoid hallucination, report missing info.

---

## 15. API

**Chat (streaming SSE):**
```
POST /api/chat  (alias: POST /chat for compat)
{ "message": "query", "session_id": "chat_...", "reasoning": true }
→ text/event-stream
  event: stage {stage: retrieving|thinking|writing}
  event: metadata {session_id, sources[], retrieval{depth,confidence,strategy}}
  event: token {delta}
  event: reasoning {reasoning}
  event: usage {prompt_tokens, completion_tokens}
  event: reward {reward, quality, faithfulness}
  event: done {message_id, session_id, retrieval}
  event: followups {questions: [3]}
```

**Ingestion:**
```
POST /api/ingestion  (aliases: /index-documents, /api/index-documents)
multipart files (max 20, 25MB each, .pdf/.txt/.md/.markdown/.pptx)
→ {documents[], chunk_count, entity_count, vector_index_size, graph{nodes,edges}}
GET /documents?session_id=… (alias: /api/documents) → {documents: [{_id, filename, chunk_count}]}
DELETE /documents/{id}?session_id=… (alias: /api/documents/{id}) → {ok, deleted}
```

**Health:**
```
GET /api/health  → {ok, service}
GET /api/app-config → {name, features: [adaptive-retrieval, graph-rag, streaming, threshold-policy]}
GET /metrics (auth) → {uptime, request_counts, latency p50/p95, vector_index_size, graph}
GET /retrieval-debug?session_id&limit (auth) → {logs}
POST /feedback (auth) {message_id, session_id, rating 0-1} → {ok}
```

All under `API_PREFIX=/api` plus legacy aliases. Frontend uses `NEXT_PUBLIC_API_BASE_URL`.

---

## 16. Config (validated at startup, fail fast)

```env
# App
PORT=8000
API_PREFIX=/api
FRONTEND_ORIGIN=http://localhost:3000
CORS_ORIGINS=http://localhost:3000

# Supabase
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
DATABASE_URL=postgresql://postgres.PROJECT:PWD@aws-0-REGION.pooler.supabase.com:6543/postgres

# Chroma
CHROMA_PATH=.chromadb
CHROMA_COLLECTION=ragnostic

# Auth
JWT_SECRET=...
JWT_ALGORITHM=HS256
ACCESS_TOKEN_MINUTES=30
REFRESH_TOKEN_DAYS=14

# LLM
LLM_API_KEY=...
LLM_BASE_URL=https://integrate.api.nvidia.com/v1
LLM_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b

# Retrieval
EMBEDDING_MODEL=Snowflake/snowflake-arctic-embed-s
CHUNK_SIZE=400
CHUNK_OVERLAP=50
TOP_K=6
HIGH_THRESHOLD=0.75
LOW_THRESHOLD=0.60
MAX_HOPS=2
MAX_GRAPH_NODES=40
MAX_CONTEXT_TOKENS=3500
```

---

## 17. Security, Error, Logging

- DTO validation (email, 1-12000 char query), size limits, CORS not `*`, secrets via env, no keys in frontend, no stack traces to client.
- Centralized error handler → `{success:false, error:{code, message}}` (500 hides internals).
- Structured logs: `query_id`, `semantic_score`, `selected_depth`, `graph_nodes`, `latency_ms`; never log keys/tokens.
- Request ID per chat for tracing, returned in metadata.

---

## 18. Frontend (§32-38)

Next.js dark chat: `ChatContainer | ChatMessage | ChatInput | TypingIndicator | SourceList | RetrievalBadge`. Clean, minimal, responsive, a11y (semantic HTML, keyboard `Cmd+Enter`, focus states). State via hooks, `services/api.ts` centralizes `fetch`. Retrieval badge subtle: `0-hop · 0.84` / `1-hop · 0.68 · 7 nodes`.

---

## 19. Testing (§49)

- **Policy:** `score >=0.75 →0-hop`, `medium →1-hop`, `low →2-hop` (max 2)
- **Graph:** 0/1/2-hop, dup/cycle/missing/disconnected
- **Context:** dup, empty, metadata, token limits
- **API:** valid/empty/malformed, auth, ingestion validation, LLM failure
- **E2E:** `memory://` + `MOCK_LLM` via `tests/test_api.py` (3 cases: health, auth, full ingestion→chat→history→debug→feedback→metrics).

Run: `cd server && pytest -q` or `python tests/run_all.py`.

---

## 20. Observability (§59) & Eval Readiness (§60)

Logs expose `query, initial_score, threshold, selected_depth, semantic_count, graph_nodes, context_size, llm_latency, total_latency`. Table `retrieval_logs` persists `{query_id, confidence, depth, chunks, diagnostics}` for later analysis; no heavy analytics in V1.

---

## 21. Extensibility (§61)

Interfaces at boundaries make V2+ additive:
- V2: `Reranker`
- V3: `BanditRetrievalPolicy`
- V4: `LearnedRetrievalPolicy`
- V5: Hybrid search
No rewrites needed — swap implementations.

---

## 22. What NOT to do in V1 (§62)

No bandit/RL/reranker/Neo4j/NetworkX file/microservices/K8s/distributed vectors/agentic workflows. Modular monolith (§63): `React → FastAPI {Chat, Retrieval, Ingestion, Graph(PG), VectorStore(Chroma), Embeddings, LLM}`.

---

## Appendix A — DDL (supabase/migrations/001_initial.sql)

See `supabase/migrations/001_initial.sql` (users, auth_sessions, chat_sessions, messages, retrieval_logs, reward_logs, indexed_documents + documents/chunks/entities/chunk_entities/relationships). All `create if not exists` + indexes. RLS off (custom JWT).

**Seed:** `supabase/seed.sql` — 3 docs (Turbocharger/Intercooler/Combustion), 3 chunks, 4 entities, 3 relationships forming 0/1/2-hop demo. Query demos: “What does turbocharger do?” (0-hop), “What happens after turbocharger compresses air?” (1-hop → Intercooler), “How does turbocharger affect combustion?” (2-hop).

---

## Appendix B — Mermaid

```mermaid
flowchart TD
  U[User] --> R[React]
  R --> C[POST /api/chat]
  C --> V[Validate]
  V --> E[Embed Query]
  E --> S[Chroma TopK]
  S --> Conf[Confidence = max(score)]
  Conf --> P{ThresholdPolicy}
  P -->|>=0.75| Z[0-Hop]
  P -->|<0.75| O[1-Hop PG]
  O --> C2{Conf after 1-hop >=0.75?}
  C2 -->|yes| O1[Use 1-Hop]
  C2 -->|no| T[2-Hop PG]
  Z --> B[ContextBuilder]
  O1 --> B
  T --> B
  B --> L[LLM nemotron]
  L --> A[Answer + sources]
  A --> R
```

---

## Appendix C — Setup

```bash
git clone ... && cd ragnostic
# Backend
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill SUPABASE_URL/KEYS, LLM_API_KEY
python -c "import asyncpg; ..." # or rely on auto-migration at startup (pooler port 6543)
uvicorn app.main:app --reload --port 8000

# Frontend
cd ../client
npm install
echo "NEXT_PUBLIC_API_BASE_URL=http://localhost:8000" > .env.local
npm run dev
```

**Env validation:** FastAPI fails fast if `SUPABASE_URL`/`KEY` or `LLM_API_KEY` (when `MOCK_LLM=false`) missing. `.chromadb/` auto-created (PersistentClient), gitignored.

---

## Appendix D — Verification Checklist (§66)

1. Client/server separated ✓
2. React runs, 3. FastAPI runs, 4. CORS, 5. Env validated
6. Supabase tables exist, 7. Chroma `.chromadb` count>0
8. Ingest → 9. chunks → 10. embeddings → 11. semantic search → 12. scores
13. Policy 0-hop, 14. 1-hop, 15. 2-hop, 16. cycles/dup prevented, 17. context, 18. LLM
19. `POST /api/chat` SSE, 20. Frontend chat, 21. loading/error, 22. sources, 23. retrieval badge
24. Tests pass, 25. README complete, 26. no secrets, 27. no extra deps, 28. `tsc --noEmit` & `pyright` strict, 29. `npm run build` & `pytest -q` green.

**Known limits:** Hash embeddings when `DISABLE_LOCAL_MODELS=true` give lower scores (~0.28) so 0-hop rarely triggers in tests; real model restores thresholds. PG graph is simple `mentioned_with`; richer relations are V2.

**Reranker status (done, supersedes the old next-step below):** implemented as `server/app/retrieval/reranking.py` (`CrossEncoderReranker` MiniLM-L6 + `NullReranker` fallback), wired post-hop in `AdaptiveRetrievalService.retrieve()` before `ContextBuilder.build()` (see `plan.md` Stages 0–4, `thinking.md` §3–5).
