import { Flame, Globe, HelpCircle, Search, Settings } from "lucide-react";
import type React from "react";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { UserMenu } from "@/components/auth/UserMenu";
import { ContextualHelpButton } from "@/components/shared/ContextualHelpButton";

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
        const [langOpen, setLangOpen] = useState(false);
        const langRef = useRef<HTMLDivElement>(null);

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
                <header className="h-12 bg-slate-900 backdrop-blur-sm border-b border-slate-700/50 flex items-center px-4 gap-3 shrink-0">
                        <Flame className="h-5 w-5 text-orange-500 shrink-0 transition-transform duration-300 hover:scale-110" />
                        <span className="text-white font-semibold text-sm tracking-wide hidden sm:inline">
                                BAZSPARK
                        </span>

                        <div className="h-5 w-px bg-slate-700/50 hidden sm:block" />

                        <span className="text-slate-300 text-sm relative pb-1 truncate">
                                {pageName}
                                <span className="absolute bottom-0 left-0 w-full h-0.5 bg-red-500 scale-x-100 transition-transform duration-300 origin-left" />
                        </span>

                        <div className="flex-1" />

                        {/* Connection status indicator */}
                        <div className="flex items-center gap-1.5">
                                <span
                                        className={`h-2.5 w-2.5 rounded-full transition-all duration-300 ${isConnected ? "bg-green-500 shadow-green-500/50 shadow-md animate-pulse" : "bg-red-500 shadow-red-500/50 shadow-md"}`}
                                        title={isConnected ? "Connected" : "Disconnected"}
                                />
                                <span className="text-slate-400 text-xs hidden md:inline">
                                        {isConnected ? "Online" : "Offline"}
                                </span>
                        </div>

                        <div className="h-5 w-px bg-slate-700/50" />

                        {/* Action buttons */}
                        <button
                                onClick={onSearchOpen}
                                className="p-1.5 text-slate-400 hover:text-slate-200 transition-all duration-200 hover:scale-110 rounded"
                                aria-label="Search"
                                title="Search (Ctrl+K)"
                        >
                                <Search className="h-4 w-4" />
                        </button>

                        <ContextualHelpButton />

                        <button
                                onClick={onHelpOpen}
                                className="p-1.5 text-slate-400 hover:text-slate-200 transition-all duration-200 hover:scale-110 rounded"
                                aria-label="Help"
                                data-onboarding="help-button"
                                title="Global help (F1)"
                        >
                                <HelpCircle className="h-4 w-4" />
                        </button>

                        <Link
                                to="/settings"
                                className="p-1.5 text-slate-400 hover:text-slate-200 transition-all duration-200 hover:scale-110 rounded"
                                aria-label="Settings"
                                title="Settings"
                        >
                                <Settings className="h-4 w-4" />
                        </Link>

                        <div className="relative" ref={langRef}>
                                <button
                                        onClick={() => setLangOpen(!langOpen)}
                                        className="flex items-center gap-1 px-1.5 py-1 text-slate-400 hover:text-slate-200 transition-all duration-200 hover:scale-105 text-xs rounded"
                                        aria-label="Change language"
                                >
                                        <Globe className="h-3.5 w-3.5" />
                                        {currentLanguage.toUpperCase()}
                                </button>
                                {langOpen && (
                                        <div className="absolute right-0 top-full mt-1 bg-slate-800 backdrop-blur-sm border border-slate-700/50 rounded shadow-lg z-50 min-w-[120px]">
                                                {["en", "ar"].map((lang) => (
                                                        <button
                                                                key={lang}
                                                                onClick={() => {
                                                                        onLanguageChange(lang);
                                                                        setLangOpen(false);
                                                                }}
                                                                className={`block w-full text-left px-3 py-1.5 text-xs transition-all duration-200 ${
                                                                        currentLanguage === lang
                                                                                ? "text-orange-400 bg-orange-500/10"
                                                                                : "text-slate-300 hover:bg-slate-700/50"
                                                                }`}
                                                        >
                                                                {lang === "en" ? "English" : "العربية"}
                                                        </button>
                                                ))}
                                        </div>
                                )}
                        </div>

                        <div className="h-5 w-px bg-slate-700/50" />

                        <UserMenu />
                </header>
        );
};

export default TopBar;
