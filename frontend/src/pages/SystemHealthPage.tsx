import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  AlertCircle,
  Zap,
  Database,
  Clock,
} from "lucide-react";
import { cn } from "@/lib/utils";

export const SystemHealthPage: React.FC = () => {
  const { t } = useTranslation();
  const [autoRefresh, setAutoRefresh] = useState(true);

  const healthStatus = {
    api: "ok" as const,
    responseTime: 145,
    errorRate: 0.02,
    lastCheck: new Date().toLocaleTimeString(),
  };

  const metrics = {
    cpu: 45,
    memory: 62,
    requests: 1234,
    errors: 8,
    uptime: "45 days 12 hours",
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "ok":
        return <CheckCircle2 className="h-6 w-6 text-green-500" />;
      case "degraded":
        return <AlertCircle className="h-6 w-6 text-yellow-500" />;
      case "down":
        return <AlertTriangle className="h-6 w-6 text-red-500" />;
      default:
        return <Activity className="h-6 w-6 text-slate-400" />;
    }
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold text-slate-100 flex items-center gap-2">
            <Activity className="h-8 w-8 text-green-500" />
            System Health Dashboard
          </h1>
          <p className="text-slate-400 mt-2">
            Real-time monitoring of BAZSPARK infrastructure and services
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="w-4 h-4 rounded"
            />
            Auto-refresh (30s)
          </label>
        </div>
      </div>

      {/* Status Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* API Status */}
        <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4">
          <div className="flex items-start justify-between mb-3">
            <h3 className="text-sm font-semibold text-slate-300">API Status</h3>
            {getStatusIcon(healthStatus.api)}
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-400">Status</span>
              <span className="text-green-400 font-medium">Operational</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Response Time</span>
              <span className="text-slate-100">{healthStatus.responseTime}ms</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Error Rate</span>
              <span className="text-slate-100">{(healthStatus.errorRate * 100).toFixed(2)}%</span>
            </div>
          </div>
        </div>

        {/* Database Status */}
        <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4">
          <div className="flex items-start justify-between mb-3">
            <h3 className="text-sm font-semibold text-slate-300">Database</h3>
            <CheckCircle2 className="h-6 w-6 text-green-500" />
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-400">Status</span>
              <span className="text-green-400 font-medium">Connected</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Connections</span>
              <span className="text-slate-100">8/10</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Query Time (avg)</span>
              <span className="text-slate-100">23ms</span>
            </div>
          </div>
        </div>

        {/* Cache Status */}
        <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4">
          <div className="flex items-start justify-between mb-3">
            <h3 className="text-sm font-semibold text-slate-300">Cache</h3>
            <CheckCircle2 className="h-6 w-6 text-green-500" />
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-400">Status</span>
              <span className="text-green-400 font-medium">Active</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Hit Rate</span>
              <span className="text-slate-100">78%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Size</span>
              <span className="text-slate-100">245 MB</span>
            </div>
          </div>
        </div>
      </div>

      {/* Metrics */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-6">
        <h2 className="text-lg font-semibold text-slate-100 mb-4">System Metrics</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* CPU Usage */}
          <div>
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm text-slate-300">CPU Usage</span>
              <span className="text-lg font-semibold text-slate-100">{metrics.cpu}%</span>
            </div>
            <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 transition-all"
                style={{ width: `${metrics.cpu}%` }}
              />
            </div>
          </div>

          {/* Memory Usage */}
          <div>
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm text-slate-300">Memory Usage</span>
              <span className="text-lg font-semibold text-slate-100">{metrics.memory}%</span>
            </div>
            <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
              <div
                className={cn("h-full transition-all", metrics.memory > 80 ? "bg-red-500" : "bg-green-500")}
                style={{ width: `${metrics.memory}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Activity */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
            <Zap className="h-4 w-4" />
            Requests (24h)
          </h3>
          <div className="text-3xl font-bold text-blue-400">{metrics.requests.toLocaleString()}</div>
          <p className="text-xs text-slate-400 mt-2">Successful API requests</p>
        </div>

        <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            Errors (24h)
          </h3>
          <div className="text-3xl font-bold text-yellow-400">{metrics.errors}</div>
          <p className="text-xs text-slate-400 mt-2">System errors detected</p>
        </div>

        <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
            <Clock className="h-4 w-4" />
            Uptime
          </h3>
          <div className="text-xl font-bold text-green-400">{metrics.uptime}</div>
          <p className="text-xs text-slate-400 mt-2">System availability</p>
        </div>
      </div>

      {/* Recent Events */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-6">
        <h2 className="text-lg font-semibold text-slate-100 mb-4">Recent System Events</h2>
        <div className="space-y-3">
          {[
            { type: "info", message: "Scheduled backup completed", time: "2 hours ago" },
            { type: "warning", message: "High memory usage detected", time: "4 hours ago" },
            { type: "info", message: "System update applied", time: "6 hours ago" },
            { type: "success", message: "Database optimization completed", time: "1 day ago" },
          ].map((event, idx) => (
            <div key={idx} className="flex items-start gap-3 p-3 bg-slate-700/30 rounded-lg">
              <div className="mt-1">
                {event.type === "info" && <Activity className="h-4 w-4 text-blue-400" />}
                {event.type === "warning" && <AlertCircle className="h-4 w-4 text-yellow-400" />}
                {event.type === "success" && <CheckCircle2 className="h-4 w-4 text-green-400" />}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-slate-100">{event.message}</p>
                <p className="text-xs text-slate-400 mt-1">{event.time}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Last Updated */}
      <div className="text-center text-xs text-slate-500">
        Last updated: {healthStatus.lastCheck}
        {autoRefresh && " • Auto-refreshing every 30 seconds"}
      </div>
    </div>
  );
};

export default SystemHealthPage;
