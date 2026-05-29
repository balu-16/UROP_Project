"use client";

import { motion } from "framer-motion";

interface UserMessageProps {
  content: string;
  index?: number;
}

export function UserMessage({ content, index = 0 }: UserMessageProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, delay: index * 0.03, ease: "easeOut" }}
      className="flex justify-end px-4 py-3"
      role="article"
      aria-label="User message"
    >
      <div className="max-w-[70%] rounded-2xl bg-[#2f2f3d] px-4 py-2.5 text-[15px] leading-[1.6] text-white/95 shadow-sm">
        {content}
      </div>
    </motion.div>
  );
}
