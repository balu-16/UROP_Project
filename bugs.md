# RAGnostic Codebase - Bug Report & Analysis

## Table of Contents
1. [Critical Bugs](#1-critical-bugs)
2. [Security Issues](#2-security-issues)
3. [Logic Errors](#3-logic-errors)
4. [Dead / Duplicate Code](#4-dead--duplicate-code)
5. [Backend Bugs](#5-backend-bugs)
6. [Frontend Bugs](#6-frontend-bugs)
7. [Performance Issues](#7-performance-issues)
8. [Configuration & Setup Issues](#8-configuration--setup-issues)
9. [Improvements](#9-improvements)

---

## 1. Critical Bugs

### 1.1 Double Bandit Update — Conflicting Reward Signals
**Files:** `backend/app/services/chat.py` (line ~117), `backend/app/api/observability.py` (line ~52)

The LinUCB bandit is updated **twice** per chat interaction:
- **First:** Automatically in `ChatService.stream()` with the auto-computed reward from `RewardEvaluator`.
- **Second:** When the user submits explicit feedback via the `/feedback` endpoint.

```python
# chat.py — automatic update (always runs)
self.bandit.update(selected_arm, feature_payload["vector"], reward["reward"])

# observability.py — explicit user feedback update
state.bandit.update(message["selected_arm"], retrieval_log.get("feature_vector", [0] * 7), payload.rating)
```

**Impact:** The bandit receives two conflicting reward signals for the same context, destabilizing learning. The automatic update may train on a poor reward before the user has a chance to give feedback. Either the automatic update should be removed (relying solely on user feedback), or the feedback endpoint should not update the bandit.

---

### 1.2 No User-Level Data Isolation in Vector Store
**File:** `backend/app/retrieval/strategies.py` (line ~38)

The `VectorStore` is a global singleton. All users' document chunks are stored in the same FAISS index. When `prefetch()` searches, it queries the entire index without filtering by `user_id`:

```python
async def prefetch(self, query: str) -> tuple[np.ndarray, list[dict[str, Any]]]:
    vector = await self.embeddings.embed_query(query)
    return vector, self.vector_store.search(vector, self.settings.retrieval_top_k)
```

**Impact:** User A can retrieve and see chunks from User B's documents. This is a significant privacy/security issue. The search should filter results by the requesting user's ID.

---

### 1.3 AbortError Displays Confusing "Backend error" Message
**File:** `frontend/src/hooks/use-chat.ts` (line ~88)

When the user clicks "Stop" during streaming, the `AbortController.abort()` triggers an `AbortError`. This is caught by the generic error handler and displayed as a "Backend error":

```typescript
catch (error) {
    const message = error instanceof Error ? error.message : "Streaming failed";
    setMessages((prev) =>
      prev.map((msg) =>
        msg.id === assistantId ? { ...msg, content: `Backend error: ${message}` } : msg,
      ),
    );
}
```

**Impact:** The user sees "Backend error: The operation was aborted." when they intentionally stop generation. Should check for `error.name === "AbortError"` and handle it silently.

---

## 2. Security Issues

### 2.1 No Limit on File Upload Count Per Request
**File:** `backend/app/api/ingestion.py` (line ~8)

```python
@router.post("/index-documents")
async def index_documents(
    files: list[UploadFile] = File(...),
    ...
):
```

There is no upper bound on `files`. A malicious user could upload thousands of files in a single request, consuming server resources and potentially causing a denial of service.

---

### 2.2 CORS Allows All Methods and Headers
**File:** `backend/app/main.py` (line ~64)

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Allowing all HTTP methods (`DELETE`, `PUT`, `PATCH`, etc.) and all headers is overly permissive. Should be restricted to `GET`, `POST`, `OPTIONS` and the specific headers needed.

---

### 2.3 Internal Feature Vectors Exposed to Client
**File:** `backend/app/services/chat.py` (line ~89)

The `metadata` SSE event sends the full feature payload, arm scores, and retrieval diagnostics to the frontend:

```python
metadata = {
    ...
    "arm_scores": arm_scores,
    "features": feature_payload,
    "retrieval": retrieval_payload["diagnostics"],
    ...
}
yield sse_event("metadata", metadata)
```

**Impact:** Exposes internal ML feature vectors, bandit arm scores, and retrieval internals to the client. Should be gated behind a `debug` flag.

---

### 2.4 Refresh Token Doesn't Invalidate Existing Access Tokens
**File:** `backend/app/services/auth.py` (line ~107)

When a refresh token is used, the old session is revoked and a new one is created. However, the old JWT access token remains valid until its natural expiration. There is no token blacklist. A stolen access token cannot be revoked.

---

### 2.5 Rate Limiter Doesn't Exclude Public Config Endpoint
**File:** `backend/app/main.py` (line ~70)

```python
if request.url.path not in {"/health"}:
    await limiter.check(request)
```

Only `/health` is excluded. The `/app-config` endpoint (also unauthenticated) is rate-limited, which could be an issue if the frontend polls it frequently.

---

## 3. Logic Errors

### 3.1 `MemoryCursor.sort()` Crashes on `None` Values
**File:** `backend/app/database/memory.py` (line ~58)

```python
def sort(self, key: str, direction: int):
    reverse = direction < 0
    self.documents.sort(key=lambda item: item.get(key), reverse=reverse)
    return self
```

If any document has `None` for the sort key (or the key is missing), Python 3 raises `TypeError: '<' not supported between instances of 'NoneType' and 'datetime.datetime'`. This can happen when sorting messages by `created_at` if any message is missing the field.

---

### 3.2 `MemoryCollection.create_index()` Doesn't Enforce Uniqueness
**File:** `backend/app/database/memory.py` (line ~97)

```python
async def create_index(self, keys, unique: bool = False):
    self.indexes.append((keys, unique))
    return f"{self.name}_{len(self.indexes)}"
```

The index is recorded but never enforced. `insert_one()` doesn't check for duplicate values when `unique=True`. The `users` collection relies on a unique index on `email`, but duplicate emails can be inserted in the in-memory backend.

---

### 3.3 `MemoryCollection._apply_update()` Doesn't Handle Nested Keys
**File:** `backend/app/database/memory.py` (line ~37)

```python
def _apply_update(document: dict[str, Any], update: dict[str, Any]) -> None:
    if "$set" in update:
        document.update(update["$set"])
```

This performs a shallow `dict.update()`. MongoDB-style nested keys like `"$set": {"metadata.status": "active"}` would create a literal key `"metadata.status"` instead of updating the nested field. This differs from real MongoDB behavior.

---

### 3.4 `ContextBuilder` Never Uses `chunk_min_tokens` Setting
**File:** `backend/app/services/context.py`, `backend/app/config/settings.py`

The settings define `chunk_min_tokens: int = 400`, but this value is never used anywhere in the codebase. Chunks shorter than this threshold are not filtered out, potentially including very short/low-quality chunks in the context.

---

### 3.5 `EntityGraph.expand_chunks()` Has No Limit on Returned Chunks
**File:** `backend/app/graph/entity_graph.py` (line ~65)

```python
def expand_chunks(self, seed_chunk_ids: list[str], hops: int, max_entities: int = 40) -> dict[str, Any]:
```

`max_entities` limits entities explored per hop, but there's no cap on the total number of returned `chunk_ids`. For a dense entity graph, this could return thousands of chunk IDs, overwhelming the context builder.

---

### 3.6 `sessions.get_or_create()` Silently Creates New Session on Invalid ID
**File:** `backend/app/services/sessions.py` (line ~21)

```python
async def get_or_create(self, user_id: str, session_id: str | None, first_message: str) -> dict:
    if session_id:
        session = await self.db.collection("chat_sessions").find_one({"_id": session_id, "user_id": user_id})
        if session:
            return session
    title = first_message.strip().splitlines()[0][:80] or "New chat"
    return await self.create(user_id, title)
```

If a `session_id` is provided but doesn't exist (or belongs to another user), a new session is silently created. The user expects to append to an existing conversation but gets a new one. This should return an error or at least notify the client.

---

### 3.7 `FeatureExtractor` Penalizes Short Queries Unfairly
**File:** `backend/app/services/features.py` (line ~22)

```python
ambiguity = min(1.0, query.count(" or ") * 0.2 + (0.3 if len(tokens) < 5 else 0.0) + (0.3 if confidence < 0.35 else 0.0))
```

A query like "What is X?" (4 tokens) gets 0.3 ambiguity just for being short. Combined with low retrieval confidence, it could reach 0.6 ambiguity even if the query is perfectly clear. Short, precise queries are unfairly penalized.

---

### 3.8 `RewardEvaluator` Faithfulness Metric Is Flawed
**File:** `backend/app/evaluation/reward.py` (line ~22)

```python
answer_terms = set(answer.lower().split())
context_terms = set()
for chunk in chunks:
    context_terms.update(chunk.get("text", "").lower().split())
overlap = len(answer_terms & context_terms) / max(1, len(answer_terms))
```

This measures word overlap between the answer and context. Common stop words ("the", "is", "and", "a") always overlap, inflating the faithfulness score. A hallucinated answer using common English words would score high on faithfulness. Should use a more robust metric (e.g., ROUGE-L, BERTScore, or LLM-based evaluation).

---

### 3.9 Embedding Cache Is Not Keyed by Model
**File:** `backend/app/embeddings/service.py` (line ~31)

```python
def _cache_key(self, text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
```

The cache key is a hash of the text only, not the model name. If the embedding model changes (e.g., from `bge-large-en-v1.5` to a different model), cached vectors from the old model are still served. This leads to inconsistent embeddings and broken similarity search.

---

### 3.10 Bandit Matrix Can Become Singular
**File:** `backend/app/bandit/linucb.py` (line ~47)

```python
a_inv = np.linalg.inv(state.a)
```

After many updates with correlated features, the `A` matrix can become singular or ill-conditioned, causing `np.linalg.inv()` to raise `LinAlgError`. Should use `np.linalg.solve()` or add regularization.

---

### 3.11 Failed Chat Still Saves Empty/Partial Message to Database
**File:** `backend/app/services/chat.py` (line ~120)

```python
except Exception as exc:
    yield sse_event("error", {"message": str(exc)})
answer = "".join(answer_parts).strip()
# ... continues to save assistant_message with potentially empty content
await self.db.collection("messages").insert_one(assistant_message)
```

If the LLM call fails before any tokens are generated, an empty answer is saved to the database. When the user loads chat history, they'll see an empty assistant message.

---

## 4. Dead / Duplicate Code

### 4.1 `globals.css` Has Duplicate `@layer base` Blocks
**File:** `frontend/src/app/globals.css`

```css
@layer base {
  * {
    border-color: hsl(var(--border));
  }
  body {
    background-color: hsl(var(--background));
    color: hsl(var(--foreground));
    ...
  }
}

@layer base {
  * {
    @apply border-border;
  }
  body {
    @apply bg-background text-foreground;
  }
}
```

Two `@layer base` blocks with overlapping rules. The first sets `border-color`, `background-color`, and `color` explicitly. The second uses `@apply` to set the same properties. The second block's `@apply border-border` duplicates the first block's `border-color` rule.

---

### 4.2 `mock-data.ts` Is Never Imported
**File:** `frontend/src/lib/mock-data.ts`

Exports `mockConversations` and `demoStreamingResponse`, but neither is imported anywhere in the codebase. Entirely dead code.

---

### 4.3 `streaming.ts` Is Never Imported
**File:** `frontend/src/lib/streaming.ts`

Exports `fakeStream()`, but it's never imported anywhere. Dead code.

---

### 4.4 `MobileSidebar` Component Returns Null
**File:** `frontend/src/components/sidebar/sidebar.tsx` (line ~55)

```tsx
export function MobileSidebar({...}) {
  return null; // Handled by Dialog in layout
}
```

The component always returns `null` and is never used. The mobile sidebar is implemented via the `Dialog` component in `page.tsx`.

---

### 4.5 `clearMessages` Is Defined But Never Called
**File:** `frontend/src/hooks/use-chat.ts` (line ~97)

```typescript
const clearMessages = useCallback(() => {
    setMessages([]);
    setIsStreaming(false);
}, []);
```

Returned from the `useChat` hook but never called from any component.

---

### 4.6 Unused Imports in Frontend Components

**`frontend/src/components/composer/input-composer.tsx`:**
```tsx
import { Plus, ArrowUp, StopCircle, Mic, Paperclip } from "lucide-react";
```
`Paperclip` is imported but never used.

**`frontend/src/components/composer/suggestion-chips.tsx`:**
```tsx
import { ArrowUp, StopCircle } from "lucide-react";
```
Both `ArrowUp` and `StopCircle` are imported but never used.

---

### 4.7 Redundant Dependency Injection in `current_user`
**File:** `backend/app/api/dependencies.py` (line ~17)

```python
async def current_user(
    authorization: str | None = Header(default=None),
    auth: AuthService = Depends(get_auth_service),
    db: AppDatabase = Depends(get_db),
) -> dict:
```

Both `auth` and `db` are injected, but `get_auth_service` already depends on `get_db`. The `auth.db` already has the database reference. The `db` parameter is redundant.

---

### 4.8 Hardcoded Sidebar Navigation Items
**File:** `frontend/src/components/sidebar/sidebar-nav.tsx`

The sidebar contains hardcoded items like "Library", "Explore GPTs", "Codex", "ChatGPT Plus", "DALL·E", "Writebox", "Code Copilot", "Web App Redesign", "Mobile SDK". None of these do anything — they're placeholder/dead UI.

---

## 5. Backend Bugs

### 5.1 `openrouter.py` — Retry Without Backoff
**File:** `backend/app/services/openrouter.py` (line ~55)

```python
for attempt in range(3):
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            ...
    except Exception as exc:
        last_error = exc
        if attempt == 2:
            raise
```

Three immediate retries with no delay between attempts. This hammers the API during outages. Should use exponential backoff (e.g., 1s, 2s, 4s).

---

### 5.2 `openrouter.py` — New `httpx.AsyncClient` Created Per Retry
**File:** `backend/app/services/openrouter.py` (line ~57)

```python
for attempt in range(3):
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
```

A new HTTP client (with new connection pool) is created on each retry attempt. The client should be created once outside the retry loop.

---

### 5.3 `openrouter.py` — `json.loads` Can Fail on Malformed SSE Data
**File:** `backend/app/services/openrouter.py` (line ~71)

```python
data = json.loads(raw)
```

If the SSE stream delivers malformed or truncated JSON, `json.loads` raises `JSONDecodeError`. This triggers a full retry from scratch, losing all previously streamed content.

---

### 5.4 `VectorStore.add()` Saves to Disk on Every Call
**File:** `backend/app/vectorstore/faiss_store.py` (line ~68)

```python
self.metadata.extend(metadata)
self.save()
```

Every call to `add()` writes the entire FAISS index and metadata to disk. During ingestion of multiple documents, this causes repeated full-disk writes. Should batch saves or save only on shutdown/periodically.

---

### 5.5 `LinUCB.update()` Saves to Disk on Every Call
**File:** `backend/app/bandit/linucb.py` (line ~63)

```python
def update(self, arm: str, features: list[float], reward: float) -> None:
    ...
    self.save()
```

Combined with the double-update bug (#1.1), this means **two disk writes** per chat message. Should debounce or batch.

---

### 5.6 Entity Extraction Is Synchronous and Blocks Event Loop
**File:** `backend/app/services/ingestion.py` (line ~42)

```python
for chunk in chunks:
    entities = self.extractor.extract(chunk["text"])
```

spaCy NER is CPU-bound. Running it synchronously in an async handler blocks the event loop, preventing other requests from being processed during ingestion. Should use `asyncio.to_thread()`.

---

### 5.7 `chunking.py` — Infinite Loop Risk
**File:** `backend/app/services/chunking.py` (line ~20)

```python
while start < len(tokens):
    end = min(start + max_tokens, len(tokens))
    ...
    start = max(0, end - overlap)
```

If `overlap >= max_tokens`, then `end - overlap <= start`, and the loop never advances (infinite loop). Default settings (`chunk_max_tokens=500`, `chunk_overlap_tokens=80`) are safe, but there's no validation to prevent misconfiguration.

---

### 5.8 `chunking.py` — Token Counting Is Inaccurate
**File:** `backend/app/services/chunking.py` (line ~6)

```python
def count_tokens(text: str) -> int:
    return len(re.findall(r"\S+", text))
```

This counts whitespace-separated tokens, not actual LLM tokens. For non-English text, code, or special characters, this can be significantly inaccurate. Should use `tiktoken` or the model's tokenizer.

---

### 5.9 Expired Sessions Are Never Cleaned Up
**File:** `backend/app/services/auth.py`

The `refresh()` method checks if a session is expired but doesn't delete it:

```python
if not session or session["expires_at"] < utc_now():
    raise HTTPException(...)
```

Old expired sessions accumulate in the database indefinitely. Should add a periodic cleanup job or delete on encounter.

---

### 5.10 `context.py` — Retrieval Scores Exposed in LLM Prompt
**File:** `backend/app/services/context.py` (line ~18)

```python
context = "\n\n".join(
    f"[{index + 1}] source={...} score={chunk.get('score', 0):.3f}\n{chunk.get('text', '')}"
    ...
)
```

Internal retrieval scores are included in the context sent to the LLM. This is an implementation detail that shouldn't be in the prompt — it can confuse the model or bias its responses.

---

### 5.11 `entity_extraction.py` — Regex Fallback Misses Common Entity Patterns
**File:** `backend/app/services/entity_extraction.py` (line ~28)

```python
for match in re.finditer(r"\b(?:[A-Z][a-z0-9]+(?:\s+[A-Z][a-z0-9]+){0,3})\b", text):
```

The regex only matches Title Case words. It misses:
- All-caps acronyms: "NASA", "FBI", "GPT"
- Mixed case: "iPhone", "macOS", "GitHub"
- Unicode names: "Schrödinger", "Müller"

---

### 5.12 `utils/ids.py` — UUID4 Is Not Sortable
**File:** `backend/app/utils/ids.py`

```python
def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"
```

UUID4 is random, so IDs are not chronologically sortable. Database queries that sort by `_id` won't return results in insertion order. Consider UUID7 or ULID for time-ordered IDs.

---

### 5.13 `LinUCB` — History Append + Save on Every Update
**File:** `backend/app/bandit/linucb.py` (line ~63)

```python
self.history.append({"arm": arm, "features": features, "reward": reward})
self.save()
```

The history list grows unbounded in memory between saves. The save function trims to 1000 entries, but between saves, the list can grow much larger in high-traffic scenarios.

---

## 6. Frontend Bugs

### 6.1 Hardcoded Username "Rakesh" in Empty State
**File:** `frontend/src/components/chat/empty-state.tsx` (line ~7)

```tsx
export function EmptyState({ userName = "Rakesh" }: EmptyStateProps) {
```

The default username is hardcoded as "Rakesh". The component is called without props in `chat-area.tsx`:
```tsx
<EmptyState />
```

**Impact:** Every user sees "Hey, Rakesh." regardless of who is logged in. Should pass the actual user name.

---

### 6.2 Metadata Title Says "ChatGPT" Instead of "RAGnostic"
**File:** `frontend/src/app/layout.tsx` (line ~10)

```tsx
export const metadata: Metadata = {
  title: "ChatGPT",
  description: "A premium ChatGPT-inspired AI chatbot",
};
```

---

### 6.3 Input Composer Disclaimer Says "ChatGPT"
**File:** `frontend/src/components/composer/input-composer.tsx` (line ~140)

```tsx
<p className="text-center text-[11px] text-foreground/25 mt-2 select-none">
  ChatGPT can make mistakes. Check important info.
</p>
```

Should say "RAGnostic" instead of "ChatGPT".

---

### 6.4 Thumbs Up/Down Feedback Never Sent to Backend
**File:** `frontend/src/components/chat/message-actions.tsx` (line ~14)

```tsx
const [liked, setLiked] = useState<boolean | null>(null);
```

The thumbs up/down buttons toggle local React state but never call the backend `/feedback` endpoint. User feedback is lost on page refresh and never influences the bandit.

---

### 6.5 `streamChat` Doesn't Handle Non-JSON SSE Data
**File:** `frontend/src/lib/api.ts` (line ~107)

```typescript
onEvent(event, JSON.parse(dataLine));
```

If `dataLine` is not valid JSON, `JSON.parse` throws an unhandled exception, breaking the stream. Should wrap in try-catch.

---

### 6.6 `Regenerate` Button Has No Implementation
**File:** `frontend/src/components/chat/chat-area.tsx` (line ~91)

```tsx
<MessageList
    messages={messages}
    isStreaming={isStreaming}
    onRegenerate={() => {
        /* regenerate last assistant message */
    }}
/>
```

The regenerate handler is an empty function.

---

### 6.7 Session Grouping Uses Milliseconds Instead of Calendar Dates
**File:** `frontend/src/app/page.tsx` (line ~17)

```typescript
const diffDays = Math.floor((now.getTime() - updated.getTime()) / 86400000);
```

This calculates day difference as raw milliseconds. Near midnight, a session updated at 11:59 PM could be grouped as "Today" while one at 12:01 AM (1 minute later) could be "Yesterday", or vice versa depending on timezone. Should compare calendar dates in the user's local timezone.

---

### 6.8 `button.tsx` Missing `"use client"` Directive
**File:** `frontend/src/components/ui/button.tsx`

All other component files include `"use client"` at the top, but `button.tsx` does not. While it may work as-is (React.forwardRef is compatible with server components in some contexts), it's inconsistent and could cause issues with certain bundler configurations.

---

## 7. Performance Issues

### 7.1 `VectorStore.add()` Writes to Disk on Every Insert
Already covered in #5.4. During document ingestion, the FAISS index and metadata JSON are written to disk after every batch of chunks, causing significant I/O overhead.

---

### 7.2 `EntityExtractor.extract()` Runs Synchronously in Async Context
Already covered in #5.6. spaCy NER is CPU-bound and blocks the event loop.

---

### 7.3 `MemoryCollection` Is O(n) for All Operations
**File:** `backend/app/database/memory.py`

The in-memory database uses a flat list for all collections. `find_one()`, `find()`, `update_one()`, and `delete_one()` are all O(n) where n is the number of documents. For large datasets, this becomes a bottleneck. Should use dictionaries indexed by `_id` for O(1) lookups.

---

### 7.4 `openrouter.py` — New HTTP Client Per Retry
Already covered in #5.2. Connection pooling is lost between retry attempts.

---

## 8. Configuration & Setup Issues

### 8.1 `@lru_cache` on `get_settings` Prevents Hot Reload
**File:** `backend/app/config/settings.py` (line ~60)

```python
@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Settings are cached after the first call. In development with `uvicorn --reload`, environment variable changes won't be picked up until the process restarts. The test file works around this with `get_settings.cache_clear()`.

---

### 8.2 Dockerfile Runs `main:app` — Not `app.main:app`
**File:** `backend/Dockerfile` (line ~13)

```dockerfile
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

This references `backend/main.py` which does `from app.main import app`. This works, but it's an unnecessary indirection. Could reference `app.main:app` directly.

---

### 8.3 `docker-compose.yml` Only Defines Backend Service
**File:** `backend/docker-compose.yml`

The frontend is not included in the Docker Compose configuration. A full-stack deployment would need a separate compose file or manual frontend setup.

---

### 8.4 No `.env.example` File
There is no `.env.example` or `.env.template` file documenting the required environment variables. New developers have to read `settings.py` to discover what variables are needed.

---

### 8.5 JWT Secret Has a Default Value
**File:** `backend/app/config/settings.py` (line ~22)

```python
jwt_secret: str = "change-this-local-development-secret"
```

If the `.env` file is missing or the variable isn't set, the application runs with a known secret. Should require the secret to be explicitly set in non-local environments.

---

## 9. Improvements

### 9.1 Add Exponential Backoff to OpenRouter Retries
Replace immediate retries with exponential backoff:
```python
import asyncio

for attempt in range(3):
    try:
        ...
        return
    except Exception as exc:
        last_error = exc
        if attempt < 2:
            await asyncio.sleep(2 ** attempt)  # 1s, 2s
```

---

### 9.2 Debounce or Batch Disk Writes
`VectorStore.save()`, `LinUCB.save()`, and `EntityGraph.save()` are called on every update. Consider:
- Saving only on shutdown (via lifespan)
- Debouncing with a timer (e.g., save at most once per 30 seconds)
- Batching writes

---

### 9.3 Use `tiktoken` for Accurate Token Counting
Replace the whitespace-based `count_tokens()` with OpenAI's `tiktoken` library for accurate token counts that match LLM tokenization.

---

### 9.4 Add Pagination to Sessions API
The backend returns at most 100 sessions, but there's no pagination. For power users with many sessions, add cursor-based pagination.

---

### 9.5 Implement User-Level Vector Store Filtering
Add a `user_id` filter to the vector store search to prevent cross-user data leakage. Options:
- Store `user_id` in metadata and filter results post-search
- Use separate FAISS indexes per user (for small user counts)
- Add a pre-filter step before similarity search

---

### 9.6 Add Proper Error Boundaries in Frontend
The frontend has no React error boundaries. If a component throws during render, the entire app crashes. Add error boundaries around the chat area and sidebar.

---

### 9.7 Implement Session Expiry Cleanup
Add a periodic task (or clean up on login) that deletes expired sessions from the database:
```python
await db.collection("sessions").delete_many({"expires_at": {"$lt": utc_now()}})
```

---

### 9.8 Use UUID7 or ULID for Sortable IDs
Replace `uuid4().hex` with UUID7 or ULID for time-ordered IDs that enable efficient chronological sorting in database queries.

---

### 9.9 Add Input Validation for `chunk_overlap` and `chunk_max_tokens`
Validate that `chunk_overlap_tokens < chunk_max_tokens` at startup to prevent the infinite loop bug (#5.7).

---

### 9.10 Connect Frontend Feedback to Backend
Wire up the thumbs up/down buttons in `message-actions.tsx` to call the `/feedback` API endpoint. This is the primary mechanism for the contextual bandit to learn from user preferences, and it's completely disconnected.

---

### 9.11 Add `"use client"` to `button.tsx`
For consistency and to prevent potential SSR issues, add the `"use client"` directive.

---

### 9.12 Pass User Name to `EmptyState` Component
```tsx
// In chat-area.tsx, accept user prop and pass it:
<EmptyState userName={user.name} />
```

---

### 9.13 Remove Dead Code
Delete the following unused files:
- `frontend/src/lib/mock-data.ts`
- `frontend/src/lib/streaming.ts`

Remove the unused `MobileSidebar` component from `sidebar.tsx`.

---

### 9.14 Add `.env.example` File
Create a `.env.example` with all required environment variables and their descriptions:
```env
# Backend
MONGODB_URL=memory://ragnostic
MONGODB_DB_NAME=ragnostic
OPENROUTER_API_KEY=
OPENROUTER_MODEL=moonshotai/kimi-k2.6:free
JWT_SECRET=
STORAGE_DIR=storage

# Frontend
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

---

### 9.15 Consolidate Duplicate CSS in `globals.css`
Merge the two `@layer base` blocks into one, removing redundant declarations.

---

### 9.16 Add Health Check to Frontend Docker Setup
The `docker-compose.yml` only has a backend health check. Add a frontend service with its own health check for full-stack monitoring.

---

### 9.17 `openrouter.py` — Reuse HTTP Client
Create the `httpx.AsyncClient` once (e.g., in `__init__` or `startup`) and reuse it across requests, rather than creating a new one per call.

---

### 9.18 Add Rate Limiting Info to Response Headers
Return `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers so clients can handle rate limiting gracefully.

---

### 9.19 Use Regularization in LinUCB
Add a small regularization term to prevent matrix singularity:
```python
state.a += np.outer(x, x) + 1e-6 * np.eye(self.dimension)
```

---

### 9.20 Add CORS Preflight Caching
Add `max_age` to the CORS middleware to cache preflight responses:
```python
app.add_middleware(
    CORSMiddleware,
    ...
    max_age=600,
)
```
