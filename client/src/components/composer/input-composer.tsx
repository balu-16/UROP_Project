"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowUp,
  StopCircle,
  Paperclip,
  Zap,
  BrainCircuit,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const ACCEPTED_TYPES = ".pdf,.txt,.md,.markdown,.pptx";

interface InputComposerProps {
  onSend: (message: string, reasoning: boolean) => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
  sessionId?: string | null;
  onUploadFiles?: (files: File[]) => void;
  uploading?: boolean;
}

export function InputComposer({
  onSend,
  onStop,
  isStreaming,
  disabled,
  sessionId,
  onUploadFiles,
  uploading,
}: InputComposerProps) {
  const [value, setValue] = useState("");
  const [deepReasoning, setDeepReasoning] = useState(true);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const draftKey = `ragnostic_draft_${sessionId || "new"}`;

  /* Restore saved draft when the session changes */
  useEffect(() => {
    try {
      setValue(window.localStorage.getItem(draftKey) || "");
    } catch {
      setValue("");
    }
  }, [draftKey]);

  const setValuePersisted = useCallback(
    (next: string) => {
      setValue(next);
      try {
        if (next) window.localStorage.setItem(draftKey, next);
        else window.localStorage.removeItem(draftKey);
      } catch {
        // storage unavailable — draft simply won't persist
      }
    },
    [draftKey],
  );

  /* Auto-resize textarea */
  const adjustHeight = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [value, adjustHeight]);

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || isStreaming || disabled) return;
    onSend(trimmed, deepReasoning);
    setValuePersisted("");
    // Reset height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFilesPicked = (files: FileList | null) => {
    if (!files?.length || !onUploadFiles) return;
    onUploadFiles(Array.from(files));
  };

  const canSend = value.trim().length > 0 && !isStreaming && !disabled;

  return (
    <div className="w-full max-w-[768px] mx-auto px-4">
      <div
        className={cn(
          "relative flex items-end gap-2 rounded-3xl border bg-card/70 backdrop-blur-xl px-4 py-3",
          "border-border/50",
          "shadow-[0_4px_24px_-12px_rgba(0,0,0,0.45)]",
          "transition-all duration-200",
          "focus-within:border-foreground/15 focus-within:bg-card/85 focus-within:shadow-[0_6px_28px_-14px_rgba(0,0,0,0.5)]",
          value && "border-border/60 bg-card/80",
        )}
      >
        {/* Left: Attach button */}
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0 text-foreground/40 hover:text-foreground/70 rounded-full -ml-1"
          aria-label="Attach documents"
          title="Attach documents (indexed into this chat only)"
          disabled={disabled || uploading}
          onClick={() => fileInputRef.current?.click()}
        >
          {uploading ? (
            <Loader2 className="h-5 w-5 animate-spin" />
          ) : (
            <Paperclip className="h-[18px] w-[18px]" />
          )}
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_TYPES}
          multiple
          hidden
          onChange={(e) => {
            handleFilesPicked(e.target.files);
            e.target.value = "";
          }}
        />

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValuePersisted(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything"
          rows={1}
          disabled={disabled}
          className={cn(
            "flex-1 bg-transparent text-[15px] text-foreground placeholder:text-foreground/35",
            "outline-none resize-none min-h-[24px] max-h-[200px] py-0.5",
            "leading-[1.5]",
          )}
          aria-label="Message input"
        />

        {/* Right: Action buttons */}
        <div className="flex items-center gap-1 shrink-0 -mr-1">
          {/* Reasoning mode toggle */}
          <TooltipButton
            active={deepReasoning}
            onClick={() => setDeepReasoning((v) => !v)}
            label={
              deepReasoning
                ? "Deep mode: model reasons step by step"
                : "Fast mode: skip extended reasoning"
            }
          >
            {deepReasoning ? (
              <BrainCircuit className="h-4 w-4" />
            ) : (
              <Zap className="h-4 w-4" />
            )}
          </TooltipButton>

          {/* Send / Stop button */}
          <AnimatePresence mode="wait">
            {isStreaming ? (
              <motion.div
                key="stop"
                initial={{ scale: 0.8, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.8, opacity: 0 }}
                transition={{ duration: 0.15 }}
              >
                <Button
                  onClick={onStop}
                  size="icon"
                  className="h-8 w-8 rounded-full bg-foreground text-background hover:bg-foreground/90"
                  aria-label="Stop generating"
                >
                  <StopCircle className="h-4 w-4" />
                </Button>
              </motion.div>
            ) : (
              <motion.div
                key="send"
                initial={{ scale: 0.8, opacity: 0 }}
                animate={{
                  scale: canSend ? 1 : 0.9,
                  opacity: canSend ? 1 : 0.3,
                }}
                exit={{ scale: 0.8, opacity: 0 }}
                transition={{ duration: 0.15 }}
              >
                <Button
                  onClick={handleSend}
                  disabled={!canSend}
                  size="icon"
                  className={cn(
                    "h-8 w-8 rounded-full transition-colors",
                    canSend
                      ? "bg-white text-black hover:bg-white/90"
                      : "bg-foreground/15 text-foreground/30 cursor-not-allowed",
                  )}
                  aria-label="Send message"
                >
                  <ArrowUp className="h-4 w-4" strokeWidth={2.5} />
                </Button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Disclaimer */}
      <p className="text-center text-[11px] text-foreground/25 mt-2 select-none">
        RAGnostic can make mistakes. Check important info.
      </p>
    </div>
  );
}

function TooltipButton({
  children,
  active,
  onClick,
  label,
}: {
  children: React.ReactNode;
  active?: boolean;
  onClick?: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      aria-pressed={active}
      className={cn(
        "flex h-8 w-8 items-center justify-center rounded-full transition-colors",
        active
          ? "text-sky-400 hover:bg-sky-400/10"
          : "text-foreground/35 hover:bg-foreground/10 hover:text-foreground/60",
      )}
    >
      {children}
    </button>
  );
}
