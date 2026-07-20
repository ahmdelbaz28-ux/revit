/**
 * useGsapAnimations.ts — GSAP Animation Hook for BAZSPARK
 *
 * Provides reusable GSAP animation presets tailored to the
 * BAZSPARK engineering identity (fire alarm, CAD, BIM, AI).
 *
 * Usage:
 *   useGsapLogoAnimation(ref, { ... })
 *   useGsapSplitText(ref, { ... })
 *   useGsapScrollReveal(ref, { ... })
 */

import { useEffect, type RefObject } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { MotionPathPlugin } from "gsap/MotionPathPlugin";

// ─── Register GSAP Plugins (Core plugins only - Club plugins are optional) ──────────────────────────────────────────
gsap.registerPlugin(useGSAP, ScrollTrigger, MotionPathPlugin);

// ─── Optional Club GSAP Plugins (loaded dynamically if available) ──────────────────────────────────────────
// NOSONAR - typescript:S6564: Club GSAP plugins have no published TS types; `any` is needed because
// these are dynamically imported at runtime and passed to gsap.registerPlugin() which expects object types.
type SplitTextType = any;  // NOSONAR
type DrawSVGPluginType = any;  // NOSONAR
type CustomEaseType = any;  // NOSONAR

let SplitText: SplitTextType | null = null;
let DrawSVGPlugin: DrawSVGPluginType | null = null;
let CustomEase: CustomEaseType | null = null;

async function loadClubPlugins() {
  if (typeof window === "undefined") return;
  try {
    // Use dynamic import with string concatenation to avoid static analysis
    const splitTextModule = await import(/* webpackIgnore: true */ "gsap/SplitText");
    const drawSVGModule = await import(/* webpackIgnore: true */ "gsap/DrawSVGPlugin");
    const customEaseModule = await import(/* webpackIgnore: true */ "gsap/CustomEase");

    SplitText = splitTextModule.SplitText;
    DrawSVGPlugin = drawSVGModule.DrawSVGPlugin;
    CustomEase = customEaseModule.CustomEase;

    gsap.registerPlugin(SplitText, DrawSVGPlugin, CustomEase);
  } catch {
    // Club plugins not available - animations using them will gracefully degrade
    console.warn("[GSAP] Club plugins (SplitText, DrawSVGPlugin, CustomEase) not available. Some animations will be disabled.");
  }
}

// Load club plugins on client side
if (typeof window !== "undefined") {
  loadClubPlugins();
}

// ─── Import Centralized Presets ─────────────────────────────────────
import { initCustomEases } from "@/lib/gsap-presets";

// ─── Initialize Custom Eases (client-side only) ─────────────────────
if (typeof window !== "undefined") {
  initCustomEases();
}

// ─── Types ──────────────────────────────────────────────────────────

export interface LogoAnimationOptions {
  duration?: number;
  stagger?: number;
  flameEase?: string;
  bracketEase?: string;
}

export interface SplitTextOptions {
  type?: "chars" | "words" | "lines" | "chars words" | "words lines";
  stagger?: number;
  duration?: number;
  y?: number;
  opacity?: number;
  ease?: string;
  delay?: number;
}

export interface ScrollRevealOptions {
  y?: number;
  x?: number;
  opacity?: number;
  scale?: number;
  duration?: number;
  stagger?: number;
  start?: string;
  end?: string;
  ease?: string;
  scrub?: boolean | number;
}

export interface MotionPathOptions {
  path: string | SVGPathElement;
  duration?: number;
  repeat?: number;
  ease?: string;
  align?: string | SVGPathElement | null;
  alignOrigin?: [number, number];
}

// ─── Hook: Flame Logo Draw Animation ────────────────────────────────

