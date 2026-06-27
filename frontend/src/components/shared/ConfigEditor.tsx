/**
 * ConfigEditor.tsx — JSON config editor with validation
 */
import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Save, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';

interface ConfigEditorProps {
  title: string;
  description?: string;
  loadConfig: () => Promise<Record<string, unknown>>;
  saveConfig: (config: Record<string, unknown>) => Promise<void>;
}

export function ConfigEditor({ title, description, loadConfig, saveConfig }: ConfigEditorProps) {
  const [configText, setConfigText] = useState('');
  const [original, setOriginal] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const config = await loadConfig();
        const text = JSON.stringify(config, null, 2);
        setConfigText(text);
        setOriginal(text);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load config');
        setConfigText('{}');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [loadConfig]);

  const validate = (): Record<string, unknown> | null => {
    try {
      const parsed = JSON.parse(configText);
      setError(null);
      return parsed;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Invalid JSON');
      return null;
    }
  };

  const handleSave = async () => {
    const parsed = validate();
    if (!parsed) {
      toast.error('Cannot save: invalid JSON');
      return;
    }
    setSaving(true);
    try {
      await saveConfig(parsed);
      setOriginal(configText);
      toast.success('Configuration saved successfully');
    } catch (err) {
      toast.error(`Save failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setSaving(false);
    }
  };

  const hasChanges = configText !== original;

  return (
    <Card className="border-slate-700 bg-slate-800/80">
      <CardHeader>
        <CardTitle className="text-slate-100">{title}</CardTitle>
        {description && <CardDescription className="text-slate-400">{description}</CardDescription>}
      </CardHeader>
      <CardContent className="space-y-3">
        {loading ? (
          <div className="h-64 bg-slate-900 rounded animate-pulse" />
        ) : (
          <>
            <div className="flex items-center gap-2">
              {error ? (
                <Badge variant="destructive" className="gap-1">
                  <AlertCircle className="h-3 w-3" /> Invalid JSON
                </Badge>
              ) : (
                <Badge variant="outline" className="border-emerald-600/30 text-emerald-400 gap-1">
                  <CheckCircle2 className="h-3 w-3" /> Valid JSON
                </Badge>
              )}
              {hasChanges && (
                <Badge variant="outline" className="border-amber-600/30 text-amber-400">
                  Unsaved changes
                </Badge>
              )}
            </div>
            <Textarea
              value={configText}
              onChange={(e) => {
                setConfigText(e.target.value);
                validate();
              }}
              className="font-mono text-sm bg-slate-900 border-slate-700 text-slate-100 min-h-[300px]"
              spellCheck={false}
            />
            {error && (
              <p className="text-xs text-red-400 font-mono">{error}</p>
            )}
            <Button
              onClick={handleSave}
              disabled={!hasChanges || saving || !!error}
              className="bg-orange-600 hover:bg-orange-700 text-white"
            >
              {saving ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Save className="h-4 w-4 mr-2" />
                  Save Configuration
                </>
              )}
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}
