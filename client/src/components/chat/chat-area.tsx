"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { FileText, PanelLeft, UploadCloud, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { EmptyState } from "./empty-state";
import { MessageList } from "./message-list";
import { InputComposer } from "@/components/composer/input-composer";
import type { PendingAttachment } from "@/components/composer/input-composer";
import { SuggestionChips } from "@/components/composer/suggestion-chips";
import { ConnectionDot } from "./connection-dot";
import { kindForFilename, type PendingStatus } from "@/components/composer/attachment-chip";
import { useChat } from "@/hooks/use-chat";
import { useKeyboardShortcuts } from "@/hooks/use-keyboard";
import { deleteDocument, uploadFiles, createSession, listDocuments } from "@/lib/api";
import { deriveTitle, titleForFilename } from "@/lib/title";
import type { Attachment } from "@/types";

interface ChatAreaProps {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  activeSessionId: string | null;
  onSessionChange: (sessionId: string) => void;
  onSessionsDirty: () => void;
}

const ACCEPTED_EXTENSIONS = [".pdf", ".txt", ".md", ".markdown", ".pptx"];

interface PendingFile {
  id: string;
  name: string;
  file: File;
  status: PendingStatus;
  /** Backend document _id once indexed (enables un-upload via DELETE). */
  documentId?: string;
}

interface SessionDoc {
  name: string;
  documentId?: string;
}

const docsKey = (sessionId: string | null) => `ragnostic_docs_${sessionId || "new"}`;

function toComposerPending(pending: PendingFile[]): PendingAttachment[] {
  return pending.map((p) => ({
    id: p.id,
    name: p.name,
    status: p.status,
    ...(p.documentId ? { documentId: p.documentId } : {}),
  }));
}

