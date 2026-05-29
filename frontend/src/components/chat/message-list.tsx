"use client";

import { useEffect, useRef } from "react";
import { AnimatePresence } from "framer-motion";
import type { Message } from "@/types";
import { UserMessage } from "./user-message";
import { AssistantMessage } from "./assistant-message";
import { TypingIndicator } from "./typing-indicator";

interface MessageListProps {
  messages: Message[];
  isStreaming: boolean;
  onRegenerate?: () => void;
}

export function MessageList({
  messages,
  isStreaming,
  onRegenerate,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const lastMessageContent = messages[messages.length - 1]?.content;

  /* Auto-scroll to bottom when new messages arrive or content updates */
  useEffect(() => {
    const el = bottomRef.current;
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth" });
  }, [messages, lastMessageContent]);

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto scroll-smooth"
      role="log"
      aria-label="Chat messages"
      aria-live="polite"
    >
      <div className="max-w-[768px] mx-auto py-4">
        <AnimatePresence initial={false}>
          {messages.map((msg, i) =>
            msg.role === "user" ? (
              <UserMessage key={msg.id} content={msg.content} index={i} />
            ) : (
              <AssistantMessage
                key={msg.id}
                content={msg.content}
                isStreaming={msg.isStreaming}
                onRegenerate={onRegenerate}
                index={i}
                selectedArm={msg.selectedArm}
                sources={msg.sources}
                reward={msg.reward}
                latencyMs={msg.latencyMs}
                messageId={msg.id}
                sessionId={msg.sessionId}
              />
            ),
          )}
        </AnimatePresence>

        {/* Typing indicator when waiting for first token */}
        {isStreaming &&
          messages.length > 0 &&
          messages[messages.length - 1]?.role === "user" && <TypingIndicator />}

        {/* Scroll anchor */}
        <div ref={bottomRef} className="h-4" />
      </div>
    </div>
  );
}
