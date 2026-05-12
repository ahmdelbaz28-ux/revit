#!/usr/bin/env python3
"""
DXF Parser for FireAI
Parses AutoCAD DXF/DWG files and extracts room polygons for fire alarm design.

Supports:
- Clean DXF files
- Corrupted layers (adds to manual_review queue)
- Broken polylines (reports error, continues)
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Manual review queue (rooms that need manual intervention)
manual_review_rooms: List[Dict[str, str]] = []


class DXFParser:
    """Parser for DXF/DWG files."""

    def __init__(self):
        self.rooms = []
        self.errors = []

    def parse(self, input_file: str) -> Dict[str, Any]:
        """
        Parse DXF file and extract rooms.
        
        Returns:
            {
                "rooms": [...],
                "manual_review": [...],  # Rooms needing manual review
                "errors": [...]  # Parse errors
            }
        """
        input_path = Path(input_file)
        
        if not input_path.exists():
            logger.error(f"File not found: {input_file}")
            return {"rooms": [], "manual_review": [], "errors": ["File not found"]}
        
        # Try to parse DXF
        try:
            # Check for ezdxf
            try:
                import ezdxf
                logger.info(f"Using ezdxf library for {input_file}")
                rooms = self._parse_with_ezdxf(input_path)
            except ImportError:
                logger.warning("ezdxf not installed, using fallback")
                rooms = self._parse_fallback(input_path)
            
            # Add rooms that failed to manual_review
            for room in self.errors:
                manual_review_rooms.append({
                    "name": room.get("name", "unknown"),
                    "reason": "DXF polyline broken / layer corrupted",
                    "suggestion": "Redraw room boundary manually or fix DXF layer",
                    "error": str(room.get("error", "Unknown error"))[:200]
                })
            
            return {
                "rooms": rooms,
                "manual_review": manual_review_rooms,
                "errors": [r.get("error", "") for r in self.errors if r.get("error")]
            }
            
        except Exception as e:
            logger.error(f"Failed to parse {input_file}: {e}")
            return {
                "rooms": [],
                "manual_review": manual_review_rooms,
                "errors": [str(e)]
            }

    def _parse_with_ezdxf(self, path: Path) -> List[Dict]:
        """Parse using ezdxf library."""
        try:
            import ezdxf
            doc = ezdxf.readfile(str(path))
            
            rooms = []
            # Extract POLYLINEs from ROOMS layer
            msp = doc.modelspace()
            
            # Find room polylines
            for entity in msp.query('LWPOLYLINE[layer=="ROOMS"'):
                try:
                    # Get vertices
                    points = list(entity.get_points())
                    if len(points) >= 3:
                        room = {
                            "name": f"Room_{len(rooms)+1}",
                            "polygon": [[float(p.dxf.x), float(p.dxf.y)] for p in points],
                            "layer": "ROOMS"
                        }
                        rooms.append(room)
                except Exception as e:
                    self.errors.append({
                        "name": getattr(entity, 'dxf', {}).get('layer', 'unknown'),
                        "error": str(e)
                    })
                    logger.warning(f"Failed to parse polyline: {e}")
            
            # If no ROOMS layer, try any LWPOLYLINE
            if not rooms:
                for entity in msp.query('LWPOLYLINE'):
                    try:
                        points = list(entity.get_points())
                        if len(points) >= 3:
                            room = {
                                "name": f"Room_{len(rooms)+1}",
                                "polygon": [[float(p.dxf.x), float(p.dxf.y)] for p in points]
                            }
                            rooms.append(room)
                    except Exception:
                        pass
            
            logger.info(f"Parsed {len(rooms)} rooms from {path.name}")
            return rooms
            
        except Exception as e:
            logger.error(f"ezdxf parse error: {e}")
            raise

    def _parse_fallback(self, path: Path) -> List[Dict]:
        """Fallback when ezdxf not available."""
        logger.warning(f"No DXF parser available for {path.name}")
        logger.info("Rooms must be provided as JSON, not DXF")
        return []


def main():
    parser = argparse.ArgumentParser(description="Parse DXF/DWG for FireAI")
    parser.add_argument("--input", "-i", required=True, help="Input DXF/DWG file")
    parser.add_argument("--output", "-o", help="Output JSON file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Parse
    dxfr = DXFParser()
    result = dxfr.parse(args.input)
    
    # Print results
    print(f"\n{'='*60}")
    print("DXF PARSE RESULTS")
    print(f"{'='*60}")
    print(f"Rooms parsed: {len(result['rooms'])}")
    print(f"Rooms needing manual review: {len(result['manual_review'])}")
    print(f"Errors: {len(result['errors'])}")
    
    if result['manual_review']:
        print(f"\n⚠️  ROOMS REQUIRING MANUAL REVIEW:")
        for room in result['manual_review']:
            print(f"  ❌ {room['name']}")
            print(f"     Reason: {room['reason']}")
            print(f"     Suggestion: {room['suggestion']}")
            print()
    
    if result['errors']:
        print(f"\n❌ ERRORS:")
        for err in result['errors']:
            print(f"  - {err}")
    
    # Save output
    if args.output and result['rooms']:
        output_data = {
            "rooms": result['rooms'],
            "manual_review": result['manual_review'],
            "errors": result['errors']
        }
        with open(args.output, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"\n✅ Saved to {args.output}")
    
    # Exit code
    if result['manual_review']:
        sys.exit(1)  # Has issues
    sys.exit(0)


if __name__ == "__main__":
    main()
