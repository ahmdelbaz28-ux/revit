#!/usr/bin/env python3
"""FireAI — API Endpoints Index Generator

Scans backend/routers/ and generates a comprehensive API index.
"""

from __future__ import annotations

# Run: python -m fireai.tools.api_indexer
# Output: backend/API_ENDPOINTS_INDEX.md
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def extract_endpoints(routers_dir: Path) -> dict[str, list[dict[str, object]]]:
    """Extract all endpoints from router files."""
    endpoints = defaultdict(list)

    http_methods = ['get', 'post', 'put', 'patch', 'delete', 'ws']

    for router_file in routers_dir.glob("*.py"):
        if router_file.name.startswith("_") or router_file.name.startswith("test_"):
            continue

        content = router_file.read_text()
        module_name = router_file.stem

        for method in http_methods:
            pattern = rf'@router\.{method}\("([^"]+)"'
            for match in re.finditer(pattern, content):
                path = match.group(1)
                line_num = content[:match.start()].count('\n') + 1

                # Extract docstring
                docstring = ""
                doc_pattern = rf'@router\.{method}\("[^"]+"(.*?)(?:def |@router|\Z)'
                doc_match = re.search(doc_pattern, content[match.end():], re.DOTALL)
                if doc_match:
                    docstring = re.sub(r'#.*', '', doc_match.group(1)).strip()
                    if docstring:
                        docstring = docstring.split('\n')[0][:60]

                endpoints[module_name].append({
                    "method": method.upper(),
                    "path": path,
                    "line": line_num,
                    "doc": docstring,
                })

    return endpoints


def generate_markdown(endpoints: dict[str, list[dict[str, object]]]) -> str:
    """Generate Markdown documentation."""
    # Group by category
    categories: dict[str, list[dict[str, object]]] = {
        "Health & Monitoring": [],
        "Projects": [],
        "Devices": [],
        "Connections": [],
        "Reports": [],
        "Exports": [],
        "Sync": [],
        "Environment": [],
        "QOMN Engineering": [],
        "FACP": [],
        "Workflow": [],
        "Memory": [],
        "Elements": [],
        "Conflicts": [],
        "DWG": [],
        "Admin": [],
        "Other": [],
    }

    # Map modules to categories
    module_categories = {
        "health": "Health & Monitoring",
        "monitor": "Health & Monitoring",
        "projects": "Projects",
        "devices": "Devices",
        "connections": "Connections",
        "connections_v2": "Connections",
        "reports": "Reports",
        "exports": "Exports",
        "sync": "Sync",
        "environment": "Environment",
        "qomn": "QOMN Engineering",
        "facp": "FACP",
        "workflow": "Workflow",
        "memory": "Memory",
        "elements": "Elements",
        "conflicts": "Conflicts",
        "dwg": "DWG",
        "api_keys": "Admin",
    }

    for module, routes in endpoints.items():
        category = module_categories.get(module, "Other")
        categories[category].extend(routes)

    md = """# FireAI — API Endpoints Index

**Generated:** {date}
**Total Endpoints:** {total}
**Source:** `backend/routers/*.py`

---

""".format(
        date=datetime.now().strftime('%Y-%m-%d'),
        total=sum(len(v) for v in endpoints.values())
    )

    for category, routes in categories.items():
        if not routes:
            continue

        md += f"## {category}\n\n"
        md += "| Method | Endpoint | Handler | Description |\n"
        md += "|--------|----------|---------|-------------|\n"

        for route in routes:
            doc = route['doc'] or ""
            md += f"| {route['method']} | `{route['path']}` | {category} | {doc} |\n"

        md += "\n"

    return md


def main():
    root = Path(__file__).parent.parent.parent
    routers_dir = root / "backend" / "routers"
    output_file = root / "backend" / "API_ENDPOINTS_INDEX.md"

    print("🔍 Scanning API endpoints...")
    endpoints = extract_endpoints(routers_dir)

    total = sum(len(v) for v in endpoints.values())
    print(f"📊 Found {total} endpoints across {len(endpoints)} routers")

    print(f"📝 Generating {output_file}...")
    md = generate_markdown(endpoints)
    output_file.write_text(md)

    print(f"✅ API Endpoints Index saved to: {output_file}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
