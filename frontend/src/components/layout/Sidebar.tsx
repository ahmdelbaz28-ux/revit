import {
        AlertTriangle,
        ArrowRightLeft,
        Activity,
        Box,
        Ship,
        Building2,
        Cable,
        Calculator,
        Cpu,
        ChevronLeft,
        ChevronRight,
        FileText,
        Siren,
        FolderKanban,
        History,
        Layers,
        LayoutDashboard,
        PencilRuler,
        Settings,
        Shield,
        CloudSun,
        Brain,
        Network,
        Workflow as WorkflowIcon,
        Settings2,
        Info,
        Pickaxe,
        Key,
        Download,
} from "lucide-react";
import type React from "react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation } from "react-router-dom";
import { BazSparkLogo } from "@/components/auth/BazSparkLogo";

interface NavItem {
        labelKey: string;
        defaultLabel: string;
        icon: React.ElementType;
        path: string;
        dataOnboarding?: string;
}

const navItems: NavItem[] = [
        {
                labelKey: "nav.dashboard",
                defaultLabel: "Dashboard",
                icon: LayoutDashboard,
                path: "/dashboard",
                dataOnboarding: "nav-dashboard",
        },
        {
                labelKey: "nav.projects",
                defaultLabel: "Projects",
                icon: FolderKanban,
                path: "/projects",
                dataOnboarding: "nav-projects",
        },
        {
                labelKey: "nav.engineering",
                defaultLabel: "Engineering",
                icon: Calculator,
                path: "/engineering",
                dataOnboarding: "nav-engineering",
        },
        {
                labelKey: "nav.facp",
                defaultLabel: "FACP Selector",
                icon: Cpu,
                path: "/facp",
        },
        {
                labelKey: "nav.marine",
                defaultLabel: "Marine",
                icon: Ship,
                path: "/marine",
        },
        {
                labelKey: "nav.mining",
                defaultLabel: "Mining",
                icon: Pickaxe,
                path: "/mining",
                dataOnboarding: "nav-mining",
        },
        {
                labelKey: "nav.fireAlarmDesigner",
                defaultLabel: "Fire Alarm Designer",
                icon: Siren,
                path: "/fire-alarm/designer",
                dataOnboarding: "nav-fire-alarm-designer",
        },
        {
                labelKey: "nav.autocad",
                defaultLabel: "AutoCAD",
                icon: PencilRuler,
                path: "/autocad",
        },
        {
                labelKey: "nav.autocadDraw",
                defaultLabel: "ACAD Draw",
                icon: PencilRuler,
                path: "/autocad/draw",
        },
        {
                labelKey: "nav.revit",
                defaultLabel: "Revit",
                icon: Building2,
                path: "/revit",
        },
        {
                labelKey: "nav.revitCreate",
                defaultLabel: "Revit Create",
                icon: Building2,
                path: "/revit/create",
        },
        {
                labelKey: "nav.revitElements",
                defaultLabel: "Revit Elements",
                icon: Layers,
                path: "/revit/elements",
        },
        {
                labelKey: "nav.digitalTwin",
                defaultLabel: "Digital Twin",
                icon: Box,
                path: "/digital-twin",
        },
        {
                labelKey: "nav.dtConvert",
                defaultLabel: "DT Convert",
                icon: ArrowRightLeft,
                path: "/digital-twin/convert",
        },
        {
                labelKey: "nav.dtConfig",
                defaultLabel: "DT Config",
                icon: Settings2,
                path: "/digital-twin/config",
        },
        {
                labelKey: "nav.dtHistory",
                defaultLabel: "DT History",
                icon: History,
                path: "/digital-twin/history",
        },
        {
                labelKey: "nav.reports",
                defaultLabel: "Reports",
                icon: FileText,
                path: "/reports",
                dataOnboarding: "nav-reports",
        },
        {
                labelKey: "nav.exports",
                defaultLabel: "Exports",
                icon: Download,
                path: "/exports",
                dataOnboarding: "nav-exports",
        },
        {
                labelKey: "nav.environment",
                defaultLabel: "Environment",
                icon: CloudSun,
                path: "/environment",
        },
        {
                labelKey: "nav.monitor",
                defaultLabel: "Monitor",
                icon: Activity,
                path: "/monitor",
        },
        {
                labelKey: "nav.selfHealing",
                defaultLabel: "Self-Healing",
                icon: Shield,
                path: "/self-healing",
        },
        {
                labelKey: "nav.memory",
                defaultLabel: "Memory",
                icon: Brain,
                path: "/memory",
        },
        {
                labelKey: "nav.graphrag",
                defaultLabel: "GraphRAG",
                icon: Network,
                path: "/graphrag",
        },
        {
                labelKey: "nav.workflow",
                defaultLabel: "Workflows",
                icon: WorkflowIcon,
                path: "/workflow",
        },
        {
                labelKey: "nav.elements",
                defaultLabel: "Elements",
                icon: Layers,
                path: "/elements",
        },
        {
                labelKey: "nav.connections",
                defaultLabel: "Connections",
                icon: Cable,
                path: "/connections",
        },
        {
                labelKey: "nav.conflicts",
                defaultLabel: "Conflicts",
                icon: AlertTriangle,
                path: "/conflicts",
        },
        {
                labelKey: "nav.settings",
                defaultLabel: "Settings",
                icon: Settings,
                path: "/settings",
                dataOnboarding: "nav-settings",
        },
        {
                labelKey: "nav.apiKeys",
                defaultLabel: "API Keys",
                icon: Key,
                path: "/api-keys",
                dataOnboarding: "nav-api-keys",
        },
];

