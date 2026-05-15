"""
COVERAGE PIPELINE — Bridge from Input Layer to NFPA 72 Engine
===============================================================
يحول مخرجات InputPipeline (غرف، كواشف، أبعاد) إلى استدعاءات
لمحرك حسابات NFPA 72، ويُصدر تقرير حماية كاملاً.

Author: The Consultant Who Refused to Lie
"""

from typing import List, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum

from src.core.input_pipeline import InputPipeline, PipelineResult, PipelineStatus


class CoverageStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    CAUTION = "CAUTION"
    REQUIRES_PE_REVIEW = "REQUIRES PE REVIEW"


@dataclass
class RoomCoverageReport:
    """تقرير تغطية غرفة واحدة."""
    room_index: int
    room_area_m2: float
    detectors_count: int
    coverage_pct: float
    spacing_ok: bool
    warnings: List[str] = field(default_factory=list)
    status: CoverageStatus = CoverageStatus.PASS


@dataclass
class CoverageReport:
    """التقرير النهائي للحماية من الحريق."""
    status: CoverageStatus
    message: str
    drawing_score: float
    total_rooms: int
    total_detectors: int
    ceiling_height_m: float
    room_reports: List[RoomCoverageReport] = field(default_factory=list)
    global_warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    requires_pe_review: bool = True


