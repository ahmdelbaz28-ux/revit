import React, { useState } from "react";
import { useLocation, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  LayoutDashboard,
  FolderKanban,
  Flame,
  Box,
  FileText,
  Layers,
  Cable,
  AlertTriangle,
  Settings,
  ChevronLeft,
  ChevronRight,
  PencilRuler,
  Building2,
  ArrowRightLeft,
  History,
  Settings2,
  ChevronDown,
  Gauge,
  Zap,
  Database,
  BarChart3,
} from "lucide-react";

interface NavItem {
  labelKey: string;
  defaultLabel: string;
  icon: React.ElementType;
  path: string;
  dataOnboarding?: string;
}

interface NavGroup {
  groupKey: string;
  groupLabelKey: string;
  defaultGroupLabel: string;
  groupIcon?: React.ElementType;
  items: NavItem[];
}

// Reorganized navigation with semantic grouping
const navGroups: NavGroup[] = [
  {
    groupKey: "core",
    groupLabelKey: "nav.group.core",
    defaultGroupLabel: "Core",
    groupIcon: LayoutDashboard,
    items: [
      { labelKey: "nav.dashboard", defaultLabel: "Dashboard", icon: LayoutDashboard, path: "/dashboard", dataOnboarding: "nav-dashboard" },
      { labelKey: "nav.projects", defaultLabel: "Projects", icon: FolderKanban, path: "/projects", dataOnboarding: "nav-projects" },
      { labelKey: "nav.elements", defaultLabel: "Elements", icon: Layers, path: "/elements" },
      { labelKey: "nav.connections", defaultLabel: "Connections", icon: Cable, path: "/connections" },
      { labelKey: "nav.conflicts", defaultLabel: "Conflicts", icon: AlertTriangle, path: "/conflicts" },
    ],
  },
  {
    groupKey: "engineering",
    groupLabelKey: "nav.group.engineering",
    defaultGroupLabel: "Engineering (Safety Critical)",
    groupIcon: Gauge,
    items: [
      { labelKey: "nav.engineering", defaultLabel: "Engineering", icon: Gauge, path: "/engineering", dataOnboarding: "nav-engineering" },
      { labelKey: "nav.qomn", defaultLabel: "QOMN Calculator", icon: Zap, path: "/engineering/qomn" },
      { labelKey: "nav.facp", defaultLabel: "FACP Designer", icon: Flame, path: "/engineering/facp" },
      { labelKey: "nav.physicsGuards", defaultLabel: "Physics Guards", icon: AlertTriangle, path: "/engineering/guards" },
    ],
  },
  {
    groupKey: "cad-integration",
    groupLabelKey: "nav.group.cad",
    defaultGroupLabel: "BIM & CAD Integration",
    groupIcon: Building2,
    items: [
      { labelKey: "nav.revit", defaultLabel: "Revit", icon: Building2, path: "/revit" },
      { labelKey: "nav.revitCreate", defaultLabel: "Revit Create", icon: Building2, path: "/revit/create" },
      { labelKey: "nav.revitElements", defaultLabel: "Revit Elements", icon: Layers, path: "/revit/elements" },
      { labelKey: "nav.autocad", defaultLabel: "AutoCAD", icon: PencilRuler, path: "/autocad" },
      { labelKey: "nav.autocadDraw", defaultLabel: "AutoCAD Draw", icon: PencilRuler, path: "/autocad/draw" },
      { labelKey: "nav.digitalTwin", defaultLabel: "Digital Twin", icon: Box, path: "/digital-twin" },
      { labelKey: "nav.dtConvert", defaultLabel: "DT Convert", icon: ArrowRightLeft, path: "/digital-twin/convert" },
      { labelKey: "nav.dtConfig", defaultLabel: "DT Config", icon: Settings2, path: "/digital-twin/config" },
      { labelKey: "nav.dtHistory", defaultLabel: "DT History", icon: History, path: "/digital-twin/history" },
      { labelKey: "nav.fireAlarmDesigner", defaultLabel: "Fire Alarm Designer", icon: Flame, path: "/fire-alarm/designer", dataOnboarding: "nav-fire-alarm-designer" },
    ],
  },
  {
    groupKey: "environment",
    groupLabelKey: "nav.group.environment",
    defaultGroupLabel: "Environment & Context",
    groupIcon: Database,
    items: [
      { labelKey: "nav.environmentContext", defaultLabel: "Weather & Geocoding", icon: Database, path: "/environment/context" },
      { labelKey: "nav.airQuality", defaultLabel: "Air Quality", icon: Database, path: "/environment/air-quality" },
      { labelKey: "nav.hazmat", defaultLabel: "HazMat Database", icon: AlertTriangle, path: "/environment/hazmat" },
    ],
  },
  {
    groupKey: "reporting",
    groupLabelKey: "nav.group.reporting",
    defaultGroupLabel: "Reports & Exports",
    groupIcon: FileText,
    items: [
      { labelKey: "nav.reports", defaultLabel: "Reports", icon: FileText, path: "/reports", dataOnboarding: "nav-reports" },
      { labelKey: "nav.exports", defaultLabel: "Export Manager", icon: ArrowRightLeft, path: "/exports" },
      { labelKey: "nav.auditTrail", defaultLabel: "Audit Trail", icon: History, path: "/audit-trail" },
    ],
  },
  {
    groupKey: "monitoring",
    groupLabelKey: "nav.group.monitoring",
    defaultGroupLabel: "System & Monitoring",
    groupIcon: BarChart3,
    items: [
      { labelKey: "nav.systemHealth", defaultLabel: "System Health", icon: BarChart3, path: "/system-health" },
      { labelKey: "nav.agentActivity", defaultLabel: "Agent Activity", icon: Database, path: "/agent-activity" },
      { labelKey: "nav.securityAlerts", defaultLabel: "Security Alerts", icon: AlertTriangle, path: "/security-alerts" },
    ],
  },
  {
    groupKey: "settings",
    groupLabelKey: "nav.group.settings",
    defaultGroupLabel: "Settings",
    groupIcon: Settings,
    items: [
      { labelKey: "nav.settings", defaultLabel: "Settings", icon: Settings, path: "/settings", dataOnboarding: "nav-settings" },
      { labelKey: "nav.advancedSettings", defaultLabel: "Advanced Settings", icon: Settings2, path: "/settings/advanced" },
    ],
  },
];

