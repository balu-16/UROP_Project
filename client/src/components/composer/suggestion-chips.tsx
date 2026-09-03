"use client";

import { motion } from "framer-motion";

interface SuggestionChipsProps {
  onSelect: (text: string) => void;
}

const chips = [
  { icon: "📄", label: "Summarize my documents" },
  { icon: "🔍", label: "What are the key findings?" },
  { icon: "💡", label: "Explain the main concepts" },
  { icon: "🧠", label: "How does adaptive retrieval work?" },
];

export function SuggestionChips({ onSelect }: SuggestionChipsProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.2 }}
      className="flex flex-wrap items-center justify-center gap-2 max-w-[560px] mx-auto px-4"
    >
      {chips.map((chip, i) => (
        <motion.button
          key={chip.label}
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.3 + i * 0.08 }}
          whileHover={{ scale: 1.02, y: -1 }}
          whileTap={{ scale: 0.97 }}
          onClick={() => onSelect(chip.label)}
          className="inline-flex items-center gap-2 rounded-full border border-border/50 bg-card/70 px-4 py-2 text-sm text-foreground/70 hover:text-foreground hover:bg-accent/8 hover:border-accent/25 hover:shadow-[0_4px_16px_-8px] hover:shadow-accent/20 transition-all duration-200 backdrop-blur-sm"
          aria-label={chip.label}
        >
          <span className="text-base">{chip.icon}</span>
          {chip.label}
        </motion.button>
      ))}
    </motion.div>
  );
}
