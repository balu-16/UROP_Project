"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Message } from "@/types";
import { getChatHistory, streamChat } from "@/lib/api";

export function useChat(
  activeSessionId: string | null,
  onSessionChange?: (sessionId: string) => void,
  onSessionsDirty?: () => void,
) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadHistory() {
      if (!activeSessionId) {
        setMessages([]);
        return;
      }
      const history = await getChatHistory(activeSessionId);
      if (!cancelled) setMessages(history);
    }
    loadHistory().catch(() => {
      if (!cancelled) setMessages([]);
    });
    return () => {
      cancelled = true;
    };
  }, [activeSessionId]);

  const sendMessage = useCallback(
    async (content: string) => {
      const userMessage: Message = {
        id: `user-${Date.now()}`,
        role: "user",
        content,
        timestamp: new Date(),
        sessionId: activeSessionId || undefined,
      };

      const assistantId = `assistant-${Date.now()}`;
      const assistantMessage: Message = {
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: new Date(),
        isStreaming: true,
      };

      setMessages((prev) => [...prev, userMessage, assistantMessage]);
      setIsStreaming(true);
      const controller = new AbortController();
      abortRef.current = controller;

      let accumulated = "";
      try {
        await streamChat(
          content,
          activeSessionId,
          controller.signal,
          (event, data) => {
            if (event === "metadata") {
              if (data.session_id) onSessionChange?.(data.session_id);
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantId
                    ? {
                        ...msg,
                        sessionId: data.session_id,
                        selectedArm: data.selected_arm,
                        sources: data.sources || [],
                        retrievalDiagnostics: data.retrieval || {},
                      }
                    : msg,
                ),
              );
            }
            if (event === "token") {
              accumulated += data.delta || "";
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantId
                    ? { ...msg, content: accumulated }
                    : msg,
                ),
              );
            }
            if (event === "reasoning") {
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantId
                    ? {
                        ...msg,
                        reasoningMetadata: {
                          ...(msg.reasoningMetadata || {}),
                          latest: data.reasoning,
                        },
                      }
                    : msg,
                ),
              );
            }
            if (event === "reward") {
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
            }
            if (event === "done") {
              if (data.session_id) onSessionChange?.(data.session_id);
              if (data.message_id) {
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantId
                      ? { ...msg, id: data.message_id }
                      : msg,
                  ),
                );
              }
              onSessionsDirty?.();
            }
          },
        );
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") {
          // User intentionally stopped generation — don't show an error
        } else {
          const message =
            error instanceof Error ? error.message : "Streaming failed";
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantId
                ? { ...msg, content: `Backend error: ${message}` }
                : msg,
            ),
          );
        }
      } finally {
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantId
              ? { ...msg, isStreaming: false, timestamp: new Date() }
              : msg,
          ),
        );
        setIsStreaming(false);
        abortRef.current = null;
      }
    },
    [activeSessionId, onSessionChange, onSessionsDirty],
  );

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
    setIsStreaming(false);
    setMessages((prev) =>
      prev.map((msg) =>
        msg.isStreaming ? { ...msg, isStreaming: false } : msg,
      ),
    );
  }, []);

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

    // Remove the last assistant message and resend
    setMessages((prev) => prev.filter((m) => m.id !== lastAssistant.id));
    sendMessage(lastUser.content);
  }, [messages, isStreaming, sendMessage]);

  return {
    messages,
    isStreaming,
    sendMessage,
    stopStreaming,
    regenerate,
  };
}
