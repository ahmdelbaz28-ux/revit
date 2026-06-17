import React, { useEffect, useState } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Toaster } from 'sonner';
import { useHealth } from '@/hooks/useApi';
import { AppShell } from '@/components/layout/AppShell';
import { SmartHelpDrawer } from '@/components/help/SmartHelpDrawer';
import { CommandPalette } from '@/components/command/CommandPalette';
import { OnboardingTour } from '@/components/onboarding/OnboardingTour';
import { DashboardPage } from './pages/DashboardPage';
import { ProjectsPage } from './pages/ProjectsPage';
import { EngineeringPage } from './pages/EngineeringPage';
import { ReportsPage } from './pages/ReportsPage';
import { SettingsPage } from './pages/SettingsPage';
import { FireAlarmPage } from './pages/FireAlarmPage';
import { FireAlarmDesigner } from './components/mockups/engineering/FireAlarmDesigner';
import { DigitalTwinPage } from './pages/DigitalTwinPage';
import { CADSettingsPage } from './pages/CADSettingsPage';
import './i18n';
import './styles/globals.css';
import './styles/typography.css';

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
  ];

  return (
    <div className="h-screen bg-slate-950 text-slate-100">
      <AppShell
        isConnected={connected}
        backendUrl={import.meta.env.VITE_API_URL || '/api/v1'}
        environment={import.meta.env.MODE || 'development'}
        currentLanguage={i18n.language}
        onLanguageChange={(lng) => i18n.changeLanguage(lng)}
        onHelpOpen={() => setHelpOpen(true)}
      >
        <main className="flex-1 overflow-auto">
          <Routes>
            {routes.map((route) => (
              <Route key={route.path} path={route.path} element={route.element} />
            ))}
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