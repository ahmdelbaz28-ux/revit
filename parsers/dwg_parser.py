"""
FireAI DWG Parser - AutoCAD DWG file parser
"""

import logging
from typing import Any, List, Optional

from core.models import (
    UniversalElement, ElementType, Point3D, Geometry, 
    SemanticProperties, ChangeSource
)

logger = logging.getLogger(__name__)


class DWGParser:
    """
    محلل ملفات AutoCAD DWG
    """
    
    def __init__(self):
        logger.info("DWG Parser initialized")
    
    def parse_dwg(self, dwg_path: str) -> List[UniversalElement]:
        """
        تحليل ملف DWG واستخراج العناصر
        
        في البداية، نستخدم ezdxf library
        لاحقاً، سنستخدم AutoCAD COM API للتطبيق الحقيقي
        """
        try:
            import ezdxf
            
            doc = ezdxf.readfile(dwg_path)
            msp = doc.modelspace()
            
            elements = []
            
            for entity in msp:
                element = self._convert_entity_to_universal(entity, dwg_path)
                if element:
                    elements.append(element)
            
            logger.info(f"Parsed {len(elements)} elements from {dwg_path}")
            return elements
        
        except ImportError:
            logger.warning("ezdxf not installed. Install with: pip install ezdxf")
            return []
        except Exception as e:
            logger.error(f"Error parsing DWG {dwg_path}: {e}")
            return []

    def extract_rooms_from_chaos(self, doc: Any) -> List['UniversalElement']:
        """Chaos-to-Order Engine v2.0"""
        from shapely.geometry import LineString
        from shapely.ops import unary_union, polygonize

        lines = []
        try:
            msp = doc.modelspace()
            for entity in msp:
                if entity.dxftype() not in ['LINE', 'LWPOLYLINE', 'POLYLINE']:
                    continue
                try:
                    if entity.dxftype() == 'LINE':
                        start = (entity.dxf.start.x, entity.dxf.start.y)
                        end = (entity.dxf.end.x, entity.dxf.end.y)
                        if ((end[0]-start[0])**2 + (end[1]-start[1])**2) > 1e-9:
                            lines.append(LineString([start, end]))
                    elif entity.dxftype() in ['LWPOLYLINE', 'POLYLINE']:
                        pts = [(p[0], p[1]) for p in entity.get_points()]
                        if len(pts) >= 2:
                            if entity.closed and pts[0] != pts[-1]:
                                pts.append(pts[0])
                            valid = True
                            for i in range(len(pts)-1):
                                if ((pts[i+1][0]-pts[i][0])**2 + (pts[i+1][1]-pts[i][1])**2) < 1e-9:
                                    valid = False
                                    break
                            if valid:
                                lines.append(LineString(pts))
                except:
                    continue
        except:
            return []

        if len(lines) < 3:
            return []

        try:
            merged = unary_union(lines)
            
            # ==== Smart topology healing: close gaps up to 1cm ====
            if hasattr(merged, 'geoms') or isinstance(merged, list):
                # Expand to close gaps (1cm = 0.01), then shrink back (0.5cm)
                merged = merged.buffer(0.01).buffer(-0.005)
            # ===============================================================
            
            polys = list(polygonize(merged))
        except:
            return []

        rooms = []
        for i, poly in enumerate(polys):
            try:
                if poly.area < 1.0 or not poly.is_valid or not poly.is_simple:
                    continue
                coords = list(poly.exterior.coords)
                if coords[0] == coords[-1]:
                    coords = coords[:-1]
                clean = [coords[0]]
                for pt in coords[1:]:
                    if (pt[0]-clean[-1][0])**2 + (pt[1]-clean[-1][1])**2 > 1e-9:
                        clean.append(pt)
                if len(clean) < 3:
                    continue
                pts = [Point3D(x, y, 0) for x, y in clean]
                geom = Geometry(points=pts, polyline_closed=True)
                geom.calculate_area()
                name = f"Room_{int(geom.area)}m2_{i}"
                room = UniversalElement(
                    properties=SemanticProperties(element_type=ElementType.ROOM, name=name),
                    geometry=geom, source_file="chaos_inference"
                )
                rooms.append(room)
            except:
                continue
        return rooms

    def _convert_entity_to_universal(self, entity, source_file: str) -> Optional[UniversalElement]:
        """تحويل كائن DXF إلى Universal Element"""
        try:
            element_type = ElementType.UNKNOWN
            points = []
            dxftype = entity.dxftype()
            
            # Determine type based on entity type
            if dxftype == 'LWPOLYLINE':
                points = [Point3D(x, y, 0) for x, y in entity.get_points()]
                
                # Heuristic: check layer name
                layer = entity.dxf.layer.upper()
                element_type = self._infer_element_type(layer)
            
            elif dxftype == 'LINE':
                start = entity.dxf.start
                end = entity.dxf.end
                points = [Point3D(start[0], start[1], start[2]), 
                         Point3D(end[0], end[1], end[2])]
                element_type = ElementType.EQUIPMENT
            
            elif dxftype == 'CIRCLE':
                center = entity.dxf.center
                points = [Point3D(center[0], center[1], center[2])]
                element_type = ElementType.EQUIPMENT
            
            # NEW: Support ARC
            elif dxftype == 'ARC':
                center = entity.dxf.center
                radius = entity.dxf.radius
                # Convert arc to polyline approximation
                import math
                start_angle = entity.dxf.start_angle
                end_angle = entity.dxf.end_angle
                num_points = 12
                for i in range(num_points + 1):
                    angle = start_angle + (end_angle - start_angle) * i / num_points
                    rad = math.radians(angle)
                    x = center[0] + radius * math.cos(rad)
                    y = center[1] + radius * math.sin(rad)
                    points.append(Point3D(x, y, center[2]))
                element_type = ElementType.EQUIPMENT
            
            # NEW: Support SPLINE
            elif dxftype == 'SPLINE':
                # Extract control points from spline
                ctrl_points = entity.control_points
                if ctrl_points:
                    points = [Point3D(p[0], p[1], p[2] if len(p) > 2 else 0) for p in ctrl_points]
                element_type = ElementType.EQUIPMENT
            
            # NEW: Support TEXT
            elif dxftype == 'TEXT':
                # Text doesn't have geometry, use insertion point
                insert = entity.dxf.insert
                points = [Point3D(insert[0], insert[1], insert[2] if len(insert) > 2 else 0)]
                element_type = ElementType.EQUIPMENT
            
            # NEW: Support BLOCK
            elif dxftype == 'BLOCK':
                # Blocks can contain other entities - return None for now
                # The entities inside will be processed separately
                return None
            
            else:
                # Skip unsupported types
                return None
            
            if not points:
                return None
            
            # Create Universal Element
            polyline_closed = dxftype in ['LWPOLYLINE', 'CIRCLE']
            geometry = Geometry(points=points, polyline_closed=polyline_closed)
            geometry.calculate_area()
            geometry.calculate_perimeter()
            
            # Extract metadata from custom properties
            metadata = self._extract_custom_properties(entity)
            
            properties = SemanticProperties(
                element_type=element_type,
                name=entity.dxf.layer,
                layer=entity.dxf.layer,
                material=metadata.get('material'),
                fire_rating=metadata.get('fire_rating')
            )
            
            element = UniversalElement(
                properties=properties,
                geometry=geometry,
                source_file=source_file,
                last_modified_by=ChangeSource.AUTOCAD.value
            )
            
            # Store AutoCAD handle
            if hasattr(entity.dxf, 'handle'):
                element.autocad_handle = entity.dxf.handle
            
            return element
        
        except Exception as e:
            logger.error(f"Error converting entity: {e}")
            return None
    
    def _infer_element_type(self, layer: str) -> ElementType:
        """استنتاج نوع العنصر من اسم الـ layer"""
        layer_upper = layer.upper()
        if 'WALL' in layer_upper:
            return ElementType.WALL
        elif 'ROOM' in layer_upper:
            return ElementType.ROOM
        elif 'DOOR' in layer_upper:
            return ElementType.DOOR
        elif 'WINDOW' in layer_upper:
            return ElementType.WINDOW
        elif 'MECHANICAL' in layer_upper:
            return ElementType.MECHANICAL
        elif 'ELECTRICAL' in layer_upper:
            return ElementType.ELECTRICAL
        else:
            return ElementType.EQUIPMENT
    
    def _extract_custom_properties(self, entity) -> dict:
        """استخراج metadata من custom properties"""
        metadata = {}
        
        try:
            # Try to get XDATA (extended entity data)
            if hasattr(entity, 'xdata'):
                for xrecord in entity.xdata:
                    for tag, value in zip(xrecord[0], xrecord[1]):
                        if tag == 'MATERIAL':
                            metadata['material'] = value
                        elif tag == 'FIRE_RATING':
                            metadata['fire_rating'] = value
        
        except Exception:
            pass
        
        return metadata