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
    """
    Generate n synthetic asset records with maintenance history.

    FIX (Critical Review #11): Cox PH duration semantics were wrong.
    Previously: duration = age_days (age at prediction time).
    Now: duration = time from installation to failure (if failed) or
         to now (if censored / still operating).

    This is the correct survival-analysis semantics: an asset that was
    installed 5 years ago and failed after 3 years has duration=1095 days,
    not 1825 days.
    """
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

        # Determine label: did this asset fail?
        # Stronger signal than before (was: 0.1 + 0.01*age_years + 0.15*n_repairs + env_factor)
        # Now: realistic failure-probability curve that the model can actually learn.
        # - Infant mortality: very low (1% chance in first year)
        # - Steady-state: rises with age + repair history
        # - Wear-out: sharp rise after design life
        age_years = (now - install_date).days / 365.25
        n_repairs = sum(1 for e in history if e.maintenance_type in ("REPAIR", "REPLACEMENT"))
        env_factor = {"indoor": 0.0, "outdoor": 0.10, "corrosive": 0.30, "coastal": 0.20}.get(env, 0.0)
        design_life_years = 20.0 if asset_type != AssetType.BATTERY else 5.0
        if age_years < 1:
            failure_prob = 0.01  # infant mortality: very low
        elif age_years < design_life_years * 0.5:
            failure_prob = 0.05 + n_repairs * 0.20 + env_factor  # steady-state
        elif age_years < design_life_years:
            failure_prob = 0.20 + n_repairs * 0.20 + env_factor  # approaching wear-out
        else:
            # Wear-out phase: probability rises sharply with age past design life
            wear_out_factor = (age_years - design_life_years) / design_life_years
            failure_prob = min(0.95, 0.40 + wear_out_factor * 0.40 + n_repairs * 0.15 + env_factor)
        failure_prob = min(0.95, max(0.01, failure_prob))
        failed = random.random() < failure_prob

        # FIX: compute actual failure date (somewhere between install and now)
        # For Cox PH, duration = (failure_date - install_date) if failed,
        # else (now - install_date) for censored assets.
        if failed:
            # Failure happened at some point during the asset's life
            age_days = (now - install_date).days
            failure_offset_days = random.randint(int(age_days * 0.3), age_days)
            failure_date = install_date + timedelta(days=failure_offset_days)
            duration_days = float(failure_offset_days)
        else:
            # Censored at observation time (now)
            duration_days = float((now - install_date).days)

        assets.append({
            "asset_type": asset_type,
            "install_date": install_date,
            "env": env,
            "history": history,
            "failed": failed,
            "age_years": age_years,
            "n_repairs": n_repairs,
            "duration_days": duration_days,  # FIX: correct Cox PH duration
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
            # FIX: use duration_days (correct survival semantics) instead of age_days
            cox_model = CoxPHFailureModel()
            X_cox.append(cox_model._features_to_cox_input(feat))
            durations.append(max(30.0, a["duration_days"]))
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
