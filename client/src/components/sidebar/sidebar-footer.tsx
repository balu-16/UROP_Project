"use client";

import { LogOut } from "lucide-react";
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
    <div className="shrink-0 border-t border-sidebar-border p-3 pb-[env(safe-area-inset-bottom)]">
      <div
        className={cn(
          "flex w-full items-center gap-3 rounded-lg px-2 py-2 text-sm",
        )}
      >
        {/* Avatar */}
        <div
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border bg-secondary text-[11px] font-semibold text-sidebar-foreground"
          aria-hidden
        >
          {initials}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-sidebar-foreground">
            {user.name}
          </p>
          <p className="truncate text-[11px] text-sidebar-foreground/50">
            {user.email}
          </p>
        </div>
        <button
          onClick={onLogout}
          aria-label="Log out"
          title="Log out"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-sidebar-foreground/50 transition-colors hover:bg-secondary hover:text-sidebar-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/15"
        >
          <LogOut className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
