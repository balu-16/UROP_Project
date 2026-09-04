const MAX_TITLE_LENGTH = 48;

/** Derive a sidebar title from the first message (or filename) of a chat. */
export function deriveTitle(text: string): string {
  const collapsed = text.replace(/\s+/g, " ").trim();
  if (!collapsed) return "New chat";
  if (collapsed.length <= MAX_TITLE_LENGTH) return collapsed;
  return `${collapsed.slice(0, MAX_TITLE_LENGTH).trimEnd()}…`;
}

/** Title for an upload-first chat, from the first filename (sans extension). */
export function titleForFilename(filename: string): string {
  const base = filename.replace(/\.[^.]+$/, "").trim();
  return deriveTitle(base || filename);
}
