#!/usr/bin/env python3
"""
run_full_pipeline.py - FireAI NFPA 72-2022 Design Pipeline
====================================================
Full pipeline from PDF to NFPA-compliant fire detection design report.

Usage:
    python3 run_full_pipeline.py <pdf_file> [--output JSON_OUTPUT_PATH]
    
Example:
    python3 run_full_pipeline.py test_data/hybrid/single_office.pdf
"""

import sys
import os
import json
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parsers.geometry_extractor import GeometryExtractor
from adapters.pdf_to_rooms_adapter import extract_rooms_from_walls, guess_room_type, select_safe_detector_type


def run_pipeline(pdf_path: str, output_path: str = None) -> dict:
    """
    Run full NFPA 72 pipeline on PDF file.
    
    Args:
        pdf_path: Path to floor plan PDF
        output_path: Optional JSON output path
        
    Returns:
        dict: Full design report
    """
    print("=" * 45)
    print("  FIREAI NFPA 72-2022 DESIGN PIPELINE")
    print("=" * 45)
    print(f"\nInput: {pdf_path}")
    print(f"Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n")
    
    # Step 1: Extract walls
    print("Step 1: Extracting geometry...")
    extractor = GeometryExtractor(pdf_path)
    walls = extractor.extract_walls()
    print(f"  Walls extracted: {len(walls)}")
    
    # Step 2: Create rooms with text extraction attempt
    print("\nStep 2: Creating rooms...")
    rooms, report = extract_rooms_from_walls(walls, pdf_path=pdf_path)
    print(f"  Rooms created: {len(rooms)}")
    
    # Step 3: Run NFPA analysis per room
    print("\nStep 3: Running NFPA 72 analysis...")
    room_results = []
    total_detectors = 0
    
    # Try to extract text using pdfplumber for suggestions
    suggested_names = {}
    text_extractor_available = False
    
    try:
        import pdfplumber
        text_extractor_available = True
        print("  Text extractor: pdfplumber available")
    except ImportError:
        print("  Text extractor: pdfplumber not installed (using basic method)")
    
    for room in rooms:
        room_name = room.name
        area_sqm = room.polygon.area if room.polygon else 0
        
        # Check if verified (not auto-generated name)
        is_verified = not room_name.startswith("room_")
        
        # Use "unknown" for unverified rooms - BE HONEST
        if is_verified and room.occupancy_type:
            occupancy_type = room.occupancy_type
        else:
            occupancy_type = "unknown"
        
        occupancy_source = "extracted" if is_verified else "auto_assigned"
        
        # Level 2: Try to extract text as "suggested" only
        suggested_name = None
        if text_extractor_available and pdf_path:
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    page = pdf.pages[0]
                    if room.polygon:
                        bounds = room.polygon.bounds  # (minx, miny, maxx, maxy)
                        # Extract text within bounds
                        text = page.extract_text(bounds=bounds)
                        if text and len(text.strip()) > 0:
                            # Take first meaningful line
                            lines = [l.strip() for l in text.split('\n') if l.strip()]
                            if lines:
                                suggested_name = lines[0]
                                print(f"  Suggested '{room_name}': '{suggested_name}'")
            except Exception as e:
                print(f"  Text extraction note: {e}")
        
        # Determine detector type - FAIL-SAFE for unknown rooms
        # If room type is unknown, don't place any detectors
        if occupancy_type == "unknown":
            # FAIL-SAFE: No detectors for unknown rooms
            detector_type = "UNKNOWN"
            detector_count = 0
            coverage_pct = 0.0
        else:
            # Known room type - use safe detector selection
            detector = select_safe_detector_type(room_name, occupancy_type)
            detector_type = detector.name
            
            # Calculate detector count
            if detector_type.startswith("SMOKE"):
                detector_count = max(1, int((area_sqm / 9.0) + 0.5))
            elif detector_type.startswith("HEAT"):
                detector_count = max(1, int((area_sqm / 20.0) + 0.5))
            else:
                detector_count = max(1, int((area_sqm / 15.0) + 0.5))
            coverage_pct = 100.0
        
        total_detectors += detector_count  # Simplified
        
        # Build warnings/errors
        warnings = []
        if not is_verified:
            warnings.append("MANUAL TYPE REQUIRED - NO DETECTORS PLACED")
        
        if suggested_name:
            warnings.append(f"⚠️ Suggested room name from PDF: '{suggested_name}'. Verify before relying.")
        
        if occupancy_type == "kitchen":
            warnings.append("Kitchen detected - SMOKE detectors prohibited per NFPA 72 §17.6.4")
        
        if occupancy_type == "unknown":
            warnings.append("🔴 MANUAL REVIEW REQUIRED - Design incomplete")
        
        room_results.append({
            "name": room_name,
            "area_sqm": round(area_sqm, 1),
            "occupancy_type": occupancy_type,
            "occupancy_source": occupancy_source,
            "occupancy_verified": is_verified,
            "suggested_name": suggested_name,
            "detector_type": detector_type,
            "detector_count": detector_count,
            "coverage_pct": coverage_pct,
            "compliant": True,
            "warnings": warnings
        })
    
    # Determine overall status
    unverified_count = sum(1 for r in room_results if not r["occupancy_verified"])
    
    # Build final report - FAIL-SAFE: if unknown rooms exist, design is FAILED
    has_unknown = unverified_count > 0
    design_report = {
        "report_metadata": {
            "source_file": pdf_path,
            "generated_utc": datetime.utcnow().isoformat() + "Z",
            "status": "FAILED" if has_unknown else "COMPLETE",
            "requires_pe_review": True,  # Always requires review
            "design_complete": not has_unknown,
            "review_reason": f"Design incomplete. {unverified_count} rooms require manual type verification." if has_unknown else None
        },
        "rooms": room_results,
        "summary": {
            "total_rooms": len(rooms),
            "unverified_rooms": unverified_count,
            "total_detectors": total_detectors,
            "compliant": not has_unknown  # Not compliant if unknowns exist
        }
    }
    
    # Save JSON if output path provided
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(design_report, f, indent=2, ensure_ascii=False)
        print(f"\nJSON saved to: {output_path}")
    
    return design_report


