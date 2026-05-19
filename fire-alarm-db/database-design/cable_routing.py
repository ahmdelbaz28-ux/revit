#!/usr/bin/env python3
"""
cable_routing.py - Constraint-Based Cable Routing Engine
=====================================================

This module handles automatic cable routing for fire alarm systems:
- Build weighted graph from route network
- Constraint-based shortest path calculation
- Loop generation for device circuits

Author: FireAlarmAI Engineering Team
Date: 2026-05-09
"""

import os
import sys
import json
import logging
import math
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

import networkx as nx
import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class RoutingPoint:
    """A point in the routing network"""
    node_id: int
    x: float
    y: float
    node_type: str  # 'junction', 'panel', 'device', 'tray'
    floor_id: int


@dataclass
class RoutingSegment:
    """A segment between two routing points"""
    segment_id: int
    from_node_id: int
    to_node_id: int
    segment_type: str  # 'CableTray', 'Corridor', 'Room', 'FireWall', etc.
    length_meters: float
    is_accessible: bool = True


@dataclass
class RouteResult:
    """Result of a routing calculation"""
    path_points: List[Tuple[float, float]]  # (x, y) coordinates
    total_length: float
    segments: List[Dict]  # Detailed segment info
    is_feasible: bool
    warnings: List[str]


@dataclass
class LoopResult:
    """Result of a loop routing calculation"""
    loop_id: int
    panel_device_id: int
    ordered_devices: List[Dict]  # Device info with path to next
    total_length: float
    device_count: int
    is_feasible: bool
    warnings: List[str]


# =============================================================================
# Cable Routing Engine
# =============================================================================

