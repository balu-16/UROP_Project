/**
 * Shared framer-motion presets — one place for the app's motion language.
 * Durations: micro 0.15 · base 0.25 · entrance 0.45. Easing: gentle expo-out.
 */
import type { Transition, Variants } from "framer-motion";

export const EASE_OUT = [0.21, 0.47, 0.32, 0.98] as const;

export const springSoft: Transition = {
  type: "spring",
  stiffness: 260,
  damping: 30,
  mass: 0.9,
};

export const springSnappy: Transition = {
  type: "spring",
  stiffness: 420,
  damping: 34,
};

export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 14 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.45, ease: EASE_OUT },
  },
};

export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: 0.35, ease: "easeOut" } },
};

export const fadeInFast: Variants = {
  hidden: { opacity: 0, y: 6 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.2, ease: "easeOut" },
  },
  exit: { opacity: 0, y: -4, transition: { duration: 0.15 } },
};

/** Parent wrapper that staggers `fadeUp`-style children. */
export const staggerContainer: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06, delayChildren: 0.05 } },
};

/** Entrance for chat messages — quick, no stagger (conversation-like). */
export const messageEntrance: Variants = {
  hidden: { opacity: 0, y: 10 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.25, ease: EASE_OUT },
  },
  exit: { opacity: 0, transition: { duration: 0.12 } },
};
