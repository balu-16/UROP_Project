"use client";

import { useEffect, useState } from "react";
import { API_BASE_URL } from "@/lib/api";
import { cn } from "@/lib/utils";

export function ConnectionDot() {
  const [online, setOnline] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 4000);
      try {
        const res = await fetch(`${API_BASE_URL}/health`, {
          signal: controller.signal,
          cache: "no-store",
          credentials: "include",
        });
        if (!cancelled) setOnline(res.ok);
      } catch {
        if (!cancelled) setOnline(false);
      } finally {
        clearTimeout(timeout);
      }
    };

    void check();
    const interval = setInterval(check, 30000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return (
    <span
      title={online ? "Backend connected" : "Backend unreachable"}
      className={cn(
        "h-2 w-2 rounded-full",
        online ? "bg-emerald-500" : "bg-red-400",
      )}
      role="status"
      aria-label={online ? "Connected" : "Disconnected"}
    />
  );
}
