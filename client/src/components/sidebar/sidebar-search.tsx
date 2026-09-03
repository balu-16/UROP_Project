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
          className="w-full rounded-lg bg-sidebar-accent/50 border border-transparent py-2 pl-9 pr-8 text-sm text-sidebar-foreground placeholder:text-sidebar-foreground/40 outline-none transition-all duration-200 focus:border-sidebar-accent-foreground/25 focus:bg-sidebar-accent/80"
          aria-label="Search conversations"
        />
        {value && (
          <button
            type="button"
            onClick={() => onChange("")}
            aria-label="Clear search"
            className="absolute right-2 top-1/2 flex h-5 w-5 -translate-y-1/2 items-center justify-center rounded-full text-sidebar-foreground/40 transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground/80"
          >
            <X className="h-3 w-3" />
          </button>
        )}
      </div>
    </div>
  );
}
