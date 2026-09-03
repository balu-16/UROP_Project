"use client";

import { useDeferredValue } from "react";
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
  const deferredQuery = useDeferredValue(searchQuery);
  const query = deferredQuery.trim().toLowerCase();
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
      {filtered.map((group, gi) => (
        <div key={group.label} className={cn(gi > 0 && "mt-4")}>
          <h3 className="px-3 py-1.5 text-[11px] font-medium uppercase tracking-wider text-sidebar-foreground/40">
            {group.label}
          </h3>
          <div className="mt-0.5 space-y-0.5">
            {group.conversations.map((conv) => {
              const active = activeId === conv.id;
              return (
                <button
                  key={conv.id}
                  onClick={() => onSelect(conv.id)}
                  title={conv.title}
                  className={cn(
                    "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm transition-colors",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/15",
                    active
                      ? "bg-secondary text-sidebar-foreground"
                      : "text-sidebar-foreground/65 hover:bg-secondary/60 hover:text-sidebar-foreground",
                  )}
                  aria-current={active ? "page" : undefined}
                >
                  <MessageSquare className="h-4 w-4 shrink-0 opacity-40" />
                  <span className="truncate">{conv.title}</span>
                </button>
              );
            })}
          </div>
        </div>
      ))}

      {query && total === 0 && (
        <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
          <span className="flex h-9 w-9 items-center justify-center rounded-full border border-sidebar-border bg-secondary/60 text-sidebar-foreground/40">
            <SearchX className="h-4 w-4" />
          </span>
          <p className="text-xs leading-relaxed text-sidebar-foreground/50">
            No conversations matching
            <br />
            <span className="font-medium text-sidebar-foreground/75">
              “{deferredQuery.trim()}”
            </span>
          </p>
        </div>
      )}
    </div>
  );
}
