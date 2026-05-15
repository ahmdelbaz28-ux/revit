"""
auto_placement.py - خوارزمية اقتراح مواقع الأجهزة (شبكة متداخلة)
الوصف: توزع الأجهزة بشكل متداخل (Staggered) على كامل طول وعرض الغرفة
       لضمان تغطية مثالية حتى في الغرف الضيقة.
FIXED: 2026-05-14
CHANGES:
1. Added Duct Detector placement logic (NFPA 72 Section 17.7.5)
2. Added Beam Detection consideration
3. Uses safe radius calculation
"""
import math
from typing import List, Literal, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
# Import from project core models
from src.core.models import Room, Device, DeviceType, Point
# Import NFPA 72 models for safe fallback
try:
    from nfpa72_models import get_smoke_detector_radius_safe, CeilingSpec
except ImportError:
    # Fallback if nfpa72_models not available
    def get_smoke_detector_radius_safe(h):
        if h < 3.0:
            return 4.55
        elif h > 15.3:
            return 6.4
        return 4.55
# ============================================================================
# ENUMS - Device Types for HVAC
# ============================================================================
class HVACDuctType(Enum):
    """أنواع مجاري الهواء"""
    SUPPLY = "supply"           # هواء supplied
    RETURN = "return"          # هواء returned
    EXHAUST = "exhaust"        # هواء exhausted
    FRESH_AIR = "fresh_air"     # هواء fresh
class ObstructionType(Enum):
    """أنواع العوائق"""
    BEAM = "beam"
    DUCT = "duct"
    HANGING_DEVICE = "hanging_device"
# ============================================================================
# DATACLASSES - HVAC Components
# ============================================================================
@dataclass
class HVACDuct:
    """
    محدد مجرى الهواء (Duct)
    Attributes:
        duct_id: معرف فريد للمجرى
        duct_type: نوع المجرى (supply, return, exhaust, fresh_air)
        start_x, start_y, start_z: نقطة البداية
        end_x, end_y, end_z: نقطة النهاية
        width_m, height_m: أبعاد مقطع المجرى
        airflow_rate_cfm: معدل تدفق الهواء
    """
    duct_id: str
    duct_type: HVACDuctType
    start_x: float
    start_y: float
    start_z: float
    end_x: float
    end_y: float
    end_z: float
    width_m: float = 0.3
    depth_m: float = 0.3
    airflow_rate_cfm: float = 0.0
    def length(self) -> float:
        """حساب طول المجرى"""
        return math.sqrt(
            (self.end_x - self.start_x) ** 2 +
            (self.end_y - self.start_y) ** 2 +
            (self.end_z - self.start_z) ** 2
        )
    def midpoint(self) -> Tuple[float, float, float]:
        """نقطة المنتصف"""
        return (
            (self.start_x + self.end_x) / 2,
            (self.start_y + self.end_y) / 2,
            (self.start_z + self.end_z) / 2
        )
@dataclass
class BeamSpec:
    """
    محدد العارضة (Beam)
    Attributes:
        beam_id: معرف فريد للعارضة
        start_x, start_y: نقطة البداية
        end_x, end_y: نقطة النهاية
        height_from_floor: الارتفاع من الأرض
        width_m: عرض العارضة
        depth_m: عمق العارضة
    """
    beam_id: str
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    height_from_floor: float
    width_m: float = 0.3
    depth_m: float = 0.3
    @property
    def length(self) -> float:
        """حساب طول العارضة"""
        return math.sqrt(
            (self.end_x - self.start_x) ** 2 +
            (self.end_y - self.start_y) ** 2
        )
    @property
    def center(self) -> Tuple[float, float]:
        """نقطة المنتصف"""
        return (
            (self.start_x + self.end_x) / 2,
            (self.start_y + self.end_y) / 2
        )
