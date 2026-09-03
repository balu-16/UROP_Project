"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDown } from "lucide-react";
import type { Message } from "@/types";
import { UserMessage } from "./user-message";
import { AssistantMessage } from "./assistant-message";
import type { ReasoningMetadata } from "@/types";

const WINDOW_SIZE = 60;

interface MessageListProps {
  messages: Message[];
  isStreaming: boolean;
  onRegenerate?: () => void;
  onEdit?: (messageId: string, newText: string) => void;
  onFollowUp?: (question: string) => void;
}

function reasoningText(msg: Message): string | undefined {
  const meta = msg.reasoningMetadata as ReasoningMetadata | undefined;
  if (!meta) return undefined;
  if (typeof meta.latest === "string" && meta.latest.trim()) return meta.latest;
  const details = meta.reasoning_details;
  if (Array.isArray(details) && details.length) return details.join("");
  return undefined;
}

export function MessageList({
  messages,
  isStreaming,
  onRegenerate,
  onEdit,
  onFollowUp,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const pinnedToBottomRef = useRef(true);
  const rafRef = useRef<number | null>(null);
  const [visibleCount, setVisibleCount] = useState(WINDOW_SIZE);
  const [showJump, setShowJump] = useState(false);

  const lastMessageContent = messages[messages.length - 1]?.content;
  // Only the tail of long conversations renders — keeps DOM small and scrolling fast
  const windowStart = Math.max(0, messages.length - visibleCount);
  const visibleMessages = messages.slice(windowStart);

  /* Track scroll position: auto-scroll only while pinned to bottom */
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const onScroll = () => {
      const distance =
        container.scrollHeight - container.scrollTop - container.clientHeight;
      pinnedToBottomRef.current = distance < 80;
      setShowJump(distance > 400);
    };
    container.addEventListener("scroll", onScroll, { passive: true });
    return () => container.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!pinnedToBottomRef.current) return;
    // Coalesce scroll work into one rAF per flush — scrollIntoView per token
    // forces layout and fights the user's own scroll gestures.
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      const container = containerRef.current;
      if (!container) return;
      container.scrollTo({ top: container.scrollHeight, behavior: "auto" });
    });
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [messages, lastMessageContent, isStreaming]);

  const jumpToLatest = () => {
    pinnedToBottomRef.current = true;
    setShowJump(false);
    containerRef.current?.scrollTo({
      top: containerRef.current.scrollHeight,
      behavior: "smooth",
    });
  };

  return (
    <div className="relative min-h-0 flex-1">
      <div
        ref={containerRef}
        className="h-full overflow-y-auto overscroll-contain"
        role="log"
        aria-label="Chat messages"
        aria-live="polite"
      >
        <div className="mx-auto max-w-[768px] px-4 py-4 sm:px-6">
          {windowStart > 0 && (
            <div className="flex justify-center pb-3">
              <button
                type="button"
                onClick={() => setVisibleCount((c) => c + WINDOW_SIZE)}
                className="rounded-full border border-border bg-card px-3.5 py-1.5 text-xs text-foreground/60 transition-colors hover:bg-secondary hover:text-foreground"
              >
                Load {Math.min(WINDOW_SIZE, windowStart)} earlier messages
              </button>
            </div>
          )}
          {visibleMessages.map((msg) =>
            msg.role === "user" ? (
              <UserMessage
                key={msg.id}
                content={msg.content}
                messageId={msg.id}
                isStreaming={isStreaming}
                onEdit={onEdit}
              />
            ) : (
              <AssistantMessage
                key={msg.id}
                content={msg.content}
                isStreaming={msg.isStreaming}
                onRegenerate={onRegenerate}
                selectedArm={msg.selectedArm}
                sources={msg.sources}
                reward={msg.reward}
                latencyMs={msg.latencyMs}
                messageId={msg.id}
                sessionId={msg.sessionId}
                reasoning={reasoningText(msg)}
                stage={msg.stage}
                followUps={msg.followUps}
                onFollowUp={onFollowUp}
                retrieval={msg.retrieval as any}
              />
            ),
          )}

          {/* Scroll anchor */}
          <div ref={bottomRef} className="h-2" />
        </div>
      </div>

      {/* Jump to latest */}
      {showJump && (
        <button
          type="button"
          onClick={jumpToLatest}
          aria-label="Jump to latest message"
          className="absolute bottom-4 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-border bg-card px-3.5 py-2 text-xs font-medium text-foreground/70 shadow-subtle transition-colors hover:text-foreground"
        >
          <ArrowDown className="h-3.5 w-3.5" />
          Jump to latest
          {isStreaming && (
            <span className="ml-0.5 h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
          )}
        </button>
      )}
    </div>
  );
}