export function useGsapLogoAnimation(
  containerRef: RefObject<HTMLElement | SVGSVGElement | null>,
  options: LogoAnimationOptions = {},
) {
  const {
    duration = 2.2,
    stagger = 0.15,
    flameEase = "bazspark-flame",
    bracketEase = "power3.out",
  } = options;

  useGSAP(
    () => {
      if (!containerRef.current) return;
      if (!DrawSVGPlugin) {
        console.warn("[GSAP] DrawSVGPlugin not available - logo draw animation disabled");
        return;
      }

      const tl = gsap.timeline({ defaults: { ease: flameEase } });

      // 1. Flame draws itself from bottom
      tl.fromTo(
        containerRef.current.querySelectorAll(".gsap-flame-path"),
        { drawSVG: "100% 100%" },
        { drawSVG: "0% 100%", duration },
      );

      // 2. Corner brackets draw in sequence
      tl.fromTo(
        containerRef.current.querySelectorAll(".gsap-bracket-path"),
        { drawSVG: "0%" },
        { drawSVG: "100%", duration: 1.2, stagger, ease: bracketEase },
        "-=0.8",
      );

      // 3. Subtle glow pulse after drawing
      tl.to(
        containerRef.current.querySelectorAll(".gsap-flame-glow"),
        {
          boxShadow: "0 0 30px rgba(239,68,68,0.4)",
          duration: 0.6,
          ease: "power2.out",
        },
        "-=0.3",
      );

      // 4. Continuous gentle flame flicker
      tl.to(
        containerRef.current.querySelectorAll(".gsap-flame-path"),
        {
          scale: 1.03,
          duration: 1.2,
          repeat: -1,
          yoyo: true,
          ease: "sine.inOut",
          transformOrigin: "50% 100%",
        },
        "+=0.5",
      );
    },
    { scope: containerRef },
  );
}

// ─── Hook: Split Text Animation ─────────────────────────────────────

export function useGsapSplitText(
  containerRef: RefObject<HTMLElement | null>,
  options: SplitTextOptions = {},
) {
  const {
    type = "chars",
    stagger = 0.03,
    duration = 0.8,
    y = 60,
    opacity = 0,
    ease = "back.out(1.7)",
    delay = 0,
  } = options;

  useGSAP(
    () => {
      if (!containerRef.current) return;

      const targets = containerRef.current.querySelectorAll(".gsap-split");

      targets.forEach((el) => {
        const split = new SplitText(el as HTMLElement, { type: type as "chars" | "words" | "lines" });
        const splitType = type.includes("chars") ? split.chars  // NOSONAR - typescript:S3358: nested ternary for split type selection is intentional
          : type.includes("words") ? split.words  // NOSONAR - typescript:S3358: nested ternary intentional for split type selection
          : split.lines;

        if (!splitType || splitType.length === 0) return;

        gsap.fromTo(
          splitType,
          { y, opacity },
          { y: 0, opacity: 1, duration, stagger, ease, delay },
        );
      });
    },
    { scope: containerRef },
  );
}

// ─── Hook: Scroll-Triggered Reveal ──────────────────────────────────

export function useGsapScrollReveal(
  containerRef: RefObject<HTMLElement | null>,
  options: ScrollRevealOptions = {},
) {
  const {
    y = 50,
    x = 0,
    opacity = 0,
    scale = 1,
    duration = 1,
    stagger = 0.1,
    start = "top 85%",
    end = "bottom 20%",
    ease = "power4.out",
    scrub = false,
  } = options;

  useGSAP(
    () => {
      if (!containerRef.current) return;

      const targets = containerRef.current.querySelectorAll(".gsap-reveal");

      targets.forEach((el) => {
        ScrollTrigger.create({
          trigger: el as HTMLElement,
          start,
          end,
          scrub,
          onEnter: () => {
            gsap.fromTo(
              el,
              { y, x, opacity, scale },
              { y: 0, x: 0, opacity: 1, scale: 1, duration, ease },
            );
          },
          once: true,
        });
      });
    },
    { scope: containerRef },
  );
}

