import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { HELP_TOPICS } from "@/help/helpTopics";

export interface CommandItem {
  id: string;
  label: string;
  shortcut?: string;
  icon?: React.ReactNode;
  category: "navigation" | "action" | "help";
  path?: string;
  helpTopicId?: string;
}

const COMMANDS: CommandItem[] = [
  // Navigation - Core
  { id: "cmd-dashboard", label: "Open Dashboard", shortcut: "G D", category: "navigation", path: "/dashboard" },
  { id: "cmd-projects", label: "Open Projects", shortcut: "G P", category: "navigation", path: "/projects" },
  { id: "cmd-elements", label: "Open Elements", category: "navigation", path: "/elements" },
  { id: "cmd-connections", label: "Open Connections", category: "navigation", path: "/connections" },
  { id: "cmd-conflicts", label: "Open Conflicts", category: "navigation", path: "/conflicts" },

  // Navigation - Engineering (Safety Critical)
  { id: "cmd-engineering", label: "Open Engineering Console", shortcut: "G E", category: "navigation", path: "/engineering" },
  { id: "cmd-qomn-calc", label: "QOMN Calculator - Smoke/Heat Spacing", category: "navigation", path: "/engineering/qomn" },
  { id: "cmd-qomn-battery", label: "Battery Requirements Calculation", category: "navigation", path: "/engineering/qomn" },
  { id: "cmd-qomn-voltage", label: "Voltage Drop Analysis", category: "navigation", path: "/engineering/qomn" },
  { id: "cmd-qomn-detectors", label: "Detector Placement Tool", category: "navigation", path: "/engineering/qomn" },
  { id: "cmd-facp-designer", label: "FACP Panel Designer", shortcut: "G F", category: "navigation", path: "/engineering/facp" },
  { id: "cmd-physics-guards", label: "Physics Guards Monitor", category: "navigation", path: "/engineering/guards" },

  // Navigation - CAD/BIM Integration
  { id: "cmd-revit", label: "Revit Integration", category: "navigation", path: "/revit" },
  { id: "cmd-revit-create", label: "Revit - Create Elements", category: "navigation", path: "/revit/create" },
  { id: "cmd-revit-elements", label: "Revit - Element Browser", category: "navigation", path: "/revit/elements" },
  { id: "cmd-autocad", label: "AutoCAD Integration", category: "navigation", path: "/autocad" },
  { id: "cmd-autocad-draw", label: "AutoCAD - Drawing Tools", category: "navigation", path: "/autocad/draw" },
  { id: "cmd-digital-twin", label: "Digital Twin", shortcut: "G T", category: "navigation", path: "/digital-twin" },
  { id: "cmd-dt-convert", label: "Digital Twin - Convert", category: "navigation", path: "/digital-twin/convert" },
  { id: "cmd-dt-config", label: "Digital Twin - Configuration", category: "navigation", path: "/digital-twin/config" },
  { id: "cmd-dt-history", label: "Digital Twin - History & Rollback", category: "navigation", path: "/digital-twin/history" },
  { id: "cmd-fire-alarm-designer", label: "Fire Alarm Designer", category: "navigation", path: "/fire-alarm/designer" },

  // Navigation - Environment & Context
  { id: "cmd-environment-context", label: "Weather & Geocoding", category: "navigation", path: "/environment/context" },
  { id: "cmd-air-quality", label: "Air Quality Data", category: "navigation", path: "/environment/air-quality" },
  { id: "cmd-hazmat-db", label: "HazMat Database", category: "navigation", path: "/environment/hazmat" },

  // Navigation - Reports & Exports
  { id: "cmd-reports", label: "Open Reports", shortcut: "G R", category: "navigation", path: "/reports" },
  { id: "cmd-export-manager", label: "Export Manager (DXF/Revit/IFC)", category: "navigation", path: "/exports" },
  { id: "cmd-audit-trail", label: "Audit Trail Viewer", category: "navigation", path: "/audit-trail" },

  // Navigation - System & Monitoring
  { id: "cmd-system-health", label: "System Health Dashboard", category: "navigation", path: "/system-health" },
  { id: "cmd-agent-activity", label: "Agent Activity Log", category: "navigation", path: "/agent-activity" },
  { id: "cmd-security-alerts", label: "Security Alerts", category: "navigation", path: "/security-alerts" },

  // Navigation - Settings
  { id: "cmd-settings", label: "Settings", shortcut: "G S", category: "navigation", path: "/settings" },
  { id: "cmd-advanced-settings", label: "Advanced Settings Hub", category: "navigation", path: "/settings/advanced" },

  // Actions
  { id: "cmd-create-project", label: "Create New Project", category: "action", path: "/projects" },
  { id: "cmd-new-element", label: "Create New Element", category: "action", path: "/elements" },
  { id: "cmd-new-connection", label: "Create New Connection", category: "action", path: "/connections" },
  { id: "cmd-generate-report", label: "Generate Report", shortcut: "N R", category: "action", path: "/reports" },
  { id: "cmd-run-compliance", label: "Run Compliance Check (NFPA 72)", category: "action", path: "/engineering" },
  { id: "cmd-export-project", label: "Export Project", category: "action", path: "/exports" },

  // Help
  { id: "cmd-help", label: "Open Help", shortcut: "F1", category: "help", helpTopicId: "dashboard.overview" },
  { id: "cmd-keyboard-shortcuts", label: "Keyboard Shortcuts", shortcut: "?", category: "help" },
];