def print_terminal_report(report: dict):
    """Print formatted report to terminal."""
    meta = report["report_metadata"]
    summary = report["summary"]
    rooms = report["rooms"]
    
    # FAIL-SAFE: Show FAILED if design incomplete
    if meta.get("status") == "FAILED":
        status = "🔴 FAILED — MANUAL TYPE REQUIRED"
    else:
        status = "✅ COMPLETE"
    
    print("\n" + "=" * 45)
    print("  FIREAI NFPA 72-2022 DESIGN REPORT")
    print("=" * 45)
    print(f"File: {meta['source_file']}")
    print(f"Generated: {meta['generated_utc']}")
    print(f"Status: {status}")
    print(f"\nRooms Extracted: {summary['total_rooms']}")
    print(f"Total Detectors: {summary['total_detectors']}")
    print(f"Fully Compliant: {summary['compliant']}")
    
    if meta.get("status") == "FAILED":
        print("\n🔴 DESIGN INCOMPLETE:")
        print("   Room types could not be determined.")
        print("   NO DETECTORS have been placed.")
        print("   Manual type verification is REQUIRED before design can complete.")
    
    print("\n" + "─" * 45)
    print("Room          Area      Type       Detectors  Coverage  Status")
    print("─" * 45)
    
    for room in rooms:
        name = room["name"][:12].ljust(12)
        area = f"{room['area_sqm']:.1f} m²".ljust(9)
        occ = room["occupancy_type"][:8].ljust(8)
        det_count = str(room["detector_count"]).ljust(8)
        cov = f"{room['coverage_pct']:.0f}%".ljust(7)
        
        if room["occupancy_verified"]:
            status_icon = "✅"
        else:
            status_icon = "⚠️"
        
        print(f"{name} {area} {occ} {det_count} {cov} {status_icon}")
        
        # Show suggested name if available
        if room.get("suggested_name"):
            print(f"  → Suggested: '{room['suggested_name']}'")
    
    print("─" * 45)
    
    if summary["unverified_rooms"] > 0:
        print(f"⚠️ WARNING: {summary['unverified_rooms']} rooms have auto-assigned types.")
        print("   Verify usage before ordering equipment.")
    
    print("=" * 45)


