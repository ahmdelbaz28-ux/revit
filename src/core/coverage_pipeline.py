"""
COVERAGE PIPELINE — PDF to Fire Protection Coverage Report
=====================================================
يربط InputPipeline بـ CoverageEngine لإنتاج تقرير تغطية كامل.

المسار: PDF → InputPipeline → CoveragePipeline → Coverage Report

Author: The Consultant Who Refused to Lie
"""

import math
from typing import List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from src.core.input_pipeline import InputPipeline, PipelineResult, PipelineStatus
from src.core.models import Room, Device, Violation, RoomType


class CoverageGrade(Enum):
    """درجة التغطية."""
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"
    PASS = "PASS"
    FULL = "FULL"


@dataclass
class CoverageReport:
    """تقرير التغطية الكامل."""
    # Input
    pdf_path: str
    drawing_score: float
    
    # Coverage results
    coverage_percentage: float
    grade: CoverageGrade
    violations: List[Violation]
    
    # Room info
    room_area_m2: float
    room_name: str
    
    # Devices info
    device_count: int
    smoke_detectors: int
    heat_detectors: int
    
    # Metadata
    ceiling_height_m: float
    requires_pe_review: bool
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "pdf": self.pdf_path,
            "score": self.drawing_score,
            "coverage": f"{self.coverage_percentage:.1f}%",
            "grade": self.grade.value,
            "violations": len(self.violations),
            "room": {
                "name": self.room_name,
                "area_m2": self.room_area_m2
            },
            "devices": {
                "total": self.device_count,
                "smoke": self.smoke_detectors,
                "heat": self.heat_detectors
            },
            "ceiling_height_m": self.ceiling_height_m,
            "requires_pe_review": self.requires_pe_review,
            "errors": self.errors
        }


