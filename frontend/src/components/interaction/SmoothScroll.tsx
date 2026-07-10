/**
 * SmoothScroll — Smooth scrolling integration.
 *
 * The BAZSPARK app uses a fixed-height shell (h-screen overflow-hidden on AppShell)
 * with internal scroll on <main>. Lenis is designed for window-level scroll,
 * so applying it here would break internal scrolling. This component is kept
 * as a pass-through to preserve the App tree shape, without activating Lenis
 * on a layout that cannot use it safely.
 *
 * If the app ever moves to a full-page scroll model, re-enable Lenis here.
 */
import { type ReactNode } from "react";

interface SmoothScrollProps {
	children: ReactNode;
}

export function SmoothScroll({ children }: SmoothScrollProps) {
	return <>{children}</>;
}
