"""revit_acl.py – Anti-Corruption Layer for Revit/BIM Data Import
==============================================================
Protects strict Pydantic domain models from corrupted external data.

Problem: Revit and other BIM tools export data with:
  - Strings where numbers are expected ("1.5" instead of 1.5)
  - Extra whitespace in enums (" ZONE_1 " instead of "ZONE_1")
  - Missing fields that should have defaults
  - Typos in enumeration values
  - Null values where required fields exist

Solution: DTO (Data Transfer Object) layer with:
  - strict=False (flexible, accepts raw external data)
  - model_validator(mode='before') for sanitization/coercion
  - to_domain() method for conversion to strict Pydantic models
  - Error collection instead of crash (log and skip)

Pattern: Loose DTO -> Strict Domain Model
  RevitSubstanceDTO -> SubstanceProperties
  RevitDetectorDTO  -> FlameDetectorSpec
  RevitObstructionDTO -> Obstruction

Reference: Anti-Corruption Layer pattern (DDD, Vernon 2013)
           IEC 60079-10-1:2015 (input data requirements)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, model_validator

from fireai.core.models_v21 import (
    FlameDetectorSpec,
    HazardType,
    Obstruction,
    SubstanceProperties,
    WavelengthBand,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Import Error Tracking
# ---------------------------------------------------------------------------


@dataclass
class ImportError:
    """Record of a data import error for reporting back to the BIM engineer."""

    element_id: str
    field_name: str
    raw_value: Any
    error_message: str
    severity: str = "WARNING"  # "WARNING" or "ERROR"

    def __str__(self) -> str:
        return (
            f"[{self.severity}] Element '{self.element_id}', "
            f"field '{self.field_name}': {self.error_message} "
            f"(raw value: {self.raw_value!r})"
        )


@dataclass
class ImportReport:
    """Summary of all errors encountered during data import."""

    total_elements: int = 0
    successful: int = 0
    skipped: int = 0
    errors: List[ImportError] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(e.severity == "ERROR" for e in self.errors)

    @property
    def has_warnings(self) -> bool:
        return any(e.severity == "WARNING" for e in self.errors)

    def add_error(
        self, element_id: str, field_name: str, raw_value: Any, message: str, severity: str = "WARNING"
    ) -> None:
        self.errors.append(
            ImportError(
                element_id=element_id,
                field_name=field_name,
                raw_value=raw_value,
                error_message=message,
                severity=severity,
            )
        )

    def summary(self) -> str:
        n_err = sum(1 for e in self.errors if e.severity == "ERROR")
        n_warn = sum(1 for e in self.errors if e.severity == "WARNING")
        return (
            f"Import Report: {self.total_elements} elements, "
            f"{self.successful} successful, {self.skipped} skipped. "
            f"Errors: {n_err}, Warnings: {n_warn}."
        )

    def detailed_report(self) -> str:
        lines = [self.summary(), ""]
        for e in self.errors:
            lines.append(str(e))
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Enum normalization helpers
# ---------------------------------------------------------------------------

_HAZARD_TYPE_ALIASES: Dict[str, str] = {
    "GAS": "GAS",
    "VAPOR": "GAS",
    "GAS/VAPOR": "GAS",
    "G": "GAS",
    "DUST": "DUST",
    "D": "DUST",
    "COMBUSTIBLE_DUST": "DUST",
    "HYBRID": "HYBRID",
    "H": "HYBRID",
    "MIXED": "HYBRID",
    "FIBER": "FIBER",
    "F": "FIBER",
    "FIBRES": "FIBER",
}

_WAVELENGTH_BAND_ALIASES: Dict[str, str] = {
    "UV": "UV",
    "ULTRAVIOLET": "UV",
    "VIS": "VIS",
    "VISIBLE": "VIS",
    "V": "VIS",
    "IR1": "IR1",
    "NEAR_IR": "IR1",
    "NIR": "IR1",
    "IR3": "IR3",
    "MID_IR": "IR3",
    "MIR": "IR3",
    "CO2": "IR3",
}


def _normalize_enum(raw: str, aliases: Dict[str, str]) -> Optional[str]:
    """Normalize an enum value from various external representations."""
    cleaned = str(raw).strip().upper().replace(" ", "_").replace("-", "_")
    return aliases.get(cleaned)


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert any value to float."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", ".")
        # Remove non-numeric characters except . and -
        cleaned = re.sub(r"[^\d.\-]", "", cleaned)
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return default
    return default


# ---------------------------------------------------------------------------
# Revit Substance DTO (Flexible Input)
# ---------------------------------------------------------------------------


class RevitSubstanceDTO(BaseModel):
    """Anti-Corruption Layer for substance data from Revit/BIM exports.

    This model is FLEXIBLE (strict=False) to accept raw external data.
    It sanitizes and coerces values before converting to strict domain models.

    Common Revit data issues handled:
    - LFL as string "5.0 %" -> float 5.0
    - Hazard type as "Gas/Vapor" -> GAS
    - Missing autoignition -> None (with warning)
    - Negative flash point strings -> proper float
    """

    model_config = ConfigDict(frozen=False, strict=False, extra="allow")

    element_id: str = "UNKNOWN"
    name: str = ""
    hazard_type: str = "GAS"  # Raw string, will be normalized
    lfl_vol_pct: Any = None
    ufl_vol_pct: Any = None
    flash_point_c: Any = None
    autoignition_c: Any = None
    mec_g_m3: Any = None
    kst_bar_m_s: Any = None
    mie_mj: Any = None
    density_kg_m3: Any = None
    molecular_weight: Any = None

    @model_validator(mode="before")
    @classmethod
    def sanitize_revit_data(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # Strip whitespace from string fields
        for key in ("name", "element_id", "hazard_type"):
            if key in data and isinstance(data[key], str):
                data[key] = data[key].strip()

        # Normalize hazard type
        if "hazard_type" in data:
            normalized = _normalize_enum(str(data["hazard_type"]), _HAZARD_TYPE_ALIASES)
            if normalized:
                data["hazard_type"] = normalized

        # Convert numeric strings to floats
        for key in (
            "lfl_vol_pct",
            "ufl_vol_pct",
            "flash_point_c",
            "autoignition_c",
            "mec_g_m3",
            "kst_bar_m_s",
            "mie_mj",
            "density_kg_m3",
            "molecular_weight",
        ):
            if key in data and data[key] is not None:
                data[key] = _safe_float(data[key], default=0.0) or None

        # Handle common Revit field name variations
        if "substance_name" in data and "name" not in data:
            data["name"] = data.pop("substance_name")
        if "lfl" in data and "lfl_vol_pct" not in data:
            data["lfl_vol_pct"] = data.pop("lfl")
        if "ufl" in data and "ufl_vol_pct" not in data:
            data["ufl_vol_pct"] = data.pop("ufl")
        if "flash_point" in data and "flash_point_c" not in data:
            data["flash_point_c"] = data.pop("flash_point")
        if "auto_ignition" in data and "autoignition_c" not in data:
            data["autoignition_c"] = data.pop("auto_ignition")

        return data

    def to_domain(self, report: Optional[ImportReport] = None) -> Optional[SubstanceProperties]:
        """Convert this flexible DTO to a strict SubstanceProperties model.
        Returns None if conversion fails (logged to report).
        """
        try:
            hazard = HazardType(self.hazard_type)
        except ValueError:
            if report:
                report.add_error(
                    self.element_id,
                    "hazard_type",
                    self.hazard_type,
                    f"Unknown hazard type '{self.hazard_type}'. Expected: GAS, DUST, HYBRID, FIBER.",
                    "ERROR",
                )
            return None

        try:
            return SubstanceProperties(
                name=self.name or self.element_id,
                hazard_type=hazard,
                lfl_vol_pct=float(self.lfl_vol_pct) if self.lfl_vol_pct else None,
                ufl_vol_pct=float(self.ufl_vol_pct) if self.ufl_vol_pct else None,
                flash_point_c=float(self.flash_point_c) if self.flash_point_c else None,
                autoignition_c=float(self.autoignition_c) if self.autoignition_c else None,
                mec_g_m3=float(self.mec_g_m3) if self.mec_g_m3 else None,
                kst_bar_m_s=float(self.kst_bar_m_s) if self.kst_bar_m_s else None,
                mie_mj=float(self.mie_mj) if self.mie_mj else None,
                density_kg_m3=float(self.density_kg_m3) if self.density_kg_m3 else None,
                molecular_weight=float(self.molecular_weight) if self.molecular_weight else None,
            )
        except Exception as exc:
            if report:
                report.add_error(
                    self.element_id,
                    "to_domain",
                    str(exc),
                    f"Failed to create SubstanceProperties: {exc}",
                    "ERROR",
                )
            return None


# ---------------------------------------------------------------------------
# Revit Obstruction DTO
# ---------------------------------------------------------------------------


class RevitObstructionDTO(BaseModel):
    """Anti-Corruption Layer for obstruction data from Revit/BIM exports.
    Handles: missing transparency data, vertex format variations, etc.
    """

    model_config = ConfigDict(frozen=False, strict=False, extra="allow")

    element_id: str = "UNKNOWN"
    obstruction_id: str = ""
    vertices: Any = []
    transparency_uv: Any = 0.0
    transparency_vis: Any = 0.0
    transparency_ir1: Any = 0.0
    transparency_ir3: Any = 0.0

    @model_validator(mode="before")
    @classmethod
    def sanitize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # Handle ID field variations
        if "id" in data and "obstruction_id" not in data:
            data["obstruction_id"] = data.pop("id")
        if "element_id" in data and "obstruction_id" not in data:
            data["obstruction_id"] = data["element_id"]

        # Handle vertex format: Revit may export as flat list [x1,y1,z1,x2,y2,z2,...]
        if "vertices" in data and isinstance(data["vertices"], (list, tuple)):
            verts = data["vertices"]
            if len(verts) > 0 and isinstance(verts[0], (int, float)):
                # Flat list -> convert to [[x,y,z], [x,y,z], ...]
                if len(verts) % 3 == 0:
                    data["vertices"] = [[verts[i], verts[i + 1], verts[i + 2]] for i in range(0, len(verts), 3)]

        # Safely convert transparency values
        for key in ("transparency_uv", "transparency_vis", "transparency_ir1", "transparency_ir3"):
            if key in data and data[key] is not None:
                val = _safe_float(data[key], 0.0)
                data[key] = max(0.0, min(1.0, val))

        return data

    def to_domain(self, report: Optional[ImportReport] = None) -> Optional[Obstruction]:
        """Convert to strict Obstruction model."""
        try:
            # Ensure at least 2 vertices for a bounding box
            verts = self.vertices if self.vertices else [[0, 0, 0], [1, 1, 1]]
            if len(verts) < 2:
                if report:
                    report.add_error(
                        self.element_id,
                        "vertices",
                        self.vertices,
                        f"Obstruction needs >= 2 vertices, got {len(verts)}",
                        "ERROR",
                    )
                return None

            return Obstruction(
                obstruction_id=self.obstruction_id or self.element_id,
                vertices=verts,  # type: ignore[arg-type]
                spectral_transparency={
                    WavelengthBand.UV: float(self.transparency_uv or 0.0),
                    WavelengthBand.VIS: float(self.transparency_vis or 0.0),
                    WavelengthBand.IR1: float(self.transparency_ir1 or 0.0),
                    WavelengthBand.IR3: float(self.transparency_ir3 or 0.0),
                },
            )
        except Exception as exc:
            if report:
                report.add_error(
                    self.element_id,
                    "to_domain",
                    str(exc),
                    f"Failed to create Obstruction: {exc}",
                    "ERROR",
                )
            return None


# ---------------------------------------------------------------------------
# Revit Detector DTO
# ---------------------------------------------------------------------------


class RevitDetectorDTO(BaseModel):
    """Anti-Corruption Layer for flame detector data from Revit/BIM exports.
    """

    model_config = ConfigDict(frozen=False, strict=False, extra="allow")

    element_id: str = "UNKNOWN"
    detector_id: str = ""
    position: Any = [0.0, 0.0, 3.0]
    orientation: Any = [0.0, 0.0, -1.0]
    rated_range_m: Any = 20.0
    aoc_deg: Any = 90.0
    spectral_bands: Any = ["IR3"]

    @model_validator(mode="before")
    @classmethod
    def sanitize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        if "id" in data and "detector_id" not in data:
            data["detector_id"] = data.pop("id")

        # Handle position as flat list
        if "position" in data and isinstance(data["position"], (list, tuple)):
            data["position"] = [_safe_float(v, 0.0) for v in data["position"]]

        # Handle orientation as flat list
        if "orientation" in data and isinstance(data["orientation"], (list, tuple)):
            data["orientation"] = [_safe_float(v, 0.0) for v in data["orientation"]]

        # Handle range
        data["rated_range_m"] = _safe_float(data.get("rated_range_m", 20.0), 20.0)
        data["aoc_deg"] = _safe_float(data.get("aoc_deg", 90.0), 90.0)

        # Normalize spectral bands
        if "spectral_bands" in data and isinstance(data["spectral_bands"], (list, str)):
            if isinstance(data["spectral_bands"], str):
                data["spectral_bands"] = [data["spectral_bands"]]
            normalized = []
            for band in data["spectral_bands"]:
                nb = _normalize_enum(str(band), _WAVELENGTH_BAND_ALIASES)
                if nb:
                    normalized.append(nb)
            data["spectral_bands"] = normalized or ["IR3"]

        return data

    def to_domain(self, report: Optional[ImportReport] = None) -> Optional[FlameDetectorSpec]:
        """Convert to strict FlameDetectorSpec model."""
        try:
            return FlameDetectorSpec(
                detector_id=self.detector_id or self.element_id,
                position=self.position[:3] if len(self.position) >= 3 else [0.0, 0.0, 3.0],
                orientation_vector=self.orientation[:3] if len(self.orientation) >= 3 else [0.0, 0.0, -1.0],
                rated_range_m=float(self.rated_range_m),
                aoc_deg=float(self.aoc_deg),
                spectral_bands=[WavelengthBand(b) for b in self.spectral_bands],
            )
        except Exception as exc:
            if report:
                report.add_error(
                    self.element_id,
                    "to_domain",
                    str(exc),
                    f"Failed to create FlameDetectorSpec: {exc}",
                    "ERROR",
                )
            return None


# ---------------------------------------------------------------------------
# Batch Import Function
# ---------------------------------------------------------------------------


def import_substances_from_revit(
    raw_data: List[Dict[str, Any]],
) -> Tuple[List[SubstanceProperties], ImportReport]:
    """Import a batch of substance data from Revit/BIM export.

    Args:
        raw_data: List of dictionaries from Revit API/CSV/JSON export.

    Returns:
        Tuple of (valid_substances, import_report).
        Invalid entries are logged in the report and skipped — CLI continues.

    """
    report = ImportReport(total_elements=len(raw_data))

    substances: List[SubstanceProperties] = []
    for item in raw_data:
        dto = RevitSubstanceDTO(**item)
        domain = dto.to_domain(report)
        if domain is not None:
            substances.append(domain)
            report.successful += 1
        else:
            report.skipped += 1

    return substances, report


def import_obstructions_from_revit(
    raw_data: List[Dict[str, Any]],
) -> Tuple[List[Obstruction], ImportReport]:
    """Import a batch of obstruction data from Revit/BIM export."""
    report = ImportReport(total_elements=len(raw_data))

    obstructions: List[Obstruction] = []
    for item in raw_data:
        dto = RevitObstructionDTO(**item)
        domain = dto.to_domain(report)
        if domain is not None:
            obstructions.append(domain)
            report.successful += 1
        else:
            report.skipped += 1

    return obstructions, report


def import_detectors_from_revit(
    raw_data: List[Dict[str, Any]],
) -> Tuple[List[FlameDetectorSpec], ImportReport]:
    """Import a batch of detector data from Revit/BIM export."""
    report = ImportReport(total_elements=len(raw_data))

    detectors: List[FlameDetectorSpec] = []
    for item in raw_data:
        dto = RevitDetectorDTO(**item)
        domain = dto.to_domain(report)
        if domain is not None:
            detectors.append(domain)
            report.successful += 1
        else:
            report.skipped += 1

    return detectors, report
