/**
 * ConnectionStatus.tsx — Connection status indicator
 */
import { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { autocadService } from '@/services/autocadService';
import { revitService } from '@/services/revitService';

type Status = 'connected' | 'disconnected' | 'checking';

interface StatusState {
  autocad: Status;
  revit: Status;
}

export function ConnectionStatus() {
  const [status, setStatus] = useState<StatusState>({
    autocad: 'checking',
    revit: 'checking',
  });

  useEffect(() => {
    const checkStatus = async () => {
      try {
        await autocadService.getStatus();
        setStatus((p) => ({ ...p, autocad: 'connected' }));
      } catch {
        setStatus((p) => ({ ...p, autocad: 'disconnected' }));
      }
      try {
        await revitService.getStatus();
        setStatus((p) => ({ ...p, revit: 'connected' }));
      } catch {
        setStatus((p) => ({ ...p, revit: 'disconnected' }));
      }
    };
    checkStatus();
    const interval = setInterval(checkStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  const colors: Record<Status, string> = {
    connected: 'bg-emerald-500',
    disconnected: 'bg-slate-500',
    checking: 'bg-amber-500 animate-pulse',
  };
  const labels: Record<Status, string> = {
    connected: 'Connected',
    disconnected: 'Offline',
    checking: 'Checking...',
  };

  return (
    <div className="flex items-center gap-4">
      <div className="flex items-center gap-2">
        <span className={`h-2.5 w-2.5 rounded-full ${colors[status.autocad]}`} />
        <span className="text-xs text-slate-400">AutoCAD</span>
        <Badge variant="outline" className="text-xs border-slate-600 text-slate-300">
          {labels[status.autocad]}
        </Badge>
      </div>
      <div className="flex items-center gap-2">
        <span className={`h-2.5 w-2.5 rounded-full ${colors[status.revit]}`} />
        <span className="text-xs text-slate-400">Revit</span>
        <Badge variant="outline" className="text-xs border-slate-600 text-slate-300">
          {labels[status.revit]}
        </Badge>
      </div>
    </div>
  );
}
