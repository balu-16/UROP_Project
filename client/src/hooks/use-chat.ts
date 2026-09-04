"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Attachment, Message } from "@/types";
import {
  getChatHistory,
  streamChat,
  truncateSession,
} from "@/lib/api";

interface StreamBuffers {
  content: string;
  reasoning: string;
}

interface SendMessageOptions {
  reasoning?: boolean;
  sessionId?: string | null;
  attachments?: Attachment[];
}

export function useChat(
  activeSessionId: string | null,
  onSessionChange?: (sessionId: string) => void,
  onSessionsDirty?: () => void,
  onError?: (message: string) => void,
) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  // History-load failures must not wipe the visible conversation. onError is
  // kept in a ref so the loader effect doesn't re-run on callback identity.
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  // High-frequency stream buffers. Tokens are accumulated in a ref and flushed
  // to React state once per animation frame, so a fast token burst causes one
  // render per frame instead of one render per token.
  const buffersRef = useRef<StreamBuffers>({ content: "", reasoning: "" });
  const assistantIdRef = useRef<string | null>(null);
  const serverIdRef = useRef<string | null>(null);
  const frameRef = useRef<number | null>(null);

  const flush = useCallback(() => {
    frameRef.current = null;
    const id = assistantIdRef.current;
    if (!id) return;
    const serverId = serverIdRef.current;
    const { content, reasoning } = buffersRef.current;
    setMessages((prev) =>
      prev.map((msg) =>
        msg.id === id || (serverId !== null && msg.id === serverId)
          ? {
              ...msg,
              content,
              reasoningMetadata: reasoning
                ? { ...msg.reasoningMetadata, latest: reasoning }
                : msg.reasoningMetadata,
            }
          : msg,
      ),
    );
  }, []);

  const scheduleFlush = useCallback(() => {
    if (frameRef.current !== null) return;
    // setTimeout instead of requestAnimationFrame: rAF never fires in
    // hidden/background tabs, which starves the stream buffers entirely.
    frameRef.current = window.setTimeout(flush, 80);
  }, [flush]);

  // Cancel any pending flush when the hook unmounts mid-stream
  useEffect(() => {
    return () => {
      if (frameRef.current !== null) clearTimeout(frameRef.current);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadHistory() {
      // A live stream owns the message list — a session change arriving
      // mid-stream (e.g. the metadata event of a brand-new chat) must not
      // clobber it with a (stale) server history.
      if (abortRef.current) return;
      if (!activeSessionId) {
        setMessages([]);
        return;
      }
      const history = await getChatHistory(activeSessionId);
      if (!cancelled) setMessages(history);
    }
    loadHistory().catch(() => {
      // Preserve whatever is on screen; surface the failure as a toast.
      if (cancelled) return;
      onErrorRef.current?.("Could not load chat history — showing cached messages.");
    });
    return () => {
      cancelled = true;
    };
  }, [activeSessionId]);

  const sendMessage = useCallback(
    async (content: string, opts?: SendMessageOptions) => {
      const trimmed = content.trim();
      if (!trimmed || abortRef.current) return;
      // Explicit session wins (e.g. just-created chat); else the active one.
      const sessionId = opts?.sessionId !== undefined ? opts.sessionId : activeSessionId;

      const userMessage: Message = {
        id: `user-${Date.now()}`,
        role: "user",
        content: trimmed,
        timestamp: new Date(),
        sessionId: sessionId || undefined,
        attachments:
          opts?.attachments?.length ? [...opts.attachments] : undefined,
      };

      const assistantId = `assistant-${Date.now()}`;
      assistantIdRef.current = assistantId;
      serverIdRef.current = null;
      buffersRef.current = { content: "", reasoning: "" };
      const assistantMessage: Message = {
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: new Date(),
        isStreaming: true,
        stage: "starting",
      };

      setMessages((prev) => [...prev, userMessage, assistantMessage]);
      setIsStreaming(true);
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        await streamChat(
          trimmed,
          sessionId,
          controller.signal,
          (event, data) => {
            if (event === "metadata") {
              if (data.session_id) onSessionChange?.(data.session_id);
              // Support both legacy selected_arm and new retrieval object
              const retrieval = data.retrieval || {};
              const selected = data.selected_arm || (retrieval.strategy ? retrieval.strategy.toLowerCase() : undefined) || (typeof retrieval.depth === "number" ? ["standard_rag","graph_rag_1hop","graph_rag_2hop"][retrieval.depth] : undefined);
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantId
                    ? {
                        ...msg,
                        sessionId: data.session_id,
                        selectedArm: selected,
                        sources: data.sources || [],
                        retrieval: retrieval,
                        retrievalDiagnostics: data.retrieval || data.retrievalDiagnostics || {},
                      }
                    : msg,
                ),
              );
            } else if (event === "stage") {
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantId ? { ...msg, stage: data.stage } : msg,
                ),
              );
            } else if (event === "token") {
              buffersRef.current.content += data.delta || "";
              scheduleFlush();
            } else if (event === "reasoning") {
              buffersRef.current.reasoning += data.reasoning || "";
              scheduleFlush();
            } else if (event === "reward") {
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantId
                    ? {
                        ...msg,
                        reward: data.reward,
                        latencyMs: data.latency_ms,
                      }
                    : msg,
                ),
              );
            } else if (event === "followups") {
              const questions: string[] = Array.isArray(data.questions)
                ? data.questions
                : [];
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantId ? { ...msg, followUps: questions } : msg,
                ),
              );
            } else if (event === "error") {
              buffersRef.current.content +=
                `\n\n> ⚠️ ${data.message || "The model returned an error."}`;
              scheduleFlush();
            } else if (event === "done") {
              if (data.session_id) onSessionChange?.(data.session_id);
              // Finalize atomically: apply whatever the rAF flushes may have
              // missed (background-tab throttling, rename races) so the answer
              // always lands complete with streaming cleared.
              const serverId = (data.message_id as string | undefined) || null;
              serverIdRef.current = serverId;
              const buffered = buffersRef.current;
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantId
                    ? {
                        ...msg,
                        id: serverId ?? msg.id,
                        content: buffered.content || msg.content,
                        reasoningMetadata: buffered.reasoning
                          ? { ...msg.reasoningMetadata, latest: buffered.reasoning }
                          : msg.reasoningMetadata,
                        isStreaming: false,
                        timestamp: new Date(),
                      }
                    : msg,
                ),
              );
              onSessionsDirty?.();
            }
          },
          opts?.reasoning ?? true,
        );
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") {
          // User intentionally stopped generation — keep partial output
        } else {
          const message =
            error instanceof Error ? error.message : "Streaming failed";
          onError?.(message);
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantId && !msg.content
                ? { ...msg, content: `Backend error: ${message}` }
                : msg,
            ),
          );
        }
      } finally {
        // Flush any buffered tokens synchronously before closing out
        if (frameRef.current !== null) {
          clearTimeout(frameRef.current);
          frameRef.current = null;
        }
        flush();
        // The done event may have renamed the message to its server id —
        // clear streaming on whichever form is present.
        const finalId = serverIdRef.current ?? assistantId;
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === finalId || msg.id === assistantId
              ? { ...msg, isStreaming: false, timestamp: new Date() }
              : msg,
          ),
        );
        setIsStreaming(false);
        abortRef.current = null;
        assistantIdRef.current = null;
        serverIdRef.current = null;
      }
    },
    [activeSessionId, onSessionChange, onSessionsDirty, onError, flush, scheduleFlush],
  );

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  /** Replace a previously sent user message and regenerate from that point. */
  const editAndResend = useCallback(
    (messageId: string, newText: string) => {
      const trimmed = newText.trim();
      if (!trimmed || isStreaming || abortRef.current) return;
      const idx = messages.findIndex((m) => m.id === messageId);
      if (idx === -1 || messages[idx].role !== "user") return;

      // Best-effort server-side truncation of this branch
      const sessionId = messages[idx].sessionId || activeSessionId;
      if (sessionId && !messageId.startsWith("user-")) {
        truncateSession(sessionId, messageId).catch(() => {});
      }

      setMessages(messages.slice(0, idx));
      sendMessage(trimmed);
    },
    [messages, isStreaming, activeSessionId, sendMessage],
  );

  const regenerate = useCallback(() => {
    const lastAssistant = [...messages]
      .reverse()
      .find((m) => m.role === "assistant");
    if (!lastAssistant || isStreaming) return;

    // Find the user message that prompted this assistant response
    const assistantIdx = messages.indexOf(lastAssistant);
    const lastUser = [...messages]
      .slice(0, assistantIdx)
      .reverse()
      .find((m) => m.role === "user");
    if (!lastUser) return;

    // Remove both the last assistant message and the user message that prompted
    // it, then resend — avoids duplicating the user message.
    // Truncate server branch like editAndResend so stale pairs don't accumulate.
    const savedUserMessage = { ...lastUser };
    const sessionId = lastUser.sessionId || activeSessionId;
    if (sessionId && !lastUser.id.startsWith("user-")) {
      truncateSession(sessionId, lastUser.id).catch(() => {});
    }
    setMessages((prev) =>
      prev.filter((m) => m.id !== lastAssistant.id && m.id !== lastUser.id),
    );
    sendMessage(savedUserMessage.content).catch(() => {
      // If sendMessage fails, restore the user message so the prompt isn't lost
      setMessages((prev) => [...prev, savedUserMessage]);
    });
  }, [messages, isStreaming, sendMessage]);

  return {
    messages,
    isStreaming,
    sendMessage,
    stopStreaming,
    regenerate,
    editAndResend,
  };
}
