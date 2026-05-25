"""
pydantic_migration_plan.py – V21 Pydantic Migration Strategy
=============================================================
Answer to Q1, Q4, Q5, Q9, Q10: Incremental migration plan.

STRATEGY: Incremental — Input models first, then outputs.
No big-bang replacement. Dual support period: 2 weeks.
Total migration: ~4 weeks for 14+ models.

PHASE 1 (Week 1): Input models — highest risk if wrong
  SubstanceProperties    -> Done (models_v21.py)
  FlameDetectorSpec      -> Done
  Obstruction            -> Done
  RayTracePoint          -> Done

PHASE 2 (Week 2): Internal models
  ZoneExtent             -> Done
  HACResult              -> Done
  ATEXEquipmentSpec      -> Done

PHASE 3 (Week 3): Output models + adapter layer
  RegSelectorResult      -> Done

PHASE 4 (Week 4): Remove legacy dataclasses, update all consumers
"""

from __future__ import annotations
from typing import Any, Dict

from fireai.core.models_v21 import SubstanceProperties, HazardType


# ---------------------------------------------------------------------------
# Q5: RawInputAdapter — strict=True after adapter normalises input
# ---------------------------------------------------------------------------

class RawInputAdapter:
    """
    Accepts raw dict (from JSON/Revit/DXF/API) with coercion,
    validates physics, then returns strict Pydantic model.

    strict=True is used ONLY after adapter normalises input.
    External sources use coercion adapter -> then strict internal models.
    """

    @staticmethod
    def substance_from_raw(raw: Dict[str, Any]) -> SubstanceProperties:
        """
        Convert raw dict with possible string numbers, None values, wrong units.
        Raises ValueError with clear message on failure.
        """
        normalised: Dict[str, Any] = {}

        # Coerce numeric strings
        numeric_fields = [
            "lfl_vol_pct", "ufl_vol_pct", "flash_point_c",
            "autoignition_c", "mec_g_m3", "kst_bar_m_s",
            "mie_mj", "density_kg_m3", "molecular_weight",
        ]
        for field_name in numeric_fields:
            val = raw.get(field_name)
            if val is None:
                normalised[field_name] = None
            elif isinstance(val, str):
                try:
                    normalised[field_name] = float(val)
                except ValueError:
                    raise ValueError(
                        f"Field '{field_name}' has non-numeric value '{val}'. "
                        f"Expected float."
                    )
            else:
                normalised[field_name] = float(val)

        normalised["name"]        = str(raw.get("name", "UNKNOWN"))
        normalised["hazard_type"] = str(raw.get("hazard_type", "GAS")).upper()

        try:
            return SubstanceProperties(**normalised)
        except Exception as exc:
            raise ValueError(
                f"Substance validation failed:\n{exc}\n"
                f"Raw input: {raw}"
            ) from exc


# ---------------------------------------------------------------------------
# Q4: LegacyTestAdapter — How to handle old V25 tests after Pydantic migration
# ---------------------------------------------------------------------------

class LegacyTestAdapter:
    """
    Old tests that passed dicts/wrong types now use this adapter.
    Options:
    A) Assert ValidationError is raised (correct behavior — test passes)
    B) Wrap with RawInputAdapter for coercion tests
    """

    @staticmethod
    def example_fix():
        """
        OLD TEST (breaks with Pydantic strict):
            props = SubstanceProperties(lfl_vol_pct="1.5")  # string!
            assert props.lfl_vol_pct == 1.5

        NEW TEST option A — test that validation catches it:
            with pytest.raises(ValidationError):
                SubstanceProperties(lfl_vol_pct="1.5")

        NEW TEST option B — use adapter:
            props = RawInputAdapter.substance_from_raw({"lfl_vol_pct": "1.5", ...})
            assert props.lfl_vol_pct == 1.5
        """
        pass


# ---------------------------------------------------------------------------
# Q9: Standard Versioning — parametrised by standard edition
# ---------------------------------------------------------------------------

class StandardVersion(str):
    """
    Identifies an edition of a standard.
    Usage: StandardVersion("IEC 60079-10-1:2015") vs "IEC 60079-10-1:2020"
    """
    pass


_VENTILATION_TABLE = {
    "IEC 60079-10-1:2015": {
        "HIGH":   {"zone_0": False, "zone_1": True,  "zone_2": True},
        "MEDIUM": {"zone_0": False, "zone_1": True,  "zone_2": True},
        "LOW":    {"zone_0": True,  "zone_1": True,  "zone_2": False},
        "POOR":   {"zone_0": True,  "zone_1": False, "zone_2": False},
    },
    "IEC 60079-10-1:2020": {
        # 2020 edition revised ventilation categories
        "HIGH":   {"zone_0": False, "zone_1": False, "zone_2": True},
        "MEDIUM": {"zone_0": False, "zone_1": True,  "zone_2": True},
        "LOW":    {"zone_0": True,  "zone_1": True,  "zone_2": False},
        "POOR":   {"zone_0": True,  "zone_1": False, "zone_2": False},
    },
}

# Q9 Answer: Tests parametrised by standard version
# pytest fixture:
# @pytest.fixture(params=["IEC 60079-10-1:2015", "IEC 60079-10-1:2020"])
# def std_version(request): return request.param
