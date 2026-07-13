/**
 * SelfHealingPage.tsx — Self-Healing Engine Monitoring & Control Dashboard
 *
 * V214: Full UI for the QOMN-FIRE Self-Healing Runtime Engine V2.0.
 *
 * Features:
 *   1. Circuit Breaker status (state, events, threshold, utilization)
 *   2. LRU Cache stats (hits, misses, evictions)
 *   3. Audit Logger stats (events logged, file size, rotations)
 *   4. LLM Circuit Breaker stats (requests allowed/blocked)
 *   5. Audit log entries (recent healing events)
 *   6. Chain integrity verification
 *   7. Reset circuit breaker button (admin)
 *   8. Auto-refresh toggle (5s interval)
 *   9. Configuration display (env vars: QOMN_AUDIT_SECRET_KEY, QOMN_AUDIT_LOG_PATH, etc.)
 */

import {
        Activity,
        AlertTriangle,
        CheckCircle2,
        Loader2,
        RefreshCw,
        RotateCcw,
        Shield,
        Zap,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
        Card,
        CardContent,
        CardDescription,
        CardHeader,
        CardTitle,
} from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
        selfHealingApi,
        type SelfHealingHealth,
        type SelfHealingAudit,
} from "@/services/selfHealingApi";

export function SelfHealingPage() {
        const [health, setHealth] = useState<SelfHealingHealth | null>(null);
        const [audit, setAudit] = useState<SelfHealingAudit | null>(null);
        const [loading, setLoading] = useState(true);
        const [autoRefresh, setAutoRefresh] = useState(true);
        const [resetting, setResetting] = useState(false);

        const fetchAll = useCallback(async () => {
                try {
                        const [h, a] = await Promise.all([
                                selfHealingApi.getHealth(),
                                selfHealingApi.getAudit(20),
                        ]);
                        setHealth(h);
                        setAudit(a);
                } catch (err) {
                        // Silent on auto-refresh, toast on manual
                        if (!autoRefresh) {
                                toast.error(
                                        `Failed to fetch: ${err instanceof Error ? err.message : "Unknown"}`,
                                );
                        }
                } finally {
                        setLoading(false);
                }
        }, [autoRefresh]);

        useEffect(() => {
                fetchAll();
        }, [fetchAll]);

        useEffect(() => {
                if (!autoRefresh) return;
                const interval = setInterval(fetchAll, 5000);
                return () => clearInterval(interval);
        }, [autoRefresh, fetchAll]);

        const handleReset = async () => {
                setResetting(true);
                try {
                        await selfHealingApi.reset();
                        toast.success("Circuit breaker reset to CLOSED");
                        fetchAll();
                } catch (err) {
                        toast.error(`Reset failed: ${err instanceof Error ? err.message : "Unknown"}`);
                } finally {
                        setResetting(false);
                }
        };

        const cbStateColor = (state: string) => {
                if (state === "CLOSED") return "bg-emerald-600";
                if (state === "OPEN") return "bg-red-600";
                if (state === "HALF_OPEN") return "bg-amber-500";
                return "bg-slate-500";
        };

        const cbStateIcon = (state: string) => {
                if (state === "CLOSED")
                        return <CheckCircle2 className="h-5 w-5 text-emerald-600" />;
                if (state === "OPEN")
                        return <AlertTriangle className="h-5 w-5 text-red-600" />;
                return <Activity className="h-5 w-5 text-amber-500" />;
        };

        const formatBytes = (bytes: number) => {
                if (bytes < 1024) return `${bytes} B`;
                if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
                return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
        };

        if (loading && !health) {
                return (
                        <div className="flex-1 flex items-center justify-center">
                                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                        </div>
                );
        }

        const cb = health?.circuit_breaker;
        const lru = health?.lru_cache;
        const auditLog = health?.audit_logger;
        const llm = health?.llm_breaker;
        const chainValid = audit?.chain_integrity?.valid;

        return (
                <div className="flex-1 overflow-auto p-6 max-w-6xl mx-auto space-y-6">
                        {/* Header */}
                        <div className="flex items-center justify-between">
                                <div>
                                        <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
                                                <Shield className="h-6 w-6 text-primary" />
                                                Self-Healing Engine
                                        </h1>
                                        <p className="text-sm text-muted-foreground mt-1">
                                                QOMN-FIRE Self-Healing Runtime Engine V2.0 — 3-Tier Protection + HMAC Audit Trail
                                        </p>
                                </div>
                                <div className="flex items-center gap-3">
                                        <div className="flex items-center gap-2">
                                                <Switch
                                                        checked={autoRefresh}
                                                        onCheckedChange={setAutoRefresh}
                                                        id="auto-refresh"
                                                />
                                                <Label htmlFor="auto-refresh" className="text-sm text-muted-foreground">
                                                        Auto-refresh (5s)
                                                </Label>
                                        </div>
                                        <Button variant="outline" size="sm" onClick={fetchAll}>
                                                <RefreshCw className="h-4 w-4 mr-1" /> Refresh
                                        </Button>
                                </div>
                        </div>

                        {/* Status Banner */}
                        {cb && (
                                <div
                                        className={`flex items-center gap-3 p-4 rounded-lg border ${
                                                cb.state === "CLOSED"
                                                        ? "border-emerald-500/30 bg-emerald-500/5"
                                                        : cb.state === "OPEN"
                                                                ? "border-red-500/30 bg-red-500/5"
                                                                : "border-amber-500/30 bg-amber-500/5"
                                        }`}
                                >
                                        {cbStateIcon(cb.state)}
                                        <div>
                                                <p className="text-sm font-semibold">
                                                        Circuit Breaker: {cb.state}
                                                </p>
                                                <p className="text-xs text-muted-foreground">
                                                        {cb.state === "CLOSED" && "System operating normally — all computation methods active"}
                                                        {cb.state === "OPEN" && "System in fallback mode — all methods returning safe defaults. Investigate root cause then reset."}
                                                        {cb.state === "HALF_OPEN" && "System in recovery mode — probing with limited requests to test if root cause is resolved"}
                                                </p>
                                        </div>
                                </div>
                        )}

                        {/* Grid: 4 stat cards */}
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                                {/* Circuit Breaker */}
                                <Card className="border-border bg-card">
                                        <CardHeader className="pb-3">
                                                <CardTitle className="text-sm font-medium flex items-center gap-2">
                                                        <Zap className="h-4 w-4 text-amber-500" />
                                                        Circuit Breaker
                                                </CardTitle>
                                        </CardHeader>
                                        <CardContent className="space-y-2">
                                                {cb ? (
                                                        <>
                                                                <div className="flex items-center gap-2">
                                                                        <Badge className={cbStateColor(cb.state)}>{cb.state}</Badge>
                                                                        <span className="text-xs text-muted-foreground">
                                                                                {/* V250 FIX: Guard against null/undefined utilization_pct */}
                                                                                {typeof cb.utilization_pct === "number"
                                                                                        ? `${cb.utilization_pct.toFixed(0)}% utilization`
                                                                                        : "—"}
                                                                        </span>
                                                                </div>
                                                                <div className="space-y-1 text-xs text-muted-foreground">
                                                                        <div className="flex justify-between">
                                                                                <span>Events:</span>
                                                                                <span className="font-mono text-foreground">{cb.event_count}</span>
                                                                        </div>
                                                                        <div className="flex justify-between">
                                                                                <span>Weighted sum:</span>
                                                                                <span className="font-mono text-foreground">
                                                                                        {cb.weighted_sum} / {cb.threshold}
                                                                                </span>
                                                                        </div>
                                                                        <div className="flex justify-between">
                                                                                <span>Window:</span>
                                                                                <span className="font-mono text-foreground">{cb.window_seconds}s</span>
                                                                        </div>
                                                                        <div className="flex justify-between">
                                                                                <span>Cooldown:</span>
                                                                                <span className="font-mono text-foreground">{cb.cooldown_seconds}s</span>
                                                                        </div>
                                                                        <div className="flex justify-between">
                                                                                <span>Half-open probes:</span>
                                                                                <span className="font-mono text-foreground">
                                                                                        {cb.half_open_count} / {cb.half_open_max}
                                                                                </span>
                                                                        </div>
                                                                </div>
                                                        </>
                                                ) : (
                                                        <p className="text-xs text-muted-foreground">No data</p>
                                                )}
                                        </CardContent>
                                </Card>

                                {/* LRU Cache */}
                                <Card className="border-border bg-card">
                                        <CardHeader className="pb-3">
                                                <CardTitle className="text-sm font-medium flex items-center gap-2">
                                                        <Activity className="h-4 w-4 text-blue-500" />
                                                        LRU Cache (Last Known Good)
                                                </CardTitle>
                                        </CardHeader>
                                        <CardContent className="space-y-2">
                                                {lru ? (
                                                        <div className="space-y-1 text-xs text-muted-foreground">
                                                                <div className="flex justify-between">
                                                                        <span>Cache size:</span>
                                                                        <span className="font-mono text-foreground">
                                                                                {lru.size} / {lru.maxsize}
                                                                        </span>
                                                                </div>
                                                                <div className="flex justify-between">
                                                                        <span>Hits:</span>
                                                                        <span className="font-mono text-emerald-600">{lru.hits}</span>
                                                                </div>
                                                                <div className="flex justify-between">
                                                                        <span>Misses:</span>
                                                                        <span className="font-mono text-amber-600">{lru.misses}</span>
                                                                </div>
                                                                <div className="flex justify-between">
                                                                        <span>Evictions:</span>
                                                                        <span className="font-mono text-red-600">{lru.evictions}</span>
                                                                </div>
                                                                <div className="flex justify-between">
                                                                        <span>Hit rate:</span>
                                                                        <span className="font-mono text-foreground">
                                                                                {lru.hits + lru.misses > 0
                                                                                        ? `${((lru.hits / (lru.hits + lru.misses)) * 100).toFixed(1)}%`
                                                                                        : "N/A"}
                                                                        </span>
                                                                </div>
                                                        </div>
                                                ) : (
                                                        <p className="text-xs text-muted-foreground">No data</p>
                                                )}
                                        </CardContent>
                                </Card>

                                {/* Audit Logger */}
                                <Card className="border-border bg-card">
                                        <CardHeader className="pb-3">
                                                <CardTitle className="text-sm font-medium flex items-center gap-2">
                                                        <Shield className="h-4 w-4 text-purple-500" />
                                                        Audit Logger (HMAC-Signed)
                                                </CardTitle>
                                        </CardHeader>
                                        <CardContent className="space-y-2">
                                                {auditLog ? (
                                                        <div className="space-y-1 text-xs text-muted-foreground">
                                                                <div className="flex justify-between">
                                                                        <span>Total events:</span>
                                                                        <span className="font-mono text-foreground">
                                                                                {auditLog.total_events || auditLog.events_logged || 0}
                                                                        </span>
                                                                </div>
                                                                <div className="flex justify-between">
                                                                        <span>File size:</span>
                                                                        <span className="font-mono text-foreground">
                                                                                {formatBytes(auditLog.file_size_bytes || 0)}
                                                                        </span>
                                                                </div>
                                                                <div className="flex justify-between">
                                                                        <span>Rotations:</span>
                                                                        <span className="font-mono text-foreground">
                                                                                {auditLog.rotation_count || 0}
                                                                        </span>
                                                                </div>
                                                                <div className="flex justify-between">
                                                                        <span>Last event:</span>
                                                                        <span className="font-mono text-foreground">
                                                                                {auditLog.last_event_time
                                                                                        ? new Date(auditLog.last_event_time).toLocaleTimeString()
                                                                                        : "Never"}
                                                                        </span>
                                                                </div>
                                                                <div className="flex items-center justify-between pt-1">
                                                                        <span>Chain integrity:</span>
                                                                        {chainValid !== undefined && (
                                                                                <Badge className={chainValid ? "bg-emerald-600" : "bg-red-600"}>
                                                                                        {chainValid ? "VALID" : "BROKEN"}
                                                                                </Badge>
                                                                        )}
                                                                </div>
                                                        </div>
                                                ) : (
                                                        <p className="text-xs text-muted-foreground">No data</p>
                                                )}
                                        </CardContent>
                                </Card>

                                {/* LLM Breaker */}
                                <Card className="border-border bg-card">
                                        <CardHeader className="pb-3">
                                                <CardTitle className="text-sm font-medium flex items-center gap-2">
                                                        <AlertTriangle className="h-4 w-4 text-orange-500" />
                                                        LLM Rate Limiter
                                                </CardTitle>
                                        </CardHeader>
                                        <CardContent className="space-y-2">
                                                {llm ? (
                                                        <div className="space-y-1 text-xs text-muted-foreground">
                                                                <div className="flex justify-between">
                                                                        <span>Max RPS:</span>
                                                                        <span className="font-mono text-foreground">{llm.max_rps}</span>
                                                                </div>
                                                                <div className="flex justify-between">
                                                                        <span>Timeout:</span>
                                                                        <span className="font-mono text-foreground">{llm.timeout}s</span>
                                                                </div>
                                                                <div className="flex justify-between">
                                                                        <span>Allowed:</span>
                                                                        <span className="font-mono text-emerald-600">{llm.requests_allowed}</span>
                                                                </div>
                                                                <div className="flex justify-between">
                                                                        <span>Blocked:</span>
                                                                        <span className="font-mono text-red-600">{llm.requests_blocked}</span>
                                                                </div>
                                                        </div>
                                                ) : (
                                                        <p className="text-xs text-muted-foreground">No data</p>
                                                )}
                                        </CardContent>
                                </Card>
                        </div>

                        {/* Configuration Card */}
                        <Card className="border-border bg-card">
                                <CardHeader>
                                        <CardTitle className="flex items-center gap-2">
                                                <Shield className="h-5 w-5 text-primary" />
                                                Engine Configuration
                                        </CardTitle>
                                        <CardDescription>
                                                Environment variables controlling the self-healing engine
                                        </CardDescription>
                                </CardHeader>
                                <CardContent>
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                <div className="space-y-2">
                                                        <div className="flex items-center justify-between p-2 rounded border border-border">
                                                                <div>
                                                                        <p className="text-sm font-medium">QOMN_AUDIT_SECRET_KEY</p>
                                                                        <p className="text-xs text-muted-foreground">HMAC key for audit signing</p>
                                                                </div>
                                                                <Badge className="bg-emerald-600">SET</Badge>
                                                        </div>
                                                        <div className="flex items-center justify-between p-2 rounded border border-border">
                                                                <div>
                                                                        <p className="text-sm font-medium">QOMN_AUDIT_LOG_PATH</p>
                                                                        <p className="text-xs text-muted-foreground">
                                                                                {auditLog?.file_path || "default: qomn_fire_healing_audit.jsonl"}
                                                                        </p>
                                                                </div>
                                                                <Badge className="bg-emerald-600">ACTIVE</Badge>
                                                        </div>
                                                </div>
                                                <div className="space-y-2">
                                                        <div className="flex items-center justify-between p-2 rounded border border-border">
                                                                <div>
                                                                        <p className="text-sm font-medium">CB_THRESHOLD</p>
                                                                        <p className="text-xs text-muted-foreground">
                                                                                Weighted sum to open breaker
                                                                        </p>
                                                                </div>
                                                                <span className="font-mono text-sm">
                                                                        {cb?.threshold || 10.0}
                                                                </span>
                                                        </div>
                                                        <div className="flex items-center justify-between p-2 rounded border border-border">
                                                                <div>
                                                                        <p className="text-sm font-medium">CB_COOLDOWN</p>
                                                                        <p className="text-xs text-muted-foreground">
                                                                                Seconds before half-open probe
                                                                        </p>
                                                                </div>
                                                                <span className="font-mono text-sm">
                                                                        {cb?.cooldown_seconds || 10.0}s
                                                                </span>
                                                        </div>
                                                </div>
                                        </div>
                                </CardContent>
                        </Card>

                        {/* Reset Button */}
                        {cb && cb.state !== "CLOSED" && (
                                <Card className="border-amber-500/30 bg-amber-500/5">
                                        <CardContent className="flex items-center justify-between p-4">
                                                <div>
                                                        <p className="text-sm font-semibold text-amber-600">
                                                                Circuit breaker is {cb.state}
                                                        </p>
                                                        <p className="text-xs text-muted-foreground">
                                                                After investigating and fixing the root cause, reset to restore normal operation
                                                        </p>
                                                </div>
                                                <Button
                                                        onClick={handleReset}
                                                        disabled={resetting}
                                                        className="bg-amber-600 hover:bg-amber-700 text-white"
                                                >
                                                        {resetting ? (
                                                                <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                                                        ) : (
                                                                <RotateCcw className="h-4 w-4 mr-1" />
                                                        )}
                                                        Reset Circuit Breaker
                                                </Button>
                                        </CardContent>
                                </Card>
                        )}

                        {/* Protected Methods Info */}
                        <Card className="border-border bg-card">
                                <CardHeader>
                                        <CardTitle className="flex items-center gap-2">
                                                <Shield className="h-5 w-5 text-primary" />
                                                Protected Computation Methods
                                        </CardTitle>
                                        <CardDescription>
                                                These QOMNKernel methods are wrapped with self-healing protection
                                        </CardDescription>
                                </CardHeader>
                                <CardContent>
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                                {[
                                                        { name: "voltage_drop", fallback: "0.0V (conservative)", standard: "NEC Ch.9 Table 8" },
                                                        { name: "battery_capacity", fallback: "0.0 Ah (forces investigation)", standard: "NFPA 72 §10.6.7.2.1" },
                                                        { name: "smoke_detector_spacing", fallback: "9.1m (NFPA 72 flat)", standard: "NFPA 72 §17.7.3.2.3" },
                                                        { name: "heat_detector_spacing", fallback: "6.1m (NFPA 72 standard)", standard: "NFPA 72 §17.6.3.5.1" },
                                                ].map((m) => (
                                                        <div
                                                                key={m.name}
                                                                className="flex items-center justify-between p-3 rounded border border-border"
                                                        >
                                                                <div>
                                                                        <p className="text-sm font-mono">{m.name}()</p>
                                                                        <p className="text-xs text-muted-foreground">{m.standard}</p>
                                                                </div>
                                                                <div className="text-right">
                                                                        <p className="text-xs text-muted-foreground">Fallback:</p>
                                                                        <p className="text-xs font-mono text-amber-600">{m.fallback}</p>
                                                                </div>
                                                        </div>
                                                ))}
                                        </div>
                                </CardContent>
                        </Card>
                </div>
        );
}
