"use client";

import { LogoMark } from "@/components/logo-mark";

export function SidebarHeader() {
  return (
    <div className="flex items-center gap-2.5 px-3.5 pt-3.5 pb-2 select-none">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-accent/30 bg-accent/10 text-accent shadow-[0_0_20px_-6px] shadow-accent/40">
        <LogoMark size={17} />
      </span>
      <span className="font-display text-[15px] font-semibold tracking-tight text-sidebar-foreground">
        RAGnostic
      </span>
    </div>
  );
}
