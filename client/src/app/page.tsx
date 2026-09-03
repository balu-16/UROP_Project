"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import {
  ArrowRight,
  Crosshair,
  GitBranch,
  Sparkles,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";

const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  show: (delay: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, delay, ease: [0.21, 0.47, 0.32, 0.98] as const },
  }),
};

const features = [
  {
    icon: Crosshair,
    title: "Adaptive Retrieval",
    description:
      "A deterministic threshold policy picks the retrieval depth per query — semantic search, plus one or two graph expansions when confidence is low.",
  },
  {
    icon: GitBranch,
    title: "Graph-RAG Expansion",
    description:
      "Entities are extracted and linked into a knowledge graph, pulling related context your documents never stated together.",
  },
  {
    icon: Zap,
    title: "Real-time Streaming",
    description:
      "Token-by-token responses over server-sent events, with retrieval diagnostics and latency visible on every answer.",
  },
  {
    icon: Sparkles,
    title: "Structured Answers",
    description:
      "Every response is well-formed Markdown — summaries, headings, tables, and cited sources you can verify at a glance.",
  },
];

const steps = [
  {
    number: "01",
    title: "Ask anything",
    description:
      "Drop in your documents and query them naturally. Ingestion chunks, embeds, and indexes everything automatically.",
  },
  {
    number: "02",
    title: "Retrieve & expand",
    description:
      "Low-confidence matches get expanded through the entity graph for deeper context, then the policy settles on 0, 1, or 2 hops.",
  },
  {
    number: "03",
    title: "Get structured answers",
    description:
      "Answers stream back as clean Markdown with source citations, so every claim traces back to your documents.",
  },
];

function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      aria-hidden
    >
      <circle cx="5" cy="18" r="2.4" fill="currentColor" opacity="0.55" />
      <circle cx="12" cy="5" r="2.4" fill="currentColor" />
      <circle cx="19" cy="15" r="2.4" fill="currentColor" opacity="0.75" />
      <path
        d="M6.3 16.2L10.8 7.2M13.8 6.6l3.9 6.4M7.4 17.4l9.2-1.8"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        opacity="0.45"
      />
    </svg>
  );
}

