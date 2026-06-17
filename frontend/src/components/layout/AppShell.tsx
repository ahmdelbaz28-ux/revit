import React from "react";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import StatusBar from "./StatusBar";

interface AppShellProps {
  children: React.ReactNode;
  isConnected: boolean;
  backendUrl: string;
  environment: string;
  onHelpOpen: () => void;
  currentLanguage: string;
  onLanguageChange: (lang: string) => void;
}

const AppShell: React.FC<AppShellProps> = ({
  children,
  isConnected,
  backendUrl,
  environment,
  onHelpOpen,
  currentLanguage,
  onLanguageChange,
}) => {
  const isRTL = document.documentElement.dir === "rtl";

  return (
    <div
      className="h-screen w-screen flex overflow-hidden bg-slate-950 relative"
      dir={isRTL ? "rtl" : "ltr"}
    >
      <div className="absolute inset-0 -z-10 overflow-hidden pointer-events-none">
        <div className="absolute inset-0 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 animate-gradient-shift" />
        <div className="absolute inset-0 opacity-30">
          <div className="absolute top-0 left-0 w-96 h-96 bg-red-500/10 rounded-full blur-3xl animate-pulse-slow" />
          <div className="absolute bottom-0 right-0 w-96 h-96 bg-orange-500/10 rounded-full blur-3xl animate-pulse-slower" />
        </div>
      </div>

      <Sidebar />

      <div className="flex-1 flex flex-col min-w-0">
        <TopBar
          isConnected={isConnected}
          onHelpOpen={onHelpOpen}
          currentLanguage={currentLanguage}
          onLanguageChange={onLanguageChange}
        />

        <main className="flex-1 overflow-auto bg-slate-950 relative">
          <div className="absolute inset-0 opacity-20 pointer-events-none">
            <div className="w-full h-full bg-[linear-gradient(rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:24px_24px]" />
          </div>
          <div className="relative z-10">{children}</div>
        </main>

        <StatusBar
          backendUrl={backendUrl}
          isConnected={isConnected}
          environment={environment}
        />
      </div>
    </div>
  );
};

export default AppShell;