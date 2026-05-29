"use client";

import { useState, useCallback } from "react";
import { motion } from "framer-motion";
import { PanelLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "./empty-state";
import { MessageList } from "./message-list";
import { InputComposer } from "@/components/composer/input-composer";
import { SuggestionChips } from "@/components/composer/suggestion-chips";
import { useChat } from "@/hooks/use-chat";
import { useKeyboardShortcuts } from "@/hooks/use-keyboard";
import { cn } from "@/lib/utils";

interface ChatAreaProps {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  activeSessionId: string | null;
  onSessionChange: (sessionId: string) => void;
  onSessionsDirty: () => void;
}

export function ChatArea({
  sidebarOpen,
  onToggleSidebar,
  activeSessionId,
  onSessionChange,
  onSessionsDirty,
}: ChatAreaProps) {
  const { messages, isStreaming, sendMessage, stopStreaming, regenerate } =
    useChat(activeSessionId, onSessionChange, onSessionsDirty);

  const hasMessages = messages.length > 0;

  /* Focus management for keyboard shortcut */
  const handleFocusComposer = useCallback(() => {
    const textarea = document.querySelector(
      'textarea[aria-label="Message input"]',
    ) as HTMLTextAreaElement | null;
    textarea?.focus();
  }, []);

  useKeyboardShortcuts({
    onToggleSidebar,
    onSendMessage: () => {
      // Handled by textarea Enter key
    },
    onFocusComposer: handleFocusComposer,
  });

  const handleSuggestion = (text: string) => {
    sendMessage(text);
  };

  return (
    <div className="flex flex-1 flex-col h-full bg-background relative overflow-hidden">
      {/* Top bar */}
      <div className="flex items-center h-12 shrink-0 px-3 border-b border-border/40">
        {!sidebarOpen && (
          <motion.div
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.2 }}
          >
            <Button
              variant="ghost"
              size="icon"
              onClick={onToggleSidebar}
              className="h-8 w-8 text-foreground/50 hover:text-foreground/80 mr-2"
              aria-label="Open sidebar"
            >
              <PanelLeft className="h-4 w-4" />
            </Button>
          </motion.div>
        )}
        <div className="flex-1" />
        <div className="flex items-center gap-1.5 text-sm text-foreground/60">
          <span className="font-medium">RAGnostic</span>
          <span className="text-foreground/30">Kimi K2.6</span>
        </div>
        <div className="flex-1" />
      </div>

      {/* Messages or Empty state */}
      {hasMessages ? (
        <MessageList
          messages={messages}
          isStreaming={isStreaming}
          onRegenerate={regenerate}
        />
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center px-4 pb-32">
          <EmptyState />
        </div>
      )}

      {/* Bottom composer area */}
      <div
        className={cn(
          "shrink-0 pb-4 pt-2 transition-all duration-300",
          hasMessages ? "" : "absolute bottom-0 left-0 right-0",
        )}
      >
        {/* Suggestion chips — only show when empty */}
        {!hasMessages && (
          <div className="mb-4">
            <SuggestionChips onSelect={handleSuggestion} />
          </div>
        )}

        <InputComposer
          onSend={sendMessage}
          onStop={stopStreaming}
          isStreaming={isStreaming}
        />
      </div>
    </div>
  );
}
