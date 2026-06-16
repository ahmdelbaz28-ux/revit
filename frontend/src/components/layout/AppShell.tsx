import { Outlet } from 'react-router-dom';
import { TopBar } from './TopBar';
import { Sidebar } from './Sidebar';
import { StatusBar } from './StatusBar';

export function AppShell() {
  return (
    <div className="flex h-screen w-full overflow-hidden bg-slate-950 text-slate-100" dir={document.documentElement.dir || 'ltr'}>
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="min-h-0 flex-1 overflow-auto bg-[radial-gradient(circle_at_top_left,rgba(239,68,68,0.08),transparent_28rem),linear-gradient(180deg,#0f172a_0%,#020617_100%)]">
          <Outlet />
        </main>
        <StatusBar />
      </div>
    </div>
  );
}