interface EnhancedSidebarProps {
  compact?: boolean;
}

const EnhancedSidebar: React.FC<EnhancedSidebarProps> = ({ compact = false }) => {
  const [collapsed, setCollapsed] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>(
    navGroups.reduce((acc, g) => ({ ...acc, [g.groupKey]: true }), {})
  );
  const [hoveredItem, setHoveredItem] = useState<string | null>(null);
  const location = useLocation();
  const { t } = useTranslation();
  const isRTL = document.documentElement.dir === "rtl";

  const toggleGroup = (groupKey: string) => {
    setExpandedGroups((prev) => ({ ...prev, [groupKey]: !prev[groupKey] }));
  };

  const width = collapsed
    ? compact
      ? "w-12"
      : "w-16"
    : compact
      ? "w-56"
      : "w-64";

  return (
    <aside
      className={`${width} h-full bg-slate-900 backdrop-blur-sm border-${
        isRTL ? "l" : "r"
      } border-slate-700/50 flex flex-col transition-all duration-300 ${
        isRTL ? "order-last" : "order-first"
      }`}
    >
      {/* Logo */}
      <div className="flex items-center gap-2 px-3 py-3 border-b border-slate-700/50">
        <Flame className="h-6 w-6 text-orange-500 shrink-0 transition-transform duration-300 group-hover:scale-110" />
        {!collapsed && (
          <span className="text-white font-bold text-lg tracking-wide">
            BAZSPARK
          </span>
        )}
      </div>

      {/* Navigation Groups */}
      <nav className="flex-1 py-2 overflow-y-auto">
        {navGroups.map((group) => {
          const isExpanded = expandedGroups[group.groupKey];
          const GroupIcon = group.groupIcon || Layers;

          // Check if any item in group is active
          const isGroupActive = group.items.some(
            (item) =>
              location.pathname === item.path ||
              (item.path !== "/dashboard" && location.pathname.startsWith(item.path + "/"))
          );

          return (
            <div key={group.groupKey} className="mb-1">
              {/* Group Header */}
              {!collapsed && (
                <button
                  onClick={() => toggleGroup(group.groupKey)}
                  className={`w-full flex items-center gap-2 px-3 py-2 mx-1 rounded-lg transition-all duration-200 ${
                    isGroupActive
                      ? "bg-slate-800/80 text-slate-100 border-l-2 border-orange-500"
                      : "text-slate-400 hover:bg-slate-800/40 hover:text-slate-200"
                  }`}
                >
                  <GroupIcon className="h-4 w-4 shrink-0" />
                  <span className="flex-1 text-left text-xs font-semibold uppercase tracking-wider truncate">
                    {t(group.groupLabelKey, group.defaultGroupLabel)}
                  </span>
                  <ChevronDown
                    className={`h-3 w-3 shrink-0 transition-transform duration-200 ${
                      isExpanded ? "" : isRTL ? "rotate-90" : "-rotate-90"
                    }`}
                  />
                </button>
              )}

              {/* Group Items */}
              {!collapsed && isExpanded && (
                <div className="py-1">
                  {group.items.map((item) => {
                    const isActive =
                      location.pathname === item.path ||
                      (item.path !== "/dashboard" && location.pathname.startsWith(item.path + "/"));
                    const isHovered = hoveredItem === item.path;
                    const labelText = t(item.labelKey, item.defaultLabel);

                    return (
                      <Link
                        key={item.path}
                        to={item.path}
                        className={`flex items-center gap-3 px-4 py-2 mx-1 rounded-lg transition-all duration-200 text-sm ${
                          isActive
                            ? "bg-orange-500/20 border-l-2 border-orange-500 text-orange-400 shadow-lg shadow-orange-500/10"
                            : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
                        }`}
                        onMouseEnter={() => setHoveredItem(item.path)}
                        onMouseLeave={() => setHoveredItem(null)}
                        title={isActive ? "" : labelText}
                        data-onboarding={item.dataOnboarding}
                      >
                        <item.icon
                          className={`h-4 w-4 shrink-0 transition-transform duration-300 ${
                            isActive ? "text-orange-400 scale-110" : isHovered ? "scale-105 text-orange-300" : ""
                          }`}
                        />
                        <span className="truncate flex-1">{labelText}</span>
                      </Link>
                    );
                  })}
                </div>
              )}

              {/* Collapsed Group Icon */}
              {collapsed && (
                <div className="flex justify-center py-2">
                  <button
                    onClick={() => toggleGroup(group.groupKey)}
                    className={`p-2 rounded-lg transition-all duration-200 ${
                      isGroupActive
                        ? "bg-slate-800 text-orange-400"
                        : "text-slate-500 hover:bg-slate-800/60 hover:text-slate-300"
                    }`}
                    title={t(group.groupLabelKey, group.defaultGroupLabel)}
                  >
                    <GroupIcon className="h-5 w-5" />
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </nav>

      {/* Collapse Button */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center justify-center py-2 border-t border-slate-700/50 text-slate-500 hover:text-slate-300 transition-all duration-200 hover:bg-slate-800/40"
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        data-onboarding="sidebar-toggle"
      >
        {collapsed ? (
          isRTL ? (
            <ChevronLeft className="h-4 w-4 transition-transform duration-200" />
          ) : (
            <ChevronRight className="h-4 w-4 transition-transform duration-200" />
          )
        ) : isRTL ? (
          <ChevronRight className="h-4 w-4 transition-transform duration-200" />
        ) : (
          <ChevronLeft className="h-4 w-4 transition-transform duration-200" />
        )}
      </button>
    </aside>
  );
};

export default EnhancedSidebar;
