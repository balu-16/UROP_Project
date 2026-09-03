# RAGnostic — Adaptive RAG System

Adaptive Retrieval-Augmented Generation that chooses retrieval depth from
retrieval confidence: exact semantic hits answer directly (0-hop), uncertain
queries expand over a Postgres entity graph (1-hop, then 2-hop), and the LLM
answers only from the fixed retrieval context with `[n]` citations.

## Architecture

```text
Chatbot/
├── client/            # Next.js 15 chat UI (port 3000)
├── server/            # FastAPI backend (port 8000), Python 3.11, local .venv
├── supabase/          # migrations/001_initial.sql + seed.sql (Postgres truth)
├── .chromadb/         # ChromaDB PersistentClient index (repo root, rebuildable)
├── SPEC.orig.md       # frozen original build spec (historical, do not follow blindly)
└── RAGnostic — Production-Grade Adaptive RAG System.md  # implementation design doc
```

- **Truth:** Supabase Postgres (`documents/chunks/entities/chunk_entities/relationships` + auth/chat tables).
- **Index:** ChromaDB `PersistentClient` at `<repo-root>/.chromadb/`, collection `ragnostic` (cosine). Deleting it only drops the index — it rebuilds from PG `chunks`.
- **Policy:** confidence = top Chroma cosine score; `>= 0.75` → ZERO_HOP/classical, else 1-hop → re-score → still `< 0.75` → 2-hop (`MAX_HOPS=2`).

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

# Frontend
cd ../client
npm install
echo "NEXT_PUBLIC_API_BASE_URL=http://localhost:8000" > .env.local
npm run dev            # http://localhost:3000
```

Keep everything local: backend deps/caches live under `server/`
(`.venv/`, `.hf_cache/`, `.torch_cache/`, `.cache/`). For offline backend
tests only: `MOCK_LLM=true` + `DISABLE_LOCAL_MODELS=true` with a `memory://` DB.

## Docs

- `server/README.md` — backend setup, full API table, retrieval policy, storage, tests, Docker.
- `client/README.md` — frontend setup, env, scripts, backend contract.
- `server/.env.example` — every backend env var with strict-boot notes.
- `client/.env.example` — frontend env (`NEXT_PUBLIC_API_BASE_URL`).
- `RAGnostic — Production-Grade Adaptive RAG System.md` — design/implementation reference.
- `SPEC.orig.md` — original frozen build prompt; historical, superseded by the code + docs above.
