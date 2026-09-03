# RAGnostic Client

Next.js 15 + React 19 chat UI for the RAGnostic backend. Deliberately
plain — flat surfaces, hairline borders, one centered `768px` column,
mono metadata lines — in the spirit of ChatGPT/Grok.

Routes: `/` (landing) and `/chat` (sidebar + messages + composer).
Auth is backend JWT (`access_token` in `localStorage` + refresh cookie);
there is no direct Supabase usage in the frontend.

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
- `npm run build` — production build (`First Load JS ~164kB /`, `~201kB /chat`)
- `npm start` — serve production build
- `npm run lint` — ESLint
- `npx tsc --noEmit` — typecheck (must be clean before PR)

## Backend contract

Base URL = `NEXT_PUBLIC_API_BASE_URL`.

| Method | Endpoint | Body | Returns |
|---|---|---|---|
| `POST` | `/auth/signup` | `{name, email, password}` | `{access_token, user}` |
| `POST` | `/auth/login` | `{email, password}` | `{access_token, user}` |
| `POST` | `/auth/refresh` | cookie | `{access_token}` (singleflight in `api.ts`) |
| `POST` | `/auth/logout` | — | clears refresh cookie |
| `GET` | `/auth/me` | — | `User` (boot check in `chat/page.tsx`) |
| `GET` | `/sessions` | — | `BackendSession[]` (grouped Today/Yesterday/Previous 7 Days) |
| `POST` | `/sessions` | `{title?}` | `BackendSession` (lazy-created on first send) |
| `POST` | `/sessions/:id/truncate` | `{message_id}` | `{ok, deleted}` (edit-and-resend branch cut) |
| `GET` | `/chat-history/:sessionId` | — | `{session, messages[]}` mapped to `Message[]` |
| `POST` | `/index-documents` | multipart `files` + `session_id` | `{chunk_count, documents?}` (max 20 files, 25MB each; `.pdf/.txt/.md/.markdown/.pptx`) |
| `POST` | `/feedback` | `{session_id, message_id, rating, comment?}` | `{ok}` (best-effort) |
| `GET` | `/health` | — | polled every 30s by `ConnectionDot` |

Chat is `POST /chat` (`{message, session_id, reasoning}`) streaming
`text/event-stream` events (parsed in `streamChat`, `src/lib/api.ts`):

| Event | Payload | UI effect |
|---|---|---|
| `stage` | `{stage: starting\|retrieving\|thinking\|writing}` | status line before first token |
| `metadata` | `{session_id, retrieval{depth,confidence,strategy}, sources[]}` | retrieval badge + sources |
| `token` | `{delta}` | appended to 80ms-batched buffer (`use-chat.ts`) |
| `reasoning` | `{reasoning}` | `ThinkingPanel` (auto-opens while active) |
| `reward` | `{reward, latency_ms}` | mono metadata row |
| `followups` | `{questions[]}` | follow-up buttons |
| `done` | `{session_id, message_id}` | renames temp id → server id, clears `isStreaming` |
| `error` | `{message}` | appended as blockquote, toast |

## Component map

```text
src/
├── app/
│   ├── layout.tsx          # Inter only, MotionConfig reducedMotion=user, Tooltip+Toast
│   ├── page.tsx            # flat landing (nav h-14, centered hero, bordered cards)
│   ├── chat/page.tsx       # boot (getMe → sessions), desktop sidebar + mobile drawer
│   └── globals.css         # midnight tokens, thin scrollbars, .offscreen-msg, .shadow-subtle
├── components/
│   ├── chat/               # chat-area, message-list, user/assistant-message,
│   │                       # markdown-renderer (dynamic ssr:false), thinking-panel,
│   │                       # message-actions, empty-state, typing-indicator, connection-dot
│   ├── composer/           # input-composer (pill 24px, Fast/Deep segmented, debounced drafts),
│   │                       # suggestion-chips (Lucide grid, no emoji)
│   ├── sidebar/            # sidebar (x-transform drawer), header/nav/search/conversations/footer
│   ├── auth/auth-gate.tsx  # split branding + form, min-h-dvh, 16px inputs (no iOS zoom)
│   └── ui/                 # Radix dialog/dropdown/tooltip, button (ghost→secondary hover), toast
├── hooks/use-chat.ts       # SSE buffers + rAF flush, abort/stop, editAndResend, regenerate
├── hooks/use-keyboard.ts   # sidebar toggle + focus-composer shortcuts (⌘K in search)
├── lib/api.ts              # TOKEN_KEY, singleflight refresh, authFetch 401→refresh→retry
└── lib/motion.ts           # shared presets (durations micro 0.15 / base 0.25 / entrance 0.4)
```

