#!/usr/bin/env python3
"""
Hybrid PDF Generator for FireAI Testing

Generates realistic fire alarm test drawings:
- Vector walls (CAD lines)
- Raster device symbols (PNG images)
- Scale bars (graphics)
- Text annotations (scale, room names)
- NFPA 170 symbols

Usage:
    python generate_hybrid_test_pdfs.py [--output-dir /path/to/output]
"""

import argparse
import math
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# =============================================================================
# CONFIGURATION
# =============================================================================

# Room dimensions (in mm, assuming 1:100 scale)
ROOM_SIZES = {
    "small_office": (3000, 4000),      # 3m x 4m = 30mm x 40mm at 1:100
    "large_office": (6000, 8000),      # 6m x 8m = 60mm x 80mm at 1:100
    "corridor": (1500, 20000),         # 1.5m x 20m = 15mm x 200mm at 1:100
    "lobby": (5000, 5000),             # 5m x 5m = 50mm x 50mm at 1:100
    "meeting_room": (4000, 6000),      # 4m x 6m = 40mm x 60mm at 1:100
    "storage": (3000, 3000),          # 3m x 3m = 30mm x 30mm at 1:100
}

# NFPA 170 device positions (in mm, from bottom-left of room)
DEVICE_POSITIONS = [
    # Smoke detectors (center of room for coverage)
    {"type": "smoke", "x_ratio": 0.5, "y_ratio": 0.5},
    # Heat detectors (near ceiling - closer to walls)
    {"type": "heat", "x_ratio": 0.25, "y_ratio": 0.25},
    {"type": "heat", "x_ratio": 0.75, "y_ratio": 0.75},
    # Pull stations (near doors)
    {"type": "pull", "x_ratio": 0.1, "y_ratio": 0.1},
    # Horn/strobe (typical ceiling mount)
    {"type": "horn", "x_ratio": 0.5, "y_ratio": 0.1},
]

# Scale: 1:100 means 1mm in PDF = 100mm in reality
SCALE = 100  # 1:100 scale


