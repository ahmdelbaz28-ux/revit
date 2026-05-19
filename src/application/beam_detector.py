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
        
        Args:
            device_pos: موقع الكاشف
            beam: العارضة
            coverage_radius: نصف قطر التغطية
            
        Returns:
            مضلع Shapely يمثل منطقة الظل
        """
        # إنشاء خط من الكاشف إلى العارضة
        device_point = geom.Point(device_pos.x, device_pos.y)
        
        beam_line = geom.LineString([
            (beam.start.x, beam.start.y),
            (beam.end.x, beam.end.y)
        ])
        
        # الحصول على أقرب نقطة على العارضة من الكاشف
        nearest = beam_line.interpolate(
            beam_line.project(device_point)
        )
        
        # حساب مسافة device من العارضة
        distance = device_point.distance(nearest)
        
        # إذا كان الكاشف خلف العارضة (ضمن نصف القطر)، احسب منطقة الظل
        if distance <= coverage_radius:
            # إنشاء مثلث الظل (من الكاشف إلى نقطتي نهاية العارضة)
            shadow_poly = geom.Polygon([
                (beam.start.x, beam.start.y),
                (beam.end.x, beam.end.y),
                (device_pos.x, device_pos.y)
            ])
            return shadow_poly
            
        return None
    
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
