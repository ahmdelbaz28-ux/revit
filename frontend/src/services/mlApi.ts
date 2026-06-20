/**
 * frontend/src/services/mlApi.ts
 * =================================
 * API client for ML subsystem endpoints.
 * Matches backend/routers/ml.py exactly.
 */

import { z } from 'zod';

// ── Types matching Python schemas ─────────────────────────────────────────

export const AssetTypeSchema = z.enum([
  'DETECTOR_SMOKE',
  'DETECTOR_HEAT',
  'DETECTOR_FLAME',
  'DETECTOR_GAS',
  'NAC',
  'FACP',
  'SLC_LOOP',
  'BATTERY',
  'CABLE',
]);

export const RiskLevelSchema = z.enum(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']);
export const ModelTypeSchema = z.enum([
  'XGBOOST',
  'LIGHTGBM',
  'LSTM',
  'PROPHET',
  'COX_PH',
  'ENSEMBLE',
  'FALLBACK_STATISTICAL',
]);

export const AssetFeaturesSchema = z.object({
  asset_id: z.string(),
  asset_type: AssetTypeSchema,
  installation_date: z.string(),
  manufacturer: z.string().default(''),
  model: z.string().default(''),
  location: z.string().default(''),
  environment_rating: z.string().default('indoor'),
  design_life_years: z.number().default(20.0),
  age_days: z.number().default(0),
  age_ratio: z.number().min(0).max(2).default(0),
  recent_failures_90d: z.number().int().min(0).default(0),
  recent_failures_365d: z.number().int().min(0).default(0),
  total_failures: z.number().int().min(0).default(0),
  maintenance_count_365d: z.number().int().min(0).default(0),
  inspection_count_90d: z.number().int().min(0).default(0),
  repair_ratio_365d: z.number().min(0).max(1).default(0),
  mean_time_between_failures_days: z.number().nullable().default(null),
  environment_factor: z.number().min(0).max(1).default(1),
  is_battery: z.boolean().default(false),
  is_outdoor: z.boolean().default(false),
  recent_event_counts: z.array(z.number().int().min(0)).default([]),
});

export const ModelExplanationSchema = z.object({
  model_type: ModelTypeSchema,
  base_value: z.number(),
  prediction_value: z.number(),
  feature_contributions: z.record(z.string(), z.number()).default({}),
  top_features: z
    .array(
      z.object({
        feature: z.string(),
        shap_value: z.number().optional(),
        abs_value: z.number().optional(),
      })
    )
    .default([]),
  explanation_text: z.string(),
});

export const MLPredictionSchema = z.object({
  model_type: ModelTypeSchema,
  failure_probability: z.number().min(0).max(1),
  predicted_ttf_days: z.number().nullable(),
  confidence_lower: z.number().nullable(),
  confidence_upper: z.number().nullable(),
  risk_level: RiskLevelSchema,
  is_fallback: z.boolean().default(false),
  model_version: z.string().default(''),
  training_data_size: z.number().int().default(0),
  last_trained_at: z.string().nullable(),
});

export const MLPredictionResponseSchema = z.object({
  asset_id: z.string(),
  generated_at: z.string(),
  horizon_days: z.number().int(),
  ensemble_failure_probability: z.number().min(0).max(1),
  ensemble_risk_level: RiskLevelSchema,
  ensemble_ttf_days: z.number().nullable(),
  predictions: z.array(MLPredictionSchema).default([]),
  explanations: z.array(ModelExplanationSchema).default([]),
  statistical_baseline: z.record(z.string(), z.unknown()).nullable(),
  advisory_notice: z.string(),
  audit_trail_id: z.string().nullable(),
});

// ── Exported TypeScript types ─────────────────────────────────────────────

export type AssetType = z.infer<typeof AssetTypeSchema>;
export type RiskLevel = z.infer<typeof RiskLevelSchema>;
export type ModelType = z.infer<typeof ModelTypeSchema>;
export type AssetFeatures = z.infer<typeof AssetFeaturesSchema>;
export type ModelExplanation = z.infer<typeof ModelExplanationSchema>;
export type MLPrediction = z.infer<typeof MLPredictionSchema>;
export type MLPredictionResponse = z.infer<typeof MLPredictionResponseSchema>;

// ── API client ────────────────────────────────────────────────────────────

const API_BASE =
  (import.meta as any).env?.VITE_API_URL || '/api/v1';

function stripV1(url: string): string {
  // ML router is mounted at /api/ml, not /api/v1/ml
  return url.replace(/\/api\/v1\/?$/, '/api').replace(/\/$/, '');
}

const ML_BASE = `${stripV1(API_BASE)}/ml`;

export interface PredictRequest {
  asset: AssetFeatures;
  models?: ModelType[];
  explain?: boolean;
  horizon_days?: number;
}

export async function predictFailure(
  request: PredictRequest
): Promise<MLPredictionResponse> {
  const body = {
    asset: request.asset,
    models: request.models ?? ['XGBOOST', 'COX_PH'],
    explain: request.explain ?? true,
    horizon_days: request.horizon_days ?? 90,
  };

  const res = await fetch(`${ML_BASE}/predictive-maintenance/predict`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`ML predict failed (${res.status}): ${text}`);
  }

  const json = await res.json();
  return MLPredictionResponseSchema.parse(json);
}

export async function checkMLHealth(): Promise<{
  status: string;
  available_models: string[];
  shap_available: boolean;
}> {
  const res = await fetch(`${ML_BASE}/predictive-maintenance/health`);
  if (!res.ok) {
    throw new Error(`ML health failed (${res.status})`);
  }
  return res.json();
}

export async function listMLModels(): Promise<{
  available_models: Array<{
    model_type: string;
    trained: boolean;
    version: string;
    training_data_size: number;
    last_trained_at: string | null;
  }>;
  unavailable_models: Array<{
    model_type: string;
    reason: string;
  }>;
}> {
  const res = await fetch(`${ML_BASE}/predictive-maintenance/models`);
  if (!res.ok) {
    throw new Error(`ML models list failed (${res.status})`);
  }
  return res.json();
}

// ── Helpers ───────────────────────────────────────────────────────────────

export const RISK_COLORS: Record<RiskLevel, string> = {
  CRITICAL: '#ef4444', // red-500
  HIGH: '#f97316', // orange-500
  MEDIUM: '#eab308', // yellow-500
  LOW: '#22c55e', // green-500
};

export const RISK_BG: Record<RiskLevel, string> = {
  CRITICAL: 'bg-red-500/15 text-red-300 border-red-500/30',
  HIGH: 'bg-orange-500/15 text-orange-300 border-orange-500/30',
  MEDIUM: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30',
  LOW: 'bg-green-500/15 text-green-300 border-green-500/30',
};

export const MODEL_LABELS: Record<ModelType, string> = {
  XGBOOST: 'XGBoost (Gradient Boosting)',
  LIGHTGBM: 'LightGBM',
  LSTM: 'LSTM (Time-Series)',
  PROPHET: 'Prophet (Seasonal)',
  COX_PH: 'Cox PH (Survival)',
  ENSEMBLE: 'Ensemble (All)',
  FALLBACK_STATISTICAL: 'Statistical Fallback',
};
