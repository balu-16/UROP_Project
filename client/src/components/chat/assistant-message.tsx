"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { motion } from "framer-motion";
import { MessageCircleQuestion, X } from "lucide-react";
import { LogoMark } from "@/components/logo-mark";
import { MessageActions } from "./message-actions";
import { ThinkingPanel } from "./thinking-panel";
import type { SourceChunk } from "@/types";

// Markdown parsing + highlight.js are heavy — load them only when needed
const MarkdownRenderer = dynamic(
  () => import("./markdown-renderer").then((m) => m.MarkdownRenderer),
  { ssr: false },
);

interface AssistantMessageProps {
  content: string;
  isStreaming?: boolean;
  onRegenerate?: () => void;
  index?: number;
  selectedArm?: string;
  sources?: SourceChunk[];
  reward?: number;
  latencyMs?: number;
  messageId?: string;
  sessionId?: string;
  reasoning?: string;
  stage?: string;
  followUps?: string[];
  onFollowUp?: (question: string) => void;
  retrieval?: { depth?: number; confidence?: number; strategy?: string; initial_confidence?: number };
}

const STAGE_LABELS: Record<string, string> = {
  starting: "Preparing…",
  retrieving: "Searching documents…",
  thinking: "Thinking…",
  writing: "Writing…",
};

/** Throttle high-frequency value updates while `active`; flush instantly when done. */
function useThrottledValue<T>(value: T, active: boolean, intervalMs = 150): T {
  const [displayed, setDisplayed] = useState(value);
  const lastUpdateRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latestRef = useRef(value);
  latestRef.current = value;

  useEffect(() => {
    if (!active) {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = null;
      setDisplayed(value);
      return;
    }
    const elapsed = Date.now() - lastUpdateRef.current;
    if (elapsed >= intervalMs && !timerRef.current) {
      lastUpdateRef.current = Date.now();
      setDisplayed(value);
      return;
    }
    if (!timerRef.current) {
      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        lastUpdateRef.current = Date.now();
        setDisplayed(latestRef.current);
      }, Math.max(intervalMs - elapsed, 16));
    }
  }, [value, active, intervalMs]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return displayed;
}