class CoveragePipeline:
    """
    المسار الكامل من PDF إلى تقرير التغطية.
    
    PDF → InputPipeline → CoverageEngine → CoverageReport
    """
    
    def __init__(self, nfpa_standard=None):
        self.standard = nfpa_standard
        self._load_engine()
    
    def _load_engine(self):
        """تحميل CoverageEngine."""
        try:
            from src.application.coverage_service import CoverageService
            from src.core.models import Room, Device
            self.CoverageService = CoverageService
            self.Room = Room
            self.Device = Device
        except ImportError as e:
            raise ImportError(f"Coverage engine not available: {e}")
    
    def process(self, pdf_path: str) -> CoverageReport:
        """
        معالجة PDF وإنتاج تقرير تغطية.
        
        Args:
            pdf_path: مسار ملف PDF
            
        Returns:
            CoverageReport مع كل التفاصيل
        """
        errors = []
        
        # 1. InputPipeline
        try:
            pipeline = InputPipeline(pdf_path)
            result = pipeline.execute()
        except Exception as e:
            return CoverageReport(
                pdf_path=pdf_path,
                drawing_score=0.0,
                coverage_percentage=0.0,
                grade=CoverageGrade.FAIL,
                violations=[],
                room_area_m2=0.0,
                room_name="ERROR",
                device_count=0,
                smoke_detectors=0,
                heat_detectors=0,
                ceiling_height_m=3.0,
                requires_pe_review=True,
                errors=[str(e)]
            )
        
        # 2. Check gate decision
        if result.status == PipelineStatus.REJECTED:
            errors.append("REJECTED by confidence gate")
            return CoverageReport(
                pdf_path=pdf_path,
                drawing_score=result.drawing_score,
                coverage_percentage=0.0,
                grade=CoverageGrade.FAIL,
                violations=[],
                room_area_m2=0.0,
                room_name="REJECTED",
                device_count=0,
                smoke_detectors=0,
                heat_detectors=0,
                ceiling_height_m=result.ceiling_height_m,
                requires_pe_review=True,
                errors=errors
            )
        
        # 3. Build Room
        room = self._build_room(result)
        if not room:
            errors.append("NO_ROOM: Could not build room from walls")
        
        # 4. Build Devices
        devices = self._build_devices(result)
        
        # 5. Coverage check
        violations = []
        coverage_pct = 0.0
        
        if room and devices:
            try:
                coverage = self.CoverageService()
                violations = coverage.check_coverage(room, devices, self.standard)
                coverage_pct = self._calculate_coverage(room, devices, violations)
            except Exception as e:
                errors.append(f"COVERAGE_ERROR: {e}")
        
        # 6. Determine grade
        grade = self._determine_grade(coverage_pct, violations)
        
        # 7. Count devices
        smoke = sum(1 for d in devices if d.device_type == "SmokeDetector")
        heat = sum(1 for d in devices if d.device_type == "HeatDetector")
        
        return CoverageReport(
            pdf_path=pdf_path,
            drawing_score=result.drawing_score,
            coverage_percentage=coverage_pct,
            grade=grade,
            violations=violations,
            room_area_m2=getattr(room, 'area', 0) if room else 0,
            room_name=getattr(room, 'name', 'Room') if room else 'Unknown',
            device_count=len(devices),
            smoke_detectors=smoke,
            heat_detectors=heat,
            ceiling_height_m=result.ceiling_height_m,
            requires_pe_review=result.requires_pe_review,
            errors=errors
        )
    
    def _build_room(self, result: PipelineResult) -> Optional[object]:
        """بناء Room من PipelineResult."""
        if not result.rooms:
            return None
        
        # Use first room
        room_spec = result.rooms[0]
        scale = self._calculate_scale(result)
        
        # Build polygon from points
        from shapely.geometry import Polygon
        shapely_points = [(x * scale, y * scale) for x, y in room_spec.points]
        if len(shapely_points) < 3:
            return None
        
        polygon = Polygon(shapely_points)
        
        room = self.Room(
            name=f"Room_{id(result)}",
            room_type=RoomType.OTHER,
            polygon=polygon,
            height=result.ceiling_height_m,
            area=room_spec.area_m2
        )
        return room
    
    def _build_devices(self, result: PipelineResult) -> List[object]:
        """بناء Devices من PipelineResult."""
        devices = []
        scale = self._calculate_scale(result)
        
        for det in result.detectors:
            x, y = det.position
            device = self.Device(
                device_type=det.detector_type.capitalize() + "Detector" if det.detector_type else "SmokeDetector",
                x=x * scale,
                y=y * scale,
                z=result.ceiling_height_m - 0.3
            )
            devices.append(device)
        
        return devices
    
    def _calculate_scale(self, result: PipelineResult) -> float:
        """حساب مقياس التحويل من pixel إلى متر."""
        if not result.dimensions:
            return 0.01  # default: 1 pixel = 1 cm
        
        # Use first dimension
        dim = result.dimensions[0]
        if hasattr(dim, 'value_m') and hasattr(dim, 'bbox'):
            # Calculate: dimension length in pixels vs real meters
            bbox = dim.bbox
            pixel_width = bbox[2] - bbox[0]
            if pixel_width > 0:
                return dim.value_m / pixel_width
        
        return 0.01
    
    def _calculate_coverage(self, room: object, devices: List, violations: List) -> float:
        """حساب نسبة التغطية."""
        if not room or not devices:
            return 0.0
        
        room_area = getattr(room, 'area', 0)
        if room_area <= 0:
            return 0.0
        
        # NFPA spacing ~9m for smoke detectors
        device_coverage = 63.0  # ~9m radius circle
        covered = len(devices) * device_coverage
        
        return min(100.0, (covered / room_area) * 100)
    
    def _determine_grade(self, coverage: float, violations: List) -> CoverageGrade:
        """تحديد الدرجة."""
        if coverage >= 100 and not violations:
            return CoverageGrade.FULL
        elif coverage >= 70:
            return CoverageGrade.PASS
        elif coverage >= 30:
            return CoverageGrade.PARTIAL
        else:
            return CoverageGrade.FAIL


def process_coverage(pdf_path: str) -> CoverageReport:
    """دالة سريعة لمعالجة PDF وإنتاج تقرير."""
    pipeline = CoveragePipeline()
    return pipeline.process(pdf_path)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        report = process_coverage(sys.argv[1])
        print(report.to_dict())
    else:
        print("Usage: python coverage_pipeline.py <pdf_path>")