# RAGnostic Codebase — Complete Bug & Error Analysis

> **Generated from a deep, line-by-line review of every source file.**
> The existing `bugs.md` is **outdated** — many items it lists have already been fixed in the current code. This document reflects the **actual current state** of the codebase.

---

## Table of Contents

1. [Critical Bugs](#1-critical-bugs)
2. [Security Issues](#2-security-issues)
3. [Logic Errors](#3-logic-errors)
4. [Frontend Bugs](#4-frontend-bugs)
5. [Data Integrity Issues](#5-data-integrity-issues)
6. [Performance Issues](#6-performance-issues)
7. [Configuration & Deployment Issues](#7-configuration--deployment-issues)
8. [Dead Code & Cleanup](#8-dead-code--cleanup)
9. [Improvements](#9-improvements)

---

## 1. Critical Bugs

### 1.1 Thumbs-Down Sends Rating of `-1` — Violates Backend Schema
**File:** `frontend/src/components/chat/message-actions.tsx` (L48)
**File:** `backend/app/models/schemas.py` (L39)

```tsx
// message-actions.tsx
await sendFeedback(sessionId, messageId, newLiked ? 1 : -1);
```

```python
# schemas.py
class FeedbackRequest(BaseModel):
    rating: float = Field(ge=0.0, le=1.0)  # Only allows 0.0 to 1.0
```

The frontend sends `-1` for a thumbs-down, but the Pydantic model validates `ge=0.0, le=1.0`. This means every thumbs-down feedback will get a **422 validation error** from the backend. User dislike feedback is never recorded.

**Fix:** Change the frontend to send `0` for dislike (or change the schema to accept `-1` to `1`).

---

### 1.2 No User-Level Data Isolation in Vector Store
**File:** `backend/app/retrieval/strategies.py` (L38)

```python
async def prefetch(self, query: str) -> tuple[np.ndarray, list[dict[str, Any]]]:
    vector = await self.embeddings.embed_query(query)
    return vector, self.vector_store.search(vector, self.settings.retrieval_top_k)
```

The `VectorStore` is a global singleton. All users' document chunks are stored in the same FAISS index. When `prefetch()` searches, it queries the entire index without filtering by `user_id`.

**Impact:** User A can retrieve and see chunks from User B's documents. This is a **privacy/security vulnerability**.

**Fix:** Filter results by the requesting user's ID after the search (or before, using metadata filtering).

---

### 1.3 MemoryCollection Missing `delete_many()` Method
**File:** `backend/app/database/memory.py`
**File:** `backend/app/services/sessions.py` (L59)

```python
# sessions.py
result = await self.db.collection("chat_sessions").delete_many(
    {"updated_at": {"$lt": cutoff}}
)
```

The `MemoryCollection` class only implements `delete_one()`, not `delete_many()`. When using the in-memory database (`memory://` URL), calling `delete_many()` will raise `AttributeError`. This breaks the `cleanup_expired()` method and any future code that uses `delete_many()`.

**Impact:** Session cleanup crashes at runtime when using the in-memory database (which is the default and what tests use).

**Fix:** Add a `delete_many()` method to `MemoryCollection`:
```python
async def delete_many(self, query: dict[str, Any]):
    original_count = len(self.documents)
    self.documents = [doc for doc in self.documents if not _matches(doc, query)]
    deleted = original_count - len(self.documents)
    for doc in [d for d in self.documents if "_id" in d]:
        self._id_index[doc["_id"]] = doc
    return DeleteResult(deleted)
```

---

### 1.4 MemoryCollection Unique Index Not Enforced on `insert_one()`
**File:** `backend/app/database/memory.py` (L121)

```python
async def insert_one(self, document: dict[str, Any]):
    stored = copy.deepcopy(document)
    # ... no unique index check ...
    self.documents.append(stored)
```

When `create_index(keys, unique=True)` is called, the index metadata is stored but **never checked** during `insert_one()`. The `users` collection relies on a unique index on `email`, but in the in-memory backend, duplicate emails can be inserted without error.

**Impact:** Signup can create multiple users with the same email when using the in-memory database.

**Fix:** Add uniqueness validation in `insert_one()`:
```python
for keys, unique in self.indexes:
    if not unique:
        continue
    key_list = [keys] if isinstance(keys, str) else keys
    query = {k: stored.get(k) for k in key_list}
    if any(_matches(doc, query) for doc in self.documents):
        raise ValueError(f"Duplicate key for index on {key_list}")
```

---

### 1.5 `MemoryCursor.sort()` Crashes on Mixed `None` and Datetime Values
**File:** `backend/app/database/memory.py` (L67)

```python
def sort(self, key: str, direction: int):
    reverse = direction < 0
    self.documents.sort(
        key=lambda item: (item.get(key) is None, item.get(key)), reverse=reverse
    )
```

The tuple `(item.get(key) is None, item.get(key))` tries to compare `datetime` objects when `reverse=True`. Python 3 cannot compare `datetime` with `NoneType` using `<`. If any document is missing the sort key, the second element of the tuple is `None`, and comparing `(False, None)` with `(False, datetime(...))` raises `TypeError`.

**Fix:** Use a sentinel value:
```python
def sort(self, key: str, direction: int):
    reverse = direction < 0
    sentinel = datetime.min if not reverse else datetime.max
    self.documents.sort(
        key=lambda item: item.get(key) or sentinel,
        reverse=reverse,
    )
```

---

## 2. Security Issues

### 2.1 No User Filtering on Retrieval — Cross-User Data Leakage
**File:** `backend/app/retrieval/strategies.py` (L38)

Same as 1.2. User A's queries can return User B's document chunks.

---

### 2.2 `/app-config` Endpoint Leaks Internal Configuration
**File:** `backend/app/api/observability.py` (L14)

```python
@router.get("/app-config")
async def app_config():
    return {
        "name": "RAGnostic",
        "model": "moonshotai/kimi-k2.6:free",
        "features": ["adaptive-retrieval", "graph-rag", "streaming", "contextual-bandits"],
    }
```

This endpoint is **unauthenticated** (no `Depends(current_user)`) and exposes the LLM model name and feature flags. An attacker can use this to fingerprint the system and target known vulnerabilities.

**Fix:** Either authenticate this endpoint or remove sensitive details.

---

### 2.3 JWT Secret Has a Weak Default Value
**File:** `backend/app/config/settings.py` (L22)

```python
jwt_secret: str = "change-this-local-development-secret"
```

If the `.env` file is missing, the app runs with a publicly known secret. Anyone can forge valid JWT tokens.

**Fix:** Require the secret to be explicitly set in production, or generate a random one at startup if not provided.

---

### 2.4 Rate Limiter Memory Leak — Unbounded Growth
**File:** `backend/app/utils/rate_limit.py` (L10)

```python
class InMemoryRateLimiter:
    def __init__(self, limit_per_minute: int):
        self.events: dict[str, deque[float]] = defaultdict(deque)
```

The `events` dictionary grows unboundedly. Every unique client IP gets an entry that is **never cleaned up**. Over time, this consumes increasing memory.

**Fix:** Add periodic cleanup of stale entries, or use an LRU cache with a max size.

---

## 3. Logic Errors

### 3.1 `ContextBuilder.build()` Iterates All Chunks Even After Budget Exhausted
**File:** `backend/app/services/context.py` (L18)

```python
for chunk in sorted(chunks, key=lambda item: item.get("score", 0), reverse=True):
    ...
    if token_count + tokens > self.settings.max_context_tokens:
        continue  # Skips this chunk but keeps iterating
```

When the token budget is exceeded, the code uses `continue` instead of `break`. It keeps iterating through all remaining chunks (potentially thousands) even though none can be added. This wastes CPU time.

**Fix:** Replace `continue` with `break` when the budget is exceeded.

---

### 3.2 `MemoryCollection.update_one()` Doesn't Enforce Unique Indexes
**File:** `backend/app/database/memory.py` (L140)

```python
async def update_one(self, query, update, upsert=False):
    for document in self.documents:
        if _matches(document, query):
            _apply_update(document, update)  # No unique index check
            return UpdateResult(1, 1)
```

When a document is updated, the new values are not validated against unique indexes. A user's email could be updated to one that already exists for another user.

---

### 3.3 `IngestionService` Doesn't Validate Empty Files
**File:** `backend/app/services/ingestion.py` (L38)

```python
text, metadata = await self.parser.parse_upload(file, self.settings.upload_max_mb)
```

If a user uploads an empty file (0 bytes), `text` will be `""`. The chunker will return 0 chunks, but a document record is still inserted into the database with `chunk_count: 0`. This pollutes the indexed documents list.

**Fix:** Skip files that produce empty text.

---

### 3.4 Source Text Truncated to 600 Chars Without Indication
**File:** `backend/app/services/chat.py` (L153)

```python
"text": chunk.get("text", "")[:600],
```

Source text is silently truncated to 600 characters. The frontend has no way to know if the text was truncated, which could confuse users who see incomplete source excerpts.

---

### 3.5 `RetrievalOrchestrator._graph_expand()` Creates New Dicts from Copies
**File:** `backend/app/retrieval/strategies.py` (L52)

```python
by_id = {item["chunk_id"]: dict(item) for item in self.vector_store.metadata}
```

This creates a **full copy** of all vector store metadata on every retrieval call. For large indexes (thousands of chunks), this is a significant memory and CPU overhead.

**Fix:** Use the metadata directly without copying, or build the lookup index once and update it incrementally.

---

### 3.6 `LinUCB.update()` Regularization Grows Over Time
**File:** `backend/app/bandit/linucb.py` (L76)

```python
state.a += np.outer(x, x) + 1e-6 * np.eye(self.dimension)
```

Every update adds `1e-6 * I` to the A matrix. After 1000 updates, the regularization is `0.001 * I`. After 1,000,000 updates, it's `1000 * I`, which completely drowns out the actual data. The regularization should be applied once at initialization, not on every update.

**Fix:** Initialize `a` with regularization:
```python
# In startup():
self.states[arm] = ArmState(
    a=np.eye(self.dimension, dtype="float64") * 1e-6,  # Regularize once
    b=np.zeros(self.dimension, dtype="float64"),
)
# In update(): remove the + 1e-6 * np.eye(...) term
state.a += np.outer(x, x)
```

---

### 3.7 `count_tokens()` Uses Word-Count Heuristic, Not Actual Token Count
**File:** `backend/app/services/chunking.py` (L7)

```python
def count_tokens(text: str) -> int:
    words = len(re.findall(r"\S+", text))
    return max(1, int(words * 1.3)) if words else 0
```

This counts whitespace-separated "words" and multiplies by 1.3. For code, URLs, CJK text, or special characters, this is wildly inaccurate. The `tiktoken` package is in `requirements.txt` but never used.

**Fix:** Use `tiktoken` for accurate token counting:
```python
import tiktoken
_encoder = tiktoken.get_encoding("cl100k_base")
def count_tokens(text: str) -> int:
    return len(_encoder.encode(text))
```

---

## 4. Frontend Bugs

### 4.1 `clearMessages` Is Returned But Never Used
**File:** `frontend/src/hooks/use-chat.ts` (L112)

```typescript
const clearMessages = useCallback(() => {
    setMessages([]);
    setIsStreaming(false);
}, []);
```

This function is defined and returned from `useChat` but never called from any component. It's dead code.

---

### 4.2 `useKeyboardShortcuts` — `onSendMessage` Callback Is Never Triggered
**File:** `frontend/src/components/chat/chat-area.tsx` (L42)

```typescript
useKeyboardShortcuts({
    onToggleSidebar,
    onSendMessage: () => {
        // Handled by textarea Enter key
    },
    onFocusComposer: handleFocusComposer,
});
```

The `onSendMessage` keyboard shortcut (Cmd/Ctrl+Enter) is registered but the handler is empty. The comment says "Handled by textarea Enter key", but the keyboard hook also fires on Cmd/Ctrl+Enter, which does nothing.

---

### 4.3 `SuggestionChips` Sends Labels, Not Meaningful Prompts
**File:** `frontend/src/components/composer/suggestion-chips.tsx` (L20)

```typescript
const chips = [
    { icon: "🎨", label: "Create an image" },
    { icon: "✏️", label: "Write or edit" },
    { icon: "🔍", label: "Look something up" },
];
```

Clicking a chip sends the literal label text (e.g., "Create an image") as the user's message. These are not meaningful prompts for a RAG system — they're generic ChatGPT-style suggestions that don't leverage the document retrieval capabilities.

---

### 4.4 `PanelLeftClose` Imported But Never Used
**File:** `frontend/src/components/chat/chat-area.tsx` (L3)

```typescript
import { PanelLeftClose, PanelLeft } from "lucide-react";
```

`PanelLeftClose` is imported but only `PanelLeft` is used in the JSX.

---

### 4.5 `authFetch` — Infinite Retry Loop on Persistent 401
**File:** `frontend/src/lib/api.ts` (L82)

```typescript
export async function authFetch(path, init, retry = true): Promise<Response> {
    ...
    if (response.status === 401 && retry) {
        await refreshToken();
        return authFetch(path, init, false);
    }
    return response;
}
```

If `refreshToken()` succeeds but the retried request still returns 401 (e.g., the new token is immediately invalid), the function returns the 401 response without handling it. The caller (`getMe`, `getSessions`, etc.) will then call `parseJson` which throws a generic error. The user sees "Request failed" with no indication that re-authentication is needed.

**Fix:** If the retry also returns 401, clear the token and redirect to login.

---

### 4.6 `loadSessions` Errors Silently Swallowed
**File:** `frontend/src/app/page.tsx` (L68)

```typescript
useEffect(() => {
    async function boot() {
        try {
            const me = await getMe();
            setUser(me);
            await loadSessions();  // If this fails, no catch
        } catch {
            setAccessToken(null);
        } finally {
            setLoadingAuth(false);
        }
    }
    boot();
}, [loadSessions]);
```

If `loadSessions()` throws (e.g., network error), the error propagates to the outer `catch`, which calls `setAccessToken(null)`. This logs the user out entirely, even though only the session list failed to load.

---

### 4.7 `AuthGate` Doesn't Validate Password Strength
**File:** `frontend/src/components/auth/auth-gate.tsx` (L24)

```tsx
<input
    value={password}
    onChange={(event) => setPassword(event.target.value)}
    placeholder="Password"
    type="password"
/>
```

No client-side validation. The backend requires `min_length=8`, but the frontend doesn't indicate this to the user. They'll only see the error after submitting.

---

## 5. Data Integrity Issues

### 5.1 Embedding Cache Can Serve Stale Vectors
**File:** `backend/app/embeddings/service.py` (L33)

The embedding cache is keyed by `model_name:text_hash`. If the model's weights are updated (e.g., a new version of `bge-large-en-v1.5`), cached vectors from the old version are still served. There's no cache invalidation mechanism.

**Fix:** Include a model version/hash in the cache key, or clear the cache when the model changes.

---

### 5.2 `VectorStore` Dimension Mismatch on Model Change
**File:** `backend/app/vectorstore/faiss_store.py` (L49)

```python
if self.index.d != vectors.shape[1]:
    self.dimension = int(vectors.shape[1])
    self.index = faiss.IndexFlatIP(self.dimension)
    self.metadata = []  # Wipes all existing metadata!
```

If the embedding dimension changes (e.g., switching models), the entire index and metadata are silently wiped. No warning is logged.

---

## 6. Performance Issues

### 6.1 `RetrievalOrchestrator._graph_expand()` Copies All Metadata Per Call
**File:** `backend/app/retrieval/strategies.py` (L52)

As noted in 3.5, every retrieval call creates a full copy of all vector store metadata. For 10,000 chunks, this is a significant overhead on every chat message.

---

### 6.2 `EntityGraph.expand_chunks()` Linear Scan of All Entities
**File:** `backend/app/graph/entity_graph.py` (L87)

```python
for entity in visited_entities:
    chunk_ids.update(self.entity_to_chunks.get(entity, set()))
    if len(chunk_ids) >= max_chunks:
        break
```

The `visited_entities` set can be large (up to 40 entities per hop × 2 hops = 80+ entities). For each entity, the code does a dict lookup and set union. This is O(entities × chunks_per_entity).

---

### 6.3 In-Memory Database Is O(n) for All Operations
**File:** `backend/app/database/memory.py`

The `MemoryCollection` uses a flat list. `find_one()`, `find()`, `update_one()`, and `delete_one()` are all O(n) where n is the number of documents. The `_id_index` dict helps for `_id`-only lookups, but all other queries are linear scans.

---

### 6.4 Document Ingestion Processes Files Sequentially
**File:** `backend/app/services/ingestion.py` (L34)

```python
for file in files:
    text, metadata = await self.parser.parse_upload(file, ...)
```

Files are processed one at a time. For multiple large files, this is slow. Could use `asyncio.gather()` for parallel processing.

---

## 7. Configuration & Deployment Issues

### 7.1 `get_settings()` Has No `cache_clear()` Method
**File:** `backend/app/config/settings.py` (L58)

```python
def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
```

**File:** `backend/tests/test_api.py` (L19)

```python
get_settings.cache_clear()
```

The test file calls `get_settings.cache_clear()`, but `get_settings()` is a plain function with a manual `global _settings` pattern — it does **not** use `@lru_cache`. This call raises `AttributeError: 'function' object has no attribute 'cache_clear'`.

**Impact:** Tests may fail or behave unexpectedly.

**Fix:** Either add `@functools.lru_cache` to `get_settings()`, or remove the `cache_clear()` call and reset `_settings` directly.

---

### 7.2 Dockerfile Doesn't Respect `api_prefix` Setting
**File:** `backend/Dockerfile` (L13)

```dockerfile
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

The `main.py` at the backend root does `from app.main import app`, which works. But if `api_prefix` is set in settings, it's never applied — the `create_app()` function doesn't use it.

---

### 7.3 Frontend Dockerfile Doesn't Copy `.env.local`
**File:** `frontend/Dockerfile`

The frontend build needs `NEXT_PUBLIC_API_BASE_URL` at build time (it's a Next.js public env var). The Dockerfile doesn't copy `.env.local`, so the variable may not be available during `npm run build`.

**Fix:** Either pass the variable as a build arg or copy the env file.

---

### 7.4 `docker-compose.yml` Doesn't Include Frontend Service
**File:** `backend/docker-compose.yml`

The compose file defines a `frontend` service, but it's in the `backend/` directory. Running `docker-compose up` from the project root won't work. The compose file should be at the project root, or the frontend service should reference the correct build context.

---

## 8. Dead Code & Cleanup

### 8.1 `clearMessages` — Never Called
**File:** `frontend/src/hooks/use-chat.ts` (L112)

Defined and returned but never used by any component.

---

### 8.2 `PanelLeftClose` — Unused Import
**File:** `frontend/src/components/chat/chat-area.tsx` (L3)

Imported but never referenced in JSX.

---

### 8.3 `projectItems` — Empty Array
**File:** `frontend/src/components/sidebar/sidebar-nav.tsx` (L32)

```typescript
const projectItems: NavItem[] = [];
```

Defined but never used.

---

### 8.4 `useChat.regenerate()` — Partially Implemented
**File:** `frontend/src/hooks/use-chat.ts` (L118)

```typescript
const regenerate = useCallback(() => {
    const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
    const lastUser = [...messages].reverse().find(
        (m) => m.role === "user" && messages.indexOf(m) < messages.indexOf(lastAssistant!),
    );
    if (!lastUser || !lastAssistant || isStreaming) return;
    setMessages((prev) => prev.filter((m) => m.id !== lastAssistant.id));
    sendMessage(lastUser.content);
}, [messages, isStreaming, sendMessage]);
```

This function removes the last assistant message and resends the last user message. However:
- It uses `messages.indexOf(lastAssistant!)` which may be stale due to closure issues.
- It doesn't update the `activeSessionId`, so the regenerated message may create a new session instead of appending to the current one.

---

## 9. Improvements

### 9.1 Add `delete_many()` to MemoryCollection
Implement the missing method to support MongoDB-compatible queries.

### 9.2 Use `tiktoken` for Token Counting
The package is already in `requirements.txt`. Replace the word-count heuristic with actual tokenization.

### 9.3 Add User-Level Vector Store Filtering
Post-filter search results by `user_id` from metadata to prevent cross-user data leakage.

### 9.4 Add Error Boundaries in Frontend
Wrap the chat area and sidebar in React error boundaries to prevent full-app crashes.

### 9.5 Add Pagination to Sessions API
The backend returns at most 100 sessions. Add cursor-based pagination for power users.

### 9.6 Validate `chunk_overlap < chunk_max_tokens` at Startup
The chunking code has a safety check, but validation should happen at startup to fail fast.

### 9.7 Log Malformed SSE Lines in OpenRouter Client
Currently silently skipped. Add `logger.debug()` for troubleshooting.

### 9.8 Add Rate Limit Headers
Return `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers.

### 9.9 Add Periodic Rate Limiter Cleanup
Clean up stale client entries in `InMemoryRateLimiter` to prevent memory leaks.

### 9.10 Convert UTC Timestamps to Local Time in Frontend
The backend sends UTC timestamps. The frontend should convert them to the user's local timezone for display.

### 9.11 Add Input Validation Feedback in Auth Form
Show password requirements (min 8 chars) before the user submits.

### 9.12 Handle `loadSessions` Failure Gracefully
Don't log the user out if only the session list fails to load. Show an error toast instead.

### 9.13 Use UUID7 or ULID for Sortable IDs
Current IDs use `uuid4().hex` with a timestamp prefix. UUID7 or ULID would be more standard.

### 9.14 Add Session Expiry Cleanup Job
The `cleanup_expired()` method exists but is never called. Add it to the lifespan or a periodic task.

### 9.15 Add Retry Logic for Embedding API Calls
If the embedding model fails to load, the fallback to hash embeddings is good, but there's no retry for transient failures.

### 9.16 Add `"use client"` to `button.tsx`
For consistency with other component files.

### 9.17 Pass User Name to `EmptyState` Component
The component accepts a `userName` prop but `chat-area.tsx` doesn't pass it. Every user sees "Hey, there." instead of their name.

### 9.18 Improve Suggestion Chips for RAG Context
Replace generic prompts with RAG-specific suggestions like "Summarize my documents" or "What are the key findings?"

---

## Summary of Already-Fixed Issues (from old `bugs.md`)

| Old Bug # | Description | Status |
|-----------|-------------|--------|
| 1.1 | Double bandit update | **Fixed** — bandit only updated via feedback |
| 2.1 | No file upload limit | **Fixed** — `MAX_FILES_PER_REQUEST = 20` |
| 2.2 | CORS allows all methods | **Fixed** — restricted to GET, POST, OPTIONS |
| 2.3 | Feature vectors exposed | **Fixed** — only sources and arm sent |
| 2.4 | Refresh doesn't invalidate tokens | **Fixed** — `token_invalid_before` field |
| 2.5 | Rate limiter excludes /app-config | **Fixed** — both excluded |
| 3.1 | MemoryCursor.sort() crashes | **Partially fixed** — uses tuple, but still fragile |
| 3.3 | _apply_update doesn't handle nested | **Fixed** — uses `_set_nested` helper |
| 3.4 | ContextBuilder ignores min_tokens | **Fixed** — uses `chunk_min_tokens` |
| 3.5 | expand_chunks no chunk limit | **Fixed** — `max_chunks=200` |
| 3.6 | get_or_create silently creates | **Fixed** — raises 404 |
| 3.9 | Embedding cache not keyed by model | **Fixed** — includes model name |
| 3.10 | Bandit matrix can become singular | **Fixed** — uses `np.linalg.solve()` |
| 3.11 | Failed chat saves empty message | **Fixed** — checks `if not answer` |
| 5.1 | OpenRouter no backoff | **Fixed** — exponential backoff |
| 5.2 | New client per retry | **Fixed** — reuses client |
| 5.3 | json.loads can fail | **Fixed** — try/except with continue |
| 5.4 | VectorStore saves on every call | **Fixed** — 30s debounce |
| 5.5 | LinUCB saves on every call | **Fixed** — 30s debounce |
| 5.6 | Entity extraction blocks event loop | **Fixed** — uses `asyncio.to_thread` |
| 5.7 | Chunking infinite loop | **Fixed** — overlap safety check |
| 5.9 | Expired sessions never cleaned | **Fixed** — `cleanup_expired()` exists |
| 5.10 | Scores exposed in LLM prompt | **Fixed** — only source name |
| 5.12 | UUID4 not sortable | **Fixed** — uses timestamp prefix |
| 6.1 | Hardcoded "Rakesh" | **Fixed** — defaults to "there" |
| 6.2 | Metadata says "ChatGPT" | **Fixed** — says "RAGnostic" |
| 6.3 | Disclaimer says "ChatGPT" | **Fixed** — says "RAGnostic" |
| 6.4 | Feedback never sent | **Fixed** — `sendFeedback` called |
| 6.5 | streamChat no JSON error handling | **Fixed** — try/catch |
| 6.7 | Session grouping uses milliseconds | **Fixed** — uses calendar dates |
| 6.8 | button.tsx missing "use client" | **Still missing** |
| 8.1 | @lru_cache prevents hot reload | **Changed** — no @lru_cache, but tests still call cache_clear |
| 8.3 | docker-compose missing frontend | **Fixed** — frontend service added |
| 8.4 | No .env.example | **Exists** — `.env.example` is present |
| 8.5 | JWT secret default value | **Still present** — warning added in lifespan |
