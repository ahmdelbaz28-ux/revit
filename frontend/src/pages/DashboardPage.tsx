import {
	Activity,
	AlertTriangle,
	Calculator,
	CheckCircle2,
	Clock,
	Database,
	Server,
	XCircle,
} from "lucide-react";
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
import { Skeleton } from "@/components/ui/skeleton";
import { useDevices, useHealth, useProjects } from "@/hooks/useApi";

export function DashboardPage() {
	const { t } = useTranslation();
	const navigate = useNavigate();
	const {
		data: health,
		loading: healthLoading,
		connected,
		refetch: refetchHealth,
	} = useHealth();
	const {
		data: projects,
		loading: projectsLoading,
		error: projectsError,
	} = useProjects();
	const {
		data: devices,
		loading: devicesLoading,
		error: devicesError,
	} = useDevices(null); // Pass null as projectId

	// Calculate stats
	const totalProjects = projects?.length || 0;
	const totalDevices = devices?.length || 0; // Use devices length instead of deviceCount property
	const activeProjects =
		projects?.filter((p) => p.status === "active").length || 0;

	// Since Device interface doesn't have a status property, we'll use placeholder values
	// In a real implementation, you would need to get this information from the API differently
	const warningDevices = 0; // Placeholder - Device doesn't have status property
	const dangerDevices = 0; // Placeholder - Device doesn't have status property
	const okDevices = totalDevices - warningDevices - dangerDevices;

	return (
		<div className="flex-1 overflow-auto" aria-label={t("dashboard.title")}>
			<div className="p-6 max-w-7xl mx-auto space-y-6">
				{/* Header */}
				<div className="flex items-center justify-between">
					<div>
						<h1 className="text-2xl font-bold text-slate-100">
							{t("dashboard.title")}
						</h1>
						<p className="text-sm text-slate-400 mt-1">
							{t("dashboard.subtitle")}
						</p>
					</div>
					<Button
						variant="outline"
						className="border-slate-600 text-slate-300 hover:bg-slate-800"
						onClick={() => refetchHealth()}
					>
						<Activity className="h-4 w-4 mr-1" />
						{t("dashboard.refresh")}
					</Button>
				</div>

				{/* Stats Cards */}
				<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
					{/* Projects Card */}
					<Card className="border-slate-700 bg-slate-800">
						<CardHeader className="pb-3">
							<CardTitle className="text-lg text-slate-100">
								{t("dashboard.projects")}
							</CardTitle>
							<CardDescription className="text-slate-400">
								{t("dashboard.acrossAllProjects")}
							</CardDescription>
						</CardHeader>
						<CardContent>
							{projectsLoading ? (
								<Skeleton className="h-8 w-16 bg-slate-700" />
							) : (
								<div className="text-3xl font-bold text-slate-100">
									{totalProjects}
								</div>
							)}
						</CardContent>
					</Card>

					{/* Active Projects Card */}
					<Card className="border-slate-700 bg-slate-800">
						<CardHeader className="pb-3">
							<CardTitle className="text-lg text-slate-100">
								{t("dashboard.active")}
							</CardTitle>
							<CardDescription className="text-slate-400">
								{t("dashboard.projects")}
							</CardDescription>
						</CardHeader>
						<CardContent>
							{projectsLoading ? (
								<Skeleton className="h-8 w-16 bg-slate-700" />
							) : (
								<div className="text-3xl font-bold text-red-600">
									{activeProjects}
								</div>
							)}
						</CardContent>
					</Card>

					{/* Total Devices Card */}
					<Card className="border-slate-700 bg-slate-800">
						<CardHeader className="pb-3">
							<CardTitle className="text-lg text-slate-100">
								{t("dashboard.totalDevices")}
							</CardTitle>
							<CardDescription className="text-slate-400">
								{t("dashboard.acrossAllProjects")}
							</CardDescription>
						</CardHeader>
						<CardContent>
							{devicesLoading ? (
								<Skeleton className="h-8 w-16 bg-slate-700" />
							) : (
								<div className="text-3xl font-bold text-slate-100">
									{totalDevices}
								</div>
							)}
						</CardContent>
					</Card>

					{/* System Health Card */}
					<Card className="border-slate-700 bg-slate-800">
						<CardHeader className="pb-3">
							<CardTitle className="text-lg text-slate-100">
								{t("dashboard.systemHealth")}
							</CardTitle>
							<CardDescription className="text-slate-400">
								{t("dashboard.status")}
							</CardDescription>
						</CardHeader>
						<CardContent>
							{healthLoading ? (
								<Skeleton className="h-8 w-24 bg-slate-700" />
							) : (
								<div className="flex items-center gap-2">
									{connected ? (
										<>
											<CheckCircle2 className="h-5 w-5 text-emerald-400" />
											<span className="text-emerald-400">
												{t("dashboard.connected")}
											</span>
										</>
									) : (
										<>
											<XCircle className="h-5 w-5 text-red-400" />
											<span className="text-red-400">
												{t("dashboard.disconnected")}
											</span>
										</>
									)}
								</div>
							)}
						</CardContent>
					</Card>
				</div>

				{/* Status Summary Card */}
				<Card className="border-slate-700 bg-slate-800">
					<CardHeader className="pb-3">
						<CardTitle className="text-lg text-slate-100">
							{t("dashboard.statusSummary")}
						</CardTitle>
						<CardDescription className="text-slate-400">
							{t("dashboard.deviceStatusOverview")}
						</CardDescription>
					</CardHeader>
					<CardContent>
						<div className="grid grid-cols-1 md:grid-cols-3 gap-4">
							<div className="flex items-center gap-3">
								<div className="w-10 h-10 rounded-full bg-emerald-500/20 flex items-center justify-center">
									<CheckCircle2 className="h-5 w-5 text-emerald-400" />
								</div>
								<div>
									<div className="text-2xl font-bold text-emerald-400">
										{okDevices}
									</div>
									<div className="text-sm text-slate-400">
										{t("dashboard.ok")}
									</div>
								</div>
							</div>
							<div className="flex items-center gap-3">
								<div className="w-10 h-10 rounded-full bg-amber-500/20 flex items-center justify-center">
									<AlertTriangle className="h-5 w-5 text-amber-400" />
								</div>
								<div>
									<div className="text-2xl font-bold text-amber-400">
										{warningDevices}
									</div>
									<div className="text-sm text-slate-400">
										{t("dashboard.warning")}
									</div>
								</div>
							</div>
							<div className="flex items-center gap-3">
								<div className="w-10 h-10 rounded-full bg-red-500/20 flex items-center justify-center">
									<XCircle className="h-5 w-5 text-red-400" />
								</div>
								<div>
									<div className="text-2xl font-bold text-red-400">
										{dangerDevices}
									</div>
									<div className="text-sm text-slate-400">
										{t("dashboard.danger")}
									</div>
								</div>
							</div>
						</div>
					</CardContent>
				</Card>

				{/* System Health Details */}
				<Card className="border-slate-700 bg-slate-800">
					<CardHeader className="pb-3">
						<CardTitle className="text-lg text-slate-100">
							{t("dashboard.systemHealth")}
						</CardTitle>
						<CardDescription className="text-slate-400">
							{healthLoading
								? t("dashboard.loading")
								: t("dashboard.lastUpdated") +
									": " +
									(health ? new Date().toLocaleString() : "")}
						</CardDescription>
					</CardHeader>
					<CardContent>
						{healthLoading ? (
							<div className="space-y-3">
								<Skeleton className="h-4 w-full bg-slate-700" />
								<Skeleton className="h-4 w-4/5 bg-slate-700" />
								<Skeleton className="h-4 w-3/4 bg-slate-700" />
							</div>
						) : health ? (
							<div className="grid grid-cols-1 md:grid-cols-3 gap-4">
								<div className="flex items-center gap-2">
									<Server className="h-5 w-5 text-blue-400" />
									<span className="text-slate-300">
										{t("dashboard.version")}: v{health.version}
									</span>
								</div>
								<div className="flex items-center gap-2">
									<Database className="h-5 w-5 text-blue-400" />
									<span className="text-slate-300">
										{t("dashboard.database")}: {health.database}
									</span>
								</div>
								<div className="flex items-center gap-2">
									<Clock className="h-5 w-5 text-blue-400" />
									<span className="text-slate-300">
										{t("dashboard.uptime")}:{" "}
										{Math.floor((health.uptime || 0) / 60)} min
									</span>
								</div>
							</div>
						) : (
							<p className="text-slate-400">{t("dashboard.disconnected")}</p>
						)}
					</CardContent>
				</Card>

				{/* Report Generator Quick Access */}
				<Card className="border-slate-700 bg-slate-800">
					<CardHeader className="pb-3">
						<CardTitle className="text-lg text-slate-100">
							{t("settings.advancedReportGenerator")}
						</CardTitle>
						<CardDescription className="text-slate-400">
							{t("settings.reportGeneratorDesc")}
						</CardDescription>
					</CardHeader>
					<CardContent>
						<div className="flex flex-col sm:flex-row gap-4">
							<div className="flex-1">
								<h3 className="font-medium text-slate-200 mb-2">
									{t("settings.comprehensiveReportGeneration")}
								</h3>
								<p className="text-sm text-slate-400">
									{t("settings.comprehensiveReportDesc")}
								</p>
							</div>
							<Button
								onClick={() => navigate("/reports")}
								className="bg-red-600 hover:bg-red-700 text-white border-none flex items-center gap-2"
								aria-label={t("settings.openReportGenerator")}
							>
								<Calculator className="h-4 w-4" />
								{t("settings.openReportGenerator")}
							</Button>
						</div>
					</CardContent>
				</Card>
			</div>
		</div>
	);
}
