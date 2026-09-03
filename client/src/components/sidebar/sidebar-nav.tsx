"use client";

import { Plus } from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export function SidebarNav({ onNewChat }: { onNewChat?: () => void }) {
  return (
    <nav className="shrink-0 px-3 pt-1 pb-2" aria-label="Sidebar navigation">
      <motion.button
        whileHover={{ scale: 1.015 }}
        whileTap={{ scale: 0.98 }}
        onClick={onNewChat}
        className={cn(
          "flex w-full items-center justify-center gap-2 rounded-xl border border-border/60 bg-card/60 px-3 py-2.5",
          "text-sm font-medium text-sidebar-foreground/85 shadow-sm",
          "transition-colors hover:border-accent/30 hover:bg-accent/10 hover:text-sidebar-foreground",
          "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-sidebar-accent-foreground/30",
        )}
        aria-label="Start a new chat"
      >
        <Plus className="h-4 w-4 shrink-0 text-accent" />
        <span>New chat</span>
      </motion.button>
    </nav>
  );
}
