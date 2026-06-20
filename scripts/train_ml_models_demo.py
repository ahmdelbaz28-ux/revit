"""
scripts/train_ml_models_demo.py
=================================
Demo script that trains XGBoost and Cox PH on synthetic failure data
to verify the training pipelines work end-to-end.

In production, replace generate_synthetic_data() with a query to the
FireAI database (backend/db_service.py) for real historical data.
"""

import sys
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from fireai.ml.models.xgboost_model import XGBoostFailureModel, FEATURE_NAMES
from fireai.ml.models.cox_model import CoxPHFailureModel
from fireai.ml.feature_engineering import FeatureEngineer
from fireai.ml.schemas import (
    AssetType,
    MaintenanceEventInput,
)


def generate_synthetic_assets(n: int = 200) -> list:
    """Generate n synthetic asset records with maintenance history."""
    random.seed(42)
    assets = []
    now = datetime.now(timezone.utc)

    for i in range(n):
        asset_type = random.choice(list(AssetType))
        install_date = now - timedelta(days=random.randint(365, 7300))
        env = random.choice(["indoor", "outdoor", "corrosive", "coastal"])

        # Generate 0-5 maintenance events
        n_events = random.randint(0, 5)
        history = []
        for j in range(n_events):
            event_date = install_date + timedelta(
                days=random.randint(30, max(31, (now - install_date).days - 30))
            )
            if event_date > now:
                continue
            mtype = random.choices(
                ["INSPECTION", "TEST", "REPAIR", "REPLACEMENT"],
                weights=[0.5, 0.3, 0.15, 0.05],
            )[0]
            history.append(
                MaintenanceEventInput(
                    event_id=f"M-{i}-{j}",
                    maintenance_type=mtype,
                    timestamp=event_date,
                )
            )

        # Determine label: did this asset fail in next 90d?
        # Higher chance of failure if: old + many repairs + harsh env
        age_years = (now - install_date).days / 365.25
        n_repairs = sum(1 for e in history if e.maintenance_type in ("REPAIR", "REPLACEMENT"))
        env_factor = {"indoor": 0, "outdoor": 0.1, "corrosive": 0.3, "coastal": 0.2}.get(env, 0)
        failure_prob = min(0.85, 0.1 + age_years * 0.01 + n_repairs * 0.15 + env_factor)
        failed = random.random() < failure_prob

        assets.append({
            "asset_type": asset_type,
            "install_date": install_date,
            "env": env,
            "history": history,
            "failed": failed,
            "age_years": age_years,
            "n_repairs": n_repairs,
        })

    return assets


def main() -> None:
    print("=" * 70)
    print("FireAI ML — Model Training Demo (Synthetic Data)")
    print("=" * 70)

    print("\n[1/4] Generating 200 synthetic assets...")
    assets = generate_synthetic_assets(200)
    n_failures = sum(1 for a in assets if a["failed"])
    print(f"  ✓ Generated: {len(assets)} assets ({n_failures} failures, {len(assets)-n_failures} censored)")

    print("\n[2/4] Building feature vectors...")
    fe = FeatureEngineer()
    X_xgboost = []
    y_xgboost = []
    X_cox = []
    durations = []
    events = []

    for a in assets:
        try:
            feat = fe.build_features(
                asset_id=f"synthetic-{a['asset_type'].value}-{random.randint(0, 99999)}",
                asset_type=a["asset_type"],
                installation_date=a["install_date"],
                maintenance_history=a["history"],
                environment_rating=a["env"],
            )
            # XGBoost feature vector
            from fireai.ml.models.xgboost_model import XGBoostFailureModel
            vec = XGBoostFailureModel().features_to_vector(feat)
            X_xgboost.append(vec)
            y_xgboost.append(1 if a["failed"] else 0)

            # Cox PH feature dict
            cox_model = CoxPHFailureModel()
            X_cox.append(cox_model._features_to_cox_input(feat))
            durations.append(max(30, feat.age_days))
            events.append(1 if a["failed"] else 0)
        except Exception as e:
            print(f"  ⚠ Skipped asset: {e}")
            continue

    print(f"  ✓ Built {len(X_xgboost)} XGBoost samples")
    print(f"  ✓ Built {len(X_cox)} Cox PH samples")

    print("\n[3/4] Training XGBoost model...")
    try:
        xgb_model = XGBoostFailureModel()
        result = xgb_model.train(X_xgboost, y_xgboost, FEATURE_NAMES)
        print(f"  ✓ Trained: {result.model_version}")
        print(f"  ✓ Samples: {result.samples_used}")
        print(f"  ✓ Metrics:")
        for k, v in result.metrics.items():
            print(f"      {k}: {v:.4f}")
        if result.feature_importance:
            print(f"  ✓ Top features:")
            for fname, imp in sorted(result.feature_importance.items(), key=lambda x: -x[1])[:5]:
                print(f"      {fname}: {imp:.2f}")
        # Save model
        save_path = ROOT / "data" / "ml_models" / "xgboost.pkl"
        xgb_model.save(save_path)
        print(f"  ✓ Saved to: {save_path}")
    except Exception as e:
        print(f"  ✗ XGBoost training failed: {e}")
        import traceback; traceback.print_exc()

    print("\n[4/4] Training Cox PH model...")
    try:
        cox_model = CoxPHFailureModel()
        result = cox_model.train(X_cox, durations, events)
        print(f"  ✓ Trained: {result.model_version}")
        print(f"  ✓ Samples: {result.samples_used}")
        print(f"  ✓ Concordance index: {result.metrics.get('concordance_index', 0):.4f}")
        if result.hazard_ratios:
            print(f"  ✓ Hazard ratios:")
            for feat, hr in sorted(result.hazard_ratios.items(), key=lambda x: -abs(x[1] - 1))[:5]:
                direction = "increases" if hr > 1 else "decreases"
                print(f"      {feat}: HR={hr:.3f} ({direction} hazard)")
        save_path = ROOT / "data" / "ml_models" / "cox.pkl"
        cox_model.save(save_path)
        print(f"  ✓ Saved to: {save_path}")
    except Exception as e:
        print(f"  ✗ Cox PH training failed: {e}")
        import traceback; traceback.print_exc()

    print("\n" + "=" * 70)
    print("✓ Training demo complete!")
    print("=" * 70)
    print("\nModels are now trained and saved. Re-run test_ml_subsystem.py")
    print("to see predictions using trained models instead of fallbacks.")


if __name__ == "__main__":
    main()
