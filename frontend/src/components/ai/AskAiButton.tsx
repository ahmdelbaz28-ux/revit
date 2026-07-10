/**
 * AskAiButton.tsx - Floating "Ask AI" button.
 *
 * V223: Blue, no borders, no shadow glow, clean flat engineering style.
 */
import { useTranslation } from "react-i18next";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface AskAiButtonProps {
	readonly onClick: () => void;
	readonly label?: string;
}

export function AskAiButton({ onClick, label }: AskAiButtonProps) {
	const { t } = useTranslation();

	return (
		<Button
			onClick={onClick}
			className="fixed bottom-6 right-6 z-50 h-10 px-4 rounded-md bg-primary hover:bg-primary/90 text-primary-foreground transition-colors gap-1.5 font-medium"
			title={t("ai.title", "Ask AI Copilot")}
		>
			<Sparkles className="w-4 h-4" />
			<span className="hidden sm:inline">
				{label || t("ai.askButton", "Ask AI")}
			</span>
		</Button>
	);
}
