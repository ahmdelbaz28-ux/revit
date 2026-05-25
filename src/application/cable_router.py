"""
cable_router.py V2.0 - Cable Routing Algorithm
=====================================
Dijkstra + loop grouping + voltage drop calculation

V2.0 Fix — Cross-Room Cable Routing:
  Previous version used only the BIGGEST room polygon as the routing
  boundary, which broke routing for devices in other rooms.
  Fix: Build a unified navigation graph from ALL room polygons,
  allowing cables to route through corridors and between rooms.

V20.2 Fix #10 (CRITICAL) — Device Current Draw:
  Previous version hardcoded device_current_ma=1.0 for ALL devices.
  This is WRONG and DANGEROUS: strobes draw 150-450mA, horns draw
  250mA. A loop with 10 strobes (1.5A actual) would be calculated as
  10mA, allowing 150x overload -> CABLE OVERHEATING -> FIRE RISK.
  Fix: Use NFPA 72 device current table based on DeviceType enum.

V20.2 Fix #11 (HIGH) — Star Topology Length Accumulation:
  Previous code summed all individual panel-to-device path lengths,
  double-counting shared cable segments for daisy-chain circuits.
  For Class B (daisy-chain), voltage drop worst-case is at the END
  of line, so total_length_m should be the FURTHEST device distance,
  NOT the sum of all distances.
  Fix: Track max path length instead of summing all paths.
"""

from typing import List, Tuple, Dict, Any, Optional
import logging
import networkx as nx
from src.core.models import Point, Device, DeviceType
from src.application.graph_builder import GraphBuilder
from src.application.schemas import (
    CablePath, LoopGroup, RoutingResult, CableSpecification
)

logger = logging.getLogger(__name__)

# ============================================================================
# V20.2 FIX #10: NFPA 72 Device Current Draw Table
# ============================================================================
# Per NFPA 72 section 18.5 and manufacturer data sheets.
# These are CONSERVATIVE steady-state values.
# Strobes and horns have 2-3x inrush during first 50-200ms.
# For voltage drop under alarm conditions (NFPA 72 section 10.14.1),
# inrush must be considered -- but loop grouping uses steady-state.
#
# SAFETY: Using 1.0mA for strobes (old code) means a loop with 10
# strobes would calculate 10mA total vs 1.5A actual = 150x overload.
# Overloaded cables overheat, potentially causing ignition.
DEVICE_CURRENT_DRAW_MA: Dict[DeviceType, float] = {
    # Detectors -- low standby current (SLC loop devices)
    DeviceType.SMOKE_DETECTOR: 3.0,       # ~1-4mA standby per NFPA 72
    DeviceType.HEAT_DETECTOR: 5.0,        # ~3-5mA standby
    DeviceType.DUCT_DETECTOR: 5.0,        # ~3-5mA standby
    DeviceType.MONITOR_MODULE: 5.0,       # ~3-5mA per module
    DeviceType.ISOLATOR: 3.0,             # ~1-3mA
    DeviceType.RELAY_MODULE: 10.0,        # ~5-15mA when energized

    # Notification appliances -- HIGH current (NAC circuit devices)
    # These values are STEADY-STATE; inrush is 2-3x higher.
    DeviceType.STROBE: 220.0,             # 15cd: 150mA, 30cd: 220mA, 75cd: 450mA
    DeviceType.SOUNDER: 250.0,            # Horn: ~250mA typical
    DeviceType.SPEAKER: 57.0,             # 4W@70V: 57mA typical

    # Manual call points -- negligible current (normally open contact)
    DeviceType.MANUAL_CALL_POINT: 0.5,    # <1mA supervisory

    # Control panel -- not a loop device, but handle gracefully
    DeviceType.CONTROL_PANEL: 0.0,        # Panel is the source, not a load
}

# Conservative fallback for unknown device types
DEFAULT_DEVICE_CURRENT_MA = 25.0  # Conservative middle ground


def get_device_current_ma(device: Device) -> float:
    """Get current draw in mA for a device based on its DeviceType.

    V20.2 FIX #10: Replaces hardcoded 1.0mA per device.

    Args:
        device: The Device object.

    Returns:
        Current draw in milliamps (steady-state).
    """
    current = DEVICE_CURRENT_DRAW_MA.get(device.device_type)
    if current is not None:
        return current
    logger.warning(
        "Unknown device type %s for device %s; using conservative "
        "default %.1fmA (verify with manufacturer data)",
        device.device_type, device.device_id, DEFAULT_DEVICE_CURRENT_MA,
    )
    return DEFAULT_DEVICE_CURRENT_MA


