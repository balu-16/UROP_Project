"use client";

import { AnimatePresence, motion } from "framer-motion";
import { SidebarHeader } from "./sidebar-header";
import { SidebarSearch } from "./sidebar-search";
import { SidebarNav } from "./sidebar-nav";
import { SidebarConversations } from "./sidebar-conversations";
import { SidebarFooter } from "./sidebar-footer";
import { springSoft } from "@/lib/motion";
import type { ConversationGroup, User } from "@/types";

interface SidebarProps {
  isOpen: boolean;
  onToggle: () => void;
  onNewChat: () => void;
  activeConversationId: string | null;
  onSelectConversation: (id: string) => void;
  groups: ConversationGroup[];
  user: User;
  onLogout: () => void;
  searchQuery: string;
  onSearchChange: (query: string) => void;
}

export function Sidebar({
  isOpen,
  onToggle,
  onNewChat,
  activeConversationId,
  onSelectConversation,
  groups,
  user,
  onLogout,
  searchQuery,
  onSearchChange,
}: SidebarProps) {
  return (
    <AnimatePresence initial={false}>
      {isOpen && (
        <motion.aside
          initial={{ width: 0, opacity: 0 }}
          animate={{ width: 264, opacity: 1 }}
          exit={{ width: 0, opacity: 0 }}
          transition={springSoft}
          className="hidden md:flex h-full shrink-0 overflow-hidden bg-sidebar border-r border-sidebar-border select-none"
          aria-label="Sidebar"
        >
          {/* Fixed-width inner column so content never squishes while animating */}
          <div className="flex w-[264px] flex-col h-full">
            <SidebarHeader />
            <SidebarSearch value={searchQuery} onChange={onSearchChange} />
            <SidebarNav onNewChat={onNewChat} />
            <SidebarConversations
              groups={groups}
              activeId={activeConversationId}
              onSelect={onSelectConversation}
              searchQuery={searchQuery}
            />
            <SidebarFooter user={user} onLogout={onLogout} />
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
