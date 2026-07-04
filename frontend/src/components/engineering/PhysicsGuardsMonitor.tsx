import React from "react";
import { AlertTriangle, CheckCircle2, AlertCircle, Info } from "lucide-react";
import { cn } from "@/lib/utils";

export interface GuardRule {
  id: string;
  name: string;
  description: string;
  severity: "info" | "warn" | "error";
  category: "voltage" | "battery" | "spacing" | "current" | "heat" | "smoke";
  min?: number;
  max?: number;
  currentValue?: number;
  unit?: string;
  status: "pass" | "warn" | "fail";
}

interface PhysicsGuardsMonitorProps {
  rules: GuardRule[];
  compact?: boolean;
}

const PhysicsGuardsMonitor: React.FC<PhysicsGuardsMonitorProps> = ({
  rules,
  compact = false,
}) => {
  // Filter rules by severity
  const failures = rules.filter((r) => r.status === "fail");
  const warnings = rules.filter((r) => r.status === "warn");
  const passes = rules.filter((r) => r.status === "pass");

  const hasFailures = failures.length > 0;
  const hasWarnings = warnings.length > 0;

  const getSeverityIcon = (severity: GuardRule["severity"]) => {
    switch (severity) {
      case "error":
        return <AlertTriangle className="h-4 w-4 text-red-500" />;
      case "warn":
        return <AlertCircle className="h-4 w-4 text-yellow-500" />;
      case "info":
        return <Info className="h-4 w-4 text-blue-500" />;
    }
  };

  const getStatusIcon = (status: GuardRule["status"]) => {
    switch (status) {
      case "fail":
        return <AlertTriangle className="h-5 w-5 text-red-500" />;
      case "warn":
        return <AlertCircle className="h-5 w-5 text-yellow-500" />;
      case "pass":
        return <CheckCircle2 className="h-5 w-5 text-green-500" />;
    }
  };

  if (compact) {
    // Compact summary view
    return (
      <div className="flex items-center gap-3 px-3 py-2 bg-slate-800/50 rounded-lg border border-slate-700">
        <div className="flex items-center gap-2">
          {hasFailures ? (
            <>
              <AlertTriangle className="h-4 w-4 text-red-500" />
              <span className="text-xs text-red-400 font-semibold">
                {failures.length} Critical
              </span>
            </>
          ) : hasWarnings ? (
            <>
              <AlertCircle className="h-4 w-4 text-yellow-500" />
              <span className="text-xs text-yellow-400 font-semibold">
                {warnings.length} Warnings
              </span>
            </>
          ) : (
            <>
              <CheckCircle2 className="h-4 w-4 text-green-500" />
              <span className="text-xs text-green-400 font-semibold">
                All Guards Pass
              </span>
            </>
          )}
        </div>
      </div>
    );
  }

  // Full detailed view
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-slate-100 mb-3 flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-orange-500" />
          Physics Guards Monitor (NFPA 72 Compliance)
        </h3>

        {/* Summary Stats */}
        <div className="grid grid-cols-3 gap-2 mb-4">
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3">
            <div className="text-2xl font-bold text-red-400">{failures.length}</div>
            <div className="text-xs text-red-300">Critical</div>
          </div>
          <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3">
            <div className="text-2xl font-bold text-yellow-400">{warnings.length}</div>
            <div className="text-xs text-yellow-300">Warnings</div>
          </div>
          <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-3">
            <div className="text-2xl font-bold text-green-400">{passes.length}</div>
            <div className="text-xs text-green-300">Passing</div>
          </div>
        </div>

        {/* Rules List */}
        <div className="space-y-2 max-h-96 overflow-y-auto">
          {failures.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-semibold text-red-400 uppercase tracking-wide">
                Critical Violations
              </h4>
              {failures.map((rule) => (
                <RuleCard key={rule.id} rule={rule} />
              ))}
            </div>
          )}

          {warnings.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-semibold text-yellow-400 uppercase tracking-wide">
                Warnings
              </h4>
              {warnings.map((rule) => (
                <RuleCard key={rule.id} rule={rule} />
              ))}
            </div>
          )}

          {!hasFailures && !hasWarnings && (
            <div className="flex items-center gap-3 p-3 bg-green-500/10 border border-green-500/30 rounded-lg">
              <CheckCircle2 className="h-5 w-5 text-green-500 shrink-0" />
              <div>
                <p className="text-sm font-semibold text-green-400">
                  All Physics Guards Passing
                </p>
                <p className="text-xs text-green-300">
                  All parameters within safe ranges
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// Individual rule card
const RuleCard: React.FC<{ rule: GuardRule }> = ({ rule }) => {
  const statusColor =
    rule.status === "fail"
      ? "bg-red-500/10 border-red-500/30 text-red-400"
      : "bg-yellow-500/10 border-yellow-500/30 text-yellow-400";

  const percentage =
    rule.currentValue && rule.min && rule.max
      ? ((rule.currentValue - rule.min) / (rule.max - rule.min)) * 100
      : 0;

  return (
    <div className={cn("rounded-lg border p-3", statusColor)}>
      <div className="flex items-start gap-3">
        <div className="mt-1">{RuleStatusIcon(rule.status)}</div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-slate-100">{rule.name}</p>
          <p className="text-xs text-slate-300 mt-1">{rule.description}</p>

          {rule.currentValue !== undefined && rule.min !== undefined && rule.max !== undefined && (
            <div className="mt-2 space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">
                  Range: {rule.min} - {rule.max}
                  {rule.unit ? ` ${rule.unit}` : ""}
                </span>
                <span className="font-semibold text-slate-100">
                  Current: {rule.currentValue} {rule.unit || ""}
                </span>
              </div>
              <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
                <div
                  className={cn(
                    "h-full transition-all",
                    rule.status === "fail" ? "bg-red-500" : "bg-yellow-500"
                  )}
                  style={{ width: `${Math.min(percentage, 100)}%` }}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

function RuleStatusIcon(status: GuardRule["status"]): React.ReactNode {
  switch (status) {
    case "fail":
      return <AlertTriangle className="h-5 w-5 text-red-500" />;
    case "warn":
      return <AlertCircle className="h-5 w-5 text-yellow-500" />;
    case "pass":
      return <CheckCircle2 className="h-5 w-5 text-green-500" />;
  }
}

export default PhysicsGuardsMonitor;
