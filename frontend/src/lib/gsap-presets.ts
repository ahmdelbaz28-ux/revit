/**
 * gsap-presets.ts — Unified GSAP Configuration for BAZSPARK
 *
 * Centralized animation presets, easings, and constants
 * to ensure consistent, professional engineering feel across the platform.
 */

import { CustomEase } from "gsap/CustomEase";
import gsap from "gsap";

// ─── Register CustomEase ─────────────────────────────────────────────
if (typeof window !== "undefined") {
  gsap.registerPlugin(CustomEase);
}

// ─── Custom Eases — BAZSPARK Engineering Identity ───────────────────
// Professional, precise, no-bounce easings suitable for safety-critical UI

export const easings = {
  /** Default engineering ease — smooth, decisive, no overshoot */
  engineering: "bazspark-ease",

  /** Flame/organic feel — for logo, fire-related elements */
  flame: "bazspark-flame",

  /** Quick UI interactions — buttons, toggles, hover */
  ui: "power2.out",

  /** Panel/sheet animations — slide in/out */
  panel: "expo.out",

  /** Data/metric animations — counters, charts */
  data: "power3.out",

  /** Staggered entrance — lists, grids */
  stagger: "power2.out",

  /** Scroll-triggered reveals */
  scroll: "power4.out",
} as const;

// ─── Initialize Custom Eases (client-side only) ─────────────────────
export function initCustomEases(): void {
  if (typeof window === "undefined") return;

  try {
    CustomEase.create("bazspark-ease", "M0,0 C0.25,0.1 0.25,1 1,1");
    CustomEase.create("bazspark-bounce", "M0,0 C0.25,0.46 0.45,0.94 1,1");
    CustomEase.create("bazspark-flame", "M0,0 C0.5,0.05 0.5,0.95 1,1");
  } catch {
    // CustomEase may not be available in all builds
  }
}

// ─── Duration Constants ─────────────────────────────────────────────
export const durations = {
  /** Instant feedback — button press, toggle */
  instant: 0.1,

  /** Fast UI — tooltip, hover, small transition */
  fast: 0.2,

  /** Standard UI — panel slide, modal, tab switch */
  standard: 0.3,

  /** Deliberate — drawer, sidebar, complex panel */
  deliberate: 0.4,

  /** Entrance animations — page load, section reveal */
  entrance: 0.6,

  /** Hero/logo animations — brand moments */
  hero: 1.2,

  /** Counter/metric animations */
  counter: 1.5,

  /** Infinite/ambient animations */
  ambient: 20,
} as const;

// ─── Stagger Constants ──────────────────────────────────────────────
export const staggers = {
  /** Tight — list items, grid children */
  tight: 0.04,

  /** Standard — cards, sections */
  standard: 0.08,

  /** Loose — major sections, hero elements */
  loose: 0.12,

  /** Logo-specific */
  logo: 0.15,
} as const;

// ─── ScrollTrigger Defaults ─────────────────────────────────────────
export const scrollDefaults = {
  /** Start animation when element top hits 85% of viewport */
  start: "top 85%",

  /** End when element bottom hits 20% of viewport */
  end: "bottom 20%",

  /** Play once, don't scrub */
  scrub: false,

  /** Only trigger once */
  once: true,

  /** Default ease for scroll reveals */
  ease: easings.scroll,
} as const;

// ─── Reduced Motion Support ─────────────────────────────────────────
/**
 * Returns true if user prefers reduced motion.
 * Should be checked before running non-essential animations.
 */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Returns animation config adjusted for reduced motion preference.
 * If reduced motion is preferred, returns minimal/zero duration config.
 */
export function getReducedMotionConfig<T extends Record<string, unknown>>(
  config: T,
  reducedOverrides: Partial<T> = { duration: 0.01, stagger: 0 } as unknown as Partial<T>
): T {
  if (prefersReducedMotion()) {
    return { ...config, ...reducedOverrides } as T;
  }
  return config;
}

// ─── Color Constants (BAZSPARK Brand) ───────────────────────────────
export const colors = {
  /** Primary coral-red — brand, fire, alerts */
  primary: "#ef4444", // red-500
  primaryDark: "#be123c", // rose-700
  primaryLight: "#f87171", // red-400

  /** Secondary blue — engineering, data, water */
  secondary: "#3b82f6", // blue-500
  secondaryDark: "#1d4ed8", // blue-700
  secondaryLight: "#93c5fd", // blue-300

  /** Amber/orange — warnings, sparks, heat */
  amber: "#f97316", // orange-500
  amberLight: "#fb923c", // orange-400

  /** Success green — compliant, safe */
  success: "#22c55e", // green-500

  /** Surface/background */
  surface: "#0f172a", // slate-900
  surfaceElevated: "#1e293b", // slate-800
  border: "#334155", // slate-700

  /** Text */
  textPrimary: "#f8fafc", // slate-50
  textSecondary: "#94a3b8", // slate-400
  textMuted: "#64748b", // slate-500
} as const;

