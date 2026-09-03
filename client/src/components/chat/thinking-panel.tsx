"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { BrainCircuit, ChevronDown } from "lucide-react";

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
    <div className="mb-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded-full border border-border/40 bg-foreground/[0.03] px-2.5 py-1 text-[11px] font-medium text-foreground/55 transition-colors hover:bg-foreground/[0.07] hover:text-foreground/75"
      >
        <BrainCircuit
          className={`h-3.5 w-3.5 ${isActive ? "animate-pulse" : ""}`}
        />
        {isActive ? "Thinking…" : "Thought process"}
        <ChevronDown
          className={`h-3 w-3 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="overflow-hidden"
          >
            <div
              ref={bodyRef}
              className="mt-2 max-h-48 overflow-y-auto rounded-lg border border-border/30 bg-foreground/[0.02] px-3 py-2 text-xs leading-relaxed whitespace-pre-wrap text-foreground/50"
            >
              {reasoning}
              {isActive && (
                <span className="ml-0.5 inline-block h-3 w-[2px] animate-pulse bg-foreground/40 align-middle" />
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
