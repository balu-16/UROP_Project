"use client";

import { FileText, Search, Lightbulb, BrainCircuit } from "lucide-react";

interface SuggestionChipsProps {
  onSelect: (text: string) => void;
}

const chips = [
  { icon: FileText, label: "Summarize my documents" },
  { icon: Search, label: "What are the key findings?" },
  { icon: Lightbulb, label: "Explain the main concepts" },
  { icon: BrainCircuit, label: "How does adaptive retrieval work?" },
];

export function SuggestionChips({ onSelect }: SuggestionChipsProps) {
  return (
    <div className="mx-auto grid max-w-[560px] grid-cols-1 gap-2 px-4 sm:grid-cols-2">
      {chips.map((chip) => (
        <button
          key={chip.label}
          type="button"
          onClick={() => onSelect(chip.label)}
          className="flex items-center gap-2.5 rounded-xl border border-border bg-card px-3.5 py-2.5 text-left text-sm text-foreground/70 shadow-subtle transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/15"
          aria-label={chip.label}
        >
          <chip.icon className="h-4 w-4 shrink-0 text-foreground/45" />
          <span className="truncate">{chip.label}</span>
        </button>
      ))}
    </div>
  );
}
