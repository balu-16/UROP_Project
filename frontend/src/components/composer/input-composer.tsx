"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Plus, ArrowUp, StopCircle, Mic } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface InputComposerProps {
  onSend: (message: string) => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
}

export function InputComposer({
  onSend,
  onStop,
  isStreaming,
  disabled,
}: InputComposerProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

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
    if (!trimmed || isStreaming) return;
    onSend(trimmed);
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

  const canSend = value.trim().length > 0 && !isStreaming;

  return (
    <div className="w-full max-w-[768px] mx-auto px-4">
      <motion.div
        initial={false}
        animate={{
          borderColor: value
            ? "rgba(255,255,255,0.15)"
            : "rgba(255,255,255,0.08)",
        }}
        className={cn(
          "relative flex items-end gap-2 rounded-3xl border bg-[#2f2f3d]/80 backdrop-blur-xl px-4 py-3",
          "shadow-[0_0_0_1px_rgba(255,255,255,0.05),0_2px_12px_rgba(0,0,0,0.3)]",
          "transition-shadow duration-200",
          "focus-within:shadow-[0_0_0_1px_rgba(255,255,255,0.12),0_4px_20px_rgba(0,0,0,0.4)]",
        )}
      >
        {/* Left: Attach button */}
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0 text-foreground/40 hover:text-foreground/70 rounded-full -ml-1"
          aria-label="Attach file"
          disabled={disabled}
        >
          <Plus className="h-5 w-5" />
        </Button>

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
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
          {/* Voice input */}
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-foreground/40 hover:text-foreground/70 rounded-full"
            aria-label="Voice input"
            disabled={disabled}
          >
            <Mic className="h-4 w-4" />
          </Button>

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
      </motion.div>

      {/* Disclaimer */}
      <p className="text-center text-[11px] text-foreground/25 mt-2 select-none">
        RAGnostic can make mistakes. Check important info.
      </p>
    </div>
  );
}
