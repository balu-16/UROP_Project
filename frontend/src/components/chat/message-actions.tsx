"use client";

import { useState } from "react";
import {
  Copy,
  ThumbsUp,
  ThumbsDown,
  Volume2,
  Share2,
  RotateCcw,
  MoreHorizontal,
  Check,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { sendFeedback } from "@/lib/api";

interface MessageActionsProps {
  onRegenerate?: () => void;
  content: string;
  messageId?: string;
  sessionId?: string;
}

export function MessageActions({
  onRegenerate,
  content,
  messageId,
  sessionId,
}: MessageActionsProps) {
  const [copied, setCopied] = useState(false);
  const [liked, setLiked] = useState<boolean | null>(null);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleFeedback = async (rating: boolean) => {
    const newLiked = liked === rating ? null : rating;
    setLiked(newLiked);
    if (newLiked !== null && messageId && sessionId) {
      try {
        await sendFeedback(sessionId, messageId, newLiked ? 1 : 0);
      } catch {
        // silently fail - feedback is best-effort
      }
    }
  };

  const actions = [
    {
      icon: copied ? Check : Copy,
      label: copied ? "Copied!" : "Copy",
      onClick: handleCopy,
    },
    {
      icon: ThumbsUp,
      label: "Good response",
      onClick: () => handleFeedback(true),
      active: liked === true,
    },
    {
      icon: ThumbsDown,
      label: "Bad response",
      onClick: () => handleFeedback(false),
      active: liked === false,
    },
    {
      icon: Volume2,
      label: "Read aloud",
      onClick: () => {},
    },
    {
      icon: Share2,
      label: "Share",
      onClick: () => {},
    },
    {
      icon: RotateCcw,
      label: "Regenerate",
      onClick: onRegenerate,
    },
    {
      icon: MoreHorizontal,
      label: "More",
      onClick: () => {},
    },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.15 }}
      className="flex items-center gap-0.5 -ml-1 mt-2"
    >
      {actions.map((action) => (
        <Tooltip key={action.label}>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={action.onClick}
              className={`h-7 w-7 rounded-md text-foreground/40 hover:text-foreground/70 hover:bg-foreground/5 transition-colors ${
                action.active ? "text-foreground/80 bg-foreground/5" : ""
              }`}
              aria-label={action.label}
            >
              <action.icon className="h-3.5 w-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom" className="text-xs">
            {action.label}
          </TooltipContent>
        </Tooltip>
      ))}
    </motion.div>
  );
}
