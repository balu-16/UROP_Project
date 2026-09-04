import type { AuthResponse, BackendSession, Message } from "@/types";

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"
).replace(/\/+$/, "");

const TOKEN_KEY = "ragnostic_access_token";

// Serialize concurrent refresh calls so only one request rotates the token
let refreshPromise: Promise<AuthResponse> | null = null;

export function getAccessToken() {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setAccessToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail: string = "Request failed";
    try {
      const payload = await response.json();
      const raw = (payload as { detail?: unknown }).detail;
      if (Array.isArray(raw)) {
        // FastAPI 422 validation errors: [{loc, msg, ...}]
        detail = raw
          .map((e) =>
            typeof e === "object" && e !== null && "msg" in e
              ? String((e as { msg: unknown }).msg)
              : JSON.stringify(e),
          )
          .join("; ");
      } else if (typeof raw === "string") {
        detail = raw;
      } else if (raw != null) {
        detail = JSON.stringify(raw);
      } else {
        detail = response.statusText || detail;
      }
    } catch {
      detail = response.statusText || detail;
    }
    throw new Error(detail);
  }
  return response.json();
}

async function rawFetch(path: string, init: RequestInit = {}) {
  return fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers || {}),
    },
  });
}

export async function signup(name: string, email: string, password: string) {
  const response = await rawFetch("/auth/signup", {
    method: "POST",
    body: JSON.stringify({ name, email, password }),
  });
  const data = await parseJson<AuthResponse>(response);
  setAccessToken(data.access_token);
  return data;
}

