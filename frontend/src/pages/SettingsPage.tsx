/**
 * SettingsPage.tsx - Application configuration
 * Stores settings in sessionStorage (SECURITY FIX: reduces XSS attack window vs localStorage)
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
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
  Eye,
  EyeOff,
  Loader2,
  Key,
} from 'lucide-react';

// ============================================================================
// Settings types
// ============================================================================

interface AppSettings {
  apiUrl: string;
  apiKey: string;
  engineeringStandard: 'IEC' | 'NEC';
  theme: 'dark' | 'light';
  autoRefreshInterval: number;
  maxRetries: number;
  requestTimeout: number;
}

const DEFAULT_SETTINGS: AppSettings = {
  apiUrl: '/api/v1',
  apiKey: '',
  engineeringStandard: 'IEC',
  theme: 'dark',
  autoRefreshInterval: 30,
  maxRetries: 3,
  requestTimeout: 15,
};

const SETTINGS_KEY = 'fireai_settings';

function loadSettings(): AppSettings {
  try {
    const stored = sessionStorage.getItem(SETTINGS_KEY);
    if (stored) {
      return { ...DEFAULT_SETTINGS, ...JSON.parse(stored) };
    }
  } catch {
    // Ignore parse errors
  }
  return DEFAULT_SETTINGS;
}

function saveSettings(settings: AppSettings): void {
  sessionStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
}

// ============================================================================
// SettingsPage Component
// ============================================================================

export function SettingsPage() {
  const { t, i18n } = useTranslation();
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [saved, setSaved] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);
  const [connectionTestResult, setConnectionTestResult] = useState<'success' | 'error' | null>(null);
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
    if (key === 'apiKey') {
      setConnectionTestResult(null);
    }
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
    setConnectionTestResult(null);
  };

  const handleTestConnection = async () => {
    setTestingConnection(true);
    setConnectionTestResult(null);
    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      if (settings.apiKey) {
        headers['X-API-Key'] = settings.apiKey;
      }
      const baseUrl = settings.apiUrl || '/api/v1';
      const response = await fetch(`${baseUrl}/health`, {
        method: 'GET',
        headers,
        signal: AbortSignal.timeout(10000),
      });
      if (response.ok) {
        setConnectionTestResult('success');
      } else {
        setConnectionTestResult('error');
      }
    } catch {
      setConnectionTestResult('error');
    } finally {
      setTestingConnection(false);
    }
  };

  const appVersion = import.meta.env.VITE_APP_VERSION || '1.0.0';

  return (
    <div className="flex-1 overflow-auto" aria-label={t('settings.title')}>
      <div className="p-6 max-w-4xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-100">{t('settings.title')}</h1>
            <p className="text-sm text-slate-400 mt-1">{t('settings.subtitle')}</p>
          </div>
          <div className="flex items-center gap-3">
            {saved && (
              <span className="flex items-center gap-1 text-sm text-emerald-400">
                <CheckCircle2 className="h-4 w-4" /> {t('settings.saved')}
              </span>
            )}
            <Button
              variant="outline"
              size="sm"
              className="border-slate-600 text-slate-300"
              onClick={handleReset}
            >
              <RotateCcw className="h-4 w-4 mr-1" /> {t('common.resetDefaults')}
            </Button>
            <Button
              size="sm"
              className="bg-red-600 hover:bg-red-700 text-white border-none"
              onClick={handleSave}
              disabled={!hasChanges}
            >
              <Save className="h-4 w-4 mr-1" /> {t('common.saveSettings')}
            </Button>
          </div>
        </div>

        {/* API Endpoint Configuration */}
        <Card className="border-slate-700 bg-slate-800/80">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Globe className="h-5 w-5 text-blue-400" />
              <CardTitle className="text-lg text-slate-100">{t('settings.apiConfiguration')}</CardTitle>
            </div>
            <CardDescription className="text-slate-400">
              {t('settings.apiConfigurationDesc')}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label className="text-slate-300" htmlFor="api-url">{t('settings.apiBaseUrl')}</Label>
              <Input
                id="api-url"
                value={settings.apiUrl}
                onChange={(e) => updateSetting('apiUrl', e.target.value)}
                className="bg-slate-900 border-slate-600 text-slate-100 font-mono"
                placeholder="e.g., http://localhost:8000/api"
                aria-describedby="api-url-hint"
              />
              <p id="api-url-hint" className="text-xs text-slate-500">
                {t('settings.apiBaseUrlHint')}
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-slate-300" htmlFor="request-timeout">{t('settings.requestTimeout')}</Label>
                <Input
                  id="request-timeout"
                  type="number"
                  min={5}
                  max={120}
                  value={settings.requestTimeout}
                  onChange={(e) => updateSetting('requestTimeout', parseInt(e.target.value) || 15)}
                  className="bg-slate-900 border-slate-600 text-slate-100"
                  aria-label={t('settings.requestTimeout')}
                />
              </div>
              <div className="space-y-2">
                <Label className="text-slate-300" htmlFor="max-retries">{t('settings.maxRetries')}</Label>
                <Input
                  id="max-retries"
                  type="number"
                  min={0}
                  max={10}
                  value={settings.maxRetries}
                  onChange={(e) => updateSetting('maxRetries', parseInt(e.target.value) || 3)}
                  className="bg-slate-900 border-slate-600 text-slate-100"
                  aria-label={t('settings.maxRetries')}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label className="text-slate-300" htmlFor="auto-refresh">{t('settings.autoRefreshInterval')}</Label>
              <Input
                id="auto-refresh"
                type="number"
                min={5}
                max={300}
                value={settings.autoRefreshInterval}
                onChange={(e) => updateSetting('autoRefreshInterval', parseInt(e.target.value) || 30)}
                className="bg-slate-900 border-slate-600 text-slate-100"
                aria-label={t('settings.autoRefreshInterval')}
              />
              <p className="text-xs text-slate-500">
                {t('settings.autoRefreshHint')}
              </p>
            </div>
          </CardContent>
        </Card>

        {/* API Key Configuration */}
        <Card className="border-slate-700 bg-slate-800/80">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Key className="h-5 w-5 text-amber-400" />
              <CardTitle className="text-lg text-slate-100">{t('settings.apiKey')}</CardTitle>
            </div>
            <CardDescription className="text-slate-400">
              {t('settings.apiKeyDesc')}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label className="text-slate-300" htmlFor="api-key">{t('settings.apiKey')}</Label>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Input
                    id="api-key"
                    type={showApiKey ? 'text' : 'password'}
                    value={settings.apiKey}
                    onChange={(e) => updateSetting('apiKey', e.target.value)}
                    className="bg-slate-900 border-slate-600 text-slate-100 font-mono pr-10"
                    placeholder="Enter your API key"
                    aria-describedby="api-key-hint"
                  />
                  <button
                    type="button"
                    onClick={() => setShowApiKey(!showApiKey)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200 p-1"
                    aria-label={showApiKey ? t('settings.hideApiKey') : t('settings.showApiKey')}
                  >
                    {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="border-slate-600 text-slate-300 shrink-0"
                  onClick={handleTestConnection}
                  disabled={testingConnection}
                >
                  {testingConnection ? (
                    <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                  ) : (
                    <Shield className="h-4 w-4 mr-1" />
                  )}
                  {t('common.testConnection')}
                </Button>
              </div>
              {connectionTestResult === 'success' && (
                <p className="text-xs text-emerald-400 flex items-center gap-1" role="status">
                  <CheckCircle2 className="h-3 w-3" /> {t('settings.connectionSuccessful')}
                </p>
              )}
              {connectionTestResult === 'error' && (
                <p className="text-xs text-red-400 flex items-center gap-1" role="alert">
                  {t('settings.connectionFailed')}
                </p>
              )}
              <p id="api-key-hint" className="text-xs text-slate-500">
                {t('settings.apiKeyHint')}
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Engineering Standard */}
        <Card className="border-slate-700 bg-slate-800/80">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-amber-400" />
              <CardTitle className="text-lg text-slate-100">{t('settings.engineeringStandard')}</CardTitle>
            </div>
            <CardDescription className="text-slate-400">
              {t('settings.engineeringStandardDesc')}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label className="text-slate-300">{t('settings.defaultStandard')}</Label>
              <Select
                value={settings.engineeringStandard}
                onValueChange={(v) => updateSetting('engineeringStandard', v as 'IEC' | 'NEC')}
              >
                <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-slate-800 border-slate-700">
                  <SelectItem value="IEC">{t('settings.iec')}</SelectItem>
                  <SelectItem value="NEC">{t('settings.nec')}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="p-3 rounded-lg bg-slate-900/50 border border-slate-700/50">
              {settings.engineeringStandard === 'IEC' ? (
                <div className="space-y-1">
                  <p className="text-xs font-medium text-slate-300">{t('settings.iecStandards')}</p>
                  <p className="text-xs text-slate-400">
                    {t('settings.iecDescription')}
                  </p>
                </div>
              ) : (
                <div className="space-y-1">
                  <p className="text-xs font-medium text-slate-300">{t('settings.necStandards')}</p>
                  <p className="text-xs text-slate-400">
                    {t('settings.necDescription')}
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
              <CardTitle className="text-lg text-slate-100">{t('settings.themePreferences')}</CardTitle>
            </div>
            <CardDescription className="text-slate-400">
              {t('settings.themePreferencesDesc')}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between p-3 rounded-lg bg-slate-900/50 border border-slate-700/50">
              <div>
                <p className="text-sm font-medium text-slate-200">{t('settings.darkMode')}</p>
                <p className="text-xs text-slate-400">
                  {settings.theme === 'dark'
                    ? t('settings.darkModeActive')
                    : t('settings.darkModeInactive')}
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
                <p className="text-xs text-slate-300 mt-2">{t('settings.dark')}</p>
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
                <p className={`text-xs mt-2 ${settings.theme === 'light' ? 'text-slate-700' : 'text-slate-400'}`}>{t('settings.light')}</p>
              </button>
            </div>
          </CardContent>
        </Card>

        {/* Language */}
        <Card className="border-slate-700 bg-slate-800/80">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Globe className="h-5 w-5 text-blue-400" />
              <CardTitle className="text-lg text-slate-100">{t('settings.language')}</CardTitle>
            </div>
            <CardDescription className="text-slate-400">
              {t('settings.languageDesc')}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label className="text-slate-300" htmlFor="language-select">{t('settings.language')}</Label>
              <Select
                value={i18n.language?.startsWith('ar') ? 'ar' : 'en'}
                onValueChange={(lng) => {
                  i18n.changeLanguage(lng);
                  document.documentElement.dir = lng === 'ar' ? 'rtl' : 'ltr';
                  document.documentElement.lang = lng;
                }}
              >
                <SelectTrigger id="language-select" className="bg-slate-900 border-slate-600 text-slate-100">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-slate-800 border-slate-700">
                  <SelectItem value="en">{t('settings.english')}</SelectItem>
                  <SelectItem value="ar">{t('settings.arabic')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        {/* System Info */}
        <Card className="border-slate-700 bg-slate-800/80">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Settings className="h-5 w-5 text-slate-400" />
              <CardTitle className="text-lg text-slate-100">{t('settings.systemInfo')}</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <p className="text-xs text-slate-500 uppercase tracking-wider">Version</p>
                <Separator className="my-1 bg-slate-700" />
                <p className="font-mono text-slate-200">{appVersion}</p>
              </div>
              <div>
                <p className="text-xs text-slate-500 uppercase tracking-wider">Platform</p>
                <Separator className="my-1 bg-slate-700" />
                <p className="font-mono text-slate-200">FireAI Revit</p>
              </div>
              <div>
                <p className="text-xs text-slate-500 uppercase tracking-wider">Storage</p>
                <Separator className="my-1 bg-slate-700" />
                <p className="font-mono text-slate-200">sessionStorage</p>
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
