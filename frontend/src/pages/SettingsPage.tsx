// NOSONAR
/**
 * SettingsPage.tsx - Application configuration and user preferences
 */

import {
	Activity,
	Calculator,
	CheckCircle2,
	Database,
	Settings,
	Shield,
	XCircle,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
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
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useHealth } from "@/hooks/useApi";

export function SettingsPage() {
	const { t } = useTranslation();
	const navigate = useNavigate();
	const {
		data: health,
		loading: healthLoading,
		connected,
		refetch: refetchHealth,
	} = useHealth();

	const [activeTab, setActiveTab] = useState("general");

	// General settings
	const [theme, setTheme] = useState("dark");
	const [language, setLanguage] = useState("en");
	const [notifications, setNotifications] = useState(true);

	// Security settings
	const [twoFactorAuth, setTwoFactorAuth] = useState(false);
	const [passwordExpiry, setPasswordExpiry] = useState(90);

	// API settings
	const [apiTimeout, setApiTimeout] = useState(30);
	const [retryAttempts, setRetryAttempts] = useState(3);

	// Report settings
	const [autoSaveReports, setAutoSaveReports] = useState(true);
	const [reportFormat, setReportFormat] = useState("pdf");
	const [reportQuality, setReportQuality] = useState("high");

	const [_saveStatus, setSaveStatus] = useState<string | null>(null);  // NOSONAR - typescript:S6754

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
			const SENSITIVE_KEYS = [
				"apiKey",
				"api_key",
				"password",
				"token",
				"secret",
			];
			for (const [k, v] of Object.entries(value)) {
				if (
					!SENSITIVE_KEYS.some((s) => k.toLowerCase().includes(s.toLowerCase()))
				) {
					safeValue[k] = v;
				}
			}
			localStorage.setItem(`fireai_settings_${key}`, JSON.stringify(safeValue));
			setSaveStatus("saved");
			setTimeout(() => setSaveStatus(null), 2000);
		} catch {
			setSaveStatus("error");
			setTimeout(() => setSaveStatus(null), 3000);
		}
	};

	const handleSaveGeneral = () => {
		persistSettings("general", { theme, language, notifications });
	};

	const handleSaveSecurity = () => {
		persistSettings("security", { twoFactorAuth, passwordExpiry });
	};

	const handleSaveApi = () => {
		persistSettings("api", { apiTimeout, retryAttempts });
	};

	const handleSaveReports = () => {
		persistSettings("reports", {
			autoSaveReports,
			reportFormat,
			reportQuality,
		});
	};

	return (
		<div className="flex-1 overflow-auto" aria-label={t("settings.title")}>
			<div className="p-6 max-w-4xl mx-auto space-y-6">
				{/* Header */}
				<div className="flex items-center justify-between">
					<div>
						<h1 className="text-2xl font-bold text-foreground">
							{t("settings.title")}
						</h1>
						<p className="text-sm text-muted-foreground mt-1">
							{t("settings.subtitle")}
						</p>
					</div>
					<Button
						variant="outline"
						className="border-border text-foreground/90 hover:bg-card"
						onClick={() => refetchHealth()}
					>
						<Activity className="h-4 w-4 mr-1" />
						{t("common.refresh")}
					</Button>
				</div>

				{/* System Health */}
				<Card className="border-border bg-card">
					<CardHeader className="pb-3">
						<CardTitle className="text-lg text-foreground flex items-center gap-2">
							<Activity className="h-5 w-5 text-info" />
							{t("settings.systemHealth")}
						</CardTitle>
						<CardDescription className="text-muted-foreground">
							{healthLoading
								? "Checking system status..."
								: "Current system status and performance metrics"}
						</CardDescription>
					</CardHeader>
					<CardContent>
						<div className="flex items-center gap-4 text-sm">
							<div className="flex items-center gap-2">
								{connected ? (
									<CheckCircle2 className="h-5 w-5 text-success" />
								) : (
									<XCircle className="h-5 w-5 text-danger" />
								)}
								<span>{connected ? "Connected" : "Disconnected"}</span>
							</div>
							{health && (
								<>
									<Separator
										orientation="vertical"
										className="h-5 bg-secondary"
									/>
									<div className="flex items-center gap-2">
										<span>API v{health.version}</span>
									</div>
									<Separator
										orientation="vertical"
										className="h-5 bg-secondary"
									/>
									<div className="flex items-center gap-2">
										<span>DB: {health.database}</span>
									</div>
									<Separator
										orientation="vertical"
										className="h-5 bg-secondary"
									/>
									<div className="flex items-center gap-2">
										<span>
											Uptime: {Math.floor((health.uptime || 0) / 60)} min
										</span>
									</div>
								</>
							)}
						</div>
					</CardContent>
				</Card>

				{/* Report Generator Quick Access */}
				<Card className="border-border bg-card">
					<CardHeader className="pb-3">
						<CardTitle className="text-lg text-foreground">
							{t("settings.advancedReportGenerator")}
						</CardTitle>
						<CardDescription className="text-muted-foreground">
							{t("settings.reportGeneratorDesc")}
						</CardDescription>
					</CardHeader>
					<CardContent>
						<div className="flex flex-col sm:flex-row gap-4">
							<div className="flex-1">
								<h3 className="font-medium text-foreground mb-2">
									{t("settings.comprehensiveReportGeneration")}
								</h3>
								<p className="text-sm text-muted-foreground">
									{t("settings.comprehensiveReportDesc")}
								</p>
							</div>
							<Button
								onClick={() => navigate("/reports")}
								className="bg-danger hover:bg-danger/90 text-white border-none flex items-center gap-2"
								aria-label={t("settings.openReportGenerator")}
							>
								<Calculator className="h-4 w-4" />
								{t("settings.openReportGenerator")}
							</Button>
						</div>
					</CardContent>
				</Card>

				{/* Settings Tabs */}
				<Tabs value={activeTab} onValueChange={setActiveTab}>
					<TabsList className="bg-card border border-border">
						<TabsTrigger
							value="general"
							className="data-[state=active]:bg-secondary data-[state=active]:text-foreground"
						>
							<Settings className="h-4 w-4 mr-1" /> {t("settings.general")}
						</TabsTrigger>
						<TabsTrigger
							value="security"
							className="data-[state=active]:bg-secondary data-[state=active]:text-foreground"
						>
							<Shield className="h-4 w-4 mr-1" /> {t("settings.security")}
						</TabsTrigger>
						<TabsTrigger
							value="api"
							className="data-[state=active]:bg-secondary data-[state=active]:text-foreground"
						>
							<Database className="h-4 w-4 mr-1" /> {t("settings.api")}
						</TabsTrigger>
						<TabsTrigger
							value="reports"
							className="data-[state=active]:bg-secondary data-[state=active]:text-foreground"
						>
							<Calculator className="h-4 w-4 mr-1" /> {t("settings.reports")}
						</TabsTrigger>
					</TabsList>

					{/* General Settings */}
					<TabsContent value="general">
						<Card className="border-border bg-card">
							<CardHeader className="pb-3">
								<CardTitle className="text-lg text-foreground">
									{t("settings.general")}
								</CardTitle>
								<CardDescription className="text-muted-foreground">
									{t("settings.generalDescription")}
								</CardDescription>
							</CardHeader>
							<CardContent className="space-y-4">
								<div className="grid grid-cols-1 md:grid-cols-2 gap-4">
									<div className="space-y-2">
										<Label className="text-foreground/90">
											{t("settings.theme")}
										</Label>
										<select
											value={theme}
											onChange={(e) => setTheme(e.target.value)}
											className="w-full bg-card border border-border rounded px-3 py-2 text-foreground"
										>
											<option value="light">{t("settings.light")}</option>
											<option value="dark">{t("settings.dark")}</option>
											<option value="system">{t("settings.system")}</option>
										</select>
									</div>
									<div className="space-y-2">
										<Label className="text-foreground/90">
											{t("settings.language")}
										</Label>
										<select
											value={language}
											onChange={(e) => setLanguage(e.target.value)}
											className="w-full bg-card border border-border rounded px-3 py-2 text-foreground"
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
										<Label className="text-foreground/90">
											{t("settings.notifications")}
										</Label>
										<p className="text-xs text-muted-foreground mt-1">
											{t("settings.notificationsDescription")}
										</p>
									</div>
									<Switch
										checked={notifications}
										onCheckedChange={setNotifications}
										className="data-[state=checked]:bg-danger"
									/>
								</div>
								<div className="pt-4">
									<Button
										className="bg-danger hover:bg-danger/90 text-white border-none"
										onClick={handleSaveGeneral}
									>
										{t("settings.save")}
									</Button>
								</div>
							</CardContent>
						</Card>
					</TabsContent>

					{/* Security Settings */}
					<TabsContent value="security">
						<Card className="border-border bg-card">
							<CardHeader className="pb-3">
								<CardTitle className="text-lg text-foreground">
									{t("settings.security")}
								</CardTitle>
								<CardDescription className="text-muted-foreground">
									{t("settings.securityDescription")}
								</CardDescription>
							</CardHeader>
							<CardContent className="space-y-4">
								<div className="flex items-center justify-between py-3">
									<div>
										<Label className="text-foreground/90">
											{t("settings.twoFactorAuth")}
										</Label>
										<p className="text-xs text-muted-foreground mt-1">
											{t("settings.twoFactorAuthDescription")}
										</p>
									</div>
									<Switch
										checked={twoFactorAuth}
										onCheckedChange={setTwoFactorAuth}
										className="data-[state=checked]:bg-danger"
									/>
								</div>
								<div className="space-y-2">
									<Label className="text-foreground/90">
										{t("settings.passwordExpiry")}
									</Label>
									<Input
										type="number"
										value={passwordExpiry}
										onChange={(e) =>
											setPasswordExpiry(parseInt(e.target.value, 10))  // NOSONAR - typescript:S7773
										}
										className="bg-card border-border text-foreground"
									/>
									<p className="text-xs text-muted-foreground">
										{t("settings.passwordExpiryDescription")}
									</p>
								</div>
								<div className="pt-4">
									<Button
										className="bg-danger hover:bg-danger/90 text-white border-none"
										onClick={handleSaveSecurity}
									>
										{t("settings.save")}
									</Button>
								</div>
							</CardContent>
						</Card>
					</TabsContent>

					{/* API Settings */}
					<TabsContent value="api">
						<Card className="border-border bg-card">
							<CardHeader className="pb-3">
								<CardTitle className="text-lg text-foreground">
									{t("settings.api")}
								</CardTitle>
								<CardDescription className="text-muted-foreground">
									{t("settings.apiDescription")}
								</CardDescription>
							</CardHeader>
							<CardContent className="space-y-4">
								<div className="grid grid-cols-1 md:grid-cols-2 gap-4">
									<div className="space-y-2">
										<Label className="text-foreground/90">
											{t("settings.apiTimeout")}
										</Label>
										<Input
											type="number"
											value={apiTimeout}
											onChange={(e) =>
												setApiTimeout(parseInt(e.target.value, 10))  // NOSONAR - typescript:S7773
											}
											className="bg-card border-border text-foreground"
										/>
										<p className="text-xs text-muted-foreground">
											{t("settings.apiTimeoutDescription")}
										</p>
									</div>
									<div className="space-y-2">
										<Label className="text-foreground/90">
											{t("settings.retryAttempts")}
										</Label>
										<Input
											type="number"
											value={retryAttempts}
											onChange={(e) =>
												setRetryAttempts(parseInt(e.target.value, 10))  // NOSONAR - typescript:S7773
											}
											className="bg-card border-border text-foreground"
										/>
										<p className="text-xs text-muted-foreground">
											{t("settings.retryAttemptsDescription")}
										</p>
									</div>
								</div>
								<div className="pt-4">
									<Button
										className="bg-danger hover:bg-danger/90 text-white border-none"
										onClick={handleSaveApi}
									>
										{t("settings.save")}
									</Button>
								</div>
							</CardContent>
						</Card>
					</TabsContent>

					{/* Report Settings */}
					<TabsContent value="reports">
						<Card className="border-border bg-card">
							<CardHeader className="pb-3">
								<CardTitle className="text-lg text-foreground">
									{t("settings.reports")}
								</CardTitle>
								<CardDescription className="text-muted-foreground">
									{t("settings.reportGeneratorDesc")}
								</CardDescription>
							</CardHeader>
							<CardContent className="space-y-4">
								<div className="flex items-center justify-between py-3">
									<div>
										<Label className="text-foreground/90">
											{t("settings.autoSaveReports")}
										</Label>
										<p className="text-xs text-muted-foreground mt-1">
											{t("settings.autoSaveReportsDesc")}
										</p>
									</div>
									<Switch
										checked={autoSaveReports}
										onCheckedChange={setAutoSaveReports}
										className="data-[state=checked]:bg-danger"
									/>
								</div>
								<div className="grid grid-cols-1 md:grid-cols-2 gap-4">
									<div className="space-y-2">
										<Label className="text-foreground/90">
											{t("settings.reportFormat")}
										</Label>
										<select
											value={reportFormat}
											onChange={(e) => setReportFormat(e.target.value)}
											className="w-full bg-card border border-border rounded px-3 py-2 text-foreground"
										>
											<option value="pdf">PDF</option>
											<option value="json">JSON</option>
											<option value="excel">Excel</option>
											<option value="xml">XML</option>
										</select>
										<p className="text-xs text-muted-foreground">
											{t("settings.reportFormatDesc")}
										</p>
									</div>
									<div className="space-y-2">
										<Label className="text-foreground/90">
											{t("settings.reportQuality")}
										</Label>
										<select
											value={reportQuality}
											onChange={(e) => setReportQuality(e.target.value)}
											className="w-full bg-card border border-border rounded px-3 py-2 text-foreground"
										>
											<option value="low">Low (Fast)</option>
											<option value="medium">Medium</option>
											<option value="high">High (Detailed)</option>
										</select>
										<p className="text-xs text-muted-foreground">
											{t("settings.reportQualityDesc")}
										</p>
									</div>
								</div>
								<div className="pt-4">
									<Button
										className="bg-danger hover:bg-danger/90 text-white border-none"
										onClick={handleSaveReports}
									>
										{t("settings.saveReportSettings")}
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
