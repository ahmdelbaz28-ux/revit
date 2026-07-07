// NOSONAR
/**
 * ReportGeneratorPage.tsx - Advanced report generator matching the new UI design
 */

import {
	Activity,
	Activity as ActivityIcon,
	Battery,
	Calculator,
	Download,
	FileText,
	FolderKanban,
	Plus,
	RefreshCw,
	Ruler,
	ShieldAlert,
	Zap,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { useProjects, useReports } from "@/hooks/useApi";
import type {
	GenerateReportInput,
	Project,
	Report,
} from "@/services/digitalTwinApi";
import { api } from "@/services/digitalTwinApi";

// ============================================================================
// Report type definitions matching the PNG design
// ============================================================================

const REPORT_TYPES = [
	{
		id: "nfpa_72_coverage",
		label: "NFPA 72 Coverage",
		description: "Detector spacing and acoustic analysis per code.",
	},
	{
		id: "battery",
		label: "Battery",
		description: "Standby and alarm capacity calculations.",
	},
	{
		id: "voltage_drop",
		label: "Voltage Drop",
		description: "End-of-line voltage deterministic analysis.",
	},
	{
		id: "complete_compliance",
		label: "Complete Compliance",
		description: "Full system audit against AHJ requirements.",
	},
	{
		id: "cause_effect",
		label: "Cause & Effect",
		description: "Logic matrix for input/output correlations.",
	},
	{
		id: "cable_schedule",
		label: "Cable Schedule",
		description: "Wiring paths, lengths, and gauge specs.",
	},
] as const;

// ============================================================================
// ReportGeneratorPage Component
// ============================================================================

export function ReportGeneratorPage() {
	const { t } = useTranslation(); // NOSONAR — acceptable in this context
	const {
		data: projects,
		loading: projectsLoading,
	} = useProjects();
	const [selectedProjectId, setSelectedProjectId] = useState<string | null>(
		null,
	);

	const {
		data: reports,
		loading: reportsLoading,
		error: reportsError,
		refetch: refetchReports,
	} = useReports(selectedProjectId);

	const [showGenerateForm, setShowGenerateForm] = useState(false);
	const [reportType, setReportType] = useState("nfpa_72_coverage");
	const [reportName, setReportName] = useState("");
	const [targetScope, setTargetScope] = useState("ENTIRE_PROJECT");
	const [outputFormat, setOutputFormat] = useState("PDF_STRICT_COMPLIANCE");
	const [includeDisabledDevices, setIncludeDisabledDevices] = useState(false);
	const [safetyMarginPadding, setSafetyMarginPadding] = useState(false);
	const [generating, setGenerating] = useState(false);
	const [generateError, setGenerateError] = useState<string | null>(null);
	const [exporting, setExporting] = useState<string | null>(null);

	const selectedProject =
		projects?.find((p: Project) => p.id === selectedProjectId) || null;

	// ---------------------------------------------------------------------------
	// Handlers
	// ---------------------------------------------------------------------------

	const handleGenerateReport = async () => {
		if (!selectedProjectId) return;
		setGenerating(true);
		setGenerateError(null);
		try {
			const input: GenerateReportInput = {
				type: reportType,
				name:
					reportName.trim() ||
					REPORT_TYPES.find((t) => t.id === reportType)?.label ||
					reportType,
				parameters: {
					targetScope,
					outputFormat,
					includeDisabledDevices,
					safetyMarginPadding,
				},
			};
			const res = await api.generateReport(selectedProjectId, input);
			if (res.success) {
				setShowGenerateForm(false);
				setReportName("");
				refetchReports();
			} else {
				setGenerateError(res.error || "Failed to generate report");
			}
		} catch (err: unknown) {
			setGenerateError(err instanceof Error ? err.message : "Network error");
		} finally {
			setGenerating(false);
		}
	};

	const handleExportReport = async (report: Report, format: string) => {
		if (!selectedProjectId) return;
		setExporting(report.id);
		try {
			const blob = await api.exportReport(selectedProjectId, report.id, format);
			// Download the blob
			const url = window.URL.createObjectURL(blob);
			const a = document.createElement("a");
			a.href = url;
			a.download = `${report.name || report.type}_${report.id.slice(0, 8)}.${format === "pdf" ? "pdf" : "json"}`;
			document.body.appendChild(a);
			a.click();
			document.body.removeChild(a);  // NOSONAR — S7762: acceptable
			window.URL.revokeObjectURL(url);
		} catch {
			// Export may fail if backend doesn't support it
			console.error("Export failed");
		} finally {
			setExporting(null);
		}
	};

	// ---------------------------------------------------------------------------
	// Report type icon helper
	// ---------------------------------------------------------------------------

	const getReportIcon = (type: string) => {
		switch (type) {
			case "nfpa_72_coverage":
				return <Zap className="h-4 w-4" />;
			case "battery":
				return <Battery className="h-4 w-4" />;
			case "voltage_drop":
				return <Zap className="h-4 w-4" />;
			case "complete_compliance":
				return <ShieldAlert className="h-4 w-4" />;
			case "cause_effect":
				return <ActivityIcon className="h-4 w-4" />;
			case "cable_schedule":
				return <Ruler className="h-4 w-4" />;
			default:
				return <FileText className="h-4 w-4" />;
		}
	};

	// ---------------------------------------------------------------------------
	// Render
	// ---------------------------------------------------------------------------

	return (
		<div className="flex-1 overflow-auto" aria-label="Report Generator">
			<div className="p-6 max-w-7xl mx-auto space-y-6">
				{/* Header */}
				<div className="flex items-center justify-between">
					<div>
						<h1 className="text-2xl font-bold text-slate-100">
							Report Generator
						</h1>
						<p className="text-sm text-slate-400 mt-1">
							Generate deterministic analysis reports
						</p>
					</div>
					<div className="flex items-center gap-3">
						{selectedProjectId && (
							<Button
								variant="outline"
								size="sm"
								className="border-slate-600 text-slate-300"
								onClick={() => refetchReports()}
							>
								<RefreshCw className="h-4 w-4 mr-1" /> Refresh
							</Button>
						)}
					</div>
				</div>

				{/* Project Selector */}
				<Card className="border-slate-700 bg-slate-800">
					<CardHeader className="pb-3">
						<CardTitle className="text-lg text-slate-100">
							Select Project
						</CardTitle>
						<CardDescription className="text-slate-400">
							Choose a project to generate reports for
						</CardDescription>
					</CardHeader>
					<CardContent>
						{projectsLoading ? (
							<div className="flex items-center gap-2 text-slate-400">
								<Activity className="h-4 w-4 animate-pulse" />
								<span className="text-sm">Loading projects...</span>
							</div>
						) : !projects || projects.length === 0 ? (  // NOSONAR — S3358: nested ternary acceptable in this localized context
							<div className="text-center py-6 text-slate-400">
								<FolderKanban className="h-8 w-8 mx-auto mb-2 opacity-50" />
								<p className="text-sm">
									No projects available. Create a project first.
								</p>
							</div>
						) : (
							<Select
								value={selectedProjectId || ""}
								onValueChange={(v) => {
									setSelectedProjectId(v);
									setShowGenerateForm(false);
								}}
							>
								<SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
									<SelectValue placeholder="Choose a project..." />
								</SelectTrigger>
								<SelectContent className="bg-slate-800 border-slate-700">
									{projects.map((project: Project) => (
										<SelectItem key={project.id} value={project.id}>
											{project.name} ({project.deviceCount || 0} devices)
										</SelectItem>
									))}
								</SelectContent>
							</Select>
						)}
					</CardContent>
				</Card>

				{/* Report content for selected project */}
				{selectedProjectId && selectedProject && (
					<>
						{/* Generate Report */}
						<div className="flex items-center justify-between">
							<h2 className="text-lg font-medium text-slate-200">
								Reports for {selectedProject.name}
							</h2>
							<Button
								size="sm"
								className="bg-red-600 hover:bg-red-700 text-white border-none"
								onClick={() => {
									setGenerateError(null);
									setShowGenerateForm(true);
								}}
							>
								<Plus className="h-4 w-4 mr-1" /> Generate Report
							</Button>
						</div>

						{/* Generate Form - matches PNG design */}
						{showGenerateForm && (
							<Card className="border-slate-700 bg-slate-800">
								<CardHeader className="pb-3">
									<CardTitle className="text-lg text-slate-100">
										Generate New Report
									</CardTitle>
									<CardDescription className="text-slate-400">
										Configure and generate your analysis report
									</CardDescription>
								</CardHeader>
								<CardContent className="space-y-6">
									{generateError && (
										<div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3">
											<p className="text-sm text-red-400">{generateError}</p>
										</div>
									)}

									{/* Report Type Selection */}
									<div className="space-y-2">
										<Label className="text-slate-300 text-xs uppercase tracking-wider">
											Report Type
										</Label>
										<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
											{REPORT_TYPES.map((type) => (
												<button
													key={type.id}
													className={`p-4 rounded-lg border text-left transition-all ${
														reportType === type.id
															? "border-red-500 bg-red-500/10"
															: "border-slate-700 bg-slate-900/50 hover:border-slate-600"
													}`}
													onClick={() => setReportType(type.id)}
												>
													<div className="flex items-start gap-3">
														<div
															className={`p-2 rounded ${
																reportType === type.id
																	? "bg-red-500/20"
																	: "bg-slate-800/50"
															}`}
														>
															{getReportIcon(type.id)}
														</div>
														<div className="flex-1 min-w-0">
															<div
																className={`font-medium ${
																	reportType === type.id
																		? "text-red-400"
																		: "text-slate-200"
																}`}
															>
																{type.label}
															</div>
															<div className="text-xs text-slate-400 mt-1 line-clamp-2">
																{type.description}
															</div>
														</div>
													</div>
												</button>
											))}
										</div>
									</div>

									{/* Execution Parameters */}
									<div className="space-y-4">
										<h3 className="text-sm font-medium text-slate-200 uppercase tracking-wider">
											Execution Parameters
										</h3>

										<div className="grid grid-cols-1 md:grid-cols-2 gap-4">
											<div className="space-y-2">
												<Label className="text-slate-300 text-xs">
													Target Scope
												</Label>
												<Select
													value={targetScope}
													onValueChange={setTargetScope}
												>
													<SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
														<SelectValue />
													</SelectTrigger>
													<SelectContent className="bg-slate-800 border-slate-700">
														<SelectItem value="ENTIRE_PROJECT">
															Entire Project
														</SelectItem>
														<SelectItem value="SPECIFIC_AREA">
															Specific Area
														</SelectItem>
														<SelectItem value="SELECTED_DEVICES">
															Selected Devices
														</SelectItem>
													</SelectContent>
												</Select>
											</div>

											<div className="space-y-2">
												<Label className="text-slate-300 text-xs">
													Output Format
												</Label>
												<Select
													value={outputFormat}
													onValueChange={setOutputFormat}
												>
													<SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
														<SelectValue />
													</SelectTrigger>
													<SelectContent className="bg-slate-800 border-slate-700">
														<SelectItem value="PDF_STRICT_COMPLIANCE">
															PDF - Strict Compliance
														</SelectItem>
														<SelectItem value="PDF_ENGINEERING">
															PDF - Engineering
														</SelectItem>
														<SelectItem value="JSON_RAW">
															JSON - Raw Data
														</SelectItem>
														<SelectItem value="EXCEL_DETAILED">
															Excel - Detailed
														</SelectItem>
													</SelectContent>
												</Select>
											</div>
										</div>
									</div>

									{/* Kernel Coverage Options */}
									<div className="space-y-4">
										<h3 className="text-sm font-medium text-slate-200 uppercase tracking-wider">
											Kernel Coverage
										</h3>

										<div className="flex items-center justify-between p-4 rounded-lg border border-slate-700 bg-slate-900/30">
											<div className="flex items-center gap-3">
												<input
													type="checkbox"
													id="include-disabled-devices"
													checked={includeDisabledDevices}
													onChange={(e) =>
														setIncludeDisabledDevices(e.target.checked)
													}
													className="h-4 w-4 text-red-500 rounded border-slate-600 bg-slate-800 focus:ring-red-500 focus:ring-offset-slate-800"
												/>
												<div>
													<Label
														htmlFor="include-disabled-devices"
														className="text-slate-200 font-medium"
													>
														Include Disabled Devices
													</Label>
													<p className="text-xs text-slate-400 mt-1">
														Include devices marked as disabled in the
														computation
													</p>
												</div>
											</div>
										</div>

										<div className="flex items-center justify-between p-4 rounded-lg border border-slate-700 bg-slate-900/30">
											<div className="flex items-center gap-3">
												<input
													type="checkbox"
													id="safety-margin-padding"
													checked={safetyMarginPadding}
													onChange={(e) =>
														setSafetyMarginPadding(e.target.checked)
													}
													className="h-4 w-4 text-red-500 rounded border-slate-600 bg-slate-800 focus:ring-red-500 focus:ring-offset-slate-800"
												/>
												<div>
													<Label
														htmlFor="safety-margin-padding"
														className="text-slate-200 font-medium"
													>
														Safety Margin Padding
													</Label>
													<p className="text-xs text-slate-400 mt-1">
														Apply additional safety margin padding to
														calculations
													</p>
												</div>
											</div>
										</div>
									</div>

									{/* Kernel Information */}
									<div className="p-4 rounded-lg border border-slate-700 bg-slate-900/30">
										<div className="flex items-center gap-2 mb-2">
											<Calculator className="h-4 w-4 text-blue-400" />
											<h4 className="text-sm font-medium text-slate-200 uppercase tracking-wider">
												QOMN-FIRE Deterministic Kernel
											</h4>
										</div>
										<div className="text-xs text-slate-400 space-y-1">
											<div>
												v4.2.1 - IEEE-754 Floating Point Deterministic
												Verification
											</div>
											<div>© Eng. Ahmed Elbaz - All Rights Reserved</div>
										</div>
									</div>

									<div className="flex gap-2 pt-2">
										<Button
											className="bg-red-600 hover:bg-red-700 text-white border-none flex-1"
											onClick={handleGenerateReport}
											disabled={generating}
										>
											{generating ? "Generating..." : "Generate Report"}
										</Button>
										<Button
											variant="outline"
											className="border-slate-600 text-slate-300 flex-1"
											onClick={() => {
												setShowGenerateForm(false);
												setReportName("");
											}}
										>
											Cancel
										</Button>
									</div>
								</CardContent>
							</Card>
						)}

						{/* Error */}
						{reportsError && (
							<Card className="border-red-500/30 bg-red-500/5">
								<CardContent className="p-3">
									<p className="text-sm text-red-400">
										Error loading reports: {reportsError}
									</p>
								</CardContent>
							</Card>
						)}

						{/* Reports List */}
						<Card className="border-slate-700 bg-slate-800">
							<CardHeader className="pb-3">
								<CardTitle className="text-lg text-slate-100">
									Report History
								</CardTitle>
								<CardDescription className="text-slate-400">
									{reportsLoading
										? "Loading..."
										: `${reports?.length || 0} reports`}
								</CardDescription>
							</CardHeader>
							<CardContent>
								{reportsLoading ? (
									<div className="flex items-center justify-center py-8">
										<Activity className="h-5 w-5 text-slate-400 animate-pulse" />
										<span className="ml-2 text-slate-400">
											Loading reports...
										</span>
									</div>
								) : !reports || reports.length === 0 ? (  // NOSONAR — S3358: nested ternary acceptable in this localized context
									<div className="text-center py-8 text-slate-400">
										<FileText className="h-8 w-8 mx-auto mb-2 opacity-50" />
										<p className="text-sm">No reports generated yet</p>
										<p className="text-xs mt-1">
											Click "Generate Report" to create your first report
										</p>
									</div>
								) : (
									<ScrollArea className="max-h-96">
										<div className="space-y-2">
											{reports.map((report: Report) => (
												<div
													key={report.id}
													className="flex items-center justify-between p-4 rounded-lg bg-slate-900/50 border border-slate-700/50"
												>
													<div className="flex items-center gap-3">
														{getReportIcon(report.type)}
														<div>
															<div className="text-sm font-medium text-slate-200">
																{report.name || report.type}
															</div>
															<div className="text-xs text-slate-400 mt-0.5">
																{report.type
																	.replace(/_/g, " ")  // NOSONAR - typescript:S7781
																	.replace(/\b\w/g, (l) => l.toUpperCase())}
																{" • "}
																{new Date(report.createdAt).toLocaleString()}
															</div>
														</div>
													</div>
													<div className="flex items-center gap-3">
														{report.status === "completed" && (
															<div className="flex items-center gap-1">
																<Button
																	variant="ghost"
																	size="sm"
																	className="h-7 text-xs text-slate-400 hover:text-slate-200"
																	onClick={() =>
																		handleExportReport(report, "json")
																	}
																	disabled={exporting === report.id}
																>
																	<Download className="h-3 w-3 mr-1" /> JSON
																</Button>
																<Button
																	variant="ghost"
																	size="sm"
																	className="h-7 text-xs text-slate-400 hover:text-slate-200"
																	onClick={() =>
																		handleExportReport(report, "pdf")
																	}
																	disabled={exporting === report.id}
																>
																	<Download className="h-3 w-3 mr-1" /> PDF
																</Button>
															</div>
														)}
													</div>
												</div>
											))}
										</div>
									</ScrollArea>
								)}
							</CardContent>
						</Card>
					</>
				)}

				{/* No project selected state */}
				{selectedProjectId === null && (
					<Card className="border-slate-700 bg-slate-800">
						<CardContent className="py-16 text-center">
							<FileText className="h-16 w-16 mx-auto mb-4 text-slate-600" />
							<h3 className="text-lg font-medium text-slate-300">
								Select a Project
							</h3>
							<p className="text-sm text-slate-400 mt-2 max-w-md mx-auto">
								Choose a project above to generate NFPA 72 coverage, battery
								calculations, voltage drop analysis, and other engineering
								reports.
							</p>
						</CardContent>
					</Card>
				)}
			</div>
		</div>
	);
}