type CommandPaletteSearchResult = {
  type: "command";
  item: CommandItem;
};

type HelpSearchResult = {
  type: "help";
  item: (typeof HELP_TOPICS)[keyof typeof HELP_TOPICS];
};

type PaletteItem = CommandPaletteSearchResult | HelpSearchResult;

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const CommandPalette: React.FC<CommandPaletteProps> = ({ open, onOpenChange }) => {
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  const results: PaletteItem[] = (() => {
    const q = query.trim().toLowerCase();
    if (!q) {
      return COMMANDS.map((item) => ({ type: "command" as const, item }));
    }

    const matchedCommands = COMMANDS.filter((item) => item.label.toLowerCase().includes(q));
    const matchedHelp = Object.values(HELP_TOPICS).filter((topic) =>
      [topic.titleEn, topic.titleAr, topic.descriptionEn, topic.descriptionAr, topic.id]
        .some((value) => value.toLowerCase().includes(q))
    );

    return [
      ...matchedCommands.map((item) => ({ type: "command" as const, item })),
      ...matchedHelp.map((item) => ({ type: "help" as const, item })),
    ];
  })();

  useEffect(() => {
    if (open) {
      setQuery("");
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  const execute = (result: PaletteItem) => {
    if (result.type === "command") {
      if (result.item.path) {
        navigate(result.item.path);
      }
    }
    setQuery("");
    onOpenChange(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev - 1 + results.length) % results.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      execute(results[selectedIndex]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setQuery("");
      onOpenChange(false);
    }
  };

  useEffect(() => {
    if (selectedIndex >= results.length && results.length > 0) {
      setSelectedIndex(results.length - 1);
    }
  }, [selectedIndex, results.length]);

  useEffect(() => {
    if (!open || !listRef.current) {
      return;
    }
    const items = listRef.current.querySelectorAll("[role=\"option\"]");
    const active = items[selectedIndex];
    if (active) {
      active.scrollIntoView({ block: "nearest" });
    }
  }, [selectedIndex, open]);

  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-[200] flex items-start justify-center pt-[20vh]">
      <div className="absolute inset-0 bg-black/70" onClick={() => onOpenChange(false)} />
      <div className="relative w-full max-w-xl mx-4 bg-slate-900 border border-slate-700 rounded-xl shadow-2xl overflow-hidden">
        <div className="flex items-center gap-3 p-4 border-b border-slate-700">
          <Search className="h-5 w-5 text-slate-400 shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a command or search help..."
            className="flex-1 bg-transparent text-slate-100 text-sm placeholder:text-slate-500 outline-none"
          />
          <button
            onClick={() => onOpenChange(false)}
            className="text-xs text-slate-500 border border-slate-700 rounded px-2 py-1 hover:text-slate-300"
          >
            ESC
          </button>
        </div>

        <div ref={listRef} className="max-h-80 overflow-y-auto p-2">
          {results.length === 0 ? (
            <div className="py-6 text-center text-sm text-slate-500">No results found</div>
          ) : (
            results.map((result, index) => {
              const isActive = index === selectedIndex;
              if (result.type === "command") {
                return (
                  <button
                    key={result.item.id}
                    role="option"
                    aria-selected={isActive}
                    onClick={() => execute(result)}
                    onMouseEnter={() => setSelectedIndex(index)}
                    className={cn(
                      "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors",
                      isActive ? "bg-slate-800 text-slate-100" : "text-slate-300 hover:bg-slate-800/60"
                    )}
                  >
                    <span className="flex h-8 w-8 items-center justify-center rounded bg-slate-800 text-slate-400">
                      {result.item.icon || <Search className="h-4 w-4" />}
                    </span>
                    <span className="flex-1 text-left">{result.item.label}</span>
                    {result.item.shortcut && (
                      <span className="flex gap-1">
                        <kbd className="hidden sm:inline-block rounded bg-slate-800 border border-slate-600 px-1.5 py-0.5 text-[10px] text-slate-400">
                          {result.item.shortcut}
                        </kbd>
                      </span>
                    )}
                  </button>
                );
              }

              const title = result.item.titleEn;
              return (
                <button
                  key={result.item.id}
                  role="option"
                  aria-selected={isActive}
                  onClick={() => execute(result)}
                  onMouseEnter={() => setSelectedIndex(index)}
                  className={cn(
                    "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors",
                    isActive ? "bg-slate-800 text-slate-100" : "text-slate-300 hover:bg-slate-800/60"
                  )}
                >
                  <span className="flex h-8 w-8 items-center justify-center rounded bg-slate-800 text-slate-400">
                    <Search className="h-4 w-4" />
                  </span>
                  <span className="flex-1 text-left">
                    <span className="block text-slate-100">{title}</span>
                    <span className="block text-xs text-slate-500">{result.item.id}</span>
                  </span>
                  <span className="text-[10px] text-slate-500 border border-slate-700 rounded px-1.5 py-0.5">HELP</span>
                </button>
              );
            })
          )}
        </div>

        <div className="flex items-center justify-between border-t border-slate-700 px-4 py-2 text-xs text-slate-500">
          <span>{results.length} results</span>
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1">
              <kbd className="rounded bg-slate-800 border border-slate-600 px-1 py-0.5 text-[10px]">↑↓</kbd> navigate
            </span>
            <span className="flex items-center gap-1">
              <kbd className="rounded bg-slate-800 border border-slate-600 px-1 py-0.5 text-[10px]">↵</kbd> select
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CommandPalette;
