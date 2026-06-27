/**
 * DigitalTwinConfigPage.tsx — Config editor for Digital Twin settings
 */
import { ConfigEditor } from '@/components/shared/ConfigEditor';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { digitalTwinService } from '@/services/digitalTwinService';
import { useEffect, useState } from 'react';

export function DigitalTwinConfigPage() {
  const [mappings, setMappings] = useState<unknown[]>([]);

  useEffect(() => {
    const fetchMappings = async () => {
      try {
        const m = await digitalTwinService.getMappings();
        setMappings(Array.isArray(m) ? m : []);
      } catch {
        setMappings([]);
      }
    };
    fetchMappings();
  }, []);

  return (
    <div className="flex-1 overflow-auto p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Digital Twin — Configuration</h1>
        <p className="text-sm text-slate-400 mt-1">Edit conversion settings and view available mappings</p>
      </div>
      <ConfigEditor
        title="Conversion Configuration"
        description="JSON configuration for the digital twin conversion engine"
        loadConfig={async () => (await digitalTwinService.getConfig()) as Record<string, unknown>}
        saveConfig={async (config) => { await digitalTwinService.setConfig(config); }}
      />
      <Card className="border-slate-700 bg-slate-800/80">
        <CardHeader>
          <CardTitle className="text-slate-100">Available Mappings ({mappings.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {mappings.length === 0 ? (
            <p className="text-slate-500 text-sm">No mappings available</p>
          ) : (
            <div className="space-y-2">
              {mappings.map((m, i) => (
                <div key={i} className="flex items-center gap-2 p-2 bg-slate-900/50 rounded border border-slate-700">
                  <Badge variant="outline" className="border-slate-600 text-slate-300">
                    {typeof m === 'object' && m ? String((m as Record<string, unknown>).name || `Mapping ${i + 1}`) : `Mapping ${i + 1}`}
                  </Badge>
                  <pre className="text-xs text-slate-500 flex-1 overflow-auto">{JSON.stringify(m, null, 2)}</pre>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
