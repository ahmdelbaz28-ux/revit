/**
 * frontend/src/components/predictive/RiskGauge.tsx
 * =================================================
 * Circular gauge showing failure probability (0–100%).
 */

import { RiskLevel, RISK_COLORS } from '@/services/mlApi';

interface RiskGaugeProps {
  probability: number; // 0..1
  riskLevel: RiskLevel;
  size?: number;
  label?: string;
}

export function RiskGauge({
  probability,
  riskLevel,
  size = 180,
  label = 'Failure Probability',
}: RiskGaugeProps) {
  const radius = (size - 24) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.min(1, Math.max(0, probability));
  const offset = circumference * (1 - pct);
  const color = RISK_COLORS[riskLevel];

  return (
    <div className="flex flex-col items-center gap-2">
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="rgba(255,255,255,0.08)"
          strokeWidth={10}
          fill="none"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={color}
          strokeWidth={10}
          fill="none"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 0.6s ease-out' }}
        />
        <text
          x="50%"
          y="50%"
          textAnchor="middle"
          dominantBaseline="central"
          className="rotate-90"
          style={{
            transformOrigin: 'center',
            fill: color,
            fontSize: size * 0.18,
            fontWeight: 700,
          }}
        >
          {(pct * 100).toFixed(1)}%
        </text>
      </svg>
      <div className="text-center">
        <div className="text-sm font-medium text-slate-300">{label}</div>
        <div className="text-xs text-slate-500">Risk: {riskLevel}</div>
      </div>
    </div>
  );
}
