import type { ElementType } from 'react';
import { useTranslation } from 'react-i18next';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  FolderKanban,
  Calculator,
  FlameKindling,
  Gem,
  FileText,
  Blocks,
  Link2,
  GitConflict,
  Settings2,
} from 'lucide-react';

export interface NavItem {
  path: string;
  labelKey: string;
  icon: ElementType;
}

export const NAV_ITEMS: NavItem[] = [
  { path: '/dashboard', labelKey: 'nav.dashboard', icon: LayoutDashboard },
  { path: '/projects', labelKey: 'nav.projects', icon: FolderKanban },
  { path: '/engineering', labelKey: 'nav.engineering', icon: Calculator },
  { path: '/fire-alarm/designer', labelKey: 'nav.fireAlarmDesigner', icon: FlameKindling },
  { path: '/digital-twin', labelKey: 'nav.digitalTwin', icon: Gem },
  { path: '/reports', labelKey: 'nav.reports', icon: FileText },
  { path: '/elements', labelKey: 'nav.elements', icon: Blocks },
  { path: '/connections', labelKey: 'nav.connections', icon: Link2 },
  { path: '/conflicts', labelKey: 'nav.conflicts', icon: GitConflict },
  { path: '/settings', labelKey: 'nav.settings', icon: Settings2 },
];

export function Sidebar() {
  return (
    <aside className="flex w-64 shrink-0 flex-col border-e border-slate-800 bg-slate-950">
      <div className="flex items-center gap-3 border-b border-slate-800 px-4 py-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-red-600 text-white">
          <FlameKindling className="h-5 w-5" />
        </div>
        <div>
          <div className="text-sm font-semibold text-slate-100">FireAI</div>
          <div className="text-[11px] text-slate-500">Engineering Shell</div>
        </div>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;

          return (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path !== '/settings'}
              className={({ isActive }) =>
                [
                  'group flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-red-600 text-white shadow-lg shadow-red-950/30'
                    : 'text-slate-400 hover:bg-slate-900 hover:text-slate-100',
                ].join(' ')
              }
            >
              <Icon className="h-4 w-4" />
              <span className="flex-1 text-left">Navigation Label</span>
            </NavLink>
          );
        })}
      </nav>

      <div className="border-t border-slate-800 p-4">
        <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-3">
          <div className="text-xs font-medium text-slate-300">Phase 1 Shell</div>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            Premium dark UI with smart help and backend status.
          </p>
        </div>
      </div>
    </aside>
  );
}
