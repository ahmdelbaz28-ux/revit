/**
 * frontend/src/components/predictive/ModelComparisonChart.tsx
 * ============================================================
 * Horizontal bar chart comparing failure probability across ML models.
 */

import { MLPrediction, MODEL_LABELS, RISK_COLORS } from '@/services/mlApi';

interface Props {
  predictions: MLPrediction[];
  ensembleProbability: number;
}

export function ModelComparisonChart({ predictions, ensembleProbability }: Props) {
  if (!predictions.length) {
    return (
      <div className="text-sm text-slate-500 italic">
        No model predictions available
      </div>
    );
  }

  const sorted = [...predictions].sort(
    (a, b) => b.failure_probability - a.failure_probability
  );

  return (
    <div className="space-y-3">
      {/* Ensemble first */}
      <div className="flex items-center gap-3">
        <div className="w-32 text-xs font-semibold text-slate-200">
          Ensemble
        </div>
        <div className="flex-1 h-6 bg-slate-800/60 rounded overflow-hidden relative">
          <div
            className="h-full bg-gradient-to-r from-violet-500 to-fuchsia-500 flex items-center justify-end pr-2"
            style={{ width: `${ensembleProbability * 100}%` }}
          >
            <span className="text-[10px] font-bold text-white">
              {(ensembleProbability * 100).toFixed(1)}%
            </span>
          </div>
        </div>
      </div>

      <div className="border-t border-slate-800 pt-3 space-y-2">
        {sorted.map((pred) => {
          const color = RISK_COLORS[pred.risk_level];
          const widthPct = Math.max(2, pred.failure_probability * 100);
          return (
            <div key={pred.model_type} className="flex items-center gap-3">
              <div className="w-32 text-xs text-slate-400 truncate">
                {MODEL_LABELS[pred.model_type]?.split(' ')[0] || pred.model_type}
                {pred.is_fallback && (
                  <span className="ml-1 text-amber-500" title="Fallback mode">
                    ⚠
                  </span>
                )}
              </div>
              <div className="flex-1 h-5 bg-slate-800/40 rounded overflow-hidden">
                <div
                  className="h-full flex items-center justify-end pr-2 transition-all"
                  style={{
                    width: `${widthPct}%`,
                    backgroundColor: color,
                    opacity: pred.is_fallback ? 0.4 : 0.85,
                  }}
                >
                  <span className="text-[10px] font-medium text-white">
                    {(pred.failure_probability * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
              <div className="w-16 text-[10px] text-slate-500 text-right">
                TTF: {pred.predicted_ttf_days ? `${pred.predicted_ttf_days}d` : '—'}
              </div>
            </div>
          );
        })}
      </div>

      <div className="pt-2 text-[10px] text-slate-600">
        Bars represent failure probability within forecast horizon.
        Fallback models (⚠) used when library unavailable.
      </div>
    </div>
  );
}