function parseSessionDocs(raw: string | null): SessionDoc[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.flatMap((d): SessionDoc[] => {
      if (typeof d === "string") return [{ name: d }]; // legacy shape
      if (d && typeof d === "object" && typeof (d as { name?: unknown }).name === "string") {
        const doc = d as { name: string; documentId?: unknown };
        return [{
          name: doc.name,
          ...(typeof doc.documentId === "string" ? { documentId: doc.documentId } : {}),
        }];
      }
      return [];
    });
  } catch {
    return [];
  }
}

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
  const [pending, setPending] = useState<PendingFile[]>([]);
  const [sessionDocs, setSessionDocs] = useState<SessionDoc[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const dragDepthRef = useRef(0);
  // Tracks the currently displayed session so late upload completions for a
  // previous chat write that chat's cache key without overwriting the live strip.
  const activeSessionRef = useRef(activeSessionId);
  activeSessionRef.current = activeSessionId;

  const hasMessages = messages.length > 0;
  const indexing = pending.some((p) => p.status === "indexing");

  /* Indexed documents for this chat: server truth wins, localStorage is the
     offline cache (survives reloads; per-message chips stay live-session
     only since history rows carry no attachments). */
  useEffect(() => {
    if (!activeSessionId) {
      setSessionDocs([]);
      setPending([]);
      return;
    }
    const sessionId = activeSessionId;
    let cancelled = false;
    try {
      setSessionDocs(parseSessionDocs(window.localStorage.getItem(docsKey(sessionId))));
    } catch {
      setSessionDocs([]);
    }
    void (async () => {
      try {
        const serverDocs = await listDocuments(sessionId);
        if (cancelled) return;
        const next = serverDocs
          .map((d) => ({
            name: String(d.filename || d._id),
            documentId: String(d._id),
          }))
          .filter((d) => d.documentId);
        setSessionDocs(next);
        try {
          window.localStorage.setItem(docsKey(sessionId), JSON.stringify(next));
        } catch {
          // storage unavailable — strip simply won't persist
        }
      } catch {
        // offline/backend down: keep localStorage cache
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeSessionId]);

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

  // Chatting requires an open chat: lazily create one on first send so the
  // composer never streams against a null session. The chat is titled from
  // the first message, so the sidebar never shows a wall of "New chat".
  const handleSend = useCallback(
    async (text: string, reasoning: boolean) => {
      const staged = pending.filter((p) => p.status !== "error");
      const attachments: Attachment[] | undefined = staged.length
        ? staged.map((p) => ({ name: p.name, kind: kindForFilename(p.name) }))
        : undefined;
      setPending([]);
      if (activeSessionId) {
        sendMessage(text, { reasoning, attachments });
        return;
      }
      try {
        const session = await createSession(deriveTitle(text));
        onSessionChange(session._id);
        onSessionsDirty();
        sendMessage(text, { reasoning, sessionId: session._id, attachments });
      } catch {
        // Restore staged files so the user doesn't lose them on failure
        setPending((prev) => {
          const ids = new Set(prev.map((p) => p.id));
          return [...staged.filter((p) => !ids.has(p.id)), ...prev];
        });
        toast("Could not open a chat — is the backend running?", "error");
      }
    },
    [activeSessionId, sendMessage, onSessionChange, onSessionsDirty, toast, pending],
  );

  const handleSuggestion = (text: string) => {
    void handleSend(text, true);
  };

  /* Un-upload: DELETE an ingested document, then drop its UI traces. */
  const unuploadDocument = useCallback(
    async (documentId: string, filename: string): Promise<boolean> => {
      if (!activeSessionId) return false;
      if (
        !window.confirm(
          `Remove "${filename}" from this chat? Its chunks and index entries will be deleted.`,
        )
      ) {
        return false;
      }
      try {
        await deleteDocument(documentId, activeSessionId);
        setSessionDocs((prev) => {
          const next = prev.filter((d) => d.documentId !== documentId);
          try {
            window.localStorage.setItem(docsKey(activeSessionId), JSON.stringify(next));
          } catch {
            // storage unavailable — strip simply won't persist
          }
          return next;
        });
        toast(`Removed ${filename} from this chat.`, "success");
        return true;
      } catch (err) {
        toast(err instanceof Error ? err.message : "Could not remove document", "error");
        return false;
      }
    },
    [activeSessionId, toast],
  );

  const handleRemovePending = useCallback(
    (id: string) => {
      const item = pending.find((p) => p.id === id);
      if (!item) return;
      if (item.documentId && item.status === "ready") {
        // Already ingested: delete on the backend first, drop the chip only
        // on success (rollback to ready on failure).
        setPending((prev) =>
          prev.map((p) => (p.id === id ? { ...p, status: "deleting" as const } : p)),
        );
        void (async () => {
          const ok = await unuploadDocument(item.documentId as string, item.name);
          if (ok) {
            setPending((prev) => prev.filter((p) => p.id !== id));
          } else {
            setPending((prev) =>
              prev.map((p) => (p.id === id ? { ...p, status: "ready" as const } : p)),
            );
          }
        })();
        return;
      }
      // Local-only (indexing/failed/never-uploaded): detach instantly, no API call.
      setPending((prev) => prev.filter((p) => p.id !== id));
    },
    [pending, unuploadDocument],
  );

  const handleRemoveSessionDoc = useCallback(
    (documentId: string | undefined, filename: string) => {
      if (!documentId) return;
      void unuploadDocument(documentId, filename);
    },
    [unuploadDocument],
  );

  const handleUpload = useCallback(
    async (files: File[]) => {
      const accepted = files.filter((f) =>
        ACCEPTED_EXTENSIONS.some((ext) => f.name.toLowerCase().endsWith(ext)),
      );
      if (!accepted.length) {
        toast("Only PDF, TXT, Markdown, and PPTX files can be indexed.", "error");
        return;
      }
      // Documents belong to exactly one chat: open one first when needed.
      // Upload-first chats are titled from the first filename.
      let sessionId = activeSessionId;
      if (!sessionId) {
        try {
          const session = await createSession(titleForFilename(accepted[0].name));
          sessionId = session._id;
          onSessionChange(sessionId);
          onSessionsDirty();
        } catch {
          toast("Could not open a chat — is the backend running?", "error");
          return;
        }
      }
      const targetSessionId: string = sessionId;
      const batch: PendingFile[] = accepted.map((file) => ({
        id: `${Date.now()}-${file.name}-${file.size}`,
        name: file.name,
        file,
        status: "indexing" as const,
      }));
      const batchIds = new Set(batch.map((b) => b.id));
      setPending((prev) => [...prev, ...batch]);
      try {
        const result = await uploadFiles(accepted, targetSessionId);
        const docs = result.documents;
        // Match uploads to IDs by _id, not by filename: duplicate filenames in
        // one batch would collide in a Map<filename,_id> (last wins, wrong ID).
        // Backend returns documents in upload order, so zip by index when the
        // counts match; otherwise fall back to per-filename queues.
        let docIds: (string | undefined)[];
        let names: string[];
        if (Array.isArray(docs) && docs.length === accepted.length) {
          docIds = docs.map((d) => (d?._id ? String(d._id) : undefined));
          names = accepted.map((f) => f.name);
        } else if (Array.isArray(docs) && docs.length) {
          const queueByName = new Map<string, string[]>();
          for (const d of docs) {
            const name = String(d?.filename || d?.metadata?.source || "");
            const docId = d?._id ? String(d._id) : "";
            if (!name || !docId) continue;
            const q = queueByName.get(name) || [];
            q.push(docId);
            queueByName.set(name, q);
          }
          docIds = accepted.map((f) => queueByName.get(f.name)?.shift());
          names = accepted.map((f) => f.name);
        } else {
          docIds = accepted.map(() => undefined);
          names = accepted.map((f) => f.name);
        }
        const idByBatchIndex = new Map<string, string>();
        batch.forEach((b, i) => {
          const docId = docIds[i];
          if (docId) idByBatchIndex.set(b.id, docId);
        });
        setPending((prev) =>
          prev.map((p) => {
            if (!batchIds.has(p.id)) return p;
            const docId = idByBatchIndex.get(p.id);
            // Files with no ID produced zero chunks: surface as error so the
            // chip stays removable and no unremovable strip entry is created.
            if (!docId) return { ...p, status: "error" as const };
            return { ...p, status: "ready" as const, documentId: docId };
          }),
        );
        // Always persist to the upload target's cache key; only touch live
        // strip state when the user is still viewing that chat.
        try {
          const cached = parseSessionDocs(window.localStorage.getItem(docsKey(targetSessionId)));
          names.forEach((n, i) => {
            const docId = docIds[i];
            if (!docId) return;
            if (!cached.some((d) => d.documentId === docId)) {
              cached.push({ name: n, documentId: docId });
            }
          });
          window.localStorage.setItem(docsKey(targetSessionId), JSON.stringify(cached));
        } catch {
          // storage unavailable — strip simply won't persist
        }
        if (activeSessionRef.current !== targetSessionId) return;
        setSessionDocs((prev) => {
          const merged = [...prev];
          names.forEach((n, i) => {
            const docId = docIds[i];
            if (!docId) return;
            if (!merged.some((d) => d.documentId === docId)) {
              merged.push({ name: n, documentId: docId });
            }
          });
          return merged;
        });
        const chunks =
          typeof result?.chunk_count === "number"
            ? result.chunk_count
            : typeof result?.indexed === "number"
              ? result.indexed
              : 0;
        if (chunks === 0) {
          toast(
            `Uploaded ${accepted.length} file(s) but no text chunks were indexed — files may be empty or unparseable.`,
            "error",
          );
        } else {
          toast(
            `Indexed ${chunks} chunk${chunks === 1 ? "" : "s"} from ${accepted.length} document${accepted.length === 1 ? "" : "s"} — ask away!`,
            "success",
          );
        }
      } catch (err) {
        setPending((prev) =>
          prev.map((p) => (batchIds.has(p.id) ? { ...p, status: "error" as const } : p)),
        );
        toast(
          err instanceof Error ? err.message : "Document upload failed",
          "error",
        );
      }
    },
    [toast, activeSessionId, onSessionChange, onSessionsDirty],
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
      <div className="grid h-14 shrink-0 grid-cols-[1fr_auto_1fr] items-center border-b border-border bg-background px-3">
        <div className="flex items-center">
          {!sidebarOpen && (
            <Button
              variant="ghost"
              size="icon"
              onClick={onToggleSidebar}
              className="h-9 w-9 text-foreground/60 hover:bg-secondary hover:text-foreground"
              aria-label="Open sidebar"
            >
              <PanelLeft className="h-4 w-4" />
            </Button>
          )}
        </div>
        <div className="flex items-center gap-2 text-sm">
          <ConnectionDot />
          <span className="text-sm font-medium tracking-tight">RAGnostic</span>
        </div>
        <div className="flex items-center justify-end">
          <span className="mono-meta hidden rounded-md border border-border bg-card px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-foreground/45 sm:inline-block">adaptive</span>
        </div>
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
        <div className="flex min-h-0 flex-1 flex-col items-center justify-center px-4">
          <EmptyState />
        </div>
      )}

      {/* Bottom composer area */}
      <div className="sticky bottom-0 shrink-0 bg-background px-0 pb-[max(1rem,env(safe-area-inset-bottom))] pt-2">
        {/* Suggestion chips — only show when empty */}
        {!hasMessages && (
          <div className="mb-3">
            <SuggestionChips onSelect={handleSuggestion} />
          </div>
        )}

        {/* Documents indexed in this chat (× un-uploads where tracked) */}
        {sessionDocs.length > 0 && (
          <div className="mb-2 flex flex-wrap justify-center gap-1.5 px-4">
            {sessionDocs.map((doc) => (
              <span
                key={`${doc.documentId || doc.name}`}
                title={doc.name}
                className="inline-flex max-w-[220px] items-center gap-1 rounded-full border border-border bg-card py-1 pl-2.5 pr-1 text-[11px] text-foreground/60"
              >
                <FileText className="h-3 w-3 shrink-0" />
                <span className="truncate">{doc.name}</span>
                {doc.documentId ? (
                  <button
                    type="button"
                    onClick={() => handleRemoveSessionDoc(doc.documentId, doc.name)}
                    aria-label={`Remove ${doc.name} from this chat`}
                    title={`Remove ${doc.name} from this chat`}
                    className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-foreground/40 transition-colors hover:bg-secondary hover:text-foreground"
                  >
                    <X className="h-3 w-3" />
                  </button>
                ) : null}
              </span>
            ))}
          </div>
        )}

        <InputComposer
          onSend={handleSend}
          onStop={stopStreaming}
          isStreaming={isStreaming}
          sessionId={activeSessionId}
          onUploadFiles={(files) => void handleUpload(files)}
          uploading={indexing}
          pending={toComposerPending(pending)}
          onRemovePending={handleRemovePending}
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
            className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center bg-background/80"
          >
            <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-foreground/25 bg-card px-10 py-8 text-center shadow-subtle">
              <UploadCloud className="h-8 w-8 text-foreground/60" />
              <p className="text-sm font-medium text-foreground">
                Drop documents to index them
              </p>
              <p className="text-xs text-foreground/50">PDF, TXT, Markdown, PPTX — staged in the message box</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
