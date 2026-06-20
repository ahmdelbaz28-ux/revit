import React, { useState } from "react";
import { useLocation, Link } from "react-router-dom";
import {
  LayoutDashboard,
  FolderKanban,
  Calculator,
  Flame,
  Box,
  FileText,
  Layers,
  Cable,
  AlertTriangle,
  Activity,
  Settings,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

interface NavItem {
  label: string;
  icon: React.ElementType;
  path: string;
  dataOnboarding?: string;
}

const navItems: NavItem[] = [
  { label: "Dashboard", icon: LayoutDashboard, path: "/", dataOnboarding: "nav-dashboard" },
  { label: "Projects", icon: FolderKanban, path: "/projects", dataOnboarding: "nav-projects" },
  { label: "Engineering", icon: Calculator, path: "/engineering", dataOnboarding: "nav-engineering" },
  { label: "Fire Alarm Designer", icon: Flame, path: "/fire-alarm-designer", dataOnboarding: "nav-fire-alarm-designer" },
  { label: "Predictive Maintenance", icon: Activity, path: "/predictive-maintenance", dataOnboarding: "nav-predictive-maintenance" },
  { label: "Digital Twin", icon: Box, path: "/digital-twin" },
  { label: "Reports", icon: FileText, path: "/reports", dataOnboarding: "nav-reports" },
  { label: "Elements", icon: Layers, path: "/elements" },
  { label: "Connections", icon: Cable, path: "/connections" },
  { label: "Conflicts", icon: AlertTriangle, path: "/conflicts" },
  { label: "Settings", icon: Settings, path: "/settings", dataOnboarding: "nav-settings" },
];

interface SidebarProps {
  compact?: boolean;
}

const Sidebar: React.FC<SidebarProps> = ({ compact = false }) => {
  const [collapsed, setCollapsed] = useState(false);
  const [hoveredItem, setHoveredItem] = useState<string | null>(null);
  const location = useLocation();
  const isRTL = document.documentElement.dir === "rtl";

  const width = collapsed
    ? compact
      ? "w-12"
      : "w-16"
    : compact
      ? "w-48"
      : "w-56";

  return (
    <aside
      className={`${width} h-full bg-slate-900/90 backdrop-blur-sm border-${
        isRTL ? "l" : "r"
      } border-slate-700/50 flex flex-col transition-all duration-300 ${
        isRTL ? "order-last" : "order-first"
      }`}
    >
      <div className="flex items-center gap-2 px-3 py-3 border-b border-slate-700/50">
        <Flame className="h-6 w-6 text-orange-500 shrink-0 transition-transform duration-300 group-hover:scale-110" />
        {!collapsed && (
          <span className="text-white font-bold text-lg tracking-wide">
            FireAI
          </span>
        )}
      </div>

      <nav className="flex-1 py-2 overflow-y-auto">
        {navItems.map((item) => {
          const isActive = location.pathname === item.path;
          const isHovered = hoveredItem === item.path;
          return (
            <div key={item.path} className="relative">
              <Link
                to={item.path}
                className={`flex items-center gap-3 px-3 py-2 mx-1 rounded-xl transition-all duration-200 ${
                  isActive
                    ? "bg-slate-800/80 border-l-2 border-orange-500 text-orange-400 shadow-lg shadow-orange-500/20"
                    : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
                } ${compact && !collapsed ? "py-1.5 text-sm" : ""}`}
                onMouseEnter={() => setHoveredItem(item.path)}
                onMouseLeave={() => setHoveredItem(null)}
                title={collapsed ? item.label : undefined}
                data-onboarding={item.dataOnboarding}
              >
                <item.icon
                  className={`shrink-0 transition-transform duration-300 ${
                    isActive ? "text-orange-400 scale-110" : isHovered ? "scale-105 text-orange-300" : "text-slate-500"
                  } ${compact && !collapsed ? "h-4 w-4" : "h-5 w-5"}`}
                />
                {!collapsed && (
                  <span
                    className={`truncate transition-all duration-200 ${compact && !collapsed ? "text-xs" : "text-sm"}`}
                  >
                    {item.label}
                  </span>
                )}
              </Link>
              {collapsed && isHovered && (
                <div className={`absolute top-1/2 -translate-y-1/2 px-2 py-1 bg-slate-800/90 backdrop-blur-sm text-slate-200 text-xs rounded shadow-lg z-50 whitespace-nowrap ${isRTL ? "right-full mr-2" : "left-full ml-2"}`}>
                  {item.label}
                </div>
              )}
            </div>
          );
        })}
      </nav>

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

export default Sidebar;