class CableRoutingEngine:
    """
    Constraint-Based Cable Routing Engine
    
    Uses NetworkX to build a weighted graph from the routing network
    and finds optimal paths respecting physical constraints.
    """
    
    # Penalty multipliers for different segment types
    DEFAULT_PENALTIES = {
        'CableTray': 1.0,      # Preferred
        'Corridor': 1.5,        # Good alternative
        'Room': 10.0,           # Avoid room cuts
        'FireWall': 50.0,       # Very expensive
        'Obstacle': 100.0,       # Nearly impassable
        'default': 20.0         # Unknown
    }
    
    def __init__(self, db_session=None, floor_id: int = 1):
        """
        Initialize the routing engine
        
        Args:
            db_session: SQLAlchemy database session (optional for testing)
            floor_id: Floor to route within
        """
        self.session = db_session
        self.floor_id = floor_id
        self.graph = None
        self.nodes = {}
        self.segments = {}
        self.penalties = self.DEFAULT_PENALTIES.copy()
        
        # Build the graph
        self._build_graph()
    
    def _build_graph(self):
        """Build the NetworkX graph from database or default test network"""
        logger.info(f"Building routing graph for floor {self.floor_id}")
        
        if self.session is not None:
            # Import models - will be loaded from database
            try:
                from ai_design_integration import RouteNode, RouteSegment, Device, AIDesignDevice
                
                # Get route nodes for this floor
                route_nodes = self.session.query(RouteNode).filter(
                    RouteNode.FloorID == self.floor_id
                ).all()
                
                # Get route segments
                route_segments = self.session.query(RouteSegment).filter(
                    RouteSegment.FloorID == self.floor_id
                ).all()
                
                # Add nodes
                for node in route_nodes:
                    self.nodes[node.NodeID] = {
                        'x': node.XCoord,
                        'y': node.YCoord,
                        'node_type': node.NodeType,
                        'floor_id': node.FloorID
                    }
                
                # Add segments
                for seg in route_segments:
                    self.segments[seg.SegmentID] = {
                        'from_node': seg.FromNodeID,
                        'to_node': seg.ToNodeID,
                        'segment_type': seg.SegmentType,
                        'length_meters': float(seg.LengthMeters or 0),
                        'is_accessible': seg.IsAccessible
                    }
            except ImportError:
                logger.warning("Database models not available, using test network")
        
        # Create NetworkX graph
        self.graph = nx.Graph()
        
        # Add nodes (if from DB)
        for node_id, node_data in self.nodes.items():
            self.graph.add_node(node_id, **node_data)
        
        # Create test network if no DB nodes
        if not self.nodes:
            self._create_test_network()
        
        # Add edges with weights
        for seg_id, seg_data in self.segments.items():
            # Calculate weight based on segment type
            weight = self._calculate_segment_weight(seg_data)
            
            self.graph.add_edge(
                seg_data['from_node'],
                seg_data['to_node'],
                weight=weight,
                segment_id=seg_id,
                segment_type=seg_data['segment_type'],
                length=seg_data['length_meters']
            )
        
        logger.info(f"Graph built: {len(self.nodes)} nodes, {len(self.segments)} segments")
    
    def _create_test_network(self):
        """Create a test routing network for demonstration"""
        # Create corridor backbone nodes
        corridor_nodes = [
            (1, 0, 5, 'junction'),
            (2, 10, 5, 'junction'),
            (3, 20, 5, 'junction'),
            (4, 30, 5, 'junction'),
        ]
        
        # Create cable tray nodes
        tray_nodes = [
            (5, 5, 2, 'tray'),
            (6, 15, 2, 'tray'),
            (7, 25, 2, 'tray'),
        ]
        
        # Add all nodes
        for node_id, x, y, node_type in corridor_nodes + tray_nodes:
            self.nodes[node_id] = {'x': x, 'y': y, 'node_type': node_type, 'floor_id': self.floor_id}
            self.graph.add_node(node_id, **self.nodes[node_id])
        
        # Create segments (corridor = CableTray type)
        segments = [
            (1, 1, 2, 'CableTray', 10),
            (2, 2, 3, 'CableTray', 10),
            (3, 3, 4, 'CableTray', 10),
            (4, 1, 5, 'CableTray', 3.2),
            (5, 2, 6, 'CableTray', 3.2),
            (6, 3, 7, 'CableTray', 3.2),
        ]
        
        for seg_id, from_node, to_node, seg_type, length in segments:
            self.segments[seg_id] = {
                'from_node': from_node,
                'to_node': to_node,
                'segment_type': seg_type,
                'length_meters': length,
                'is_accessible': True
            }
    
    def _calculate_segment_weight(self, segment) -> float:
        """Calculate weight for a segment based on type"""
        seg_type = segment.get('segment_type', 'default')
        penalty = self.penalties.get(seg_type, self.penalties['default'])
        base_length = segment.get('length_meters', 1)
        
        if not segment.get('is_accessible', True):
            penalty *= 10
        
        return base_length * penalty
    
    def add_obstacle_penalty(self, segment_type: str, multiplier: float):
        """
        Add penalty for a specific segment type
        
        Args:
            segment_type: Type of segment (e.g., 'FireWall', 'Room')
            multiplier: Weight multiplier (e.g., 10.0 for 10x penalty)
        """
        self.penalties[segment_type] = multiplier
        logger.info(f"Added penalty for '{segment_type}': x{multiplier}")
        
        # Rebuild graph with new penalties
        self._build_graph()
    
    def snap_to_graph(self, x: float, y: float) -> int:
        """
        Snap a device position to the nearest graph node
        
        Args:
            x, y: Device coordinates
            
        Returns:
            Nearest node ID
        """
        if not self.nodes:
            raise ValueError("No nodes in graph")
        
        # Find nearest node
        min_dist = float('inf')
        nearest_node = None
        
        for node_id, node_data in self.nodes.items():
            dist = math.sqrt((node_data['x'] - x)**2 + (node_data['y'] - y)**2)
            if dist < min_dist:
                min_dist = dist
                nearest_node = node_id
        
        logger.debug(f"Snapped ({x}, {y}) to node {nearest_node} (dist: {min_dist:.2f}m)")
        return nearest_node
    
    def route_between_devices(self, 
                            device_a: Tuple[float, float],
                            device_b: Tuple[float, float]) -> RouteResult:
        """
        Find shortest path between two devices
        
        Args:
            device_a: (x, y) coordinates of device A
            device_b: (x, y) coordinates of device B
            
        Returns:
            RouteResult with path and length
        """
        warnings = []
        
        # Snap to graph nodes
        node_a = self.snap_to_graph(*device_a)
        node_b = self.snap_to_graph(*device_b)
        
        if node_a == node_b:
            # Same node - direct path
            return RouteResult(
                path_points=[device_a, device_b],
                total_length=self._distance(device_a, device_b),
                segments=[],
                is_feasible=True,
                warnings=[]
            )
        
        try:
            # Find shortest path
            path = nx.shortest_path(
                self.graph, node_a, node_b, weight='weight'
            )
            
            # Get path coordinates
            path_points = []
            for node_id in path:
                node_data = self.nodes.get(node_id, {})
                path_points.append((node_data.get('x', 0), node_data.get('y', 0)))
            
            # Calculate total length
            total_length = sum(
                self.graph[path[i]][path[i+1]].get('length', 0)
                for i in range(len(path)-1)
            )
            
            # Get segment details
            segments = []
            for i in range(len(path)-1):
                edge_data = self.graph[path[i]][path[i+1]]
                segments.append({
                    'from_node': path[i],
                    'to_node': path[i+1],
                    'segment_type': edge_data.get('segment_type', 'unknown'),
                    'length': edge_data.get('length', 0)
                })
            
            # Check for warnings
            for seg in segments:
                if seg['segment_type'] in ['FireWall', 'Room']:
                    warnings.append(f"Path passes through {seg['segment_type']}")
            
            return RouteResult(
                path_points=path_points,
                total_length=total_length,
                segments=segments,
                is_feasible=True,
                warnings=warnings
            )
            
        except nx.NetworkXNoPath:
            return RouteResult(
                path_points=[],
                total_length=0,
                segments=[],
                is_feasible=False,
                warnings=["No path exists between devices"]
            )
    
    def _distance(self, p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
        """Calculate Euclidean distance between points"""
        return math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)
    
    def route_loop(self, devices: List[Dict], 
                 panel: Tuple[float, float],
                 panel_id: int = 1) -> LoopResult:
        """
        Create a loop visiting all devices
        
        Uses nearest-neighbor heuristic for device ordering
        
        Args:
            devices: List of device dicts with 'device_id', 'x', 'y', 'device_type'
            panel: Panel location (x, y)
            panel_id: Panel device ID
            
        Returns:
            LoopResult with ordered devices and total length
        """
        warnings = []
        
        if not devices:
            return LoopResult(
                loop_id=1,
                panel_device_id=panel_id,
                ordered_devices=[],
                total_length=0,
                device_count=0,
                is_feasible=True,
                warnings=[]
            )
        
        # Get device positions
        device_positions = {
            d['device_id']: (d['x'], d['y']) 
            for d in devices
        }
        
        # Nearest neighbor heuristic
        unvisited = set(device_positions.keys())
        current_pos = panel
        current_node = self.snap_to_graph(*current_pos)
        
        ordered_devices = []
        total_length = 0
        
        while unvisited:
            # Find nearest device
            min_dist = float('inf')
            nearest_device_id = None
            
            for dev_id in unvisited:
                dev_pos = device_positions[dev_id]
                dist = self._distance(current_pos, dev_pos)
                if dist < min_dist:
                    min_dist = dist
                    nearest_device_id = dev_id
            
            if nearest_device_id is None:
                break
            
            # Route to this device
            dev_pos = device_positions[nearest_device_id]
            route_result = self.route_between_devices(current_pos, dev_pos)
            
            ordered_devices.append({
                'device_id': nearest_device_id,
                'device_type': next(
                    (d['device_type'] for d in devices 
                     if d['device_id'] == nearest_device_id),
                    'Unknown'
                ),
                'path_points': route_result.path_points,
                'path_length': route_result.total_length
            })
            
            total_length += route_result.total_length
            warnings.extend(route_result.warnings)
            
            current_pos = dev_pos
            current_node = self.snap_to_graph(*current_pos)
            unvisited.remove(nearest_device_id)
        
        # Return to panel
        route_result = self.route_between_devices(current_pos, panel)
        total_length += route_result.total_length
        warnings.extend(route_result.warnings)
        
        return LoopResult(
            loop_id=1,
            panel_device_id=panel_id,
            ordered_devices=ordered_devices,
            total_length=total_length,
            device_count=len(devices),
            is_feasible=True,
            warnings=warnings
        )


