"use client";

import { AnimatePresence, motion } from "framer-motion";
import { SidebarHeader } from "./sidebar-header";
import { SidebarSearch } from "./sidebar-search";
import { SidebarNav } from "./sidebar-nav";
import { SidebarConversations } from "./sidebar-conversations";
import { SidebarFooter } from "./sidebar-footer";
import { cn } from "@/lib/utils";
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
}: SidebarProps) {
  return (
    <AnimatePresence mode="wait">
      {isOpen && (
        <motion.aside
          initial={{ width: 0, opacity: 0 }}
          animate={{ width: 260, opacity: 1 }}
          exit={{ width: 0, opacity: 0 }}
          transition={{ duration: 0.2, ease: "easeInOut" }}
          className={cn(
            "hidden md:flex flex-col h-full bg-sidebar border-r border-sidebar-border overflow-hidden",
            "select-none",
          )}
          aria-label="Sidebar"
        >
          <SidebarHeader onNewChat={onNewChat} />
          <SidebarSearch />
          <SidebarNav onNewChat={onNewChat} />
          <SidebarConversations
            groups={groups}
            activeId={activeConversationId}
            onSelect={onSelectConversation}
          />
          <SidebarFooter user={user} onLogout={onLogout} />
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
