/**
 * AskAiButton.tsx - Floating "Ask AI" button.
 *
 * A fixed-position button that opens the AI Copilot Sheet.
 * Placed at bottom-right, above the toaster (z-50 vs toaster z-[100]).
 */
import { useTranslation } from "react-i18next";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface AskAiButtonProps {
        readonly onClick: () => void;
        /** Optional label override; defaults to i18n "ai.askButton" */
        readonly label?: string;
}

export function AskAiButton({ onClick, label }: AskAiButtonProps) {
        const { t } = useTranslation();

        return (
                <Button
                        onClick={onClick}
                        className="fixed bottom-6 right-6 z-50 h-12 px-5 rounded-full bg-danger hover:bg-danger/90 text-white shadow-lg shadow-red-900/50 hover:shadow-red-900/70 transition-all hover:scale-105 gap-2 font-medium"
                        title={t("ai.title", "Ask AI Copilot")}
                >
                        <Sparkles className="w-5 h-5" />
                        <span className="hidden sm:inline">
                                {label || t("ai.askButton", "Ask AI")}
                        </span>
                </Button>
        );
}
