#!/usr/bin/env python3
"""
run_analysis.py - Demo script to test FireAI parsers
Usage: python3 run_analysis.py <pdf_file>
"""
import sys
import json
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parsers import ParserConfidence, GeometryExtractor, evaluate_drawing


def main(pdf_path: str):
    """Run analysis on a PDF file."""
    
    print("=" * 50)
    print("FireAI Analysis Demo")
    print("=" * 50)
    print("File: " + pdf_path)
    print()
    
    if not os.path.exists(pdf_path):
        print("ERROR: File not found: " + pdf_path)
        return 1
    
    print("Step 1: Evaluating PDF with ParserConfidence...")
    try:
        result = evaluate_drawing(pdf_path)
        print("  Gate Decision: " + result.gate.value)
        print("  Confidence Score: {:.2f}".format(result.score))
        print("  Details: " + str(result.details))
        print("  Message: " + str(result.message))
        
        if result.gate.value == "REJECT":
            print("\nREJECTED - Cannot proceed with analysis")
            return 1
            
    except Exception as e:
        print("ERROR in ParserConfidence: " + str(e))
        return 1
    
    print("\nStep 2: Extracting geometry with GeometryExtractor...")
    try:
        extractor = GeometryExtractor(pdf_path)
        walls = extractor.extract_walls()
        
        print("  Walls found: {}".format(len(walls)))
        for i, wall in enumerate(walls[:5]):
            print("    Wall {}: {}".format(i+1, wall))
            
    except Exception as e:
        print("ERROR in GeometryExtractor: " + str(e))
        walls = []
    
    output = {
        "file": pdf_path,
        "gate": result.gate.value,
        "score": result.score,
        "details": result.details,
        "message": result.message,
        "walls_extracted": len(walls),
    }
    
    output_file = "analysis_result.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print("\nResults saved to: " + output_file)
    print("=" * 50)
    
    return 0


if __name__ == "__main__":
    test_file = sys.argv[1] if len(sys.argv) > 1 else "test_data/hybrid/single_office.pdf"
    
    exit_code = main(test_file)
    sys.exit(exit_code)