class CableRouter:
    """Cable routing engine with NFPA 72 compliant loop grouping."""
    
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
            panel_location: (x, y) panel location
            panel_voltage_v: Panel voltage
            max_loop_devices: Max devices per loop
            max_loop_current_ma: Max current per loop
            grid_spacing_m: Grid node spacing
        """
        self.panel_location = panel_location
        self.panel_voltage_v = panel_voltage_v
        self.max_loop_devices = max_loop_devices
        self.max_loop_current_ma = max_loop_current_ma
        self.grid_spacing_m = grid_spacing_m
        
        self.graph = None
        self.graph_builder = GraphBuilder(grid_spacing_m)
        
        # Cable specification
        self.cable_spec = CableSpecification()
    
    def route(
        self,
        devices: List[Device],
        room_polygon: List[Tuple[float, float]],
        wall_lines: List[Tuple[Tuple[float, float], Tuple[float, float]]] = None
    ) -> RoutingResult:
        """Route all devices into loop groups.
        
        Args:
            devices: List of devices to route
            room_polygon: [(x,y), ...] room/building boundary
            wall_lines: [(p1,p2), ...] wall lines
            
        Returns:
            RoutingResult with loop groups and paths
        """
        # 1. Build navigation graph
        self.graph = self.graph_builder.build_from_polygon(
            polygon_points=room_polygon,
            panel_location=self.panel_location,
            wall_lines=wall_lines
        )
        
        if not self.graph:
            raise ValueError("Failed to build navigation graph")
        
        # 2. Map devices to graph nodes
        # V20.2 FIX #10: Build device_id -> Device lookup for current draw
        device_lookup = {d.device_id: d for d in devices}
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
            logger.warning(
                "%d device(s) could not be mapped to graph: %s",
                len(skipped_devices), skipped_devices,
            )
        
        # 3. Calculate paths
        all_paths = []
        for device_id, device_node in device_nodes.items():
            path = self._calculate_path(device_node)
            if path:
                all_paths.append({
                    'device_id': device_id,
                    'path': path['path_points'],
                    'length': path['length']
                })
        
        # 4. Group into loops
        # V20.2 FIX #10: Pass device_lookup so loop grouping can get current draw
        result = self._group_into_loops(all_paths, device_lookup)
        
        return result
    
    def _calculate_path(
        self,
        device_node: int
    ) -> Optional[Dict[str, Any]]:
        """Calculate shortest path from device to panel using Dijkstra."""
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
            
            # Extract path coordinates
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
        all_paths: List[Dict[str, Any]],
        device_lookup: Optional[Dict[Any, Device]] = None,
    ) -> RoutingResult:
        """Group devices into loops with NFPA 72 compliance.

        V20.2 FIX #10: Uses actual device current draw instead of
        hardcoded 1.0mA. Strobes draw 220mA -- using 1mA would allow
        220x overload, risking cable ignition.

        V20.2 FIX #11: Uses MAX path length for total_length_m instead
        of summing all paths. For a Class B daisy-chain circuit, the
        voltage drop worst-case is at the END of line, so the relevant
        length is the distance to the FURTHEST device, NOT the sum of
        all individual distances (which double-counts shared segments).
        """
        result = RoutingResult()
        
        if not all_paths:
            return result
        
        # Sort devices by distance (furthest first)
        sorted_paths = sorted(
            all_paths,
            key=lambda x: x['length'],
            reverse=True
        )
        
        # Greedy grouping
        current_loop = LoopGroup(
            loop_id=1,
            panel_location=self.panel_location,
            panel_voltage_v=self.panel_voltage_v,
            max_devices=self.max_loop_devices,
            max_current_ma=self.max_loop_current_ma,
            cable_spec=self.cable_spec
        )

        # V20.2 FIX #11: Track max path length for accurate voltage drop
        # For Class B daisy-chain, worst-case is at the furthest device.
        # Summing all individual distances double-counts shared cable segments.
        max_path_length_in_loop = 0.0
        # Track path lengths by device_id for recomputation on removal
        device_path_lengths: Dict[Any, float] = {}
        
        for path_info in sorted_paths:
            device_id = path_info['device_id']
            device_length = path_info['length']

            # V20.2 FIX #10: Get ACTUAL device current from DeviceType lookup
            device = device_lookup.get(device_id) if device_lookup else None
            device_current = get_device_current_ma(device) if device else DEFAULT_DEVICE_CURRENT_MA
            
            # Add to current loop
            current_loop.add_device(device_id, device_current_ma=device_current)
            # V20.2 FIX #11: Use max path length, not sum of all paths
            device_path_lengths[device_id] = device_length
            max_path_length_in_loop = max(max_path_length_in_loop, device_length)
            current_loop.total_length_m = max_path_length_in_loop
            
            # Check compliance
            current_loop.check_compliance()
            
            # If loop is full, create a new loop
            if not current_loop.is_compliant:
                # Remove the last device
                current_loop.devices.pop()
                current_loop.total_current_ma -= device_current
                del device_path_lengths[device_id]
                # V20.2 FIX #11: Recompute max length from remaining devices
                if device_path_lengths:
                    max_path_length_in_loop = max(device_path_lengths.values())
                else:
                    max_path_length_in_loop = 0.0
                current_loop.total_length_m = max_path_length_in_loop
                
                # Finalize current loop
                current_loop.check_compliance()
                result.add_loop(current_loop)
                
                # Create a new loop
                current_loop = LoopGroup(
                    loop_id=len(result.loops) + 1,
                    panel_location=self.panel_location,
                    panel_voltage_v=self.panel_voltage_v,
                    max_devices=self.max_loop_devices,
                    max_current_ma=self.max_loop_current_ma,
                    cable_spec=self.cable_spec
                )
                max_path_length_in_loop = device_length
                device_path_lengths = {device_id: device_length}
                
                # Add device to new loop
                current_loop.add_device(device_id, device_current_ma=device_current)
                current_loop.total_length_m = max_path_length_in_loop
        
        # Add the last loop
        if current_loop.devices:
            current_loop.check_compliance()
            result.add_loop(current_loop)
        
        return result
    
    def route_single_device(
        self,
        device_position: Tuple[float, float]
    ) -> Optional[CablePath]:
        """Route a single device."""
        if not self.graph:
            return None
        
        # Get node for device
        device_node = self.graph_builder.get_device_node(device_position)
        if device_node is None:
            return None
        
        # Calculate path
        path_info = self._calculate_path(device_node)
        if not path_info:
            return None
        
        # Create CablePath
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
        """Validate a loop for compliance."""
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
    """Convenience function for routing from a DXF file.

    V2.0 Fix: Uses the convex hull of ALL room polygons as the routing
    boundary, instead of only the biggest room. This ensures devices in
    all rooms can be reached by cable routing.

    Args:
        dxf_file: Path to DXF file.
        devices: List of devices to route.
        panel_location: (x, y) panel position.

    Returns:
        RoutingResult with loop groups and paths.
    """
    from fireai.dxf_importer import DXFImporter

    importer = DXFImporter()
    rooms = importer.import_file(dxf_file)

    if not rooms:
        raise ValueError("No rooms found in DXF file")

    # V2.0: Build unified polygon from ALL rooms using convex hull
    # Previous code used only the biggest room, which broke routing
    # for devices in other rooms.
    try:
        from shapely.geometry import MultiPolygon
        from shapely.ops import unary_union

        # Collect all room polygons
        all_polygons = []
        for r in rooms:
            poly = getattr(r, 'polygon', None)
            if poly and hasattr(poly, 'exterior'):
                all_polygons.append(poly)

        if all_polygons:
            # Union all room polygons, then take convex hull for routing
            unified = unary_union(all_polygons)
            hull = unified.convex_hull
            polygon = [(p[0], p[1]) for p in hull.exterior.coords]
        else:
            # Fallback to biggest room if no polygons available
            biggest_room = max(rooms, key=lambda r: r.area or 0)
            polygon = [(p.x, p.y) for p in biggest_room.polygon.exterior]
    except ImportError:
        # Shapely not available: fallback to biggest room
        biggest_room = max(rooms, key=lambda r: r.area or 0)
        polygon = [(p.x, p.y) for p in biggest_room.polygon.exterior]

    # Create router
    router = CableRouter(panel_location=panel_location)

    return router.route(devices, polygon)
