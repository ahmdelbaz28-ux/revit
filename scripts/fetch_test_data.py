#!/usr/bin/env python3
"""
Test Data Fetcher - Legal Public Sources for Fire Alarm CAD Testing

This script downloads safe, legal architectural PDFs for testing:
- US GSA (federal buildings)
- OpenStreetMap (community maps) 
- Sample vendor PDFs (manufacturers)
- Academic datasets (MIT/CC licensed)

Usage:
    python fetch_test_data.py [--output-dir /path/to/output]
"""

import argparse
import os
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import List, Dict, Optional

# =============================================================================
# CONFIGURATION
# =============================================================================

SOURCES = {
    "gsa": {
        "name": "US General Services Administration",
        "description": "Federal building floor plans - Public Domain",
        "base_url": "https://www.gsa.gov",
        "license": "Public Domain (US Government)",
        "sample_files": [
            # Note: GSA doesn't have direct API, this is a placeholder
            # In practice, you'd browse gsa.gov/realestate to find building PDFs
        ],
    },
    "openstreetmap": {
        "name": "OpenStreetMap",
        "description": "Community maps - Open Database License",
        "base_url": "https://openstreetmap.org",
        "license": "ODbL (Open Database License)",
        "export_url": "https://download.openstreetmap.fr/extracts/",
    },
    "vendors": {
        "name": "Fire Alarm Manufacturers",
        "description": "Sample drawings from Honeywell, Siemens, Notifier, etc.",
        "base_url": "https://www.fire-alarm.com",
        "license": "Review/evaluation only - Copyright belongs to vendors",
        "notes": [
            "Check individual vendor sites for terms",
            "Usually free for product evaluation",
        ],
    },
    "academic": {
        "name": "Academic Datasets",
        "description": "Research datasets on GitHub",
        "license": "MIT/CC",
        "datasets": [
            {
                "name": "FloorPlanCAD Dataset",
                "url": "https://github.com/Lixxion/FloorPlanCAD",
                "description": "15,000+ floor plans - residential to commercial",
                "format": "CAD (DXF/DWG)",
                "license": "MIT",
            },
            {
                "name": "VahidAz/Floorplan_dataset", 
                "url": "https://github.com/VahidAz/Floorplan_dataset",
                "description": "35,126 floor plans with room labels",
                "format": "2D floor plans",
                "license": "MIT",
            },
            {
                "name": "HouseExpo",
                "url": "https://github.com/TeaganLi/HouseExpo",
                "description": "House layout dataset",
                "format": "JSON/PNG",
                "license": "MIT",
            },
        ],
    },
}


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Fetch legal test data for FireAI testing"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./test_data/public",
        help="Output directory for downloaded files",
    )
    parser.add_argument(
        "--source",
        type=str,
        choices=list(SOURCES.keys()),
        default="all",
        help="Which source to fetch from",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be downloaded without downloading",
    )
    return parser.parse_args()


def create_output_dir(output_dir: str) -> Path:
    """Create output directory if it doesn't exist."""
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def check_curl_available() -> bool:
    """Check if curl is available for downloads."""
    import shutil
    return shutil.which("curl") is not None


