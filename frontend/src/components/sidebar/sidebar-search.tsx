"use client";

import { Search } from "lucide-react";
import { cn } from "@/lib/utils";

interface SidebarSearchProps {
  className?: string;
}

export function SidebarSearch({ className }: SidebarSearchProps) {
  return (
    <div className={cn("px-3 pb-2", className)}>
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-sidebar-foreground/40" />
        <input
          type="text"
          placeholder="Search"
          className="w-full rounded-lg bg-sidebar-accent/50 border border-transparent focus:border-sidebar-accent-foreground/20 py-2 pl-9 pr-3 text-sm text-sidebar-foreground placeholder:text-sidebar-foreground/40 outline-none transition-colors"
          aria-label="Search conversations"
        />
      </div>
    </div>
  );
}
