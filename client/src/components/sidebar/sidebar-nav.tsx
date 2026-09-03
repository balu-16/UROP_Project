"use client";

import { Plus } from "lucide-react";
import { cn } from "@/lib/utils";

export function SidebarNav({ onNewChat }: { onNewChat?: () => void }) {
  return (
    <nav className="shrink-0 px-3 pb-2 pt-1" aria-label="Sidebar navigation">
      <button
        onClick={onNewChat}
        className={cn(
          "flex h-10 w-full items-center justify-center gap-2 rounded-lg border border-border bg-card px-3",
          "text-sm font-medium text-sidebar-foreground",
          "transition-colors hover:bg-secondary",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/15",
        )}
        aria-label="Start a new chat"
      >
        <Plus className="h-4 w-4 shrink-0 text-sidebar-foreground/70" />
        <span>New chat</span>
      </button>
    </nav>
  );
}
