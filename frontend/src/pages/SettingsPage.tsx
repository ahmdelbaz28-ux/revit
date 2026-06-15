/**
 * SettingsPage.tsx - Application configuration and user preferences
 */
import { useState } from 'react';
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
} from 'lucide-react';
import { useHealth } from '@/hooks/useApi';
import { api } from '@/services/digitalTwinApi';

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
    try {
      localStorage.setItem(`fireai_settings_${key}`, JSON.stringify(value));
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