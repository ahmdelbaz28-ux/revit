"""
ETAP-AI-WORK Revit Integration Geometry Transformation Service
===========================================================

Service for transforming Revit geometry for GIS and other systems.

Principal Software Architect: Eng. Ahmed Elbaz
"""
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import math


class GeometryTransformationService:
    """
    Service for transforming Revit geometry for GIS and other downstream systems.
    Converts 3D BIM geometry to 2D representations and GIS-compatible formats.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    async def transform_to_2d_footprint(self, geometry_3d: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform 3D geometry to 2D footprint for GIS applications.
        
        Args:
            geometry_3d: 3D geometry data
            
        Returns:
            Dict: 2D footprint geometry
        """
        # Extract 2D footprint from 3D geometry
        footprint = {
            "type": "Polygon",
            "coordinates": [],
            "bbox": [],
            "properties": {
                "original_height": geometry_3d.get("height"),
                "transformation_method": "2d_footprint"
            }
        }
        
        # In a real implementation, this would extract the 2D footprint
        # For now, we'll simulate it
        if "vertices" in geometry_3d:
            # Project 3D vertices to 2D (X, Y plane)
            footprint["coordinates"] = [
                [[vertex[0], vertex[1]] for vertex in geometry_3d["vertices"]]
            ]
        
        # Calculate bounding box
        if footprint["coordinates"]:
            x_coords = [point[0] for ring in footprint["coordinates"] for point in ring]
            y_coords = [point[1] for ring in footprint["coordinates"] for point in ring]
            footprint["bbox"] = [min(x_coords), min(y_coords), max(x_coords), max(y_coords)]
        
        return footprint
    
    async def transform_to_gis_format(self, model_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Transform model elements to GIS-compatible format.
        
        Args:
            model_elements: List of model elements to transform
            
        Returns:
            List[Dict]: GIS-compatible features
        """
        gis_features = []
        
        for element in model_elements:
            if element.get('location') and element.get('geometry'):
                # Create a GIS feature
                feature = {
                    "type": "Feature",
                    "geometry": await self._element_to_geometry(element),
                    "properties": {
                        "id": element.get('id'),
                        "name": element.get('name', ''),
                        "category": element.get('category', ''),
                        "family": element.get('family', ''),
                        "type": element.get('type', ''),
                        "parameters": element.get('parameters', {}),
                        "level": element.get('level'),
                        "workset": element.get('workset')
                    },
                    "id": element.get('id')
                }
                gis_features.append(feature)
        
        self.logger.info(f"Transformed {len(gis_features)} elements to GIS format")
        return gis_features
    
    async def transform_coordinate_system(self, coordinates: List[float], 
                                       from_crs: str = "Revit_Local", 
                                       to_crs: str = "WGS84") -> List[float]:
        """
        Transform coordinates from one coordinate system to another.
        
        Args:
            coordinates: Input coordinates [X, Y, Z]
            from_crs: Source coordinate reference system
            to_crs: Target coordinate reference system
            
        Returns:
            List[float]: Transformed coordinates
        """
        # For now, implement a basic offset transformation
        # In a real implementation, this would use proper CRS transformation libraries
        transformed = coordinates.copy()
        
        # Example: Apply a simple offset (this would be replaced with proper transformation)
        if from_crs == "Revit_Local" and to_crs == "WGS84":
            # This is a simplified example - real implementation would use pyproj or similar
            # Adding a simple offset for demonstration
            transformed[0] += 0.001  # longitude offset
            transformed[1] += 0.001  # latitude offset
            # Keep Z (elevation) the same
        
        return transformed
    
    async def simplify_geometry(self, geometry: Dict[str, Any], tolerance: float = 0.1) -> Dict[str, Any]:
        """
        Simplify complex geometry using Douglas-Peucker algorithm or similar.
        
        Args:
            geometry: Geometry to simplify
            tolerance: Simplification tolerance
            
        Returns:
            Dict: Simplified geometry
        """
        simplified = geometry.copy()
        
        if geometry.get("type") == "Polygon" and "coordinates" in geometry:
            # Simplify polygon coordinates
            simplified["coordinates"] = [
                await self._simplify_polygon_ring(ring, tolerance) 
                for ring in geometry["coordinates"]
            ]
        elif geometry.get("type") == "LineString" and "coordinates" in geometry:
            # Simplify line string
            simplified["coordinates"] = await self._simplify_line_string(
                geometry["coordinates"], tolerance
            )
        
        return simplified
    
    async def _simplify_polygon_ring(self, ring: List[List[float]], tolerance: float) -> List[List[float]]:
        """Simplify a polygon ring using distance-based simplification."""
        if len(ring) <= 2:
            return ring
        
        # Implement a basic distance-based simplification
        simplified = [ring[0]]  # Always keep first point
        
        for i in range(1, len(ring) - 1):
            prev_point = simplified[-1]
            curr_point = ring[i]
            next_point = ring[i + 1]
            
            # Calculate distance from line formed by prev and next to current point
            dist = self._point_to_line_distance(curr_point, prev_point, next_point)
            
            if dist > tolerance:
                simplified.append(curr_point)
        
        simplified.append(ring[-1])  # Always keep last point
        return simplified
    
    async def _simplify_line_string(self, coords: List[List[float]], tolerance: float) -> List[List[float]]:
        """Simplify a line string using distance-based simplification."""
        if len(coords) <= 2:
            return coords
        
        simplified = [coords[0]]  # Always keep first point
        
        for i in range(1, len(coords) - 1):
            prev_point = simplified[-1]
            curr_point = coords[i]
            next_point = coords[i + 1]
            
            # Calculate distance from line formed by prev and next to current point
            dist = self._point_to_line_distance(curr_point, prev_point, next_point)
            
            if dist > tolerance:
                simplified.append(curr_point)
        
        simplified.append(coords[-1])  # Always keep last point
        return simplified
    
    def _point_to_line_distance(self, point: List[float], line_start: List[float], line_end: List[float]) -> float:
        """Calculate perpendicular distance from point to line."""
        x, y = point[0], point[1]
        x1, y1 = line_start[0], line_start[1]
        x2, y2 = line_end[0], line_end[1]
        
        # Calculate the distance from point to line
        nom = abs((y2 - y1) * x - (x2 - x1) * y + x2 * y1 - y2 * x1)
        denom = math.sqrt((y2 - y1)**2 + (x2 - x1)**2)
        
        if denom == 0:
            return math.sqrt((x - x1)**2 + (y - y1)**2)
        
        return nom / denom
    
    async def calculate_centroid(self, geometry: Dict[str, Any]) -> Optional[List[float]]:
        """
        Calculate centroid of a geometry.
        
        Args:
            geometry: Input geometry
            
        Returns:
            Optional[List[float]]: Centroid coordinates [X, Y] or None
        """
        if geometry.get("type") == "Point":
            return geometry.get("coordinates")
        elif geometry.get("type") == "Polygon":
            coords = geometry.get("coordinates", [])
            if coords and len(coords) > 0:
                ring = coords[0]  # Exterior ring
                if len(ring) >= 3:
                    # Calculate centroid using shoelace formula
                    cx = sum(p[0] for p in ring) / len(ring)
                    cy = sum(p[1] for p in ring) / len(ring)
                    return [cx, cy]
        elif geometry.get("type") == "MultiPolygon":
            # For multipolygon, return centroid of first polygon
            polygons = geometry.get("coordinates", [])
            if polygons and len(polygons) > 0:
                ring = polygons[0][0]  # First polygon, exterior ring
                if len(ring) >= 3:
                    cx = sum(p[0] for p in ring) / len(ring)
                    cy = sum(p[1] for p in ring) / len(ring)
                    return [cx, cy]
        
        return None
    
    async def calculate_area(self, geometry: Dict[str, Any]) -> float:
        """
        Calculate area of a polygon geometry.
        
        Args:
            geometry: Polygon geometry
            
        Returns:
            float: Calculated area
        """
        if geometry.get("type") == "Polygon":
            coords = geometry.get("coordinates", [])
            if coords and len(coords) > 0:
                ring = coords[0]  # Exterior ring
                if len(ring) >= 3:
                    # Calculate area using shoelace formula
                    n = len(ring)
                    area = 0.0
                    for i in range(n):
                        j = (i + 1) % n
                        area += ring[i][0] * ring[j][1]
                        area -= ring[j][0] * ring[i][1]
                    return abs(area) / 2.0
        
        return 0.0
    
    async def calculate_length(self, geometry: Dict[str, Any]) -> float:
        """
        Calculate length of a line geometry.
        
        Args:
            geometry: LineString geometry
            
        Returns:
            float: Calculated length
        """
        if geometry.get("type") == "LineString":
            coords = geometry.get("coordinates", [])
            if len(coords) >= 2:
                length = 0.0
                for i in range(len(coords) - 1):
                    dx = coords[i+1][0] - coords[i][0]
                    dy = coords[i+1][1] - coords[i][1]
                    dz = coords[i+1][2] - coords[i][2] if len(coords[i]) > 2 else 0
                    length += math.sqrt(dx*dx + dy*dy + dz*dz)
                return length
        
        return 0.0
    
    async def transform_for_gis_export(self, model_elements: List[Dict[str, Any]], 
                                     target_format: str = "geojson") -> Dict[str, Any]:
        """
        Transform model data for GIS export in specified format.
        
        Args:
            model_elements: Model elements to transform
            target_format: Target format ('geojson', 'shapefile', 'kml', etc.)
            
        Returns:
            Dict: Transformed data in target format
        """
        if target_format.lower() == "geojson":
            # Create GeoJSON FeatureCollection
            features = await self.transform_to_gis_format(model_elements)
            return {
                "type": "FeatureCollection",
                "features": features,
                "crs": {
                    "type": "name",
                    "properties": {
                        "name": "EPSG:4326"  # WGS84
                    }
                },
                "metadata": {
                    "generated_at": datetime.utcnow().isoformat(),
                    "source": "Revit Model",
                    "format": "GeoJSON"
                }
            }
        
        # For other formats, return appropriate structure
        return {
            "elements": model_elements,
            "format": target_format,
            "transformed_at": datetime.utcnow().isoformat()
        }
    
    async def _element_to_geometry(self, element: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a model element to geometry representation."""
        # This is a simplified implementation
        # In a real implementation, this would handle complex geometry conversion
        
        location = element.get('location')
        geometry = element.get('geometry')
        
        if location:
            # If location is available, create a point geometry
            return {
                "type": "Point",
                "coordinates": [location['x'], location['y'], location.get('z', 0)]
            }
        else:
            # Default to a point at origin if no location available
            return {
                "type": "Point",
                "coordinates": [0, 0, 0]
            }