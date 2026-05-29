"use client";

import { motion } from "framer-motion";

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
      className="flex flex-col items-center justify-center h-full select-none"
    >
      {/* Greeting */}
      <motion.h1
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2, duration: 0.4 }}
        className="text-[28px] md:text-[32px] font-semibold text-foreground/85 tracking-tight"
      >
        Hey, {displayName}.
      </motion.h1>
      <motion.p
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.35, duration: 0.4 }}
        className="text-[28px] md:text-[32px] font-semibold text-foreground/40 tracking-tight mt-1"
      >
        Ready to dive in?
      </motion.p>
    </motion.div>
  );
}
