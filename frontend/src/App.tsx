import React, { useEffect, useState, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Toaster } from 'sonner';
import { useHealth } from '@/hooks/useApi';
import AppShell from '@/components/layout/AppShell';
import { SmartHelpDrawer } from '@/components/help/SmartHelpDrawer';
import CommandPalette from '@/components/command/CommandPalette';
import OnboardingTour from '@/components/onboarding/OnboardingTour';
import { PageErrorBoundary } from '@/components/core/PageErrorBoundary';
// P1.9: Eagerly load DashboardPage (landing page — must render instantly)
// and NotFoundPage (404 fallback — small, no benefit from lazy).
import { DashboardPage } from './pages/DashboardPage';
import { NotFoundPage } from './pages/NotFoundPage';
// P1.9: Lazily load all other pages to reduce initial bundle size.
// Each page becomes a separate chunk loaded on first navigation.
// Pattern for named exports: .then(m => ({ default: m.PageName }))
const ProjectsPage = React.lazy(() =>
  import('./pages/ProjectsPage').then(m => ({ default: m.ProjectsPage }))
);
const EngineeringPage = React.lazy(() =>
  import('./pages/EngineeringPage').then(m => ({ default: m.EngineeringPage }))
);
const ReportsPage = React.lazy(() =>
  import('./pages/ReportsPage').then(m => ({ default: m.ReportsPage }))
);
const ReportGeneratorPage = React.lazy(() =>
  import('./pages/ReportGeneratorPage').then(m => ({ default: m.ReportGeneratorPage }))
);
const SettingsPage = React.lazy(() =>
  import('./pages/SettingsPage').then(m => ({ default: m.SettingsPage }))
);
const FireAlarmPage = React.lazy(() =>
  import('./pages/FireAlarmPage').then(m => ({ default: m.FireAlarmPage }))
);
const FireAlarmDesigner = React.lazy(() =>
  import('./components/mockups/engineering/FireAlarmDesigner').then(m => ({ default: m.FireAlarmDesigner }))
);
const DigitalTwinPage = React.lazy(() =>
  import('./pages/DigitalTwinPage').then(m => ({ default: m.DigitalTwinPage }))
);
const CADSettingsPage = React.lazy(() =>
  import('./pages/CADSettingsPage').then(m => ({ default: m.CADSettingsPage }))
);
const PredictiveMaintenancePage = React.lazy(() =>
  import('./pages/PredictiveMaintenancePage').then(m => ({ default: m.PredictiveMaintenancePage }))
);
const DiagramDemoPage = React.lazy(() =>
  import('./pages/DiagramDemoPage').then(m => ({ default: m.DiagramDemoPage }))
);
// These use default exports — simpler pattern
const Elements = React.lazy(() => import('./pages/Elements'));
const ElementDetail = React.lazy(() => import('./pages/ElementDetail'));
const Connections = React.lazy(() => import('./pages/Connections'));
const Conflicts = React.lazy(() => import('./pages/Conflicts'));
import './i18n';
import './styles/globals.css';
import './styles/typography.css';

// P1.9: Simple loading fallback shown while lazy chunks download.
function PageLoader() {
  return (
    <div className="flex items-center justify-center min-h-[60vh]" role="status" aria-live="polite">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-slate-600 border-t-slate-300 rounded-full animate-spin" />
        <span className="text-sm text-slate-400">Loading…</span>
      </div>
    </div>
  );
}

/**
 * P0.6 FIX — App.tsx routing + syntax + 404 fallback
 * ===================================================
 *
 * THREE bugs fixed in this file:
 *
 * 1. SYNTAX ERROR (line 30, pre-fix):
 *      `const elpOpen, setHelpOpen] = useState(false);`
 *    Missing the opening `[h` — this is an unrecoverable syntax error
 *    that breaks `npm run typecheck` AND `npm run build` entirely. The
 *    entire frontend CI Gate 4 has been red since commit cdbbad3f.
 *    Fix: `const [helpOpen, setHelpOpen] = useState(false);`
 *
 * 2. UNREACHABLE ROUTES (5 missing):
 *    The Sidebar links to /elements, /connections, /conflicts,
 *    /element-detail/:id, and /report-generator, but App.tsx only
 *    registered 12 routes — none of these 5 were present. Clicking
 *    those sidebar items rendered a blank page.
 *    Fix: added all 5 routes pointing to their existing page components.
 *
 * 3. NO 404 FALLBACK:
 *    Without a `path="*"` catch-all route, any unrecognized URL (typos,
 *    stale bookmarks, misconfigured links) silently rendered a blank
 *    page. In a safety-critical fire-protection tool, a blank page
 *    could mislead an engineer into thinking the system is working
 *    when a route is misconfigured. Now renders NotFoundPage with a
 *    clear 404 message + link back to dashboard.
 *
 * Additionally: every route is now wrapped in <PageErrorBoundary> so a
 * runtime error in one page does not crash the entire app. The
 * PageErrorBoundary component already existed at
 * @/components/core/PageErrorBoundary but was not being used.
 */
