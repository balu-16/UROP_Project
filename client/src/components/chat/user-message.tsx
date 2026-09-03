"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Check, Pencil, X } from "lucide-react";

interface UserMessageProps {
  content: string;
  index?: number;
  messageId?: string;
  isStreaming?: boolean;
  onEdit?: (messageId: string, newText: string) => void;
}

export function UserMessage({
  content,
  index = 0,
  messageId,
  isStreaming,
  onEdit,
}: UserMessageProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(content);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (editing && textareaRef.current) {
      const el = textareaRef.current;
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
    }
  }, [editing]);

  const canEdit = Boolean(onEdit && messageId && !isStreaming);

  const startEdit = () => {
    if (!canEdit) return;
    setDraft(content);
    setEditing(true);
  };

  const commit = () => {
    const trimmed = draft.trim();
    setEditing(false);
    if (!trimmed || trimmed === content || !messageId) return;
    onEdit?.(messageId, trimmed);
  };

  const cancel = () => {
    setEditing(false);
    setDraft(content);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, delay: index * 0.03, ease: "easeOut" }}
      className="group flex justify-end px-4 py-3"
      role="article"
      aria-label="User message"
    >
      {editing ? (
        <div className="w-[min(560px,85%)] rounded-2xl border border-accent/30 bg-card px-3 py-2.5 shadow-lg">
          <textarea
            ref={textareaRef}
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`;
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                commit();
              } else if (e.key === "Escape") {
                cancel();
              }
            }}
            rows={1}
            aria-label="Edit message"
            className="w-full resize-none bg-transparent text-[15px] leading-[1.6] text-foreground outline-none"
          />
          <div className="mt-1.5 flex items-center justify-end gap-1.5">
            <button
              type="button"
              onClick={cancel}
              aria-label="Cancel edit"
              className="flex h-7 items-center gap-1 rounded-full px-2.5 text-xs text-foreground/50 transition-colors hover:bg-white/10 hover:text-foreground/80"
            >
              <X className="h-3.5 w-3.5" /> Cancel
            </button>
            <button
              type="button"
              onClick={commit}
              disabled={!draft.trim()}
              aria-label="Save and resend"
              className="flex h-7 items-center gap-1 rounded-full bg-white px-3 text-xs font-medium text-black transition-opacity disabled:opacity-40"
            >
              <Check className="h-3.5 w-3.5" /> Send
            </button>
          </div>
        </div>
      ) : (
        <div className="flex max-w-[70%] items-start gap-1.5">
          <button
            type="button"
            onClick={startEdit}
            disabled={!canEdit}
            aria-label="Edit and resend message"
            className="mt-2 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-foreground/30 opacity-0 transition-all hover:bg-foreground/10 hover:text-foreground/70 group-hover:opacity-100 disabled:pointer-events-none"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          <div className="whitespace-pre-wrap break-words rounded-2xl bg-secondary border border-border/40 px-4 py-2.5 text-[15px] leading-[1.6] text-foreground shadow-sm">
            {content}
          </div>
        </div>
      )}
    </motion.div>
  );
}
