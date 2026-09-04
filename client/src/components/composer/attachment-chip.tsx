import { useMemo } from "react";
import { FileText, Presentation, FileType, Loader2, Check, AlertTriangle, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Attachment } from "@/types";

export type AttachmentKind = Attachment["kind"];

export function kindForFilename(name: string): AttachmentKind {
  const ext = name.toLowerCase().split(".").pop() || "";
  if (ext === "pdf") return "pdf";
  if (ext === "pptx") return "slides";
  return "text";
}

export function kindLabel(kind: AttachmentKind): string {
  switch (kind) {
    case "pdf":
      return "PDF";
    case "slides":
      return "Presentation";
    default:
      return "Document";
  }
}

const KIND_STYLES: Record<AttachmentKind, { icon: typeof FileText; className: string }> = {
  pdf: { icon: FileText, className: "text-red-400" },
  slides: { icon: Presentation, className: "text-orange-400" },
  text: { icon: FileType, className: "text-foreground/50" },
};

export type PendingStatus = "indexing" | "ready" | "error" | "deleting";

interface AttachmentChipProps {
  name: string;
  kind?: AttachmentKind;
  /** Pending-composer mode: shows indexing status + remove button. Omit for sent-message display. */
  status?: PendingStatus;
  onRemove?: () => void;
  className?: string;
}

/** File chip shared by the composer (pending, removable) and sent user messages (static). */
export function AttachmentChip({ name, kind, status, onRemove, className }: AttachmentChipProps) {
  const resolved = useMemo(() => kind ?? kindForFilename(name), [kind, name]);
  const { icon: Icon, className: iconClassName } = KIND_STYLES[resolved];
  const removable = Boolean(onRemove);

  return (
    <div
      className={cn(
        "flex w-fit max-w-full items-center gap-2.5 rounded-xl border border-border bg-card py-2 pl-3 pr-2.5 text-left shadow-subtle",
        className,
      )}
    >
      <span className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-secondary", iconClassName)}>
        <Icon className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px] font-medium text-foreground">{name}</span>
        <span className="flex items-center gap-1 text-[11px] text-foreground/45">
          {kindLabel(resolved)}
          {(status === "indexing" || status === "deleting") && (
            <Loader2 className="h-3 w-3 animate-spin text-foreground/40" />
          )}
          {status === "ready" && <Check className="h-3 w-3 text-emerald-500" />}
          {status === "error" && <AlertTriangle className="h-3 w-3 text-red-400" />}
        </span>
      </span>
      {removable && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${name}`}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-foreground/40 transition-colors hover:bg-secondary hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}