class CoveragePipeline:
    """
    يربط مخرجات InputPipeline بمحرك NFPA 72.

    المسار:
    1. يستقبل PipelineResult
    2. لكل غرفة: يبني Room و Detectors
    3. يستدعي check_coverage من CoverageService
    4. يجمع النتائج في تقرير نهائي
    """

    def __init__(self, pipeline_result: PipelineResult):
        self.result = pipeline_result
        self._load_engine()
        self.report = CoverageReport(
            status=CoverageStatus.PASS,
            message="",
            drawing_score=pipeline_result.drawing_score,
            total_rooms=len(pipeline_result.rooms),
            total_detectors=len(pipeline_result.detectors),
            ceiling_height_m=pipeline_result.ceiling_height_m,
            requires_pe_review=pipeline_result.requires_pe_review,
        )

    def _load_engine(self):
        """تحميل محرك التغطية."""
        try:
            from src.application.coverage_service import CoverageService
            from src.core.models import Room, Device, RoomType
            self.CoverageService = CoverageService
            self.Room = Room
            self.Device = Device
            self.RoomType = RoomType
        except ImportError as e:
            raise ImportError(f"Cannot load NFPA 72 engine: {e}")

    def execute(self, beam_depth_pct: float = 0.0) -> CoverageReport:
        """تنفيذ حسابات التغطية لكل الغرف."""

        if self.result.status == PipelineStatus.REJECTED:
            self.report.status = CoverageStatus.FAIL
            self.report.message = (
                f"Drawing rejected at input gate (score {self.result.drawing_score}). "
                f"Cannot proceed with coverage calculations."
            )
            self.report.errors = self.result.errors
            return self.report

        if not self.result.rooms:
            self.report.status = CoverageStatus.FAIL
            self.report.message = "No rooms extracted from drawing."
            self.report.errors.append("NO_ROOMS")
            return self.report

        if not self.result.detectors:
            self.report.status = CoverageStatus.FAIL
            self.report.message = "No detectors extracted from drawing."
            self.report.errors.append("NO_DETECTORS")
            return self.report

        # تنفيذ التغطية لكل غرفة
        all_detector_positions = [d.position for d in self.result.detectors]

        for i, room in enumerate(self.result.rooms):
            room_report = self._calculate_room_coverage(
                room_index=i,
                room=room,
                detector_positions=all_detector_positions,
                beam_depth_pct=beam_depth_pct,
            )
            self.report.room_reports.append(room_report)

        # تجميع التحذيرات العامة
        self._aggregate_warnings()

        # تحديد الحالة النهائية
        self._determine_final_status()

        return self.report

    def _calculate_room_coverage(
        self,
        room_index: int,
        room,
        detector_positions: List[Tuple[float, float]],
        beam_depth_pct: float,
    ) -> RoomCoverageReport:
        """حساب تغطية غرفة واحدة."""

        # تحويل RoomSpec إلى Room
        scale = self._calculate_scale()
        polygon = self._build_polygon(room.points, scale)

        if not polygon:
            return RoomCoverageReport(
                room_index=room_index,
                room_area_m2=room.area_m2,
                detectors_count=len(detector_positions),
                coverage_pct=0.0,
                spacing_ok=False,
                warnings=["Cannot build polygon"],
                status=CoverageStatus.FAIL,
            )

        nfpa_room = self.Room(
            name=f"Room_{room_index}",
            room_type=self.RoomType.OTHER,
            polygon=polygon,
            height=self.result.ceiling_height_m,
            area=room.area_m2,
        )

        # تحويل الكواشف
        devices = []
        for x, y in detector_positions:
            devices.append(self.Device(
                device_type="SmokeDetector",
                x=x * scale,
                y=y * scale,
                z=self.result.ceiling_height_m - 0.3,
            ))

        # استدعاء محرك NFPA 72
        try:
            violations = self.CoverageService().check_coverage(nfpa_room, devices)
        except Exception as e:
            return RoomCoverageReport(
                room_index=room_index,
                room_area_m2=room.area_m2,
                detectors_count=len(detector_positions),
                coverage_pct=0.0,
                spacing_ok=False,
                warnings=[f"Engine error: {e}"],
                status=CoverageStatus.FAIL,
            )

        # تحليل النتيجة
        coverage_pct = max(0.0, 100.0 - len(violations) * 15.0)
        
        if coverage_pct < 70.0:
            status = CoverageStatus.FAIL
        elif coverage_pct < 100.0 or violations:
            status = CoverageStatus.CAUTION
        else:
            status = CoverageStatus.PASS

        warnings = [v.violation_code or v.standard_name for v in violations]
        
        # تحذير ارتفاع السقف غير قياسي
        if self.result.ceiling_height_m < 3.0 or self.result.ceiling_height_m > 9.0:
            warnings.append(
                f"Ceiling height {self.result.ceiling_height_m}m is non-standard. "
                f"REQUIRES PE REVIEW."
            )

        return RoomCoverageReport(
            room_index=room_index,
            room_area_m2=room.area_m2,
            detectors_count=len(detector_positions),
            coverage_pct=coverage_pct,
            spacing_ok=len(violations) == 0,
            warnings=warnings,
            status=status,
        )

    def _calculate_scale(self) -> float:
        """حساب مقياس التحويل."""
        if not self.result.dimensions:
            return 0.01

        dim = self.result.dimensions[0]
        if hasattr(dim, 'value_m') and hasattr(dim, 'bbox'):
            bbox = dim.bbox
            pixel_width = bbox[2] - bbox[0]
            if pixel_width > 0:
                return dim.value_m / pixel_width

        return 0.01

    def _build_polygon(self, points: List, scale: float):
        """بناء polygon من النقاط."""
        try:
            from shapely.geometry import Polygon
            shapely_points = [(x * scale, y * scale) for x, y in points]
            if len(shapely_points) < 3:
                return None
            return Polygon(shapely_points)
        except:
            return None

    def _aggregate_warnings(self):
        """تجميع التحذيرات من كل الغرف."""
        for rr in self.report.room_reports:
            if rr.warnings:
                self.report.global_warnings.extend(rr.warnings)
            if rr.status == CoverageStatus.FAIL:
                self.report.global_warnings.append(
                    f"Room {rr.room_index}: coverage {rr.coverage_pct}% — FAIL"
                )
            elif rr.status == CoverageStatus.CAUTION:
                self.report.global_warnings.append(
                    f"Room {rr.room_index}: requires review"
                )

    def _determine_final_status(self):
        """تحديد الحالة النهائية."""
        statuses = [rr.status for rr in self.report.room_reports]

        fail_count = sum(1 for s in statuses if s == CoverageStatus.FAIL)
        caution_count = sum(1 for s in statuses if s == CoverageStatus.CAUTION)

        if fail_count > 0:
            self.report.status = CoverageStatus.FAIL
            self.report.message = (
                f"FAIL: {fail_count} rooms have insufficient coverage. "
                f"PE REVIEW REQUIRED."
            )
        elif caution_count > 0:
            self.report.status = CoverageStatus.REQUIRES_PE_REVIEW
            self.report.message = (
                f"CAUTION: {caution_count} rooms have warnings. "
                f"PE REVIEW REQUIRED."
            )
        else:
            self.report.status = CoverageStatus.PASS
            self.report.message = (
                f"All {len(self.report.room_reports)} rooms pass coverage checks. "
                f"PE REVIEW REQUIRED before final approval."
            )

        self.report.requires_pe_review = True


def run_coverage_analysis(pdf_path: str, beam_depth_pct: float = 0.0) -> CoverageReport:
    """
    المسار الكامل: PDF → تقرير حماية حريق.

    Args:
        pdf_path: مسار ملف PDF
        beam_depth_pct: عمق العوارض بالنسبة لارتفاع السقف (%)

    Returns:
        CoverageReport: تقرير كامل مع حالة كل غرفة وتحذيرات
    """
    pipeline = InputPipeline(pdf_path)
    result = pipeline.execute()

    coverage = CoveragePipeline(result)
    return coverage.execute(beam_depth_pct=beam_depth_pct)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        report = run_coverage_analysis(sys.argv[1])
        print(f"Status: {report.status.value}")
        print(f"Rooms: {report.total_rooms}")
        print(f"Detectors: {report.total_detectors}")
        print(f"Message: {report.message}")
    else:
        print("Usage: python coverage_pipeline.py <pdf_path>")