# RAGnostic Client

Next.js 15 chat UI for the RAGnostic backend (dark chat, sources with
citations, retrieval badge, feedback actions).

## Setup

```bash
cd client
npm install
echo "NEXT_PUBLIC_API_BASE_URL=http://localhost:8000" > .env.local
npm run dev     # http://localhost:3000
```

The backend must allow this origin (`FRONTEND_ORIGIN`/`CORS_ORIGINS` in
`server/.env`, default `http://localhost:3000`).

## Environment

Only one variable is read by the app (`src/lib/api.ts`, defaults to
`http://localhost:8000` when unset):

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Put it in `.env.local` (gitignored, see `.env.example`). There are no other
required frontend vars — the Supabase placeholders some examples mention are
unused; auth is handled by the backend's custom JWT.

## Scripts

- `npm run dev` — local dev server (port 3000)
- `npm run build` — production build
- `npm start` — serve production build
- `npm run lint` — ESLint

## Backend contract

Base URL = `NEXT_PUBLIC_API_BASE_URL`. Chat is `POST /chat`
(`{message, session_id, reasoning}`) streaming `text/event-stream` events:
`stage`, `metadata` (`retrieval{depth,confidence,strategy}`, `sources[]`),
`token`, `reasoning`, `usage`, `reward`, `done`, `followups`, `error`.
Uploads go to `POST /index-documents` (multipart `files`, max 20 files,
25 MB each; `.pdf/.txt/.md/.markdown/.pptx`).
