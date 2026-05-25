# FireCalc Pro V8 — Installation & Integration

## 1. Drop-in into your existing repo

```bash
# From the root of your existing FireAI / FireSafetyGenius repo:
cp -r firecalc_v8/src/v8_core           src/v8_core
cp    firecalc_v8/tests/test_v8_core.py tests/
cp    firecalc_v8/docs/INSTALL.md       docs/
cp    firecalc_v8/docs/README_V8.md     README_V8.md
cp    firecalc_v8/.github/workflows/firecalc-lint.yml .github/workflows/ 2>/dev/null || \
  mkdir -p .github/workflows && cp firecalc_v8/.github/workflows/firecalc-lint.yml .github/workflows/
```

## 2. Verify the modules import cleanly

```bash
PYTHONPATH=src python -c "import v8_core; print('FireCalc V8', v8_core.__version__)"
```

Expected:

```
FireCalc V8 8.0.0
```

## 3. Run each module's self-test

```bash
PYTHONPATH=src python -m v8_core.code_authority
PYTHONPATH=src python -m v8_core.decision_provenance
PYTHONPATH=src python -m v8_core.safety_optimizer
PYTHONPATH=src python -m v8_core.pattern_library
PYTHONPATH=src python -m v8_core.smoke_estimator
```

Every line should end with `PASS` or `OK`.

## 4. Run the full test suite

```bash
PYTHONPATH=src python -m unittest tests.test_v8_core -v
```

Expected: **all green**.

## 5. Run the V8 linter against your existing code (this WILL fail loudly)

```bash
PYTHONPATH=src python src/v8_core/linter_rules.py src/
```

You will see a list of every banned word, hardcoded literal, and unannotated
function. **This is intentional.** That list is your Phase 0 worklist.

Add to CI (GitHub Actions example included in `.github/workflows/firecalc-lint.yml`).

## 6. Wire the existing optimizer to the V8 path

Inside `src/engineering/panel_optimizer.py`, replace the body of
`optimize_panels()` with a thin shim that delegates to
`v8_core.safety_optimizer.optimize_panels_safety_first()`:

```python
# src/engineering/panel_optimizer.py
from v8_core.safety_optimizer import (
    Device, optimize_panels_safety_first,
)
from v8_core.code_authority import CodeAuthority


def optimize_panels(devices, k, *, jurisdiction_id, code_authority,
                    project_date=None, drawing_hash="sha256:unknown"):
    typed = [Device(id=getattr(d, "id", str(i)), x=d.x, y=d.y)
             for i, d in enumerate(devices)]
    return optimize_panels_safety_first(
        typed, k=k, jurisdiction_id=jurisdiction_id,
        code_authority=code_authority, project_date=project_date,
        drawing_hash=drawing_hash,
    )
```

Note: the return type is now `DecisionProvenance`, not a list of points.
Every caller must be updated to consume the new object.

## 7. DELETE the V7.6 self-learner (do not refactor)

```bash
git rm src/knowledge/self_learner.py
```

Replace any caller with `v8_core.pattern_library.PatternLibrary`. The new
module exposes `submit_for_review`, `approve`, `reject`, `search_similar` —
and intentionally does NOT expose any `auto_learn` method.

## 8. Production hardening (before any paying customer)

- Replace HMAC dev keys with Vault / KMS / HSM-backed signing.
- Swap the SQLite store for a managed Postgres + S3 Object Lock audit log.
- Add Ed25519 asymmetric signatures for FPE attestation.
- Wire `linter_rules.py` as a **required** CI check on the default branch.
