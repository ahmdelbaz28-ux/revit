/**
 * MonitorPage.tsx — System monitoring dashboard.
 *
 * V217: New page — 6 backend endpoints now have UI.
 * Health, metrics, engine status, agent activity, security alerts.
 */
import { useState } from "react";
import { Activity, AlertCircle, Cpu, Loader2, ShieldAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { monitorApi } from "@/services/fullApi";
import { useToast } from "@/hooks/use-toast";

export function MonitorPage() {
	const { toast } = useToast();
	const [loading, setLoading] = useState(false);
	const [health, setHealth] = useState<Record<string, unknown> | null>(null);
	const [engineStatus, setEngineStatus] = useState<Record<string, unknown> | null>(null);
	const [agentActivity, setAgentActivity] = useState<unknown[]>([]);
	const [securityAlerts, setSecurityAlerts] = useState<unknown[]>([]);
	const [metrics, setMetrics] = useState<string>("");

	const handleHealth = async () => {
		setLoading(true);
		try {
			const res = await monitorApi.getHealth();
			setHealth(res as Record<string, unknown>);
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

	const handleEngineStatus = async () => {
		setLoading(true);
		try {
			const res = await monitorApi.getEngineStatus();
			setEngineStatus(res as Record<string, unknown>);
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

	const handleAgentActivity = async () => {
		setLoading(true);
		try {
			const res = await monitorApi.getAgentActivity({ limit: 20 });
			setAgentActivity((res as { activities?: unknown[] }).activities || []);
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

	const handleSecurityAlerts = async () => {
		setLoading(true);
		try {
			const res = await monitorApi.getSecurityAlerts({ limit: 20 });
			setSecurityAlerts((res as { alerts?: unknown[] }).alerts || []);
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

	const handleMetrics = async () => {
		setLoading(true);
		try {
			const res = await monitorApi.getMetrics();
			setMetrics(res as string);
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

	return (
		<div className="flex-1 overflow-auto">
			<div className="p-6 max-w-5xl mx-auto space-y-6">
				<div>
					<h1 className="text-lg font-semibold text-foreground flex items-center gap-2">
						<Activity className="h-5 w-5 text-primary" />
						System Monitor
					</h1>
					<p className="text-sm text-muted-foreground mt-1">
						Engine health · Agent activity · Security alerts · Prometheus metrics
					</p>
				</div>

				{/* Quick Actions */}
				<div className="grid grid-cols-2 md:grid-cols-5 gap-3">
					<Button onClick={handleHealth} disabled={loading} variant="outline">
						{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Activity className="h-4 w-4" />}
						Health
					</Button>
					<Button onClick={handleEngineStatus} disabled={loading} variant="outline">
						{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Cpu className="h-4 w-4" />}
						Engine Status
					</Button>
					<Button onClick={handleAgentActivity} disabled={loading} variant="outline">
						{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Activity className="h-4 w-4" />}
						Agent Activity
					</Button>
					<Button onClick={handleSecurityAlerts} disabled={loading} variant="outline">
						{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldAlert className="h-4 w-4" />}
						Security Alerts
					</Button>
					<Button onClick={handleMetrics} disabled={loading} variant="outline">
						{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Activity className="h-4 w-4" />}
						Prometheus
					</Button>
				</div>

				{/* Health Status */}
				{health && (
					<Card>
						<CardHeader>
							<CardTitle className="flex items-center gap-2">
								<Activity className="h-4 w-4 text-success" />
								System Health
							</CardTitle>
						</CardHeader>
						<CardContent>
							<div className="grid grid-cols-2 md:grid-cols-4 gap-4">
								{Object.entries(health).map(([key, val]) => (
									<div key={key} className="space-y-1">
										<span className="text-xs text-muted-foreground uppercase tracking-wider">
											{key}
										</span>
										<div className="text-sm font-mono text-foreground">
											{typeof val === "boolean" ? (
												<Badge variant={val ? "default" : "destructive"}>
													{val ? "OK" : "FAIL"}
												</Badge>
											) : (
												String(val)
											)}
										</div>
									</div>
								))}
							</div>
						</CardContent>
					</Card>
				)}

				{/* Engine Status */}
				{engineStatus && (
					<Card>
						<CardHeader>
							<CardTitle className="flex items-center gap-2">
								<Cpu className="h-4 w-4 text-primary" />
								Engine Status
							</CardTitle>
						</CardHeader>
						<CardContent>
							<pre className="text-xs font-mono bg-muted p-3 rounded-md overflow-auto max-h-48">
								{JSON.stringify(engineStatus, null, 2)}
							</pre>
						</CardContent>
					</Card>
				)}

				{/* Agent Activity */}
				{agentActivity.length > 0 && (
					<Card>
						<CardHeader>
							<CardTitle>Agent Activity ({agentActivity.length})</CardTitle>
						</CardHeader>
						<CardContent>
							<div className="space-y-2 max-h-60 overflow-auto">
								{agentActivity.map((a, i) => {
									const activity = a as { timestamp: string; agent: string; action: string; status: string };
									return (
										<div
											key={i}
											className="flex items-center justify-between text-sm border-b border-border pb-2"
										>
											<span className="font-mono text-xs text-muted-foreground">
												{activity.timestamp}
											</span>
											<span className="text-foreground">{activity.agent}</span>
											<span className="text-muted-foreground">{activity.action}</span>
											<Badge
												variant={
													activity.status === "success"
														? "default"
														: activity.status === "error"
															? "destructive"
															: "secondary"
												}
											>
												{activity.status}
											</Badge>
										</div>
									);
								})}
							</div>
						</CardContent>
					</Card>
				)}

				{/* Security Alerts */}
				{securityAlerts.length > 0 && (
					<Card>
						<CardHeader>
							<CardTitle className="flex items-center gap-2">
								<ShieldAlert className="h-4 w-4 text-warning" />
								Security Alerts ({securityAlerts.length})
							</CardTitle>
						</CardHeader>
						<CardContent>
							<div className="space-y-2 max-h-60 overflow-auto">
								{securityAlerts.map((a, i) => {
									const alert = a as {
										timestamp: string;
										severity: string;
										type: string;
										message: string;
									};
									return (
										<div
											key={i}
											className="flex items-center gap-3 text-sm border-b border-border pb-2"
										>
											<AlertCircle
												className={`h-4 w-4 shrink-0 ${
													alert.severity === "critical"
														? "text-danger"
														: alert.severity === "high"
															? "text-warning"
															: "text-muted-foreground"
												}`}
											/>
											<span className="font-mono text-xs text-muted-foreground">
												{alert.timestamp}
											</span>
											<span className="text-foreground flex-1">{alert.message}</span>
											<Badge variant="outline" className="text-xs">
												{alert.type}
											</Badge>
										</div>
									);
								})}
							</div>
						</CardContent>
					</Card>
				)}

				{/* Prometheus Metrics */}
				{metrics && (
					<Card>
						<CardHeader>
							<CardTitle>Prometheus Metrics</CardTitle>
							<CardDescription>Raw /metrics endpoint output</CardDescription>
						</CardHeader>
						<CardContent>
							<pre className="text-xs font-mono bg-muted p-3 rounded-md overflow-auto max-h-96 whitespace-pre-wrap">
								{metrics}
							</pre>
						</CardContent>
					</Card>
				)}
			</div>
		</div>
	);
}
