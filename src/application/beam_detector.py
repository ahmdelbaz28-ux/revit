"""
beam_detector.py - كشف وتحليل العوارض وتأثيرها على تغطية الكواشف
المرجع: NFPA 72 (2022) الفقرة 17.6.3.2.4
"""
from typing import List, Optional
from src.core.models import Room, Beam, Point
import shapely.geometry as geom
import shapely.ops as ops


class BeamDetector:
    """
    يكشف العوارض العميقة التي تؤثر على تغطية الكواشف.
    
    حدودNFPA 72:
    - عمق < 10% من ارتفاع السقف → سقف أملس
    - عمق >= 10% وتباعد >= 40% من ارتفاع السقف → كل جيب عارضة يحتاج كاشف
    - عمق >= 10% وتباعد < 40% → تقليل التباعد بنسبة معينة
    """
    
    # نسبة عمق العارضة الحرجة (10% من ارتفاع السقف)
    DEPTH_RATIO_THRESHOLD = 0.10
    
    def analyze(self, room: Room, beams: List[Beam], 
              ceiling_height: float = None) -> List[Beam]:
        """
        يحلل العوارض ويعيد العوارض 'العميقة' (تتطلب معالجة خاصة).
        
        Args:
            room: الغرفة
            beams: قائمة العوارض
            ceiling_height: ارتفاع السقف (افتراضي 3 أمتار)
            
        Returns:
            قائمة العوارض العميقة
        """
        if ceiling_height is None:
            ceiling_height = room.height if room.height else 3.0
            
        depth_threshold = ceiling_height * self.DEPTH_RATIO_THRESHOLD
        
        deep_beams = []
        for beam in beams:
            if not hasattr(beam, 'depth'):
                continue
            if beam.depth >= depth_threshold:
                deep_beams.append(beam)
                
        return deep_beams
    
    def is_blocked(self, point_a: Point, point_b: Point, 
                  beams: List[Beam]) -> bool:
        """
        يتحقق من أن خط الرؤية بين نقطتين لا يقطع أي عارضة عميقة.
        
        Args:
            point_a: نقطة البداية
            point_b: نقطة النهاية  
            beams: قائمة العوارض
            
        Returns:
            True إذا كان هناك عارضة تعترض خط الرؤية
        """
        if not beams:
            return False
            
        # إنشاء خط الرؤية
        line = geom.LineString([(point_a.x, point_a.y), (point_b.x, point_b.y)])
        
        for beam in beams:
            # إنشاء مضلع العارضة كخط
            beam_line = geom.LineString([
                (beam.start.x, beam.start.y),
                (beam.end.x, beam.end.y)
            ])
            
            # توسيع العارضة لتصبح مضلع (buffer عرض العارضة)
            beam_poly = beam_line.buffer(beam.width)
            
            if line.intersects(beam_poly):
                return True
                
        return False
    
    def compute_shadow(self, device_pos: Point, beam: Beam,
                    coverage_radius: float) -> Optional[geom.Polygon]:
        """
        يحسب 'منطقة الظل' خلف عارضة بالنسبة لكاشف.

        هذه المنطقة تُطرح من circle التغطية للdevice.

        الظل يمتد من حواف العارضة بعيداً عن الكاشف حتى نهاية نصف قطر
        التغطية. الخطان المماسان (tangent) من الكاشف إلى نقطتي نهاية
        العارضة يحددان الحدود الجانبية لمنطقة الظل.

        المرجع: NFPA 72-2022 §17.6.3.2.4 — العوارض العميقة تخلق جيوباً
        تحتاج كواشف مستقلة.

        Args:
            device_pos: موقع الكاشف
            beam: العارضة
            coverage_radius: نصف قطر التغطية

        Returns:
            مضلع Shapely يمثل منطقة الظل خلف العارضة، أو None إذا لم
            يكن هناك ظل (الكاشف بعيد جداً)
        """
        import math

        device_point = geom.Point(device_pos.x, device_pos.y)

        beam_line = geom.LineString([
            (beam.start.x, beam.start.y),
            (beam.end.x, beam.end.y)
        ])

        # الحصول على أقرب نقطة على العارضة من الكاشف
        nearest = beam_line.interpolate(
            beam_line.project(device_point)
        )

        # حساب مسافة الكاشف من العارضة
        distance = device_point.distance(nearest)

        # إذا كان الكاشف خارج نصف قطر التغطية من العارضة، لا يوجد ظل
        if distance > coverage_radius:
            return None

        # إذا كان الكاشف على العارضة نفسها أو خلفها مباشرة (distance≈0)،
        # فإن نصف قطر التغطية بأكمله خلف العارضة هو ظل
        if distance < 0.01:
            # الظل = نصف دائرة التغطية الممتدة خلف العارضة
            beam_dir_x = beam.end.x - beam.start.x
            beam_dir_y = beam.end.y - beam.start.y
            beam_len = math.hypot(beam_dir_x, beam_dir_y)
            if beam_len < 1e-9:
                return None
            # normal يشير بعيداً عن الكاشف
            nx = -beam_dir_y / beam_len
            ny = beam_dir_x / beam_len
            # نصف دائرة خلف العارضة
            coverage_circle = device_point.buffer(coverage_radius, resolution=32)
            # تقسيم بناءً على اتجاه العارضة
            beam_mid_x = (beam.start.x + beam.end.x) / 2
            beam_mid_y = (beam.start.y + beam.end.y) / 2
            # الظل هو الجزء من دائرة التغطية على الجانب البعيد عن الكاشف
            cutting_line = geom.LineString([
                (beam.start.x, beam.start.y),
                (beam.end.x, beam.end.y)
            ])
            # استخدام خط العارضة لتقسيم الدائرة
            from shapely.ops import split
            try:
                parts = split(coverage_circle, cutting_line)
                if len(parts.geoms) >= 2:
                    # اختيار الجزء الأبعد عن الكاشف (وراء العارضة)
                    best = None
                    best_dist = -1
                    for part in parts.geoms:
                        centroid = part.centroid
                        d = centroid.distance(device_point)
                        if d > best_dist:
                            best_dist = d
                            best = part
                    return best
            except Exception:
                pass
            # Fallback: إرجاع دائرة التغطية بأكملها كظل (محافظ)
            return coverage_circle

        # الحساب العام: خطان مماسان من الكاشف إلى حواف العارضة
        # ثم امتدادهما خلف العارضة حتى نهاية نصف قطر التغطية

        # متجه من الكاشف إلى كل حافة من العارضة
        dx_start = beam.start.x - device_pos.x
        dy_start = beam.start.y - device_pos.y
        dist_start = math.hypot(dx_start, dy_start)

        dx_end = beam.end.x - device_pos.x
        dy_end = beam.end.y - device_pos.y
        dist_end = math.hypot(dx_end, dy_end)

        if dist_start < 1e-9 or dist_end < 1e-9:
            return None

        # تطويل الخطوط إلى نهاية نصف قطر التغطية
        # نقطة على الخط من الكاشف إلى beam.start ممتدة إلى coverage_radius
        scale_start = coverage_radius / dist_start
        far_start_x = device_pos.x + dx_start * scale_start
        far_start_y = device_pos.y + dy_start * scale_start

        # نقطة على الخط من الكاشف إلى beam.end ممتدة إلى coverage_radius
        scale_end = coverage_radius / dist_end
        far_end_x = device_pos.x + dx_end * scale_end
        far_end_y = device_pos.y + dy_end * scale_end

        # مضلع الظل: beam.start → beam.end → far_end → far_start
        # هذا يمثل المنطقة خلف العارضة المحجوبة عن الكاشف
        shadow_poly = geom.Polygon([
            (beam.start.x, beam.start.y),
            (beam.end.x, beam.end.y),
            (far_end_x, far_end_y),
            (far_start_x, far_start_y),
        ])

        # التحقق من صحة المضلع
        if not shadow_poly.is_valid:
            shadow_poly = shadow_poly.buffer(0)

        # تقاطع الظل مع دائرة التغطية (الظل لا يمتد خارج نصف القطر)
        coverage_circle = device_point.buffer(coverage_radius, resolution=32)
        shadow_in_coverage = shadow_poly.intersection(coverage_circle)

        if shadow_in_coverage.is_empty:
            return None

        return shadow_in_coverage
    
    def get_coverage_gaps(self, room: Room, devices: List, 
                       beams: List[Beam]) -> List[Point]:
        """
        يجد المناطق 'المظللة' (غير المغطاة) بسبب العوارض.
        
        Args:
            room: الغرفة
            devices: الأجهزة المقترحة
            beams: العوارض
            
        Returns:
            قائمة بالنقاط التي تحتاج أجهزة إضافية
        """
        gaps = []
        
        # بسيطة: كل جيب بين عوارض يحتاج كاشف
        for beam in beams:
            mid_x = (beam.start.x + beam.end.x) / 2
            mid_y = (beam.start.y + beam.end.y) / 2
            mid_point = Point(mid_x, mid_y)
            
            # إذا كانت نقطة المنتصف داخل الغرفة
            if room.polygon.is_point_inside(mid_point):
                gaps.append(mid_point)
                
        return gaps
