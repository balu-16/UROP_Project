"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { PanelLeft, UploadCloud } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { EmptyState } from "./empty-state";
import { MessageList } from "./message-list";
import { InputComposer } from "@/components/composer/input-composer";
import { SuggestionChips } from "@/components/composer/suggestion-chips";
import { ConnectionDot } from "./connection-dot";
import { useChat } from "@/hooks/use-chat";
import { useKeyboardShortcuts } from "@/hooks/use-keyboard";
import { uploadFiles, createSession } from "@/lib/api";
import { cn } from "@/lib/utils";

interface ChatAreaProps {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  activeSessionId: string | null;
  onSessionChange: (sessionId: string) => void;
  onSessionsDirty: () => void;
}

const ACCEPTED_EXTENSIONS = [".pdf", ".txt", ".md", ".markdown", ".pptx"];

export function ChatArea({
  sidebarOpen,
  onToggleSidebar,
  activeSessionId,
  onSessionChange,
  onSessionsDirty,
}: ChatAreaProps) {
  const { toast } = useToast();
  const { messages, isStreaming, sendMessage, stopStreaming, regenerate, editAndResend } =
    useChat(activeSessionId, onSessionChange, onSessionsDirty, (msg) =>
      toast(msg, "error"),
    );
  const [uploading, setUploading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const dragDepthRef = useRef(0);

  const hasMessages = messages.length > 0;

  /* Focus management for keyboard shortcut */
  const handleFocusComposer = useCallback(() => {
    const textarea = document.querySelector(
      'textarea[aria-label="Message input"]',
    ) as HTMLTextAreaElement | null;
    textarea?.focus();
  }, []);

  useKeyboardShortcuts({
    onToggleSidebar,
    onFocusComposer: handleFocusComposer,
  });

  const handleSuggestion = (text: string) => {
    sendMessage(text);
  };

  // Chatting requires an open chat: lazily create one on first send so the
  // composer never streams against a null session.
  const handleSend = useCallback(
    async (text: string, reasoning: boolean) => {
      if (activeSessionId) {
        sendMessage(text, { reasoning });
        return;
      }
      try {
        const session = await createSession();
        onSessionChange(session._id);
        onSessionsDirty();
        sendMessage(text, { reasoning, sessionId: session._id });
      } catch {
        toast("Could not open a chat — is the backend running?", "error");
      }
    },
    [activeSessionId, sendMessage, onSessionChange, onSessionsDirty, toast],
  );

  const handleUpload = useCallback(
    async (files: File[]) => {
      if (!files.length || uploading) return;
      if (!activeSessionId) {
        toast("Open or create a chat first — documents belong to one chat.", "error");
        return;
      }
      setUploading(true);
      try {
        const result = await uploadFiles(files, activeSessionId);
        const chunks =
          typeof result?.chunk_count === "number"
            ? result.chunk_count
            : typeof result?.indexed === "number"
              ? result.indexed
              : 0;
        if (chunks === 0) {
          toast(
            `Uploaded ${files.length} file(s) but no text chunks were indexed — files may be empty or unparseable.`,
            "error",
          );
        } else {
          toast(
            `Indexed ${chunks} chunk${chunks === 1 ? "" : "s"} from ${files.length} document${files.length === 1 ? "" : "s"} — ask away!`,
            "success",
          );
        }
      } catch (err) {
        toast(
          err instanceof Error ? err.message : "Document upload failed",
          "error",
        );
      } finally {
        setUploading(false);
      }
    },
    [uploading, toast, activeSessionId],
  );

  /* Drag & drop document ingestion */
  const hasAcceptedFiles = (files: FileList | null) =>
    Boolean(
      files?.length &&
        Array.from(files).some((f) =>
          ACCEPTED_EXTENSIONS.some((ext) => f.name.toLowerCase().endsWith(ext)),
        ),
    );

  const onDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    dragDepthRef.current += 1;
    if (hasAcceptedFiles(e.dataTransfer?.files ?? null)) setDragActive(true);
  };
  const onDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    dragDepthRef.current -= 1;
    if (dragDepthRef.current <= 0) {
      dragDepthRef.current = 0;
      setDragActive(false);
    }
  };
  const onDragOver = (e: React.DragEvent) => e.preventDefault();
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    dragDepthRef.current = 0;
    setDragActive(false);
    if (hasAcceptedFiles(e.dataTransfer?.files ?? null)) {
      void handleUpload(Array.from(e.dataTransfer.files));
    }
  };

  return (
    <div
      className="flex flex-1 flex-col h-full bg-background relative overflow-hidden"
      onDragEnter={onDragEnter}
      onDragLeave={onDragLeave}
      onDragOver={onDragOver}
      onDrop={onDrop}
    >
      {/* Top bar */}
      <div className="flex items-center h-12 shrink-0 px-3 border-b border-border/40 bg-card/20 backdrop-blur supports-[backdrop-filter]:bg-card/20">
        {!sidebarOpen && (
          <motion.div
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.2 }}
          >
            <Button
              variant="ghost"
              size="icon"
              onClick={onToggleSidebar}
              className="h-8 w-8 text-foreground/50 hover:text-foreground hover:bg-accent/10 mr-2"
              aria-label="Open sidebar"
            >
              <PanelLeft className="h-4 w-4" />
            </Button>
          </motion.div>
        )}
        <div className="flex-1" />
        <div className="flex items-center gap-2 text-sm">
          <ConnectionDot />
          <span className="font-display font-medium tracking-tight">RAGnostic</span>
          <span className="hidden sm:inline-flex rounded-full bg-accent/10 border border-accent/20 px-2 py-0.5 text-[11px] font-medium text-accent">ADAPTIVE</span>
        </div>
        <div className="flex-1" />
      </div>

      {/* Messages or Empty state */}
      {hasMessages ? (
        <MessageList
          messages={messages}
          isStreaming={isStreaming}
          onRegenerate={regenerate}
          onEdit={editAndResend}
          onFollowUp={(q) => sendMessage(q)}
        />
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center px-4 pb-32">
          <EmptyState />
        </div>
      )}

      {/* Bottom composer area */}
      <div
        className={cn(
          "shrink-0 pb-4 pt-2 transition-all duration-300",
          hasMessages ? "" : "absolute bottom-0 left-0 right-0",
        )}
      >
        {/* Suggestion chips — only show when empty */}
        {!hasMessages && (
          <div className="mb-4">
            <SuggestionChips onSelect={handleSuggestion} />
          </div>
        )}

        <InputComposer
          onSend={handleSend}
          onStop={stopStreaming}
          isStreaming={isStreaming}
          sessionId={activeSessionId}
          onUploadFiles={(files) => void handleUpload(files)}
          uploading={uploading}
        />
      </div>

      {/* Drag & drop overlay */}
      <AnimatePresence>
        {dragActive && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center bg-background/70 backdrop-blur-sm"
          >
            <div className="flex flex-col items-center gap-3 rounded-3xl border-2 border-dashed border-sky-400/50 bg-card/80 px-12 py-10">
              <UploadCloud className="h-10 w-10 text-sky-400" />
              <p className="text-sm font-medium text-foreground/85">
                Drop documents to index them
              </p>
              <p className="text-xs text-foreground/45">PDF, TXT, Markdown, PPTX — indexed into this chat only</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
