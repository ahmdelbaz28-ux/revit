import React, { useEffect, useState } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Toaster } from 'sonner';
import { useHealth } from '@/hooks/useApi';
import AppShell from '@/components/layout/AppShell';
import { SmartHelpDrawer } from '@/components/help/SmartHelpDrawer';
import CommandPalette from '@/components/command/CommandPalette';
import OnboardingTour from '@/components/onboarding/OnboardingTour';
import { GlobalHelpDrawer } from '@/components/shared/GlobalHelpDrawer';
import { ContextualHelpButton } from '@/components/shared/ContextualHelpButton';
import { ROUTE_HELP_MAP } from '@/help/types';
import type { HelpTopicId } from '@/help/types';
import { DashboardPage } from './pages/DashboardPage';
import { ProjectsPage } from './pages/ProjectsPage';
import { EngineeringPage } from './pages/EngineeringPage';
import { ReportsPage } from './pages/ReportsPage';
import { SettingsPage } from './pages/SettingsPage';
import { FireAlarmPage } from './pages/FireAlarmPage';
import { FireAlarmDesigner } from './components/mockups/engineering/FireAlarmDesigner';
import { DigitalTwinPage } from './pages/DigitalTwinPage';
import { CADSettingsPage } from './pages/CADSettingsPage';
import Elements from './pages/Elements';
import Connections from './pages/Connections';
import Conflicts from './pages/Conflicts';
import ElementDetail from './pages/ElementDetail';
// V140 Phase 6: New pages for comprehensive API coverage
import { AutoCADPage } from './pages/AutoCADPage';
import { AutoCADDrawPage } from './pages/AutoCADDrawPage';
import { RevitPage } from './pages/RevitPage';
import { RevitCreatePage } from './pages/RevitCreatePage';
import { RevitElementsPage } from './pages/RevitElementsPage';
import { DigitalTwinConvertPage } from './pages/DigitalTwinConvertPage';
import { DigitalTwinConfigPage } from './pages/DigitalTwinConfigPage';
import { DigitalTwinHistoryPage } from './pages/DigitalTwinHistoryPage';
import './i18n';
import './styles/globals.css';
import './styles/typography.css';

function App() {
  const { t, i18n } = useTranslation();
  const { connected } = useHealth();
  const location = useLocation();
  const [helpOpen, setHelpOpen] = useState(false);
  const [magicHelpTopic, setMagicHelpTopic] = useState<HelpTopicId | null>(null);
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

  // V140 Phase 7: Magic Help — F1 opens help for current page
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'F1' || (e.ctrlKey && e.key === 'h')) {
        e.preventDefault();
        // Find help topic for current route
        const routeTopic = ROUTE_HELP_MAP[location.pathname];
        setMagicHelpTopic(routeTopic || null);
        setHelpOpen(true);
      } else if (e.ctrlKey && e.key === 'k') {
        e.preventDefault();
        setCommandPaletteOpen(true);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [location.pathname]);

  // Define routes
  const routes = [
    { path: '/', element: <Navigate to="/dashboard" /> },
    { path: '/dashboard', element: <DashboardPage /> },
    { path: '/projects', element: <ProjectsPage /> },
    { path: '/engineering', element: <EngineeringPage /> },
    { path: '/reports', element: <ReportsPage /> },
    { path: '/settings', element: <SettingsPage /> },
    { path: '/settings/cad', element: <CADSettingsPage /> },
    { path: '/digital-twin', element: <DigitalTwinPage /> },
    { path: '/fire-alarm', element: <FireAlarmPage /> },
    { path: '/fire-alarm/designer', element: <FireAlarmDesigner /> },
    // V140 FIX: Add missing routes that Sidebar links to
    { path: '/fire-alarm-designer', element: <Navigate to="/fire-alarm/designer" /> },
    { path: '/elements', element: <Elements /> },
    { path: '/elements/:elementId', element: <ElementDetail /> },
    { path: '/connections', element: <Connections /> },
    { path: '/conflicts', element: <Conflicts /> },
    // V140 Phase 6: New routes for comprehensive API coverage
    { path: '/autocad', element: <AutoCADPage /> },
    { path: '/autocad/draw', element: <AutoCADDrawPage /> },
    { path: '/revit', element: <RevitPage /> },
    { path: '/revit/create', element: <RevitCreatePage /> },
    { path: '/revit/elements', element: <RevitElementsPage /> },
    { path: '/digital-twin/convert', element: <DigitalTwinConvertPage /> },
    { path: '/digital-twin/config', element: <DigitalTwinConfigPage /> },
    { path: '/digital-twin/history', element: <DigitalTwinHistoryPage /> },
  ];

  return (
    <div className="h-screen bg-slate-950 text-slate-100">
      <AppShell
        isConnected={connected}
        backendUrl={import.meta.env.VITE_API_URL || '/api/v1'}
        environment={import.meta.env.MODE || 'development'}
        currentLanguage={i18n.language}
        onLanguageChange={(lng: string) => i18n.changeLanguage(lng)}
        onHelpOpen={() => { setMagicHelpTopic(null); setHelpOpen(true); }}
      >
        <main className="flex-1 overflow-auto relative">
          <Routes>
            {routes.map((route) => (
              <Route key={route.path} path={route.path} element={route.element} />
            ))}
          </Routes>
          {/* V140 Phase 7: Contextual Help button — floats in top-right of every page */}
          <div className="fixed top-16 right-4 z-30">
            <ContextualHelpButton />
          </div>
        </main>
      </AppShell>
      {/* V140 Phase 7: Global Help Drawer with full tree + user guide */}
      <GlobalHelpDrawer
        open={helpOpen}
        onOpenChange={setHelpOpen}
        initialTopicId={magicHelpTopic}
      />
      <CommandPalette open={commandPaletteOpen} onOpenChange={setCommandPaletteOpen} />
      <OnboardingTour />
      <Toaster position="bottom-right" />
    </div>
  );
}

export default App;