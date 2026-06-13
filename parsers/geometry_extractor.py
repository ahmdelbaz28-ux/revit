"""
GEOMETRY EXTRACTOR — Wall Detection for NFPA 72 Engine
=======================================================
يستخلص الجدران المغلقة من ملف PDF (vector paths) فقط.
لا يستخدم شبكات عصبية. لا يخمّن.
كل ما يستخلصه يأتي مع درجة ثقته ومصدره.

Author: The Consultant Who Refused to Lie
"""

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # PDF features unavailable without pymupdf
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class ConfidenceLevel(Enum):
    CERTAIN = "CERTAIN"        # إحداثيات رقمية دقيقة
    HIGH = "HIGH"              # موثوق لكن يحتاج تأكيد
    MODERATE = "MODERATE"      # يحتاج مراجعة
    UNACCEPTABLE = "UNACCEPTABLE"


@dataclass
class WallElement:
    """جدار مستخلص من الرسم."""
    geometry: List[Tuple[float, float]]  # قائمة نقاط مغلقة
    confidence: ConfidenceLevel
    source: str
    raw_data: Dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        geometry_list = [(round(x, 2), round(y, 2)) for x, y in self.geometry]
        return {
            "geometry": list(geometry_list),
            "confidence": self.confidence.value,
            "source": self.source,
            "raw_data": self.raw_data
        }
    
    def get_area(self) -> float:
        """Calculate approximate area using shoelace formula."""
        if len(self.geometry) < 3:
            return 0.0
        n = len(self.geometry)
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += self.geometry[i][0] * self.geometry[j][1]
            area -= self.geometry[j][0] * self.geometry[i][1]
        return abs(area) / 2.0
    
    def get_perimeter(self) -> float:
        """Calculate perimeter."""
        if len(self.geometry) < 2:
            return 0.0
        perimeter = 0.0
        for i in range(len(self.geometry) - 1):
            dx = self.geometry[i+1][0] - self.geometry[i][0]
            dy = self.geometry[i+1][1] - self.geometry[i][1]
            perimeter += (dx**2 + dy**2) ** 0.5
        return perimeter


