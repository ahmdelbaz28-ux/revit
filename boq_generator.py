"""
boq_generator.py — FireAI V1.0
Bill of Quantities Generator for NFPA 72 Fire Alarm Systems

Generates equipment lists, wiring estimates, and cost breakdowns
from FireAI design reports.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime


# Standard NFPA 72 equipment specifications
DETECTOR_SPECS = {
    "SMOKE": {
        "name": "Photoelectric Smoke Detector",
        "model": "System Sensor PHOTOELECTRIC-24",
        "cost_unit": 45.00,
        "wiring_awg": 18,
        "current_ma": 0.15,
    },
    "SMOKE_PHOTOELECTRIC": {
        "name": "Photoelectric Smoke Detector",
        "model": "System Sensor PHOTOELECTRIC-24",
        "cost_unit": 45.00,
        "wiring_awg": 18,
        "current_ma": 0.15,
    },
    "SMOKE_IONIZATION": {
        "name": "Ionization Smoke Detector",
        "model": "System Sensor IONIZATION-24",
        "cost_unit": 42.00,
        "wiring_awg": 18,
        "current_ma": 0.12,
    },
    "SMOKE_HEAT_COMBINATION": {
        "name": "Smoke/Heat Combination Detector",
        "model": "System Sensor COMB24",
        "cost_unit": 78.00,
        "wiring_awg": 18,
        "current_ma": 0.20,
    },
    "HEAT_FIXED_TEMP": {
        "name": "Fixed Temperature Heat Detector",
        "model": "System Sensor HEAT-24-135",
        "cost_unit": 35.00,
        "wiring_awg": 18,
        "current_ma": 0.10,
    },
    "HEAT_RATE_OF_RISE": {
        "name": "Rate of Rise Heat Detector",
        "model": "System Sensor ROR-24",
        "cost_unit": 38.00,
        "wiring_awg": 18,
        "current_ma": 0.11,
    },
    "PULL_STATION": {
        "name": "Manual Pull Station",
        "model": "System Sensor PULL-24",
        "cost_unit": 55.00,
        "wiring_awg": 18,
        "current_ma": 0.05,
    },
    "HORN": {
        "name": "Fire Alarm Horn",
        "model": "System Sensor HORN-24",
        "cost_unit": 28.00,
        "wiring_awg": 16,
        "current_ma": 0.25,
    },
    "STROBE": {
        "name": "Visual Alarm (Strobe)",
        "model": "System Sensor STROBE-24-CD",
        "cost_unit": 65.00,
        "wiring_awg": 16,
        "current_ma": 0.15,
    },
    "HORN_STROBE": {
        "name": "Horn/Strobe Combination",
        "model": "System Sensor HS-24",
        "cost_unit": 85.00,
        "wiring_awg": 16,
        "current_ma": 0.35,
    },
}

# Standard peripheral devices
PERIPHERAL_SPECS = {
    "PULL_STATION": {
        "name": "Manual Pull Station",
        "model": "System Sensor PULL-24",
        "cost_unit": 55.00,
        "wiring_awg": 18,
    },
    "HORN": {
        "name": "Fire Alarm Horn",
        "model": "System Sensor HORN-24",
        "cost_unit": 28.00,
    },
    "STROBE": {
        "name": "Visual Alarm (Strobe)",
        "model": "System Sensor STROBE-24-CD",
        "cost_unit": 65.00,
    },
    "HORN_STROBE": {
        "name": "Horn/Strobe Combination",
        "model": "System Sensor HS-24",
        "cost_unit": 85.00,
    },
    "JUNCTION_BOX_4x4": {
        "name": "4x4 Junction Box",
        "model": "Steel City 4x4x2",
        "cost_unit": 12.00,
    },
    "JUNCTION_BOX_6x6": {
        "name": "6x6 Junction Box",
        "model": "Steel City 6x6x3",
        "cost_unit": 18.00,
    },
    "TERMINAL_BLOCK_10P": {
        "name": "10-Position Terminal Block",
        "model": "Panduit TB10",
        "cost_unit": 8.00,
    },
    "WIRE_NM_14_2": {
        "name": "NM-B 14/2 Wire (per 100ft)",
        "model": "Romex 14/2",
        "cost_unit": 45.00,
    },
    "WIRE_NM_12_2": {
        "name": "NM-B 12/2 Wire (per 100ft)",
        "model": "Romex 12/2",
        "cost_unit": 65.00,
    },
    "CONDUIT_3_4": {
        "name": "3/4\" EMT Conduit (per 100ft)",
        "model": "EMT 3/4",
        "cost_unit": 35.00,
    },
    "CONDUIT_1_2": {
        "name": "1/2\" EMT Conduit (per 100ft)",
        "model": "EMT 1/2",
        "cost_unit": 25.00,
    },
}


@dataclass
class BOQLineItem:
    """Single line item in BOQ."""
    item_code: str
    description: str
    model: str
    quantity: int
    unit: str
    unit_price: float
    total_price: float


@dataclass
class BOQReport:
    """Complete Bill of Quantities report."""
    project_name: str
    generated_utc: str
    source_report: str
    
    # Summary
    total_detectors: int = 0
    total_pull_stations: int = 0
    total_notification_devices: int = 0
    
    # Costs
    equipment_cost: float = 0.0
    labor_hours_estimated: float = 0.0
    materials_cost: float = 0.0
    total_system_cost: float = 0.0
    
    # Line items
    line_items: List[BOQLineItem] = field(default_factory=list)
    
    # Warnings
    warnings: List[str] = field(default_factory=list)


def generate_boq(design_report: dict, project_name: str = "Fire Alarm Project") -> BOQReport:
    """
    Generate Bill of Quantities from FireAI design report.
    
    Args:
        design_report: JSON report from run_full_pipeline.py
        project_name: Name of the project
        
    Returns:
        BOQReport with itemized quantities and cost estimates
    """
    report = BOQReport(
        project_name=project_name,
        generated_utc=datetime.utcnow().isoformat() + "Z",
        source_report=design_report.get("report_metadata", {}).get("source_file", "unknown")
    )
    
    # Count devices by type
    detector_counts: Dict[str, int] = {}
    
    for room in design_report.get("rooms", []):
        det_type = room.get("detector_type", "UNKNOWN")
        det_count = room.get("detector_count", 0)
        
        if det_type == "UNKNOWN" or det_count == 0:
            report.warnings.append(
                f"Room '{room['name']}' has {det_count} detectors - "
                f"type '{det_type}' requires manual verification"
            )
            continue
            
        if det_type not in detector_counts:
            detector_counts[det_type] = 0
        detector_counts[det_type] += det_count
    
    # Add detector line items
    for det_type, count in detector_counts.items():
        if det_type not in DETECTOR_SPECS:
            report.warnings.append(f"Unknown detector type: {det_type}")
            continue
            
        spec = DETECTOR_SPECS[det_type]
        
        # Add detectors
        item = BOQLineItem(
            item_code=f"DET-{det_type}",
            description=spec["name"],
            model=spec["model"],
            quantity=count,
            unit="ea",
            unit_price=spec["cost_unit"],
            total_price=count * spec["cost_unit"]
        )
        report.line_items.append(item)
        report.total_detectors += count
        report.equipment_cost += item.total_price
        
        # Add wiring estimate (assume 1.5m per detector average)
        wire_length_m = count * 1.5
        wire_length_100ft = wire_length_m / 30.48  # Convert to 100ft units
        
        wire_item = BOQLineItem(
            item_code="WIRE-DET",
            description=f"Detection circuit wire {spec['wiring_awg']} AWG",
            model=f"THHN {spec['wiring_awg']}/1C",
            quantity=int(wire_length_100ft * 10) / 10,  # Round to 0.1
            unit="x100ft",
            unit_price=spec["wiring_awg"] * 2.5,  # ~$2.50 per 100ft per AWG
            total_price=wire_length_100ft * spec["wiring_awg"] * 2.5
        )
        report.line_items.append(wire_item)
        report.materials_cost += wire_item.total_price
        
        # Add junction box (1 per 4 detectors)
        jbox_count = max(1, count // 4)
        jbox_item = BOQLineItem(
            item_code="JBOX-DET",
            description="4x4 Junction Box for detectors",
            model="Steel City 4x4x2",
            quantity=jbox_count,
            unit="ea",
            unit_price=PERIPHERAL_SPECS["JUNCTION_BOX_4x4"]["cost_unit"],
            total_price=jbox_count * PERIPHERAL_SPECS["JUNCTION_BOX_4x4"]["cost_unit"]
        )
        report.line_items.append(jbox_item)
        report.materials_cost += jbox_item.total_price
    
    # Add standard peripherals for notification devices
    # Estimate: 1 pull station per 500 sqm, 1 strobe per 100 sqm
    total_area = sum(r.get("area_sqm", 0) for r in design_report.get("rooms", []))
    
    if total_area > 0:
        # Pull stations
        pull_count = max(1, int(total_area / 500))
        pull_item = BOQLineItem(
            item_code="DET-PULL",
            description="Manual Pull Station",
            model=PERIPHERAL_SPECS["PULL_STATION"]["model"],
            quantity=pull_count,
            unit="ea",
            unit_price=PERIPHERAL_SPECS["PULL_STATION"]["cost_unit"],
            total_price=pull_count * PERIPHERAL_SPECS["PULL_STATION"]["cost_unit"]
        )
        report.line_items.append(pull_item)
        report.total_pull_stations = pull_count
        report.equipment_cost += pull_item.total_price
        
        # Notification devices (horns/strobes)
        notification_count = max(1, int(total_area / 100))
        notif_item = BOQLineItem(
            item_code="NOTIF-HS",
            description="Horn/Strobe Combination",
            model=PERIPHERAL_SPECS["HORN_STROBE"]["model"],
            quantity=notification_count,
            unit="ea",
            unit_price=PERIPHERAL_SPECS["HORN_STROBE"]["cost_unit"],
            total_price=notification_count * PERIPHERAL_SPECS["HORN_STROBE"]["cost_unit"]
        )
        report.line_items.append(notif_item)
        report.total_notification_devices = notification_count
        report.equipment_cost += notif_item.total_price
    
    # Calculate labor (estimate: 1 hour per detector + 2 hours per notification device)
    report.labor_hours_estimated = (
        report.total_detectors * 1.0 + 
        report.total_notification_devices * 2.0 +
        report.total_pull_stations * 0.5
    )
    
    # Calculate total system cost
    labor_rate = 85.00  # $85/hour for licensed technician
    report.total_system_cost = (
        report.equipment_cost + 
        report.materials_cost +
        report.labor_hours_estimated * labor_rate
    )
    
    return report


def boq_to_json(boq: BOQReport) -> dict:
    """Convert BOQReport to JSON-serializable dict."""
    return {
        "boq_metadata": {
            "project_name": boq.project_name,
            "generated_utc": boq.generated_utc,
            "source_report": boq.source_report,
        },
        "summary": {
            "total_detectors": boq.total_detectors,
            "total_pull_stations": boq.total_pull_stations,
            "total_notification_devices": boq.total_notification_devices,
            "equipment_cost": round(boq.equipment_cost, 2),
            "materials_cost": round(boq.materials_cost, 2),
            "labor_hours": round(boq.labor_hours_estimated, 1),
            "total_system_cost": round(boq.total_system_cost, 2),
        },
        "line_items": [
            {
                "item_code": item.item_code,
                "description": item.description,
                "model": item.model,
                "quantity": item.quantity,
                "unit": item.unit,
                "unit_price": item.unit_price,
                "total_price": item.total_price,
            }
            for item in boq.line_items
        ],
        "warnings": boq.warnings,
    }


def boq_to_markdown(boq: BOQReport) -> str:
    """Convert BOQReport to formatted markdown."""
    lines = [
        f"# Bill of Quantities - {boq.project_name}",
        f"",
        f"**Generated:** {boq.generated_utc}",
        f"**Source:** {boq.source_report}",
        "",
        "---",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Detectors | {boq.total_detectors} |",
        f"| Pull Stations | {boq.total_pull_stations} |",
        f"| Notification Devices | {boq.total_notification_devices} |",
        f"| Equipment Cost | ${boq.equipment_cost:,.2f} |",
        f"| Materials Cost | ${boq.materials_cost:,.2f} |",
        f"| Labor Hours | {boq.labor_hours_estimated:.1f} |",
        f"| **Total System Cost** | **${boq.total_system_cost:,.2f}** |",
        "",
        "---",
        "",
        "## Line Items",
        "",
        f"| Item | Description | Model | Qty | Unit | Unit $ | Total $ |",
        f"|------|------------|-------|-----|-----|--------|--------|",
    ]
    
    for item in boq.line_items:
        lines.append(
            f"| {item.item_code} | {item.description} | {item.model} | "
            f"{item.quantity} | {item.unit} | ${item.unit_price:.2f} | ${item.total_price:.2f} |"
        )
    
    if boq.warnings:
        lines.extend([
            "",
            "---",
            "",
            "## Warnings",
            "",
        ])
        for w in boq.warnings:
            lines.append(f"- {w}")
    
    return "\n".join(lines)


if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python boq_generator.py <report.json> [project_name]")
        sys.exit(1)
    
    report_path = sys.argv[1]
    project_name = sys.argv[2] if len(sys.argv) > 2 else "Fire Alarm Project"
    
    with open(report_path, "r") as f:
        design_report = json.load(f)
    
    boq = generate_boq(design_report, project_name)
    
    # Output formats
    print(boq_to_markdown(boq))