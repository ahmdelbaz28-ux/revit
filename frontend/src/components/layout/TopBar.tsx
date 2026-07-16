import { Globe, HelpCircle, Search, Settings, Sun, Moon } from "lucide-react";
import type React from "react";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { UserMenu } from "@/components/auth/UserMenu";
import { ContextualHelpButton } from "@/components/shared/ContextualHelpButton";
import { useTheme } from "@/contexts/ThemeContext";
import { BazSparkLogo } from "@/components/auth/BazSparkLogo";

interface TopBarProps {
        isConnected: boolean;
        onHelpOpen: () => void;
        onSearchOpen?: () => void;
        currentLanguage: string;
        onLanguageChange: (lang: string) => void;
}

const routeLabels: Record<string, string> = {
        "/": "Dashboard",
        "/projects": "Projects",
        "/engineering": "Engineering",
        "/fire-alarm-designer": "Fire Alarm Designer",
        "/fire-alarm/designer": "Fire Alarm Designer",
        "/digital-twin": "Digital Twin",
        "/reports": "Reports",
        "/elements": "Elements",
        "/connections": "Connections",
        "/conflicts": "Conflicts",
        "/settings": "Settings",
        "/autocad": "AutoCAD",
        "/autocad/draw": "ACAD Draw",
        "/revit": "Revit",
        "/revit/create": "Revit Create",
        "/revit/elements": "Revit Elements",
        "/digital-twin/convert": "DT Convert",
        "/digital-twin/config": "DT Config",
        "/digital-twin/history": "DT History",
};

const TopBar: React.FC<TopBarProps> = ({
        isConnected,
        onHelpOpen,
        onSearchOpen,
        currentLanguage,
        onLanguageChange,
}) => {
        const location = useLocation();
        const { dark, toggle } = useTheme();
        const [langOpen, setLangOpen] = useState(false);
        const langRef = useRef<HTMLDivElement>(null);

        // Close language dropdown on outside click
        useEffect(() => {
                const handler = (e: MouseEvent) => {
                        if (langRef.current && !langRef.current.contains(e.target as Node)) {
                                setLangOpen(false);
                        }
                };
                document.addEventListener("mousedown", handler);
                return () => document.removeEventListener("mousedown", handler);
        }, []);

        const pageName = routeLabels[location.pathname] || "BAZSPARK";

        return (
                <header
                        className="h-16 glass flex items-center px-4 lg:px-6 gap-2 lg:gap-4 shrink-0 sticky top-0 z-40"
                        style={{ borderBottom: "1px solid rgba(255,255,255,0.1)" }}
                >
                        {/* Left — logo + page title */}
                        <div className="flex items-center gap-3 min-w-0">
                                <BazSparkLogo size={30} className="shrink-0" />
                                <h1 className="text-foreground font-semibold text-[16px] tracking-tight truncate ml-1">
                                        {pageName}
                                </h1>
                        </div>

                        <div className="flex-1" />

                        {/* Connection status — neutral slate when offline, no red */}
                        <div className="flex items-center gap-2">
                                <span
                                        className={`h-2 w-2 rounded-full ${isConnected ? "bg-success" : "bg-slate-500"}`}
                                        title={isConnected ? "Connected" : "Disconnected"}
                                />
                                <span className="text-muted-foreground text-[13px] hidden md:inline">
                                        {isConnected ? "Online" : "Offline"}
                                </span>
                        </div>

                        <div className="h-5 w-px bg-white/10" />

                        {/* Action buttons */}
                        <button
                                onClick={onSearchOpen}
                                className="p-2 text-muted-foreground hover:text-cyan-300 hover:bg-white/5 transition-all duration-200 rounded-lg"
                                aria-label="Search"
                                title="Search (Ctrl+K)"
                        >
                                <Search className="h-[18px] w-[18px]" />
                        </button>

                        <ContextualHelpButton />

                        <button
                                onClick={onHelpOpen}
                                className="p-2 text-muted-foreground hover:text-cyan-300 hover:bg-white/5 transition-all duration-200 rounded-lg"
                                aria-label="Help"
                                data-onboarding="help-button"
                                title="Global help (F1)"
                        >
                                <HelpCircle className="h-[18px] w-[18px]" />
                        </button>

                        <Link
                                to="/settings"
                                className="p-2 text-muted-foreground hover:text-cyan-300 hover:bg-white/5 transition-all duration-200 rounded-lg"
                                aria-label="Settings"
                                title="Settings"
                        >
                                <Settings className="h-[18px] w-[18px]" />
                        </Link>

			{/* Dark mode toggle */}
			<button
				onClick={toggle}
				aria-label="Toggle dark mode"
				className="p-2 text-muted-foreground hover:text-cyan-300 hover:bg-white/5 transition-all duration-200 rounded-lg"
			>
				{dark ? <Moon className="h-5 w-5" /> : <Sun className="h-5 w-5" />}
			</button>

			{/* Language selector */}
                        <div className="relative" ref={langRef}>
                                <button
                                        onClick={() => setLangOpen(!langOpen)}
                                        className="flex items-center gap-1.5 px-3 py-2 text-muted-foreground hover:text-cyan-300 hover:bg-white/5 transition-all duration-200 text-[13px] rounded-lg border border-white/10 font-medium"
                                        aria-label="Change language"
                                >
                                        <Globe className="h-4 w-4" />
                                        {currentLanguage.toUpperCase()}
                                </button>
                                {langOpen && (
                                        <div className="absolute right-0 top-full mt-2 glass rounded-lg shadow-xl z-50 min-w-[120px] overflow-hidden">
                                                {["en", "ar"].map((lang) => (
                                                        <button
                                                                key={lang}
                                                                onClick={() => {
                                                                        onLanguageChange(lang);
                                                                        setLangOpen(false);
                                                                }}
                                                                className={`block w-full text-left px-3 py-2.5 text-[13px] transition-all duration-200 ${
                                                                        currentLanguage === lang
                                                                                ? "text-cyan-300 bg-cyan-400/10"
                                                                                : "text-foreground hover:bg-white/5"
                                                                }`}
                                                        >
                                                                {lang === "en" ? "English" : "العربية"}
                                                        </button>
                                                ))}
                                        </div>
                                )}
                        </div>

                        <div className="h-5 w-px bg-white/10" />

                        <UserMenu />
                </header>
        );
};

export default TopBar;