export function AssistantMessage({
  content,
  isStreaming,
  onRegenerate,
  index = 0,
  selectedArm,
  sources = [],
  reward,
  latencyMs,
  messageId,
  sessionId,
  reasoning,
  stage,
  followUps,
  onFollowUp,
  retrieval,
}: AssistantMessageProps) {
  const [activeCitation, setActiveCitation] = useState<number | null>(null);
  // While streaming, re-parse markdown at most every ~150ms for smooth rendering
  const displayContent = useThrottledValue(content, Boolean(isStreaming));

  const handleCitation = (n: number) => {
    if (n < 1 || n > sources.length) return;
    setActiveCitation((prev) => (prev === n ? null : n));
  };

  const citedSource =
    activeCitation !== null ? sources[activeCitation - 1] : null;
  const showStageStatus = isStreaming && !content;
  const showSourceSkeletons =
    isStreaming && !sources.length && stage !== "thinking" && stage !== "writing";

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: index * 0.05, ease: "easeOut" }}
      className="group flex items-start gap-3 px-4 py-3"
      role="article"
      aria-label="Assistant message"
    >
        {/* Avatar */}
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent/12 border border-accent/25 text-accent mt-0.5 shadow-[0_0_16px_-6px] shadow-accent/40">
        <LogoMark size={16} />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0 max-w-[720px]">
        <ThinkingPanel reasoning={reasoning} isActive={Boolean(isStreaming)} />

        {/* Live pipeline status before the first token arrives */}
        {showStageStatus && (
          <div className="flex items-center gap-2 py-1 text-[13px] text-foreground/45">
            <span className="flex gap-1">
              {[0, 1, 2].map((i) => (
                <motion.span
                  key={i}
                  className="h-1.5 w-1.5 rounded-full bg-foreground/40"
                  animate={{ opacity: [0.25, 1, 0.25] }}
                  transition={{
                    duration: 1.1,
                    repeat: Infinity,
                    delay: i * 0.18,
                    ease: "easeInOut",
                  }}
                />
              ))}
            </span>
            <span>{STAGE_LABELS[stage || "starting"] || "Working…"}</span>
          </div>
        )}

        {content && (
          <MarkdownRenderer
            content={displayContent}
            onCitation={handleCitation}
            activeCitation={activeCitation}
          />
        )}

        {/* Streaming cursor */}
        {isStreaming && (
          <motion.span
            className="inline-block h-4 w-[2px] bg-foreground/60 ml-0.5 -mb-[2px]"
            animate={{ opacity: [1, 0] }}
            transition={{ duration: 0.6, repeat: Infinity, ease: "easeInOut" }}
          />
        )}

        {/* Citation detail popover */}
        {citedSource && !isStreaming && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.15 }}
            className="mt-2 rounded-xl border border-border/50 bg-card/90 p-3 backdrop-blur-sm"
          >
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <p className="text-xs font-medium text-sky-300/90">
                Source [{activeCitation}]
                {citedSource.metadata?.source
                  ? ` · ${String(citedSource.metadata.source)}`
                  : ""}
              </p>
              <button
                type="button"
                onClick={() => setActiveCitation(null)}
                aria-label="Close source preview"
                className="rounded p-0.5 text-foreground/35 hover:text-foreground/70"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
            <p className="max-h-40 overflow-y-auto whitespace-pre-wrap text-xs leading-relaxed text-foreground/65">
              {citedSource.text}
            </p>
          </motion.div>
        )}

        {/* Action bar — visible on hover */}
        {!isStreaming && content && (
          <div className="opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity duration-200">
            <MessageActions
              onRegenerate={onRegenerate}
              content={content}
              messageId={messageId}
              sessionId={sessionId}
            />
          </div>
        )}

        {/* Suggested follow-ups */}
        {!isStreaming && followUps && followUps.length > 0 && onFollowUp && (
          <div className="mt-2 flex flex-col gap-1.5">
            {followUps.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => onFollowUp(q)}
                className="group/fu flex w-fit max-w-full items-start gap-2 rounded-xl border border-border/40 bg-foreground/[0.03] px-3 py-1.5 text-left text-[13px] text-foreground/65 transition-colors hover:border-border/70 hover:bg-foreground/[0.07] hover:text-foreground/90"
              >
                <MessageCircleQuestion className="mt-0.5 h-3.5 w-3.5 shrink-0 text-foreground/35 group-hover/fu:text-sky-400/80" />
                <span className="line-clamp-2">{q}</span>
              </button>
            ))}
          </div>
        )}

        {!isStreaming && content && (
          <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-foreground/45">
            {retrieval && typeof retrieval.depth === "number" && (
              <span className="rounded-md bg-sky-500/10 text-sky-300 px-2 py-1 border border-sky-500/20">
                {retrieval.depth}-hop · {typeof retrieval.confidence === "number" ? retrieval.confidence.toFixed(2) : "--"} · {retrieval.strategy || (retrieval.depth===0?"ZERO_HOP":retrieval.depth===1?"ONE_HOP":"TWO_HOP")}
              </span>
            )}
            {!retrieval?.strategy && selectedArm && (
              <span className="rounded-md bg-foreground/5 px-2 py-1">
                {selectedArm.replaceAll("_", " ")}
              </span>
            )}
            {typeof latencyMs === "number" && (
              <span className="rounded-md bg-foreground/5 px-2 py-1">
                {Math.round(latencyMs)} ms
              </span>
            )}
            {typeof reward === "number" && (
              <span className="rounded-md bg-foreground/5 px-2 py-1">
                reward {reward.toFixed(2)}
              </span>
            )}
          </div>
        )}

        {/* Source skeletons while retrieval runs */}
        {showSourceSkeletons && (
          <div className="mt-3 flex flex-wrap gap-2">
            {[64, 88, 52].map((w, i) => (
              <div
                key={i}
                style={{ width: w }}
                className="h-5 animate-pulse rounded-md bg-foreground/[0.06]"
              />
            ))}
          </div>
        )}

        {!isStreaming && content && sources.length > 0 && (
          <div className="mt-3 pt-3 border-t border-border/30">
            <p className="text-xs text-foreground/30 mb-2">Sources</p>
            <div className="flex flex-wrap gap-2">
              {sources.slice(0, 4).map((source, i) => (
                <button
                  key={source.chunk_id}
                  type="button"
                  title={source.text}
                  onClick={() => handleCitation(i + 1)}
                  className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] transition-colors ${
                    activeCitation === i + 1
                      ? "bg-sky-400/10 text-sky-300"
                      : "bg-foreground/5 text-foreground/50 hover:text-foreground/70 hover:bg-foreground/[0.08]"
                  }`}
                >
                  <span className="h-3 w-3 rounded-sm bg-foreground/20" />
                  {String(source.metadata?.source || source.chunk_id)}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
}
