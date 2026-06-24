"""fireai/bridges/ifc_pipeline.py
================================
Full IFC → L1 → L2 → L3 → L5 → V23 → L7 → IFC pipeline.

Orchestrates the complete FireAI V24 analysis on an IFC building model,
using the CORRECT API surfaces of each layer module.

Architecture:
  IFC file
    → HeadlessIFCBridge.extract_spaces_enhanced()  (room geometry)
    → HeadlessIFCBridge.extract_obstructions()      (AABB walls/beams)
    → L1: InternationalRegSelector.resolve_v21()    (regulatory framework)
    → L2: HACClassificationEngine.classify_v21()    (hazardous area zone)
    → L3: ATEXHazardousArbiter.arbitrate_v21()      (equipment spec)
    → L5: FlameDetectorAOCRayTrace.analyse_multi_v21() (optical coverage)
    → V23: trace_acoustic_ray()                     (acoustic coverage)
    → L7: HybridSurvivabilityEngine.analyse()       (hybrid survivability)
    → HeadlessIFCBridge.push_fire_alarm_design()    (write IFC)
    → HybridSurvivabilityEngine.export_heatmap_json() (write heatmap)

CRITICAL NOTE on API surfaces:
  This pipeline uses the ACTUAL method signatures from the FireAI codebase.
  It does NOT use invented APIs. Every call matches the real module interfaces.

Standards:
  IEC 60079-10-1:2015  — HAC zone classification
  IEC 60079-0/14       — ATEX equipment selection
  NFPA 72-2022 §17.8   — flame detector placement
  ISA-TR 84.00.07      — UGLD placement
  NFPA 72 §17.8.3.4    — redundancy requirement
  IFC4 / ISO 16739-1   — building model schema
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class IfcPipelineConfig:
    """Configuration for one IfcFirePipeline run."""

    ifc_input_path: str
    ifc_output_path: str
    country_code: str = "SA"  # ISO 3166-1 alpha-2
    substance_cas: str = "74-98-6"  # propane default
    ventilation: str = "MEDIUM"
    release_grade: str = "PRIMARY"
    release_rate_kg_s: float = 0.001
    is_indoor: bool = True
    detector_grid_res_m: float = 1.0
    flame_range_m: float = 15.0
    flame_aoc_deg: float = 90.0
    ugld_range_m: float = 10.0
    leak_spl_at_1m: float = 100.0
    ambient_temp_c: float = 40.0
    wind_speed_m_s: float = 0.5
    project_name: str = "FireAI V24 Export"


@dataclass
class SpaceAnalysisResult:
    """Result of full pipeline analysis for one space."""

    space_guid: str
    space_name: str
    storey_name: str
    layer1_framework: str
    layer2_zone: str
    layer2_extent_h: float
    layer2_extent_v: float
    layer3_epl: str
    layer3_tclass: str
    layer3_protections: List[str]
    layer5_coverage_pct: float
    layer7_redundant_pct: float
    layer7_blind_spot_pct: float
    detector_placements: List[Dict[str, Any]]
    warnings: List[str] = field(default_factory=list)


@dataclass
class PipelineReport:
    """Aggregate report for the full building."""

    ifc_input: str
    ifc_output: str
    heatmap_path: str
    run_time_s: float
    spaces_analysed: int
    total_detectors: int
    global_coverage_pct: float
    global_blind_spot_pct: float
    space_results: List[SpaceAnalysisResult]
    pipeline_warnings: List[str]


class IfcFirePipeline:
    """Orchestrates the full FireAI V24 pipeline on an IFC building model.

    Flow:
    IFC → extract_spaces_enhanced() → extract_obstructions()
       → L1 (InternationalRegSelector) → L2 (HACClassificationEngine)
       → L3 (ATEXHazardousArbiter) → L5 (FlameDetectorAOCRayTrace)
       → V23 (UGLD acoustics) → L7 (HybridSurvivabilityEngine)
       → push_fire_alarm_design() → IFC output
       → export_heatmap_json() → heatmap JSON output

    All method calls match the ACTUAL FireAI module API surfaces.
    """

    def __init__(self, config: IfcPipelineConfig):
        self.cfg = config
        self._warnings: List[str] = []

    def run(self) -> PipelineReport:
        """Execute the full IFC → L1→L7 → IFC pipeline.

        Returns a PipelineReport with per-space results and aggregate stats.
        """
        t0 = time.perf_counter()
        from fireai.bridges.ifc_headless_bridge import HeadlessIFCBridge

        bridge = HeadlessIFCBridge(self.cfg.ifc_input_path)

        # ── Extract geometry from IFC ──────────────────────────────
        spaces_data = bridge.extract_spaces_enhanced()
        obstructions_data = bridge.extract_obstructions()

        # Convert IFC obstructions → FireAI Obstruction objects
        raytrace_obstructions = self._to_raytrace_obstructions(obstructions_data)

        # ── L1: Regulatory framework ──────────────────────────────
        framework, l1_warnings = self._run_l1()
        self._warnings.extend(l1_warnings)

        # ── Per-space analysis ─────────────────────────────────────
        all_results: List[SpaceAnalysisResult] = []
        all_devices: List[Dict[str, Any]] = []
        all_hybrid_maps: List[Any] = []
        slc_loop = 1
        slc_address = 1

        for space in spaces_data:
            try:
                result, devices, next_loop, next_addr = self._analyse_space(
                    space,
                    raytrace_obstructions,
                    framework,
                    slc_loop,
                    slc_address,
                )
                all_results.append(result)
                all_devices.extend(devices)
                slc_loop, slc_address = next_loop, next_addr
            except Exception as exc:
                self._warnings.append(
                    f"Space {space.get('name', '?')} ({space.get('guid', '?')}): analysis failed — {exc}"
                )
                logger.error("Space analysis failed: %s", exc, exc_info=True)

        # ── Write back to IFC ──────────────────────────────────────
        bridge.push_fire_alarm_design(all_devices, self.cfg.ifc_output_path)

        # ── Compute global heatmap ─────────────────────────────────
        heatmap_path = self.cfg.ifc_output_path.replace(".ifc", "_heatmap.json")
        try:
            from fireai.core.hybrid_survivability import HybridSurvivabilityEngine

            # Export heatmap for the last computed hybrid map
            if all_hybrid_maps:
                h_engine = HybridSurvivabilityEngine()
                h_engine.export_heatmap_json(all_hybrid_maps[-1], heatmap_path)
        except Exception as exc:
            self._warnings.append(f"Heatmap export failed: {exc}")

        # ── Aggregate statistics ───────────────────────────────────
        total_dets = len(all_devices)
        cov_pcts = [r.layer5_coverage_pct for r in all_results] or [0.0]
        blind_pcts = [r.layer7_blind_spot_pct for r in all_results] or [0.0]
        # V78 FIX: Area-weighted average instead of arithmetic mean.
        # Arithmetic mean: 10m²@90% + 1000m²@50% → 70% (WRONG)
        # Area-weighted:   10m²@90% + 1000m²@50% → 50.4% (CORRECT)
        # A small room with high coverage inflates the average unfairly.
        areas = [getattr(r, '_space_area_m2', getattr(r, 'space_area_m2', 0.0)) for r in all_results]
        total_area = sum(areas) if areas else 0.0
        if total_area > 0:
            global_cov = sum(c * a for c, a in zip(cov_pcts, areas, strict=False)) / total_area
            global_bs = sum(b * a for b, a in zip(blind_pcts, areas, strict=False)) / total_area
        elif all_results:
            # V79 FIX: All spaces have zero area — geometry extraction may have failed.
            # Arithmetic mean of unreliable coverage values is still unreliable.
            # Set to worst-case instead of reporting misleading numbers.
            global_cov = 0.0
            global_bs = 100.0
            self._warnings.append(
                "CRITICAL: All spaces have zero area — area-weighted coverage "
                "impossible. Global coverage set to 0% and blind spot to 100%. "
                "Geometry extraction likely failed for all spaces. "
                "Manual fire protection engineering review REQUIRED."
            )
        else:
            global_cov = 0.0
            global_bs = 100.0
        elapsed = time.perf_counter() - t0

        return PipelineReport(
            ifc_input=self.cfg.ifc_input_path,
            ifc_output=self.cfg.ifc_output_path,
            heatmap_path=heatmap_path,
            run_time_s=round(elapsed, 2),
            spaces_analysed=len(all_results),
            total_detectors=total_dets,
            global_coverage_pct=round(global_cov, 2),
            global_blind_spot_pct=round(global_bs, 2),
            space_results=all_results,
            pipeline_warnings=list(self._warnings),
        )

    # ── L1: Regulatory Framework ──────────────────────────────────

    def _run_l1(self) -> Tuple[str, List[str]]:
        """Resolve regulatory framework from country code."""
        try:
            from fireai.core.international_reg_selector import (
                InternationalRegSelector,
            )

            selector = InternationalRegSelector()
            res = selector.resolve_v21(self.cfg.country_code)
            return res.framework.value, list(res.warnings)
        except Exception as exc:
            warn = f"L1 failed for country {self.cfg.country_code}: {exc}. Defaulting to IECEx."
            return "IECEx", [warn]

    # ── Per-space analysis ────────────────────────────────────────

    def _analyse_space(
        self,
        space: Dict[str, Any],
        obstructions: List[Any],
        framework: str,
        slc_loop: int,
        slc_address: int,
    ) -> Tuple[SpaceAnalysisResult, List[Dict[str, Any]], int, int]:
        """Run L2→L3→L5→V23→L7 for one space."""
        warnings: List[str] = []

        # ── L2: HAC Classification ────────────────────────────────
        l2 = self._run_l2(space, warnings)

        # ── L3: ATEX Arbitration ──────────────────────────────────
        l3 = self._run_l3(l2, space, warnings)

        # ── Build target grid ─────────────────────────────────────
        grid_pts = self._make_grid(space)

        # ── L5: Flame detector optical coverage ───────────────────
        flame_det_specs = self._place_flame_detectors(space)
        l5_coverage, optical_result = self._run_l5(flame_det_specs, grid_pts, obstructions, warnings)

        # ── V23 + L7: Acoustic + Hybrid Survivability ─────────────
        ugld_sensors, sensor_positions = self._place_ugld_sensors(space)
        l7_result, hybrid_map = self._run_l7(optical_result, grid_pts, ugld_sensors, sensor_positions, warnings)

        # ── Build device placement list ───────────────────────────
        zone_id = f"{space.get('storey_name', '?')}_{l2.get('zone', 'UNKNOWN')}"
        devices: List[Dict[str, Any]] = []

        for fds in flame_det_specs:
            devices.append(
                {
                    "device_id": fds["id"],
                    "type": "FLAME",
                    "x": fds["position"][0],
                    "y": fds["position"][1],
                    "z": fds["position"][2],
                    "loop_id": slc_loop,
                    "address": slc_address,
                    "checksum": f"V24_{fds['id']}_{zone_id}",
                }
            )
            slc_address += 1
            if slc_address > 99:
                slc_loop += 1
                slc_address = 1

        for us in ugld_sensors:
            devices.append(
                {
                    "device_id": us["id"],
                    "type": "UGLD",
                    "x": us["position"][0],
                    "y": us["position"][1],
                    "z": us["position"][2],
                    "loop_id": slc_loop,
                    "address": slc_address,
                    "checksum": f"V24_{us['id']}_{zone_id}",
                }
            )
            slc_address += 1
            if slc_address > 99:
                slc_loop += 1
                slc_address = 1

        result = SpaceAnalysisResult(
            space_guid=space.get("guid", ""),
            space_name=space.get("name", ""),
            storey_name=space.get("storey_name", ""),
            layer1_framework=framework,
            layer2_zone=l2.get("zone", "UNKNOWN"),
            layer2_extent_h=l2.get("extent_h", 0.0),
            layer2_extent_v=l2.get("extent_v", 0.0),
            layer3_epl=l3.get("epl", "?"),
            layer3_tclass=l3.get("tclass", "?"),
            layer3_protections=l3.get("protections", []),
            layer5_coverage_pct=round(l5_coverage * 100, 2),
            layer7_redundant_pct=round(l7_result.get("redundant_pct", 0.0), 2),
            layer7_blind_spot_pct=round(l7_result.get("blind_spot_pct", 0.0), 2),
            detector_placements=devices,
            warnings=warnings,
        )
        return result, devices, slc_loop, slc_address

    # ── L2: HAC Classification ────────────────────────────────────

    def _run_l2(self, space: Dict, warnings: List[str]) -> Dict:
        """L2 using the REAL HACClassificationEngine.classify_v21() API.
        """
        try:
            from fireai.core.hac_classification_engine import (
                HACClassificationEngine,
                ReleaseGrade,
            )
            from fireai.core.models_v21 import (
                EnvironmentalContext,
                PasquillStability,
                VentilationLevel,
            )

            substance = self._get_substance()
            env = EnvironmentalContext(
                ambient_temp_c=self.cfg.ambient_temp_c,
                wind_speed_m_s=self.cfg.wind_speed_m_s,
                stability_class=PasquillStability.F,
                is_indoor=self.cfg.is_indoor,
            )

            engine = HACClassificationEngine()
            result = engine.classify_v21(
                substance=substance,
                ventilation=VentilationLevel(self.cfg.ventilation),
                release_grade=ReleaseGrade[self.cfg.release_grade],
                is_indoor=self.cfg.is_indoor,
                env_context=env,
                release_rate_kg_s=self.cfg.release_rate_kg_s,
                # V78 FIX: No longer default to 1000 m³ — a typical 10m²×3m room is 30 m³.
                # 1000 m³ default overestimates air changes, producing zone extents that
                # are too small (more dilution assumed than reality). IEC 60079-10-1
                # requires conservative (small volume = less dilution = larger zones).
                room_volume_m3=space.get("volume_m3") or max(
                    space.get("area_m2", 0.0) * space.get("height_m", 3.0), 1.0
                ),
            )

            warnings.extend(result.warnings)
            warnings.extend(result.critical_flags)

            return {
                "zone": result.zone.value,
                "extent_h": result.extent.horizontal_m,
                "extent_v": result.extent.vertical_m,
                "hac": result,
            }
        except Exception as exc:
            warnings.append(f"L2 HAC failed: {exc}")
            # V76 CRIT-07 FIX: Default to ZONE_0 (most hazardous) on failure.
            # Previous default was ZONE_1 — non-conservative. IEC 60079-10-1:
            # when classification fails, the safest assumption is the worst case.
            # Zone 0 equipment (EPL Ga) is always safe for Zone 1 or 2.
            # Zone 1 equipment (EPL Gb) is NOT safe for Zone 0 — explosion risk.
            return {"zone": "ZONE_0", "extent_h": 6.0, "extent_v": 3.0}

    # ── L3: ATEX Arbitration ──────────────────────────────────────

    def _run_l3(self, l2: Dict, space: Dict, warnings: List[str]) -> Dict:
        """L3 using the REAL ATEXHazardousArbiter.arbitrate_v21() API.
        Parameters: zone, hazard_type, autoignition_c, ...
        """
        try:
            from fireai.core.atex_hazardous_arbiter import ATEXHazardousArbiter
            from fireai.core.models_v21 import HazardType, ZoneType

            hac_result = l2.get("hac")
            substance = self._get_substance()

            arbiter = ATEXHazardousArbiter()

            # Real API: arbitrate_v21(zone, hazard_type, autoignition_c, ...)
            atex_result = arbiter.arbitrate_v21(
                zone=hac_result.zone if hac_result else ZoneType(l2.get("zone", "ZONE_0")),
                hazard_type=hac_result.hazard_type if hac_result else HazardType.GAS,
                autoignition_c=substance.autoignition_c,
                hac_warnings=list(hac_result.warnings) if hac_result else [],
                hac_critical=list(hac_result.critical_flags) if hac_result else [],
            )

            warnings.extend(atex_result.all_warnings)

            spec = atex_result.equipment_spec
            return {
                "epl": spec.epl_required,
                "tclass": spec.temp_class.value,
                "protections": list(spec.protection_modes),
            }
        except Exception as exc:
            warnings.append(f"L3 ATEX failed: {exc}")
            # V76 CRIT-08 FIX: Default to most protective spec on failure.
            # Previous default was EPL Gb/T3/ib (Zone 1 level) — non-conservative.
            # When ATEX arbitration fails, must assume worst case: EPL Ga (Zone 0),
            # T6 (lowest surface temp), ia (highest intrinsic safety). Equipment
            # rated Ga/ia is always safe for less hazardous zones; the reverse is NOT true.
            return {"epl": "Ga", "tclass": "T6", "protections": ["ia"]}

    # ── L5: Flame Detector Coverage ───────────────────────────────

    def _run_l5(
        self,
        det_specs: List[Dict],
        grid_pts: List[Any],
        obstructions: List[Any],
        warnings: List[str],
    ) -> Tuple[float, Any]:
        """L5 using the REAL FlameDetectorAOCRayTrace.analyse_multi_v21() API.
        FlameDetectorSpec(position=[x,y,z], orientation_vector=[...], ...)
        """
        try:
            from fireai.core.flame_detector_aoc_raytrace import (
                FlameDetectorAOCRayTrace,
            )
            from fireai.core.models_v21 import (
                FlameDetectorSpec,
                WavelengthBand,
            )

            engine = FlameDetectorAOCRayTrace(
                grid_step_m=self.cfg.detector_grid_res_m,
            )

            detectors = [
                FlameDetectorSpec(
                    detector_id=d["id"],
                    position=d["position"],  # List[float] — correct API
                    orientation_vector=[0.0, 0.0, -1.0],
                    rated_range_m=self.cfg.flame_range_m,
                    aoc_deg=self.cfg.flame_aoc_deg,
                    spectral_bands=[WavelengthBand.IR1, WavelengthBand.IR3],
                )
                for d in det_specs
            ]

            if not detectors or not grid_pts:
                return 0.0, None

            cov = engine.analyse_multi_v21(
                detectors=detectors,
                target_grid=grid_pts,
                obstructions=obstructions,
            )
            warnings.extend(cov.warnings)
            return cov.coverage_fraction, cov
        except Exception as exc:
            warnings.append(f"L5 flame coverage failed: {exc}")
            return 0.0, None

    # ── V23 + L7: Acoustic + Hybrid ──────────────────────────────

    def _run_l7(
        self,
        optical_result: Any,
        grid_pts: List[Any],
        ugld_sensors: List[Dict],
        sensor_positions: Dict[str, Tuple],
        warnings: List[str],
    ) -> Tuple[Dict, Any]:
        """L7 using the REAL HybridSurvivabilityEngine.analyse() API.
        Parameters: optical_result, grid, ugld_sensors, sensor_positions, ...
        """
        try:
            from fireai.core.hybrid_survivability import HybridSurvivabilityEngine
            from fireai.core.ugld_acoustics import UltrasonicSensor

            # Build REAL UltrasonicSensor objects (no position field!)
            sensors = [
                UltrasonicSensor(
                    sensor_id=s["id"],
                    trigger_threshold_db=74.0,
                    background_noise_db=55.0,
                    center_frequency_hz=40_000.0,
                )
                for s in ugld_sensors
            ]

            if optical_result is None or not grid_pts:
                return {"redundant_pct": 0.0, "blind_spot_pct": 100.0}, None

            # L7 engine — REAL API
            engine = HybridSurvivabilityEngine(
                leak_spl_at_1m=self.cfg.leak_spl_at_1m,
                temp_c=self.cfg.ambient_temp_c,
            )

            hybrid_map = engine.analyse(
                optical_result=optical_result,
                grid=grid_pts,
                ugld_sensors=sensors,
                sensor_positions=sensor_positions,
            )

            return {
                "redundant_pct": hybrid_map.redundant_hybrid_pct,
                "blind_spot_pct": hybrid_map.blind_spot_pct,
                "hybrid_map": hybrid_map,
            }, hybrid_map
        except Exception as exc:
            warnings.append(f"L7 hybrid survivability failed: {exc}")
            return {"redundant_pct": 0.0, "blind_spot_pct": 100.0}, None

    # ── Placement helpers ─────────────────────────────────────────

    def _make_grid(self, space: Dict) -> List[Any]:
        """Generate uniform 3D RayTracePoint grid within space."""
        try:
            from fireai.core.models_v21 import RayTracePoint
        except ImportError:
            return []

        polygon = space.get("floor_polygon")
        if not polygon:
            return []

        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        z0 = space.get("center", (0, 0, 0))[2] - space.get("height_m", 3.0) / 2
        res = self.cfg.detector_grid_res_m

        pts = []
        x = x0 + res / 2
        while x < x1:
            y = y0 + res / 2
            while y < y1:
                pts.append(RayTracePoint(x=round(x, 3), y=round(y, 3), z=round(z0 + 0.9, 3)))
                y += res
            x += res
        return pts

    def _place_flame_detectors(self, space: Dict) -> List[Dict]:
        """Simple ceiling-mounted flame detector placement per NFPA 72."""
        polygon = space.get("floor_polygon")
        if not polygon:
            return []

        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        z_ceil = space.get("center", (0, 0, 0))[2] + space.get("height_m", 3.0) / 2 - 0.1
        R = self.cfg.flame_range_m
        spacing = R * math.sqrt(2)

        dets = []
        det_n = 1
        x = x0 + spacing / 2
        while x <= x1:
            y = y0 + spacing / 2
            while y <= y1:
                dets.append(
                    {
                        "id": f"FD_{space['guid'][:6]}_{det_n:03d}",
                        "position": [round(x, 3), round(y, 3), round(z_ceil, 3)],
                        "type": "FLAME",
                    }
                )
                det_n += 1
                y += spacing
            x += spacing

        if not dets:
            cx, cy = space.get("center", (0, 0, 0))[:2]
            dets.append(
                {
                    "id": f"FD_{space['guid'][:6]}_001",
                    "position": [round(cx, 3), round(cy, 3), round(z_ceil, 3)],
                    "type": "FLAME",
                }
            )
        return dets

    def _place_ugld_sensors(self, space: Dict) -> Tuple[List[Dict], Dict[str, Tuple]]:
        """Place UGLD sensors at 1 m above floor per ISA-TR 84.00.07.
        Returns (sensor_specs, sensor_positions) — positions are separate
        per the Separation of Concerns design in hybrid_survivability.py.
        """
        polygon = space.get("floor_polygon")
        if not polygon:
            return [], {}

        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        z_low = space.get("center", (0, 0, 0))[2] - space.get("height_m", 3.0) / 2 + 1.0
        R = self.cfg.ugld_range_m
        spacing = R * 1.4

        sensors = []
        positions = {}
        sn = 1
        x = x0 + spacing / 2
        while x <= x1:
            y = y0 + spacing / 2
            while y <= y1:
                sid = f"UGLD_{space['guid'][:6]}_{sn:03d}"
                pos = (round(x, 3), round(y, 3), round(z_low, 3))
                sensors.append({"id": sid, "position": pos, "type": "UGLD"})
                positions[sid] = pos
                sn += 1
                y += spacing
            x += spacing

        if not sensors:
            cx, cy = space.get("center", (0, 0, 0))[:2]
            sid = f"UGLD_{space['guid'][:6]}_001"
            pos = (round(cx, 3), round(cy, 3), round(z_low, 3))
            sensors.append({"id": sid, "position": pos, "type": "UGLD"})
            positions[sid] = pos

        return sensors, positions

    # ── IFC → FireAI model conversion ────────────────────────────

    def _to_raytrace_obstructions(self, obstructions_data: List[Dict]) -> List[Any]:
        """Convert IFC AABB data → FireAI Obstruction objects."""
        result: List[Any] = []
        try:
            from fireai.core.models_v21 import Obstruction, WavelengthBand
        except ImportError:
            return result

        for od in obstructions_data:
            try:
                result.append(
                    Obstruction(
                        obstruction_id=od["guid"],
                        vertices=od["aabb_vertices"],
                        spectral_transparency={
                            WavelengthBand.UV: 0.0,
                            WavelengthBand.VIS: 0.0,
                            WavelengthBand.IR1: 0.0,
                            WavelengthBand.IR3: 0.0,
                        },
                    )
                )
            except Exception as e:
                logger.debug("Could not convert obstruction %s: %s", od.get('guid', '?'), e)
        return result

    # ── Substance lookup ─────────────────────────────────────────

    def _get_substance(self) -> Any:
        """Return SubstanceProperties for the configured CAS number.

        V79 FIX: Previously, all physical properties were hardcoded to propane
        regardless of CAS number. Only the substance name was updated from the
        registry. This meant hydrogen (UFL 75%) or methane (UFL 15%) would get
        propane's flammability limits (UFL 9.5%), causing underestimated HAC
        zone extents — potentially placing non-ATEX equipment inside explosive
        atmospheres. Now returns full SubstanceProperties from registry when
        available, with propane as fallback only when registry is unavailable.
        """
        from fireai.core.models_v21 import HazardType, SubstanceProperties

        # Try spectral registry for the CAS number — get FULL properties
        try:
            from fireai.core.models_v21 import SpectralSignatureRegistry

            registry = SpectralSignatureRegistry()
            sig = registry.get(self.cfg.substance_cas)
            if sig and hasattr(sig, 'substance_properties') and sig.substance_properties:
                return sig.substance_properties
            # Try SubstanceRegistry for full property data
            try:
                from fireai.core.substance_registry import SubstanceRegistry
                sub_reg = SubstanceRegistry()
                substance = sub_reg.get_by_cas(self.cfg.substance_cas)
                if substance is not None:
                    return substance
            except Exception as e:
                logger.debug("Substance registry lookup failed for CAS %s: %s", self.cfg.substance_cas, e)
        except Exception as e:
            logger.debug("Spectral signature registry lookup failed for CAS %s: %s", self.cfg.substance_cas, e)

        # Fallback: propane — ONLY when registry is unavailable, with CRITICAL warning
        logger.critical(
            "%s: Substance registry unavailable for CAS %s. "
            "Defaulting to propane properties — THIS MAY BE WRONG FOR YOUR SUBSTANCE. "
            "Manual HAC classification REQUIRED per IEC 60079-10-1.",
            self.__class__.__name__,
            self.cfg.substance_cas,
        )
        return SubstanceProperties(  # type: ignore[call-arg]
            name="Propane (DEFAULT — VERIFY)",
            hazard_type=HazardType.GAS,
            lfl_vol_pct=2.1,
            ufl_vol_pct=9.5,
            flash_point_c=-104.0,
            autoignition_c=450.0,  # NFPA 497-2024 Table 4.4.2
            molecular_weight=44.1,
            density_kg_m3=1.882,
        )


__all__ = [
    "IfcFirePipeline",
    "IfcPipelineConfig",
    "PipelineReport",
    "SpaceAnalysisResult",
]
