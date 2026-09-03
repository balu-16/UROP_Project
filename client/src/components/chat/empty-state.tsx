"use client";

import { motion } from "framer-motion";
import { FileText, Sparkles, Search, Library } from "lucide-react";

interface EmptyStateProps {
  userName?: string;
}

export function EmptyState({ userName }: EmptyStateProps) {
  const displayName = userName || "there";
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
      className="flex flex-col items-center justify-center h-full select-none px-6 py-12"
    >
      {/* Icon cluster */}
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.1, duration: 0.5 }}
        className="relative mb-6"
      >
        <div className="absolute inset-0 -z-10 blur-2xl opacity-40 bg-accent/20 rounded-full" />
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl border border-accent/20 bg-accent/10 text-accent shadow-[0_8px_32px_-12px] shadow-accent/40">
          <Library className="h-7 w-7" />
        </div>
        <span className="absolute -right-1 -top-1 flex h-6 w-6 items-center justify-center rounded-full bg-card border border-border/60 shadow-sm">
          <Sparkles className="h-3.5 w-3.5 text-accent" />
        </span>
      </motion.div>

      {/* Greeting */}
      <motion.h1
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2, duration: 0.4 }}
        className="text-[28px] md:text-[32px] font-semibold text-foreground tracking-tight text-center"
      >
        Hey, {displayName}.
      </motion.h1>
      <motion.p
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.35, duration: 0.4 }}
        className="text-[28px] md:text-[32px] font-semibold text-foreground/35 tracking-tight text-center"
      >
        Ready to dive in?
      </motion.p>
      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.5, duration: 0.4 }}
        className="mt-3 max-w-[420px] text-center text-sm leading-relaxed text-foreground/45"
      >
        Drop PDFs, ask questions, and get cited answers. Your documents are indexed with Chroma + PG graph.
      </motion.p>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.6, duration: 0.4 }}
        className="mt-6 flex flex-wrap justify-center gap-2 text-xs"
      >
        <span className="inline-flex items-center gap-1.5 rounded-full border border-border/50 bg-card/60 px-3 py-1.5 text-foreground/55 backdrop-blur">
          <Search className="h-3.5 w-3.5" /> Threshold retrieval
        </span>
        <span className="inline-flex items-center gap-1.5 rounded-full border border-border/50 bg-card/60 px-3 py-1.5 text-foreground/55 backdrop-blur">
          <FileText className="h-3.5 w-3.5" /> Graph expansion
        </span>
      </motion.div>
    </motion.div>
  );
}
