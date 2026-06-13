/**
 * App.tsx - FireAI Revit Digital Twin Application
 * Uses React Router for navigation with all pages accessible
 */
import { Routes, Route, NavLink, useLocation } from 'react-router-dom';
import { useState, useEffect, Suspense, lazy } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  LayoutDashboard,
  FolderKanban,
  Flame,
  Calculator,
  FileText,
  Settings,
  Menu,
  X,
  Activity,
  Layers,
  Cable,
  AlertTriangle,
} from 'lucide-react';
import { useHealth } from '@/hooks/useApi';
import { ErrorBoundary } from '@/components/core/ErrorBoundary';
import { PageErrorBoundary } from '@/components/core/PageErrorBoundary';
import { DashboardPage } from '@/pages/DashboardPage';
import { ProjectsPage } from '@/pages/ProjectsPage';
import { EngineeringPage } from '@/pages/EngineeringPage';
import { FireAlarmPage } from '@/pages/FireAlarmPage';
import { ReportsPage } from '@/pages/ReportsPage';
import { SettingsPage } from '@/pages/SettingsPage';

// Lazy-load the BIM pages that use the older api.ts / @tanstack/react-query
const ElementsPage = lazy(() => import('@/pages/Elements'));
const ElementDetailPage = lazy(() => import('@/pages/ElementDetail'));
const ConnectionsPage = lazy(() => import('@/pages/Connections'));
const ConflictsPage = lazy(() => import('@/pages/Conflicts'));

// ============================================================================
// Navigation configuration
// ============================================================================

interface NavConfig {
  to: string;
  label: string;
  icon: React.ReactNode;
  description: string;
  end?: boolean;
}

const NAV_ITEMS: NavConfig[] = [
  { to: '/', label: 'Dashboard', icon: <LayoutDashboard className="h-4 w-4" />, description: 'Overview & Status', end: true },
  { to: '/projects', label: 'Projects', icon: <FolderKanban className="h-4 w-4" />, description: 'Manage Projects' },
  { to: '/fire-alarm', label: 'Fire Alarm Designer', icon: <Flame className="h-4 w-4" />, description: 'Fire Alarm Layout' },
  { to: '/engineering', label: 'Engineering', icon: <Calculator className="h-4 w-4" />, description: 'Calculations' },
  { to: '/elements', label: 'Elements', icon: <Layers className="h-4 w-4" />, description: 'BIM Elements' },
  { to: '/connections', label: 'Connections', icon: <Cable className="h-4 w-4" />, description: 'Element Links' },
  { to: '/conflicts', label: 'Conflicts', icon: <AlertTriangle className="h-4 w-4" />, description: 'Conflict Resolution' },
  { to: '/reports', label: 'Reports', icon: <FileText className="h-4 w-4" />, description: 'Generate Reports' },
  { to: '/settings', label: 'Settings', icon: <Settings className="h-4 w-4" />, description: 'Configuration' },
];

// ============================================================================
// Page loading fallback
// ============================================================================

function PageLoader() {
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <Activity className="h-8 w-8 text-slate-400 animate-pulse" />
        <span className="text-sm text-slate-400">Loading...</span>
      </div>
    </div>
  );
}

// ============================================================================
// App Component
// ============================================================================