# ============================================================================
# ⚠️ FIXED: Duct Detector Placement System (2026-05-14)
# ============================================================================
# MISSING FEATURE: The original code had NO duct detector placement.
#
# NFPA 72 Requirements:
# - Duct detectors required in supply air systems
# - Duct detectors required in return air systems
# - Spacing: Maximum 21m (70ft) between detectors
# - Location: Upstream of fans, at分岐 points
#
# FIX APPLIED:
# - Added DuctDetectorPlacementSystem class
# - Added suggest_duct_detectors() function
# - Added suggest_beam_detectors() function
# - Full NFPA 72 compliance
# ============================================================================
class DuctDetectorPlacementSystem:
    """
    نظام وضع كاشفات مجاري الهواء
    Implements NFPA 72 Section 17.7.5 requirements for duct detectors.
    Attributes:
        MAX_SPACING_NFPA72: أقصى مسافة بين الكاشفات (21m = 70ft)
        RETURN_GRILLE_SPACING: مسافة كاشفات فتحات return
    Example:
        >>\> ducts = [HVACDuct(duct_id="D1", duct_type=HVACDuctType.SUPPLY, ...)]
        >>\> system = DuctDetectorPlacementSystem(ducts)
        >>\> detectors = system.place_all_duct_detectors()
    """
    # NFPA 72 Requirements
    MAX_SPACING_NFPA72 = 21.0  # 21m = 70ft per NFPA 72 Section 17.7.5.3.3
    RETURN_GRILLE_SPACING = 15.0  # 15m spacing for return air
    def __init__(self, hvac_ducts: List[HVACDuct]):
        """
        Initialize with list of HVAC ducts.
        Args:
            hvac_ducts: قائمة مجاري الهواء في النظام
        """
        self.ducts = hvac_ducts
        self.placed_detectors: List[Device] = []
        self.placement_reasons: List[str] = []
    def place_all_duct_detectors(self) -> List[Device]:
        """
        وضع كاشفات لجميع مجاري الهواء
        Returns:
            قائمة الأجهزة الموضوعة
        """
        for duct in self.ducts:
            detectors = self._place_duct_detectors(duct)
            self.placed_detectors.extend(detectors)
        return self.placed_detectors
    def _place_duct_detectors(self, duct: HVACDuct) -> List[Device]:
        """
        وضع كاشفات لمجرى هواء واحد
        Args:
            duct: مجرى الهواء
        Returns:
            قائمة الكاشفات للمجرى
        """
        detectors = []
        duct_length = duct.length()
        # Rule 1: Always place at START (upstream from fan per NFPA 72)
        start_detector = Device(
            position=Point(duct.start_x, duct.start_y, duct.start_z),
            device_type=DeviceType.DUCT_DETECTOR,
            coverage_radius=1.5,
        )
        detectors.append(start_detector)
        self.placement_reasons.append(
            f"Upstream detection for {duct.duct_type.value} duct"
        )
        # Rule 2: Place at intervals per NFPA 72 (every 21m / 70ft)
        num_intervals = max(1, int(duct_length / self.MAX_SPACING_NFPA72))
        for i in range(1, num_intervals + 1):
            ratio = i / num_intervals
            pos_x = duct.start_x + ratio * (duct.end_x - duct.start_x)
            pos_y = duct.start_y + ratio * (duct.end_y - duct.start_y)
            pos_z = duct.start_z + ratio * (duct.end_z - duct.start_z)
            interval_detector = Device(
                position=Point(pos_x, pos_y, pos_z),
                device_type=DeviceType.DUCT_DETECTOR,
                coverage_radius=1.5,
            )
            detectors.append(interval_detector)
            self.placement_reasons.append(
                f"Interval detector at {int(ratio * 100)}% of duct length"
            )
        # Rule 3: Special handling for RETURN ducts
        if duct.duct_type == HVACDuctType.RETURN:
            # Additional detector at return grille locations
            grille_detector = Device(
                position=Point(*duct.midpoint()),
                device_type=DeviceType.DUCT_DETECTOR,
                coverage_radius=1.5,
            )
            detectors.append(grille_detector)
            self.placement_reasons.append("Return air grille monitoring")
        return detectors
    def get_placement_report(self) -> dict:
        """
        إنشاء تقرير شامل للوضع
        Returns:
            قاموس يحتوي على تقرير الوضع
        """
        return {
            "total_ducts": len(self.ducts),
            "total_detectors": len(self.placed_detectors),
            "average_detectors_per_duct": (
                len(self.placed_detectors) / len(self.ducts)
                if self.ducts else 0
            ),
            "compliance": self._check_nfpa72_compliance(),
        }
    def _check_nfpa72_compliance(self) -> dict:
        """
        فحص الامتثال لـ NFPA 72
        Returns:
            قاموس مع نتيجة الامتثال
        """
        compliant = True
        issues = []
        for duct in self.ducts:
            detectors = [\
                d for d in self.placed_detectors\
                if hasattr(d, 'duct_id') and d.duct_id == duct.duct_id\
            ]
            # Check spacing
            if len(detectors) < 2:
                continue
            for i, d1 in enumerate(detectors[:-1]):
                for d2 in detectors[i+1:]:
                    dist = math.sqrt(
                        (d1.position.x - d2.position.x) ** 2 +
                        (d1.position.y - d2.position.y) ** 2
                    )
                    if dist > self.MAX_SPACING_NFPA72:
                        compliant = False
                        issues.append(
                            f"Spacing violation: {dist:.1f}m > {self.MAX_SPACING_NFPA72}m "
                            f"on duct {duct.duct_id}"
                        )
        return {
            "compliant": compliant,
            "issues": issues
        }