interface SidebarProps {
        compact?: boolean;
}

const Sidebar: React.FC<SidebarProps> = () => {
        const [collapsed, setCollapsed] = useState(false);
        const location = useLocation();
        const { t } = useTranslation();
        const isRTL = document.documentElement.dir === "rtl";

        const width = collapsed ? "w-16" : "w-60";

        return (
                <aside
                        className={`${width} h-full glass flex flex-col transition-all duration-300 ${isRTL ? "order-last" : "order-first"}`}
                        style={{
                                borderRight: isRTL ? "none" : "1px solid rgba(255,255,255,0.1)",
                                borderLeft: isRTL ? "1px solid rgba(255,255,255,0.1)" : "none",
                        }}
                >
                        {/* Brand header — BAZSPARK with official flame logo */}
                        <div className="flex items-center gap-3 px-5 h-16 shrink-0 border-b border-white/10">
                                <BazSparkLogo size={32} className="shrink-0" />
                                {!collapsed && (
                                         <div className="flex flex-col leading-relaxed">
                                                 <span className="text-foreground font-semibold text-[15px] tracking-tight">
                                                         BAZSPARK
                                                 </span>
                                                 <span className="text-[11px] text-muted-foreground uppercase tracking-wider mt-0.5">
                                                         FireAI Digital Twin
                                                 </span>
                                         </div>
                                )}
                        </div>

                        <nav
                                className="flex-1 py-3 overflow-y-auto overflow-x-hidden"
                                aria-label="Primary navigation"
                        >
                                {navItems.map((item) => {
                                        const isActive =
                                                location.pathname === item.path ||
                                                (item.path !== "/dashboard" &&
                                                        location.pathname.startsWith(`${item.path}/`));
                                        const labelText = t(item.labelKey, item.defaultLabel);
                                        return (
                                                <div key={item.path} className="relative px-3 mb-1">
                                                        <Link
                                                                to={item.path}
                                                                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 ${
                                                                        isActive
                                                                                ? "bg-cyan-400/10 text-cyan-300 border border-cyan-400/20"
                                                                                : "text-muted-foreground hover:bg-white/5 hover:text-foreground border border-transparent"
                                                                }`}
                                                                title={collapsed ? labelText : undefined}
                                                                data-onboarding={item.dataOnboarding}
                                                        >
                                                                <item.icon
                                                                        className={`shrink-0 h-[18px] w-[18px] ${isActive ? "text-cyan-300" : ""}`}  // NOSONAR: typescript:S3358
                                                                />
                                                                {!collapsed && (
                                                                        <span className="truncate text-[13px] font-medium tracking-wide">
                                                                                {labelText}
                                                                        </span>
                                                                )}
                                                        </Link>
                                                </div>
                                        );
                                })}
                        </nav>

                        {/* Footer — About + collapse */}
                        <div className="border-t border-white/10 shrink-0 p-3">
                                {!collapsed && (
                                        <Link
                                                to="/settings"
                                                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-muted-foreground hover:bg-white/5 hover:text-foreground transition-all duration-200"
                                        >
                                                <Info className="h-[18px] w-[18px] shrink-0" />
                                                <span className="text-[13px] font-medium">About BAZSPARK</span>
                                        </Link>
                                )}
                                <button
                                        onClick={() => setCollapsed(!collapsed)}
                                        className="flex items-center justify-center w-full py-2.5 rounded-lg text-muted-foreground hover:text-cyan-400 hover:bg-white/5 transition-all duration-200 mt-1"
                                        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                                        data-onboarding="sidebar-toggle"
                                >
                                        {collapsed ? (
                                                isRTL ? (
                                                        <ChevronLeft className="h-4 w-4" />
                                                ) : (
                                                        <ChevronRight className="h-4 w-4" />
                                                )
                                        ) : isRTL ? (
                                                <ChevronRight className="h-4 w-4" />
                                        ) : (
                                                <ChevronLeft className="h-4 w-4" />
                                        )}
                                </button>
                        </div>
                </aside>
        );
};

export default Sidebar;
