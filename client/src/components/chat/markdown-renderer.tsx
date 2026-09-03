"use client";

import React, { useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils";
import "highlight.js/styles/github-dark.css";

interface MarkdownRendererProps {
  content: string;
  className?: string;
  onCitation?: (n: number) => void;
  activeCitation?: number | null;
}

/** Wrap [n] citation markers in links — but never inside fenced code blocks. */
function linkifyCitations(content: string): string {
  const parts = content.split(/(```[\s\S]*?(?:```|$))/g);
  return parts
    .map((part, i) =>
      i % 2 === 1
        ? part
        : part.replace(/\[(\d{1,2})\](?!\()/g, (_m, n) => `[${n}](#cite-${n})`),
    )
    .join("");
}

function CodeBlock({ children }: { children?: React.ReactNode }) {
  const preRef = useRef<HTMLPreElement>(null);
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    const text = preRef.current?.innerText ?? "";
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      // clipboard unavailable (e.g. insecure context) — ignore
    }
  };

  return (
    <div className="group/code relative mb-3">
      <pre
        ref={preRef}
        className="hljs rounded-lg bg-[#16162a] border border-border/50 overflow-x-auto !my-0 py-3.5 px-4 text-[13px]"
      >
        {children}
      </pre>
      <button
        type="button"
        onClick={handleCopy}
        aria-label={copied ? "Copied" : "Copy code"}
        className="absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-md border border-border/40 bg-[#1f1f36]/90 text-foreground/45 opacity-0 transition-all hover:text-foreground/85 group-hover/code:opacity-100"
      >
        {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
    </div>
  );
}

export function MarkdownRenderer({
  content,
  className,
  onCitation,
  activeCitation,
}: MarkdownRendererProps) {
  return (
    <div className={cn("prose-chat", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeHighlight, { detect: false, ignoreMissing: true }]]}
        components={{
          h1: ({ children }) => (
            <h1 className="text-xl font-bold text-foreground mb-3 mt-4 first:mt-0">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-lg font-semibold text-foreground mb-2 mt-4 first:mt-0">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-base font-semibold text-foreground mb-2 mt-3 first:mt-0">
              {children}
            </h3>
          ),
          p: ({ children }) => (
            <p className="text-[15px] leading-[1.7] text-foreground/90 mb-3 last:mb-0">
              {children}
            </p>
          ),
          ul: ({ children }) => (
            <ul className="list-disc list-outside ml-5 mb-3 space-y-1 text-[15px] leading-[1.7] text-foreground/90">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal list-outside ml-5 mb-3 space-y-1 text-[15px] leading-[1.7] text-foreground/90">
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li className="text-foreground/90">{children}</li>
          ),
          code: ({ className, children, ...props }) => {
            const isInline = !className?.includes("language-") && !className?.includes("hljs");
            if (isInline) {
              return (
                <code
                  className="rounded bg-muted px-1.5 py-0.5 text-[13px] font-mono text-foreground/90"
                  {...props}
                >
                  {children}
                </code>
              );
            }
            return (
              <code
                className={cn(
                  "font-mono text-[13px] text-foreground/90 bg-transparent",
                  className,
                )}
                {...props}
              >
                {children}
              </code>
            );
          },
          pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
          strong: ({ children }) => (
            <strong className="font-semibold text-foreground">{children}</strong>
          ),
          em: ({ children }) => (
            <em className="italic text-foreground/90">{children}</em>
          ),
          a: ({ href, children }) => {
            const match = href?.match(/^#cite-(\d{1,2})$/);
            if (match && onCitation) {
              const n = Number(match[1]);
              const active = activeCitation === n;
              return (
                <button
                  type="button"
                  onClick={() => onCitation(n)}
                  aria-label={`Show source ${n}`}
                  className={cn(
                    "mx-0.5 inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full border align-super px-1 text-[10px] font-semibold leading-none transition-colors",
                    active
                      ? "border-sky-400/70 bg-sky-400/20 text-sky-300"
                      : "border-border/60 bg-foreground/[0.06] text-foreground/55 hover:border-sky-400/50 hover:bg-sky-400/10 hover:text-sky-300",
                  )}
                >
                  {n}
                </button>
              );
            }
            return (
              <a
                href={href}
                className="text-blue-400 hover:text-blue-300 underline underline-offset-2"
                target="_blank"
                rel="noopener noreferrer"
              >
                {children}
              </a>
            );
          },
          hr: () => <hr className="border-border my-4" />,
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-border pl-4 my-3 text-foreground/70 italic">
              {children}
            </blockquote>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto mb-3 rounded-lg border border-border/50">
              <table className="w-full border-collapse text-[14px]">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border-b border-border/60 bg-foreground/[0.04] px-3 py-2 text-left font-semibold text-foreground/85">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border-b border-border/30 px-3 py-2 text-foreground/80 align-top">
              {children}
            </td>
          ),
        }}
      >
        {linkifyCitations(content)}
      </ReactMarkdown>
    </div>
  );
}
