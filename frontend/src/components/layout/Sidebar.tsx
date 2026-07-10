// NOSONAR
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
        CloudSun,
        Brain,
        Network,
        Workflow as WorkflowIcon,
        Settings2,
        ShieldCheck,
} from "lucide-react";
import type React from "react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation } from "react-router-dom";

interface NavItem {
        labelKey: string;
        defaultLabel: string;
        icon: React.ElementType;
        path: string;
        dataOnboarding?: string;
}

// V140 FIX + Phase 6: Use i18n keys + correct paths + new CAD/BIM routes
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
                labelKey: "nav.fireAlarmDesigner",
                defaultLabel: "Fire Alarm Designer",
                icon: Siren,
                path: "/fire-alarm/designer",
                dataOnboarding: "nav-fire-alarm-designer",
        },
        // V140 Phase 6: New AutoCAD / Revit / Digital Twin routes
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
];

interface SidebarProps {
        compact?: boolean;
}

const Sidebar: React.FC<SidebarProps> = ({ compact = false }) => {
        const [collapsed, setCollapsed] = useState(false);
        const [hoveredItem, setHoveredItem] = useState<string | null>(null);
        const location = useLocation();
        const { t } = useTranslation();
        const isRTL = document.documentElement.dir === "rtl";

        const width = collapsed
                ? compact  // NOSONAR — S3358: nested ternary acceptable in this localized context
                        ? "w-12"
                        : "w-16"
                : compact  // NOSONAR — S3358: nested ternary acceptable in this localized context
                        ? "w-48"
                        : "w-56";

        return (
                <aside
                        className={`${width} h-full bg-card backdrop-blur-sm border-${
                                isRTL ? "l" : "r"
                        } border-border/50 flex flex-col transition-all duration-300 ${
                                isRTL ? "order-last" : "order-first"
                        }`}
                >
                        <div className="flex items-center gap-2 px-3 py-2.5 border-b border-border shrink-0">
                                <div className="h-8 w-8 rounded-md bg-primary flex items-center justify-center shrink-0">
                                        <ShieldCheck className="h-4 w-4 text-primary-foreground" />
                                </div>
                                {!collapsed && (
                                        <div className="flex flex-col leading-tight">
                                                <span className="text-foreground font-semibold text-sm tracking-tight">
                                                        BAZSPARK
                                                </span>
                                                <span className="text-[10px] text-muted-foreground uppercase tracking-wider">
                                                        FireAI Digital Twin
                                                </span>
                                        </div>
                                )}
                        </div>

                        <nav
                                className="flex-1 py-2 overflow-y-auto overflow-x-hidden"
                                aria-label="Primary navigation"
                        >
                                {navItems.map((item) => {
                                        // V140 FIX: Match both exact path and sub-paths (e.g. /elements/123 matches /elements)
                                        const isActive =
                                                location.pathname === item.path ||
                                                (item.path !== "/dashboard" &&
                                                        location.pathname.startsWith(`${item.path}/`));
                                        const isHovered = hoveredItem === item.path;
                                        const labelText = t(item.labelKey, item.defaultLabel);
                                        return (
                                                <div key={item.path} className="relative">
                                                        <Link
                                                                to={item.path}
                                                                className={`flex items-center gap-3 px-3 py-2 mx-1 rounded-md transition-all duration-200 ${
                                                                        isActive
                                                                                ? "bg-card border-l-2 border-primary text-primary shadow-lg shadow-orange-500/20"
                                                                                : "text-muted-foreground hover:bg-card/60 hover:text-foreground"
                                                                } ${compact && !collapsed ? "py-1.5 text-sm" : ""}`}
                                                                onMouseEnter={() => setHoveredItem(item.path)}
                                                                onMouseLeave={() => setHoveredItem(null)}
                                                                title={collapsed ? labelText : undefined}
                                                                data-onboarding={item.dataOnboarding}
                                                        >
                                                                <item.icon
                                                                        className={`shrink-0 transition-transform duration-300 ${
                                                                                isActive
                                                                                        ? "text-primary scale-110"
                                                                                        : isHovered  // NOSONAR — S3358: nested ternary acceptable in this localized context
                                                                                                ? "scale-105 text-orange-300"
                                                                                                : "text-muted-foreground"
                                                                        } ${compact && !collapsed ? "h-4 w-4" : "h-5 w-5"}`}
                                                                />
                                                                {!collapsed && (
                                                                        <span
                                                                                className={`truncate transition-all duration-200 ${compact && !collapsed ? "text-xs" : "text-sm"}`}
                                                                        >
                                                                                {labelText}
                                                                        </span>
                                                                )}
                                                        </Link>
                                                        {collapsed && isHovered && (
                                                                <div
                                                                        className={`absolute top-1/2 -translate-y-1/2 px-2 py-1 bg-card backdrop-blur-sm text-foreground text-xs rounded shadow-lg z-50 whitespace-nowrap ${isRTL ? "right-full mr-2" : "left-full ml-2"}`}
                                                                >
                                                                        {labelText}
                                                                </div>
                                                        )}
                                                </div>
                                        );
                                })}
                        </nav>

                        <button
                                onClick={() => setCollapsed(!collapsed)}
                                className="flex items-center justify-center py-2 border-t border-border/50 text-muted-foreground hover:text-foreground/90 transition-all duration-200 hover:bg-card/40 shrink-0"
                                aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                                data-onboarding="sidebar-toggle"
                        >
                                {collapsed ? (
                                        isRTL ? (  // NOSONAR — S3358: nested ternary acceptable in this localized context
                                                <ChevronLeft className="h-4 w-4 transition-transform duration-200" />
                                        ) : (
                                                <ChevronRight className="h-4 w-4 transition-transform duration-200" />
                                        )
                                ) : isRTL ? (  // NOSONAR — S3358: nested ternary acceptable in this localized context
                                        <ChevronRight className="h-4 w-4 transition-transform duration-200" />
                                ) : (
                                        <ChevronLeft className="h-4 w-4 transition-transform duration-200" />
                                )}
                        </button>
                </aside>
        );
};

export default Sidebar;
