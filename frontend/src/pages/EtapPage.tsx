/**
 * EtapPage.tsx — ETAP Power System Integration.
 *
 * Full integration settings page for ETAP:
 *   - Connection management (host, port, username, password)
 *   - Project sync (local ↔ ETAP)
 *   - Export/Import controls
 *   - Sync schedule
 *   - Operation logs
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
        Activity,
        AlertCircle,
        CheckCircle2,
        Download,
        Globe,
        Import,
        Loader2,
        Play,
        RefreshCw,
        Save,
        Server,
        Settings2,
        Trash2,
        Upload,
        XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
        Card,
        CardContent,
        CardDescription,
        CardHeader,
        CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
        Select,
        SelectContent,
        SelectItem,
        SelectTrigger,
        SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { etapApi, type EtapConnectionSettings, type EtapExportRequest, type EtapImportRequest, type EtapProjectInfo, type EtapSettingsResponse, type EtapSyncLog } from "@/services/fullApi";

const DEFAULT_PROJECT_ID = "default";

export function EtapPage() {
        const { t } = useTranslation();
        const { toast } = useToast();

        // Connection state
        const [connectionStatus, setConnectionStatus] = useState<"disconnected" | "connecting" | "connected" | "error">("disconnected");
        const [connectionMessage, setConnectionMessage] = useState<string>("");
        const [serverVersion, setServerVersion] = useState<string>("");

        // Settings form
        const [settings, setSettings] = useState<EtapConnectionSettings>({
                host: "",
                port: 9876,
                username: "",
                password: "",
                timeout_seconds: 30,
        });
        const [savedSettings, setSavedSettings] = useState<EtapSettingsResponse | null>(null);
        const [settingsLoaded, setSettingsLoaded] = useState(false);

        // Projects
        const [etapProjects, setEtapProjects] = useState<EtapProjectInfo[]>([]);
        const [localProjects, setLocalProjects] = useState<{ id: string; name: string }[]>([]);
        const [selectedLocalProject, setSelectedLocalProject] = useState<string>(DEFAULT_PROJECT_ID);
        const [selectedEtapProject, setSelectedEtapProject] = useState<string>("");

        // Export/Import forms
        const [exportFormat, setExportFormat] = useState<"csv" | "ort">("csv");
        const [includeLoads, setIncludeLoads] = useState(true);
        const [includeSources, setIncludeSources] = useState(true);
        const [includeTopology, setIncludeTopology] = useState(false);
        const [importLoads, setImportLoads] = useState(true);
        const [importSources, setImportSources] = useState(true);
        const [conflictResolution, setConflictResolution] = useState<"skip" | "overwrite" | "merge">("skip");

        // Logs
        const [logs, setLogs] = useState<EtapSyncLog[]>([]);
        const [logsPage, setLogsPage] = useState(1);

        // UI state
        const [loading, setLoading] = useState<string | null>(null);
        const [showPassword, setShowPassword] = useState(false);
        const [syncEnabled, setSyncEnabled] = useState(false);

        const loadSettings = async () => {
                setLoading("loading-settings");
                try {
                        const data = await etapApi.getSettings(selectedLocalProject);
                        if (data) {
                                setSavedSettings(data);
                                setSettings({
                                        host: data.host,
                                        port: data.port,
                                        username: data.username,
                                        password: "",
                                        timeout_seconds: 30,
                                });
                                setSyncEnabled(data.enabled);
                        }
                        setSettingsLoaded(true);
                } catch (error) {
                        console.error("Failed to load ETAP settings", error);
                } finally {
                        setLoading(null);
                }
        };

        const loadProjects = async () => {
                setLoading("loading-projects");
                try {
                        const [etap, local] = await Promise.all([
                                etapApi.listEtapProjects(selectedLocalProject),
                                etapApi.listLocalProjects(),
                        ]);
                        setEtapProjects(etap);
                        setLocalProjects(local.map((p: any) => ({ id: p.id, name: p.name })));
                } catch (error) {
                        console.error("Failed to load projects", error);
                } finally {
                        setLoading(null);
                }
        };

        const loadLogs = async () => {
                setLoading("loading-logs");
                try {
                        const data = await etapApi.getLogs(selectedLocalProject, logsPage, 20);
                        setLogs(data.items || []);
                } catch (error) {
                        console.error("Failed to load logs", error);
                } finally {
                        setLoading(null);
                }
        };

        const handleTestConnection = async () => {
                if (!settings.host || !settings.port || !settings.username || !settings.password) {
                        toast({
                                title: t("etap.missingFields"),
                                description: t("etap.fillAllFields"),
                                variant: "destructive",
                        });
                        return;
                }

                setConnectionStatus("connecting");
                setConnectionMessage("");
                setServerVersion("");

                try {
                        const response = await etapApi.testConnection(settings, selectedLocalProject);
                        if (response.success) {
                                setConnectionStatus("connected");
                                setConnectionMessage(response.message || "Connected");
                                setServerVersion(response.server_version || "");
                                toast({
                                        title: t("etap.connectionSuccess"),
                                        description: response.message,
                                });
                        } else {
                                setConnectionStatus("error");
                                setConnectionMessage(response.message);
                                toast({
                                        title: t("etap.connectionFailed"),
                                        description: response.message,
                                        variant: "destructive",
                                });
                        }
                } catch (error: any) {
                        setConnectionStatus("error");
                        setConnectionMessage(error.message || "Connection failed");
                        toast({
                                title: t("etap.connectionError"),
                                description: error.message,
                                variant: "destructive",
                        });
                }
        };

        const handleSaveSettings = async () => {
                setLoading("saving-settings");
                try {
                        if (savedSettings) {
                                await etapApi.updateSettings(selectedLocalProject, {
                                        host: settings.host,
                                        port: settings.port,
                                        username: settings.username,
                                        password: settings.password || undefined,
                                        timeout_seconds: settings.timeout_seconds,
                                        enabled: syncEnabled,
                                });
                        } else {
                                await etapApi.createSettings(selectedLocalProject, settings);
                        }
                        await loadSettings();
                        toast({
                                title: t("etap.settingsSaved"),
                                description: t("etap.settingsSavedDesc"),
                        });
                } catch (error: any) {
                        toast({
                                title: t("etap.saveFailed"),
                                description: error.message,
                                variant: "destructive",
                        });
                } finally {
                        setLoading(null);
                }
        };

        const handleDeleteSettings = async () => {
                setLoading("deleting-settings");
                try {
                        await etapApi.deleteSettings(selectedLocalProject);
                        setSavedSettings(null);
                        setSettings({
                                host: "",
                                port: 9876,
                                username: "",
                                password: "",
                                timeout_seconds: 30,
                        });
                        setSyncEnabled(false);
                        setConnectionStatus("disconnected");
                        toast({
                                title: t("etap.settingsDeleted"),
                                description: t("etap.settingsDeletedDesc"),
                        });
                } catch (error: any) {
                        toast({
                                title: t("etap.deleteFailed"),
                                description: error.message,
                                variant: "destructive",
                        });
                } finally {
                        setLoading(null);
                }
        };

        const handleExport = async () => {
                setLoading("exporting");
                try {
                        const request: EtapExportRequest = {
                                project_id: selectedLocalProject,
                                include_loads: includeLoads,
                                include_sources: includeSources,
                                include_topology: includeTopology,
                                format: exportFormat,
                        };
                        const response = await etapApi.exportToEtap(request);
                        toast({
                                title: t("etap.exportSuccess"),
                                description: `${t("etap.exportedRecords")}: ${response.records_exported}`,
                        });
                        await loadLogs();
                } catch (error: any) {
                        toast({
                                title: t("etap.exportFailed"),
                                description: error.message,
                                variant: "destructive",
                        });
                } finally {
                        setLoading(null);
                }
        };

        const handleImport = async () => {
                if (!selectedEtapProject) {
                        toast({
                                title: t("etap.selectEtapProject"),
                                description: t("etap.selectEtapProjectDesc"),
                                variant: "destructive",
                        });
                        return;
                }

                setLoading("importing");
                try {
                        const request: EtapImportRequest = {
                                project_id: selectedLocalProject,
                                etap_project_id: selectedEtapProject,
                                import_loads: importLoads,
                                import_sources: importSources,
                                conflict_resolution: conflictResolution,
                        };
                        const response = await etapApi.importFromEtap(request);
                        toast({
                                title: t("etap.importSuccess"),
                                description: response.message,
                        });
                        await loadLogs();
                } catch (error: any) {
                        toast({
                                title: t("etap.importFailed"),
                                description: error.message,
                                variant: "destructive",
                        });
                } finally {
                        setLoading(null);
                }
        };

        const getStatusBadge = () => {
                switch (connectionStatus) {
                        case "connected":
                                return <Badge className="bg-green-500/20 text-green-400 border-green-500/30"><CheckCircle2 className="h-3 w-3 mr-1" />{t("etap.connected")}</Badge>;
                        case "connecting":
                                return <Badge className="bg-yellow-500/20 text-yellow-400 border-yellow-500/30"><Loader2 className="h-3 w-3 mr-1 animate-spin" />{t("etap.connecting")}</Badge>;
                        case "error":
                                return <Badge className="bg-red-500/20 text-red-400 border-red-500/30"><XCircle className="h-3 w-3 mr-1" />{t("etap.error")}</Badge>;
                        default:
                                return <Badge className="bg-slate-500/20 text-slate-400 border-slate-500/30"><XCircle className="h-3 w-3 mr-1" />{t("etap.disconnected")}</Badge>;
                }
        };

        return (
                <div className="space-y-6">
                        {/* Header */}
                        <div className="flex items-center justify-between">
                                <div>
                                        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
                                                <Server className="h-6 w-6 text-cyan-400" />
                                                {t("etap.title", "ETAP Integration")}
                                        </h1>
                                        <p className="text-slate-400 mt-1">
                                                {t("etap.description", "Connect and synchronize with ETAP Power System Analysis software")}
                                        </p>
                                </div>
                                <div className="flex items-center gap-2">
                                        {getStatusBadge()}
                                </div>
                        </div>

                        <Tabs defaultValue="connection" className="space-y-4">
                                <TabsList className="bg-slate-800 border-slate-700">
                                        <TabsTrigger value="connection" className="data-[state=active]:bg-slate-700">
                                                <Settings2 className="h-4 w-4 mr-2" />
                                                {t("etap.connection")}
                                        </TabsTrigger>
                                        <TabsTrigger value="projects" className="data-[state=active]:bg-slate-700">
                                                <Globe className="h-4 w-4 mr-2" />
                                                {t("etap.projects")}
                                        </TabsTrigger>
                                        <TabsTrigger value="sync" className="data-[state=active]:bg-slate-700">
                                                <RefreshCw className="h-4 w-4 mr-2" />
                                                {t("etap.sync")}
                                        </TabsTrigger>
                                        <TabsTrigger value="logs" className="data-[state=active]:bg-slate-700">
                                                <Activity className="h-4 w-4 mr-2" />
                                                {t("etap.logs")}
                                        </TabsTrigger>
                                </TabsList>

                                {/* Connection Tab */}
                                <TabsContent value="connection" className="space-y-4">
                                        <Card className="bg-slate-800/50 border-slate-700">
                                                <CardHeader>
                                                        <CardTitle className="text-white flex items-center gap-2">
                                                                <Server className="h-5 w-5 text-cyan-400" />
                                                                {t("etap.connectionSettings")}
                                                        </CardTitle>
                                                        <CardDescription className="text-slate-400">
                                                                {t("etap.connectionSettingsDesc")}
                                                        </CardDescription>
                                                </CardHeader>
                                                <CardContent className="space-y-4">
                                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                                <div className="space-y-2">
                                                                        <Label htmlFor="host" className="text-slate-300">
                                                                                {t("etap.host")}
                                                                        </Label>
                                                                        <Input
                                                                                id="host"
                                                                                value={settings.host}
                                                                                onChange={(e) => setSettings({ ...settings, host: e.target.value })}
                                                                                placeholder="etap.example.com"
                                                                                className="bg-slate-900 border-slate-700 text-white"
                                                                        />
                                                                </div>
                                                                <div className="space-y-2">
                                                                        <Label htmlFor="port" className="text-slate-300">
                                                                                {t("etap.port")}
                                                                        </Label>
                                                                        <Input
                                                                                id="port"
                                                                                type="number"
                                                                                value={settings.port}
                                                                                onChange={(e) => setSettings({ ...settings, port: parseInt(e.target.value) || 0 })}
                                                                                className="bg-slate-900 border-slate-700 text-white"
                                                                        />
                                                                </div>
                                                                <div className="space-y-2">
                                                                        <Label htmlFor="username" className="text-slate-300">
                                                                                {t("etap.username")}
                                                                        </Label>
                                                                        <Input
                                                                                id="username"
                                                                                value={settings.username}
                                                                                onChange={(e) => setSettings({ ...settings, username: e.target.value })}
                                                                                className="bg-slate-900 border-slate-700 text-white"
                                                                        />
                                                                </div>
                                                                <div className="space-y-2">
                                                                        <Label htmlFor="password" className="text-slate-300">
                                                                                {t("etap.password")}
                                                                        </Label>
                                                                        <div className="relative">
                                                                                <Input
                                                                                        id="password"
                                                                                        type={showPassword ? "text" : "password"}
                                                                                        value={settings.password}
                                                                                        onChange={(e) => setSettings({ ...settings, password: e.target.value })}
                                                                                        className="bg-slate-900 border-slate-700 text-white pr-10"
                                                                                />
                                                                                <Button
                                                                                        type="button"
                                                                                        variant="ghost"
                                                                                        size="sm"
                                                                                        className="absolute right-0 top-0 h-full px-3"
                                                                                        onClick={() => setShowPassword(!showPassword)}
                                                                                >
                                                                                        {showPassword ? <EyeOffIcon className="h-4 w-4" /> : <EyeIcon className="h-4 w-4" />}
                                                                                </Button>
                                                                        </div>
                                                                </div>
                                                                <div className="space-y-2">
                                                                        <Label htmlFor="timeout" className="text-slate-300">
                                                                                {t("etap.timeoutSeconds")}
                                                                        </Label>
                                                                        <Input
                                                                                id="timeout"
                                                                                type="number"
                                                                                value={settings.timeout_seconds}
                                                                                onChange={(e) => setSettings({ ...settings, timeout_seconds: parseInt(e.target.value) || 30 })}
                                                                                className="bg-slate-900 border-slate-700 text-white"
                                                                        />
                                                                </div>
                                                        </div>

                                                        <div className="flex flex-wrap gap-2">
                                                                <Button
                                                                        onClick={handleTestConnection}
                                                                        disabled={connectionStatus === "connecting"}
                                                                        className="bg-cyan-600 hover:bg-cyan-700"
                                                                >
                                                                        {connectionStatus === "connecting" ? (
                                                                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                                                        ) : (
                                                                                <Play className="h-4 w-4 mr-2" />
                                                                        )}
                                                                        {t("etap.testConnection")}
                                                                </Button>
                                                                <Button
                                                                        onClick={handleSaveSettings}
                                                                        disabled={loading === "saving-settings"}
                                                                        className="bg-emerald-600 hover:bg-emerald-700"
                                                                >
                                                                        {loading === "saving-settings" ? (
                                                                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                                                        ) : (
                                                                                <Save className="h-4 w-4 mr-2" />
                                                                        )}
                                                                        {t("etap.saveSettings")}
                                                                </Button>
                                                                {savedSettings && (
                                                                        <Button
                                                                                onClick={handleDeleteSettings}
                                                                                disabled={loading === "deleting-settings"}
                                                                                variant="destructive"
                                                                        >
                                                                                {loading === "deleting-settings" ? (
                                                                                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                                                                ) : (
                                                                                        <Trash2 className="h-4 w-4 mr-2" />
                                                                                )}
                                                                                {t("etap.deleteSettings")}
                                                                        </Button>
                                                                )}
                                                        </div>

                                                        {connectionMessage && (
                                                                <div className={`p-3 rounded-md flex items-start gap-2 ${
                                                                        connectionStatus === "connected" ? "bg-green-500/10 text-green-400" :
                                                                        connectionStatus === "error" ? "bg-red-500/10 text-red-400" :
                                                                        "bg-slate-500/10 text-slate-400"
                                                                }`}>
                                                                        {connectionStatus === "connected" ? <CheckCircle2 className="h-5 w-5 mt-0.5" /> :
                                                                         connectionStatus === "error" ? <AlertCircle className="h-5 w-5 mt-0.5" /> :
                                                                         <Activity className="h-5 w-5 mt-0.5" />}
                                                                        <div>
                                                                                <p className="font-medium">{connectionMessage}</p>
                                                                                {serverVersion && <p className="text-sm mt-1 opacity-80">{serverVersion}</p>}
                                                                        </div>
                                                                </div>
                                                        )}

                                                        <div className="flex items-center justify-between p-4 bg-slate-900/50 rounded-lg border border-slate-700">
                                                                <div className="flex items-center gap-2">
                                                                        <RefreshCw className="h-5 w-5 text-slate-400" />
                                                                        <div>
                                                                                <Label className="text-white">{t("etap.autoSync")}</Label>
                                                                                <p className="text-sm text-slate-400">{t("etap.autoSyncDesc")}</p>
                                                                        </div>
                                                                </div>
                                                                <Switch checked={syncEnabled} onCheckedChange={setSyncEnabled} />
                                                        </div>
                                                </CardContent>
                                        </Card>
                                </TabsContent>

                                {/* Projects Tab */}
                                <TabsContent value="projects" className="space-y-4">
                                        <Card className="bg-slate-800/50 border-slate-700">
                                                <CardHeader>
                                                        <CardTitle className="text-white flex items-center gap-2">
                                                                <Globe className="h-5 w-5 text-cyan-400" />
                                                                {t("etap.projectSync")}
                                                        </CardTitle>
                                                        <CardDescription className="text-slate-400">
                                                                {t("etap.projectSyncDesc")}
                                                        </CardDescription>
                                                </CardHeader>
                                                <CardContent className="space-y-4">
                                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                                <div className="space-y-2">
                                                                        <Label className="text-slate-300">{t("etap.localProject")}</Label>
                                                                        <Select value={selectedLocalProject} onValueChange={setSelectedLocalProject}>
                                                                                <SelectTrigger className="bg-slate-900 border-slate-700 text-white">
                                                                                        <SelectValue placeholder={t("etap.selectLocalProject")} />
                                                                                </SelectTrigger>
                                                                                <SelectContent>
                                                                                        {localProjects.map((p) => (
                                                                                                <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                                                                                        ))}
                                                                                </SelectContent>
                                                                        </Select>
                                                                </div>
                                                                <div className="space-y-2">
                                                                        <Label className="text-slate-300">{t("etap.etapProject")}</Label>
                                                                        <Select value={selectedEtapProject} onValueChange={setSelectedEtapProject}>
                                                                                <SelectTrigger className="bg-slate-900 border-slate-700 text-white">
                                                                                        <SelectValue placeholder={t("etap.selectEtapProject")} />
                                                                                </SelectTrigger>
                                                                                <SelectContent>
                                                                                        {etapProjects.map((p) => (
                                                                                                <SelectItem key={p.project_id} value={p.project_id}>
                                                                                                        {p.name} {p.size_mb ? `(${p.size_mb} MB)` : ""}
                                                                                                </SelectItem>
                                                                                        ))}
                                                                                </SelectContent>
                                                                        </Select>
                                                                </div>
                                                        </div>
                                                </CardContent>
                                        </Card>
                                </TabsContent>

                                {/* Sync Tab */}
                                <TabsContent value="sync" className="space-y-4">
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                <Card className="bg-slate-800/50 border-slate-700">
                                                        <CardHeader>
                                                                <CardTitle className="text-white flex items-center gap-2">
                                                                        <Download className="h-5 w-5 text-emerald-400" />
                                                                        {t("etap.exportToEtap")}
                                                                </CardTitle>
                                                                <CardDescription className="text-slate-400">
                                                                        {t("etap.exportToEtapDesc")}
                                                                </CardDescription>
                                                        </CardHeader>
                                                        <CardContent className="space-y-4">
                                                                <div className="flex items-center gap-2">
                                                                        <Switch id="includeLoads" checked={includeLoads} onCheckedChange={setIncludeLoads} />
                                                                        <Label htmlFor="includeLoads" className="text-slate-300">{t("etap.includeLoads")}</Label>
                                                                </div>
                                                                <div className="flex items-center gap-2">
                                                                        <Switch id="includeSources" checked={includeSources} onCheckedChange={setIncludeSources} />
                                                                        <Label htmlFor="includeSources" className="text-slate-300">{t("etap.includeSources")}</Label>
                                                                </div>
                                                                <div className="flex items-center gap-2">
                                                                        <Switch id="includeTopology" checked={includeTopology} onCheckedChange={setIncludeTopology} />
                                                                        <Label htmlFor="includeTopology" className="text-slate-300">{t("etap.includeTopology")}</Label>
                                                                </div>
                                                                <div className="space-y-2">
                                                                        <Label className="text-slate-300">{t("etap.format")}</Label>
                                                                        <Select value={exportFormat} onValueChange={(v) => setExportFormat(v as "csv" | "ort")}>
                                                                                <SelectTrigger className="bg-slate-900 border-slate-700 text-white">
                                                                                        <SelectValue />
                                                                                </SelectTrigger>
                                                                                <SelectContent>
                                                                                        <SelectItem value="csv">CSV</SelectItem>
                                                                                        <SelectItem value="ort">ORT (ETAP Native)</SelectItem>
                                                                                </SelectContent>
                                                                        </Select>
                                                                </div>
                                                                <Button
                                                                        onClick={handleExport}
                                                                        disabled={loading === "exporting"}
                                                                        className="w-full bg-emerald-600 hover:bg-emerald-700"
                                                                >
                                                                        {loading === "exporting" ? (
                                                                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                                                        ) : (
                                                                                <Download className="h-4 w-4 mr-2" />
                                                                        )}
                                                                        {t("etap.export")}
                                                                </Button>
                                                        </CardContent>
                                                </Card>

                                                <Card className="bg-slate-800/50 border-slate-700">
                                                        <CardHeader>
                                                                <CardTitle className="text-white flex items-center gap-2">
                                                                        <Import className="h-5 w-5 text-blue-400" />
                                                                        {t("etap.importFromEtap")}
                                                                </CardTitle>
                                                                <CardDescription className="text-slate-400">
                                                                        {t("etap.importFromEtapDesc")}
                                                                </CardDescription>
                                                        </CardHeader>
                                                        <CardContent className="space-y-4">
                                                                <div className="flex items-center gap-2">
                                                                        <Switch id="importLoads" checked={importLoads} onCheckedChange={setImportLoads} />
                                                                        <Label htmlFor="importLoads" className="text-slate-300">{t("etap.importLoads")}</Label>
                                                                </div>
                                                                <div className="flex items-center gap-2">
                                                                        <Switch id="importSources" checked={importSources} onCheckedChange={setImportSources} />
                                                                        <Label htmlFor="importSources" className="text-slate-300">{t("etap.importSources")}</Label>
                                                                </div>
                                                                <div className="space-y-2">
                                                                        <Label className="text-slate-300">{t("etap.conflictResolution")}</Label>
                                                                        <Select value={conflictResolution} onValueChange={(v) => setConflictResolution(v as any)}>
                                                                                <SelectTrigger className="bg-slate-900 border-slate-700 text-white">
                                                                                        <SelectValue />
                                                                                </SelectTrigger>
                                                                                <SelectContent>
                                                                                        <SelectItem value="skip">{t("etap.conflictSkip")}</SelectItem>
                                                                                        <SelectItem value="overwrite">{t("etap.conflictOverwrite")}</SelectItem>
                                                                                        <SelectItem value="merge">{t("etap.conflictMerge")}</SelectItem>
                                                                                </SelectContent>
                                                                        </Select>
                                                                </div>
                                                                <Button
                                                                        onClick={handleImport}
                                                                        disabled={loading === "importing" || !selectedEtapProject}
                                                                        className="w-full bg-blue-600 hover:bg-blue-700"
                                                                >
                                                                        {loading === "importing" ? (
                                                                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                                                        ) : (
                                                                                <Upload className="h-4 w-4 mr-2" />
                                                                        )}
                                                                        {t("etap.import")}
                                                                </Button>
                                                        </CardContent>
                                                </Card>
                                        </div>
                                </TabsContent>

                                {/* Logs Tab */}
                                <TabsContent value="logs" className="space-y-4">
                                        <Card className="bg-slate-800/50 border-slate-700">
                                                <CardHeader>
                                                        <CardTitle className="text-white flex items-center gap-2">
                                                                <Activity className="h-5 w-5 text-cyan-400" />
                                                                {t("etap.syncLogs")}
                                                        </CardTitle>
                                                        <CardDescription className="text-slate-400">
                                                                {t("etap.syncLogsDesc")}
                                                        </CardDescription>
                                                </CardHeader>
                                                <CardContent>
                                                        <div className="overflow-x-auto">
                                                                <table className="w-full text-sm">
                                                                        <thead>
                                                                                <tr className="border-b border-slate-700">
                                                                                        <th className="text-left py-2 px-4 text-slate-400">{t("etap.direction")}</th>
                                                                                        <th className="text-left py-2 px-4 text-slate-400">{t("etap.status")}</th>
                                                                                        <th className="text-left py-2 px-4 text-slate-400">{t("etap.records")}</th>
                                                                                        <th className="text-left py-2 px-4 text-slate-400">{t("etap.error")}</th>
                                                                                        <th className="text-left py-2 px-4 text-slate-400">{t("etap.timestamp")}</th>
                                                                                </tr>
                                                                        </thead>
                                                                        <tbody>
                                                                                {logs.length === 0 ? (
                                                                                        <tr>
                                                                                                <td colSpan={5} className="text-center py-8 text-slate-500">
                                                                                                        {t("etap.noLogs")}
                                                                                                </td>
                                                                                        </tr>
                                                                                ) : (
                                                                                        logs.map((log) => (
                                                                                                <tr key={log.id} className="border-b border-slate-700/50 hover:bg-slate-700/20">
                                                                                                        <td className="py-2 px-4 text-slate-300">
                                                                                                                <Badge variant={log.direction === "export" ? "default" : "secondary"}>
                                                                                                                        {log.direction === "export" ? <Download className="h-3 w-3 mr-1" /> : <Upload className="h-3 w-3 mr-1" />}
                                                                                                                        {log.direction}
                                                                                                                </Badge>
                                                                                                        </td>
                                                                                                        <td className="py-2 px-4">
                                                                                                                <Badge className={
                                                                                                                        log.status === "success" ? "bg-green-500/20 text-green-400 border-green-500/30" :
                                                                                                                        log.status === "error" ? "bg-red-500/20 text-red-400 border-red-500/30" :
                                                                                                                        "bg-yellow-500/20 text-yellow-400 border-yellow-500/30"
                                                                                                                }>
                                                                                                                        {log.status}
                                                                                                                </Badge>
                                                                                                        </td>
                                                                                                        <td className="py-2 px-4 text-slate-300">{log.records_synced}</td>
                                                                                                        <td className="py-2 px-4 text-slate-400">{log.error_message || "—"}</td>
                                                                                                        <td className="py-2 px-4 text-slate-400">{new Date(log.created_at).toLocaleString()}</td>
                                                                                                </tr>
                                                                                        ))
                                                                                )}
                                                                        </tbody>
                                                                </table>
                                                        </div>
                                                </CardContent>
                                        </Card>
                                </TabsContent>
                        </Tabs>
                </div>
        );
}

// Icons as components to avoid JSX issues
function EyeIcon({ className }: { readonly className: string }) {
        return (
                <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
        );
}

function EyeOffIcon({ className }: { readonly className: string }) {
        return (
                <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.542-7a10.059 10.059 0 013.999-5.398M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        <path strokeLinecap="round" strokeLinejoin="round" d="M3 3l18 18" />
                </svg>
        );
}