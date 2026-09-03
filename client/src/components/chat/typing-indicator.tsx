"use client";

export function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 px-1 py-3" aria-label="Assistant is typing">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-pulse rounded-full bg-foreground/35"
          style={{ animationDelay: `${i * 180}ms` }}
        />
      ))}
    </div>
  );
}
