"use client";

import { memo, useEffect, useRef, useState } from "react";
import { Check, Pencil, X } from "lucide-react";
import { AttachmentChip } from "@/components/composer/attachment-chip";
import type { Attachment } from "@/types";

interface UserMessageProps {
  content: string;
  messageId?: string;
  isStreaming?: boolean;
  attachments?: Attachment[];
  onEdit?: (messageId: string, newText: string) => void;
}

export const UserMessage = memo(function UserMessage({
  content,
  messageId,
  isStreaming,
  attachments,
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
    <div
      className="offscreen-msg group flex justify-end py-2.5"
      role="article"
      aria-label="User message"
    >
      {editing ? (
        <div className="w-[min(560px,90%)] rounded-2xl border border-border bg-card px-3 py-2.5 shadow-subtle">
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
              className="flex h-8 items-center gap-1 rounded-full px-2.5 text-xs text-foreground/60 transition-colors hover:bg-secondary hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" /> Cancel
            </button>
            <button
              type="button"
              onClick={commit}
              disabled={!draft.trim()}
              aria-label="Save and resend"
              className="flex h-8 items-center gap-1 rounded-full bg-foreground px-3 text-xs font-medium text-background transition-opacity disabled:opacity-40"
            >
              <Check className="h-3.5 w-3.5" /> Send
            </button>
          </div>
        </div>
      ) : (
        <div className="flex max-w-[85%] flex-col items-end gap-2 sm:max-w-[70%]">
          {/* Attached documents — only on the message sent with them */}
          {attachments && attachments.length > 0 && (
            <div className="flex flex-col items-end gap-1.5">
              {attachments.map((a) => (
                <AttachmentChip key={a.name} name={a.name} kind={a.kind} />
              ))}
            </div>
          )}
          <div className="flex max-w-full items-start gap-1">
            <button
              type="button"
              onClick={startEdit}
              disabled={!canEdit}
              aria-label="Edit and resend message"
              className="mt-1.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-foreground/35 transition-colors hover:bg-secondary hover:text-foreground/70 disabled:pointer-events-none [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100"
            >
              <Pencil className="h-3.5 w-3.5" />
            </button>
            <div className="whitespace-pre-wrap break-words rounded-2xl rounded-br-md border border-border/60 bg-secondary px-4 py-2.5 text-[15px] leading-[1.6] text-foreground">
              {content}
            </div>
          </div>
        </div>
      )}
    </div>
  );
});
