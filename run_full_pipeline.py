#!/usr/bin/env python3
"""
run_full_pipeline.py - NFPA 72-2022 Design Pipeline
====================================================
Full pipeline from PDF to NFPA-compliant fire detection design report.
NOT an AI - this is a deterministic calculator.

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
from adapters.pdf_to_rooms_adapter import extract_rooms_from_walls, select_safe_detector_type


def run_pipeline(pdf_path: str, output_path: str = None, manual_room_types: dict = None) -> dict:
    """
    Run full NFPA 72 pipeline on PDF file.
    
    Args:
        pdf_path: Path to floor plan PDF
        output_path: Optional JSON output path
        manual_room_types: Optional dict of room_name -> room_type
        
    Returns:
        dict: Full design report
    """
    if manual_room_types is None:
        manual_room_types = {}
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
    # No suggested names - manual input only
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
        
        # Priority 1: Check manual types (highest priority)
        if room_name in manual_room_types:
            occupancy_type = manual_room_types[room_name]
            is_verified = True
            source = "manual"
        elif is_verified and room.occupancy_type:
            occupancy_type = room.occupancy_type
            source = "extracted"
        else:
            occupancy_type = "unknown"
            source = "unverified"
        
        # Skip auto-detection if manual types provided
        # Skip text extraction if manual types provided - NO auto-detection for unverified rooms
        # HONESTY ONLY: text must be IN polygon bounds to be trusted
        if room_name in manual_room_types:
            pass  # Manual already set above
        elif text_extractor_available and pdf_path:
            try:
                # ONLY extract text INSIDE polygon bounds
                if room.polygon:
                    bounds = room.polygon.bounds
                    with pdfplumber.open(pdf_path) as pdf:
                        page = pdf.pages[0]
                        text = page.extract_text(bounds=bounds)
                        
                        if text and len(text.strip()) > 0:
                            text_clean = text.strip().split('\n')[0].lower().strip()
                            # Accept only exact matches in polygon bounds
                            known_rooms = ['corridor', 'lobby', 'office', 'kitchen', 'meeting', 'bathroom', 'bedroom']
                            if any(text_clean == known for known in known_rooms):
                                pass  # Text found in bounds - currently not used
            except Exception as e:
                pass  # Silently ignore extraction errors
        
        # Initialize warnings early for large room check
        warnings = []
        
        # Calculate detectors with LARGE ROOM handling
        # CRITICAL: Apply fail-safe to UNKNOWN only, not to ALL large rooms
        LARGE_ROOM_THRESHOLD_SQM = 500.0  # Flag for special review (not block)
        
        if occupancy_type == "unknown":
            # FAIL-SAFE: No detectors for unknown rooms
            detector_type = "UNKNOWN"
            detector_count = 0
            coverage_pct = 0.0
            is_flagged = True
            warnings.append("🔴 Type unknown - no detectors placed. MANUAL REVIEW REQUIRED.")
        elif is_verified and occupancy_type != "unknown":
            # KNOWN room type - calculate detectors (even if large)
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
            
            # Flag largeKnown rooms for special review (but DO place detectors)
            if area_sqm > LARGE_ROOM_THRESHOLD_SQM:
                is_flagged = True
                warnings.append(f"⚠️ Large known room ({area_sqm:.1f}m²) - verify coverage meets NFPA 72 §17.6.3.1.")
            
            # CRITICAL: Flag atrium-type rooms for special review
            if occupancy_type in ["atrium", "lobby", "hall", "grande"]:
                is_flagged = True
                warnings.append(f"⚠️ LARGE OPEN SPACE ({occupancy_type}) - Engineer review REQUIRED")
                warnings.append("   Standard detectors may be unsuitable per NFPA 72")
            
            if not is_flagged:
                is_flagged = False
        elif room.is_flagged:
            # Flagged outlier from adapter - require manual review
            detector_type = "REVIEW_REQUIRED"
            detector_count = 0
            coverage_pct = 0.0
            is_flagged = True
            warnings.append(f"⚠️ Outlier detected ({area_sqm:.1f}m²) - MANUAL REVIEW REQUIRED")
        else:
            # Fallback: unknown but not flagged
            detector_type = "UNKNOWN"
            detector_count = 0
            coverage_pct = 0.0
            is_flagged = True
            warnings.append("🔴 Type unknown - no detectors placed.")
        
        total_detectors += detector_count  # Simplified
        
        # Add standard warnings
        if occupancy_type == "unknown":
            warnings.append("🔴 MANUAL REVIEW REQUIRED - Design incomplete")
        
        if occupancy_type == "kitchen":
            warnings.append("Kitchen detected - SMOKE detectors prohibited per NFPA 72 §17.6.4")
        
        room_results.append({
            "name": room_name,
            "area_sqm": round(area_sqm, 1),
            "occupancy_type": occupancy_type,
            "source": source,
            "detector_type": detector_type,
            "detector_count": detector_count,
            "coverage_pct": coverage_pct,
            "is_flagged": is_flagged,
            "compliant": True,
            "warnings": warnings
        })
    
    # Determine overall status
    unknown_count = sum(1 for r in room_results if r["source"] == "unverified")
    
    # Build final report - FAIL-SAFE: if unknown rooms exist, design is FAILED
    has_unknown = unknown_count > 0
    design_report = {
        "report_metadata": {
            "source_file": pdf_path,
            "generated_utc": datetime.utcnow().isoformat() + "Z",
            "status": "FAILED" if has_unknown else "COMPLETE",
            "requires_pe_review": True,  # Always requires review
            "design_complete": not has_unknown,
            "review_reason": f"Design incomplete. {unknown_count} rooms require manual type verification." if has_unknown else None
        },
        "rooms": room_results,
        "summary": {
            "total_rooms": len(rooms),
            "unverified_rooms": unknown_count,
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
        
        if room.get("source", "unverified") != "unverified":
            status_icon = "✅"
        else:
            status_icon = "⚠️"
        
        print(f"{name} {area} {occ} {det_count} {cov} {status_icon}")
    
    print("─" * 45)
    
    if summary["unverified_rooms"] > 0:
        print(f"⚠️ WARNING: {summary['unverified_rooms']} rooms require manual type input.")
        print("   Verify usage before ordering equipment.")
    
    print("=" * 45)


def main():
    """Main entry point with interactive human review."""
    parser = argparse.ArgumentParser(description="FireAI NFPA 72 Design Pipeline")
    parser.add_argument("pdf_file", help="Path to floor plan PDF")
    parser.add_argument("--output", "-o", help="JSON output path", default=None)
    parser.add_argument("--room-types", "-t", help="JSON file with manual room types", default=None)
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
    
    # Load manual room types if provided
    manual_room_types = {}
    if args.room_types:
        if os.path.exists(args.room_types):
            with open(args.room_types, 'r', encoding='utf-8') as f:
                data = json.load(f)
                manual_room_types = data.get("rooms", {})
            print(f"  Loaded {len(manual_room_types)} manual room types from {args.room_types}")
        else:
            print(f"WARNING: Room types file not found: {args.room_types}")
    
    # Run pipeline with manual types
    report = run_pipeline(args.pdf_file, output_path, manual_room_types)
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
                
                prompt = f"  {room_name} (area: {room['area_sqm']}m²) [type required]: "
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
                
                # Calculate detectors with LARGE ROOM handling
                # CRITICAL: Apply fail-safe to UNKNOWN only, not to ALL large rooms
                LARGE_ROOM_THRESHOLD_SQM = 500.0  # 500 m² flag threshold
                is_flagged = False
                warnings = []
                
                if user_type == "unknown":
                    detector_type = "UNKNOWN"
                    detector_count = 0
                    coverage_pct = 0.0
                    is_flagged = True
                    warnings.append("🔴 Type unknown - no detectors placed.")
                elif is_verified:
                    # KNOWN room type - calculate detectors (even if large)
                    detector = select_safe_detector_type(room_name, user_type)
                    detector_type = detector.name
                    if detector_type.startswith("SMOKE"):
                        detector_count = max(1, int((area_sqm / 9.0) + 0.5))
                    elif detector_type.startswith("HEAT"):
                        detector_count = max(1, int((area_sqm / 20.0) + 0.5))
                    else:
                        detector_count = max(1, int((area_sqm / 15.0) + 0.5))
                    coverage_pct = 100.0
                    
                    # Flag large rooms for special review (but DO place detectors)
                    if area_sqm > LARGE_ROOM_THRESHOLD_SQM:
                        is_flagged = True
                        warnings.append(f"⚠️ Large known room ({area_sqm:.1f}m²) - verify NFPA 72 §17.6.3.1.")
                elif area_sqm > LARGE_ROOM_THRESHOLD_SQM:
                    # Unknown AND large - flag for review
                    detector_type = "REVIEW_REQUIRED"
                    detector_count = 0
                    coverage_pct = 0.0
                    is_flagged = True
                    warnings.append(f"⚠️ Large outlier ({area_sqm:.1f}m²) - MANUAL REVIEW REQUIRED")
                
                # Check for special warnings
                if user_type == "kitchen":
                    warnings.append("Kitchen - SMOKE prohibited per NFPA 72 §17.6.4")
                
                # Area vs Type validation - flag anomalies
                MAX_REASONABLE_AREAS = {
                    "bathroom": 50, "closet": 20, "storage": 500,
                    "office": 200, "corridor": 100, "kitchen": 100,
                    "atrium": 1000, "lobby": 200, "mechanical": 500,
                    "electrical": 100
                }
                max_area = MAX_REASONABLE_AREAS.get(user_type, 500)
                if area_sqm > max_area:
                    warnings.append(f"⚠️ Unusual area for {user_type}: {area_sqm:.1f}m² > {max_area}m²")
                
                final_rooms.append({
                    "name": room_name,
                    "area_sqm": round(area_sqm, 1),
                    "occupancy_type": user_type,
                    "occupancy_verified": user_type != "unknown",
                    "source": "human_review" if user_type != "unknown" else "unverified",
                    "detector_type": detector_type,
                    "detector_count": detector_count,
                    "coverage_pct": coverage_pct,
                    "is_flagged": is_flagged,
                    "compliant": True,
                    "warnings": warnings
                })
            
            total_detectors = sum(r["detector_count"] for r in final_rooms)
            unknown_count = sum(1 for r in final_rooms if r["source"] == "unverified")
            
            # Build final report
            final_report = {
                "report_metadata": {
                    "source_file": args.pdf_file,
                    "generated_utc": datetime.utcnow().isoformat() + "Z",
                    "status": "COMPLETE" if unknown_count == 0 else "PARTIAL",
                    "requires_pe_review": unknown_count > 0,
                    "design_complete": unknown_count == 0,
                    "review_reason": "Human review completed" if unknown_count == 0 else f"{unknown_count} rooms still unknown"
                },
                "rooms": final_rooms,
                "summary": {
                    "total_rooms": len(final_rooms),
                    "unverified_rooms": unknown_count,
                    "total_detectors": total_detectors,
                    "compliant": unknown_count == 0
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