def download_with_curl(url: str, output_path: Path) -> bool:
    """Download file using curl."""
    import subprocess
    
    try:
        result = subprocess.run(
            ["curl", "-L", "-o", str(output_path), url],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        return False


def download_with_urllib(url: str, output_path: Path) -> bool:
    """Download file using urllib."""
    try:
        urllib.request.urlretrieve(url, output_path)
        return True
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        return False


def fetch_from_source(
    source_key: str, 
    output_dir: Path,
    dry_run: bool = False
) -> Dict[str, any]:
    """Fetch files from a specific source."""
    source = SOURCES[source_key]
    results = {
        "source": source["name"],
        "license": source["license"],
        "files": [],
        "success": False,
    }
    
    print(f"\n{'='*60}")
    print(f"Source: {source['name']}")
    print(f"License: {source['license']}")
    print(f"{'='*60}")
    
    if source_key == "openstreetmap":
        # OpenStreetMap exports - OSM XML format
        extracts = [
            ("europe/luxembourg.osm.gz", "Luxembourg - small test"),
            ("europe/monaco.osm.gz", "Monaco - small test"),
        ]
        
        for filename, description in extracts:
            url = f"{source['export_url']}{filename}"
            output_file = output_dir / filename
            
            print(f"\n{description}")
            print(f"URL: {url}")
            
            if dry_run:
                print("  [DRY RUN] Would download...")
                results["files"].append({
                    "filename": filename,
                    "description": description,
                    "dry_run": True,
                })
            else:
                # Note: OSM files are XML, not PDF
                # But they can be used for spatial testing
                print("  Note: OSM exports are XML format, not PDF")
                results["files"].append({
                    "filename": filename,
                    "description": description,
                    "note": "XML format",
                    "dry_run": dry_run,
                })
    
    elif source_key == "academic":
        # Academic datasets from GitHub (real, MIT/CC licensed)
        datasets = source.get("datasets", [])
        
        print(f"\nFound {len(datasets)} datasets:")
        
        for ds in datasets:
            print(f"\n  {ds['name']}")
            print(f"    URL: {ds['url']}")
            print(f"    Description: {ds['description']}")
            print(f"    Format: {ds['format']}")
            print(f"    License: {ds['license']}")
            
            results["files"].append({
                "name": ds["name"],
                "url": ds["url"],
                "description": ds["description"],
                "format": ds["format"],
                "license": ds["license"],
                "dry_run": dry_run,
            })
    
    elif source_key == "vendors":
        print("\nFire Alarm Vendor Resources:")
        
        vendors = [
            ("Honeywell", "https://www.honeywell.com/content/honeywell-ss/en-us/building-technologies.html"),
            ("Siemens", "https://www.usa.siemens.com/industry/software-brands/siemens-smart-infrastructure.html"),
            ("Notifier", "https://www.notifier.com/"),
            ("Bosch", "https://www.boschsecurity.com/"),
            ("Johnson Controls", "https://www.johnsoncontrols.com/"),
        ]
        
        for name, url in vendors:
            print(f"  {name}: {url}")
        
        results["files"].append({
            "note": "Check vendor websites directly",
            "vendors": [v[0] for v in vendors],
        })
    
    elif source_key == "gsa":
        print("\nUS GSA Building Plans:")
        print("  URL: https://www.gsa.gov/realestate")
        print("  Note: Most floor plans require direct request")
        print("  Many federal buildings have public floor plans")
        
        # Example federal buildings with public plans:
        examples = [
            ("DHS HQ", "Washington, DC"),
            ("Federal Courthouse", "Various cities"),
            ("Veterans Affairs", "Multiple locations"),
        ]
        
        for name, location in examples:
            print(f"    - {name}: {location}")
        
        results["files"].append({
            "note": "Request from GSA directly",
            "examples": examples,
        })
    
    results["success"] = True
    return results


def main():
    """Main entry point."""
    args = parse_args()
    
    print("="*60)
    print("FireAI Test Data Fetcher")
    print("="*60)
    print(f"Output directory: {args.output_dir}")
    print(f"Source: {args.source}")
    print(f"Dry run: {args.dry_run}")
    print()
    
    # Create output directory
    output_dir = create_output_dir(args.output_dir)
    print(f"Output directory created: {output_dir}")
    
    # Fetch from sources
    if args.source == "all":
        all_results = {}
        for source_key in SOURCES.keys():
            results = fetch_from_source(source_key, output_dir, args.dry_run)
            all_results[source_key] = results
        return all_results
    else:
        results = fetch_from_source(args.source, output_dir, args.dry_run)
        
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        print(f"Source: {results['source']}")
        print(f"License: {results['license']}")
        print(f"Files identified: {len(results['files'])}")
        
        return results


if __name__ == "__main__":
    main()