"use client";

import { memo, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { MessageCircleQuestion, X } from "lucide-react";
import { MessageActions } from "./message-actions";
import { ThinkingPanel } from "./thinking-panel";
import type { SourceChunk } from "@/types";

// Markdown parsing + highlight.js are heavy — load them only when needed
const MarkdownRenderer = dynamic(
  () => import("./markdown-renderer").then((m) => m.MarkdownRenderer),
  { ssr: false, loading: () => <div className="h-16 animate-pulse rounded-lg bg-secondary/60" /> },
);

interface AssistantMessageProps {
  content: string;
  isStreaming?: boolean;
  onRegenerate?: () => void;
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

export const AssistantMessage = memo(function AssistantMessage({
  content,
  isStreaming,
  onRegenerate,
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
    <div
      className="offscreen-msg group py-2.5"
      role="article"
      aria-label="Assistant message"
    >
      <ThinkingPanel reasoning={reasoning} isActive={Boolean(isStreaming)} />

      {/* Live pipeline status before the first token arrives */}
      {showStageStatus && (
        <div className="flex items-center gap-2 py-1 text-[13px] text-foreground/50">
          <span className="flex gap-1" aria-hidden>
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="h-1.5 w-1.5 animate-pulse rounded-full bg-foreground/35"
                style={{ animationDelay: `${i * 180}ms` }}
              />
            ))}
          </span>
          <span>{STAGE_LABELS[stage || "starting"] || "Working…"}</span>
        </div>
      )}

      {content && (
        <>
          <MarkdownRenderer
            content={displayContent}
            onCitation={handleCitation}
            activeCitation={activeCitation}
          />
          {isStreaming && (
            <span
              className="ml-0.5 inline-block h-4 w-[2px] animate-pulse bg-foreground/50 align-[-2px]"
              aria-hidden
            />
          )}
        </>
      )}

      {/* Citation detail */}
      {citedSource && !isStreaming && (
        <div className="mt-2 rounded-xl border border-border bg-card p-3">
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <p className="mono-meta text-[11px] text-foreground/70">
              Source [{activeCitation}]
              {citedSource.metadata?.source
                ? ` · ${String(citedSource.metadata.source)}`
                : ""}
            </p>
            <button
              type="button"
              onClick={() => setActiveCitation(null)}
              aria-label="Close source preview"
              className="flex h-7 w-7 items-center justify-center rounded-md text-foreground/40 hover:bg-secondary hover:text-foreground/70"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <p className="max-h-40 overflow-y-auto whitespace-pre-wrap text-xs leading-relaxed text-foreground/65">
            {citedSource.text}
          </p>
        </div>
      )}

      {/* Action bar — always visible on touch, hover-reveal on desktop */}
      {!isStreaming && content && (
        <div className="transition-opacity [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100 [@media(hover:hover)]:focus-within:opacity-100">
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
        <div className="mt-2 flex flex-col items-start gap-1.5">
          {followUps.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => onFollowUp(q)}
              className="flex w-fit max-w-full items-start gap-2 rounded-lg border border-border bg-card px-3 py-2 text-left text-[13px] text-foreground/65 transition-colors hover:bg-secondary hover:text-foreground"
            >
              <MessageCircleQuestion className="mt-0.5 h-3.5 w-3.5 shrink-0 text-foreground/40" />
              <span className="line-clamp-2">{q}</span>
            </button>
          ))}
        </div>
      )}

      {!isStreaming && content && (
        <div className="mono-meta mt-2.5 flex flex-wrap gap-1.5 text-[11px] text-foreground/45">
          {retrieval && typeof retrieval.depth === "number" && (
            <span className="rounded-md border border-border bg-card px-2 py-1">
              {retrieval.depth}-hop · {typeof retrieval.confidence === "number" ? retrieval.confidence.toFixed(2) : "--"} · {retrieval.strategy || (retrieval.depth===0?"ZERO_HOP":retrieval.depth===1?"ONE_HOP":"TWO_HOP")}
            </span>
          )}
          {!retrieval?.strategy && selectedArm && (
            <span className="rounded-md border border-border bg-card px-2 py-1">
              {selectedArm.replaceAll("_", " ")}
            </span>
          )}
          {typeof latencyMs === "number" && (
            <span className="rounded-md border border-border bg-card px-2 py-1">
              {Math.round(latencyMs)} ms
            </span>
          )}
          {typeof reward === "number" && (
            <span className="rounded-md border border-border bg-card px-2 py-1">
              reward {reward.toFixed(2)}
            </span>
          )}
        </div>
      )}

      {/* Source skeletons while retrieval runs */}
      {showSourceSkeletons && (
        <div className="mt-2.5 flex flex-wrap gap-2" aria-hidden>
          {[64, 88, 52].map((w, i) => (
            <div
              key={i}
              style={{ width: w }}
              className="h-5 animate-pulse rounded-md bg-secondary"
            />
          ))}
        </div>
      )}

      {!isStreaming && content && sources.length > 0 && (
        <div className="mt-3 border-t border-border pt-2.5">
          <p className="mono-meta mb-2 text-[11px] uppercase tracking-wide text-foreground/40">Sources</p>
          <div className="flex flex-wrap gap-1.5">
            {sources.slice(0, 4).map((source, i) => (
              <button
                key={source.chunk_id}
                type="button"
                title={source.text}
                onClick={() => handleCitation(i + 1)}
                className={`inline-flex max-w-[220px] items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] transition-colors ${
                  activeCitation === i + 1
                    ? "border-foreground/25 bg-secondary text-foreground"
                    : "border-border bg-card text-foreground/55 hover:bg-secondary hover:text-foreground"
                }`}
              >
                <span className="mono-meta flex h-4 min-w-4 items-center justify-center rounded bg-secondary px-1 text-[10px]">
                  {i + 1}
                </span>
                <span className="truncate">{String(source.metadata?.source || source.chunk_id)}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
});
