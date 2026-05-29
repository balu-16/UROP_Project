"use client";

import { motion, AnimatePresence } from "framer-motion";
import { MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ConversationGroup } from "@/types";

interface SidebarConversationsProps {
  groups: ConversationGroup[];
  activeId: string | null;
  onSelect: (id: string) => void;
}

export function SidebarConversations({
  groups,
  activeId,
  onSelect,
}: SidebarConversationsProps) {
  return (
    <div
      className="flex-1 overflow-y-auto px-2 py-1"
      aria-label="Recent conversations"
    >
      <AnimatePresence>
        {groups.map((group, gi) => (
          <div key={group.label} className={cn(gi > 0 && "mt-4")}>
            <h3 className="px-3 py-1.5 text-xs font-semibold text-sidebar-foreground/40 uppercase tracking-wider">
              {group.label}
            </h3>
            <div className="mt-1 space-y-0.5">
              {group.conversations.map((conv, ci) => (
                <motion.button
                  key={conv.id}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: ci * 0.03 }}
                  whileHover={{ x: 1 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => onSelect(conv.id)}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                    "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-sidebar-accent-foreground/30",
                    activeId === conv.id
                      ? "bg-sidebar-accent text-sidebar-foreground"
                      : "text-sidebar-foreground/60 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
                  )}
                  aria-current={activeId === conv.id ? "page" : undefined}
                >
                  <MessageSquare className="h-4 w-4 shrink-0 opacity-50" />
                  <span className="truncate">{conv.title}</span>
                </motion.button>
              ))}
            </div>
          </div>
        ))}
      </AnimatePresence>
    </div>
  );
}