// ─── Shadow/Glow Presets ────────────────────────────────────────────
export const shadows = {
  /** Subtle glow for primary elements */
  primaryGlow: "0 0 20px rgba(239, 68, 68, 0.3)",

  /** Stronger glow for active/focused state */
  primaryGlowStrong: "0 0 40px rgba(239, 68, 68, 0.5)",

  /** Flame/orange glow */
  flameGlow: "0 0 30px rgba(249, 115, 22, 0.4)",

  /** Engineering blue glow */
  engineeringGlow: "0 0 20px rgba(59, 130, 246, 0.3)",

  /** Panel elevation */
  panel: "0 4px 24px rgba(0, 0, 0, 0.4)",

  /** Modal/drawer elevation */
  modal: "0 16px 64px rgba(0, 0, 0, 0.6)",
} as const;

// ─── Animation Presets (Ready-to-use configs) ───────────────────────
export const presets = {
  /** Button press/tap feedback */
  buttonPress: {
    scale: 0.97,
    duration: durations.instant,
    ease: easings.ui,
  },

  /** Button hover */
  buttonHover: {
    scale: 1.02,
    duration: durations.fast,
    ease: easings.ui,
  },

  /** Card entrance (staggered) */
  cardEntrance: {
    y: 30,
    opacity: 0,
    duration: durations.entrance,
    ease: easings.stagger,
    stagger: staggers.standard,
  },

  /** Section reveal on scroll */
  sectionReveal: {
    y: 50,
    opacity: 0,
    duration: durations.entrance,
    ...scrollDefaults,
  },

  /** Metric counter */
  metricCounter: {
    duration: durations.counter,
    ease: easings.data,
    start: scrollDefaults.start,
  },

  /** Logo draw animation */
  logoDraw: {
    duration: durations.hero,
    stagger: staggers.logo,
    flameEase: easings.flame,
    bracketEase: easings.engineering,
  },

  /** Modal/sheet slide up */
  modalSlideUp: {
    y: 40,
    opacity: 0,
    duration: durations.deliberate,
    ease: easings.panel,
  },

  /** Sidebar/drawer slide */
  drawerSlide: {
    x: -300,
    opacity: 0,
    duration: durations.deliberate,
    ease: easings.panel,
  },

  /** Tab/panel crossfade */
  crossfade: {
    opacity: 0,
    duration: durations.standard,
    ease: easings.ui,
  },

  /** Tooltip/popover */
  tooltip: {
    scale: 0.9,
    opacity: 0,
    duration: durations.fast,
    ease: easings.ui,
  },

  /** Loading spinner */
  spinner: {
    rotation: 360,
    duration: 1,
    ease: "none",
    repeat: -1,
  },

  /** Pulse (for live indicators, recording dots) */
  pulse: {
    scale: [1, 1.1, 1],
    opacity: [0.6, 1, 0.6],
    duration: 1.5,
    ease: "sine.inOut",
    repeat: -1,
  },
} as const;

// ─── Utility Functions ──────────────────────────────────────────────

/**
 * Creates a staggered delay for index-based animations
 */
export function staggerDelay(index: number, baseStagger: number = staggers.standard): number {
  return index * baseStagger;
}

/**
 * Creates a timeline with BAZSPARK defaults
 */
export function createTimeline(defaults?: gsap.TimelineVars): gsap.core.Timeline {
  return gsap.timeline({
    defaults: {
      ease: easings.engineering,
      duration: durations.standard,
      ...defaults,
    },
  });
}

/**
 * Kills all animations on an element (cleanup)
 */
export function killAnimations(target: gsap.TweenTarget): void {
  gsap.killTweensOf(target);
  ScrollTrigger.getAll().forEach((st) => {
    if (st.trigger === target || (st.vars.trigger === target)) {
      st.kill();
    }
  });
}

// ─── Re-export ScrollTrigger for convenience ────────────────────────
import { ScrollTrigger } from "gsap/ScrollTrigger";
gsap.registerPlugin(ScrollTrigger);

export { ScrollTrigger };
export { gsap };
export { CustomEase };
export { SplitText } from "gsap/SplitText";
export { DrawSVGPlugin } from "gsap/DrawSVGPlugin";
export { TextPlugin } from "gsap/TextPlugin";
export { Flip } from "gsap/Flip";
export { MotionPathPlugin } from "gsap/MotionPathPlugin";
export { Observer } from "gsap/Observer";