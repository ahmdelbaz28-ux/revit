"""
ReverseScaleEstimator - Estimate scale from known room dimensions
====================================================

If we know ONE room's actual area from the drawing text,
we can calculate the scale in reverse.

Example:
- Drawing shows room labeled "12' x 15' = 180 SF"
- On image, room measures 1000 pixels x 1250 pixels
- Scale = 1000px / 12ft = 83.3 px/ft = 1000 px/m

This turns "REJECT" into "CAUTION with estimated scale".
"""

import re
import cv2
import numpy as np
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple
from pdf2image import convert_from_path


@dataclass
class ReverseScaleResult:
    """Result from reverse scale estimation."""
    found: bool
    meters_per_unit: Optional[float]
    confidence: float
    method: str
    evidence: Dict  # What we based the calculation on


class ReverseScaleEstimator:
    """
    Estimate scale by finding known dimensions in the drawing.
    
    Searches for:
    - Room dimensions with area (e.g., "12' x 15' = 180 SF")
    - Dimension annotations (e.g., "10'-0"")
    - Scale bars (if text visible)
    """
    
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
    
    def _extract_text_with_positions(self) -> List[Dict]:
        """Extract text and their positions from PDF."""
        import fitz
        text_items = []
        
        doc = fitz.open(self.pdf_path)
        for page_num, page in enumerate(doc):
            # Get text with rectangles
            dict_items = page.get_text("dict")
            for block in dict_items.get("blocks", []):
                if block.get("type") == 0:  # Text block
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            text = span.get("text", "").strip()
                            if text:
                                bbox = span.get("bbox", [0,0,0,0])
                                text_items.append({
                                    'text': text,
                                    'bbox': bbox,
                                    'page': page_num,
                                    'x': bbox[0],
                                    'y': bbox[1],
                                })
        
        return text_items
    
    def _parse_dimension_text(self, text: str) -> Optional[Dict]:
        """
        Parse dimension text like:
        - "12' x 15'" 
        - "10'-0""
        - "12 x 15 = 180 SF"
        - "12' x 15' = 180"
        """
        # Pattern 1: "12' x 15' = 180 SF"
        match = re.search(
            r"(\d+)'?\s*[xX]\s*(\d+)'?\s*=?\s*(\d+)\s*(?:SF|sf|sq\.?\s*ft\.?)?",
            text
        )
        if match:
            dim1, dim2, area = int(match.group(1)), int(match.group(2)), int(match.group(3))
            return {
                'width_ft': dim1,
                'height_ft': dim2,
                'area_sf': area,
                'type': 'area_calculated'
            }
        
        # Pattern 2: "12' x 15'"
        match = re.search(r"(\d+)'?\s*[xX]\s*(\d+)'?", text)
        if match:
            return {
                'width_ft': int(match.group(1)),
                'height_ft': int(match.group(2)),
                'area_sf': None,
                'type': 'dimensions_only'
            }
        
        # Pattern 3: "10'-0"" (single dimension)
        match = re.search(r"(\d+)'-\d+\"?", text)
        if match:
            return {
                'width_ft': int(match.group(1)),
                'height_ft': None,
                'area_sf': None,
                'type': 'single_dimension'
            }
        
        return None
    
    def _estimate_pixel_dimensions(self, bbox: Tuple, dpi: int = 300) -> Dict:
        """Convert bbox to pixel dimensions."""
        x1, y1, x2, y2 = bbox
        width_px = x2 - x1
        height_px = y2 - y1
        return {'width_px': width_px, 'height_px': height_px}
    
    def _find_rooms_with_dimensions(self, text_items: List[Dict]) -> List[Dict]:
        """Find rooms that have dimension annotations near them."""
        rooms = []
        
        for i, item in enumerate(text_items):
            parsed = self._parse_dimension_text(item['text'])
            if parsed:
                # This text has dimension info
                rooms.append({
                    **item,
                    **parsed,
                    **self._estimate_pixel_dimensions(item['bbox'])
                })
        
        return rooms
    
    def _calculate_scale(self, room_info: Dict, estimated_area_pixels: float) -> Optional[float]:
        """Calculate scale from room info."""
        if room_info.get('area_sf'):
            # We know actual area
            area_sf = room_info['area_sf']
            # Convert to meters
            area_m = area_sf * 0.092903
            
            # If we can estimate image area
            # For a typical room shown in a typical drawing
            # Assume room takes ~20% of image height
            # This is a rough estimate
            
            # Better: use dimension ratio
            if room_info.get('width_ft') and room_info.get('height_ft'):
                width_ft = room_info['width_ft']
                height_ft = room_info['height_ft']
                
                # Get pixel dimensions from bbox
                width_px = room_info.get('width_px', 0)
                height_px = room_info.get('height_px', 0)
                
                if width_px > 0 and height_px > 0:
                    # Scale = pixels per foot
                    scale_x = width_px / width_ft
                    scale_y = height_px / height_ft
                    
                    # Average if both available
                    if scale_x > 0 and scale_y > 0:
                        scale = (scale_x + scale_y) / 2
                        # Convert to meters per unit
                        meters_per_foot = 0.3048  # feet to meters
                        return scale * meters_per_foot
        
        return None
    
    def estimate(self) -> ReverseScaleResult:
        """
        Main estimation: find at least one dimension and calculate scale.
        
        Returns ReverseScaleResult with estimated scale.
        """
        # 1. Extract text with positions
        try:
            text_items = self._extract_text_with_positions()
        except Exception as e:
            return ReverseScaleResult(
                found=False,
                meters_per_unit=None,
                confidence=0.0,
                method="text_extraction_failed",
                evidence={'error': str(e)}
            )
        
        # 2. Find rooms with dimensions
        rooms = self._find_rooms_with_dimensions(text_items)
        
        if not rooms:
            return ReverseScaleResult(
                found=False,
                meters_per_unit=None,
                confidence=0.0,
                method="no_dimensions_found",
                evidence={'text_items_checked': len(text_items)}
            )
        
        # 3. Try to calculate scale from each room
        for room in rooms:
            scale = self._calculate_scale(room, 0)  # simplified
            if scale and scale > 0.1 and scale < 10:  # reasonable range
                return ReverseScaleResult(
                    found=True,
                    meters_per_unit=scale,
                    confidence=0.6,  # Lower confidence - estimation
                    method="room_dimensions",
                    evidence={
                        'text': room['text'],
                        'dims': {
                            'width': room.get('width_ft'),
                            'height': room.get('height_ft')
                        }
                    }
                )
        
        # If we found dimensions but couldn't calculate
        return ReverseScaleResult(
            found=False,
            meters_per_unit=None,
            confidence=0.0,
            method="dimensions_found_but_cannot_calculate",
            evidence={'rooms_found': len(rooms)}
        )


def estimate_reverse_scale(pdf_path: str) -> ReverseScaleResult:
    """Convenience function."""
    estimator = ReverseScaleEstimator(pdf_path)
    return estimator.estimate()


# Alternative: Simple estimation from overall document
def quick_scale_estimate(pdf_path: str, known_room_area_sf: float = None) -> Optional[float]:
    """
    Quick scale estimation with known room area.
    
    If you know ONE room's area from the drawing:
    - Pass known_room_area_sf (e.g., 180 for 12x15 room)
    
    Returns estimated scale in meters per unit.
    """
    if not known_room_area_sf:
        return None
    
    # This would require measuring the room on the image
    # For now, return a placeholder that requires manual measurement
    
    return None