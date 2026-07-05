/**
 * ContextualHelpButton.tsx — Per-page help button
 *
 * Displays a floating help button in the top-right of each page.
 * When clicked, opens the help drawer showing the topic for the current page.
 * Uses ROUTE_HELP_MAP to find the relevant help topic.
 */

import { HelpCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useLocation } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { HELP_TOPICS as TOPICS } from "@/help/helpTopics";
import { ROUTE_HELP_MAP } from "@/help/types";

interface ContextualHelpButtonProps {
	/** Override the route (defaults to current location) */
	route?: string;
	/** Custom label */
	label?: string;
}

export function ContextualHelpButton({
	route,
	label,
}: ContextualHelpButtonProps) {
	const location = useLocation();
	const { t, i18n } = useTranslation();
	const currentRoute = route || location.pathname;

	// Find the best matching help topic for the current route
	const findHelpTopic = (): string | null => {
		// Try exact match first
		if (ROUTE_HELP_MAP[currentRoute]) {
			return ROUTE_HELP_MAP[currentRoute];
		}
		// Try prefix match (e.g. /elements/123 → /elements)
		const sortedRoutes = Object.keys(ROUTE_HELP_MAP).sort(
			(a, b) => b.length - a.length,
		);
		for (const r of sortedRoutes) {
			if (currentRoute.startsWith(`${r}/`) || currentRoute === r) {
				return ROUTE_HELP_MAP[r];
			}
		}
		return null;
	};

	const topicId = findHelpTopic();
	const topic = topicId ? TOPICS[topicId as keyof typeof TOPICS] : null;

	const handleClick = () => {
		if (!topic) {
			toast.info(
				i18n.language === "ar"
					? "لا يوجد مساعدة متاحة لهذه الصفحة"
					: "No help available for this page",
			);
			return;
		}
		// Show help content in a toast (lightweight, no heavy drawer needed)
		const title = i18n.language === "ar" ? topic.titleAr : topic.titleEn;
		const desc =
			i18n.language === "ar" ? topic.descriptionAr : topic.descriptionEn;
		const steps = i18n.language === "ar" ? topic.stepsAr : topic.stepsEn;

		toast(
			<div className="space-y-2 max-w-md">
				<h3 className="font-bold text-slate-100">{title}</h3>
				<p className="text-sm text-slate-400">{desc}</p>
				{steps.length > 0 && (
					<ol className="text-xs text-slate-500 list-decimal list-inside space-y-1">
						{steps.slice(0, 5).map((step, i) => (
							<li key={i}>{step}</li>
						))}
					</ol>
				)}
			</div>,
			{ duration: 10000, position: "top-right" },
		);

		// Also try to open the SmartHelpDrawer if available
		const helpEvent = new CustomEvent("fireai:open-help", {
			detail: { topicId },
		});
		window.dispatchEvent(helpEvent);
	};

	return (
		<Button
			variant="ghost"
			size="sm"
			onClick={handleClick}
			className="text-slate-400 hover:text-orange-400 hover:bg-slate-800 gap-1"
			title={
				label ||
				(i18n.language === "ar" ? "مساعدة هذه الصفحة" : "Help for this page")
			}
		>
			<HelpCircle className="h-4 w-4" />
			{label || (i18n.language === "ar" ? "مساعدة" : "Help")}
		</Button>
	);
}
