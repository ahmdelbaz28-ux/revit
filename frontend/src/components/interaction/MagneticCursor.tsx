/**
 * MagneticCursor — Custom cursor with magnetic attraction.
 *
 * Default: 8px cyan dot
 * Button hover: 60px circle, bg-cyan/10, invert
 * Text hover: 2px × 24px vertical line
 * Uses lerp easing (factor 0.15) for smooth follow
 * Disabled on mobile (< 1024px) and reduced-motion
 */
import { useEffect, useRef, useState } from "react";

export function MagneticCursor() {
        const cursorRef = useRef<HTMLDivElement>(null);
        const [isDesktop, setIsDesktop] = useState(false);

        useEffect(() => {
                const mq = window.matchMedia("(min-width: 1024px)");
                const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
                const active = mq.matches && !reduced.matches;
                setIsDesktop(active);

                // Only hide native cursor when MagneticCursor is actually active
                if (active) {
                        document.documentElement.classList.add("cursor-active");
                }

                const update = () => {
                        const nowActive = mq.matches && !reduced.matches;
                        setIsDesktop(nowActive);
                        if (nowActive) {
                                document.documentElement.classList.add("cursor-active");
                        } else {
                                document.documentElement.classList.remove("cursor-active");
                        }
                };
                mq.addEventListener("change", update);
                return () => {
                        mq.removeEventListener("change", update);
                        document.documentElement.classList.remove("cursor-active");
                };
        }, []);

        useEffect(() => {
                if (!isDesktop || !cursorRef.current) return;

                const cursor = cursorRef.current;
                let mouseX = window.innerWidth / 2;
                let mouseY = window.innerHeight / 2;
                let cursorX = mouseX;
                let cursorY = mouseY;
                let rafId = 0;

                const lerp = (start: number, end: number, factor: number) =>
                        start + (end - start) * factor;

                const animate = () => {
                        cursorX = lerp(cursorX, mouseX, 0.15);
                        cursorY = lerp(cursorY, mouseY, 0.15);
                        cursor.style.transform = `translate3d(${cursorX - 4}px, ${cursorY - 4}px, 0)`;
                        rafId = requestAnimationFrame(animate);
                };

                const onMouseMove = (e: MouseEvent) => {
                        mouseX = e.clientX;
                        mouseY = e.clientY;
                };

                const onMouseOver = (e: MouseEvent) => {
                        const target = e.target as HTMLElement;
                        if (!target) return;

                        if (
                                target.closest("button, a, [role='button'], input, textarea, select, .magnetic-target")
                        ) {
                                cursor.classList.add("hovering-button");
                                cursor.classList.remove("hovering-text");
                        } else if (target.closest("h1, h2, h3, h4, h5, p, span, .text-target")) {
                                cursor.classList.add("hovering-text");
                                cursor.classList.remove("hovering-button");
                        } else {
                                cursor.classList.remove("hovering-button", "hovering-text");
                        }
                };

                window.addEventListener("mousemove", onMouseMove);
                window.addEventListener("mouseover", onMouseOver);
                rafId = requestAnimationFrame(animate);

                return () => {
                        window.removeEventListener("mousemove", onMouseMove);
                        window.removeEventListener("mouseover", onMouseOver);
                        cancelAnimationFrame(rafId);
                };
        }, [isDesktop]);

        if (!isDesktop) return null;

        return (
                <div ref={cursorRef} className="magnetic-cursor">
                        <div className="magnetic-cursor-dot" />
                </div>
        );
}
