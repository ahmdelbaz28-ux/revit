/**
 * AskAiButton.tsx - Floating glass "Ask AI" button.
 *
 * V215 redesign: Frosted-glass pill with a gentle floating animation,
 * soft cyan glow that pulses, and a tonally-consistent palette (uses
 * the existing --primary cyan #22d3ee + --card #111827 tokens so the
 * button blends with the dark navy page background instead of fighting it).
 *
 * Animations + glass surface live in src/index.css under .ask-ai-button
 * so they can be reused and stay in one place. This component only owns
 * layout + label + accessibility.
 *
 * Accessibility:
 *   - aria-label + title for screen readers
 *   - focus-visible outline (cyan) for keyboard users
 *   - respects prefers-reduced-motion (CSS handles it)
 *   - keyboard shortcut Ctrl+J still works (handled in App.tsx)
 *
 * The button is rendered globally in App.tsx so it shows on EVERY
 * protected page — no per-page wiring needed.
 */
import { useTranslation } from "react-i18next";
import { Sparkles } from "lucide-react";

export interface AskAiButtonProps {
        readonly onClick: () => void;
        readonly label?: string;
}

export function AskAiButton({ onClick, label }: AskAiButtonProps) {
        const { t, i18n } = useTranslation();
        const buttonText = label || t("ai.askButton", "Ask AI");
        const ariaLabel = t("ai.title", "Ask AI Copilot");
        // V215 self-critique: In RTL layouts (Arabic), the button should anchor
        // to the left edge, not the right, so it doesn't overlap the sidebar
        // which flips to the right side in RTL mode.
        const isRTL = i18n.language === "ar" || i18n.dir() === "rtl";
        const positionClass = isRTL ? "left-6" : "right-6";
        // V215 self-critique: Show platform-appropriate keyboard shortcut hint.
        // Mac users expect ⌘, Windows/Linux users expect Ctrl.
        const isMac =
                typeof navigator !== "undefined" &&
                (navigator.platform.toLowerCase().includes("mac") ||
                        navigator.userAgent.toLowerCase().includes("mac"));
        const shortcutHint = isMac ? "⌘J" : "Ctrl+J";

        return (
                <button
                        type="button"
                        onClick={onClick}
                        aria-label={ariaLabel}
                        title={ariaLabel}
                        className={`ask-ai-button fixed bottom-6 ${positionClass} z-50 inline-flex h-12 items-center gap-2 rounded-full px-5 font-medium tracking-wide shadow-lg`}
                >
                        <Sparkles className="ask-ai-sparkle h-4 w-4 text-cyan-300" />
                        <span className="hidden text-sm sm:inline">
                                {buttonText}
                        </span>
                        {/* Tiny keyboard-hint chip — visible only on md+ screens */}
                        <kbd
                                className="ml-1 hidden items-center rounded border border-cyan-400/25 bg-cyan-400/5 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-cyan-300/80 md:inline-flex"
                                aria-hidden="true"
                        >
                                {shortcutHint}
                        </kbd>
                </button>
        );
}
