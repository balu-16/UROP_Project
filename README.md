# RAGnostic — Adaptive RAG System

Adaptive Retrieval-Augmented Generation that chooses retrieval depth from
retrieval confidence: exact semantic hits answer directly (0-hop), uncertain
queries expand over a Postgres entity graph (1-hop, then 2-hop), and the LLM
answers only from the fixed retrieval context with `[n]` citations.

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
| Supabase Postgres | `documents / chunks / entities / chunk_entities / relationships` + auth/chat tables | `supabase/migrations/001_initial.sql` |
| ChromaDB | `PersistentClient` at `<repo-root>/.chromadb/`, collection `ragnostic` (cosine) | Rebuilds from PG `chunks`; deleting it only drops the index |
| Policy | confidence = top Chroma cosine score; `>= 0.75` → ZERO_HOP, else 1-hop → re-score → still `< 0.75` → 2-hop (`MAX_HOPS=2`) | `server/` retrieval module |
| Client | Dark chat, sources with citations, retrieval badge, feedback actions | `client/src/` |

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
  → SSE: stage → metadata{retrieval{depth,confidence,strategy}, sources[]}
  → token* (80ms-batched) → reasoning* → reward → followups → done
upload (attach / drag-drop) → POST /index-documents (multipart files + session_id)
  → {chunk_count} → toast "Indexed N chunks — ask away!"
```

Documents belong to exactly one chat: the backend requires `session_id` on
upload and scopes every chunk/vector to it. Chatting lazily creates a session
on first send so the composer never streams against `null`.

## Environment

| File | Variables | Notes |
|---|---|---|
| `server/.env` | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`, `LLM_API_KEY`, `JWT_SECRET`, `FRONTEND_ORIGIN`/`CORS_ORIGINS`, `MAX_HOPS`, `MOCK_LLM`, `DISABLE_LOCAL_MODELS` | Full commented list in `server/.env.example`; strict boot fails fast on bad config |
| `client/.env.local` | `NEXT_PUBLIC_API_BASE_URL` (defaults to `http://localhost:8000`) | Copy from `client/.env.example`; Supabase placeholders elsewhere are unused — auth is backend JWT |

## Screenshots

Add captures here as the UI evolves (landing, auth, chat, sources):

```text
docs/screenshots/landing.png
docs/screenshots/auth.png
docs/screenshots/chat.png
docs/screenshots/chat-sources.png
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Backend error 0 / Failed to fetch` in chat | Backend down or CORS: check `python main.py` logs + `FRONTEND_ORIGIN=http://localhost:3000` in `server/.env` |
| 401 loop → kicked to login | Refresh cookie expired; `POST /auth/refresh` failed — sign in again |
| Upload succeeds but `0 chunks indexed` | Files empty/unparseable or wrong extension (only `.pdf/.txt/.md/.markdown/.pptx`, 20 files, 25MB each) |
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