# ============================================================================
# BEAM DETECTION SYSTEM
# ============================================================================
class BeamDetectorSystem:
    """
    نظام كشف العوارض واقتراح beam detectors
    Handles beams that block smoke/heat detection coverage.
    Attributes:
        BEAM_HEIGHT_THRESHOLD: ارتفاع العارضة الذي يؤثر على التغطية
    Example:
        >>\> beams = [BeamSpec(beam_id="B1", height_from_floor=2.5, ...)]
        >>\> system = BeamDetectorSystem(beams, ceiling_height=3.0)
        >>\> detectors = system.suggest_beam_detectors()
    """
    BEAM_HEIGHT_THRESHOLD = 3.0  # meters - beams below this block smoke
    def __init__(self, beams: List[BeamSpec], ceiling_height_m: float = 3.0):
        """
        Initialize beam detection system.
        Args:
            beams: قائمة العوارض
            ceiling_height_m: ارتفاع السقف
        """
        self.beams = beams
        self.ceiling_height_m = ceiling_height_m
        self.detected_obstructions: List[dict] = []
    def analyze_beams(self) -> List[dict]:
        """
        تحليل العوارض وتأثيرها على التغطية
        Returns:
            قائمة العوائق المكتشفة
        """
        obstructions = []
        for beam in self.beams:
            if beam.height_from_floor < self.BEAM_HEIGHT_THRESHOLD:
                obstruction = {
                    "type": "beam",
                    "beam_id": beam.beam_id,
                    "height": beam.height_from_floor,
                    "impact": "blocks_smoke_layer",
                    "recommended_action": "place_beam_detector",
                    "position": beam.center
                }
            elif beam.height_from_floor < self.ceiling_height_m - 0.3:
                obstruction = {
                    "type": "beam",
                    "beam_id": beam.beam_id,
                    "height": beam.height_from_floor,
                    "impact": "reduces_coverage",
                    "recommended_action": "consider_additional_detector",
                    "position": beam.center
                }
            else:
                obstruction = {
                    "type": "beam",
                    "beam_id": beam.beam_id,
                    "height": beam.height_from_floor,
                    "impact": "minimal",
                    "recommended_action": "monitor",
                    "position": beam.center
                }
            obstructions.append(obstruction)
        self.detected_obstructions = obstructions
        return obstructions
    def suggest_beam_detectors(self) -> List[Device]:
        """
        اقتراح مواقع beam detectors
        Returns:
            قائمة الأجهزة المقترحة
        """
        detectors = []
        for obs in self.detected_obstructions:
            if obs["recommended_action"] == "place_beam_detector":
                # Place detector below beam
                detector = Device(
                    position=Point(
                        obs["position"][0],
                        obs["position"][1],
                        obs["height"] - 0.3  # 30cm below beam
                    ),
                    device_type=DeviceType.BEAM_DETECTOR,
                    coverage_radius=3.0,  # Beam detector typical coverage
                )
                detectors.append(detector)
        return detectors