function AppInner() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const location = useLocation();

  const { data: health, connected, refetch: refetchHealth } = useHealth();

  // Auto-refresh health status every 30 seconds
  // In a safety-critical system, operators must see current connection state
  useEffect(() => {
    const interval = setInterval(() => {
      refetchHealth();
    }, 30_000);
    return () => clearInterval(interval);
  }, [refetchHealth]);

  // Fire Alarm Designer gets full-screen mode
  const isFireAlarm = location.pathname === '/fire-alarm';

  if (isFireAlarm) {
    return (
      <div className="relative">
        <NavLink to="/">
          <Button
            variant="outline"
            size="sm"
            className="fixed top-3 left-3 z-50 bg-slate-800/90 border-slate-600 text-slate-300 hover:bg-slate-700 backdrop-blur-sm"
          >
            ← Exit Designer
          </Button>
        </NavLink>
        <FireAlarmPage />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex">
      {/* Mobile overlay */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed lg:static inset-y-0 left-0 z-50
          w-64 bg-slate-800 border-r border-slate-700
          flex flex-col
          transform transition-transform duration-200 ease-in-out
          ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
        `}
      >
        {/* Logo */}
        <div className="p-4 border-b border-slate-700">
          <NavLink to="/" className="flex items-center gap-3" onClick={() => setMobileMenuOpen(false)}>
            <div className="w-8 h-8 rounded-lg bg-red-600 flex items-center justify-center">
              <Flame className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-sm font-bold text-slate-100 tracking-wide">FireAI</h1>
              <p className="text-[10px] text-slate-400 uppercase tracking-wider">Revit Platform</p>
            </div>
          </NavLink>
        </div>

        {/* Navigation */}
        <ScrollArea className="flex-1 py-3">
          <nav className="space-y-1 px-2">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                onClick={() => setMobileMenuOpen(false)}
                className={({ isActive }) => `
                  w-full flex items-center gap-3 px-3 py-2.5 rounded-lg
                  text-sm transition-all duration-150
                  ${
                    isActive
                      ? 'bg-red-600/10 text-red-400 font-medium border border-red-500/20'
                      : 'text-slate-300 hover:bg-slate-700/50 hover:text-slate-100 border border-transparent'
                  }
                `}
              >
                {({ isActive }) => (
                  <>
                    <span className={isActive ? 'text-red-400' : 'text-slate-400'}>
                      {item.icon}
                    </span>
                    <div className="text-left">
                      <div>{item.label}</div>
                      <div className="text-[10px] text-slate-500">{item.description}</div>
                    </div>
                  </>
                )}
              </NavLink>
            ))}
          </nav>
        </ScrollArea>

        {/* Connection Status */}
        <div className="p-3 border-t border-slate-700">
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${connected ? 'bg-emerald-400' : 'bg-red-400'} ${!connected && !health ? 'animate-pulse' : ''}`} />
            <span className="text-xs text-slate-400">
              {connected ? 'Connected' : 'Offline'}
            </span>
            {health && (
              <Badge variant="outline" className="text-[9px] ml-auto py-0 px-1 border-slate-600 text-slate-400">
                v{health.version}
              </Badge>
            )}
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="w-full mt-2 text-xs text-slate-400 hover:text-slate-200"
            onClick={() => refetchHealth()}
          >
            <Activity className="h-3 w-3 mr-1" /> Refresh Status
          </Button>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Bar */}
        <header className="h-12 border-b border-slate-700 bg-slate-800/50 flex items-center justify-between px-4 shrink-0">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              className="lg:hidden text-slate-400 hover:text-slate-200"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            >
              {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </Button>
            <Separator orientation="vertical" className="h-5 bg-slate-700 hidden lg:block" />
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-slate-200">
                {NAV_ITEMS.find((n) => {
                  if (n.end) return location.pathname === n.to;
                  return location.pathname.startsWith(n.to);
                })?.label || 'Dashboard'}
              </span>
              <Badge
                variant="outline"
                className="text-[9px] border-slate-600 text-slate-400"
              >
                {connected ? 'LIVE' : 'OFFLINE'}
              </Badge>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${connected ? 'bg-emerald-400' : 'bg-red-400'}`} />
            <span className="text-xs text-slate-400 hidden sm:inline">
              {connected ? 'Backend Connected' : 'Backend Disconnected'}
            </span>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 flex flex-col overflow-hidden">
          <Suspense fallback={<PageLoader />}>
            <Routes>
              <Route path="/" element={<PageErrorBoundary pageName="Dashboard"><DashboardPage /></PageErrorBoundary>} />
              <Route path="/projects" element={<PageErrorBoundary pageName="Projects"><ProjectsPage /></PageErrorBoundary>} />
              <Route path="/engineering" element={<PageErrorBoundary pageName="Engineering"><EngineeringPage /></PageErrorBoundary>} />
              <Route path="/fire-alarm" element={<PageErrorBoundary pageName="Fire Alarm Designer"><FireAlarmPage /></PageErrorBoundary>} />
              <Route path="/elements" element={<PageErrorBoundary pageName="Elements"><ElementsPage /></PageErrorBoundary>} />
              <Route path="/elements/:id" element={<PageErrorBoundary pageName="Element Detail"><ElementDetailPage /></PageErrorBoundary>} />
              <Route path="/connections" element={<PageErrorBoundary pageName="Connections"><ConnectionsPage /></PageErrorBoundary>} />
              <Route path="/conflicts" element={<PageErrorBoundary pageName="Conflicts"><ConflictsPage /></PageErrorBoundary>} />
              <Route path="/reports" element={<PageErrorBoundary pageName="Reports"><ReportsPage /></PageErrorBoundary>} />
              <Route path="/settings" element={<PageErrorBoundary pageName="Settings"><SettingsPage /></PageErrorBoundary>} />
              <Route path="*" element={<div className="flex-1 flex items-center justify-center"><div className="text-center"><h2 className="text-2xl font-bold text-slate-300 mb-2">404</h2><p className="text-slate-500">Page not found</p><NavLink to="/" className="text-red-400 hover:text-red-300 text-sm mt-4 inline-block">Return to Dashboard</NavLink></div></div>} />
            </Routes>
          </Suspense>
        </main>
      </div>
    </div>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <AppInner />
    </ErrorBoundary>
  );
}

export default App;
