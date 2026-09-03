"use client";

interface EmptyStateProps {
  userName?: string;
}

export function EmptyState({ userName }: EmptyStateProps) {
  const displayName = userName || "there";
  return (
    <div className="flex select-none flex-col items-center justify-center px-6 py-8 text-center">
      <h1 className="text-balance text-[26px] font-semibold leading-tight tracking-tight text-foreground sm:text-[30px]">
        Hey, {displayName}.
      </h1>
      <p className="mt-1 text-balance text-[26px] font-semibold leading-tight tracking-tight text-foreground/40 sm:text-[30px]">
        What can I help with?
      </p>
      <p className="mt-3 max-w-[420px] text-balance text-sm leading-relaxed text-foreground/55">
        Drop PDFs, ask questions, and get cited answers. Your documents stay scoped to this chat.
      </p>
    </div>
  );
}
