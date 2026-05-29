"use client";

import { useEffect } from "react";

interface KeyboardShortcuts {
  onToggleSidebar?: () => void;
  onSendMessage?: () => void;
  onFocusComposer?: () => void;
}

export function useKeyboardShortcuts({
  onToggleSidebar,
  onSendMessage,
  onFocusComposer,
}: KeyboardShortcuts) {
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const isMod = e.metaKey || e.ctrlKey;

      // Cmd/Ctrl + Shift + S → toggle sidebar
      if (isMod && e.shiftKey && e.key === "s") {
        e.preventDefault();
        onToggleSidebar?.();
      }

      // Cmd/Ctrl + Enter → send message
      if (isMod && e.key === "Enter") {
        e.preventDefault();
        onSendMessage?.();
      }

      // Cmd/Ctrl + / → focus composer
      if (isMod && e.key === "/") {
        e.preventDefault();
        onFocusComposer?.();
      }

      // Escape → blur focus
      if (e.key === "Escape") {
        (document.activeElement as HTMLElement)?.blur();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onToggleSidebar, onSendMessage, onFocusComposer]);
}
