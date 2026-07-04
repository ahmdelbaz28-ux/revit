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
  ChevronDown,
  Gauge,
  Zap,
  Database,
  BarChart3,
  Building2,
  PencilRuler,
  ArrowRightLeft,
  History,
  Settings2,
  Menu,
  X,
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
      { labelKey: "nav.exports", defaultLabel: "Export Manager", icon: FileText, path: "/exports" },
      { labelKey: "nav.auditTrail", defaultLabel: "Audit Trail", icon: BarChart3, path: "/audit-trail" },
    ],
  },
  {
    groupKey: "monitoring",
    groupLabelKey: "nav.group.monitoring",
    defaultGroupLabel: "System & Monitoring",
    groupIcon: BarChart3,
    items: [
      { labelKey: "nav.systemHealth", defaultLabel: "System Health", icon: BarChart3, path: "/system-health" },
      { labelKey: "nav.agentActivity", defaultLabel: "Agent Activity", icon: Zap, path: "/agent-activity" },
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

interface SidebarGroupProps {
  group: NavGroup;
  isOpen: boolean;
  onToggle: () => void;
  currentPath: string;
}

const SidebarGroup: React.FC<SidebarGroupProps> = ({ group, isOpen, onToggle, currentPath }) => {
  const { t } = useTranslation();
  const GroupIcon = group.groupIcon;

  const isGroupActive = group.items.some((item) => currentPath === item.path);

  return (
    <div className="mb-2">
      <button
        onClick={onToggle}
        className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-200 ${
          isGroupActive
            ? "bg-cyan-500/10 text-cyan-400 border border-cyan-500/20"
            : "text-slate-400 hover:bg-slate-700/30 hover:text-slate-200"
        }`}
      >
        {GroupIcon && <GroupIcon size={18} className="flex-shrink-0" />}
        <span className="flex-1 text-left text-sm font-semibold">{t(group.groupLabelKey, group.defaultGroupLabel)}</span>
        <ChevronDown
          size={16}
          className={`flex-shrink-0 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`}
        />
      </button>

      {isOpen && (
        <div className="mt-2 ml-4 space-y-1 border-l border-slate-600/30 pl-3">
          {group.items.map((item) => {
            const ItemIcon = item.icon;
            const isActive = currentPath === item.path;

            return (
              <Link
                key={item.path}
                to={item.path}
                data-onboarding={item.dataOnboarding}
                className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-all duration-150 ${
                  isActive
                    ? "bg-cyan-500/20 text-cyan-300 font-medium"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-700/20"
                }`}
              >
                <ItemIcon size={16} className="flex-shrink-0" />
                <span className="truncate">{t(item.labelKey, item.defaultLabel)}</span>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
};

const EnhancedSidebar: React.FC = () => {
  const { t } = useTranslation();
  const location = useLocation();
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({
    core: true,
    engineering: true,
  });

  const toggleGroup = (groupKey: string) => {
    setExpandedGroups((prev) => ({
      ...prev,
      [groupKey]: !prev[groupKey],
    }));
  };

  const sidebarContent = (
    <div className="h-full flex flex-col bg-gradient-to-b from-slate-900 to-slate-950 border-r border-slate-700/50">
      {/* Header */}
      <div className="px-6 py-5 border-b border-slate-700/30">
        <h1 className="text-xl font-bold bg-gradient-to-r from-cyan-400 to-blue-400 bg-clip-text text-transparent">
          BAZSPARK
        </h1>
        <p className="text-xs text-slate-500 mt-1 font-medium">Fire Safety System</p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-4 py-5 space-y-1">
        {navGroups.map((group) => (
          <SidebarGroup
            key={group.groupKey}
            group={group}
            isOpen={expandedGroups[group.groupKey] || false}
            onToggle={() => toggleGroup(group.groupKey)}
            currentPath={location.pathname}
          />
        ))}
      </nav>

      {/* Footer */}
      <div className="px-4 py-4 border-t border-slate-700/30">
        <div className="text-xs text-slate-500 text-center">
          <p>v1.0.0</p>
          <p className="mt-1">NFPA 72 Compliant</p>
        </div>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Sidebar */}
      <div className="hidden md:flex w-64 flex-col bg-slate-900">
        {sidebarContent}
      </div>

      {/* Mobile Sidebar */}
      <div className="md:hidden flex items-center justify-between px-4 py-3 bg-slate-900 border-b border-slate-700/50">
        <h1 className="text-lg font-bold bg-gradient-to-r from-cyan-400 to-blue-400 bg-clip-text text-transparent">
          BAZSPARK
        </h1>
        <button
          onClick={() => setIsMobileOpen(!isMobileOpen)}
          className="p-2 hover:bg-slate-700/30 rounded-lg transition-colors"
        >
          {isMobileOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      {isMobileOpen && (
        <div className="md:hidden fixed inset-0 bg-black/50 z-40" onClick={() => setIsMobileOpen(false)}>
          <div className="absolute left-0 top-0 w-64 h-screen" onClick={(e) => e.stopPropagation()}>
            {sidebarContent}
          </div>
        </div>
      )}
    </>
  );
};

export default EnhancedSidebar;