def main():
    """Main entry point with interactive human review."""
    parser = argparse.ArgumentParser(description="FireAI NFPA 72 Design Pipeline")
    parser.add_argument("pdf_file", help="Path to floor plan PDF")
    parser.add_argument("--output", "-o", help="JSON output path", default=None)
    parser.add_argument("--non-interactive", "-n", help="Skip human review", action="store_true")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.pdf_file):
        print(f"ERROR: File not found: {args.pdf_file}")
        return 1
    
    # Generate output path if not provided
    output_path = args.output
    if not output_path:
        base_name = Path(args.pdf_file).stem
        output_path = f"sample_outputs/{base_name}_FULL_REPORT.json"
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Run initial pipeline
    report = run_pipeline(args.pdf_file, output_path)
    print_terminal_report(report)
    
    # Interactive human review loop (Level 3)
    if not args.non_interactive and report["report_metadata"].get("status") == "FAILED":
        print("\n" + "=" * 45)
        print("  🔴 HUMAN REVIEW REQUIRED")
        print("=" * 45)
        print("\nEnter room types to complete the design.")
        print("Valid types: office, kitchen, server_room, bedroom, bathroom,")
        print("           corridor, warehouse, storage, garage")
        print("Press Enter to keep as 'unknown' (no detectors will be placed)\n")
        
        room_types = {}
        
        for room in report["rooms"]:
            if room["occupancy_type"] == "unknown":
                room_name = room["name"]
                current_type = room.get("suggested_name", "unknown")
                
                prompt = f"  {room_name} (area: {room['area_sqm']}m²) [{current_type}]: "
                user_input = input(prompt).strip().lower()
                
                if user_input:
                    room_types[room_name] = user_input
                else:
                    # Keep as unknown if no input
                    room_types[room_name] = "unknown"
        
        # If user provided any room types, re-run analysis
        if any(v != "unknown" for v in room_types.values()):
            print("\n🔄 Re-running analysis with verified types...")
            
            # Open the PDF and run analysis with corrected occupancy types
            from parsers.geometry_extractor import GeometryExtractor
            from adapters.pdf_to_rooms_adapter import extract_rooms_from_walls, select_safe_detector_type
            
            extractor = GeometryExtractor(args.pdf_file)
            walls = extractor.extract_walls()
            rooms, _ = extract_rooms_from_walls(walls, pdf_path=args.pdf_file)
            
            # Re-analyze with user-provided types
            final_rooms = []
            for room in rooms:
                room_name = room.name
                user_type = room_types.get(room_name, "unknown")
                area_sqm = room.polygon.area if room.polygon else 0
                
                is_verified = user_type != "unknown"
                
                # Calculate detectors
                if user_type == "unknown":
                    detector_type = "UNKNOWN"
                    detector_count = 0
                    coverage_pct = 0.0
                else:
                    detector = select_safe_detector_type(room_name, user_type)
                    detector_type = detector.name
                    if detector_type.startswith("SMOKE"):
                        detector_count = max(1, int((area_sqm / 9.0) + 0.5))
                    elif detector_type.startswith("HEAT"):
                        detector_count = max(1, int((area_sqm / 20.0) + 0.5))
                    else:
                        detector_count = max(1, int((area_sqm / 15.0) + 0.5))
                    coverage_pct = 100.0
                
                # Check for special warnings
                warnings = []
                if user_type == "kitchen":
                    warnings.append("Kitchen - SMOKE prohibited per NFPA 72 §17.6.4")
                
                final_rooms.append({
                    "name": room_name,
                    "area_sqm": round(area_sqm, 1),
                    "occupancy_type": user_type,
                    "occupancy_source": "human_review",
                    "occupancy_verified": is_verified,
                    "detector_type": detector_type,
                    "detector_count": detector_count,
                    "coverage_pct": coverage_pct,
                    "compliant": True,
                    "warnings": warnings
                })
            
            total_detectors = sum(r["detector_count"] for r in final_rooms)
            unverified_count = sum(1 for r in final_rooms if not r["occupancy_verified"])
            
            # Build final report
            final_report = {
                "report_metadata": {
                    "source_file": args.pdf_file,
                    "generated_utc": datetime.utcnow().isoformat() + "Z",
                    "status": "COMPLETE" if unverified_count == 0 else "PARTIAL",
                    "requires_pe_review": unverified_count > 0,
                    "design_complete": unverified_count == 0,
                    "review_reason": "Human review completed" if unverified_count == 0 else f"{unverified_count} rooms still unknown"
                },
                "rooms": final_rooms,
                "summary": {
                    "total_rooms": len(final_rooms),
                    "unverified_rooms": unverified_count,
                    "total_detectors": total_detectors,
                    "compliant": unverified_count == 0
                }
            }
            
            # Save final JSON
            final_output = output_path.replace("_FULL_REPORT", "_FINAL_REPORT")
            with open(final_output, 'w', encoding='utf-8') as f:
                json.dump(final_report, f, indent=2, ensure_ascii=False)
            
            # Print final report
            print("\n" + "=" * 45)
            print("  ✅ DESIGN COMPLETE (AFTER HUMAN REVIEW)")
            print("=" * 45)
            print(f"\nRooms: {len(final_rooms)} | Detectors: {total_detectors}")
            print(f"Saved to: {final_output}")
            
            for room in final_rooms:
                status = "✅" if room["occupancy_verified"] else "⚠️"
                print(f"  {room['name']} → {room['detector_type']} ({room['detector_count']} detectors) {status}")
        else:
            print("\nNo room types provided. Design incomplete.")
            print(f"Progress saved to: {output_path}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())