/**
 * WorkflowPage.tsx — Engineering Workflow Management.
 *
 * V219: New page — 6 backend endpoints now have UI.
 * Start/monitor/approve/reject engineering workflows with audit trail.
 * Requires langgraph (optional dependency) — router auto-skips if missing.
 */
import { useState } from "react";
import {
	Workflow as WorkflowIcon,
	Loader2,
	Play,
	CheckCircle2,
	XCircle,
	History,
	RefreshCw,
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
import { Textarea } from "@/components/ui/textarea";
import { workflowApi } from "@/services/fullApi";
import { useToast } from "@/hooks/use-toast";

interface WorkflowStatus {
	status: string;
	workflow_type?: string;
	current_step?: string;
	steps?: Array<{ name: string; status: string; timestamp?: string }>;
}

const WORKFLOW_TYPES = [
	{ value: "design_review", label: "Design Review" },
	{ value: "compliance_check", label: "Compliance Check" },
	{ value: "device_placement", label: "Device Placement" },
	{ value: "report_generation", label: "Report Generation" },
];

const STATUS_VARIANTS: Record<string, "default" | "secondary" | "destructive"> = {
	running: "secondary",
	pending: "secondary",
	completed: "default",
	approved: "default",
	rejected: "destructive",
	failed: "destructive",
};

export function WorkflowPage() {
	const { toast } = useToast();
	const [loading, setLoading] = useState(false);
	const [globalStatus, setGlobalStatus] = useState<Record<string, unknown> | null>(null);
	const [activeWorkflow, setActiveWorkflow] = useState<WorkflowStatus | null>(null);
	const [auditTrail, setAuditTrail] = useState<unknown[]>([]);

	// Start form
	const [projectId, setProjectId] = useState("default-project");
	const [workflowType, setWorkflowType] = useState("design_review");
	const [workflowId, setWorkflowId] = useState("");

	// Approve/Reject
	const [approveComment, setApproveComment] = useState("");
	const [rejectReason, setRejectReason] = useState("");

	const handleStatus = async () => {
		setLoading(true);
		try {
			const res = await workflowApi.getStatus();
			setGlobalStatus(res as Record<string, unknown>);
		} catch (err) {
			toast({
				title: "Status Failed",
				description: err instanceof Error ? err.message : "Workflow engine may not be configured",
				variant: "destructive",
			});
		} finally {
			setLoading(false);
		}
	};

	const handleStart = async () => {
		setLoading(true);
		try {
			const res = await workflowApi.start({
				project_id: projectId,
				workflow_type: workflowType,
			});
			const data = res as { workflow_id?: string };
			if (data.workflow_id) {
				setWorkflowId(data.workflow_id);
				toast({
					title: "Workflow Started",
					description: `ID: ${data.workflow_id}`,
				});
			}
		} catch (err) {
			toast({
				title: "Start Failed",
				description: err instanceof Error ? err.message : "Failed",
				variant: "destructive",
			});
		} finally {
			setLoading(false);
		}
	};

	const handleGetStatus = async () => {
		if (!workflowId) {
			toast({ title: "Enter a workflow ID first", variant: "destructive" });
			return;
		}
		setLoading(true);
		try {
			const res = await workflowApi.getWorkflowStatus(workflowId);
			setActiveWorkflow(res as WorkflowStatus);
		} catch (err) {
			toast({
				title: "Failed",
				description: err instanceof Error ? err.message : "Failed",
				variant: "destructive",
			});
		} finally {
			setLoading(false);
		}
	};

	const handleApprove = async () => {
		if (!workflowId) return;
		setLoading(true);
		try {
			await workflowApi.approve(workflowId, { comment: approveComment || undefined });
			toast({ title: "Approved", description: "Workflow step approved." });
			setApproveComment("");
			handleGetStatus();
		} catch (err) {
			toast({
				title: "Approve Failed",
				description: err instanceof Error ? err.message : "Failed",
				variant: "destructive",
			});
		} finally {
			setLoading(false);
		}
	};

	const handleReject = async () => {
		if (!workflowId) return;
		setLoading(true);
		try {
			await workflowApi.reject(workflowId, { reason: rejectReason || "Rejected by engineer" });
			toast({ title: "Rejected", description: "Workflow step rejected.", variant: "destructive" });
			setRejectReason("");
			handleGetStatus();
		} catch (err) {
			toast({
				title: "Reject Failed",
				description: err instanceof Error ? err.message : "Failed",
				variant: "destructive",
			});
		} finally {
			setLoading(false);
		}
	};

	const handleAudit = async () => {
		if (!workflowId) return;
		setLoading(true);
		try {
			const res = await workflowApi.getAudit(workflowId);
			setAuditTrail((res as { entries?: unknown[] }).entries || []);
		} catch (err) {
			toast({
				title: "Audit Failed",
				description: err instanceof Error ? err.message : "Failed",
				variant: "destructive",
			});
		} finally {
			setLoading(false);
		}
	};

	return (
		<div className="flex-1 overflow-auto">
			<div className="p-6 max-w-5xl mx-auto space-y-6">
				<div>
					<h1 className="text-lg font-semibold text-foreground flex items-center gap-2">
						<WorkflowIcon className="h-5 w-5 text-primary" />
						Engineering Workflows
					</h1>
					<p className="text-sm text-muted-foreground mt-1">
						Start, monitor, approve, and reject engineering review workflows with audit trail
					</p>
				</div>

				{/* Engine Status */}
				<div className="flex items-center gap-3">
					<Button onClick={handleStatus} disabled={loading} variant="outline">
						{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
						Check Engine Status
					</Button>
					{globalStatus && (
						<div className="flex items-center gap-2">
							{Object.entries(globalStatus).map(([key, val]) => (
								<Badge
									key={key}
									variant={val === true || val === "running" ? "default" : "secondary"}
									className="text-xs"
								>
									{key}: {String(val)}
								</Badge>
							))}
						</div>
					)}
				</div>

				{/* Start New Workflow */}
				<Card>
					<CardHeader>
						<CardTitle>Start New Workflow</CardTitle>
						<CardDescription>
							Launch an engineering review or compliance check workflow
						</CardDescription>
					</CardHeader>
					<CardContent>
						<div className="grid grid-cols-1 md:grid-cols-3 gap-4">
							<div className="space-y-1.5">
								<Label className="text-xs text-muted-foreground">Project ID</Label>
								<Input
									value={projectId}
									onChange={(e) => setProjectId(e.target.value)}
									placeholder="default-project"
								/>
							</div>
							<div className="space-y-1.5">
								<Label className="text-xs text-muted-foreground">Workflow Type</Label>
								<Select value={workflowType} onValueChange={setWorkflowType}>
									<SelectTrigger>
										<SelectValue />
									</SelectTrigger>
									<SelectContent>
										{WORKFLOW_TYPES.map((wt) => (
											<SelectItem key={wt.value} value={wt.value}>
												{wt.label}
											</SelectItem>
										))}
									</SelectContent>
								</Select>
							</div>
							<div className="flex items-end">
								<Button onClick={handleStart} disabled={loading} className="w-full">
									{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
									Start
								</Button>
							</div>
						</div>
					</CardContent>
				</Card>

				{/* Workflow Monitor */}
				<Card>
					<CardHeader>
						<CardTitle>Workflow Monitor</CardTitle>
						<CardDescription>Check status of a running or completed workflow</CardDescription>
					</CardHeader>
					<CardContent>
						<div className="flex gap-2 mb-4">
							<Input
								value={workflowId}
								onChange={(e) => setWorkflowId(e.target.value)}
								placeholder="Enter workflow ID..."
							/>
							<Button onClick={handleGetStatus} disabled={loading || !workflowId} variant="outline">
								<RefreshCw className="h-4 w-4" />
								Refresh
							</Button>
							<Button onClick={handleAudit} disabled={loading || !workflowId} variant="ghost">
								<History className="h-4 w-4" />
								Audit
							</Button>
						</div>

						{activeWorkflow && (
							<div className="space-y-3">
								<div className="flex items-center gap-3">
									<span className="text-sm text-muted-foreground">Status:</span>
									<Badge variant={STATUS_VARIANTS[activeWorkflow.status] || "secondary"}>
										{activeWorkflow.status}
									</Badge>
									{activeWorkflow.workflow_type && (
										<span className="text-xs text-muted-foreground">
											{activeWorkflow.workflow_type}
										</span>
									)}
									{activeWorkflow.current_step && (
										<span className="text-xs text-muted-foreground">
											Step: {activeWorkflow.current_step}
										</span>
									)}
								</div>

								{activeWorkflow.steps && activeWorkflow.steps.length > 0 && (
									<div className="space-y-2">
										<Label className="text-xs text-muted-foreground">Steps</Label>
										{activeWorkflow.steps.map((step, i) => (
											<div
												key={i}
												className="flex items-center justify-between text-sm border-b border-border pb-2"
											>
												<span className="text-foreground">{step.name}</span>
												<Badge variant={STATUS_VARIANTS[step.status] || "secondary"} className="text-xs">
													{step.status}
												</Badge>
											</div>
										))}
									</div>
								)}

								{/* Approve / Reject */}
								{(activeWorkflow.status === "pending" || activeWorkflow.status === "running") && (
									<div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
										<div className="space-y-2">
											<Label className="text-xs text-muted-foreground">Approve with comment</Label>
											<div className="flex gap-2">
												<Input
													value={approveComment}
													onChange={(e) => setApproveComment(e.target.value)}
													placeholder="Optional comment..."
												/>
												<Button onClick={handleApprove} disabled={loading} size="icon">
													<CheckCircle2 className="h-4 w-4 text-success" />
												</Button>
											</div>
										</div>
										<div className="space-y-2">
											<Label className="text-xs text-muted-foreground">Reject with reason</Label>
											<div className="flex gap-2">
												<Input
													value={rejectReason}
													onChange={(e) => setRejectReason(e.target.value)}
													placeholder="Reason for rejection..."
												/>
												<Button onClick={handleReject} disabled={loading} size="icon" variant="destructive">
													<XCircle className="h-4 w-4" />
												</Button>
											</div>
										</div>
									</div>
								)}
							</div>
						)}
					</CardContent>
				</Card>

				{/* Audit Trail */}
				{auditTrail.length > 0 && (
					<Card>
						<CardHeader>
							<CardTitle className="flex items-center gap-2">
								<History className="h-4 w-4 text-primary" />
								Audit Trail ({auditTrail.length})
							</CardTitle>
						</CardHeader>
						<CardContent>
							<div className="space-y-2 max-h-60 overflow-auto">
								{auditTrail.map((entry, i) => {
									const e = entry as {
										timestamp: string;
										action: string;
										actor: string;
										detail?: string;
									};
									return (
										<div
											key={i}
											className="flex items-center gap-3 text-sm border-b border-border pb-2"
										>
											<span className="font-mono text-xs text-muted-foreground shrink-0">
												{e.timestamp}
											</span>
											<Badge variant="outline" className="text-xs shrink-0">
												{e.action}
											</Badge>
											<span className="text-foreground">{e.actor}</span>
											{e.detail && (
												<span className="text-muted-foreground text-xs truncate">{e.detail}</span>
											)}
										</div>
									);
								})}
							</div>
						</CardContent>
					</Card>
				)}
			</div>
		</div>
	);
}
