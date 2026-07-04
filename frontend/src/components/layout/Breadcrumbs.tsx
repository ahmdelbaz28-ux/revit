import React from "react";
import { useLocation, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ChevronRight, Home } from "lucide-react";

interface BreadcrumbItem {
  label: string;
  path: string;
  icon?: React.ElementType;
}

// Route to breadcrumb mapping
const BREADCRUMB_MAP: Record<string, BreadcrumbItem[]> = {
  "/dashboard": [{ label: "Dashboard", path: "/dashboard" }],
  "/projects": [{ label: "Projects", path: "/projects" }],
  "/projects/:id": [
    { label: "Projects", path: "/projects" },
    { label: "Project Details", path: "" },
  ],
  "/engineering": [{ label: "Engineering", path: "/engineering" }],
  "/engineering/qomn": [
    { label: "Engineering", path: "/engineering" },
    { label: "QOMN Calculator", path: "/engineering/qomn" },
  ],
  "/engineering/facp": [
    { label: "Engineering", path: "/engineering" },
    { label: "FACP Designer", path: "/engineering/facp" },
  ],
  "/engineering/guards": [
    { label: "Engineering", path: "/engineering" },
    { label: "Physics Guards", path: "/engineering/guards" },
  ],
  "/fire-alarm/designer": [
    { label: "Fire Alarm", path: "/fire-alarm" },
    { label: "Designer", path: "/fire-alarm/designer" },
  ],
  "/reports": [{ label: "Reports", path: "/reports" }],
  "/elements": [{ label: "Elements", path: "/elements" }],
  "/connections": [{ label: "Connections", path: "/connections" }],
  "/conflicts": [{ label: "Conflicts", path: "/conflicts" }],
  "/revit": [{ label: "Revit", path: "/revit" }],
  "/revit/create": [
    { label: "Revit", path: "/revit" },
    { label: "Create", path: "/revit/create" },
  ],
  "/revit/elements": [
    { label: "Revit", path: "/revit" },
    { label: "Elements", path: "/revit/elements" },
  ],
  "/autocad": [{ label: "AutoCAD", path: "/autocad" }],
  "/autocad/draw": [
    { label: "AutoCAD", path: "/autocad" },
    { label: "Draw", path: "/autocad/draw" },
  ],
  "/digital-twin": [{ label: "Digital Twin", path: "/digital-twin" }],
  "/digital-twin/convert": [
    { label: "Digital Twin", path: "/digital-twin" },
    { label: "Convert", path: "/digital-twin/convert" },
  ],
  "/digital-twin/config": [
    { label: "Digital Twin", path: "/digital-twin" },
    { label: "Configuration", path: "/digital-twin/config" },
  ],
  "/digital-twin/history": [
    { label: "Digital Twin", path: "/digital-twin" },
    { label: "History", path: "/digital-twin/history" },
  ],
  "/settings": [{ label: "Settings", path: "/settings" }],
  "/settings/advanced": [
    { label: "Settings", path: "/settings" },
    { label: "Advanced", path: "/settings/advanced" },
  ],
  "/system-health": [
    { label: "System", path: "" },
    { label: "Health", path: "/system-health" },
  ],
  "/integrations": [{ label: "Integrations", path: "/integrations" }],
};

const Breadcrumbs: React.FC = () => {
  const location = useLocation();
  const { t } = useTranslation();
  const isRTL = document.documentElement.dir === "rtl";

  // Get breadcrumbs from map, or generate from path
  let breadcrumbs = BREADCRUMB_MAP[location.pathname];

  if (!breadcrumbs) {
    // Generate default breadcrumb from path
    const segments = location.pathname.split("/").filter(Boolean);
    breadcrumbs = [
      { label: "Home", path: "/dashboard" },
      ...segments.map((segment, idx) => ({
        label: segment.charAt(0).toUpperCase() + segment.slice(1),
        path: "/" + segments.slice(0, idx + 1).join("/"),
      })),
    ];
  }

  // Don't show breadcrumbs on dashboard
  if (location.pathname === "/dashboard") {
    return null;
  }

  return (
    <nav
      className="flex items-center gap-1 px-4 py-2.5 bg-slate-950 border-b border-slate-800/50 text-sm"
      aria-label="Breadcrumb"
    >
      <Link
        to="/dashboard"
        className="flex items-center gap-1 text-slate-400 hover:text-slate-200 transition-colors"
        title="Home"
      >
        <Home className="h-4 w-4" />
      </Link>

      {breadcrumbs.map((item, idx) => (
        <React.Fragment key={`${item.path}-${idx}`}>
          <ChevronRight className={`h-4 w-4 text-slate-600 ${isRTL ? "rotate-180" : ""}`} />
          {item.path ? (
            <Link
              to={item.path}
              className="text-slate-400 hover:text-slate-200 transition-colors truncate"
            >
              {item.label}
            </Link>
          ) : (
            <span className="text-slate-300 truncate">{item.label}</span>
          )}
        </React.Fragment>
      ))}
    </nav>
  );
};

export default Breadcrumbs;