// ─── Hook: Motion Path Animation ────────────────────────────────────

export function useGsapMotionPath(
  containerRef: RefObject<HTMLElement | null>,
  options: MotionPathOptions,
) {
  const { path, duration = 3, repeat = -1, ease = "none", align, alignOrigin } = options;

  useGSAP(
    () => {
      if (!containerRef.current) return;

      const targets = containerRef.current.querySelectorAll(".gsap-motion-path");

      targets.forEach((el) => {
        gsap.to(el, {
          motionPath: {
            path,
            align: align ?? undefined,
            alignOrigin,
          },
          duration,
          repeat,
          ease,
        });
      });
    },
    { scope: containerRef },
  );
}

// ─── Hook: Number Counter (for metrics) ─────────────────────────────

export function useGsapCounter(
  containerRef: RefObject<HTMLElement | null>,
  options: { duration?: number; ease?: string; start?: string } = {},
) {
  const { duration = 2, ease = "bazspark-ease", start = "top 85%" } = options;

  useGSAP(
    () => {
      if (!containerRef.current) return;

      const targets = containerRef.current.querySelectorAll(".gsap-counter");

      targets.forEach((el) => {
        const target = el as HTMLElement;
        const finalValue = parseFloat(target.dataset.value || "0");
        const suffix = target.dataset.suffix || "";
        const prefix = target.dataset.prefix || "";

        ScrollTrigger.create({
          trigger: target,
          start,
          once: true,
          onEnter: () => {
            const obj = { val: 0 };
            gsap.to(obj, {
              val: finalValue,
              duration,
              ease,
              onUpdate: () => {  // NOSONAR - typescript:S2004: nested callbacks intentional for GSAP animation sequence
                const formatted = finalValue % 1 === 0
                  ? Math.round(obj.val)
                  : obj.val.toFixed(1);
                target.textContent = `${prefix}${formatted}${suffix}`;
              },
            });
          },
        });
      });
    },
    { scope: containerRef },
  );
}

// ─── Hook: Engineering Grid Background Animation ────────────────────

