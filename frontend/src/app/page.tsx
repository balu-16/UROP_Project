"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Sidebar } from "@/components/sidebar/sidebar";
import { ChatArea } from "@/components/chat/chat-area";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { AuthGate } from "@/components/auth/auth-gate";
import { SidebarHeader } from "@/components/sidebar/sidebar-header";
import { SidebarSearch } from "@/components/sidebar/sidebar-search";
import { SidebarNav } from "@/components/sidebar/sidebar-nav";
import { SidebarConversations } from "@/components/sidebar/sidebar-conversations";
import { SidebarFooter } from "@/components/sidebar/sidebar-footer";
import {
  getMe,
  getSessions,
  logout as apiLogout,
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

export default function Home() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [sessions, setSessions] = useState<BackendSession[]>([]);
  const [loadingAuth, setLoadingAuth] = useState(true);

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
      } catch {
        setAccessToken(null);
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
    setActiveConvId(null);
    setMobileOpen(false);
  }, []);

  const handleSelectConversation = useCallback((id: string) => {
    setActiveConvId(id);
    setMobileOpen(false);
  }, []);

  const handleAuthenticated = useCallback(
    async (nextUser: User) => {
      setUser(nextUser);
      await loadSessions();
    },
    [loadSessions],
  );

  const handleLogout = useCallback(async () => {
    await apiLogout().catch(() => undefined);
    setUser(null);
    setSessions([]);
    setActiveConvId(null);
  }, []);

  if (loadingAuth) {
    return (
      <div className="flex h-screen items-center justify-center bg-background text-foreground/50">
        Loading RAGnostic...
      </div>
    );
  }

  if (!user) {
    return <AuthGate onAuthenticated={handleAuthenticated} />;
  }

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background">
      <Sidebar
        isOpen={sidebarOpen}
        onToggle={handleToggleSidebar}
        onNewChat={handleNewChat}
        activeConversationId={activeConvId}
        onSelectConversation={handleSelectConversation}
        groups={groups}
        user={user}
        onLogout={handleLogout}
      />

      <Dialog open={mobileOpen} onOpenChange={setMobileOpen}>
        <DialogContent className="w-[300px] p-0 bg-sidebar border-sidebar-border">
          <DialogHeader className="sr-only">
            <DialogTitle>Navigation</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col h-full">
            <SidebarHeader onNewChat={handleNewChat} />
            <SidebarSearch />
            <SidebarNav />
            <SidebarConversations
              groups={groups}
              activeId={activeConvId}
              onSelect={handleSelectConversation}
            />
            <SidebarFooter user={user} onLogout={handleLogout} />
          </div>
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
