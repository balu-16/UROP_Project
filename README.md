# RAGnostic — Adaptive RAG System

Adaptive Retrieval-Augmented Generation that chooses retrieval depth from
retrieval confidence: exact semantic hits answer directly (0-hop), uncertain
queries expand over a Postgres entity graph (1-hop, then 2-hop), and the LLM
answers only from the fixed retrieval context with `[n]` citations.
Hybrid retrieval (Chroma vectors + Postgres full-text fused by RRF) feeds the
policy, and a MiniLM cross-encoder reranks the final evidence before answering.

The UI is deliberately plain — ChatGPT/Grok-style flat surfaces, hairline
borders, one centered `768px` column — so the retrieval diagnostics
(depth, confidence, latency, sources) do the talking instead of decoration.

## Repository map

```text
Chatbot/
├── client/            # Next.js 15 chat UI (port 3000)
├── server/            # FastAPI backend (port 8000), Python 3.11, local .venv
├── supabase/          # migrations/001_initial.sql + seed.sql (Postgres truth)
├── .chromadb/         # ChromaDB PersistentClient index (repo root, rebuildable)
├── SPEC.orig.md       # frozen original build spec (historical, do not follow blindly)
└── RAGnostic — Production-Grade Adaptive RAG System.md  # implementation design doc
```

| Layer | Role | Source of truth |
|---|---|---|
| Supabase Postgres | `documents / chunks / entities / chunk_entities / relationships` + auth/chat tables | `supabase/migrations/001_initial.sql` + `002_fts_keyword.sql` (keyword GIN index + `match_chunks_fts` RPC) |
| ChromaDB | `PersistentClient` at `<repo-root>/.chromadb/`, collection `ragnostic` (cosine) | Rebuilds from PG `chunks`; deleting it only drops the index |
| Policy | confidence = top vector cosine (RRF never touches the gate); `>= 0.75` → ZERO_HOP, else 1-hop → re-score → still `< 0.75` → 2-hop (`MAX_HOPS=2`); MiniLM-L6 reranks the final pool (top 5) | `server/app/retrieval/` (`adaptive.py`, `policy.py`, `confidence.py`, `keyword.py`, `fusion.py`, `reranking.py`) |
| Client | Dark chat, attachment chips + per-message docs, auto-titled sessions, sources with citations, retrieval badge (`· top N`), feedback actions | `client/src/` |

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Node.js | 20+ | `client/` uses Next 15.1, React 19 |
| Python | 3.11 | Backend venv must live under `server/.venv/` |
| Supabase project | — | Provides `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL` |
| NVIDIA NIM key | — | OpenAI-compatible endpoint via `LLM_API_KEY` |
| `FRONTEND_ORIGIN` | `http://localhost:3000` locally | Must match where `client/` runs or CORS blocks `POST /chat` |

## Quickstart

```bash
# Backend
cd server
python3.11 -m venv .venv && source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python -m spacy download en_core_web_sm
cp .env.example .env   # fill SUPABASE_*, DATABASE_URL, LLM_API_KEY, JWT_SECRET
python main.py         # http://localhost:8000, strict boot (fail-fast)

# Frontend (new terminal)
cd client
npm install
echo "NEXT_PUBLIC_API_BASE_URL=http://localhost:8000" > .env.local
npm run dev            # http://localhost:3000
```

Health checks:

```bash
curl http://localhost:8000/health        # backend strict-boot gate
curl http://localhost:3000               # frontend landing
```

Keep everything local: backend deps/caches live under `server/`
(`.venv/`, `.hf_cache/`, `.torch_cache/`, `.cache/`). For offline backend
tests only: `MOCK_LLM=true` + `DISABLE_LOCAL_MODELS=true` with a `memory://` DB.

## Request flow