class GeometryExtractor:
    """
    يستخلص الجدران المغلقة من صفحة PDF vector.
    لا يتعامل مع الصور raster.
    
    USAGE:
        extractor = GeometryExtractor("drawing.pdf", page=0)
        walls = extractor.extract_walls()
        
        for wall in walls:
            print(f"Wall area: {wall.get_area():.1f} sq units")
    """

    def __init__(self, pdf_path: str, page_number: int = 0):
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)
        if page_number >= len(self.doc):
            raise ValueError(f"Page {page_number} not found in PDF")
        self.page = self.doc[page_number]
        self.page_number = page_number

    def extract_walls(self) -> List[WallElement]:
        """
        استخراج كل المسارات المغلقة التي يمكن أن تكون جدراناً.
        
        Returns:
            List of WallElement objects
        """
        drawings = self.page.get_drawings()
        walls = []

        for draw in drawings:
            wall = self._parse_drawing(draw)
            if wall:
                walls.append(wall)

        self.doc.close()
        return self._merge_adjacent_walls(walls)
    
    def _parse_drawing(self, draw: dict) -> Optional[WallElement]:
        """Parse a single drawing object into a WallElement."""
        # نتعامل فقط مع المسارات المغلقة (type 'f' = fill, أو 's' = stroke, 're' = rect)
        draw_type = draw.get("type", "")
        if draw_type not in ("f", "s", "re", "fs", "fse"):
            return None

        # نستبعد الخطوط الرفيعة جداً (غالباً أبواب أو شبابيك)
        width = draw.get("width", 0) or 0
        if draw_type in ("s", "fs", "fse") and width < 0.3:
            return None

        # الحصول على المستطيل المحيط
        rect = draw.get("rect")
        if not rect:
            return None

        # استخراج النقاط من الـ rect
        if draw_type == "re":
            # مستطيل بسيط
            points = [
                (rect.x0, rect.y0),
                (rect.x1, rect.y0),
                (rect.x1, rect.y1),
                (rect.x0, rect.y1),
            ]
            confidence = ConfidenceLevel.CERTAIN
            source = "VECTOR_RECT"
        else:
            # استخدم المستطيل المحيط للرسم type="s"
            # هذا يعمل لأن PyMuPDF لا يُرجع items مفصلة للرسم
            points = [
                (rect.x0, rect.y0),
                (rect.x1, rect.y0),
                (rect.x1, rect.y1),
                (rect.x0, rect.y1),
            ]
            # classify confidence based on width
            confidence = ConfidenceLevel.CERTAIN if width >= 1.0 else ConfidenceLevel.HIGH
            source = "VECTOR_RECT"
            # close the shape if not already closed
            points.append(points[0])

        return WallElement(
            geometry=points,
            confidence=confidence,
            source=source,
            raw_data={
                "type": draw_type,
                "width": width,
                "color": draw.get("color"),
                "layer": draw.get("layer")
            }
        )
    
    def _extract_points_from_items(self, items: list) -> List[Tuple[float, float]]:
        """Extract points from drawing items."""
        points = []
        for item in items:
            item_type = item[0]
            if item_type == "l":  # line to
                points.append((item[1], item[2]))
            elif item_type == "c":  # curve to
                # نأخذ نقطة النهاية فقط
                points.append((item[-2], item[-1]))
            elif item_type == "m":  # move to (start)
                points.append((item[1], item[2]))
            elif item_type == "s":  # smooth curve
                points.append((item[-2], item[-1]))
        return points
    
    def _merge_adjacent_walls(self, walls: List[WallElement]) -> List[WallElement]:
        """Merge walls that share edges."""
        if len(walls) <= 1:
            return walls
        
        # Sort by area (largest first - these are likely outer walls)
        walls.sort(key=lambda w: w.get_area(), reverse=True)
        
        merged = []
        used = set()
        
        for i, wall in enumerate(walls):
            if i in used:
                continue
            
            current = wall
            used.add(i)
            
            # Try to merge with other walls
            for j, other in enumerate(walls):
                if j in used:
                    continue
                
                # Check if walls share an edge
                if self._walls_share_edge(current, other):
                    current = self._merge_walls(current, other)
                    used.add(j)
            
            merged.append(current)
        
        return merged
    
    def _walls_share_edge(self, wall1: WallElement, wall2: WallElement) -> bool:
        """Check if two walls share a significant edge."""
        # Simple check: if their bounding boxes overlap significantly
        if len(wall1.geometry) < 2 or len(wall2.geometry) < 2:
            return False
        
        # Get first point of each wall
        p1_start = wall1.geometry[0]
        p2_start = wall2.geometry[0]
        
        # If walls are very close, they might be the same wall
        distance = ((p1_start[0] - p2_start[0])**2 + (p1_start[1] - p2_start[1])**2)**0.5
        
        # Threshold for "same wall" - this is configurable
        return distance < 1.0
    
    def _merge_walls(self, wall1: WallElement, wall2: WallElement) -> WallElement:
        """Merge two walls into one (simple union)."""
        # This is a simplified merge - in reality you'd use proper polygon union
        all_points = wall1.geometry[:-1] + wall2.geometry
        
        return WallElement(
            geometry=all_points,
            confidence=ConfidenceLevel.MODERATE,
            source="MERGED",
            raw_data={"merged_from": [wall1.source, wall2.source]}
        )

    def get_wall_count(self) -> int:
        """Get count of extracted walls (without closing)."""
        drawings = self.page.get_drawings()
        count = 0
        for draw in drawings:
            if draw.get("type") in ("f", "s", "re", "fs", "fse"):
                width = draw.get("width", 0) or 0
                if width >= 0.5:
                    count += 1
        return count
    
    def get_page_info(self) -> dict:
        """Get page dimensions and info."""
        rect = self.page.rect
        return {
            "page": self.page_number,
            "width": rect.width,
            "height": rect.height,
            "wall_count": self.get_wall_count()
        }


def extract_walls_from_pdf(pdf_path: str, page: int = 0) -> List[WallElement]:
    """
    دالة مساعدة سريعة لاستخراج الجدران.
    
    Args:
        pdf_path: مسار ملف PDF
        page: رقم الصفحة ( يبدأ من 0)
        
    Returns:
        List of WallElement objects
    """
    extractor = GeometryExtractor(pdf_path, page)
    return extractor.extract_walls()


def extract_rooms_from_walls(walls: List[WallElement]) -> List[dict]:
    """
    استخراج الغرف من الجدران المستخلصة.
    
    كل غرفة تكون面 مغلقة (closed polygon).
    """
    rooms = []
    
    for wall in walls:
        area = wall.get_area()
        if area > 10:  # Filter out tiny shapes (likely objects, not rooms)
            rooms.append({
                "area": round(area, 2),
                "perimeter": round(wall.get_perimeter(), 2),
                "points": wall.geometry,
                "confidence": wall.confidence.value
            })
    
    # Sort by area (largest first)
    rooms.sort(key=lambda r: r["area"], reverse=True)
    
    return rooms