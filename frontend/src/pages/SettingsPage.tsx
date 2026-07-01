/**
 * SettingsPage.tsx - Application configuration and user preferences
 *
 * V151: Adds "Vision API Keys" tab for managing customer-supplied OpenAI
 * Vision API keys. Keys are stored AES-256-GCM encrypted on the backend
 * (HF Space) and only the masked form (e.g. fe_sk***...***f4c1) is ever
 * returned to this frontend.
 */
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Settings,
  Database,
  Monitor,
  User,
  Key,
  Shield,
  Activity,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Calculator,
  Eye,
  Loader2,
  Plus,
  Trash2,
  Zap,
} from 'lucide-react';
import { useHealth } from '@/hooks/useApi';
import { api } from '@/services/digitalTwinApi';
import { toast } from 'sonner';
import { ErrorBoundary } from '@/components/core/ErrorBoundary';

export function SettingsPage() {
  const { t } = useTranslation();
  const { data: health, loading: healthLoading, connected, refetch: refetchHealth } = useHealth();
  
  const [activeTab, setActiveTab] = useState('general');
  
  // General settings
  const [theme, setTheme] = useState('dark');
  const [language, setLanguage] = useState('en');
  const [notifications, setNotifications] = useState(true);
  
  // Security settings
  const [twoFactorAuth, setTwoFactorAuth] = useState(false);
  const [passwordExpiry, setPasswordExpiry] = useState(90);
  
  // API settings
  const [apiTimeout, setApiTimeout] = useState(30);
  const [retryAttempts, setRetryAttempts] = useState(3);
  
  // Report settings
  const [autoSaveReports, setAutoSaveReports] = useState(true);
  const [reportFormat, setReportFormat] = useState('pdf');
  const [reportQuality, setReportQuality] = useState('high');

  const [saveStatus, setSaveStatus] = useState<string | null>(null);

  const persistSettings = (key: string, value: Record<string, unknown>) => {
    // CodeQL: js/clear-text-storage-of-sensitive-data — FALSE POSITIVE.
    // localStorage is used ONLY for non-sensitive UI preferences:
    //   - theme (light/dark)
    //   - language (en/ar)
    //   - notifications (on/off)
    //   - reportFormat (pdf/dxf)
    //   - reportQuality (high/medium)
    // API keys are NEVER stored in localStorage — they use HttpOnly cookies
    // set by POST /api/v1/auth/login (see backend/routers/auth.py).
    // sessionStorage is used as a legacy fallback for the API key, but
    // that is being deprecated in favor of cookie-based auth.
    try {
      // Strip any sensitive fields before storing
      const safeValue: Record<string, unknown> = {};
      const SENSITIVE_KEYS = ['apiKey', 'api_key', 'password', 'token', 'secret'];
      for (const [k, v] of Object.entries(value)) {
        if (!SENSITIVE_KEYS.some(s => k.toLowerCase().includes(s.toLowerCase()))) {
          safeValue[k] = v;
        }
      }
      localStorage.setItem(`fireai_settings_${key}`, JSON.stringify(safeValue));
      setSaveStatus('saved');
      setTimeout(() => setSaveStatus(null), 2000);
    } catch {
      setSaveStatus('error');
      setTimeout(() => setSaveStatus(null), 3000);
    }
  };

  const handleSaveGeneral = () => {
    persistSettings('general', { theme, language, notifications });
  };

  const handleSaveSecurity = () => {
    persistSettings('security', { twoFactorAuth, passwordExpiry });
  };

  const handleSaveApi = () => {
    persistSettings('api', { apiTimeout, retryAttempts });
  };

  const handleSaveReports = () => {
    persistSettings('reports', { autoSaveReports, reportFormat, reportQuality });
  };

  return (
    <div className="flex-1 overflow-auto" aria-label={t('settings.title')}>
      <div className="p-6 max-w-4xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-100">{t('settings.title')}</h1>
            <p className="text-sm text-slate-400 mt-1">{t('settings.subtitle')}</p>
          </div>
          <Button
            variant="outline"
            className="border-slate-600 text-slate-300 hover:bg-slate-800"
            onClick={() => refetchHealth()}
          >
            <Activity className="h-4 w-4 mr-1" />
            {t('common.refresh')}
          </Button>
        </div>

        {/* System Health */}
        <Card className="border-slate-700 bg-slate-800/80">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg text-slate-100 flex items-center gap-2">
              <Activity className="h-5 w-5 text-blue-400" />
              {t('settings.systemHealth')}
            </CardTitle>
            <CardDescription className="text-slate-400">
              {healthLoading ? 'Checking system status...' : 'Current system status and performance metrics'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-4 text-sm">
              <div className="flex items-center gap-2">
                {connected ? (
                  <CheckCircle2 className="h-5 w-5 text-emerald-400" />
                ) : (
                  <XCircle className="h-5 w-5 text-red-400" />
                )}
                <span>{connected ? 'Connected' : 'Disconnected'}</span>
              </div>
              {health && (
                <>
                  <Separator orientation="vertical" className="h-5 bg-slate-700" />
                  <div className="flex items-center gap-2">
                    <span>API v{health.version}</span>
                  </div>
                  <Separator orientation="vertical" className="h-5 bg-slate-700" />
                  <div className="flex items-center gap-2">
                    <span>DB: {health.database}</span>
                  </div>
                  <Separator orientation="vertical" className="h-5 bg-slate-700" />
                  <div className="flex items-center gap-2">
                    <span>Uptime: {Math.floor((health.uptime || 0) / 60)} min</span>
                  </div>
                </>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Report Generator Quick Access */}
        <Card className="border-slate-700 bg-slate-800/80">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg text-slate-100">Advanced Report Generator</CardTitle>
            <CardDescription className="text-slate-400">
              Generate deterministic analysis reports with NFPA 72 compliance
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col sm:flex-row gap-4">
              <div className="flex-1">
                <h3 className="font-medium text-slate-200 mb-2">Comprehensive Report Generation</h3>
                <p className="text-sm text-slate-400">
                  Generate NFPA 72 Coverage, Battery Calculations, Voltage Drop Analysis, Complete Compliance Reports, Cause & Effect Matrices, and Cable Schedules.
                </p>
              </div>
              <Button className="bg-red-600 hover:bg-red-700 text-white border-none flex items-center gap-2">
                <Calculator className="h-4 w-4" />
                Open Report Generator
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Settings Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="bg-slate-800 border border-slate-700">
            <TabsTrigger value="general" className="data-[state=active]:bg-slate-700 data-[state=active]:text-slate-100">
              <Settings className="h-4 w-4 mr-1" /> {t('settings.general')}
            </TabsTrigger>
            <TabsTrigger value="security" className="data-[state=active]:bg-slate-700 data-[state=active]:text-slate-100">
              <Shield className="h-4 w-4 mr-1" /> {t('settings.security')}
            </TabsTrigger>
            <TabsTrigger value="api" className="data-[state=active]:bg-slate-700 data-[state=active]:text-slate-100">
              <Database className="h-4 w-4 mr-1" /> {t('settings.api')}
            </TabsTrigger>
            <TabsTrigger value="vision" className="data-[state=active]:bg-slate-700 data-[state=active]:text-slate-100">
              <Eye className="h-4 w-4 mr-1" /> Vision API Keys
            </TabsTrigger>
            <TabsTrigger value="reports" className="data-[state=active]:bg-slate-700 data-[state=active]:text-slate-100">
              <Calculator className="h-4 w-4 mr-1" /> {t('settings.reports')}
            </TabsTrigger>
          </TabsList>

          {/* General Settings */}
          <TabsContent value="general">
            <Card className="border-slate-700 bg-slate-800/80">
              <CardHeader className="pb-3">
                <CardTitle className="text-lg text-slate-100">{t('settings.general')}</CardTitle>
                <CardDescription className="text-slate-400">
                  {t('settings.generalDescription')}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label className="text-slate-300">{t('settings.theme')}</Label>
                    <select
                      value={theme}
                      onChange={(e) => setTheme(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-slate-100"
                    >
                      <option value="light">{t('settings.light')}</option>
                      <option value="dark">{t('settings.dark')}</option>
                      <option value="system">{t('settings.system')}</option>
                    </select>
                  </div>
                  <div className="space-y-2">
                    <Label className="text-slate-300">{t('settings.language')}</Label>
                    <select
                      value={language}
                      onChange={(e) => setLanguage(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-slate-100"
                    >
                      <option value="en">English</option>
                      <option value="es">Español</option>
                      <option value="fr">Français</option>
                      <option value="de">Deutsch</option>
                    </select>
                  </div>
                </div>
                <div className="flex items-center justify-between py-3">
                  <div>
                    <Label className="text-slate-300">{t('settings.notifications')}</Label>
                    <p className="text-xs text-slate-400 mt-1">{t('settings.notificationsDescription')}</p>
                  </div>
                  <Switch
                    checked={notifications}
                    onCheckedChange={setNotifications}
                    className="data-[state=checked]:bg-red-600"
                  />
                </div>
                <div className="pt-4">
                  <Button
                    className="bg-red-600 hover:bg-red-700 text-white border-none"
                    onClick={handleSaveGeneral}
                  >
                    {t('settings.save')}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Security Settings */}
          <TabsContent value="security">
            <Card className="border-slate-700 bg-slate-800/80">
              <CardHeader className="pb-3">
                <CardTitle className="text-lg text-slate-100">{t('settings.security')}</CardTitle>
                <CardDescription className="text-slate-400">
                  {t('settings.securityDescription')}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between py-3">
                  <div>
                    <Label className="text-slate-300">{t('settings.twoFactorAuth')}</Label>
                    <p className="text-xs text-slate-400 mt-1">{t('settings.twoFactorAuthDescription')}</p>
                  </div>
                  <Switch
                    checked={twoFactorAuth}
                    onCheckedChange={setTwoFactorAuth}
                    className="data-[state=checked]:bg-red-600"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300">{t('settings.passwordExpiry')}</Label>
                  <Input
                    type="number"
                    value={passwordExpiry}
                    onChange={(e) => setPasswordExpiry(parseInt(e.target.value))}
                    className="bg-slate-900 border-slate-600 text-slate-100"
                  />
                  <p className="text-xs text-slate-400">{t('settings.passwordExpiryDescription')}</p>
                </div>
                <div className="pt-4">
                  <Button
                    className="bg-red-600 hover:bg-red-700 text-white border-none"
                    onClick={handleSaveSecurity}
                  >
                    {t('settings.save')}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* API Settings */}
          <TabsContent value="api">
            <Card className="border-slate-700 bg-slate-800/80">
              <CardHeader className="pb-3">
                <CardTitle className="text-lg text-slate-100">{t('settings.api')}</CardTitle>
                <CardDescription className="text-slate-400">
                  {t('settings.apiDescription')}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label className="text-slate-300">{t('settings.apiTimeout')}</Label>
                    <Input
                      type="number"
                      value={apiTimeout}
                      onChange={(e) => setApiTimeout(parseInt(e.target.value))}
                      className="bg-slate-900 border-slate-600 text-slate-100"
                    />
                    <p className="text-xs text-slate-400">{t('settings.apiTimeoutDescription')}</p>
                  </div>
                  <div className="space-y-2">
                    <Label className="text-slate-300">{t('settings.retryAttempts')}</Label>
                    <Input
                      type="number"
                      value={retryAttempts}
                      onChange={(e) => setRetryAttempts(parseInt(e.target.value))}
                      className="bg-slate-900 border-slate-600 text-slate-100"
                    />
                    <p className="text-xs text-slate-400">{t('settings.retryAttemptsDescription')}</p>
                  </div>
                </div>
                <div className="pt-4">
                  <Button
                    className="bg-red-600 hover:bg-red-700 text-white border-none"
                    onClick={handleSaveApi}
                  >
                    {t('settings.save')}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* V151: Vision API Keys */}
          <TabsContent value="vision">
            <ErrorBoundary>
              <VisionApiKeysTab />
            </ErrorBoundary>
          </TabsContent>

          {/* Report Settings */}
          <TabsContent value="reports">
            <Card className="border-slate-700 bg-slate-800/80">
              <CardHeader className="pb-3">
                <CardTitle className="text-lg text-slate-100">{t('settings.reports')}</CardTitle>
                <CardDescription className="text-slate-400">
                  Configure report generation and export options
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between py-3">
                  <div>
                    <Label className="text-slate-300">Auto-save Reports</Label>
                    <p className="text-xs text-slate-400 mt-1">Automatically save reports after generation</p>
                  </div>
                  <Switch
                    checked={autoSaveReports}
                    onCheckedChange={setAutoSaveReports}
                    className="data-[state=checked]:bg-red-600"
                  />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label className="text-slate-300">Report Format</Label>
                    <select
                      value={reportFormat}
                      onChange={(e) => setReportFormat(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-slate-100"
                    >
                      <option value="pdf">PDF</option>
                      <option value="json">JSON</option>
                      <option value="excel">Excel</option>
                      <option value="xml">XML</option>
                    </select>
                    <p className="text-xs text-slate-400">Default format for exported reports</p>
                  </div>
                  <div className="space-y-2">
                    <Label className="text-slate-300">Report Quality</Label>
                    <select
                      value={reportQuality}
                      onChange={(e) => setReportQuality(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-slate-100"
                    >
                      <option value="low">Low (Fast)</option>
                      <option value="medium">Medium</option>
                      <option value="high">High (Detailed)</option>
                    </select>
                    <p className="text-xs text-slate-400">Level of detail in reports</p>
                  </div>
                </div>
                <div className="pt-4">
                  <Button
                    className="bg-red-600 hover:bg-red-700 text-white border-none"
                    onClick={handleSaveReports}
                  >
                    Save Report Settings
                  </Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}


// ─── V151: Vision API Keys Tab ──────────────────────────────────────────────


interface VisionKeyRecord {
  id: string;
  provider: string;
  masked_key: string;
  base_url: string;
  model_name: string;
  description: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  last_used_at: string | null;
  expires_at?: string | null;
  is_expired?: boolean;
}


/**
 * VisionApiKeysTab — manage customer-supplied OpenAI Vision API keys.
 *
 * Flow:
 *   1. Customer enters OpenAI key + base URL + model name
 *   2. Frontend POSTs to /api/v1/settings/keys/openai
 *   3. Backend encrypts with AES-256, stores in SQLite, returns masked form
 *   4. UI displays masked key (fe_***...***f4c1) — plaintext never returned
 *
 * Security:
 *   - Plaintext keys are NEVER stored in localStorage / sessionStorage.
 *   - The input field is type="password" so the plaintext is masked while typing.
 *   - After successful save, the input field is cleared immediately.
 *   - The "Test" button pings the OpenAI /models endpoint with the stored key.
 */
function VisionApiKeysTab() {
  const [keys, setKeys] = useState<VisionKeyRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Form state
  const [provider, setProvider] = useState('openai');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('https://api.openai.com/v1');
  const [modelName, setModelName] = useState('gpt-4o');
  const [description, setDescription] = useState('');
  const [expiresAt, setExpiresAt] = useState('');

  // Per-key testing state
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<Record<string, { ok: boolean; error?: string }>>({});
  // V151.1: copied key feedback
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const API_BASE = (import.meta as any).env?.VITE_API_BASE_URL || '/api/v1';
  const authToken = typeof sessionStorage !== 'undefined'
    ? sessionStorage.getItem('fireai_api_key') || ''
    : '';

  // V151.1 S1: CSRF token helper — reads the __Host-fireai_csrf_token cookie
  // set by the backend CSRFMiddleware and sends it as X-CSRF-Token header
  // on all state-changing requests (POST/DELETE). Matches backend/security_csrf.py.
  const getCsrfToken = (): string => {
    if (typeof document === 'undefined') return '';
    const match = document.cookie.match(/__Host-fireai_csrf_token=([^;]+)/);
    return match ? match[1] : '';
  };

  // V151.1 S1: build headers with auth + CSRF for state-changing requests
  const buildMutationHeaders = (contentType = false): Record<string, string> => {
    const headers: Record<string, string> = {};
    if (authToken) headers['X-API-Key'] = authToken;
    const csrf = getCsrfToken();
    if (csrf) headers['X-CSRF-Token'] = csrf;
    if (contentType) headers['Content-Type'] = 'application/json';
    return headers;
  };

  // V151.1 U3: copy masked key to clipboard
  const handleCopyMasked = async (id: string, maskedKey: string) => {
    try {
      await navigator.clipboard.writeText(maskedKey);
      setCopiedId(id);
      toast.success('Masked key copied to clipboard', { description: maskedKey });
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      toast.error('Failed to copy — clipboard not available');
    }
  };

  const fetchKeys = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${API_BASE}/settings/keys/${provider}`, {
        headers: authToken ? { 'X-API-Key': authToken } : {},
      });
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
      const data = await resp.json();
      setKeys(Array.isArray(data) ? data : []);
    } catch (e: any) {
      setError(e.message || 'Failed to load keys');
    } finally {
      setLoading(false);
    }
  };

  // V152: re-fetch when provider changes
  useEffect(() => {
    fetchKeys();
  }, [provider]);

  const handleSave = async () => {
    setError(null);
    setSuccess(null);
    if (!apiKey || apiKey.length < 8) {
      const msg = 'API key must be at least 8 characters';
      setError(msg);
      toast.error(msg);
      return;
    }
    setLoading(true);
    try {
      const resp = await fetch(`${API_BASE}/settings/keys/${provider}`, {
        method: 'POST',
        headers: buildMutationHeaders(true),
        body: JSON.stringify({
          api_key: apiKey,
          base_url: baseUrl,
          model_name: modelName,
          description,
          expires_at: expiresAt || null,
        }),
      });
      if (!resp.ok) {
        const errBody = await resp.json().catch(() => ({}));
        throw new Error(errBody.detail || `HTTP ${resp.status}`);
      }
      const saved = await resp.json();
      const successMsg = `Key saved — masked as ${saved.masked_key}`;
      setSuccess(successMsg);
      toast.success('Vision API key saved', { description: `Masked: ${saved.masked_key}` });
      // Clear the plaintext from the form immediately
      setApiKey('');
      setDescription('');
      setExpiresAt('');
      await fetchKeys();
    } catch (e: any) {
      const msg = e.message || 'Failed to save key';
      setError(msg);
      toast.error('Failed to save key', { description: msg });
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this key? The CUA loop will fall back to OpenCV or the env var.')) {
      return;
    }
    setError(null);
    setSuccess(null);
    try {
      const resp = await fetch(`${API_BASE}/settings/keys/${provider}/${id}`, {
        method: 'DELETE',
        headers: buildMutationHeaders(),
      });
      if (!resp.ok && resp.status !== 204) {
        throw new Error(`HTTP ${resp.status}`);
      }
      setSuccess('Key deleted');
      toast.success('Vision API key deleted', { description: 'CUA loop will fall back to OpenCV' });
      await fetchKeys();
    } catch (e: any) {
      const msg = e.message || 'Failed to delete key';
      setError(msg);
      toast.error('Failed to delete key', { description: msg });
    }
  };

  // V152: bulk delete — delete all keys for the current provider
  const handleBulkDelete = async () => {
    if (!confirm(`Delete ALL keys for provider "${provider}"? This cannot be undone.`)) {
      return;
    }
    setError(null);
    setSuccess(null);
    try {
      const resp = await fetch(`${API_BASE}/settings/keys/${provider}/bulk-delete`, {
        method: 'POST',
        headers: buildMutationHeaders(true),
        body: JSON.stringify({ ids: null }),
      });
      if (!resp.ok) {
        const errBody = await resp.json().catch(() => ({}));
        throw new Error(errBody.detail || `HTTP ${resp.status}`);
      }
      const data = await resp.json();
      setSuccess(`Deleted ${data.deleted_count} keys`);
      toast.success(`Bulk-deleted ${data.deleted_count} keys`, { description: `Provider: ${provider}` });
      await fetchKeys();
    } catch (e: any) {
      const msg = e.message || 'Failed to bulk-delete keys';
      setError(msg);
      toast.error('Failed to bulk-delete keys', { description: msg });
    }
  };

  const handleTest = async (id: string) => {
    setTestingId(id);
    setTestResult((prev) => ({ ...prev, [id]: { ok: false, error: 'Testing...' } }));
    try {
      const resp = await fetch(`${API_BASE}/settings/keys/${provider}/${id}/test`, {
        method: 'POST',
        headers: buildMutationHeaders(),
      });
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
      const data = await resp.json();
      setTestResult((prev) => ({
        ...prev,
        [id]: { ok: data.ok, error: data.error || undefined },
      }));
      if (data.ok) {
        toast.success('Key test passed', { description: 'OpenAI accepted the key' });
      } else {
        toast.error('Key test failed', { description: data.error || 'OpenAI rejected the key' });
      }
    } catch (e: any) {
      const msg = e.message || 'Network error';
      setTestResult((prev) => ({
        ...prev,
        [id]: { ok: false, error: msg },
      }));
      toast.error('Key test failed', { description: msg });
    } finally {
      setTestingId(null);
    }
  };

  return (
    <Card className="border-slate-700 bg-slate-800/80">
      <CardHeader className="pb-3">
        <CardTitle className="text-lg text-slate-100 flex items-center gap-2">
          <Eye className="h-5 w-5 text-blue-400" />
          Vision API Keys
          <Badge variant="outline" className="ml-2 text-emerald-400 border-emerald-700 bg-emerald-900/20">
            AES-256-GCM
          </Badge>
        </CardTitle>
        <CardDescription className="text-slate-400">
          Add an OpenAI Vision API key to enable AI-powered screenshot analysis.
          Keys are encrypted at rest and never exposed to the frontend.
          Optional — the system falls back to OpenCV if no key is set.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Add new key form */}
        <div className="space-y-4 p-4 rounded-lg border border-slate-700 bg-slate-900/50">
          <h3 className="font-medium text-slate-200 flex items-center gap-2">
            <Plus className="h-4 w-4" /> Add / Update Vision API Key
          </h3>
          {/* V152: provider selector */}
          <div className="space-y-2">
            <Label className="text-slate-300">Provider</Label>
            <select
              value={provider}
              onChange={(e) => {
                setProvider(e.target.value);
                // Reset base_url + model to provider defaults on change
                const defaults: Record<string, { base_url: string; model: string }> = {
                  openai: { base_url: 'https://api.openai.com/v1', model: 'gpt-4o' },
                  anthropic: { base_url: 'https://api.anthropic.com/v1', model: 'claude-3-5-sonnet-20241022' },
                  gemini: { base_url: 'https://generativelanguage.googleapis.com/v1beta', model: 'gemini-2.0-flash' },
                  azure: { base_url: '', model: 'gpt-4o' },
                  openrouter: { base_url: 'https://openrouter.ai/api/v1', model: 'openai/gpt-4o' },
                  opencode: { base_url: 'https://api.opencode.ai/v1', model: 'gpt-4o' },
                };
                const d = defaults[e.target.value];
                if (d) { setBaseUrl(d.base_url); setModelName(d.model); }
              }}
              className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-slate-100"
            >
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic (Claude)</option>
              <option value="gemini">Google Gemini</option>
              <option value="azure">Azure OpenAI</option>
              <option value="openrouter">OpenRouter</option>
              <option value="opencode">OpenCode</option>
            </select>
            <p className="text-xs text-slate-400">
              Select the Vision API provider. Base URL and model will auto-fill with defaults.
            </p>
          </div>
          <div className="space-y-2">
            <Label className="text-slate-300">API Key</Label>
            <Input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-proj-..."
              className="bg-slate-900 border-slate-600 text-slate-100 font-mono"
              autoComplete="off"
            />
            <p className="text-xs text-slate-400">
              Stored AES-256-GCM encrypted. Only the masked form is returned after save.
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label className="text-slate-300">Base URL</Label>
              <Input
                type="text"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="https://api.openai.com/v1"
                className="bg-slate-900 border-slate-600 text-slate-100 font-mono"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-slate-300">Model Name</Label>
              <Input
                type="text"
                value={modelName}
                onChange={(e) => setModelName(e.target.value)}
                placeholder="gpt-4o"
                className="bg-slate-900 border-slate-600 text-slate-100 font-mono"
              />
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label className="text-slate-300">Description (optional)</Label>
              <Input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="e.g. Production OpenAI key"
                maxLength={200}
                className="bg-slate-900 border-slate-600 text-slate-100"
              />
            </div>
            {/* V152: expiry field */}
            <div className="space-y-2">
              <Label className="text-slate-300">Expires At (optional)</Label>
              <Input
                type="datetime-local"
                value={expiresAt}
                onChange={(e) => setExpiresAt(e.target.value)}
                className="bg-slate-900 border-slate-600 text-slate-100"
              />
              <p className="text-xs text-slate-400">
                Key auto-disables after this date. Leave empty for no expiry.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3 pt-2">
            <Button
              className="bg-red-600 hover:bg-red-700 text-white border-none"
              onClick={handleSave}
              disabled={loading || !apiKey}
            >
              {loading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}
              Save Key (Encrypted)
            </Button>
            {success && (
              <span className="text-sm text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="h-4 w-4" /> {success}
              </span>
            )}
            {error && (
              <span className="text-sm text-red-400 flex items-center gap-1">
                <AlertTriangle className="h-4 w-4" /> {error}
              </span>
            )}
          </div>
        </div>

        {/* Existing keys list */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-medium text-slate-200">Stored Keys ({provider})</h3>
            <div className="flex items-center gap-2">
              {/* V152: bulk delete button */}
              {keys.length > 0 && (
                <Button
                  variant="outline"
                  size="sm"
                  className="border-red-800 text-red-400 hover:bg-red-900/30"
                  onClick={handleBulkDelete}
                  disabled={loading}
                >
                  <Trash2 className="h-3 w-3 mr-1" />
                  Delete All
                </Button>
              )}
              <Button
                variant="outline"
                className="border-slate-600 text-slate-300 hover:bg-slate-800"
                onClick={fetchKeys}
                disabled={loading}
              >
                {loading ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Activity className="h-4 w-4 mr-1" />}
                Refresh
              </Button>
            </div>
          </div>
          {loading && keys.length === 0 ? (
            // V151.1 U4: loading skeleton (instead of empty state during initial load)
            <div className="space-y-2">
              {[1, 2].map((i) => (
                <div key={i} className="flex items-center p-3 rounded-lg border border-slate-700 bg-slate-900/50 animate-pulse">
                  <div className="flex-1 space-y-2">
                    <div className="h-4 bg-slate-700 rounded w-1/3" />
                    <div className="h-3 bg-slate-800 rounded w-1/2" />
                  </div>
                </div>
              ))}
            </div>
          ) : keys.length === 0 ? (
            <div className="text-sm text-slate-400 p-4 rounded-lg border border-dashed border-slate-700 text-center">
              No active keys. The CUA loop is using OpenCV fallback.
            </div>
          ) : (
            <div className="space-y-2">
              {keys.map((k) => (
                <div
                  key={k.id}
                  className="flex items-center justify-between p-3 rounded-lg border border-slate-700 bg-slate-900/50"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <Key className="h-4 w-4 text-slate-400 flex-shrink-0" />
                      <code className="text-sm text-slate-200 font-mono truncate">
                        {k.masked_key}
                      </code>
                      {k.is_active && !k.is_expired && (
                        <Badge variant="outline" className="text-emerald-400 border-emerald-700 bg-emerald-900/20">
                          active
                        </Badge>
                      )}
                      {k.is_expired && (
                        <Badge variant="outline" className="text-amber-400 border-amber-700 bg-amber-900/20">
                          expired
                        </Badge>
                      )}
                      {/* V151.1 U3: copy-to-clipboard button */}
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 px-2 text-slate-400 hover:text-slate-200 hover:bg-slate-800"
                        onClick={() => handleCopyMasked(k.id, k.masked_key)}
                        title="Copy masked key"
                      >
                        {copiedId === k.id ? (
                          <CheckCircle2 className="h-3 w-3 text-emerald-400" />
                        ) : (
                          <Key className="h-3 w-3" />
                        )}
                      </Button>
                    </div>
                    <div className="text-xs text-slate-500 mt-1 flex flex-wrap gap-x-3 gap-y-1">
                      <span>model: {k.model_name}</span>
                      <span>base: {k.base_url}</span>
                      {k.description && <span>desc: {k.description}</span>}
                      {k.last_used_at && <span>last used: {k.last_used_at}</span>}
                      {k.expires_at && <span>expires: {k.expires_at}</span>}
                    </div>
                    {testResult[k.id] && (
                      <div
                        className={`text-xs mt-2 flex items-center gap-1 ${
                          testResult[k.id].ok ? 'text-emerald-400' : 'text-red-400'
                        }`}
                      >
                        {testResult[k.id].ok ? (
                          <><CheckCircle2 className="h-3 w-3" /> Key works</>
                        ) : (
                          <><XCircle className="h-3 w-3" /> {testResult[k.id].error}</>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-1 ml-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="border-slate-600 text-slate-300 hover:bg-slate-800"
                      onClick={() => handleTest(k.id)}
                      disabled={testingId === k.id}
                    >
                      {testingId === k.id ? (
                        <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                      ) : (
                        <Zap className="h-3 w-3 mr-1" />
                      )}
                      Test
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="border-red-800 text-red-400 hover:bg-red-900/30"
                      onClick={() => handleDelete(k.id)}
                    >
                      <Trash2 className="h-3 w-3 mr-1" />
                      Delete
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Security notice */}
        <div className="text-xs text-slate-500 p-3 rounded-lg border border-slate-800 bg-slate-900/30 flex items-start gap-2">
          <Shield className="h-4 w-4 flex-shrink-0 mt-0.5" />
          <div>
            <strong>Security:</strong> Keys are encrypted with AES-256-GCM at rest.
            Plaintext is never logged or returned to the frontend. The system
            works without a key (OpenCV fallback). Wrong keys auto-fallback to
            OpenCV. You can add, delete, or update keys at any time.
          </div>
        </div>
      </CardContent>
    </Card>
  );
}