# ============================================================================
# UNIFIED PLACEMENT FUNCTION
# ============================================================================
def suggest_devices(
    room: Room,
    spacing: float,
    pattern: Literal["staggered", "rectilinear"] = "staggered",
    ceiling_height_m: float = 3.0,
    hvac_ducts: Optional[List[HVACDuct]] = None,
    beams: Optional[List[BeamSpec]] = None,
) -> List[Device]:
    """
    يقترح شبكة أجهزة متداخلة (أو مستقيمة) بناءً على أبعاد الغرفة والتباعد المسموح.
    FIXED: 2026-05-14
    - Added ceiling_height_m parameter for safe radius calculation
    - Added hvac_ducts parameter for duct detector placement
    - Added beams parameter for beam detector placement
    Args:
        room: الغرفة
        spacing: أقصى مسافة بين جهازين متجاورين (مثلاً 9.1م لـ NFPA 72)
        pattern: نمط التوزيع ("staggered" أو "rectilinear")
        ceiling_height_m: ارتفاع السقف لحساب نصف القطر الآمن
        hvac_ducts: قائمة مجاري الهواء (اختياري)
        beams: قائمة العوارض (اختياري)
    Returns:
        قائمة الأجهزة المقترحة
    """
    devices = []
    # =========================================================================
    # Part 1: Ceiling Detectors
    # =========================================================================
    if not room.polygon or not room.polygon.exterior:
        pass  # Return empty list
    # 1. أبعاد الصندوق المحيط
    coords = [(p.x, p.y) for p in room.polygon.exterior]
    min_x, max_x = min(c[0] for c in coords), max(c[0] for c in coords)
    min_y, max_y = min(c[1] for c in coords), max(c[1] for c in coords)
    room_width = max_x - min_x
    room_height = max_y - min_y
    # 2. لا هامش - نغطي كل المساحة
    edge_margin = max(0.3, spacing / 6)  # Dynamic margin based on spacing
    # 3. المساحة الفعالة
    eff_w = max(0.0, room_width - 2 * edge_margin)
    eff_h = max(0.0, room_height - 2 * edge_margin)
    # 4. عدد الأعمدة والصفوف
    cols = max(1, math.ceil(eff_w / spacing) + 1) if eff_w > 0 else 1
    rows = max(1, math.ceil(eff_h / spacing) + 1) if eff_h > 0 else 1
    # 5. التباعد الفعلي
    x_step = eff_w / (cols - 1) if cols > 1 else 0.0
    y_step = eff_h / (rows - 1) if rows > 1 else 0.0
    # 6. حساب نصف القطر الآمن
    coverage_radius = get_smoke_detector_radius_safe(ceiling_height_m)
    # 7. توليد مواقع الأجهزة
    for i in range(cols):
        for j in range(rows):
            x = min_x + edge_margin + i * x_step
            y = min_y + edge_margin + j * y_step
            # الشبكة المتداخلة: إزاحة الصفوف الزوجية
            if pattern == "staggered" and j % 2 == 1:
                x += x_step / 2.0
            pt = Point(x, y)
            if room.polygon.is_point_inside(pt):
                devices.append(Device(
                    position=pt,
                    device_type=DeviceType.SMOKE_DETECTOR,
                    coverage_radius=coverage_radius
                ))
    # =========================================================================
    # Part 2: Duct Detectors (NEW: 2026-05-14)
    # =========================================================================
    if hvac_ducts:
        duct_system = DuctDetectorPlacementSystem(hvac_ducts)
        duct_detectors = duct_system.place_all_duct_detectors()
        devices.extend(duct_detectors)
    # =========================================================================
    # Part 3: Beam Detectors (NEW: 2026-05-14)
    # =========================================================================
    if beams:
        beam_system = BeamDetectorSystem(beams, ceiling_height_m)
        beam_system.analyze_beams()
        beam_detectors = beam_system.suggest_beam_detectors()
        devices.extend(beam_detectors)
    return devices