function App() {
  const { t, i18n } = useTranslation();
  const { connected } = useHealth();
  const [helpOpen, setHelpOpen] = useState(false);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);

  useEffect(() => {
    // Set document direction based on language for RTL support
    if (i18n.language === 'ar') {
      document.documentElement.dir = 'rtl';
      document.documentElement.lang = 'ar';
    } else {
      document.documentElement.dir = 'ltr';
      document.documentElement.lang = 'en';
    }
  }, [i18n.language]);

  // Keyboard shortcuts for help and command palette
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'F1' || (e.ctrlKey && e.key === 'h')) {
        e.preventDefault();
        setHelpOpen(true);
      } else if (e.ctrlKey && e.key === 'k') {
        e.preventDefault();
        setCommandPaletteOpen(true);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Define routes — every route is wrapped in <PageErrorBoundary> so a
  // runtime error in one page does not crash the entire app.
  const routes = [
    { path: '/', element: <Navigate to="/dashboard" />, name: 'root-redirect' },
    { path: '/dashboard', element: <DashboardPage />, name: 'dashboard' },
    { path: '/projects', element: <ProjectsPage />, name: 'projects' },
    { path: '/engineering', element: <EngineeringPage />, name: 'engineering' },
    { path: '/reports', element: <ReportsPage />, name: 'reports' },
    { path: '/report-generator', element: <ReportGeneratorPage />, name: 'report-generator' },
    { path: '/settings', element: <SettingsPage />, name: 'settings' },
    { path: '/settings/cad', element: <CADSettingsPage />, name: 'settings-cad' },
    { path: '/digital-twin', element: <DigitalTwinPage />, name: 'digital-twin' },
    { path: '/fire-alarm', element: <FireAlarmPage />, name: 'fire-alarm' },
    { path: '/fire-alarm/designer', element: <FireAlarmDesigner />, name: 'fire-alarm-designer' },
    { path: '/fire-alarm-designer', element: <FireAlarmDesigner />, name: 'fire-alarm-designer-alt' },
    { path: '/elements', element: <Elements />, name: 'elements' },
    { path: '/elements/:id', element: <ElementDetail />, name: 'element-detail' },
    { path: '/connections', element: <Connections />, name: 'connections' },
    { path: '/conflicts', element: <Conflicts />, name: 'conflicts' },
    { path: '/predictive-maintenance', element: <PredictiveMaintenancePage />, name: 'predictive-maintenance' },
    { path: '/diagram-demo', element: <DiagramDemoPage />, name: 'diagram-demo' },
  ];

  return (
    <div className="h-screen bg-slate-950 text-slate-100">
      <AppShell
        isConnected={connected}
        backendUrl={import.meta.env.VITE_API_URL || '/api/v1'}
        environment={import.meta.env.MODE || 'development'}
        currentLanguage={i18n.language}
        onLanguageChange={(lng: string) => i18n.changeLanguage(lng)}
        onHelpOpen={() => setHelpOpen(true)}
      >
        <main className="flex-1 overflow-auto">
          <Routes>
            {routes.map((route) => (
              <Route
                key={route.path}
                path={route.path}
                element={
                  <PageErrorBoundary pageName={route.name}>
                    <Suspense fallback={<PageLoader />}>
                      {route.element}
                    </Suspense>
                  </PageErrorBoundary>
                }
              />
            ))}
            {/* 404 fallback — must be last. Catches any unmatched URL. */}
            <Route
              path="*"
              element={
                <PageErrorBoundary pageName="not-found">
                  <NotFoundPage />
                </PageErrorBoundary>
              }
            />
          </Routes>
        </main>
      </AppShell>
      <SmartHelpDrawer
        open={helpOpen}
        onOpenChange={setHelpOpen}
      />
      <CommandPalette open={commandPaletteOpen} onOpenChange={setCommandPaletteOpen} />
      <OnboardingTour />
      <Toaster position="bottom-right" />
    </div>
  );
}

export default App;
