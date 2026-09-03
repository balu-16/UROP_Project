"use client";

import { Search, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface SidebarSearchProps {
  className?: string;
  value: string;
  onChange: (value: string) => void;
}

export function SidebarSearch({ className, value, onChange }: SidebarSearchProps) {
  return (
    <div className={cn("px-3 pb-2", className)}>
      <div className="group relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-sidebar-foreground/40 transition-colors group-focus-within:text-sidebar-foreground/70" />
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Search conversations…"
          className="h-10 w-full rounded-lg border border-transparent bg-secondary/70 pl-9 pr-14 text-sm text-sidebar-foreground outline-none transition-colors placeholder:text-sidebar-foreground/40 focus:border-border focus:bg-secondary"
          aria-label="Search conversations"
        />
        {value ? (
          <button
            type="button"
            onClick={() => onChange("")}
            aria-label="Clear search"
            className="absolute right-2 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-sidebar-foreground/40 transition-colors hover:bg-secondary hover:text-sidebar-foreground/80"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        ) : (
          <kbd className="mono-meta pointer-events-none absolute right-3 top-1/2 hidden -translate-y-1/2 rounded border border-border bg-card px-1.5 py-0.5 text-[10px] text-sidebar-foreground/40 lg:block">
            ⌘K
          </kbd>
        )}
      </div>
    </div>
  );
}
