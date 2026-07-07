import type React from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";

export interface TourStep {
	id: string;
	target: string;
	title: string;
	content: string;
	position?: "top" | "bottom" | "left" | "right";
}

const TOUR_STEPS: TourStep[] = [
	{
		id: "sidebar-toggle",
		target: "[data-onboarding='sidebar-toggle']",
		title: "Navigation Sidebar",
		content:
			"Toggle the sidebar to expand or collapse the navigation menu. This gives you more screen space for your work.",
		position: "bottom",
	},
	{
		id: "nav-dashboard",
		target: "[data-onboarding='nav-dashboard']",
		title: "Dashboard",
		content:
			"The dashboard provides an overview of your projects and recent activity. This is your starting point for all projects.",
		position: "right",
	},
	{
		id: "nav-projects",
		target: "[data-onboarding='nav-projects']",
		title: "Projects",
		content:
			"Manage all your fire alarm engineering projects from here. Create, edit, and organize your work.",
		position: "right",
	},
	{
		id: "nav-engineering",
		target: "[data-onboarding='nav-engineering']",
		title: "Engineering",
		content:
			"Access engineering tools and calculations for fire alarm system design and analysis.",
		position: "right",
	},
	{
		id: "nav-fire-alarm-designer",
		target: "[data-onboarding='nav-fire-alarm-designer']",
		title: "Fire Alarm Designer",
		content:
			"Design fire alarm systems visually with our interactive designer tool.",
		position: "right",
	},
	{
		id: "nav-reports",
		target: "[data-onboarding='nav-reports']",
		title: "Reports",
		content:
			"Generate and view reports for your projects including compliance and system analysis reports.",
		position: "right",
	},
	{
		id: "nav-settings",
		target: "[data-onboarding='nav-settings']",
		title: "Settings",
		content:
			"Configure application preferences, integrations, and user settings.",
		position: "right",
	},
	{
		id: "help-button",
		target: "[data-onboarding='help-button']",
		title: "Help & Support",
		content:
			"Access help documentation and support. Press F1 or Ctrl+H for quick access anytime.",
		position: "bottom",
	},
	{
		id: "status-bar",
		target: "[data-onboarding='status-bar']",
		title: "Status Bar",
		content: "View connection status and application information at a glance.",
		position: "top",
	},
];

const STORAGE_KEY = "onboarding-completed";

