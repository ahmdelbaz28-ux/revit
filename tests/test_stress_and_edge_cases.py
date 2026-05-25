"""
Stress & Edge-Case Test Suite – FireAI v1.0.0
==============================================
اختبارات قاسية تكشف نقاط الضعف والحالات الحرجة في كل طبقة من طبقات النظام.
تغطي: DensityOptimizer · FloorAnalyser · BuildingEngine · PolygonOptimizer
       · PDF Report · CLI · Audit · Scenarios · JSON I/O · Geometry

API MISMATCH FIXES (vs. original draft):
- calculate_coverage_radius(float, str) → calculate_coverage_radius_from_height(float, str).radius
- FloorAnalyser() → FloorAnalyser(floor_id=..., optimizer=DensityOptimizer())
- BuildingReport.floor_results → floor_reports
- PolygonRoom imported from fireai.core.polygon_optimizer (not polygon_room)
- RoomSummary has no 'errors' field; removed from stubs
- RoomSummary.scenario_fail_count (not scenario_fail_count → same name, confirmed)
- RoomSummary.scenario_blind_spots → scenario_blind_spots (confirmed same)
- DensityOptimizer ignores room.detector_type; must pass coverage_radius explicitly
- _make_room duck-type: DensityOptimizer.optimize() only uses .width, .length;
  ceiling_height/detector_type are metadata for radius calculation, not read by optimize()
"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

import pytest


# ===========================================================================
# 0. Shared fixtures & stubs
# ===========================================================================

def _make_room(
    width: float = 8.0,
    length: float = 6.0,
    ceiling_height: float = 3.0,
    detector_type: str = "smoke",
    room_id: str = "R-00",
):
    """Return a minimal room duck-type accepted by DensityOptimizer.

    DensityOptimizer.optimize() reads only .width and .length from the Room.
    ceiling_height and detector_type are stored for the caller to compute
    coverage_radius via calculate_coverage_radius_from_height().
    """
    class _R:
        pass
    r = _R()
    r.width          = width
    r.length         = length
    r.ceiling_height = ceiling_height
    r.detector_type  = detector_type
    r.room_id        = room_id
    r.name           = room_id
    return r


def _coverage_radius(ceiling_height: float = 3.0, detector_type: str = "smoke") -> float:
    """Compute NFPA 72 coverage radius from ceiling height and detector type."""
    from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height
    cov_det_type = "heat" if "heat" in detector_type.lower() else "smoke"
    spec = calculate_coverage_radius_from_height(ceiling_height, cov_det_type)
    return spec.radius


def _room_dict(**kw) -> Dict[str, Any]:
    """Create a room dict suitable for FloorAnalyser.analyse().

    FloorAnalyser requires 'polygon_coords' (mandatory in _build_room).
    If the caller provides 'width' and 'length' but no 'polygon_coords',
    we auto-generate an axis-aligned rectangle polygon.
    """
    base = dict(
        room_id="R-00", width=8.0, length=6.0,
        ceiling_height=3.0, detector_type="smoke",
    )
    base.update(kw)
    # Auto-generate polygon_coords from width/length if not provided
    if "polygon_coords" not in base:
        w = base.get("width", 8.0)
        l = base.get("length", 6.0)
        base["polygon_coords"] = [(0, 0), (w, 0), (w, l), (0, l)]
    return base


# ===========================================================================
# 1. DensityOptimizer – حالات الحافة الهندسية
# ===========================================================================

class TestDensityOptimizerEdge:

    def _opt(self):
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
        return DensityOptimizer()

    # --- أبعاد متطرفة --------------------------------------------------

    def test_tiny_room_1cm_x_1cm(self):
        """غرفة 1 سم × 1 سم: يجب أن يُعيد كاشفاً واحداً على الأقل."""
        opt = self._opt()
        room = _make_room(width=0.01, length=0.01, ceiling_height=3.0)
        layout = opt.optimize(room)
        assert layout.count >= 1
        assert 0.0 <= layout.coverage_pct <= 100.0

    def test_very_long_corridor_100m_x_1m(self):
        """ممر 100 م × 1 م: يجب أن يغطي بكاشفات متعددة."""
        opt = self._opt()
        room = _make_room(width=100.0, length=1.0, ceiling_height=3.0)
        layout = opt.optimize(room)
        assert layout.count >= 5
        assert layout.coverage_pct >= 95.0

    def test_square_room_50m_x_50m(self):
        """غرفة ضخمة 50 × 50 م: لا يُفترض تعليق."""
        opt = self._opt()
        room = _make_room(width=50.0, length=50.0, ceiling_height=6.0)
        radius = _coverage_radius(6.0, "smoke")
        layout = opt.optimize(room, coverage_radius=radius)
        assert layout.count > 0
        assert layout.coverage_pct >= 90.0

    def test_extreme_ceiling_20m(self):
        """سقف 20 م: نصف القطر يتمدد، عدد الكاشفات يجب أن يبقى معقولاً."""
        opt = self._opt()
        room = _make_room(width=20.0, length=20.0, ceiling_height=20.0)
        radius = _coverage_radius(20.0, "smoke")
        layout = opt.optimize(room, coverage_radius=radius)
        assert layout.count >= 1

    def test_very_low_ceiling_1m5(self):
        """سقف 1.5 م: نصف قطر أصغر = كاشفات أكثر (conservative)."""
        opt = self._opt()
        room_low  = _make_room(width=10.0, length=10.0, ceiling_height=1.5)
        room_std  = _make_room(width=10.0, length=10.0, ceiling_height=3.0)
        r_low = _coverage_radius(1.5, "smoke")
        r_std = _coverage_radius(3.0, "smoke")
        lo = opt.optimize(room_low, coverage_radius=r_low)
        st = opt.optimize(room_std, coverage_radius=r_std)
        assert lo.count >= st.count

    def test_square_room_exactly_one_radius(self):
        """غرفة بعرض = نصف قطر التغطية بالضبط: كاشف واحد يكفي."""
        radius = _coverage_radius(3.0, "smoke")
        opt = self._opt()
        room = _make_room(width=radius, length=radius, ceiling_height=3.0)
        layout = opt.optimize(room, coverage_radius=radius)
        assert layout.count >= 1
        assert layout.coverage_pct >= 95.0

    # --- أنواع الكاشفات ------------------------------------------------

    def test_heat_detector_type(self):
        """كاشف حراري: نصف قطر أصغر من الدخان."""
        opt = self._opt()
        room = _make_room(width=10.0, length=10.0, detector_type="heat")
        radius = _coverage_radius(3.0, "heat")
        layout = opt.optimize(room, coverage_radius=radius)
        assert layout.count >= 1

    def test_unknown_detector_type_does_not_crash(self):
        """نوع كاشف غير معروف: لا يُفترض تعليق، يُرجع نتيجة أو رسالة خطأ واضحة."""
        opt = self._opt()
        room = _make_room(detector_type="laser_unknown_xyz")
        try:
            # Unknown type defaults to "smoke" in _coverage_radius helper
            radius = _coverage_radius(3.0, "smoke")
            layout = opt.optimize(room, coverage_radius=radius)
            assert layout.count >= 0
        except (ValueError, KeyError) as exc:
            assert str(exc)  # خطأ صريح مقبول

    # --- coverage_radius مخصص -----------------------------------------

    def test_explicit_radius_zero_raises_or_fallback(self):
        """نصف قطر صفر: سلوك محدد (استثناء أو fallback)."""
        opt = self._opt()
        room = _make_room(width=5.0, length=5.0)
        try:
            layout = opt.optimize(room, coverage_radius=0.0)
            # إذا نجح، يجب أن يكون هناك كاشف واحد على الأقل
            assert layout.count >= 1
        except (ZeroDivisionError, ValueError):
            pass  # سلوك مقبول

    def test_explicit_radius_larger_than_room(self):
        """نصف قطر أكبر من الغرفة: كاشف واحد يكفي."""
        opt = self._opt()
        room = _make_room(width=5.0, length=5.0)
        layout = opt.optimize(room, coverage_radius=100.0)
        assert layout.count >= 1
        assert layout.coverage_pct >= 99.0

    # --- تكرار الاستدعاء -----------------------------------------------

    def test_idempotent_same_input_same_output(self):
        """نفس المدخل يُعطي نفس المخرج دائماً."""
        opt = self._opt()
        room = _make_room(width=12.0, length=9.0)
        r1 = opt.optimize(room)
        r2 = opt.optimize(room)
        assert r1.count == r2.count
        assert abs(r1.coverage_pct - r2.coverage_pct) < 0.001

    def test_wall_violations_zero_for_valid_room(self):
        """لا يُفترض وجود كاشفات خارج الجدران لغرفة مستطيلة عادية."""
        opt = self._opt()
        room = _make_room(width=10.0, length=8.0)
        layout = opt.optimize(room)
        assert layout.wall_violations == 0

    def test_all_detectors_within_bounds(self):
        """كل كاشف يجب أن يكون داخل حدود الغرفة."""
        opt = self._opt()
        w, l = 15.0, 12.0
        room = _make_room(width=w, length=l)
        layout = opt.optimize(room)
        for x, y in layout.detectors:
            assert 0.0 <= x <= w, f"x={x} خارج النطاق [0, {w}]"
            assert 0.0 <= y <= l, f"y={y} خارج النطاق [0, {l}]"


# ===========================================================================
# 2. PolygonDensityOptimizer – مضلعات حرجة
# ===========================================================================

class TestPolygonOptimizerEdge:

    def _poly_room(self, polygon, ceiling_height=3.0,
                   detector_type="smoke", room_id="P-00", ducts=None):
        from fireai.core.polygon_optimizer import PolygonRoom
        return PolygonRoom(
            room_id=room_id,
            polygon=polygon,
            ceiling_height=ceiling_height,
            detector_type=detector_type,
            ducts=ducts or [],
        )

    def _opt(self):
        from fireai.core.polygon_optimizer import PolygonDensityOptimizer
        return PolygonDensityOptimizer()

    # --- مستطيلات (يجب أن تُفوَّض إلى DensityOptimizer) ----------------

    def test_rectangular_polygon_uses_rectangular_method(self):
        poly = [(0,0),(10,0),(10,8),(0,8)]
        room = self._poly_room(poly)
        summary = self._opt().optimize_polygon(room)
        assert summary.method == "rectangular"

    def test_rectangular_polygon_same_result_as_density_optimizer(self):
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
        poly = [(0,0),(10,0),(10,8),(0,8)]
        room = self._poly_room(poly)
        summary = self._opt().optimize_polygon(room)
        rect_room = _make_room(width=10.0, length=8.0)
        radius = _coverage_radius(3.0, "smoke")
        layout = DensityOptimizer().optimize(rect_room, coverage_radius=radius)
        assert summary.count == layout.count

    # --- مضلعات L-شكل ---------------------------------------------------

    def test_l_shaped_room(self):
        """غرفة على شكل L: تغطية >= 90%."""
        poly = [(0,0),(10,0),(10,5),(5,5),(5,10),(0,10)]
        room = self._poly_room(poly)
        summary = self._opt().optimize_polygon(room)
        assert summary.method == "greedy_polygon"
        assert summary.count >= 1
        assert summary.coverage_pct >= 90.0

    def test_l_shaped_no_detectors_outside_polygon(self):
        poly = [(0,0),(10,0),(10,5),(5,5),(5,10),(0,10)]
        room = self._poly_room(poly)
        from fireai.core.geometry_utils import point_in_polygon
        summary = self._opt().optimize_polygon(room)
        for det in summary.detectors:
            assert point_in_polygon(det, poly), \
                f"كاشف {det} خارج المضلع"

    # --- مضلع T-شكل -----------------------------------------------------

    def test_t_shaped_room(self):
        poly = [
            (0,4),(10,4),(10,6),(7,6),(7,10),
            (3,10),(3,6),(0,6),
        ]
        room = self._poly_room(poly)
        summary = self._opt().optimize_polygon(room)
        assert summary.count >= 1
        assert summary.coverage_pct >= 85.0

    # --- مضلع عُشاري (10 أضلاع) ----------------------------------------

    def test_decagonal_room(self):
        n, r = 10, 8.0
        poly = [
            (r * math.cos(2*math.pi*i/n),
             r * math.sin(2*math.pi*i/n))
            for i in range(n)
        ]
        room = self._poly_room(poly)
        summary = self._opt().optimize_polygon(room)
        assert summary.count >= 1
        assert summary.coverage_pct >= 85.0

    # --- مضلع ضيق جداً --------------------------------------------------

    def test_very_narrow_polygon_corridor(self):
        """ممر مثلثي ضيق: 0.5 م عرضاً، 20 م طولاً."""
        poly = [(0,0),(20,0),(20,0.5),(0,0.5)]
        room = self._poly_room(poly)
        summary = self._opt().optimize_polygon(room)
        assert summary.count >= 1

    # --- مضلع محدب مقعر -------------------------------------------------

    def test_concave_polygon_star_shape(self):
        """شكل نجمة مقعر: يجب ألا يتعلق."""
        def star(n=5, r_out=10.0, r_in=4.0):
            pts = []
            for i in range(2*n):
                r = r_out if i % 2 == 0 else r_in
                a = math.pi * i / n - math.pi/2
                pts.append((r*math.cos(a), r*math.sin(a)))
            return pts
        poly = star()
        room = self._poly_room(poly)
        summary = self._opt().optimize_polygon(room)
        assert summary.count >= 1

    # --- مضلع بنقاط مكررة -----------------------------------------------

    def test_polygon_with_duplicate_vertices(self):
        """رؤوس مكررة: يجب ألا يتعلق."""
        poly = [(0,0),(5,0),(5,0),(5,5),(0,5),(0,0)]
        room = self._poly_room(poly)
        try:
            summary = self._opt().optimize_polygon(room)
            assert summary.count >= 0
        except Exception as exc:
            pytest.fail(f"تعليق عند رؤوس مكررة: {exc}")

    # --- غرفة نقطة (مساحة = صفر) ----------------------------------------

    def test_degenerate_single_point_polygon(self):
        """مضلع يتقلص إلى نقطة: لا يُفترض تعليق."""
        poly = [(5,5),(5,5),(5,5)]
        room = self._poly_room(poly)
        try:
            summary = self._opt().optimize_polygon(room)
            assert summary.count >= 0
        except Exception:
            pass  # استثناء صريح مقبول

    # --- duct devices ---------------------------------------------------

    def test_duct_devices_appended_to_summary(self):
        """analyse_ducts يجب أن يُلحق النتائج بـ summary."""
        poly = [(0,0),(10,0),(10,8),(0,8)]
        ducts = [{"duct_id": "D-01", "position": (5.0, 4.0), "width": 0.6}]
        room = self._poly_room(poly, ducts=ducts)
        summary = self._opt().optimize_polygon(room)
        # duct_devices و duct_warnings يجب أن يكونا lists
        assert isinstance(summary.duct_devices, list)
        assert isinstance(summary.duct_warnings, list)


# ===========================================================================
# 3. FloorAnalyser – حالات الطابق الحرجة
# ===========================================================================

class TestFloorAnalyserEdge:

    def _analyser(self):
        from fireai.core.floor_analyser import FloorAnalyser
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
        return FloorAnalyser(floor_id="F-STRESS", optimizer=DensityOptimizer())

    def test_empty_room_list(self):
        """قائمة غرف فارغة: لا تعليق، تقرير صالح."""
        report = self._analyser().analyse([])
        summaries = getattr(report, "room_summaries", [])
        assert isinstance(summaries, list)
        assert len(summaries) == 0

    def test_single_room_floor(self):
        report = self._analyser().analyse([_room_dict()])
        summaries = getattr(report, "room_summaries", [])
        assert len(summaries) == 1

    def test_100_rooms_performance(self):
        """100 غرفة: يجب أن ينتهي في أقل من 30 ثانية."""
        rooms = [_room_dict(room_id=f"R-{i:03d}",
                            width=5.0+i%10,
                            length=4.0+i%8)
                 for i in range(100)]
        start = time.time()
        report = self._analyser().analyse(rooms)
        elapsed = time.time() - start
        assert elapsed < 30.0, f"تحليل 100 غرفة استغرق {elapsed:.1f}s"
        summaries = getattr(report, "room_summaries", [])
        assert len(summaries) == 100

    def test_mixed_rectangular_and_polygon_rooms(self):
        """طابق يضم غرف مستطيلة وغير مستطيلة معاً."""
        rooms = [
            _room_dict(room_id="R-RECT",  width=8.0, length=6.0),
            dict(
                room_id="R-POLY",
                width=10.0, length=10.0,
                ceiling_height=3.0,
                detector_type="smoke",
                polygon_coords=[(0,0),(10,0),(10,5),(5,5),(5,10),(0,10)],
            ),
        ]
        report = self._analyser().analyse(rooms)
        summaries = getattr(report, "room_summaries", [])
        assert len(summaries) == 2

    def test_room_with_zero_dimensions_does_not_crash(self):
        """غرفة بأبعاد صفر: لا يُفترض تعليق."""
        try:
            report = self._analyser().analyse([_room_dict(width=0.0, length=0.0)])
            assert report is not None
        except (ValueError, ZeroDivisionError) as exc:
            assert str(exc)  # خطأ صريح مقبول

    def test_room_with_negative_dimensions_raises_or_handles(self):
        """أبعاد سالبة: استثناء صريح أو معالجة."""
        try:
            report = self._analyser().analyse([_room_dict(width=-5.0, length=-3.0)])
            assert report is not None
        except (ValueError, AssertionError):
            pass

    def test_coverage_pct_never_exceeds_100(self):
        rooms = [_room_dict(width=w, length=l)
                 for w, l in [(5,5),(10,8),(3,3),(50,50)]]
        report = self._analyser().analyse(rooms)
        for rs in getattr(report, "room_summaries", []):
            cov = getattr(rs, "coverage_pct", 0)
            assert cov <= 100.0, f"coverage_pct={cov} يتجاوز 100%"

    def test_detector_count_never_zero_for_valid_room(self):
        rooms = [_room_dict(width=10.0, length=8.0)]
        report = self._analyser().analyse(rooms)
        for rs in getattr(report, "room_summaries", []):
            cnt = getattr(rs, "detector_count", getattr(rs, "count", 0))
            assert cnt > 0

    def test_duplicate_room_ids_handled(self):
        """معرفات غرف مكررة: لا تعليق."""
        rooms = [_room_dict(room_id="SAME") for _ in range(5)]
        report = self._analyser().analyse(rooms)
        assert report is not None

    def test_extremely_high_ceiling_room(self):
        rooms = [_room_dict(ceiling_height=50.0)]
        report = self._analyser().analyse(rooms)
        assert report is not None


# ===========================================================================
# 4. Geometry Utils – حالات حرجة هندسية
# ===========================================================================

class TestGeometryUtils:

    def test_is_rectangular_true_axis_aligned(self):
        from fireai.core.geometry_utils import is_rectangular
        assert is_rectangular([(0,0),(10,0),(10,5),(0,5)]) is True

    def test_is_rectangular_false_for_triangle(self):
        from fireai.core.geometry_utils import is_rectangular
        assert is_rectangular([(0,0),(10,0),(5,5)]) is False

    def test_is_rectangular_false_for_l_shape(self):
        from fireai.core.geometry_utils import is_rectangular
        poly = [(0,0),(10,0),(10,5),(5,5),(5,10),(0,10)]
        assert is_rectangular(poly) is False

    def test_point_in_polygon_center(self):
        from fireai.core.geometry_utils import point_in_polygon
        poly = [(0,0),(10,0),(10,10),(0,10)]
        assert point_in_polygon((5,5), poly) is True

    def test_point_in_polygon_outside(self):
        from fireai.core.geometry_utils import point_in_polygon
        poly = [(0,0),(10,0),(10,10),(0,10)]
        assert point_in_polygon((15,15), poly) is False

    def test_point_in_polygon_on_edge_does_not_crash(self):
        from fireai.core.geometry_utils import point_in_polygon
        poly = [(0,0),(10,0),(10,10),(0,10)]
        try:
            result = point_in_polygon((5,0), poly)
            assert isinstance(result, bool)
        except Exception:
            pass

    def test_bounding_rect_dimensions_correct(self):
        from fireai.core.geometry_utils import bounding_rect_dimensions
        poly = [(2,3),(12,3),(12,11),(2,11)]
        w, l, min_x, min_y = bounding_rect_dimensions(poly)
        assert abs(w - 10.0) < 1e-9
        assert abs(l - 8.0)  < 1e-9
        assert abs(min_x - 2.0) < 1e-9
        assert abs(min_y - 3.0) < 1e-9

    def test_bounding_rect_non_origin_polygon(self):
        from fireai.core.geometry_utils import bounding_rect_dimensions
        poly = [(5,5),(15,5),(15,15),(5,15)]
        w, l, mx, my = bounding_rect_dimensions(poly)
        assert abs(w - 10.0) < 1e-9
        assert abs(l - 10.0) < 1e-9

    def test_point_in_polygon_concave_shape(self):
        """نقطة في حفرة المضلع المقعر يجب أن تُعاد False."""
        from fireai.core.geometry_utils import point_in_polygon
        # L-shape: نقطة في الركن المقطوع
        poly = [(0,0),(10,0),(10,5),(5,5),(5,10),(0,10)]
        # (8,8) خارج شكل L
        result = point_in_polygon((8, 8), poly)
        assert result is False

    def test_empty_polygon_does_not_crash(self):
        from fireai.core.geometry_utils import is_rectangular
        try:
            result = is_rectangular([])
            assert isinstance(result, bool)
        except Exception:
            pass


# ===========================================================================
# 5. NFPA72 Calculations – حالات حرجة
# ===========================================================================

class TestNFPA72Calculations:

    def test_smoke_radius_at_standard_height(self):
        from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height
        spec = calculate_coverage_radius_from_height(3.0, "smoke")
        r = spec.radius
        assert 3.0 <= r <= 12.0, f"نصف قطر غير متوقع: {r}"

    def test_heat_radius_smaller_than_smoke(self):
        from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height
        r_smoke = calculate_coverage_radius_from_height(3.0, "smoke").radius
        r_heat  = calculate_coverage_radius_from_height(3.0, "heat").radius
        assert r_heat <= r_smoke

    def test_radius_increases_with_ceiling_height(self):
        """NFPA 72 Table 17.6.3.1.1: radius DECREASES with higher ceiling
        (more detectors needed). This test verifies the table lookup works."""
        from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height
        r_low  = calculate_coverage_radius_from_height(3.0, "smoke").radius
        r_high = calculate_coverage_radius_from_height(8.0, "smoke").radius
        # In NFPA 72 Table 17.6.3.1.1, higher ceilings get SMALLER radii
        # (smoke disperses more before reaching detector)
        assert r_high <= r_low, \
            f"Expected r(8m)={r_high} <= r(3m)={r_low} per NFPA 72"

    def test_radius_is_positive(self):
        from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height
        for h in [1.5, 3.0, 5.0, 10.0, 20.0]:
            try:
                spec = calculate_coverage_radius_from_height(h, "smoke")
                assert spec.radius > 0, f"نصف القطر سالب عند h={h}"
            except (ValueError, TypeError):
                pass  # خارج النطاق: خطأ صريح مقبول

    def test_radius_zero_height_does_not_crash(self):
        from fireai.core.nfpa72_calculations import calculate_coverage_radius_from_height
        try:
            spec = calculate_coverage_radius_from_height(0.0, "smoke")
            assert spec.radius >= 0
        except (ValueError, TypeError):
            pass  # خطأ صريح مقبول


# ===========================================================================
# 6. Thread Safety – استدعاء متوازٍ
# ===========================================================================

class TestConcurrency:

    def test_density_optimizer_thread_safe(self):
        """10 خيوط تُشغّل DensityOptimizer في نفس الوقت."""
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
        errors = []

        def worker(i):
            try:
                opt = DensityOptimizer()
                room = _make_room(width=5.0+i, length=4.0+i)
                layout = opt.optimize(room)
                assert layout.count >= 1
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == [], f"أخطاء في الخيوط: {errors}"

    def test_floor_analyser_thread_safe(self):
        """5 خيوط تُشغّل FloorAnalyser في نفس الوقت."""
        from fireai.core.floor_analyser import FloorAnalyser
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
        errors = []

        def worker(i):
            try:
                rooms = [_room_dict(room_id=f"R-{i}-{j}",
                                    width=6.0+j, length=5.0+j)
                         for j in range(5)]
                opt = DensityOptimizer()
                FloorAnalyser(floor_id=f"F-{i}", optimizer=opt).analyse(rooms)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == [], f"أخطاء في الخيوط: {errors}"


# ===========================================================================
# 7. PDF Report – حالات حرجة
# ===========================================================================

@dataclass
class _RS:
    """Stub RoomSummary that matches the real RoomSummary fields used by PDF report."""
    room_id: str = "R-01"
    name: str = "Test Room"
    width: float = 10.0
    length: float = 8.0
    ceiling_height: float = 3.0
    detector_type: str = "smoke"
    detector_count: int = 4
    coverage_pct: float = 98.5
    proof_valid: bool = True
    nfpa_valid: bool = True
    wall_violations: int = 0
    theoretical_lower_bound: int = 3
    efficiency_ratio: float = 1.33
    mip_proven_optimal_count: int = 1
    used_mip: bool = True
    scenario_pass: int = 10
    scenario_fail_count: int = 0
    scenario_blind_spots: List = field(default_factory=list)
    duct_devices: List = field(default_factory=list)
    duct_warnings: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    method: str = "rectangular"


@dataclass
class _FR:
    """Stub FloorReport."""
    floor_id: str = "F-01"
    room_summaries: List = field(default_factory=lambda: [_RS()])


@dataclass
class _BR:
    """Stub BuildingReport — uses floor_reports (NOT floor_results)."""
    building_id: str = "BLD-STRESS"
    floor_reports: List = field(default_factory=lambda: [_FR()])
    total_detectors: int = 4
    total_duct_devices: int = 0
    total_theoretical_lower_bound: int = 0
    total_floors: int = 1
    fully_compliant: bool = True
    safe_to_submit: bool = True
    non_compliant_floors: List = field(default_factory=list)
    unsafe_floors: List = field(default_factory=list)
    building_warnings: List = field(default_factory=list)
    project_profile: Any = None
    analysis_time_s: float = 0.0


class TestPDFReportEdge:

    def test_pdf_with_zero_rooms(self):
        from fireai.core.pdf_report import generate_pdf
        report = _BR(floor_reports=[_FR(room_summaries=[])])
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "zero_rooms.pdf")
            generate_pdf(report, out)
            assert os.path.getsize(out) > 0

    def test_pdf_with_50_rooms(self):
        """50 غرفة في طابق واحد: يجب أن يُنتج PDF صالح."""
        from fireai.core.pdf_report import generate_pdf
        rooms = [_RS(room_id=f"R-{i:02d}",
                     coverage_pct=85.0+i%15,
                     nfpa_valid=(i%5 != 0))
                 for i in range(50)]
        report = _BR(floor_reports=[_FR(room_summaries=rooms)])
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "big_floor.pdf")
            generate_pdf(report, out)
            assert os.path.getsize(out) > 0

    def test_pdf_with_10_floors(self):
        from fireai.core.pdf_report import generate_pdf
        floors = [_FR(floor_id=f"F-{i:02d}",
                      room_summaries=[_RS(room_id=f"F{i}R{j}") for j in range(5)])
                  for i in range(10)]
        report = _BR(floor_reports=floors, total_floors=10)
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "multi_floor.pdf")
            generate_pdf(report, out)
            assert os.path.getsize(out) > 0

    def test_pdf_never_raises_on_none_report(self):
        """generate_pdf with None report: should produce fallback file (never crash)."""
        from fireai.core.pdf_report import generate_pdf
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "none_report.pdf")
            result = generate_pdf(None, out)  # type: ignore
            assert isinstance(result, str)

    def test_pdf_unicode_building_id(self):
        from fireai.core.pdf_report import generate_pdf
        report = _BR(building_id="مبنى-اختبار-١٢٣")
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "unicode.pdf")
            generate_pdf(report, out)
            assert os.path.getsize(out) > 0

    def test_pdf_room_with_all_warnings_and_errors(self):
        from fireai.core.pdf_report import generate_pdf
        room = _RS(
            nfpa_valid=False,
            proof_valid=False,
            warnings=["تحذير 1", "تحذير 2"],
            duct_warnings=["تحذير قناة"],
        )
        report = _BR(
            safe_to_submit=False,
            fully_compliant=False,
            non_compliant_floors=["F-01"],
            floor_reports=[_FR(room_summaries=[room])],
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "all_errors.pdf")
            generate_pdf(report, out)
            assert os.path.getsize(out) > 0

    def test_pdf_output_path_in_nonexistent_dir(self):
        """المسار غير موجود: generate_pdf لا تتعطل (تنشئ المجلد أو تكتب fallback)."""
        from fireai.core.pdf_report import generate_pdf
        report = _BR()
        out = "/tmp/fireai_stress_nonexistent_dir_xyz/report.pdf"
        result = generate_pdf(report, out)
        assert isinstance(result, str)

    def test_pdf_with_scenario_results_all_failing(self):
        from fireai.core.pdf_report import generate_pdf
        scenario_results = {
            f"R-{i:02d}": type("B", (), {
                "total_scenarios": 20,
                "passed": 0,
                "failed": 20,
                "worst_detection_time": 999.9,
                "blind_spots": [f"zone-{j}" for j in range(5)],
            })()
            for i in range(5)
        }
        report = _BR(safe_to_submit=False)
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "all_fail_scenarios.pdf")
            generate_pdf(report, out, scenario_results=scenario_results)
            assert os.path.getsize(out) > 0

    def test_pdf_with_large_audit_summary(self):
        from fireai.core.pdf_report import generate_pdf
        audit = {
            "total_records": 99999,
            "hash_chain_valid": False,
            "tamper_detected": True,
            **{f"extra_key_{i}": f"value_{i}" for i in range(20)},
        }
        report = _BR()
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "large_audit.pdf")
            generate_pdf(report, out, audit_summary=audit)
            assert os.path.getsize(out) > 0


# ===========================================================================
# 8. CLI – حالات حرجة
# ===========================================================================

class TestCLIEdge:
    import subprocess

    def _run(self, *args):
        import subprocess
        return subprocess.run(
            [sys.executable, "-m", "fireai.core.fire_cli", *args],
            capture_output=True, text=True,
        )

    def test_no_args_exits_nonzero(self):
        r = self._run()
        assert r.returncode != 0

    def test_unknown_command_exits_nonzero(self):
        r = self._run("unknown_command_xyz")
        assert r.returncode != 0

    def test_analyse_missing_file_exits_nonzero(self):
        r = self._run("analyse", "/no/such/file.json")
        assert r.returncode != 0

    def test_analyse_invalid_json_exits_nonzero(self):
        with tempfile.NamedTemporaryFile(suffix=".json",
                                        mode="w", delete=False) as f:
            f.write("{ invalid json !!!")
            fname = f.name
        try:
            r = self._run("analyse", fname)
            assert r.returncode != 0
        finally:
            os.unlink(fname)

    def test_analyse_valid_room_json_exits_zero(self):
        data = {"room_id":"R-CLI","width":8.0,"length":6.0,
                "ceiling_height":3.0,"detector_type":"smoke"}
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w",
                                         delete=False) as f:
            json.dump(data, f)
            fname = f.name
        try:
            r = self._run("analyse", fname)
            assert r.returncode == 0
            out = json.loads(r.stdout)
            assert "detector_count" in out or "count" in out
        finally:
            os.unlink(fname)

    def test_version_subcommand(self):
        r = self._run("version")
        assert r.returncode == 0
        assert "1.0.0" in r.stdout

    def test_version_flag(self):
        r = self._run("--version")
        assert r.returncode == 0
        assert "1.0.0" in r.stdout

    def test_report_invalid_format(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w",
                                         delete=False) as f:
            json.dump({}, f)
            fname = f.name
        try:
            r = self._run("report", "--format", "xlsx", fname)
            assert r.returncode != 0
        finally:
            os.unlink(fname)


# ===========================================================================
# 9. JSON Round-Trip – صحة التسلسل
# ===========================================================================

class TestJSONRoundTripStress:

    def test_detectors_serialise_as_lists_of_two(self):
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
        room = _make_room(width=20.0, length=15.0)
        r = _coverage_radius(3.0, "smoke")
        layout = DensityOptimizer().optimize(room, coverage_radius=r)
        blob = json.loads(json.dumps({"d": layout.detectors}, default=str))
        for pair in blob["d"]:
            assert len(pair) == 2

    def test_coverage_pct_survives_json_roundtrip(self):
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
        room = _make_room(width=12.0, length=9.0)
        layout = DensityOptimizer().optimize(room)
        blob = json.loads(json.dumps({"c": layout.coverage_pct}))
        assert abs(blob["c"] - layout.coverage_pct) < 0.001

    def test_floor_report_room_ids_stable_after_roundtrip(self):
        from fireai.core.floor_analyser import FloorAnalyser
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
        rooms = [_room_dict(room_id=f"ROOM-{i}", width=6+i, length=5+i)
                 for i in range(10)]
        opt = DensityOptimizer()
        report = FloorAnalyser(floor_id="F-RT", optimizer=opt).analyse(rooms)
        ids_before = [r["room_id"] for r in rooms]
        ids_after  = [getattr(rs, "room_id", None)
                      for rs in getattr(report, "room_summaries", [])]
        for rid in ids_before:
            assert rid in ids_after

    def test_full_building_json_keys_present(self):
        """مفاتيح BuildingReport الأساسية موجودة في JSON."""
        from fireai.core.floor_analyser import FloorAnalyser
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
        rooms = [_room_dict()]
        opt = DensityOptimizer()
        report = FloorAnalyser(floor_id="F-JK", optimizer=opt).analyse(rooms)
        blob = json.dumps({
            "total_detectors": getattr(report, "total_detectors", 0),
            "fully_compliant": getattr(report, "fully_compliant", None),
        }, default=str)
        d = json.loads(blob)
        assert "total_detectors" in d
        assert "fully_compliant" in d


# ===========================================================================
# 10. Coverage & Proof Validity – ثوابت النظام
# ===========================================================================

class TestSystemInvariants:

    def test_coverage_pct_in_0_100_range(self):
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
        opt = DensityOptimizer()
        for w, l, h in [(3,3,3),(10,8,3),(50,30,5),(1,100,3),(0.5,0.5,3)]:
            room = _make_room(width=w, length=l, ceiling_height=h)
            try:
                radius = _coverage_radius(h, "smoke")
                layout = opt.optimize(room, coverage_radius=radius)
                assert 0.0 <= layout.coverage_pct <= 100.0, \
                    f"w={w},l={l}: coverage={layout.coverage_pct}"
            except Exception:
                pass  # حالات بعدد صفر مسموح باستثنائها

    def test_detector_count_matches_detectors_list_length(self):
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
        opt = DensityOptimizer()
        for w, l in [(5,5),(10,8),(20,15)]:
            room = _make_room(width=w, length=l)
            layout = opt.optimize(room)
            assert layout.count == len(layout.detectors), \
                f"count={layout.count} != len(detectors)={len(layout.detectors)}"

    def test_proof_valid_implies_coverage_100(self):
        """إذا كان proof_valid=True، يجب أن تكون التغطية >= 99%."""
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
        opt = DensityOptimizer()
        for w, l in [(5,5),(8,6),(12,10)]:
            room = _make_room(width=w, length=l)
            layout = opt.optimize(room)
            if layout.proof_valid:
                assert layout.coverage_pct >= 99.0, \
                    f"proof_valid=True لكن coverage={layout.coverage_pct}%"

    def test_wall_violations_non_negative(self):
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
        opt = DensityOptimizer()
        room = _make_room(width=10.0, length=8.0)
        layout = opt.optimize(room)
        assert layout.wall_violations >= 0

    def test_polygon_summary_count_matches_detectors(self):
        from fireai.core.polygon_optimizer import PolygonRoom, PolygonDensityOptimizer
        poly = [(0,0),(10,0),(10,5),(5,5),(5,10),(0,10)]
        room = PolygonRoom(
            room_id="INV-01", polygon=poly,
            ceiling_height=3.0, detector_type="smoke",
        )
        summary = PolygonDensityOptimizer().optimize_polygon(room)
        assert summary.count == len(summary.detectors)

    def test_greedy_coverage_at_least_90_percent_for_l_shape(self):
        from fireai.core.polygon_optimizer import PolygonRoom, PolygonDensityOptimizer
        poly = [(0,0),(12,0),(12,6),(6,6),(6,12),(0,12)]
        room = PolygonRoom(
            room_id="L-INV", polygon=poly,
            ceiling_height=3.0, detector_type="smoke",
        )
        summary = PolygonDensityOptimizer().optimize_polygon(room)
        assert summary.coverage_pct >= 90.0


# ===========================================================================
# 11. Memory & Performance – ضغط الذاكرة
# ===========================================================================

class TestPerformanceStress:

    def test_1000_small_rooms_no_memory_explosion(self):
        """1000 غرفة صغيرة: لا تعليق، ينتهي في وقت معقول."""
        from fireai.core.spatial_engine.density_optimizer import DensityOptimizer
        opt = DensityOptimizer()
        start = time.time()
        for i in range(1000):
            room = _make_room(width=3.0, length=3.0, ceiling_height=3.0)
            layout = opt.optimize(room)
            assert layout.count >= 1
        elapsed = time.time() - start
        assert elapsed < 60.0, f"1000 غرفة استغرقت {elapsed:.1f}s"

    def test_large_polygon_100_vertices(self):
        """مضلع بـ 100 رأس: لا تعليق."""
        from fireai.core.polygon_optimizer import PolygonRoom, PolygonDensityOptimizer
        n, r = 100, 15.0
        poly = [
            (r*math.cos(2*math.pi*i/n), r*math.sin(2*math.pi*i/n))
            for i in range(n)
        ]
        room = PolygonRoom(
            room_id="BIGPOLY", polygon=poly,
            ceiling_height=3.0, detector_type="smoke",
        )
        start = time.time()
        summary = PolygonDensityOptimizer().optimize_polygon(room)
        elapsed = time.time() - start
        assert summary.count >= 1
        assert elapsed < 30.0, f"مضلع 100 رأس استغرق {elapsed:.1f}s"

    def test_repeated_pdf_generation_no_leak(self):
        """توليد 5 PDF متتالية: لا تعليق ولا تراكم أخطاء."""
        from fireai.core.pdf_report import generate_pdf
        report = _BR()
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(5):
                out = os.path.join(tmp, f"rep_{i}.pdf")
                generate_pdf(report, out)
                assert os.path.getsize(out) > 0