export async function login(email: string, password: string) {
  const response = await rawFetch("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  const data = await parseJson<AuthResponse>(response);
  setAccessToken(data.access_token);
  return data;
}

export async function refreshToken(): Promise<AuthResponse> {
  // If a refresh is already in-flight, wait for it instead of starting a new one
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    try {
      const response = await rawFetch("/auth/refresh", { method: "POST" });
      const data = await parseJson<AuthResponse>(response);
      setAccessToken(data.access_token);
      return data;
    } catch (err) {
      // Clear token once on failure — all concurrent callers share this path
      setAccessToken(null);
      throw err;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

export async function logout() {
  await authFetch("/auth/logout", { method: "POST" });
  setAccessToken(null);
}

export async function authFetch(
  path: string,
  init: RequestInit = {},
  retry = true,
): Promise<Response> {
  const token = getAccessToken();
  const headers: Record<string, string> = {
    ...(init.body instanceof FormData
      ? {}
      : { "Content-Type": "application/json" }),
    ...((init.headers as Record<string, string>) || {}),
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers,
  });
  if (response.status === 401 && retry) {
    try {
      await refreshToken();
      return authFetch(path, init, false);
    } catch {
      // Refresh failed — refreshToken() already cleared the token
      return response;
    }
  }
  return response;
}

export async function getMe() {
  const response = await authFetch("/auth/me");
  return parseJson<AuthResponse["user"]>(response);
}

export async function getSessions() {
  const response = await authFetch("/sessions");
  return parseJson<BackendSession[]>(response);
}

export async function createSession(title?: string) {
  const response = await authFetch("/sessions", {
    method: "POST",
    body: JSON.stringify({ title }),
  });
  return parseJson<BackendSession>(response);
}

function toMessage(raw: Record<string, any>): Message {
  const diag = (raw.retrieval_diagnostics as Record<string, any>) || {};
  const fallbackRetrieval =
    typeof diag.depth === "number"
      ? {
          depth: diag.depth,
          confidence: diag.confidence ?? 0,
          strategy: diag.strategy || "",
          retrieval_mode: (diag as Record<string, any>).retrieval_mode ?? "hybrid",
          candidate_count:
            (diag as Record<string, any>).candidate_count ??
            (diag as Record<string, any>).rerank_candidate_count,
          reranked_count: (diag as Record<string, any>).reranked_count,
          reranker_model: (diag as Record<string, any>).reranker_model ?? null,
        }
      : undefined;
  return {
    id: raw._id,
    role: raw.role,
    content: raw.content,
    timestamp: new Date(raw.created_at),
    sessionId: raw.session_id,
    selectedArm: raw.selected_arm,
    sources: raw.sources || [],
    reward: raw.reward,
    latencyMs: raw.latency_ms,
    reasoningMetadata: raw.reasoning_metadata || {},
    retrievalDiagnostics: raw.retrieval_diagnostics || {},
    // New rows persist full `retrieval`; legacy rows fall back to diagnostics.
    retrieval: raw.retrieval || fallbackRetrieval,
    // Follow-ups/stage are live-SSE-only today (never persisted server-side);
    // pass through when present so a future persisted shape just works.
    ...(Array.isArray(raw.follow_ups) || Array.isArray(raw.followups)
      ? { followUps: raw.follow_ups ?? raw.followups }
      : {}),
    ...(typeof raw.stage === "string" ? { stage: raw.stage } : {}),
  };
}

export async function getChatHistory(sessionId: string) {
  const response = await authFetch(`/chat-history/${sessionId}`);
  const data = await parseJson<{
    session: BackendSession | null;
    messages: Record<string, any>[];
  }>(response);
  return data.messages.map(toMessage);
}

export async function sendFeedback(
  sessionId: string,
  messageId: string,
  rating: number,
  comment?: string,
) {
  const response = await authFetch("/feedback", {
    method: "POST",
    body: JSON.stringify({
      session_id: sessionId,
      message_id: messageId,
      rating,
      comment: comment || null,
    }),
  });
  return parseJson<{ ok: boolean }>(response);
}

export async function truncateSession(sessionId: string, messageId: string) {
  const response = await authFetch(`/sessions/${sessionId}/truncate`, {
    method: "POST",
    body: JSON.stringify({ message_id: messageId }),
  });
  return parseJson<{ ok: boolean; deleted: number }>(response);
}

export async function uploadFiles(
  files: File[],
  sessionId: string | null,
): Promise<{ indexed: number; chunk_count: number; documents?: UploadedDocument[] }> {
  const formData = new FormData();
  for (const file of files) formData.append("files", file);
  // Documents belong to exactly one chat: the backend requires session_id
  // and scopes every chunk/vector to it.
  formData.append("session_id", sessionId || "");
  const response = await authFetch("/index-documents", {
    method: "POST",
    body: formData,
  });
  const data = await parseJson<{
    chunk_count: number;
    documents?: UploadedDocument[];
  }>(response);
  // Backend returns {chunk_count, ...}; keep legacy {indexed} for callers
  return { indexed: data.chunk_count, chunk_count: data.chunk_count, documents: data.documents };
}

export interface UploadedDocument {
  _id: string;
  filename?: string;
  metadata?: { source?: string };
  chunk_count?: number;
}

export interface SessionDocument {
  _id: string;
  filename?: string;
  chunk_count?: number;
  created_at?: string;
}

/** Session-scoped document list (server truth; localStorage stays as cache). */
export async function listDocuments(sessionId: string): Promise<SessionDocument[]> {
  const response = await authFetch(
    `/documents?session_id=${encodeURIComponent(sessionId)}`,
  );
  const data = await parseJson<{ documents?: SessionDocument[] }>(response);
  return Array.isArray(data.documents) ? data.documents : [];
}

/** Un-upload: delete a document and all its chunks/vectors/graph links. */
export async function deleteDocument(
  documentId: string,
  sessionId: string,
): Promise<{ ok: boolean; deleted?: Record<string, unknown> }> {
  const response = await authFetch(
    `/documents/${encodeURIComponent(documentId)}?session_id=${encodeURIComponent(sessionId)}`,
    { method: "DELETE" },
  );
  return parseJson<{ ok: boolean; deleted?: Record<string, unknown> }>(response);
}

export async function streamChat(
  message: string,
  sessionId: string | null,
  signal: AbortSignal,
  onEvent: (event: string, data: any) => void,
  reasoning = true,
) {
  const response = await authFetch("/chat", {
    method: "POST",
    body: JSON.stringify({ message, session_id: sessionId, reasoning }),
    signal,
  });
  if (!response.ok || !response.body) {
    let msg = response.statusText || "Unable to start chat stream";
    try {
      const payload = await response.clone().json();
      const raw = (payload as { detail?: unknown }).detail;
      if (typeof raw === "string") msg = raw;
      else if (Array.isArray(raw)) msg = raw.map((e) => JSON.stringify(e)).join("; ");
      else if (raw != null) msg = JSON.stringify(raw);
    } catch {
      // keep statusText fallback (body may be SSE stream, not JSON)
    }
    throw new Error(`Backend error ${response.status}: ${msg}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";
    for (const raw of events) {
      const lines = raw.split("\n");
      const event =
        lines
          .find((line) => line.startsWith("event:"))
          ?.slice(6)
          .trim() || "message";
      // Per SSE spec, multiple data: lines in a single event must be concatenated
      const dataLines = lines
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim());
      if (dataLines.length === 0) continue;
      const dataLine = dataLines.join("\n");
      try {
        onEvent(event, JSON.parse(dataLine));
      } catch {
        // skip malformed SSE data
      }
    }
  }
}
