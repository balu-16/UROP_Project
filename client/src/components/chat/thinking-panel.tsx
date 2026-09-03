"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";

interface ThinkingPanelProps {
  reasoning?: string;
  isActive: boolean;
}

export function ThinkingPanel({ reasoning, isActive }: ThinkingPanelProps) {
  const [open, setOpen] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const hasContent = Boolean(reasoning && reasoning.trim().length > 0);

  // Auto-open while thinking starts, auto-collapse once the answer streams
  useEffect(() => {
    if (isActive && hasContent) setOpen(true);
    if (!isActive) setOpen(false);
  }, [isActive, hasContent]);

  // Keep the latest reasoning line visible while open and active
  useEffect(() => {
    if (open && isActive && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [reasoning, open, isActive]);

  if (!hasContent) return null;

  return (
    <div className="mb-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="mono-meta inline-flex h-7 items-center gap-1.5 rounded-full border border-border bg-card px-2.5 text-[11px] text-foreground/55 transition-colors hover:bg-secondary hover:text-foreground"
      >
        <span className={`h-1.5 w-1.5 rounded-full ${isActive ? "animate-pulse bg-foreground/50" : "bg-foreground/30"}`} aria-hidden />
        {isActive ? "Thinking…" : "Thought process"}
        <ChevronDown
          className={`h-3 w-3 transition-transform duration-150 ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <div
          ref={bodyRef}
          className="mt-2 max-h-48 overflow-y-auto whitespace-pre-wrap rounded-lg border border-border bg-card px-3 py-2 text-xs leading-relaxed text-foreground/55"
        >
          {reasoning}
          {isActive && (
            <span className="ml-0.5 inline-block h-3 w-[2px] animate-pulse bg-foreground/40 align-middle" />
          )}
        </div>
      )}
    </div>
  );
}
