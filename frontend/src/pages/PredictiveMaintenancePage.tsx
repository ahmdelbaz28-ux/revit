/**
 * frontend/src/pages/PredictiveMaintenancePage.tsx
 * =================================================
 * Main dashboard for ML-based predictive maintenance.
 *
 * Architecture:
 *  - Top: Health check banner (which ML models are available)
 *  - Left: Asset input form (asset ID, type, history)
 *  - Right: Predictions panel (gauge + model comparison + SHAP)
 *  - Bottom: Audit trail notice (safety-critical requirement)
 *
 * References:
 *   FireAI Roadmap Q4 2026 — AI-Powered Features
 *   NFPA 72-2022 §14.4 — Inspection, testing, maintenance
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import {
  AssetFeatures,
  AssetType,
  checkMLHealth,
  MLPredictionResponse,
  predictFailure,
  RISK_BG,
  RiskLevel,
} from '@/services/mlApi';
import { RiskGauge } from '@/components/predictive/RiskGauge';
import { ModelComparisonChart } from '@/components/predictive/ModelComparisonChart';
import { SHAPExplanation } from '@/components/predictive/SHAPExplanation';

interface MLHealth {
  status: string;
  available_models: string[];
  shap_available: boolean;
}

const ASSET_TYPES: AssetType[] = [
  'DETECTOR_SMOKE',
  'DETECTOR_HEAT',
  'DETECTOR_FLAME',
  'DETECTOR_GAS',
  'NAC',
  'FACP',
  'SLC_LOOP',
  'BATTERY',
  'CABLE',
];

const ENVIRONMENTS = [
  'indoor',
  'outdoor',
  'hazardous',
  'cleanroom',
  'corrosive',
  'coastal',
  'desert',
];

const DEFAULT_ASSET: AssetFeatures = {
  asset_id: 'DET-001',
  asset_type: 'DETECTOR_SMOKE',
  installation_date: '2018-06-01T00:00:00Z',
  manufacturer: 'SystemSensor',
  model: 'i3',
  location: 'Building A - Floor 3',
  environment_rating: 'indoor',
  design_life_years: 20.0,
  age_days: 0,
  age_ratio: 0,
  recent_failures_90d: 0,
  recent_failures_365d: 1,
  total_failures: 2,
  maintenance_count_365d: 4,
  inspection_count_90d: 1,
  repair_ratio_365d: 0.25,
  mean_time_between_failures_days: 540,
  environment_factor: 1.0,
  is_battery: false,
  is_outdoor: false,
  recent_event_counts: [],
};

export function PredictiveMaintenancePage() {
  const { t } = useTranslation();
  const [health, setHealth] = useState<MLHealth | null>(null);
  const [asset, setAsset] = useState<AssetFeatures>(DEFAULT_ASSET);
  const [horizon, setHorizon] = useState(90);
  const [explain, setExplain] = useState(true);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<MLPredictionResponse | null>(null);

  useEffect(() => {
    checkMLHealth()
      .then(setHealth)
      .catch((err) => {
        console.error('ML health check failed:', err);
        toast.error('ML backend unavailable. Is FastAPI running?');
      });
  }, []);

  const handlePredict = async () => {
    setLoading(true);
    try {
      const response = await predictFailure({
        asset,
        models: ['XGBOOST', 'COX_PH', 'LSTM'],
        explain,
        horizon_days: horizon,
      });
      setResult(response);
      toast.success('Prediction complete (advisory only)');
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(`Prediction failed: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  const riskLevel = result?.ensemble_risk_level ?? 'LOW';

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">
            {t('predictive.title', 'Predictive Maintenance')}
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            ML-based failure prediction (FireAI Roadmap Q4 2026)
          </p>
        </div>
        <div className="text-right">
          <div className="text-xs text-slate-500">Backend status</div>
          <div
            className={`text-sm font-medium ${
              health?.status === 'healthy' ? 'text-green-400' : 'text-amber-400'
            }`}
          >
            {health?.status ?? 'checking...'}
          </div>
        </div>
      </div>

      {/* Health banner */}
      {health && (
        <div className="border border-slate-800 rounded-lg p-4 bg-slate-900/40">
          <div className="flex flex-wrap items-center gap-4 text-sm">
            <span className="text-slate-300">Available ML models:</span>
            {health.available_models.length === 0 ? (
              <span className="text-amber-400">
                None trained — predictions will use statistical fallback
              </span>
            ) : (
              health.available_models.map((m) => (
                <span
                  key={m}
                  className="px-2 py-1 bg-violet-500/15 text-violet-300 rounded text-xs font-medium"
                >
                  {m}
                </span>
              ))
            )}
            <span className="ml-auto text-xs text-slate-500">
              SHAP explanations: {health.shap_available ? '✓' : '✗'}
            </span>
          </div>
        </div>
      )}

      {/* Main content grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Asset input form */}
        <div className="lg:col-span-1 space-y-4 border border-slate-800 rounded-lg p-4 bg-slate-900/40">
          <h2 className="text-sm font-semibold text-slate-200">Asset Configuration</h2>

          <div className="space-y-3">
            <div>
              <label className="text-xs text-slate-400">Asset ID</label>
              <input
                type="text"
                value={asset.asset_id}
                onChange={(e) =>
                  setAsset({ ...asset, asset_id: e.target.value })
                }
                className="w-full mt-1 px-2 py-1.5 bg-slate-800 border border-slate-700 rounded text-sm"
              />
            </div>

            <div>
              <label className="text-xs text-slate-400">Asset Type</label>
              <select
                value={asset.asset_type}
                onChange={(e) =>
                  setAsset({
                    ...asset,
                    asset_type: e.target.value as AssetType,
                    is_battery: e.target.value === 'BATTERY',
                  })
                }
                className="w-full mt-1 px-2 py-1.5 bg-slate-800 border border-slate-700 rounded text-sm"
              >
                {ASSET_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-xs text-slate-400">Installation Date</label>
              <input
                type="date"
                value={asset.installation_date.split('T')[0]}
                onChange={(e) =>
                  setAsset({
                    ...asset,
                    installation_date: new Date(
                      e.target.value
                    ).toISOString(),
                  })
                }
                className="w-full mt-1 px-2 py-1.5 bg-slate-800 border border-slate-700 rounded text-sm"
              />
            </div>

            <div>
              <label className="text-xs text-slate-400">Environment</label>
              <select
                value={asset.environment_rating}
                onChange={(e) =>
                  setAsset({
                    ...asset,
                    environment_rating: e.target.value,
                    is_outdoor: ['outdoor', 'coastal', 'desert'].includes(
                      e.target.value
                    ),
                  })
                }
                className="w-full mt-1 px-2 py-1.5 bg-slate-800 border border-slate-700 rounded text-sm"
              >
                {ENVIRONMENTS.map((env) => (
                  <option key={env} value={env}>
                    {env}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-xs text-slate-400">Recent failures (90d)</label>
                <input
                  type="number"
                  min={0}
                  value={asset.recent_failures_90d}
                  onChange={(e) =>
                    setAsset({
                      ...asset,
                      recent_failures_90d: parseInt(e.target.value) || 0,
                    })
                  }
                  className="w-full mt-1 px-2 py-1.5 bg-slate-800 border border-slate-700 rounded text-sm"
                />
              </div>
              <div>
                <label className="text-xs text-slate-400">Recent failures (365d)</label>
                <input
                  type="number"
                  min={0}
                  value={asset.recent_failures_365d}
                  onChange={(e) =>
                    setAsset({
                      ...asset,
                      recent_failures_365d: parseInt(e.target.value) || 0,
                    })
                  }
                  className="w-full mt-1 px-2 py-1.5 bg-slate-800 border border-slate-700 rounded text-sm"
                />
              </div>
            </div>

            <div>
              <label className="text-xs text-slate-400">
                Prediction horizon (days)
              </label>
              <input
                type="range"
                min={7}
                max={365}
                step={7}
                value={horizon}
                onChange={(e) => setHorizon(parseInt(e.target.value))}
                className="w-full mt-1"
              />
              <div className="text-xs text-slate-500 text-right">{horizon} days</div>
            </div>

            <label className="flex items-center gap-2 text-xs text-slate-300">
              <input
                type="checkbox"
                checked={explain}
                onChange={(e) => setExplain(e.target.checked)}
              />
              Generate SHAP explanations (recommended for audit)
            </label>

            <button
              onClick={handlePredict}
              disabled={loading}
              className="w-full px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:bg-slate-700 text-white text-sm font-medium rounded transition"
            >
              {loading ? 'Predicting...' : 'Run ML Prediction'}
            </button>
          </div>
        </div>

        {/* Right: Results panel */}
        <div className="lg:col-span-2 space-y-4">
          {result ? (
            <>
              {/* Ensemble + gauge */}
              <div className="border border-slate-800 rounded-lg p-5 bg-slate-900/40">
                <div className="flex flex-col md:flex-row items-center gap-6">
                  <RiskGauge
                    probability={result.ensemble_failure_probability}
                    riskLevel={result.ensemble_risk_level}
                    size={160}
                  />
                  <div className="flex-1 space-y-3">
                    <div>
                      <div className="text-xs text-slate-400">Asset</div>
                      <div className="text-lg font-mono text-slate-200">
                        {result.asset_id}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-400">Ensemble risk level</div>
                      <span
                        className={`inline-block mt-1 px-3 py-1 rounded border text-sm font-medium ${
                          RISK_BG[result.ensemble_risk_level as RiskLevel]
                        }`}
                      >
                        {result.ensemble_risk_level}
                      </span>
                    </div>
                    {result.ensemble_ttf_days && (
                      <div>
                        <div className="text-xs text-slate-400">
                          Estimated time-to-failure
                        </div>
                        <div className="text-lg text-slate-200">
                          {result.ensemble_ttf_days.toLocaleString()} days
                        </div>
                      </div>
                    )}
                    <div>
                      <div className="text-xs text-slate-400">
                        Horizon: {result.horizon_days} days
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Model comparison */}
              <div className="border border-slate-800 rounded-lg p-5 bg-slate-900/40">
                <h3 className="text-sm font-semibold text-slate-200 mb-4">
                  Model Comparison
                </h3>
                <ModelComparisonChart
                  predictions={result.predictions}
                  ensembleProbability={result.ensemble_failure_probability}
                />
              </div>

              {/* SHAP explanations */}
              {explain && result.explanations.length > 0 && (
                <div className="border border-slate-800 rounded-lg p-5 bg-slate-900/40">
                  <h3 className="text-sm font-semibold text-slate-200 mb-1">
                    SHAP Explanations (Audit Trail)
                  </h3>
                  <p className="text-xs text-slate-500 mb-4">
                    Required for safety-critical systems (NFPA 72 §14.4, IEC 61508)
                  </p>
                  <SHAPExplanation explanations={result.explanations} />
                </div>
              )}

              {/* Statistical baseline comparison */}
              {result.statistical_baseline && (
                <div className="border border-slate-800 rounded-lg p-5 bg-slate-900/40">
                  <h3 className="text-sm font-semibold text-slate-200 mb-3">
                    Statistical Baseline (fireai/analytics)
                  </h3>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                    <div>
                      <div className="text-xs text-slate-500">Health score</div>
                      <div className="font-mono">
                        {(result.statistical_baseline as any).health_score}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-500">
                        Failure probability
                      </div>
                      <div className="font-mono">
                        {(result.statistical_baseline as any).failure_probability}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-500">Risk level</div>
                      <div className="font-mono">
                        {(result.statistical_baseline as any).risk_level}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-500">TTF (days)</div>
                      <div className="font-mono">
                        {(result.statistical_baseline as any).estimated_ttf_days ??
                          '∞'}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="border border-dashed border-slate-700 rounded-lg p-12 text-center text-slate-500">
              <div className="text-4xl mb-3 opacity-40">📊</div>
              <p className="text-sm">
                Configure an asset and run a prediction to see results.
              </p>
              <p className="text-xs mt-2 text-slate-600">
                ML predictions are ADVISORY only. NFPA 72 deterministic rules
                remain authoritative for life-safety decisions.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Footer advisory */}
      <div className="border border-amber-900/40 bg-amber-950/20 rounded-lg p-3 text-xs text-amber-300">
        ⚠️ <strong>Safety Notice:</strong> ML outputs are advisory only.
        Deterministic NFPA 72 calculations in <code>fireai/core/</code> remain
        authoritative. All ML predictions are logged with SHAP explanations for
        regulatory audit per NFPA 72 §14.4 and IEC 61508.
      </div>
    </div>
  );
}