export function useGsapGridBackground(
  canvasRef: RefObject<HTMLCanvasElement | null>,
) {
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const handleResize = () => {
      width = canvas!.width = window.innerWidth;
      height = canvas!.height = window.innerHeight;
    };
    window.addEventListener("resize", handleResize);

    // ─── Grid 3D perspective ───
    const gridSize = 40;
    let offset = 0;

    // ─── Nodes (sensor network) ───
    const nodes: { x: number; y: number; vx: number; vy: number; phase: number }[] = [];
    const nodeCount = Math.min(20, Math.floor((width * height) / 50000));
    for (let i = 0; i < nodeCount; i++) {
      nodes.push({
        x: Math.random() * width,  // NOSONAR - typescript:S2245: Math.random safe for canvas animation positioning
        y: Math.random() * height,  // NOSONAR - typescript:S2245
        vx: (Math.random() - 0.5) * 0.3,  // NOSONAR - typescript:S2245
        vy: (Math.random() - 0.5) * 0.3,  // NOSONAR - typescript:S2245
        phase: Math.random() * Math.PI * 2,  // NOSONAR - typescript:S2245
      });
    }

    // ─── Particles (sparks) ───
    const sparks: { x: number; y: number; vx: number; vy: number; life: number; maxLife: number; size: number }[] = [];
    const maxSparks = 40;

    const spawnSpark = () => {
      if (sparks.length >= maxSparks) return;
      sparks.push({
        x: Math.random() * width,  // NOSONAR - typescript:S2245
        y: height + 5,
        vx: (Math.random() - 0.5) * 0.6,  // NOSONAR - typescript:S2245
        vy: -Math.random() * 1.5 - 0.5,  // NOSONAR - typescript:S2245
        life: 1,
        maxLife: 80 + Math.random() * 60,  // NOSONAR - typescript:S2245
        size: Math.random() * 1.5 + 0.5,  // NOSONAR - typescript:S2245
      });
    };

    let time = 0;

    const animate = () => {
      time += 0.016;
      offset += 0.3;
      ctx.clearRect(0, 0, width, height);

      // ─── 3D perspective grid ───
      ctx.save();
      ctx.strokeStyle = "rgba(239, 68, 68, 0.04)";
      ctx.lineWidth = 0.5;
      const perspective = 0.4;
      const vanishY = height * 0.35;

      for (let i = -10; i < width / gridSize + 10; i++) {
        const x = i * gridSize + offset % gridSize;
        const topY = (vanishY - height * 0.3) * perspective + height * 0.3;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x + 40, height);
        ctx.stroke();

        ctx.beginPath();
        ctx.moveTo(x - 40, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
      ctx.restore();

      // ─── Horizontal grid lines ───
      ctx.strokeStyle = "rgba(59, 130, 246, 0.03)";
      ctx.lineWidth = 0.5;
      for (let y = offset % gridSize; y < height; y += gridSize) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }

      // ─── Nodes network ───
      nodes.forEach((n, i) => {
        n.x += n.vx;
        n.y += n.vy;
        if (n.x < 0 || n.x > width) n.vx *= -1;
        if (n.y < 0 || n.y > height) n.vy *= -1;

        // Connections
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = n.x - nodes[j].x;
          const dy = n.y - nodes[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 120) {
            ctx.strokeStyle = `rgba(244, 63, 94, ${(1 - dist / 120) * 0.06})`;
            ctx.lineWidth = 0.6;
            ctx.beginPath();
            ctx.moveTo(n.x, n.y);
            ctx.lineTo(nodes[j].x, nodes[j].y);
            ctx.stroke();
          }
        }

        // Node pulse
        const pulse = Math.sin(time * 2 + n.phase) * 0.5 + 0.5;
        ctx.fillStyle = `rgba(244, 63, 94, ${0.15 + pulse * 0.2})`;
        ctx.beginPath();
        ctx.arc(n.x, n.y, 2 + pulse * 1.5, 0, Math.PI * 2);
        ctx.fill();
      });

      // ─── Rising sparks (flame-like) ───
      if (Math.random() < 0.2) spawnSpark();  // NOSONAR - typescript:S2245: Math.random safe for visual canvas animation timing

      for (let i = sparks.length - 1; i >= 0; i--) {
        const s = sparks[i];
        s.x += s.vx;
        s.y += s.vy;
        s.life -= 1 / s.maxLife;

        if (s.life <= 0) {
          sparks.splice(i, 1);
          continue;
        }

        const grad = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, s.size * 3);
        grad.addColorStop(0, `rgba(249, 115, 22, ${s.life * 0.6})`);
        grad.addColorStop(1, `rgba(249, 115, 22, 0)`);
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.size * 3, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = `rgba(244, 63, 94, ${s.life * 0.8})`;
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.size, 0, Math.PI * 2);
        ctx.fill();
      }

      animId = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      window.removeEventListener("resize", handleResize);
      cancelAnimationFrame(animId);
    };
  }, [canvasRef]);
}

// ─── Hook: Infinite Marquee / Diagnostic Ticker ─────────────────────

export function useGsapTicker(
  containerRef: RefObject<HTMLElement | null>,
  options: { duration?: number } = {},
) {
  const { duration = 20 } = options;

  useGSAP(
    () => {
      if (!containerRef.current) return;

      const ticker = containerRef.current.querySelector(".gsap-ticker-content");
      if (!ticker) return;

      const clone = ticker.cloneNode(true) as HTMLElement;
      containerRef.current.appendChild(clone);

      const totalWidth = ticker.scrollWidth;

      gsap.to([ticker, clone], {
        x: () => -totalWidth,
        duration,
        repeat: -1,
        ease: "none",
      });
    },
    { scope: containerRef },
  );
}
