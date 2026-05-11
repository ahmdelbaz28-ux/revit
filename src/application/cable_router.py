"""
cable_router.py - خوارزمية توجيه الكابلات
=====================================
Dijkstra + تجميع الحلقات + حساب انخفاض الجهد
"""

from typing import List, Tuple, Dict, Any, Optional
import networkx as nx
from src.core.models import Point, Device
from src.application.graph_builder import GraphBuilder
from src.application.schemas import (
    CablePath, LoopGroup, RoutingResult, CableSpecification
)


class CableRouter:
    """محرك توجيه الكابلات"""
    
    def __init__(
        self,
        panel_location: Tuple[float, float],
        panel_voltage_v: float = 24.0,
        max_loop_devices: int = 250,
        max_loop_current_ma: float = 5000.0,
        grid_spacing_m: float = 1.0
    ):
        """
        Args:
            panel_location: (x, y) موقع لوحة التحكم
            panel_voltage_v: جهد اللوحة
            max_loop_devices: أقصى عدد أجهزة لكل حلقة
            max_loop_current_ma: أقصى تيار لكل حلقة
            grid_spacing_m: التباعد بين نقاط الشبكة
        """
        self.panel_location = panel_location
        self.panel_voltage_v = panel_voltage_v
        self.max_loop_devices = max_loop_devices
        self.max_loop_current_ma = max_loop_current_ma
        self.grid_spacing_m = grid_spacing_m
        
        self.graph = None
        self.graph_builder = GraphBuilder(grid_spacing_m)
        
        # مواصفات الكابل
        self.cable_spec = CableSpecification()
    
    def route(
        self,
        devices: List[Device],
        room_polygon: List[Tuple[float, float]],
        wall_lines: List[Tuple[Tuple[float, float], Tuple[float, float]]] = None
    ) -> RoutingResult:
        """
        توجيه جميع الأجهزة.
        
        Args:
            devices: قائمة الأجهزة
            room_polygon: [(x,y), ...] حدود الغرفة/المبنى
            wall_lines: [(p1,p2), ...] خطوط الجدران
            
        Returns:
            RoutingResult بالحلقات والم المسارات
        """
        # 1. بناء الرسم البياني
        self.graph = self.graph_builder.build_from_polygon(
            polygon_points=room_polygon,
            panel_location=self.panel_location,
            wall_lines=wall_lines
        )
        
        if not self.graph:
            raise ValueError("Failed to build navigation graph")
        
        # 2. ربط جميع الأجهزة بالرسم البياني
        device_nodes = {}
        skipped_devices = []
        
        for device in devices:
            if device.position:
                node = self.graph_builder.get_device_node(
                    (device.position.x, device.position.y)
                )
                if node is not None:
                    device_nodes[device.device_id] = node
                else:
                    skipped_devices.append(device.device_id)
        
        if skipped_devices:
            print(f"Warning: {len(skipped_devices)} device(s) could not be mapped to graph: {skipped_devices}")
        
        # 3. حساب المسارات
        all_paths = []
        for device_id, device_node in device_nodes.items():
            path = self._calculate_path(device_node)
            if path:
                all_paths.append({
                    'device_id': device_id,
                    'path': path['path_points'],
                    'length': path['length']
                })
        
        # 4. تجميع الحلقات
        result = self._group_into_loops(all_paths)
        
        return result
    
    def _calculate_path(
        self,
        device_node: int
    ) -> Optional[Dict[str, Any]]:
        """حساب أقصر مسار من الجهاز إلى اللوحة"""
        panel_node = self.graph_builder.get_panel_node()
        
        if panel_node is None:
            return None
        
        try:
            # Dijkstra path
            path = nx.dijkstra_path(
                self.graph,
                device_node,
                panel_node,
                weight='weight'
            )
            
            # استخراج إحداثيات المسار
            path_points = []
            total_length = 0.0
            
            for i, node in enumerate(path):
                pos = self.graph.nodes[node].get('pos')
                if pos:
                    path_points.append(pos)
                
                if i > 0:
                    prev_pos = self.graph.nodes[path[i-1]].get('pos')
                    if prev_pos and pos:
                        dx = pos[0] - prev_pos[0]
                        dy = pos[1] - prev_pos[1]
                        total_length += (dx**2 + dy**2) ** 0.5
            
            return {
                'path_points': path_points,
                'length': total_length,
                'device_node': device_node,
                'panel_node': panel_node
            }
            
        except nx.NetworkXNoPath:
            return None
    
    def _group_into_loops(
        self,
        all_paths: List[Dict[str, Any]]
    ) -> RoutingResult:
        """تجميع الأجهزة في حلقات"""
        result = RoutingResult()
        
        if not all_paths:
            return result
        
        # ترتيب الأجهزة حسب المسافة (ter最喜欢的 = أبعد جهاز)
        sorted_paths = sorted(
            all_paths,
            key=lambda x: x['length'],
            reverse=True
        )
        
        # greedy grouping
        current_loop = LoopGroup(
            loop_id=1,
            panel_location=self.panel_location,
            panel_voltage_v=self.panel_voltage_v,
            max_devices=self.max_loop_devices,
            max_current_ma=self.max_loop_current_ma,
            cable_spec=self.cable_spec
        )
        
        for path_info in sorted_paths:
            device_id = path_info['device_id']
            device_length = path_info['length']
            
            # إضافة لل حلقة الحالية
            current_loop.add_device(device_id, device_current_ma=1.0)  # 1mA per device
            current_loop.total_length_m += device_length
            
            # التحقق من الامتثال
            current_loop.check_compliance()
            
            # إذا امتلات الحلقة، إنشاء حلقة جديدة
            if not current_loop.is_compliant:
                # إزالة الأخير
                current_loop.devices.pop()
                current_loop.total_current_ma -= 1.0
                current_loop.total_length_m -= device_length
                
                # فحص و إضافة للحالة
                current_loop.check_compliance()
                result.add_loop(current_loop)
                
                # إنشاء حلقة جديدة
                current_loop = LoopGroup(
                    loop_id=len(result.loops) + 1,
                    panel_location=self.panel_location,
                    panel_voltage_v=self.panel_voltage_v,
                    max_devices=self.max_loop_devices,
                    max_current_ma=self.max_loop_current_ma,
                    cable_spec=self.cable_spec
                )
                
                # إضافة these to new loop
                current_loop.add_device(device_id, device_current_ma=1.0)
                current_loop.total_length_m = device_length
        
        # إضافة الحلقة الأخيرة
        if current_loop.devices:
            current_loop.check_compliance()
            result.add_loop(current_loop)
        
        return result
    
    def route_single_device(
        self,
        device_position: Tuple[float, float]
    ) -> Optional[CablePath]:
        """توجيه جهاز واحد"""
        if not self.graph:
            return None
        
        # الحصول على node للجهاز
        device_node = self.graph_builder.get_device_node(device_position)
        if device_node is None:
            return None
        
        # حساب المسار
        path_info = self._calculate_path(device_node)
        if not path_info:
            return None
        
        # إنشاء CablePath
        cable_path = CablePath(
            device_id=0,  # Would be passed in
            path_points=path_info['path_points'],
            total_length_m=path_info['length']
        )
        
        return cable_path
    
    def validate_loop(
        self,
        loop: LoopGroup
    ) -> Dict[str, Any]:
        """التحقق من حلقة"""
        is_compliant = loop.check_compliance()
        
        return {
            'compliant': is_compliant,
            'voltage_drop_v': loop.voltage_drop_v,
            'max_allowed_v_drop': self.panel_voltage_v * 0.10,
            'current_ma': loop.total_current_ma,
            'max_current_ma': loop.max_current_ma,
            'device_count': len(loop.devices),
            'max_devices': loop.max_devices,
            'total_length_m': loop.total_length_m
        }


def route_from_dxf(
    dxf_file: str,
    devices: List[Device],
    panel_location: Tuple[float, float]
) -> RoutingResult:
    """دالة ملائمة للتوجيه من ملف DXF"""
    # استخراج حدود المبنى
    from fireai.dxf_importer import DXFImporter
    
    importer = DXFImporter()
    rooms = importer.import_file(dxf_file)
    
    if not rooms:
        raise ValueError("No rooms found in DXF file")
    
    # استخدام أكبر غرفة كحدود
    biggest_room = max(rooms, key=lambda r: r.area or 0)
    polygon = [(p.x, p.y) for p in biggest_room.polygon.exterior]
    
    # إنشاء الموجه
    router = CableRouter(panel_location=panel_location)
    
    return router.route(devices, polygon)