def create_simple_symbol_png(output_path: Path, symbol_type: str, size: int = 30) -> bool:
    """
    Create a simple symbol PNG using pure Python (no PIL依赖).
    This creates a minimalist symbol for testing.
    """
    try:
        # For testing, we'll use a simple approach
        # If PIL not available, create placeholder
        import subprocess
        
        # Try to create a simple colored square as symbol
        # This is a fallback - ideally we'd use PIL
        header = b'\x89PNG\r\n\x1a\n'
        
        # Check if we can use PIL
        try:
            from PIL import Image, ImageDraw
            img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            
            # Draw symbol based on type
            if symbol_type == "smoke":
                # Circle for smoke detector
                draw.ellipse([5, 5, size-5, size-5], outline='blue', width=2)
            elif symbol_type == "heat":
                # Triangle-ish for heat detector  
                draw.polygon([(size//2, 5), (size-5, size-5), (5, size-5)], outline='red', width=2)
            elif symbol_type == "pull":
                # Rectangle for pull station
                draw.rectangle([10, 10, size-10, size-10], outline='green', width=2)
            elif symbol_type == "horn":
                # Diamond shape for horn/strobe
                draw.polygon([(size//2, 5), (size-5, size//2), (size//2, size-5), (5, size//2)], 
                          outline='orange', width=2)
            
            img.save(output_path)
            return True
        except ImportError:
            # PIL not available - create text file marker
            with open(output_path.with_suffix('.txt'), 'w') as f:
                f.write(f"SYMBOL:{symbol_type}\nSIZE:{size}")
            return False
            
    except Exception as e:
        print(f"Error creating symbol {symbol_type}: {e}")
        return False


def generate_vector_walls(msp, room_name: str, x_offset: int = 0, y_offset: int = 0):
    """Add vector walls to DXF modelspace."""
    if room_name not in ROOM_SIZES:
        return
    
    width, height = ROOM_SIZES[room_name]
    
    # Convert to DXF units (1 unit = 1mm at 1:1 scale)
    # For PDF at 1:100, we divide by 100
    w_scaled = width / SCALE
    h_scaled = height / SCALE
    
    # Add walls as lines
    points = [
        ((x_offset, y_offset), (x_offset + w_scaled, y_offset)),  # Bottom
        ((x_offset + w_scaled, y_offset), (x_offset + w_scaled, y_offset + h_scaled)),  # Right
        ((x_offset + w_scaled, y_offset + h_scaled), (x_offset, y_offset + h_scaled)),  # Top
        ((x_offset, y_offset + h_scaled), (x_offset, y_offset)),  # Left
    ]
    
    for start, end in points:
        msp.add_line(start, end, dxfattribs={'layer': 'WALLS'})


def generate_room_label(dwg, text: str, x: float, y: float):
    """Add room name text."""
    # Add text (mtext for multi-line)
    dwg.add_text(
        text,
        dxfattribs={
            'layer': 'TEXT',
            'style': 'Standard',
        }
    ).set_placement((x, y), align=2)


def calculate_coverage(room_name: str) -> Dict:
    """Calculate NFPA 72 coverage for a room."""
    if room_name not in ROOM_SIZES:
        return {"area_m2": 0, "max_detectors": 0, "coverage_type": "unknown"}
    
    width, height = ROOM_SIZES[room_name]
    area_m2 = (width / 1000) * (height / 1000)  # Convert mm to m
    
    # NFPA 72 rules:
    # Smoke detectors: max 100m² per detector
    # Heat detectors: max 120m² per detector
    max_smoke = math.ceil(area_m2 / 100)
    max_heat = math.ceil(area_m2 / 120)
    
    return {
        "area_m2": round(area_m2, 2),
        "max_smoke_detectors": max_smoke,
        "max_heat_detectors": max_heat,
        "coverage_type": "standard",
    }


def create_test_dxf(output_path: Path, config: Dict) -> bool:
    """Create a test DXF file with walls and devices."""
    try:
        import ezdxf
        
        # Create new document
        doc = ezdxf.new('R2010')
        doc.layers.add('WALLS', color=7)   # White/black - walls
        doc.layers.add('DEVICES', color=1)    # Red - devices
        doc.layers.add('TEXT', color=7)      # White - text
        msp = doc.modelspace()
        
        # Generate rooms
        rooms = config.get("rooms", ["small_office"])
        x_offset = 0
        
        for i, room_name in enumerate(rooms):
            # Add walls
            generate_vector_walls(msp, room_name, x_offset, 0)
            
            # Add room label
            room_label = config.get("room_labels", ["Office"])[i] if i < len(config.get("room_labels", [])) else room_name
            generate_room_label(doc, msp, room_label, x_offset + 10, 10)
            
            # Calculate and add device positions
            width, height = ROOM_SIZES[room_name]
            w_scaled = width / SCALE
            h_scaled = height / SCALE
            
            for device in DEVICE_POSITIONS:
                dx = w_scaled * device["x_ratio"]
                dy = h_scaled * device["y_ratio"]
                
                # Add device symbol (as simple point for now)
                point = (x_offset + dx, dy)
                msp.add_circle(point, radius=2, dxfattribs={'layer': 'DEVICES'})
            
            # Add coverage info text
            coverage = calculate_coverage(room_name)
            coverage_text = f"A:{coverage['area_m2']}m2 S:{coverage['max_smoke_detectors']}"
            msp.add_text(coverage_text, dxfattribs={'layer': 'TEXT'}).set_placement(
                (x_offset + w_scaled - 30, h_scaled + 5)
            )
            
            x_offset += w_scaled + 20  # Add gap between rooms
        
        # Add title block
        msp.add_text(
            f"FireAI Test - {config.get('name', 'Test Drawing')}",
            dxfattribs={'layer': 'TEXT'}
        ).set_placement((10, -20))
        
        msp.add_text(
            f"Scale 1:{SCALE}",
            dxfattribs={'layer': 'TEXT'}
        ).set_placement((10, -30))
        
        # Save
        doc.saveas(output_path)
        print(f"Created: {output_path}")
        return True
        
    except ImportError:
        print("Error: ezdxf not installed. Install with: pip install ezdxf")
        return False
    except Exception as e:
        print(f"Error creating DXF: {e}")
        import traceback
        traceback.print_exc()
        return False


def generate_room_label(doc, msp, text: str, x: float, y: float):
    """Add room name text."""
    from ezdxf.enums import TextEntityAlignment
    
    msp.add_text(
        text,
        dxfattribs={
            'layer': 'TEXT',
            'style': 'Standard',
        }
    ).set_placement((x, y), align=TextEntityAlignment.BOTTOM_CENTER)


def create_hybrid_pdf_with_reportlab(output_path: Path, config: Dict) -> bool:
    """
    Create a hybrid PDF using reportlab.
    
    Hybrid = Vector walls + Raster symbols + Scale bar + Text
    """
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        
        # Create PDF
        c = canvas.Canvas(str(output_path), pagesize=A4)
        width, height = A4
        
        # Draw title
        c.setFont("Helvetica-Bold", 14)
        c.drawString(20*mm, height - 20*mm, f"FireAI Test - {config.get('name', 'Test Drawing')}")
        
        # Draw scale
        c.setFont("Helvetica", 10)
        c.drawString(20*mm, height - 30*mm, f"Scale: 1:{SCALE}")
        
        # Draw north arrow
        c.setFont("Helvetica", 8)
        c.drawString(width - 30*mm, height - 25*mm, "N")
        c.line(width - 28*mm, height - 25*mm, width - 28*mm, height - 35*mm)
        c.line(width - 28*mm, height - 35*mm, width - 30*mm, height - 33*mm)
        c.line(width - 28*mm, height - 35*mm, width - 26*mm, height - 33*mm)
        
        # Draw rooms and walls
        rooms = config.get("rooms", ["small_office"])
        x_offset = 20*mm
        y_offset = height - 80*mm
        
        c.setLineWidth(2)
        c.setStrokeColorRGB(0, 0, 0)
        
        for i, room_name in enumerate(rooms):
            if room_name not in ROOM_SIZES:
                continue
            
            width, height_room = ROOM_SIZES[room_name]
            w_scaled = width / SCALE * mm
            h_scaled = height_room / SCALE * mm
            
            # Draw walls (vector)
            c.rect(x_offset, y_offset - h_scaled, w_scaled, h_scaled)
            
            # Room label
            c.setFont("Helvetica", 8)
            room_label = config.get("room_labels", ["Office"])[i] if i < len(config.get("room_labels", [])) else room_name
            c.drawString(x_offset + 5, y_offset - h_scaled + 5, room_label)
            
            # Add devices
            c.setLineWidth(1)
            for device in DEVICE_POSITIONS:
                dx = w_scaled * device["x_ratio"]
                dy = h_scaled * device["y_ratio"]
                
                # Draw symbol (simplified as circle)
                cx = x_offset + dx
                cy = y_offset - h_scaled + dy
                
                if device["type"] == "smoke":
                    c.setStrokeColorRGB(0, 0, 1)  # Blue
                    c.circle(cx, cy, 3, fill=0)
                elif device["type"] == "heat":
                    c.setStrokeColorRGB(1, 0, 0)  # Red
                    c.circle(cx, cy, 3, fill=0)
                elif device["type"] == "pull":
                    c.setStrokeColorRGB(0, 0.7, 0)  # Green
                    c.rect(cx-3, cy-3, 6, 6)
                elif device["type"] == "horn":
                    c.setStrokeColorRGB(1, 0.5, 0)  # Orange
                    c.circle(cx, cy, 3, fill=0)
            
            # Coverage info
            coverage = calculate_coverage(room_name)
            c.setFont("Helvetica", 6)
            info = f"Area: {coverage['area_m2']}m² | Max Smoke: {coverage['max_smoke_detectors']}"
            c.drawString(x_offset + 5, y_offset - h_scaled + 15, info)
            
            x_offset += w_scaled + 10*mm
        
        # Draw scale bar
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(1)
        scale_bar_length = 100*mm  # 100mm in PDF = 10m in reality at 1:100
        c.line(20*mm, 20*mm, 20*mm + scale_bar_length, 20*mm)
        c.line(20*mm, 15*mm, 20*mm, 25*mm)
        c.line(20*mm + scale_bar_length, 15*mm, 20*mm + scale_bar_length, 25*mm)
        c.setFont("Helvetica", 8)
        c.drawString(20*mm, 10*mm, "10m")
        
        # Save
        c.save()
        print(f"Created: {output_path}")
        return True
        
    except ImportError:
        print("Error: reportlab not installed. Install with: pip install reportlab")
        return False
    except Exception as e:
        print(f"Error creating PDF: {e}")
        return False


def generate_all_test_pdfs(output_dir: Path) -> Dict[str, bool]:
    """Generate all test configurations."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    configs = [
        {
            "name": "single_office",
            "rooms": ["small_office"],
            "room_labels": ["Office 1"],
        },
        {
            "name": "two_rooms",
            "rooms": ["small_office", "meeting_room"],
            "room_labels": ["Office", "Meeting"],
        },
        {
            "name": "corridor_rooms", 
            "rooms": ["corridor", "lobby", "small_office"],
            "room_labels": ["Corridor", "Lobby", "Office"],
        },
        {
            "name": "multi_floor_typical",
            "rooms": ["small_office", "small_office", "meeting_room", "storage"],
            "room_labels": ["Office A", "Office B", "Meeting", "Storage"],
        },
    ]
    
    results = {}
    
    for config in configs:
        # Try DXF first
        dxf_path = output_dir / f"{config['name']}.dxf"
        results[dxf_path.name] = create_test_dxf(dxf_path, config)
        
        # Then PDF
        pdf_path = output_dir / f"{config['name']}.pdf"
        results[pdf_path.name] = create_hybrid_pdf_with_reportlab(pdf_path, config)
    
    return results


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate hybrid fire alarm test PDFs for FireAI testing"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./test_data/hybrid",
        help="Output directory for generated files",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["dxf", "pdf", "both"],
        default="both",
        help="Output format",
    )
    parser.add_argument(
        "--list-rooms",
        action="store_true",
        help="List available room configurations",
    )
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    
    print("="*60)
    print("FireAI Hybrid PDF Generator")
    print("="*60)
    
    if args.list_rooms:
        print("\nAvailable room configurations:")
        for name, (w, h) in ROOM_SIZES.items():
            area_m2 = (w/1000) * (h/1000)
            print(f"  {name}: {w}mm x {h}mm = {area_m2:.1f}m²")
        return
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nOutput directory: {output_dir}")
    
    # Generate files
    print("\nGenerating test files...")
    results = generate_all_test_pdfs(output_dir)
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    success = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"Generated: {success}/{total} files successfully")
    
    print("\nFiles created:")
    for filename, status in results.items():
        status_str = "✓" if status else "✗"
        print(f"  {status_str} {filename}")


if __name__ == "__main__":
    main()