# RAGnostic Backend

Production-oriented FastAPI backend for adaptive Retrieval-Augmented Generation.

## Local Setup

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The local `.env` contains the development MongoDB/OpenRouter configuration. Rotate those keys before deployment.

## Main APIs

- `POST /auth/signup`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `GET /auth/me`
- `GET /sessions`
- `POST /sessions`
- `POST /chat`
- `POST /index-documents`
- `GET /chat-history/{session_id}`
- `GET /retrieval-debug`
- `GET /metrics`
- `POST /feedback`
- `GET /app-config`
- `GET /health`

`POST /chat` returns server-sent events: `metadata`, `reasoning`, `token`, `usage`, `reward`, `done`, and `error`.

## Tests

```bash
cd backend
python tests/run_all.py
```

Tests use `memory://` MongoDB, mock OpenRouter streaming, disabled local models, and isolated storage.

## Docker

```bash
cd backend
docker compose up --build
```