export const OnboardingTour: React.FC = () => {
	const [currentStep, setCurrentStep] = useState(0);
	const [isVisible, setIsVisible] = useState(false);
	const [targetElement, setTargetElement] = useState<DOMRect | null>(null);
	const [isMounted, setIsMounted] = useState(false);
	const overlayRef = useRef<HTMLDivElement>(null);

	const _location = useLocation();

	useEffect(() => {
		setIsMounted(true);
		// V181 FIX: Do NOT auto-start the onboarding tour after 1 second.
		// The previous behavior (setTimeout 1000ms → setIsVisible(true)) caused
		// a full-screen bg-slate-950/80 overlay to appear over EVERY new visitor's
		// first session, making the entire UI look "dimmed/empty" (the overlay
		// sat at z-[9998] above all content). This was the ROOT CAUSE of the
		// 'pages look dim' issue reported by the operator — not the CSS vars,
		// not the overlays in AppShell (V177), not the card transparency (V178).
		//
		// The tour is still available via the help menu / F1 / Ctrl+H, but it no
		// longer ambushes new users with a dark overlay.
		//
		// To re-enable auto-tour in the future, gate it behind an explicit
		// user opt-in (e.g. a "Take Tour" button in the help drawer) rather
		// than auto-firing on first visit.
	}, []);

	const getTargetPosition = useCallback(() => {
		const selector = TOUR_STEPS[currentStep].target;
		const element = document.querySelector(selector) as HTMLElement;
		if (element) {
			const rect = element.getBoundingClientRect();
			setTargetElement(rect);
		} else {
			setTargetElement(null);
		}
	}, [currentStep]);

	useEffect(() => {
		if (!isVisible) return;
		getTargetPosition();
		const handleResize = () => getTargetPosition();
		globalThis.addEventListener("resize", handleResize);
		return () => globalThis.removeEventListener("resize", handleResize);
	}, [isVisible, getTargetPosition]);

	const completeTour = useCallback(() => {
		localStorage.setItem(STORAGE_KEY, "true");
		setIsVisible(false);
	}, []);

	const skipTour = useCallback(() => {
		completeTour();
	}, [completeTour]);

	const nextStep = useCallback(() => {
		if (currentStep < TOUR_STEPS.length - 1) {
			setCurrentStep(currentStep + 1);
		} else {
			completeTour();
		}
	}, [currentStep, completeTour]);

	const prevStep = useCallback(() => {
		if (currentStep > 0) {
			setCurrentStep(currentStep - 1);
		}
	}, [currentStep]);

	if (!isMounted || !isVisible || !targetElement) return null;

	const step = TOUR_STEPS[currentStep];
	const isFirst = currentStep === 0;
	const isLast = currentStep === TOUR_STEPS.length - 1;

	const tooltipStyle = {
		top:
			step.position === "top"
				? `${targetElement.top - 160}px`
				: step.position === "bottom"
					? `${targetElement.bottom + 16}px`
					: `${targetElement.top + targetElement.height / 2 - 80}px`,
		left:
			step.position === "left"
				? `${targetElement.left - 280}px`
				: step.position === "right"
					? `${targetElement.right + 16}px`
					: `${targetElement.left + targetElement.width / 2 - 140}px`,
	};

	const arrowClasses = cn(
		"absolute w-0 h-0 border-8",
		step.position === "top" &&
			"bottom-full left-1/2 -translate-x-1/2 border-l-transparent border-r-transparent border-b-0 border-t-slate-900",
		step.position === "bottom" &&
			"top-full left-1/2 -translate-x-1/2 border-l-transparent border-r-transparent border-t-0 border-b-slate-900",
		step.position === "left" &&
			"right-full top-1/2 -translate-y-1/2 border-t-transparent border-b-transparent border-r-0 border-l-slate-900",
		step.position === "right" &&
			"left-full top-1/2 -translate-y-1/2 border-t-transparent border-b-transparent border-l-0 border-r-slate-900",
	);

	return (
		<>
			<div
				ref={overlayRef}
				className="fixed inset-0 z-[9998] bg-slate-950/80"
				aria-hidden="true"
			/>

			<div
				className="fixed z-[9998] pointer-events-none"
				aria-hidden="true"
				style={{
					top: `${targetElement.top}px`,
					left: `${targetElement.left}px`,
					width: `${targetElement.width}px`,
					height: `${targetElement.height}px`,
					boxShadow: `0 0 0 9999px rgba(17, 24, 39, 0.8)`,
				}}
			/>

			<div
				className="fixed z-[9999] w-72 bg-slate-900 border border-slate-700 rounded-lg shadow-2xl"
				style={tooltipStyle}
			>
				<div className="p-4">
					<div className="flex items-start justify-between mb-2">
						<h3 className="text-orange-400 font-semibold text-sm">
							{step.title}
						</h3>
						<button
							onClick={skipTour}
							className="text-slate-500 hover:text-slate-300 text-xs"
						>
							Skip
						</button>
					</div>

					<p className="text-slate-300 text-sm mb-4">{step.content}</p>

					<div className="flex items-center justify-between">
						<span className="text-slate-500 text-xs">
							Step {currentStep + 1} of {TOUR_STEPS.length}
						</span>

						<div className="flex gap-2">
							{!isFirst && (
								<button
									onClick={prevStep}
									className="px-3 py-1 text-slate-400 hover:text-slate-200 text-xs border border-slate-700 rounded"
								>
									← Previous
								</button>
							)}
							<button
								onClick={nextStep}
								className="px-3 py-1 bg-orange-600 hover:bg-orange-500 text-white text-xs rounded"
							>
								{isLast ? "Done" : "Next"} →
							</button>
						</div>
					</div>
				</div>

				<div className={arrowClasses} />
			</div>
		</>
	);
};

export const useOnboarding = () => {
	const [hasCompleted, setHasCompleted] = useState(false);

	useEffect(() => {
		const completed = localStorage.getItem(STORAGE_KEY);
		setHasCompleted(!!completed);
	}, []);

	const resetOnboarding = useCallback(() => {
		localStorage.removeItem(STORAGE_KEY);
		setHasCompleted(false);
	}, []);

	return { hasCompleted, resetOnboarding };
};

export default OnboardingTour;