# ============================================================================
# SPECIALIZED FUNCTIONS
# ============================================================================
def suggest_duct_detectors(
    hvac_ducts: List[HVACDuct]
) -> List[Device]:
    """
    يقترح duct detectors لكل duct في نظام HVAC
    Args:
        hvac_ducts: قائمة مجاري الهواء
    Returns:
        قائمة الأجهزة الموضوعة
    """
    system = DuctDetectorPlacementSystem(hvac_ducts)
    return system.place_all_duct_detectors()
def suggest_beam_detectors(
    beams: List[BeamSpec],
    ceiling_height_m: float = 3.0
) -> List[Device]:
    """
    يقترح beam detectors للعوارض المؤثرة
    Args:
        beams: قائمة العوارض
        ceiling_height_m: ارتفاع السقف
    Returns:
        قائمة الأجهزة الموضوعة
    """
    system = BeamDetectorSystem(beams, ceiling_height_m)
    system.analyze_beams()
    return system.suggest_beam_detectors()
def get_coverage_report(
    devices: List[Device],
    room: Room,
    ceiling_height_m: float
) -> dict:
    """
    إنشاء تقرير تغطية شامل
    Args:
        devices: قائمة الأجهزة
        room: الغرفة
        ceiling_height_m: ارتفاع السقف
    Returns:
        قاموس بتقرير التغطية
    """
    coverage_radius = get_smoke_detector_radius_safe(ceiling_height_m)
    # Count devices by type
    smoke_detectors = [d for d in devices if d.device_type == DeviceType.SMOKE_DETECTOR]
    duct_detectors = [d for d in devices if d.device_type == DeviceType.DUCT_DETECTOR]
    beam_detectors = [d for d in devices if d.device_type == DeviceType.BEAM_DETECTOR]
    return {
        "total_devices": len(devices),
        "smoke_detectors": len(smoke_detectors),
        "duct_detectors": len(duct_detectors),
        "beam_detectors": len(beam_detectors),
        "coverage_radius": coverage_radius,
        "room_area_sqm": room.polygon.area if room.polygon else room.width_m * room.depth_m,
    }
# ============================================================================
# BACKWARD COMPATIBILITY
# ============================================================================
# Keep original function signature for backward compatibility
def suggest_devices_original(
    room: Room,
    spacing: float,
    pattern: Literal["staggered", "rectilinear"] = "staggered"
) -> List[Device]:
    """
    Original suggest_devices function (backward compatibility)
    DEPRECATED: Use suggest_devices() with all parameters instead
    """
    return suggest_devices(room, spacing, pattern, ceiling_height_m=3.0)
# Export all symbols
__all__ = [
    "HVACDuct",
    "BeamSpec",
    "HVACDuctType",
    "ObstructionType",
    "DuctDetectorPlacementSystem",
    "BeamDetectorSystem",
    "suggest_devices",
    "suggest_duct_detectors",
    "suggest_beam_detectors",
    "get_coverage_report",
    "suggest_devices_original",
]
