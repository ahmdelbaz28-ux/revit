/**
 * frontend/src/components/predictive/SHAPExplanation.tsx
 * =======================================================
 * Visualises SHAP feature contributions for ML model explainability.
 * Critical for safety-critical audit trails (NFPA 72 §14.4, IEC 61508).
 */

import { ModelExplanation, MODEL_LABELS } from '@/services/mlApi';

interface Props {
  explanations: ModelExplanation[];
}

export function SHAPExplanation({ explanations }: Props) {
  if (!explanations.length) {
    return (
      <div className="text-sm text-slate-500 italic">
        No SHAP explanations available (install 'shap' Python package)
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {explanations.map((expl) => {
        const contributions = Object.entries(expl.feature_contributions)
          .map(([feature, value]) => ({ feature, value }))
          .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
          .slice(0, 8);

        const maxAbs = Math.max(
          ...contributions.map((c) => Math.abs(c.value)),
          0.01
        );

        return (
          <div
            key={expl.model_type}
            className="border border-slate-800 rounded-lg p-4 bg-slate-900/40"
          >
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-semibold text-slate-200">
                {MODEL_LABELS[expl.model_type] || expl.model_type}
              </h4>
              <div className="text-[10px] text-slate-500 font-mono">
                base: {expl.base_value.toFixed(3)} → pred:{' '}
                {expl.prediction_value.toFixed(3)}
              </div>
            </div>

            <div className="space-y-1.5 mb-3">
              {contributions.map(({ feature, value }) => {
                const pct = (Math.abs(value) / maxAbs) * 50; // max 50% width
                const positive = value > 0;
                return (
                  <div key={feature} className="flex items-center gap-2 text-xs">
                    <div className="w-40 text-slate-400 truncate" title={feature}>
                      {feature}
                    </div>
                    <div className="flex-1 relative h-4 flex items-center">
                      <div className="absolute left-1/2 w-px h-full bg-slate-700" />
                      {positive ? (
                        <div
                          className="absolute left-1/2 h-3 bg-red-500/60 rounded-r"
                          style={{ width: `${pct}%` }}
                        />
                      ) : (
                        <div
                          className="absolute right-1/2 h-3 bg-green-500/60 rounded-l"
                          style={{ width: `${pct}%` }}
                        />
                      )}
                    </div>
                    <div
                      className={`w-16 text-right font-mono ${
                        positive ? 'text-red-400' : 'text-green-400'
                      }`}
                    >
                      {value > 0 ? '+' : ''}
                      {value.toFixed(3)}
                    </div>
                  </div>
                );
              })}
            </div>

            <p className="text-xs text-slate-400 leading-relaxed bg-slate-800/40 p-2 rounded">
              {expl.explanation_text}
            </p>
          </div>
        );
      })}
    </div>
  );
}
