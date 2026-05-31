/**
 * SettingsPage.tsx - Application configuration
 * Stores settings in localStorage
 */
import { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import {
  Settings,
  Globe,
  Shield,
  Palette,
  Save,
  RotateCcw,
  CheckCircle2,
} from 'lucide-react';

// ============================================================================
// Settings types
// ============================================================================

interface AppSettings {
  apiUrl: string;
  engineeringStandard: 'IEC' | 'NEC';
  theme: 'dark' | 'light';
  autoRefreshInterval: number;
  maxRetries: number;
  requestTimeout: number;
}

const DEFAULT_SETTINGS: AppSettings = {
  apiUrl: '/api',
  engineeringStandard: 'IEC',
  theme: 'dark',
  autoRefreshInterval: 30,
  maxRetries: 3,
  requestTimeout: 15,
};

const SETTINGS_KEY = 'fireai_settings';

function loadSettings(): AppSettings {
  try {
    const stored = localStorage.getItem(SETTINGS_KEY);
    if (stored) {
      return { ...DEFAULT_SETTINGS, ...JSON.parse(stored) };
    }
  } catch {
    // Ignore parse errors
  }
  return DEFAULT_SETTINGS;
}

function saveSettings(settings: AppSettings): void {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
}

// ============================================================================
// SettingsPage Component
// ============================================================================

export function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [saved, setSaved] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const savedTimerRef = useRef<ReturnType<typeof setTimeout>>();

  // Load settings on mount, cleanup timer on unmount
  useEffect(() => {
    setSettings(loadSettings());
    return () => { if (savedTimerRef.current) clearTimeout(savedTimerRef.current); };
  }, []);

  const updateSetting = <K extends keyof AppSettings>(key: K, value: AppSettings[K]) => {
    setSettings(prev => ({ ...prev, [key]: value }));
    setHasChanges(true);
    setSaved(false);
  };

  const handleSave = () => {
    saveSettings(settings);
    setSaved(true);
    setHasChanges(false);

    // Apply theme
    if (settings.theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }

    // Clear saved indicator after a few seconds
    if (savedTimerRef.current) clearTimeout(savedTimerRef.current);
    savedTimerRef.current = setTimeout(() => setSaved(false), 3000);
  };

  const handleReset = () => {
    setSettings(DEFAULT_SETTINGS);
    setHasChanges(true);
    setSaved(false);
  };

  return (
    <div className="flex-1 overflow-auto">
      <div className="p-6 max-w-4xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-100">Settings</h1>
            <p className="text-sm text-slate-400 mt-1">Application configuration</p>
          </div>
          <div className="flex items-center gap-3">
            {saved && (
              <span className="flex items-center gap-1 text-sm text-emerald-400">
                <CheckCircle2 className="h-4 w-4" /> Saved
              </span>
            )}
            <Button
              variant="outline"
              size="sm"
              className="border-slate-600 text-slate-300"
              onClick={handleReset}
            >
              <RotateCcw className="h-4 w-4 mr-1" /> Reset Defaults
            </Button>
            <Button
              size="sm"
              className="bg-red-600 hover:bg-red-700 text-white border-none"
              onClick={handleSave}
              disabled={!hasChanges}
            >
              <Save className="h-4 w-4 mr-1" /> Save Settings
            </Button>
          </div>
        </div>

        {/* API Endpoint Configuration */}
        <Card className="border-slate-700 bg-slate-800/80">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Globe className="h-5 w-5 text-blue-400" />
              <CardTitle className="text-lg text-slate-100">API Configuration</CardTitle>
            </div>
            <CardDescription className="text-slate-400">
              Configure the backend API endpoint
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label className="text-slate-300">API Base URL</Label>
              <Input
                value={settings.apiUrl}
                onChange={(e) => updateSetting('apiUrl', e.target.value)}
                className="bg-slate-900 border-slate-600 text-slate-100 font-mono"
                placeholder="e.g., http://localhost:8000/api"
              />
              <p className="text-xs text-slate-500">
                The base URL for the Digital Twin API. Default: /api (relative, uses same host)
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-slate-300">Request Timeout (seconds)</Label>
                <Input
                  type="number"
                  min={5}
                  max={120}
                  value={settings.requestTimeout}
                  onChange={(e) => updateSetting('requestTimeout', parseInt(e.target.value) || 15)}
                  className="bg-slate-900 border-slate-600 text-slate-100"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-slate-300">Max Retries</Label>
                <Input
                  type="number"
                  min={0}
                  max={10}
                  value={settings.maxRetries}
                  onChange={(e) => updateSetting('maxRetries', parseInt(e.target.value) || 3)}
                  className="bg-slate-900 border-slate-600 text-slate-100"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label className="text-slate-300">Auto-refresh Interval (seconds)</Label>
              <Input
                type="number"
                min={5}
                max={300}
                value={settings.autoRefreshInterval}
                onChange={(e) => updateSetting('autoRefreshInterval', parseInt(e.target.value) || 30)}
                className="bg-slate-900 border-slate-600 text-slate-100"
              />
              <p className="text-xs text-slate-500">
                How often dashboard data refreshes automatically (0 = disabled)
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Engineering Standard */}
        <Card className="border-slate-700 bg-slate-800/80">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-amber-400" />
              <CardTitle className="text-lg text-slate-100">Engineering Standard</CardTitle>
            </div>
            <CardDescription className="text-slate-400">
              Default standard for engineering calculations
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label className="text-slate-300">Default Standard</Label>
              <Select
                value={settings.engineeringStandard}
                onValueChange={(v) => updateSetting('engineeringStandard', v as 'IEC' | 'NEC')}
              >
                <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-slate-800 border-slate-700">
                  <SelectItem value="IEC">IEC (International Electrotechnical Commission)</SelectItem>
                  <SelectItem value="NEC">NEC (National Electrical Code - NFPA 70)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="p-3 rounded-lg bg-slate-900/50 border border-slate-700/50">
              {settings.engineeringStandard === 'IEC' ? (
                <div className="space-y-1">
                  <p className="text-xs font-medium text-slate-300">IEC Standards</p>
                  <p className="text-xs text-slate-400">
                    Uses IEC 60364 for low-voltage installations, IEC 60909 for short circuit calculations, 
                    and IEC 60502 for cable sizing. Voltage levels: 230/400V.
                  </p>
                </div>
              ) : (
                <div className="space-y-1">
                  <p className="text-xs font-medium text-slate-300">NEC Standards</p>
                  <p className="text-xs text-slate-400">
                    Uses NFPA 70 (NEC) for electrical installations, IEEE 1584 for arc flash, 
                    and NEMA standards for fire alarm. Voltage levels: 120/208V, 277/480V.
                  </p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Theme Preferences */}
        <Card className="border-slate-700 bg-slate-800/80">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Palette className="h-5 w-5 text-purple-400" />
              <CardTitle className="text-lg text-slate-100">Theme Preferences</CardTitle>
            </div>
            <CardDescription className="text-slate-400">
              Customize the application appearance
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between p-3 rounded-lg bg-slate-900/50 border border-slate-700/50">
              <div>
                <p className="text-sm font-medium text-slate-200">Dark Mode</p>
                <p className="text-xs text-slate-400">
                  {settings.theme === 'dark'
                    ? 'Dark theme is currently active'
                    : 'Switch to dark theme for reduced eye strain'}
                </p>
              </div>
              <Switch
                checked={settings.theme === 'dark'}
                onCheckedChange={(checked) => updateSetting('theme', checked ? 'dark' : 'light')}
              />
            </div>

            {/* Preview */}
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={() => updateSetting('theme', 'dark')}
                className={`p-4 rounded-lg border-2 transition-colors ${
                  settings.theme === 'dark'
                    ? 'border-red-500 bg-slate-900'
                    : 'border-slate-700 bg-slate-900/50 hover:border-slate-500'
                }`}
              >
                <div className="flex flex-col gap-2">
                  <div className="h-2 w-12 rounded bg-slate-600" />
                  <div className="h-2 w-8 rounded bg-slate-700" />
                  <div className="flex gap-1 mt-1">
                    <div className="h-4 w-4 rounded bg-red-600/30" />
                    <div className="h-4 w-4 rounded bg-blue-600/30" />
                    <div className="h-4 w-4 rounded bg-emerald-600/30" />
                  </div>
                </div>
                <p className="text-xs text-slate-300 mt-2">Dark</p>
              </button>
              <button
                onClick={() => updateSetting('theme', 'light')}
                className={`p-4 rounded-lg border-2 transition-colors ${
                  settings.theme === 'light'
                    ? 'border-red-500 bg-white'
                    : 'border-slate-700 bg-white/10 hover:border-slate-500'
                }`}
              >
                <div className="flex flex-col gap-2">
                  <div className="h-2 w-12 rounded bg-slate-300" />
                  <div className="h-2 w-8 rounded bg-slate-200" />
                  <div className="flex gap-1 mt-1">
                    <div className="h-4 w-4 rounded bg-red-100" />
                    <div className="h-4 w-4 rounded bg-blue-100" />
                    <div className="h-4 w-4 rounded bg-emerald-100" />
                  </div>
                </div>
                <p className={`text-xs mt-2 ${settings.theme === 'light' ? 'text-slate-700' : 'text-slate-400'}`}>Light</p>
              </button>
            </div>
          </CardContent>
        </Card>

        {/* System Info */}
        <Card className="border-slate-700 bg-slate-800/80">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Settings className="h-5 w-5 text-slate-400" />
              <CardTitle className="text-lg text-slate-100">System Information</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <p className="text-xs text-slate-500 uppercase tracking-wider">Version</p>
                <Separator className="my-1 bg-slate-700" />
                <p className="font-mono text-slate-200">1.0.0</p>
              </div>
              <div>
                <p className="text-xs text-slate-500 uppercase tracking-wider">Platform</p>
                <Separator className="my-1 bg-slate-700" />
                <p className="font-mono text-slate-200">FireAI Revit</p>
              </div>
              <div>
                <p className="text-xs text-slate-500 uppercase tracking-wider">Storage</p>
                <Separator className="my-1 bg-slate-700" />
                <p className="font-mono text-slate-200">localStorage</p>
              </div>
              <div>
                <p className="text-xs text-slate-500 uppercase tracking-wider">Config Key</p>
                <Separator className="my-1 bg-slate-700" />
                <p className="font-mono text-slate-200">{SETTINGS_KEY}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
