#!/usr/bin/env python3
"""
run_analysis.py - Demo script to test FireAI parsers
Usage: python3 run_analysis.py <pdf_file>
"""
import sys
import json
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parsers import ParserConfidence, GeometryExtractor, evaluate_drawing


def main(pdf_path: str):
    """Run analysis on a PDF file."""
    
    print(f"=" * 50)
    print(f"FireAI Analysis Demo")
    print(f=" * 50)
    print(f"File: {pdf_path}")
    print()
    
    # Step 1: Check file exists
    if not os.path.exists(pdf_path):
        print(f"ERROR: File not found: {pdf_path}")
        return 1
    
    # Step 2: Evaluate with ParserConfidence
    print("Step 1: Evaluating PDF with ParserConfidence...")
    try:
        result = evaluate_drawing(pdf_path)
        print(f"  Gate Decision: {result.gate}")
        print(f"  Confidence Score: {result.score:.2f}")
        print(f"  Reasons: {result.reasons}")
        
        if result.gate.value == "REJECT":
            print(f"\n❌ REJECTED - Cannot proceed with analysis")
            return 1
            
    except Exception as e:
        print(f"ERROR in ParserConfidence: {e}")
        return 1
    
    # Step 3: Extract geometry if CAUTION or HIGH
    print("\nStep 2: Extracting geometry with GeometryExtractor...")
    try:
        extractor = GeometryExtractor(pdf_path)
        walls = extractor.extract_walls()
        
        print(f"  Walls found: {len(walls)}")
        for i, wall in enumerate(walls[:5]):  # Show first 5
            print(f"    Wall {i+1}: {wall}")
            
    except Exception as e:
        print(f"ERROR in GeometryExtractor: {e}")
        walls = []
    
    # Step 4: Save results
    output = {
        "file": pdf_path,
        "gate": result.gate.value,
        "score": result.score,
        "reasons": result.reasons,
        "walls_extracted": len(walls),
        "wall_details": [w.__dict__ for w in walls] if walls else []
    }
    
    output_file = "analysis_result.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Results saved to: {output_file}")
    print("=" * 50)
    
    return 0


if __name__ == "__main__":
    # Default test file if none provided
    test_file = sys.argv[1] if len(sys.argv) > 1 else "test_data/hybrid/single_office.pdf"
    
    exit_code = main(test_file)
    sys.exit(exit_code)