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
  hidden: { opacity: 0, y: 24 },
  show: (delay: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, delay, ease: [0.21, 0.47, 0.32, 0.98] as const },
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
    <div className="relative min-h-screen overflow-x-clip bg-background text-foreground">
      {/* Atmosphere */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute inset-0 bg-grid bg-grid-fade" />
        <div className="glow-orb left-1/2 top-[-220px] h-[420px] w-[720px] -translate-x-1/2 bg-accent/20 animate-float-slow" />
        <div className="glow-orb right-[-160px] top-[340px] h-[360px] w-[360px] bg-violet-500/12" />
        <div className="glow-orb bottom-[-180px] left-[-120px] h-[320px] w-[320px] bg-accent/10" />
      </div>

      {/* Nav */}
      <header className="sticky top-0 z-40 border-b border-border/40 bg-background/70 backdrop-blur-xl">
        <nav className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link href="/" className="flex items-center gap-2.5" aria-label="RAGnostic home">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-accent/30 bg-accent/10 text-accent shadow-[0_0_24px_-6px] shadow-accent/40">
              <LogoMark />
            </span>
            <span className="font-display text-lg font-semibold tracking-tight">
              RAGnostic
            </span>
          </Link>

          <div className="hidden items-center gap-8 text-sm text-foreground/60 md:flex">
            <a href="#features" className="hover:text-foreground transition-colors">
              Features
            </a>
            <a href="#how-it-works" className="hover:text-foreground transition-colors">
              How it works
            </a>
          </div>

          <Button
            asChild
            size="sm"
            className="gap-1.5 bg-accent font-medium text-accent-foreground hover:bg-accent/90 shadow-[0_0_28px_-8px] shadow-accent/50"
          >
            <Link href="/chat">
              Launch app
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </Button>
        </nav>
      </header>

      <main className="relative">
        {/* Hero */}
        <section className="mx-auto flex max-w-6xl flex-col items-center px-4 pb-24 pt-20 text-center sm:px-6 sm:pt-28">
          <motion.div variants={fadeUp} initial="hidden" animate="show" custom={0}>
            <span className="inline-flex items-center gap-2 rounded-full border border-accent/25 bg-accent/8 px-3.5 py-1.5 text-xs font-medium text-accent">
              <span className="h-1.5 w-1.5 rounded-full bg-accent shadow-[0_0_8px_2px] shadow-accent/50" />
              Adaptive RAG · Graph expansion · Threshold policy
            </span>
          </motion.div>

          <motion.h1
            variants={fadeUp}
            initial="hidden"
            animate="show"
            custom={0.12}
            className="mt-7 max-w-3xl font-display text-4xl font-bold leading-[1.08] tracking-tight sm:text-6xl"
          >
            Answers grounded in{" "}
            <span className="text-gradient">your documents</span>, not guesses.
          </motion.h1>

          <motion.p
            variants={fadeUp}
            initial="hidden"
            animate="show"
            custom={0.24}
            className="mt-6 max-w-xl text-base leading-relaxed text-foreground/55 sm:text-lg"
          >
            RAGnostic measures retrieval confidence for every question,
            expands context through a knowledge graph, and streams structured,
            citable answers in real time.
          </motion.p>

          <motion.div
            variants={fadeUp}
            initial="hidden"
            animate="show"
            custom={0.36}
            className="mt-9 flex w-full flex-col items-center justify-center gap-3 sm:w-auto sm:flex-row"
          >
            <Button
              asChild
              size="lg"
              className="w-full gap-2 bg-accent px-7 font-semibold text-accent-foreground hover:bg-accent/90 shadow-[0_0_40px_-10px] shadow-accent/60 sm:w-auto"
            >
              <Link href="/chat">
                Start chatting
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <Button
              asChild
              size="lg"
              variant="outline"
              className="w-full border-border/70 bg-transparent px-7 font-medium hover:bg-foreground/5 sm:w-auto"
            >
              <a href="#features">Explore features</a>
            </Button>
          </motion.div>

          <motion.div
            variants={fadeUp}
            initial="hidden"
            animate="show"
            custom={0.48}
            className="mt-14 w-full max-w-4xl"
          >
            <div className="glass relative overflow-hidden rounded-2xl p-1.5 shadow-2xl shadow-black/50">
              <div className="rounded-xl border border-border/40 bg-card/80 p-5 text-left sm:p-7">
                <div className="flex items-center gap-1.5 pb-4">
                  <span className="h-2.5 w-2.5 rounded-full bg-red-400/60" />
                  <span className="h-2.5 w-2.5 rounded-full bg-yellow-400/60" />
                  <span className="h-2.5 w-2.5 rounded-full bg-green-400/60" />
                  <span className="ml-3 text-xs text-foreground/35">ragnostic — chat</span>
                </div>
                <div className="space-y-4 text-sm leading-relaxed">
                  <div className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-secondary px-4 py-2.5 text-foreground/90">
                    What changed between v1 and v2 of the spec?
                  </div>
                  <div className="flex items-start gap-3">
                    <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-accent/25 bg-accent/10 text-accent">
                      <Sparkles className="h-3.5 w-3.5" />
                    </span>
                    <div className="min-w-0 space-y-2 text-foreground/75">
                      <p className="font-semibold text-foreground">
                        Three changes separate v2 from v1:
                      </p>
                      <ul className="list-disc space-y-1 pl-5">
                        <li>
                          <strong className="text-foreground">Auth flow</strong> moved to refresh rotation [1]
                        </li>
                        <li>
                          <strong className="text-foreground">Rate limits</strong> raised to 90 req/min [2]
                        </li>
                        <li>
                          <strong className="text-foreground">Webhooks</strong> added for indexing events [2]
                        </li>
                      </ul>
                      <p className="text-xs text-foreground/40">
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
        <section id="features" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-20 sm:px-6">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 0.6 }}
            className="mx-auto max-w-2xl text-center"
          >
            <h2 className="font-display text-3xl font-bold tracking-tight sm:text-4xl">
              Retrieval that adapts, answers you can trust
            </h2>
            <p className="mt-4 text-foreground/55">
              Most chatbots guess. RAGnostic measures retrieval confidence
              and expands depth only when the evidence demands it.
            </p>
          </motion.div>

          <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {features.map((feature, i) => (
              <motion.div
                key={feature.title}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-60px" }}
                transition={{ duration: 0.5, delay: i * 0.08 }}
                className="group glass rounded-2xl p-6 transition-all duration-300 hover:-translate-y-1 hover:border-accent/30 hover:shadow-[0_8px_40px_-12px] hover:shadow-accent/25"
              >
                <span className="flex h-11 w-11 items-center justify-center rounded-xl border border-accent/25 bg-accent/10 text-accent transition-shadow duration-300 group-hover:shadow-[0_0_20px_-4px] group-hover:shadow-accent/50">
                  <feature.icon className="h-5 w-5" />
                </span>
                <h3 className="mt-5 font-display text-lg font-semibold">
                  {feature.title}
                </h3>
                <p className="mt-2.5 text-sm leading-relaxed text-foreground/50">
                  {feature.description}
                </p>
              </motion.div>
            ))}
          </div>
        </section>

        {/* How it works */}
        <section id="how-it-works" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-20 sm:px-6">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 0.6 }}
            className="mx-auto max-w-2xl text-center"
          >
            <h2 className="font-display text-3xl font-bold tracking-tight sm:text-4xl">
              From upload to insight in three steps
            </h2>
          </motion.div>

          <div className="relative mt-14 grid gap-10 md:grid-cols-3 md:gap-6">
            <div
              aria-hidden
              className="absolute left-[16%] right-[16%] top-6 hidden h-px bg-gradient-to-r from-transparent via-accent/40 to-transparent md:block"
            />
            {steps.map((step, i) => (
              <motion.div
                key={step.number}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-60px" }}
                transition={{ duration: 0.5, delay: i * 0.12 }}
                className="relative text-center md:text-left"
              >
                <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl border border-accent/30 bg-background font-display text-sm font-bold text-accent shadow-[0_0_24px_-6px] shadow-accent/40 md:mx-0">
                  {step.number}
                </span>
                <h3 className="mt-5 font-display text-lg font-semibold">{step.title}</h3>
                <p className="mt-2.5 text-sm leading-relaxed text-foreground/50">
                  {step.description}
                </p>
              </motion.div>
            ))}
          </div>
        </section>

        {/* CTA */}
        <section className="mx-auto max-w-6xl px-4 pb-24 pt-8 sm:px-6">
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 0.6 }}
            className="glass relative overflow-hidden rounded-3xl px-6 py-16 text-center sm:px-12"
          >
            <div className="glow-orb left-1/2 top-[-140px] h-[280px] w-[480px] -translate-x-1/2 bg-accent/15" />
            <h2 className="relative font-display text-3xl font-bold tracking-tight sm:text-4xl">
              Ready to interrogate your documents?
            </h2>
            <p className="relative mx-auto mt-4 max-w-lg text-foreground/55">
              Sign up in seconds, index your first document, and watch adaptive
              retrieval find what keyword search never could.
            </p>
            <Button
              asChild
              size="lg"
              className="relative mt-8 gap-2 bg-accent px-8 font-semibold text-accent-foreground hover:bg-accent/90 shadow-[0_0_40px_-10px] shadow-accent/60"
            >
              <Link href="/chat">
                Launch RAGnostic
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </motion.div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-border/40">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-4 py-8 text-sm text-foreground/40 sm:flex-row sm:px-6">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-md border border-accent/25 bg-accent/10 text-accent">
              <LogoMark className="h-3.5 w-3.5" />
            </span>
            <span className="font-display font-medium text-foreground/60">RAGnostic</span>
          </div>
          <p>Adaptive retrieval-augmented generation.</p>
        </div>
      </footer>
    </div>
  );
}
