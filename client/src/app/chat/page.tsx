"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Sidebar } from "@/components/sidebar/sidebar";
import { ChatArea } from "@/components/chat/chat-area";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { AuthGate } from "@/components/auth/auth-gate";
import { LogoMark } from "@/components/logo-mark";
import { SidebarHeader } from "@/components/sidebar/sidebar-header";
import { SidebarSearch } from "@/components/sidebar/sidebar-search";
import { SidebarNav } from "@/components/sidebar/sidebar-nav";
import { SidebarConversations } from "@/components/sidebar/sidebar-conversations";
import { SidebarFooter } from "@/components/sidebar/sidebar-footer";
import {
  getMe,
  getSessions,
  createSession,
  logout as apiLogout,
  getAccessToken,
  setAccessToken,
} from "@/lib/api";
import type { BackendSession, ConversationGroup, User } from "@/types";

function groupSessions(sessions: BackendSession[]): ConversationGroup[] {
  const groups: Record<string, BackendSession[]> = {
    Today: [],
    Yesterday: [],
    "Previous 7 Days": [],
  };
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  sessions.forEach((session) => {
    const updated = new Date(session.updated_at);
    const updatedDayStart = new Date(
      updated.getFullYear(),
      updated.getMonth(),
      updated.getDate(),
    );
    const diffDays = Math.floor(
      (todayStart.getTime() - updatedDayStart.getTime()) / 86400000,
    );
    if (diffDays <= 0) groups.Today.push(session);
    else if (diffDays === 1) groups.Yesterday.push(session);
    else groups["Previous 7 Days"].push(session);
  });
  return Object.entries(groups)
    .filter(([, items]) => items.length > 0)
    .map(([label, items]) => ({
      label,
      conversations: items.map((session) => ({
        id: session._id,
        title: session.title,
        messages: [],
        createdAt: new Date(session.created_at),
        updatedAt: new Date(session.updated_at),
      })),
    }));
}

function BootSplash() {
  return (
    <div className="flex h-dvh flex-col items-center justify-center gap-5 bg-background">
      <motion.div
        initial={{ opacity: 0, scale: 0.85 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="relative"
      >
        <div className="absolute inset-0 -z-10 rounded-full bg-accent/20 blur-2xl" />
        <span className="flex h-14 w-14 items-center justify-center rounded-2xl border border-accent/25 bg-accent/10 text-accent shadow-[0_0_36px_-8px] shadow-accent/50">
          <LogoMark size={26} />
        </span>
      </motion.div>
      <div className="flex items-center gap-2.5 text-sm text-foreground/60">
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-accent/30 border-t-accent" />
        Loading RAGnostic
      </div>
    </div>
  );
}

export default function ChatPage() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [sessions, setSessions] = useState<BackendSession[]>([]);
  const [loadingAuth, setLoadingAuth] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");

  const loadSessions = useCallback(async () => {
    const data = await getSessions();
    setSessions(data);
  }, []);

  useEffect(() => {
    async function boot() {
      try {
        const me = await getMe();
        setUser(me);
        try {
          await loadSessions();
        } catch {
          // Session list failed to load, but don't log the user out
          console.error("Failed to load sessions");
        }
      } catch (error) {
        // Only clear the token if authFetch already cleared it (401 path).
        // For transient errors (500, network), keep the token so the user
        // can retry on next load instead of being kicked to login.
        if (!getAccessToken()) {
          // Token was already cleared by authFetch's 401 handler
        } else {
          console.error("Failed to verify session, will retry on next load:", error);
        }
      } finally {
        setLoadingAuth(false);
      }
    }
    boot();
  }, [loadSessions]);

  const groups = useMemo(() => groupSessions(sessions), [sessions]);

  const handleToggleSidebar = useCallback(() => {
    if (typeof window !== "undefined" && window.innerWidth < 768) {
      setMobileOpen((v) => !v);
    } else {
      setSidebarOpen((v) => !v);
    }
  }, []);

  const handleNewChat = useCallback(() => {
    // Open a real chat immediately: chatting and uploading both require
    // an active session, since documents are scoped to one chat.
    setActiveConvId(null);
    setMobileOpen(false);
    createSession()
      .then((session) => {
        setActiveConvId(session._id);
        setSessions((prev) => [session, ...prev]);
      })
      .catch(() => {
        // Backend unreachable — stay without a session; send/upload
        // will surface the error.
      });
  }, []);

  const handleSelectConversation = useCallback((id: string) => {
    setActiveConvId(id);
    setMobileOpen(false);
  }, []);

  const handleAuthenticated = useCallback(
    async (nextUser: User) => {
      setUser(nextUser);
      try {
        await loadSessions();
      } catch {
        console.error("Failed to load sessions after authentication");
      }
    },
    [loadSessions],
  );

  const handleLogout = useCallback(async () => {
    await apiLogout().catch(() => undefined);
    setUser(null);
    setSessions([]);
    setActiveConvId(null);
    setSearchQuery("");
  }, []);

  if (loadingAuth) {
    return <BootSplash />;
  }

  if (!user) {
    return <AuthGate onAuthenticated={handleAuthenticated} />;
  }

  const sidebarContent = (
    <>
      <SidebarHeader />
      <SidebarSearch value={searchQuery} onChange={setSearchQuery} />
      <SidebarNav onNewChat={handleNewChat} />
      <SidebarConversations
        groups={groups}
        activeId={activeConvId}
        onSelect={handleSelectConversation}
        searchQuery={searchQuery}
      />
      <SidebarFooter user={user} onLogout={handleLogout} />
    </>
  );

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-background">
      <Sidebar
        isOpen={sidebarOpen}
        onToggle={handleToggleSidebar}
        onNewChat={handleNewChat}
        activeConversationId={activeConvId}
        onSelectConversation={handleSelectConversation}
        groups={groups}
        user={user}
        onLogout={handleLogout}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
      />

      <Dialog open={mobileOpen} onOpenChange={setMobileOpen}>
        <DialogContent className="w-[290px] rounded-r-2xl p-0 bg-sidebar border-sidebar-border pb-[env(safe-area-inset-bottom)]">
          <DialogHeader className="sr-only">
            <DialogTitle>Navigation</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col h-full">{sidebarContent}</div>
        </DialogContent>
      </Dialog>

      <ChatArea
        sidebarOpen={sidebarOpen}
        onToggleSidebar={handleToggleSidebar}
        activeSessionId={activeConvId}
        onSessionChange={setActiveConvId}
        onSessionsDirty={loadSessions}
      />
    </div>
  );
}
