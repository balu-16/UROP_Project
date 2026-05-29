import type { AuthResponse, BackendSession, Message } from "@/types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

const TOKEN_KEY = "ragnostic_access_token";

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
    let detail = "Request failed";
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {
      detail = response.statusText;
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

export async function refreshToken() {
  const response = await rawFetch("/auth/refresh", { method: "POST" });
  const data = await parseJson<AuthResponse>(response);
  setAccessToken(data.access_token);
  return data;
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
      // Refresh failed — clear token so user is redirected to login
      setAccessToken(null);
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

export async function streamChat(
  message: string,
  sessionId: string | null,
  signal: AbortSignal,
  onEvent: (event: string, data: any) => void,
) {
  const response = await authFetch("/chat", {
    method: "POST",
    body: JSON.stringify({ message, session_id: sessionId }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(response.statusText || "Unable to start chat stream");
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
      const dataLine = lines
        .find((line) => line.startsWith("data:"))
        ?.slice(5)
        .trim();
      if (!dataLine) continue;
      try {
        onEvent(event, JSON.parse(dataLine));
      } catch {
        // skip malformed SSE data
      }
    }
  }
}