```text
composer (Enter) → POST /chat {message, session_id, reasoning}
  → SSE: stage → metadata{retrieval{depth,confidence,strategy,retrieval_mode,candidate_count,reranked_count,reranker_model}, sources[]}
  → token* (80ms-batched) → reasoning* → reward → followups → done
upload (attach / drag-drop) → staged as chips in the composer → POST /index-documents (multipart files + session_id)
  → {chunk_count, documents: [{_id, filename}]} → chips marked ready → send snapshots them onto the message
strip (per-chat docs) → GET /documents?session_id=… (server truth; localStorage is offline cache)
un-upload (× on an ingested chip) → confirm → DELETE /documents/{id}?session_id=… → chip + index entries removed
```

Retrieval notes: `RERANK_TOP_K=5 < TOP_K=6` by design (final context holds at
most top-5 reranked chunks); with `NullReranker` (offline/tests) RRF order is
preserved verbatim (no score re-sort). Known quirk (preserved): terminal 1-hop
is currently unreachable with defaults (`initial<0.75` to expand,
post-expansion `max(<0.75,0.55)<0.75` → always 2-hop); recalibration deferred
until telemetry, per paused-calibration plan.

Documents belong to exactly one chat: the backend requires `session_id` on
upload and scopes every chunk/vector to it. Chatting lazily creates a session
on first send — titled from the message (or filename for upload-first chats) —
so the composer never streams against `null` and the sidebar never fills with
"New chat".

## Environment

| File | Variables | Notes |
|---|---|---|
| `server/.env` | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`, `LLM_API_KEY`, `JWT_SECRET`, `CORS_ORIGINS` (`FRONTEND_ORIGIN` deprecated), `MAX_HOPS`, `MOCK_LLM`, `DISABLE_LOCAL_MODELS`, `VECTOR_TOP_K`/`KEYWORD_TOP_K`/`RRF_K`, `RERANKER_ENABLED`/`RERANKER_MODEL`/`RERANK_CANDIDATE_CAP`/`RERANK_TOP_K`, `UPLOAD_MAX_MB`/`TOTAL_UPLOAD_MAX_MB`, `RATE_LIMIT_*`, `GREETING_CONFIDENCE_THRESHOLD` | Full commented list in `server/.env.example`; strict boot fails fast on bad config. Supabase migrations `001`+`002` auto-apply on boot (manual SQL-editor step is fallback only). |
| `client/.env.local` | `NEXT_PUBLIC_API_BASE_URL` (defaults to `http://localhost:8000`) | Copy from `client/.env.example`; Supabase placeholders elsewhere are unused — auth is backend JWT |

## Screenshots

No captures checked in yet (`docs/screenshots/` does not exist). Planned shots
as the UI evolves: landing, auth, chat, chat-sources.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Backend error 0 / Failed to fetch` in chat | Backend down or CORS: check `python main.py` logs + `FRONTEND_ORIGIN=http://localhost:3000` in `server/.env` |
| 401 loop → kicked to login | Refresh cookie expired; `POST /auth/refresh` failed — sign in again |
| Upload succeeds but `0 chunks indexed` | Files empty/unparseable or wrong extension (only `.pdf/.txt/.md/.markdown/.pptx`, 20 files, 25MB each) |
| Un-upload × does nothing / 404 | Backend image predates the DELETE endpoint — rebuild + redeploy `:1.0.1+`; check `session_id` matches the chat |
| Empty answers / stale history | Session changed mid-stream; the hook ignores history loads while `abortRef` is set — retry after stream ends |
| Chroma corrupt / wrong vectors | `rm -rf .chromadb/` at repo root; it rebuilds from PG `chunks` on next index |
| `npm run build` font fetch retry | Offline fonts.googleapis.com; build still succeeds (Next retries, falls back to system fonts) |

## Docs

- `server/README.md` — backend setup, full API table, retrieval policy, storage, tests, Docker.
- `client/README.md` — frontend setup, env, scripts, backend contract, component map, perf notes.
- `server/.env.example` — every backend env var with strict-boot notes.
- `client/.env.example` — frontend env (`NEXT_PUBLIC_API_BASE_URL`).
- `RAGnostic — Production-Grade Adaptive RAG System.md` — design/implementation reference.
- `SPEC.orig.md` — original frozen build prompt; historical, superseded by the code + docs above.