export default function LandingPage() {
  return (
    <div className="relative min-h-dvh bg-background text-foreground">
      {/* Nav */}
      <header className="sticky top-0 z-40 border-b border-border bg-background">
        <nav className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link href="/" className="flex items-center gap-2.5" aria-label="RAGnostic home">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-card text-foreground">
              <LogoMark />
            </span>
            <span className="text-[15px] font-semibold tracking-tight">
              RAGnostic
            </span>
          </Link>

          <div className="hidden items-center gap-7 text-sm text-foreground/60 md:flex">
            <a href="#features" className="transition-colors hover:text-foreground">
              Features
            </a>
            <a href="#how-it-works" className="transition-colors hover:text-foreground">
              How it works
            </a>
          </div>

          <Button asChild size="sm" className="gap-1.5">
            <Link href="/chat">
              Launch app
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </Button>
        </nav>
      </header>

      <main className="relative">
        {/* Hero */}
        <section className="mx-auto flex max-w-3xl flex-col items-center px-4 pb-16 pt-16 text-center sm:px-6 sm:pt-24">
          <motion.div variants={fadeUp} initial="hidden" animate="show" custom={0}>
            <span className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-xs text-foreground/60">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              Adaptive RAG · Graph expansion · Threshold policy
            </span>
          </motion.div>

          <motion.h1
            variants={fadeUp}
            initial="hidden"
            animate="show"
            custom={0.08}
            className="mt-6 max-w-2xl text-balance text-4xl font-semibold leading-[1.1] tracking-tight sm:text-5xl"
          >
            Answers grounded in your documents, not guesses.
          </motion.h1>

          <motion.p
            variants={fadeUp}
            initial="hidden"
            animate="show"
            custom={0.16}
            className="mt-5 max-w-xl text-balance text-base leading-relaxed text-foreground/60 sm:text-lg"
          >
            RAGnostic measures retrieval confidence for every question,
            expands context through a knowledge graph, and streams structured,
            citable answers in real time.
          </motion.p>

          <motion.div
            variants={fadeUp}
            initial="hidden"
            animate="show"
            custom={0.24}
            className="mt-8 flex w-full flex-col items-center justify-center gap-3 sm:w-auto sm:flex-row"
          >
            <Button asChild size="lg" className="w-full gap-2 px-6 sm:w-auto">
              <Link href="/chat">
                Start chatting
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <Button
              asChild
              size="lg"
              variant="outline"
              className="w-full px-6 sm:w-auto"
            >
              <a href="#features">Explore features</a>
            </Button>
          </motion.div>

          <motion.div
            variants={fadeUp}
            initial="hidden"
            animate="show"
            custom={0.32}
            className="mt-12 w-full max-w-3xl"
          >
            <div className="relative overflow-hidden rounded-xl border border-border bg-card">
              <div className="p-5 text-left sm:p-6">
                <div className="flex items-center gap-1.5 border-b border-border pb-3">
                  <span className="h-2.5 w-2.5 rounded-full bg-foreground/15" />
                  <span className="h-2.5 w-2.5 rounded-full bg-foreground/15" />
                  <span className="h-2.5 w-2.5 rounded-full bg-foreground/15" />
                  <span className="mono-meta ml-3 text-[11px] text-foreground/40">ragnostic — chat</span>
                </div>
                <div className="space-y-4 pt-4 text-sm leading-relaxed">
                  <div className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-secondary px-4 py-2.5 text-foreground/90">
                    What changed between v1 and v2 of the spec?
                  </div>
                  <div className="flex items-start gap-3">
                    <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-border bg-background text-foreground/70">
                      <Sparkles className="h-3.5 w-3.5" />
                    </span>
                    <div className="min-w-0 space-y-2 text-foreground/75">
                      <p className="font-medium text-foreground">
                        Three changes separate v2 from v1:
                      </p>
                      <ul className="list-disc space-y-1 pl-5">
                        <li>
                          <strong className="font-medium text-foreground">Auth flow</strong> moved to refresh rotation [1]
                        </li>
                        <li>
                          <strong className="font-medium text-foreground">Rate limits</strong> raised to 90 req/min [2]
                        </li>
                        <li>
                          <strong className="font-medium text-foreground">Webhooks</strong> added for indexing events [2]
                        </li>
                      </ul>
                      <p className="mono-meta text-[11px] text-foreground/40">
                        Sources: spec-v2.md · changelog.md
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        </section>

        {/* Features */}
        <section id="features" className="border-t border-border">
          <div className="mx-auto max-w-6xl scroll-mt-20 px-4 py-16 sm:px-6 sm:py-20">
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ duration: 0.4 }}
              className="mx-auto max-w-2xl text-center"
            >
              <h2 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">
                Retrieval that adapts, answers you can trust
              </h2>
              <p className="mt-3 text-foreground/60">
                Most chatbots guess. RAGnostic measures retrieval confidence
                and expands depth only when the evidence demands it.
              </p>
            </motion.div>

            <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {features.map((feature) => (
                <motion.div
                  key={feature.title}
                  initial={{ opacity: 0, y: 12 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: "-60px" }}
                  transition={{ duration: 0.4 }}
                  className="rounded-xl border border-border bg-card p-5"
                >
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-background text-foreground/80">
                    <feature.icon className="h-4 w-4" />
                  </span>
                  <h3 className="mt-4 text-[15px] font-semibold tracking-tight">
                    {feature.title}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-foreground/60">
                    {feature.description}
                  </p>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* How it works */}
        <section id="how-it-works" className="border-t border-border">
          <div className="mx-auto max-w-6xl scroll-mt-20 px-4 py-16 sm:px-6 sm:py-20">
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ duration: 0.4 }}
              className="mx-auto max-w-2xl text-center"
            >
              <h2 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">
                From upload to insight in three steps
              </h2>
            </motion.div>

            <div className="relative mt-10 grid gap-8 md:grid-cols-3 md:gap-6">
              {steps.map((step) => (
                <motion.div
                  key={step.number}
                  initial={{ opacity: 0, y: 12 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: "-60px" }}
                  transition={{ duration: 0.4 }}
                  className="relative"
                >
                  <span className="mono-meta text-xs text-foreground/40">
                    {step.number}
                  </span>
                  <h3 className="mt-2 text-[15px] font-semibold tracking-tight">{step.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-foreground/60">
                    {step.description}
                  </p>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="border-t border-border">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ duration: 0.4 }}
              className="rounded-2xl border border-border bg-card px-6 py-12 text-center sm:px-12 sm:py-16"
            >
              <h2 className="mx-auto max-w-xl text-balance text-2xl font-semibold tracking-tight sm:text-3xl">
                Ready to interrogate your documents?
              </h2>
              <p className="mx-auto mt-3 max-w-lg text-foreground/60">
                Sign up in seconds, index your first document, and watch adaptive
                retrieval find what keyword search never could.
              </p>
              <Button asChild size="lg" className="mt-7 gap-2 px-6">
                <Link href="/chat">
                  Launch RAGnostic
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
            </motion.div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-4 py-6 text-sm text-foreground/50 sm:flex-row sm:px-6">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-md border border-border bg-card text-foreground/70">
              <LogoMark className="h-3.5 w-3.5" />
            </span>
            <span className="font-medium text-foreground/70">RAGnostic</span>
          </div>
          <p className="text-[13px]">Adaptive retrieval-augmented generation.</p>
        </div>
      </footer>
    </div>
  );
}