State flow: `InputComposer.onSend → useChat.sendMessage → streamChat onEvent →
buffersRef → scheduleFlush(80ms) → MessageList rAF scrollTo (only if pinned) →
AssistantMessage plain-text while streaming → MarkdownRenderer on done`.

Drafts persist per session (`ragnostic_draft_<sessionId|new>`, 300ms debounce).

## Styling / motion conventions

- Tokens in `globals.css` (`--background/foreground/card/border`, `--radius 0.85rem`); never hardcode `#16162a`-style surfaces — use `bg-card/bg-secondary/border`.
- `font-sans` = Inter everywhere; `mono-meta` class for depth/confidence/latency/timestamps.
- Elevation = `shadow-subtle` only; no `shadow-accent/*`, `glow-orb`, `bg-grid`, or gradient text in chat/auth paths (those utilities remain deprecated in CSS for landing compat).
- Motion: fade `0.15–0.4s`, no stagger on history (animate last message only), sidebar via `x` transform (never `width`), `AnimatePresence mode="wait"` avoided in composer, `prefers-reduced-motion` respected globally.
- Touch: hover-reveal actions use `[@media(hover:hover)]:opacity-0 ...` so they stay visible on touch; tap targets `h-8` minimum (`h-9` for icon buttons); inputs `text-base` on mobile to prevent iOS zoom.

## Performance notes

- `MessageList` windows to last 60 (`WINDOW_SIZE`); rows are `React.memo` + `content-visibility:auto` (`.offscreen-msg`); streaming renders plain text, full GFM only on `done` (throttled 150ms).
- `MarkdownRenderer` is `next/dynamic ssr:false` with a skeleton fallback; `highlight.js` `github-dark.css` is overridden to `bg-secondary/60` so code matches the theme.
- `next.config.ts`: `compress`, `optimizePackageImports: [lucide-react, framer-motion]`, production `removeConsole`.
- Sidebar search uses `useDeferredValue`; composer drafts debounce `localStorage`; `ConnectionDot` polls `/health` every 30s (4s timeout).

## Responsive / accessibility

- `h-dvh` + `env(safe-area-inset-*)` on drawer/composer/footer; composer is `sticky bottom-0` in normal flow (never `absolute`), so the iOS keyboard doesn't cover it.
- Topbar is `grid [1fr_auto_1fr]` so the title doesn't jump when the sidebar toggle mounts.
- Tables get `-mx-1 overflow-x-auto min-w-[480px]`; user bubbles `max-w-[85%] sm:max-w-[70%]`.
- `role=log aria-live=polite` on the list, `aria-label` on icon buttons, `focus-visible:ring-2 ring-foreground/15`, `MotionConfig reducedMotion=user`.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Could not open a chat — is the backend running?` | `POST /sessions` failed (CORS/backend down) | Check `NEXT_PUBLIC_API_BASE_URL`, `server/.env` `FRONTEND_ORIGIN` |
| `Uploaded N files but 0 chunks indexed` | Empty/unparseable files | Re-export PDFs with selectable text; stick to supported extensions |
| Stream stalls in background tab | `requestAnimationFrame` throttled | Buffers flush via `setTimeout(80ms)` fallback — switch back to tab; content finalizes on `done` |
| Draft from another chat appears | `sessionId` null at mount | Draft key is `ragnostic_draft_new` until the lazy session resolves — expected |
| `Jump to latest` stuck visible | Unpinned (`distance > 400`) | Click it or scroll to bottom; auto-scroll resumes only while pinned |
