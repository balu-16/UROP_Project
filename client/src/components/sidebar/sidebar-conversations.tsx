"use client";

import { AnimatePresence, motion } from "framer-motion";
import { MessageSquare, SearchX } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ConversationGroup } from "@/types";

interface SidebarConversationsProps {
  groups: ConversationGroup[];
  activeId: string | null;
  onSelect: (id: string) => void;
  searchQuery: string;
}

export function SidebarConversations({
  groups,
  activeId,
  onSelect,
  searchQuery,
}: SidebarConversationsProps) {
  const query = searchQuery.trim().toLowerCase();
  const filtered = query
    ? groups
        .map((g) => ({
          ...g,
          conversations: g.conversations.filter((c) =>
            c.title.toLowerCase().includes(query),
          ),
        }))
        .filter((g) => g.conversations.length > 0)
    : groups;
  const total = filtered.reduce((n, g) => n + g.conversations.length, 0);

  return (
    <div
      className="flex-1 overflow-y-auto px-2 py-1"
      aria-label="Recent conversations"
    >
      <AnimatePresence initial={false}>
        {filtered.map((group, gi) => (
          <motion.div
            key={group.label}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className={cn(gi > 0 && "mt-4")}
          >
            <h3 className="px-3 py-1.5 text-xs font-semibold text-sidebar-foreground/40 uppercase tracking-wider">
              {group.label}
            </h3>
            <div className="mt-1 space-y-0.5">
              {group.conversations.map((conv, ci) => {
                const active = activeId === conv.id;
                return (
                  <motion.button
                    key={conv.id}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -8 }}
                    transition={{
                      duration: 0.2,
                      delay: ci * 0.03,
                      ease: "easeOut",
                    }}
                    onClick={() => onSelect(conv.id)}
                    className={cn(
                      "relative flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                      "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-sidebar-accent-foreground/30",
                      active
                        ? "text-sidebar-foreground"
                        : "text-sidebar-foreground/60 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground",
                    )}
                    aria-current={active ? "page" : undefined}
                  >
                    {/* Animated active pill */}
                    {active && (
                      <motion.span
                        layoutId="sidebar-active-pill"
                        transition={{
                          type: "spring",
                          stiffness: 420,
                          damping: 34,
                        }}
                        className="absolute inset-0 rounded-lg bg-sidebar-accent"
                      />
                    )}
                    <MessageSquare className="relative z-10 h-4 w-4 shrink-0 opacity-50" />
                    <span className="relative z-10 truncate">{conv.title}</span>
                  </motion.button>
                );
              })}
            </div>
          </motion.div>
        ))}
      </AnimatePresence>

      {query && total === 0 && (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
          className="flex flex-col items-center gap-2 px-4 py-10 text-center"
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-full border border-sidebar-border bg-sidebar-accent/50 text-sidebar-foreground/40">
            <SearchX className="h-4 w-4" />
          </span>
          <p className="text-xs leading-relaxed text-sidebar-foreground/45">
            No conversations matching
            <br />
            <span className="font-medium text-sidebar-foreground/70">
              “{searchQuery.trim()}”
            </span>
          </p>
        </motion.div>
      )}
    </div>
  );
}
