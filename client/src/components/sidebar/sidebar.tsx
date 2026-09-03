"use client";

import { AnimatePresence, motion } from "framer-motion";
import { SidebarHeader } from "./sidebar-header";
import { SidebarSearch } from "./sidebar-search";
import { SidebarNav } from "./sidebar-nav";
import { SidebarConversations } from "./sidebar-conversations";
import { SidebarFooter } from "./sidebar-footer";
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
          initial={{ x: -264, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: -264, opacity: 0 }}
          transition={{ duration: 0.22, ease: [0.21, 0.47, 0.32, 0.98] }}
          className="hidden h-full w-[264px] shrink-0 overflow-hidden border-r border-sidebar-border bg-sidebar select-none md:flex"
          aria-label="Sidebar"
        >
          {/* Fixed-width inner column so content never squishes while animating */}
          <div className="flex w-[264px] h-full flex-col">
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
