"""
graph_builder.py - بناء الرسم البياني للممرات والمساحات القابلة للمرور
=================================================================
"""

from typing import List, Tuple, Optional, Set, Dict
import networkx as nx
import numpy as np
from src.core.models import Point, Polygon, Room
import shapely.geometry as geom
import shapely.ops as ops


class GraphBuilder:
    """يبني رسم بياني قابل للمرور من غرفة وأجهزة ولوحة تحكم"""
    
    def __init__(self, grid_spacing_m: float = 1.0):
        """
        Args:
            grid_spacing_m: التباعد بين نقاط الشبكة (متر)
        """
        self.grid_spacing_m = grid_spacing_m
        self.graph = None
        self.walls = []
        self.boundary = None
    
    def build_from_room(
        self,
        room: Room,
        panel_location: Tuple[float, float],
        obstacles: List[Polygon] = None
    ) -> nx.Graph:
        """
        بناء رسم بياني من غرفة.
        
        Args:
            room: الغرفة
            panel_location: (x, y) موقع اللوحة
            obstacles: قائمة المضلعات المعيقة (جدران، أعمدة، إلخ)
            
        Returns:
            NetworkX graph
        """
        self._extract_walls_and_boundary(room, obstacles)
        
        # إنشاء شبكة النقاط
        grid_points = self._create_grid_points(room)
        
        # تصفية النقاط المعيقة
        valid_points = self._filter_valid_points(
            grid_points, 
            self.walls, 
            self.boundary
        )
        
        # ربط النقاط
        self.graph = self._connect_points(valid_points)
        
        # ربط اللوحة
        panel_point = self._nearest_valid_point(
            valid_points, 
            panel_location
        )
        if panel_point:
            self.graph.add_node(
                'panel', 
                pos=panel_point,
                is_panel=True
            )
        
        return self.graph
    
    def build_from_polygon(
        self,
        polygon_points: List[Tuple[float, float]],
        panel_location: Tuple[float, float],
        wall_lines: List[Tuple[Tuple[float, float], Tuple[float, float]]] = None
    ) -> nx.Graph:
        """
        بناء رسم بياني من مضلع.
        
        Args:
            polygon_points: [(x,y), ...] حدود المخطط
            panel_location: (x, y) موقع اللوحة
            wall_lines: [(p1, p2), ...] خطوط الجدران
        """
        # إنشاء boundary
        self.boundary = geom.Polygon(polygon_points)
        if not self.boundary.is_valid:
            self.boundary = self.boundary.buffer(0)
        
        # تحويل الجدران
        self.walls = []
        if wall_lines:
            for p1, p2 in wall_lines:
                self.walls.append(geom.LineString([p1, p2]))
        
        # إنشاء شبكة النقاط
        minx, miny, maxx, maxy = self.boundary.bounds
        
        grid_points = []
        x = minx
        while x <= maxx:
            y = miny
            while y <= maxy:
                grid_points.append((x, y))
                y += self.grid_spacing_m
            x += self.grid_spacing_m
        
        # تصفية النقاط
        valid_points = self._filter_valid_points(
            grid_points,
            self.walls,
            self.boundary
        )
        
        # ربط النقاط
        self.graph = self._connect_points(valid_points)
        
        # ربط اللوحة - استخدامها كـ node منفصل
        panel_point = self._nearest_valid_point(
            valid_points,
            panel_location
        )
        if panel_point is not None:
            #獲得 الإحداثيات
            panel_pos = valid_points[panel_point]
            self.graph.add_node(
                'panel',
                pos=panel_pos,
                is_panel=True
            )
            
            # ربط اللوحة بأقرب نقاط الشبكة
            panel_x, panel_y = panel_pos
            for node in list(self.graph.nodes()):
                if node == 'panel':
                    continue
                pos = self.graph.nodes[node].get('pos')
                if pos:
                    dx = abs(pos[0] - panel_x)
                    dy = abs(pos[1] - panel_y)
                    if dx < 1.5 or dy < 1.5:  # Connect to neighboring nodes
                        dist = (dx**2 + dy**2) ** 0.5
                        self.graph.add_edge(node, 'panel', weight=dist)
        
        return self.graph
    
    def _extract_walls_and_boundary(
        self,
        room: Room,
        obstacles: List[Polygon] = None
    ):
        """استخراج الجدران والحدود"""
        self.walls = []
        
        if room.polygon and room.polygon.exterior:
            # إضافة الجدران
            points = room.polygon.exterior
            for i in range(len(points)):
                j = (i + 1) % len(points)
                line = geom.LineString([
                    (points[i].x, points[i].y),
                    (points[j].x, points[j].y)
                ])
                self.walls.append(line)
            
            # إنشاء المضلع
            coords = [(p.x, p.y) for p in points]
            self.boundary = geom.Polygon(coords)
        else:
            raise ValueError("Room has no polygon")
    
    def _create_grid_points(self, room: Room) -> List[Tuple[float, float]]:
        """إنشاء نقاط الشبكة"""
        coords = [(p.x, p.y) for p in room.polygon.exterior]
        minx = min(c[0] for c in coords)
        maxx = max(c[0] for c in coords)
        miny = min(c[1] for c in coords)
        maxy = max(c[1] for c in coords)
        
        points = []
        x = minx
        while x <= maxx:
            y = miny
            while y <= maxy:
                points.append((x, y))
                y += self.grid_spacing_m
            x += self.grid_spacing_m
        
        return points
    
    def _filter_valid_points(
        self,
        points: List[Tuple[float, float]],
        walls: List[geom.LineString],
        boundary: geom.Polygon
    ) -> List[Tuple[float, float]]:
        """تصفية النقاط غير المعيقة"""
        valid = []
        
        # إنشاء buffer للجدران
        wall_buffer = 0.2  # 20cm clearance
        
        for x, y in points:
            pt = geom.Point(x, y)
            
            # يجب أن يكون داخل الحدود
            if not boundary.contains(pt) and not boundary.touches(pt):
                continue
            
            # يجب ألا يقطع جدار
            blocked = False
            
            for wall in walls:
                if wall.distance(pt) < wall_buffer:
                    blocked = True
                    break
            
            if not blocked:
                # تحويل إلى tuple عادي
                valid.append((float(x), float(y)))
        
        return valid
    
    def _connect_points(
        self,
        points: List[Tuple[float, float]]
    ) -> nx.Graph:
        """ربط النقاط لإنشاء الرسم البياني"""
        G = nx.Graph()
        
        # إضافة جميع النقاط
        for i, (x, y) in enumerate(points):
            G.add_node(i, pos=(x, y))
        
        # ربط الجيران (أفقية وعمودية)
        threshold = self.grid_spacing_m * 1.5
        
        for i, (x1, y1) in enumerate(points):
            for j, (x2, y2) in enumerate(points):
                if i >= j:
                    continue
                
                # check if horizontal or vertical neighbor
                dx = abs(x2 - x1)
                dy = abs(y2 - y1)
                
                if (dx < 0.1 and dy < threshold) or (dy < 0.1 and dx < threshold):
                    distance = (dx**2 + dy**2) ** 0.5
                    G.add_edge(i, j, weight=distance)
        
        return G
    
    def _nearest_valid_point(
        self,
        valid_points: List[Tuple[float, float]],
        target: Tuple[float, float]
    ) -> Optional[int]:
        """البحث عن أقرب نقطة صالحة"""
        if not valid_points:
            return None
        
        min_dist = float('inf')
        nearest_idx = None
        
        for i, (x, y) in enumerate(valid_points):
            dx = x - target[0]
            dy = y - target[1]
            dist = (dx**2 + dy**2) ** 0.5
            
            if dist < min_dist:
                min_dist = dist
                nearest_idx = i
        
        return nearest_idx
    
    def get_device_node(
        self,
        device_position: Tuple[float, float]
    ) -> Optional[int]:
        """الحصول على أقرب node integer لجهاز"""
        if not self.graph:
            return None

        # Get only integer nodes (not panel string node)
        int_nodes = [n for n in self.graph.nodes() if isinstance(n, int)]
        if not int_nodes:
            return None
        
        min_dist = float('inf')
        nearest_node = None
        
        for node in int_nodes:
            pos = self.graph.nodes[node].get('pos')
            if not pos:
                continue
            
            dx = pos[0] - device_position[0]
            dy = pos[1] - device_position[1]
            dist = (dx**2 + dy**2) ** 0.5
            
            if dist < min_dist:
                min_dist = dist
                nearest_node = node
        
        return nearest_node
    
    def get_panel_node(self) -> Optional[str]:
        """الحصول على node اللوحة"""
        if not self.graph:
            return None
        
        for node in self.graph.nodes():
            if self.graph.nodes[node].get('is_panel'):
                return node
        
        return None
