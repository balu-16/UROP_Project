"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { API_BASE_URL } from "@/lib/api";

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
    <motion.span
      initial={false}
      animate={{
        backgroundColor: online ? "#34d399" : "#f87171",
        scale: online ? [1, 1.18, 1] : 1,
      }}
      transition={{
        backgroundColor: { duration: 0.4 },
        scale: {
          duration: 2.2,
          repeat: Infinity,
          ease: "easeInOut",
        },
      }}
      title={online ? "Backend connected" : "Backend unreachable"}
      className={`h-2 w-2 rounded-full shadow-[0_0_8px_1px] ${
        online ? "shadow-emerald-400/50" : "shadow-red-400/50"
      }`}
      role="status"
      aria-label={online ? "Connected" : "Disconnected"}
    />
  );
}
