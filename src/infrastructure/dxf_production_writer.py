"""
dxf_production_writer.py - مولد ملفات DXF النهائية
==============================================
"""

import math
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass

# Try ezdxf, fall back to simple text format if not available
try:
    import ezdxf
    from ezdxf.document import Drawing
    HAS_EZDXF = True
except ImportError:
    HAS_EZDXF = False


@dataclass
class ProductionOutput:
    """نتيجة الإنتاج"""
    dxf_created: bool = False
    boq_created: bool = False
    device_count: int = 0
    cable_meters: float = 0.0
    loop_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'dxf_created': self.dxf_created,
            'boq_created': self.boq_created,
            'device_count': self.device_count,
            'cable_meters': self.cable_meters,
            'loop_count': self.loop_count
        }


class DXFProductionWriter:
    """مولد ملفات DXF للإنتاج"""
    
    # Layer colors (AutoCAD ACI)
    LAYER_COLORS = {
        'FIRE-COVERAGE-DEVICES': 1,    # Red
        'FIRE-CABLE-PATHS': 5,      # Blue/Cyan
        'FIRE-DEVICE-LOCATIONS': 3, # Green
        'FIRE-PANEL': 2,          # Yellow
        'FIRE-ROOM-BOUNDARIES': 8,  # Gray
    }
    
    def __init__(self, coverage_radius_m: float = 6.0):
        """
        Args:
            coverage_radius_m: نصف قطر التغطية لكل جهاز
        """
        self.coverage_radius = coverage_radius_m
        self.doc = None
    
    def create_dxf(
        self,
        devices: List[Dict],
        cable_paths: List[List[Tuple[float, float]]],
        panel_location: Tuple[float, float],
        room_boundaries: List[List[Tuple[float, float]]],
        output_file: str
    ) -> bool:
        """
        إنشاء ملف DXF
        
        Args:
            devices: قائمة الأجهزة [{device_id, position: (x,y), type, ...}]
            cable_paths: قائمة مسارات الكابلات [[(x,y), ...], ...]
            panel_location: (x, y) موقع اللوحة
            room_boundaries: [[(x,y), ...], ...] حدود الغرف
            output_file: اسم الملف الناتج
            
        Returns:
            True if successful
        """
        if HAS_EZDXF:
            return self._create_with_ezdxf(
                devices, cable_paths, panel_location, 
                room_boundaries, output_file
            )
        else:
            return self._create_fallback(
                devices, cable_paths, panel_location,
                room_boundaries, output_file
            )
    
    def _create_with_ezdxf(
        self,
        devices: List[Dict],
        cable_paths: List[List[Tuple[float, float]]],
        panel_location: Tuple[float, float],
        room_boundaries: List[List[Tuple[float, float]]],
        output_file: str
    ) -> bool:
        """إنشاء DXF باستخدام ezdxf"""
        try:
            # Create new document
            self.doc = ezdxf.new('R2010')
            msp = self.doc.modelspace()
            
            # 1. Room boundaries (gray)
            self._add_layer('FIRE-ROOM-BOUNDARIES', 8)
            for boundary in room_boundaries:
                if len(boundary) >= 3:
                    points = [f"{p[0]},{p[1]},0" for p in boundary + [boundary[0]]]
                    msp.add_lwpolyline(points, dxfattribs={
                        'layer': 'FIRE-ROOM-BOUNDARIES'
                    })
            
            # 2. Device locations (green points)
            self._add_layer('FIRE-DEVICE-LOCATIONS', 3)
            for device in devices:
                pos = device.get('position')
                if pos:
                    msp.add_circle(
                        (pos[0], pos[1]),
                        radius=0.15,
                        dxfattribs={'layer': 'FIRE-DEVICE-LOCATIONS'}
                    )
            
            # 3. Coverage circles (red)
            self._add_layer('FIRE-COVERAGE-DEVICES', 1)
            for device in devices:
                pos = device.get('position')
                if pos:
                    msp.add_circle(
                        (pos[0], pos[1]),
                        radius=self.coverage_radius,
                        dxfattribs={'layer': 'FIRE-COVERAGE-DEVICES'}
                    )
            
            # 4. Cable paths (blue)
            self._add_layer('FIRE-CABLE-PATHS', 5)
            for path in cable_paths:
                if len(path) >= 2:
                    points = [f"{p[0]},{p[1]},0" for p in path]
                    msp.add_lwpolyline(points, dxfattribs={
                        'layer': 'FIRE-CABLE-PATHS'
                    })
            
            # 5. Panel location (yellow)
            self._add_layer('FIRE-PANEL', 2)
            msp.add_circle(
                panel_location,
                radius=0.3,
                dxfattribs={'layer': 'FIRE-PANEL'}
            )
            
            # Save
            self.doc.saveas(output_file)
            return True
            
        except Exception as e:
            print(f"Error creating DXF: {e}")
            return False
    
    def _add_layer(self, name: str, color: int):
        """إضافة طبقة"""
        if name not in self.doc.layers:
            self.doc.layers.add(name, color=color)
    
    def _create_fallback(
        self,
        devices: List[Dict],
        cable_paths: List[List[Tuple[float, float]]],
        panel_location: Tuple[float, float],
        room_boundaries: List[List[Tuple[float, float]]],
        output_file: str
    ) -> bool:
        """إنشاء ملف نصي بديل (بدون ezdxf)"""
        try:
            with open(output_file.replace('.dxf', '.txt'), 'w') as f:
                f.write("="*60 + "\n")
                f.write("FIRE ALARM PRODUCTION OUTPUT (TXT FORMAT)\n")
                f.write("="*60 + "\n\n")
                
                # Rooms
                f.write(f"ROOM BOUNDARIES ({len(room_boundaries)} rooms):\n")
                for i, boundary in enumerate(room_boundaries):
                    f.write(f"  Room {i+1}: {len(boundary)} points\n")
                
                # Panel
                f.write(f"\nCONTROL PANEL: {panel_location}\n")
                
                # Devices
                f.write(f"\nDEVICES ({len(devices)} total):\n")
                for d in devices:
                    pos = d.get('position', (0, 0))
                    dtype = d.get('type', 'SMOKE')
                    f.write(f"  ID {d.get('id')}: {dtype} at ({pos[0]:.2f}, {pos[1]:.2f})\n")
                
                # Cables
                total_cable = 0.0
                for path in cable_paths:
                    length = self._calculate_path_length(path)
                    total_cable += length
                f.write(f"\nCABLE PATHS ({len(cable_paths)} paths):\n")
                f.write(f"  Total cable: {total_cable:.1f}m\n")
                
                f.write("\n" + "="*60 + "\n")
                f.write("DXF file not generated (ezdxf not installed)\n")
                f.write("Install ezdxf: pip install ezdxf\n")
            
            # Also create a simple SVG for visualization
            self._create_svg(devices, cable_paths, panel_location, 
                          room_boundaries, output_file.replace('.dxf', '.svg'))
            return True
            
        except Exception as e:
            print(f"Error: {e}")
            return False
    
    def _create_svg(
        self,
        devices: List[Dict],
        cable_paths: List[List[Tuple[float, float]]],
        panel_location: Tuple[float, float],
        room_boundaries: List[List[Tuple[float, float]]],
        output_file: str
    ) -> bool:
        """إنشاء SVG للتصور"""
        try:
            # Calculate bounds
            all_points = []
            for b in room_boundaries:
                all_points.extend(b)
            for d in devices:
                pos = d.get('position')
                if pos:
                    all_points.append(pos)
            
            if not all_points:
                return False
            
            minx = min(p[0] for p in all_points)
            maxx = max(p[0] for p in all_points)
            miny = min(p[1] for p in all_points)
            maxy = max(p[1] for p in all_points)
            
            width = maxx - minx + 4
            height = maxy - miny + 4
            scale = 800 / max(width, 1)
            
            offset_x = -minx + 2
            offset_y = -miny + 2
            
            def to_svg(x, y):
                return (x + offset_x) * scale, (height - (y + offset_y)) * scale
            
            with open(output_file, 'w') as f:
                f.write(f'<svg xmlns="http://www.w3.org/2000/svg" '
                      f'width="{width*scale}" height="{height*scale}">\n')
                
                # Room boundaries
                for boundary in room_boundaries:
                    if len(boundary) >= 3:
                        pts = ' '.join(f"{to_svg(p[0], p[1])[0]},{to_svg(p[0], p[1])[1]}" 
                                     for p in boundary + [boundary[0]])
                        f.write(f'<polygon points="{pts}" fill="none" stroke="gray" stroke-width="2"/>\n')
                
                # Cable paths
                for path in cable_paths:
                    if len(path) >= 2:
                        pts = ' '.join(f"{to_svg(p[0], p[1])[0]},{to_svg(p[0], p[1])[1]}" 
                                     for p in path)
                        f.write(f'<polyline points="{pts}" fill="none" stroke="blue" stroke-width="2"/>\n')
                
                # Coverage circles
                r = self.coverage_radius * scale
                for d in devices:
                    pos = d.get('position')
                    if pos:
                        x, y = to_svg(pos[0], pos[1])
                        f.write(f'<circle cx="{x}" cy="{y}" r="{r}" fill="red" opacity="0.1"/>\n')
                
                # Device locations
                for d in devices:
                    pos = d.get('position')
                    if pos:
                        x, y = to_svg(pos[0], pos[1])
                        f.write(f'<circle cx="{x}" cy="{y}" r="4" fill="green"/>\n')
                
                # Panel
                x, y = to_svg(panel_location[0], panel_location[1])
                f.write(f'<rect x="{x-6}" y="{y-6}" width="12" height="12" fill="yellow"/>\n')
                
                f.write('</svg>')
            
            return True
            
        except Exception as e:
            print(f"SVG error: {e}")
            return False
    
    def _calculate_path_length(
        self,
        path: List[Tuple[float, float]]
    ) -> float:
        """حساب طول المسار"""
        if len(path) < 2:
            return 0.0
        
        total = 0.0
        for i in range(len(path) - 1):
            dx = path[i+1][0] - path[i][0]
            dy = path[i+1][1] - path[i][1]
            total += math.sqrt(dx*dx + dy*dy)
        
        return total


def write_production_dxf(
    dxf_file: str,
    devices: List[Dict],
    cable_paths: List[List[Tuple[float, float]]],
    panel_location: Tuple[float, float],
    room_polygons: List[List[Tuple[float, float]]],
    coverage_radius: float = 6.0
) -> ProductionOutput:
    """دالة ملائمة للإنتاج"""
    writer = DXFProductionWriter(coverage_radius_m=coverage_radius)
    
    success = writer.create_dxf(
        devices=devices,
        cable_paths=cable_paths,
        panel_location=panel_location,
        room_boundaries=room_polygons,
        output_file=dxf_file
    )
    
    return ProductionOutput(
        dxf_created=success,
        device_count=len(devices),
        cable_meters=sum(writer._calculate_path_length(p) for p in cable_paths),
        loop_count=len(cable_paths)
    )