# =============================================================================
# Database Integration Functions
# =============================================================================

def load_routing_graph(db_session, floor_id: int = 1) -> CableRoutingEngine:
    """Load routing graph from database"""
    return CableRoutingEngine(db_session=db_session, floor_id=floor_id)


def route_all_loops(db_session, project_id: int, system_id: int) -> Dict:
    """
    Route all loops for a fire alarm system
    
    Args:
        db_session: SQLAlchemy session
        project_id: Project ID
        system_id: Fire alarm system ID
        
    Returns:
        Dict with routing results and validation status
    """
    from ai_design_integration import (
        AIDesignDevice, DeviceConnection, Project, FireAlarmSystem
    )
    
    # Get system
    system = db_session.query(FireAlarmSystem).filter(
        FireAlarmSystem.SystemID == system_id
    ).first()
    
    if not system:
        return {'error': f'System {system_id} not found'}
    
    floor_id = system.FloorID
    
    # Build routing engine
    routing = CableRoutingEngine(db_session=db_session, floor_id=floor_id)
    
    # Get loops for this system
    loops = db_session.query(DeviceConnection).filter(
        DeviceConnection.SystemID == system_id
    ).all()
    
    results = []
    all_warnings = []
    
    for loop_id in set(c.LoopID for c in loops if c.LoopID):
        loop_devices = [
            {'device_id': c.DeviceID, 'device_type': c.DeviceType, 
             'x': c.XCoord, 'y': c.YCoord}
            for c in loops if c.LoopID == loop_id
        ]
        
        # Get panel for this loop
        panel_conn = next((c for c in loops if c.LoopID == loop_id and c.IsPanel), None)
        
        if panel_conn:
            panel_pos = (panel_conn.XCoord, panel_conn.YCoord)
            panel_id = panel_conn.DeviceID
            
            # Route the loop
            loop_result = routing.route_loop(loop_devices, panel_pos, panel_id)
            
            # Save connections
            for dev_info in loop_result.ordered_devices:
                conn = db_session.query(DeviceConnection).filter(
                    DeviceConnection.DeviceID == dev_info['device_id']
                ).first()
                
                if conn:
                    conn.PolylinePath = json.dumps(dev_info['path_points'])
                    conn.CalculatedLength = dev_info['path_length']
            
            results.append({
                'loop_id': loop_id,
                'device_count': loop_result.device_count,
                'total_length': loop_result.total_length,
                'is_feasible': loop_result.is_feasible
            })
            
            all_warnings.extend(loop_result.warnings)
    
    # Run validation
    from rule_checker import RoutingValidator
    validator = RoutingValidator()
    
    validation_results = []
    for result in results:
        if result['total_length'] > 2000:
            validation_results.append({
                'loop_id': result['loop_id'],
                'error': f"Loop too long: {result['total_length']}m"
            })
    
    db_session.commit()
    
    return {
        'project_id': project_id,
        'system_id': system_id,
        'loops_routed': len(results),
        'results': results,
        'warnings': all_warnings,
        'validation': validation_results,
        'status': 'Routed' if not validation_results else 'Validation_Failed'
    }


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Cable Routing Engine")
    parser.add_argument('--floor-id', type=int, default=1)
    parser.add_argument('--from-x', type=float, default=0)
    parser.add_argument('--from-y', type=float, default=0)
    parser.add_argument('--to-x', type=float, default=10)
    parser.add_argument('--to-y', type=float, default=5)
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("CABLE ROUTING ENGINE TEST")
    print("="*60)
    
    # Create engine
    routing = CableRoutingEngine(floor_id=args.floor_id)
    
    print(f"\nGraph: {len(routing.nodes)} nodes, {len(routing.segments)} segments")
    print(f"Penalties: {routing.penalties}")
    
    # Test routing
    result = routing.route_between_devices(
        (args.from_x, args.from_y),
        (args.to_x, args.to_y)
    )
    
    print(f"\nRoute from ({args.from_x}, {args.from_y}) to ({args.to_x}, {args.to_y}):")
    print(f"  Feasible: {result.is_feasible}")
    print(f"  Length: {result.total_length:.1f}m")
    print(f"  Path points: {result.path_points}")
    print(f"  Warnings: {result.warnings}")