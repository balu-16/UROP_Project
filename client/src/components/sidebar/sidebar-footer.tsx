"use client";

import { LogOut } from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import type { User } from "@/types";

export function SidebarFooter({ user, onLogout }: { user: User; onLogout: () => void }) {
  const initials = user.name
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return (
    <div className="shrink-0 border-t border-sidebar-border p-3">
      <motion.div
        whileHover={{ backgroundColor: "rgba(255,255,255,0.05)" }}
        transition={{ duration: 0.15 }}
        className={cn(
          "flex w-full items-center gap-3 rounded-xl px-2 py-2 text-sm transition-colors",
          "focus-within:ring-1 focus-within:ring-sidebar-accent-foreground/25",
        )}
      >
        {/* Avatar */}
        <div
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-accent/80 to-violet-500/80 text-[11px] font-semibold text-white ring-1 ring-white/10"
          aria-hidden
        >
          {initials}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-sidebar-foreground">
            {user.name}
          </p>
          <p className="truncate text-[11px] text-sidebar-foreground/40">
            {user.email}
          </p>
        </div>
        <button
          onClick={onLogout}
          aria-label="Log out"
          title="Log out"
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-sidebar-foreground/40 transition-all hover:bg-red-500/10 hover:text-red-300 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-sidebar-accent-foreground/30"
        >
          <LogOut className="h-4 w-4" />
        </button>
      </motion.div>
    </div>
  );
}
