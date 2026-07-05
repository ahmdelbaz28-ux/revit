/**
 * types.ts — Help system types
 *
 * V140 Phase 7: Extended help system with contextual help per page,
 * global help tree, magic help (F1), and comprehensive user guide.
 */

export type HelpCategory =
	| "dashboard"
	| "projects"
	| "engineering"
	| "fire-alarm"
	| "autocad"
	| "revit"
	| "digital-twin"
	| "reports"
	| "elements"
	| "connections"
	| "conflicts"
	| "settings"
	| "troubleshooting"
	| "general"
	| "getting-started";

export type HelpTopicId =
	// Dashboard
	| "dashboard.overview"
	// Projects
	| "projects.create"
	| "projects.manage"
	// Engineering
	| "engineering.overview"
	| "engineering.voltage-drop"
	| "engineering.cable-sizing"
	| "engineering.battery"
	// Fire Alarm
	| "fire-alarm.detector-placement"
	| "fire-alarm.symbol-library"
	| "fire-alarm.zone-navigation"
	// AutoCAD
	| "autocad.connect"
	| "autocad.draw"
	| "autocad.files"
	// Revit
	| "revit.connect"
	| "revit.create"
	| "revit.elements"
	| "revit.files"
	// Digital Twin
	| "digital-twin.overview"
	| "digital-twin.convert"
	| "digital-twin.config"
	| "digital-twin.history"
	// Reports
	| "reports.generate"
	// Elements
	| "elements.overview"
	// Connections
	| "connections.create"
	// Conflicts
	| "conflicts.overview"
	// Settings
	| "settings.backend"
	| "settings.api-keys"
	// Getting Started
	| "getting-started.quickstart"
	| "getting-started.api-setup"
	// Troubleshooting
	| "troubleshooting.backend"
	| "troubleshooting.api"
	| "troubleshooting.auth"
	| "troubleshooting.app-crash";

export type HelpLanguage = "en" | "ar";
export type HelpTextDirection = "ltr" | "rtl";

export interface HelpTopic {
	id: HelpTopicId;
	category: HelpCategory;
	titleEn: string;
	titleAr: string;
	descriptionEn: string;
	descriptionAr: string;
	stepsEn: string[];
	stepsAr: string[];
	warningsEn: string[];
	warningsAr: string[];
	keywords: string[];
	relatedTopics: HelpTopicId[];
	navigateTo?: string;
	/** Route path that this topic is contextual for (for magic help) */
	contextRoute?: string;
}

export interface HelpTreeNode {
	category: HelpCategory;
	labelEn: string;
	labelAr: string;
	icon?: string;
	topics: HelpTopicId[];
	children?: HelpTreeNode[];
}

export interface HelpContext {
	route: string;
	topicId: HelpTopicId;
	labelEn: string;
	labelAr: string;
}

/** Map of route → help topic for contextual/magic help */
export const ROUTE_HELP_MAP: Record<string, HelpTopicId> = {
	"/dashboard": "dashboard.overview",
	"/projects": "projects.create",
	"/engineering": "engineering.overview",
	"/fire-alarm": "fire-alarm.detector-placement",
	"/fire-alarm/designer": "fire-alarm.detector-placement",
	"/autocad": "autocad.connect",
	"/autocad/draw": "autocad.draw",
	"/revit": "revit.connect",
	"/revit/create": "revit.create",
	"/revit/elements": "revit.elements",
	"/digital-twin": "digital-twin.overview",
	"/digital-twin/convert": "digital-twin.convert",
	"/digital-twin/config": "digital-twin.config",
	"/digital-twin/history": "digital-twin.history",
	"/reports": "reports.generate",
	"/elements": "elements.overview",
	"/connections": "connections.create",
	"/conflicts": "conflicts.overview",
	"/settings": "settings.backend",
};

