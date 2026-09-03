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
        className="hljs overflow-x-auto rounded-lg border border-border bg-secondary/60 !my-0 px-4 py-3.5 text-[13px] leading-relaxed"
      >
        {children}
      </pre>
      <button
        type="button"
        onClick={handleCopy}
        aria-label={copied ? "Copied" : "Copy code"}
        className="absolute right-2 top-2 flex h-8 w-8 items-center justify-center rounded-md border border-border bg-card text-foreground/50 transition-colors hover:text-foreground [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover/code:opacity-100 [@media(hover:hover)]:focus-within:opacity-100"
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
            <h1 className="mb-3 mt-4 text-xl font-semibold tracking-tight text-foreground first:mt-0">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="mb-2 mt-4 text-lg font-semibold tracking-tight text-foreground first:mt-0">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="mb-2 mt-3 text-base font-semibold tracking-tight text-foreground first:mt-0">
              {children}
            </h3>
          ),
          p: ({ children }) => (
            <p className="mb-3 text-[15px] leading-[1.7] text-foreground/90 last:mb-0">
              {children}
            </p>
          ),
          ul: ({ children }) => (
            <ul className="mb-3 ml-5 list-outside list-disc space-y-1 text-[15px] leading-[1.7] text-foreground/90">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="mb-3 ml-5 list-outside list-decimal space-y-1 text-[15px] leading-[1.7] text-foreground/90">
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
                  className="rounded-md border border-border bg-secondary px-1.5 py-0.5 font-mono text-[13px] text-foreground"
                  {...props}
                >
                  {children}
                </code>
              );
            }
            return (
              <code
                className={cn(
                  "bg-transparent font-mono text-[13px] text-foreground",
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
                    "mx-0.5 inline-flex h-[20px] min-w-[20px] items-center justify-center rounded-md border px-1 align-super font-mono text-[10px] font-medium leading-none transition-colors",
                    active
                      ? "border-foreground/30 bg-secondary text-foreground"
                      : "border-border bg-card text-foreground/55 hover:border-foreground/25 hover:text-foreground",
                  )}
                >
                  {n}
                </button>
              );
            }
            return (
              <a
                href={href}
                className="text-foreground underline decoration-foreground/30 underline-offset-2 hover:decoration-foreground/60"
                target="_blank"
                rel="noopener noreferrer"
              >
                {children}
              </a>
            );
          },
          hr: () => <hr className="my-4 border-border" />,
          blockquote: ({ children }) => (
            <blockquote className="my-3 border-l-2 border-border pl-4 italic text-foreground/70">
              {children}
            </blockquote>
          ),
          table: ({ children }) => (
            <div className="-mx-1 overflow-x-auto px-1">
              <table className="mb-3 w-full min-w-[480px] border-collapse rounded-lg border border-border text-[14px]">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border-b border-border bg-secondary/60 px-3 py-2 text-left font-medium text-foreground">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border-b border-border/60 px-3 py-2 align-top text-foreground/80">
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
