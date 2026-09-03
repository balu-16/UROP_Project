/**
 * RAGnostic brand mark — three connected nodes forming a retrieval graph.
 * Single source of truth used across landing, auth, sidebar, and chat avatars.
 */
export function LogoMark({
  className,
  size = 22,
}: {
  className?: string;
  size?: number;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      aria-hidden
    >
      <circle cx="5" cy="18" r="2.4" fill="currentColor" opacity="0.55" />
      <circle cx="12" cy="5" r="2.4" fill="currentColor" />
      <circle cx="19" cy="15" r="2.4" fill="currentColor" opacity="0.75" />
      <path
        d="M6.3 16.2L10.8 7.2M13.8 6.6l3.9 6.4M7.4 17.4l9.2-1.8"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        opacity="0.45"
      />
    </svg>
  );
}
