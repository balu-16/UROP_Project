"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import {
  ArrowUp,
  Square,
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
  const draftTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const draftKey = `ragnostic_draft_${sessionId || "new"}`;

  /* Restore saved draft when the session changes */
  useEffect(() => {
    try {
      setValue(window.localStorage.getItem(draftKey) || "");
    } catch {
      setValue("");
    }
    return () => {
      if (draftTimerRef.current) clearTimeout(draftTimerRef.current);
    };
  }, [draftKey]);

  const setValuePersisted = useCallback(
    (next: string) => {
      setValue(next);
      // Debounced persist — avoids synchronous localStorage writes per keystroke
      if (draftTimerRef.current) clearTimeout(draftTimerRef.current);
      draftTimerRef.current = setTimeout(() => {
        try {
          if (next) window.localStorage.setItem(draftKey, next);
          else window.localStorage.removeItem(draftKey);
        } catch {
          // storage unavailable — draft simply won't persist
        }
      }, 300);
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
    if (draftTimerRef.current) clearTimeout(draftTimerRef.current);
    try {
      window.localStorage.removeItem(draftKey);
    } catch {
      // ignore
    }
    onSend(trimmed, deepReasoning);
    setValue("");
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
    <div className="mx-auto w-full max-w-[768px] px-4">
      <div
        className={cn(
          "relative flex items-end gap-1.5 rounded-[24px] border border-border bg-card px-3 py-2.5 shadow-subtle",
          "transition-colors duration-150",
          "focus-within:border-foreground/20",
        )}
      >
        {/* Left: Attach button */}
        <Button
          variant="ghost"
          size="icon"
          className="h-9 w-9 shrink-0 rounded-full text-foreground/50 hover:bg-secondary hover:text-foreground"
          aria-label="Attach documents"
          title="Attach documents (indexed into this chat only)"
          disabled={disabled || uploading}
          onClick={() => fileInputRef.current?.click()}
        >
          {uploading ? (
            <Loader2 className="h-[18px] w-[18px] animate-spin" />
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
            "flex-1 resize-none bg-transparent py-1.5",
            "text-base leading-[1.5] text-foreground outline-none sm:text-[15px]",
            "min-h-[24px] max-h-[200px]",
            "placeholder:text-foreground/40",
          )}
          aria-label="Message input"
        />

        {/* Right: Reasoning segmented control + Send / Stop */}
        <div className="flex shrink-0 items-center gap-1.5">
          <div
            className="hidden items-center rounded-full border border-border bg-background p-0.5 sm:flex"
            role="group"
            aria-label="Reasoning mode"
          >
            <button
              type="button"
              onClick={() => setDeepReasoning(false)}
              aria-pressed={!deepReasoning}
              title="Fast mode: skip extended reasoning"
              className={cn(
                "flex h-7 items-center gap-1 rounded-full px-2.5 text-[11px] font-medium transition-colors",
                !deepReasoning
                  ? "bg-secondary text-foreground"
                  : "text-foreground/45 hover:text-foreground/70",
              )}
            >
              <Zap className="h-3 w-3" />
              Fast
            </button>
            <button
              type="button"
              onClick={() => setDeepReasoning(true)}
              aria-pressed={deepReasoning}
              title="Deep mode: model reasons step by step"
              className={cn(
                "flex h-7 items-center gap-1 rounded-full px-2.5 text-[11px] font-medium transition-colors",
                deepReasoning
                  ? "bg-secondary text-foreground"
                  : "text-foreground/45 hover:text-foreground/70",
              )}
            >
              <BrainCircuit className="h-3 w-3" />
              Deep
            </button>
          </div>

          {/* Compact reasoning toggle for mobile */}
          <button
            type="button"
            onClick={() => setDeepReasoning((v) => !v)}
            aria-pressed={deepReasoning}
            title={deepReasoning ? "Deep mode on" : "Fast mode on"}
            className={cn(
              "flex h-9 w-9 items-center justify-center rounded-full transition-colors sm:hidden",
              deepReasoning
                ? "text-foreground"
                : "text-foreground/40",
            )}
          >
            {deepReasoning ? (
              <BrainCircuit className="h-4 w-4" />
            ) : (
              <Zap className="h-4 w-4" />
            )}
          </button>

          {isStreaming ? (
            <Button
              onClick={onStop}
              size="icon"
              className="h-9 w-9 rounded-full bg-foreground text-background hover:bg-foreground/90"
              aria-label="Stop generating"
            >
              <Square className="h-3.5 w-3.5 fill-current" />
            </Button>
          ) : (
            <Button
              onClick={handleSend}
              disabled={!canSend}
              size="icon"
              className={cn(
                "h-9 w-9 rounded-full transition-colors",
                canSend
                  ? "bg-foreground text-background hover:bg-foreground/90"
                  : "bg-secondary text-foreground/30",
              )}
              aria-label="Send message"
            >
              <ArrowUp className="h-4 w-4" strokeWidth={2.5} />
            </Button>
          )}
        </div>
      </div>

      {/* Disclaimer */}
      <p className="mt-2 select-none text-center text-[11px] text-foreground/35">
        RAGnostic can make mistakes. Check important info.
      </p>
    </div>
  );
}
