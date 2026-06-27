/**
 * DigitalTwinHistoryPage.tsx — Full-page conversion history with rollback
 */
import { HistoryTimeline } from '@/components/shared/HistoryTimeline';

export function DigitalTwinHistoryPage() {
  return (
    <div className="flex-1 overflow-auto p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Digital Twin — History</h1>
        <p className="text-sm text-slate-400 mt-1">View conversion history and rollback to previous versions</p>
      </div>
      <HistoryTimeline />
    </div>
  );
}
