"use client";

import { LogoMark } from "@/components/logo-mark";

export function SidebarHeader() {
  return (
    <div className="flex items-center gap-2.5 px-3.5 pb-2 pt-3.5 select-none">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-card text-foreground">
        <LogoMark size={17} />
      </span>
      <span className="text-[15px] font-semibold tracking-tight text-sidebar-foreground">
        RAGnostic
      </span>
    </div>
  );
}
