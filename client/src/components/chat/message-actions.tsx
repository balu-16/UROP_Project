"use client";

import { useState } from "react";
import {
  Copy,
  ThumbsUp,
  ThumbsDown,
  RotateCcw,
  Check,
} from "lucide-react";
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
      icon: RotateCcw,
      label: "Regenerate",
      onClick: onRegenerate,
    },
  ];

  return (
    <div className="-ml-1 mt-1.5 flex items-center gap-0.5">
      {actions.map((action) => (
        <Tooltip key={action.label}>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              onClick={action.onClick}
              className={`h-8 w-8 rounded-lg text-foreground/45 hover:bg-secondary hover:text-foreground ${
                action.active ? "bg-secondary text-foreground" : ""
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
    </div>
  );
}