/** Help tree structure for the global help drawer */
export const HELP_TREE: HelpTreeNode[] = [
	{
		category: "getting-started",
		labelEn: "Getting Started",
		labelAr: "البدء السريع",
		icon: "🚀",
		topics: ["getting-started.quickstart", "getting-started.api-setup"],
	},
	{
		category: "dashboard",
		labelEn: "Dashboard",
		labelAr: "لوحة التحكم",
		icon: "📊",
		topics: ["dashboard.overview"],
	},
	{
		category: "projects",
		labelEn: "Projects",
		labelAr: "المشاريع",
		icon: "📁",
		topics: ["projects.create", "projects.manage"],
	},
	{
		category: "engineering",
		labelEn: "Engineering",
		labelAr: "الهندسة",
		icon: "🧮",
		topics: [
			"engineering.overview",
			"engineering.voltage-drop",
			"engineering.cable-sizing",
			"engineering.battery",
		],
	},
	{
		category: "fire-alarm",
		labelEn: "Fire Alarm",
		labelAr: "إنذار الحريق",
		icon: "🔥",
		topics: [
			"fire-alarm.detector-placement",
			"fire-alarm.symbol-library",
			"fire-alarm.zone-navigation",
		],
	},
	{
		category: "autocad",
		labelEn: "AutoCAD",
		labelAr: "أوتوكاد",
		icon: "📐",
		topics: ["autocad.connect", "autocad.draw", "autocad.files"],
	},
	{
		category: "revit",
		labelEn: "Revit",
		labelAr: "ريفيت",
		icon: "🏗️",
		topics: ["revit.connect", "revit.create", "revit.elements", "revit.files"],
	},
	{
		category: "digital-twin",
		labelEn: "Digital Twin",
		labelAr: "التوأم الرقمي",
		icon: "🔄",
		topics: [
			"digital-twin.overview",
			"digital-twin.convert",
			"digital-twin.config",
			"digital-twin.history",
		],
	},
	{
		category: "reports",
		labelEn: "Reports",
		labelAr: "التقارير",
		icon: "📄",
		topics: ["reports.generate"],
	},
	{
		category: "elements",
		labelEn: "Elements",
		labelAr: "العناصر",
		icon: "🧱",
		topics: ["elements.overview"],
	},
	{
		category: "connections",
		labelEn: "Connections",
		labelAr: "التوصيلات",
		icon: "🔗",
		topics: ["connections.create"],
	},
	{
		category: "conflicts",
		labelEn: "Conflicts",
		labelAr: "التعارضات",
		icon: "⚠️",
		topics: ["conflicts.overview"],
	},
	{
		category: "settings",
		labelEn: "Settings",
		labelAr: "الإعدادات",
		icon: "⚙️",
		topics: ["settings.backend", "settings.api-keys"],
	},
	{
		category: "troubleshooting",
		labelEn: "Troubleshooting",
		labelAr: "استكشاف الأخطاء",
		icon: "🔧",
		topics: [
			"troubleshooting.backend",
			"troubleshooting.api",
			"troubleshooting.auth",
			"troubleshooting.app-crash",
		],
	},
];

// ─── Legacy types for backward compatibility ───────────────────────────────

export interface HelpSearchResult {
	topic: HelpTopic;
	score: number;
	matchedKeywords: string[];
}

export interface SmartHelpContextValue {
	open: boolean;
	setOpen: (open: boolean) => void;
	searchQuery: string;
	setSearchQuery: (q: string) => void;
	selectedTopicId: HelpTopicId | null;
	setSelectedTopicId: (id: HelpTopicId | null) => void;
	topics: HelpTopic[];
	categories: HelpCategory[];
	searchResults: HelpSearchResult[];
	navigateToTopic: (id: HelpTopicId) => void;
}

export interface SmartHelpHookValue {
	isOpen: boolean;
	open: () => void;
	close: () => void;
	toggle: () => void;
	searchQuery: string;
	setSearchQuery: (q: string) => void;
	results: HelpSearchResult[];
	selectedTopic: HelpTopic | undefined;
	selectTopic: (id: HelpTopicId) => void;
	categories: HelpCategory[];
	getCategoryLabel: (cat: HelpCategory) => { en: string; ar: string };
	// Legacy fields for backward compatibility
	openHelp?: () => void;
	openSearch?: () => void;
	closeHelp?: () => void;
	isHelpOpen?: boolean;
	category?: HelpCategory | "all";
	setCategory?: (cat: HelpCategory | "all") => void;
	topics?: HelpTopic[];
}
