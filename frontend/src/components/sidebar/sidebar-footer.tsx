"use client";

import { LogOut } from "lucide-react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import type { User } from "@/types";

export function SidebarFooter({ user, onLogout }: { user: User; onLogout: () => void }) {
  const initials = user.name
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return (
    <div className="border-t border-sidebar-border p-3">
      <motion.button
        whileHover={{ backgroundColor: "rgba(255,255,255,0.06)" }}
        className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-sm text-sidebar-foreground/70 hover:text-sidebar-foreground transition-colors"
        aria-label="User profile and settings"
      >
        {/* Avatar */}
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-purple-600 text-white text-xs font-semibold">
          {initials}
        </div>
        <div className="flex-1 text-left">
          <p className="text-sm font-medium text-sidebar-foreground truncate">
            {user.name}
          </p>
          <p className="text-[11px] text-sidebar-foreground/40">{user.email}</p>
        </div>
        <Button
          onClick={onLogout}
          variant="ghost"
          size="icon-sm"
          className="text-sidebar-foreground/40 hover:text-sidebar-foreground"
          aria-label="Logout"
        >
          <LogOut className="h-4 w-4" />
        </Button>
      </motion.button>
    </div>
  );
}
