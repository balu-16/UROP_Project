"use client";

import { Plus } from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export function SidebarNav({ onNewChat }: { onNewChat?: () => void }) {
  return (
    <nav
      className="flex-1 overflow-y-auto px-2 py-1"
      aria-label="Sidebar navigation"
    >
      <div className="space-y-0.5">
        <motion.button
          whileHover={{ x: 1 }}
          whileTap={{ scale: 0.98 }}
          onClick={onNewChat}
          className={cn(
            "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-sidebar-foreground/70",
            "hover:bg-sidebar-accent hover:text-sidebar-foreground transition-colors",
            "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-sidebar-accent-foreground/30",
          )}
          aria-label="New chat"
        >
          <Plus className="h-4 w-4 shrink-0" />
          <span className="truncate">New chat</span>
        </motion.button>
      </div>
    </nav>
  );
}
