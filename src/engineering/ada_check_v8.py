"""
engineering/ada_check_v8.py
=========================
V8 Refactored ADA / NFPA 72 Compliance Checker - Returns DecisionProvenance

This module refactors ada_check.py to return DecisionProvenance (§3.5 of Blueprint).
Returns full reasoning chain with NFPA/ICC citations instead of bare findings.

Safety-critical: These checks ensure fire alarm devices are mounted at 
accessible heights per ADA, NFPA 72, and ICC A117.1 requirements.
"""
from __future__ import annotations
import hashlib
from dataclasses import dataclass
from typing import Optional

# V8 Core imports
from ..v8_core.decision_provenance import (
    DecisionProvenance,
    RuleApplied,
    ConfidenceScore,
    ConfidenceLevel,
    Violation,
    Alternative
)


@dataclass
class ADAFinding:
    """Legacy finding structure (for backward compat)."""
    severity: str
    rule: str
    message: str
    citation: str
    device_id: Optional[str] = None
    recommendation: str = ""


def check_pull_station_height(
    device_id: str,
    mount_height_m: float,
    code_authority=None
) -> DecisionProvenance:
    """
    Check manual pull station mounting height per NFPA 72 §17.14.8.4.
    
    Required: 1.07–1.22 m (42-48 inches) AFF.
    """
    input_str = str(device_id) + str(mount_height_m)
    seed = int(hashlib.sha256(input_str.encode()).hexdigest()[:8], 16) % (2**31)
    
    lo, hi = 1.07, 1.22  # meters
    mm_lo, mm_hi = lo * 1000, hi * 1000
    
    is_valid = lo <= mount_height_m <= hi
    
    violations = []
    if not is_valid:
        severity = "CRITICAL"
        citations = "NFPA 72 §17.14.8.4"
        if mount_height_m < lo:
            desc = f"Pull station {device_id} at {mount_height_m*1000:.0f}mm - below minimum {mm_lo:.0f}mm"
        else:
            desc = f"Pull station {device_id} at {mount_height_m*1000:.0f}mm - above maximum {mm_hi:.0f}mm"
        violations.append(Violation(
            severity=severity,
            citation=citations,
            description=desc,
            location=device_id
        ))
    
    rules = [
        RuleApplied(
            citation="NFPA 72-2022 §17.14.8.4",
            constant_id="NFPA72.17.14.8.4.pull_height",
            value_used=lo,
            unit="m",
        ),
        RuleApplied(
            citation="NFPA 72-2022 §17.14.8.4",
            constant_id="NFPA72.17.14.8.4.pull_height",
            value_used=hi,
            unit="m",
        )
    ]
    
    conf_level = ConfidenceLevel.HIGH if is_valid else ConfidenceLevel.MEDIUM
    conf = ConfidenceScore(
        input_quality_score=1.0,  # direct measurement
        rule_coverage=1.0,
        geometry_certainty=1.0,
        overall=conf_level
    )
    
    selected = "Within required height range" if is_valid else "Outside required height range"
    
    return DecisionProvenance.new(
        decision_type="ada_check",
        value={
            "device_id": device_id,
            "mount_height_m": mount_height_m,
            "within_range": is_valid,
            "required_range_m": [lo, hi]
        },
        inputs={"device_id": device_id, "mount_height_m": mount_height_m},
        rules_applied=rules,
        algorithm={"name": "height_check", "version": "v8.0.0", "parameters": {"seed": seed}},
        confidence=conf,
        selected_because=selected,
        feasible_alternatives_considered=0,
        warnings=[] if is_valid else [f"Re-mount within {mm_lo:.0f}-{mm_hi:.0f}mm of finished floor"],
        violations=violations
    )


def check_strobe_height(
    device_id: str,
    mount_height_m: float,
    ceiling_height_m: float,
    code_authority=None
) -> DecisionProvenance:
    """
    Check wall-mounted strobe mounting height per NFPA 72 §18.5.5.6.
    
    Required: ≥ 2.03m to bottom of lens OR within 0.15m of ceiling.
    """
    input_str = str(device_id) + str(mount_height_m) + str(ceiling_height_m)
    seed = int(hashlib.sha256(input_str.encode()).hexdigest()[:8], 16) % (2**31)
    
    min_height = 2.03  # meters
    max_proximity = 0.15  # meters from ceiling
    
    # Two valid conditions: ≥ 2.03m OR within 0.15m of ceiling
    meets_min = mount_height_m >= min_height
    near_ceiling = (ceiling_height_m - mount_height_m) <= max_proximity
    is_valid = meets_min or near_ceiling
    
    violations = []
    if not is_valid:
        citations = "NFPA 72 §18.5.5.6"
        desc = f"Strobe at {mount_height_m:.2f}m - must be ≥{min_height:.2f}m OR ≤{max_proximity:.2f}m from ceiling"
        violations.append(Violation(
            severity="MAJOR",
            citation=citations,
            description=desc,
            location=device_id
        ))
    
    rules = [
        RuleApplied(
            citation="NFPA 72-2022 §18.5.5.6",
            constant_id="NFPA72.18.5.5.6.strobe_min_height",
            value_used=min_height,
            unit="m",
        ),
        RuleApplied(
            citation="NFPA 72-2022 §18.5.5.6",
            constant_id="NFPA72.18.5.5.6.ceiling_proximity",
            value_used=max_proximity,
            unit="m",
        )
    ]
    
    conf_level = ConfidenceLevel.HIGH if is_valid else ConfidenceLevel.MEDIUM
    conf = ConfidenceScore(
        input_quality_score=1.0,
        rule_coverage=1.0,
        geometry_certainty=1.0,
        overall=conf_level
    )
    
    selected = "Within required height range" if is_valid else "Outside required height range"
    
    return DecisionProvenance.new(
        decision_type="ada_check",
        value={
            "device_id": device_id,
            "mount_height_m": mount_height_m,
            "ceiling_height_m": ceiling_height_m,
            "within_range": is_valid,
            "meets_min_requirement": meets_min,
            "near_ceiling": near_ceiling
        },
        inputs={
            "device_id": device_id,
            "mount_height_m": mount_height_m,
            "ceiling_height_m": ceiling_height_m
        },
        rules_applied=rules,
        algorithm={"name": "strobe_height_check", "version": "v8.0.0", "parameters": {"seed": seed}},
        confidence=conf,
        selected_because=selected,
        feasible_alternatives_considered=0,
        warnings=[] if is_valid else [f"Raise strobe lens to ≥{min_height:.2f}m above finished floor"],
        violations=violations
    )


def check_reach_ranges(
    device_id: str,
    mount_height_m: float,
    reach_type: str = "forward",
    code_authority=None
) -> DecisionProvenance:
    """
    Check accessible reach ranges per ICC A117.1 §308.
    
    Forward reach: 0.38–1.22 m (38-122 cm)
    Side reach: 0.38–1.37 m (38-137 cm)
    """
    input_str = str(device_id) + str(mount_height_m) + reach_type
    seed = int(hashlib.sha256(input_str.encode()).hexdigest()[:8], 16) % (2**31)
    
    if reach_type == "forward":
        lo, hi = 0.38, 1.22
        cite = "ICC A117.1 §308.2"
    else:  # side
        lo, hi = 0.38, 1.37
        cite = "ICC A117.1 §308.3"
    
    is_valid = lo <= mount_height_m <= hi
    
    violations = []
    if not is_valid:
        citations = cite
        if mount_height_m < lo:
            desc = f"Control {device_id} at {mount_height_m:.2f}m - below minimum {lo:.2f}m"
        else:
            desc = f"Control {device_id} at {mount_height_m:.2f}m - above maximum {hi:.2f}m"
        violations.append(Violation(
            severity="MAJOR",
            citation=citations,
            description=desc,
            location=device_id
        ))
    
    rules = [
        RuleApplied(
            citation=cite,
            constant_id=f"ICC.308.{reach_type}_reach",
            value_used=lo,
            unit="m",
        ),
        RuleApplied(
            citation=cite,
            constant_id=f"ICC.308.{reach_type}_reach",
            value_used=hi,
            unit="m",
        )
    ]
    
    conf = ConfidenceScore(
        input_quality_score=1.0,
        rule_coverage=1.0,
        geometry_certainty=1.0,
        overall=ConfidenceLevel.HIGH if is_valid else ConfidenceLevel.MEDIUM
    )
    
    selected = "Within reachable range" if is_valid else "Outside reachable range"
    
    return DecisionProvenance.new(
        decision_type="ada_check",
        value={
            "device_id": device_id,
            "mount_height_m": mount_height_m,
            "reach_type": reach_type,
            "within_range": is_valid,
            "required_range_m": [lo, hi]
        },
        inputs={"device_id": device_id, "mount_height_m": mount_height_m, "reach_type": reach_type},
        rules_applied=rules,
        algorithm={"name": "reach_check", "version": "v8.0.0", "parameters": {"seed": seed}},
        confidence=conf,
        selected_because=selected,
        feasible_alternatives_considered=0,
        warnings=[] if is_valid else [f"Re-mount between {lo*1000:.0f} and {hi*1000:.0f} mm AFF"],
        violations=violations
    )


def check_strobe_candela(
    room_area_m2: float,
    ceiling_height_m: float,
    strobe_candela: int,
    code_authority=None,
    device_id: str = None
) -> DecisionProvenance:
    """
    Check strobe candela rating per NFPA 72 Table 18.5.5.4.1(a).
    
    Minimum candela based on room size (using square-room equivalent).
    """
    input_str = str(room_area_m2) + str(strobe_candela)
    seed = int(hashlib.sha256(input_str.encode()).hexdigest()[:8], 16) % (2**31)
    
    # Table 18.5.5.4.1(a) - wall-mount, 1 light
    # Format: (room_side_m, min_candela)
    table = [
        (2.4, 15), (3.4, 20), (4.6, 30), (5.5, 40),
        (6.1, 50), (7.3, 60), (8.5, 75), (10.7, 100),
        (12.2, 135), (14.0, 177)
    ]
    
    side_m = room_area_m2 ** 0.5
    needed = None
    for size, cd in table:
        if side_m <= size:
            needed = cd
            break
    if needed is None:
        needed = 1000  # outside table - requires engineering
    
    is_valid = strobe_candela >= needed
    
    violations = []
    if not is_valid:
        violations.append(Violation(
            severity="MAJOR",
            citation="NFPA 72 Table 18.5.5.4.1(a)",
            description=f"Wall strobe {strobe_candela} cd insufficient for {room_area_m2:.0f}m² - needs ≥{needed}cd",
            location=device_id
        ))
    
    alternatives = []
    for size, cd in table:
        alternatives.append(Alternative(
            rank=len(alternatives) + 1,
            value={"room_side_m": size, "min_candela": cd},
            cost=cd,
            safety_margin=1.0 - (cd / 1000) if cd else 0.0,
            why_not_selected="" if cd >= needed else "insufficient"
        ))
    
    rules = [
        RuleApplied(
            citation="NFPA 72-2022 Table 18.5.5.4.1(a)",
            constant_id="NFPA72.18.5.5.4.1.strobe_candela",
            value_used=needed,
            unit="candela",
        )
    ]
    
    conf = ConfidenceScore(
        input_quality_score=1.0,
        rule_coverage=1.0,
        geometry_certainty=0.95,
        overall=ConfidenceLevel.HIGH if is_valid else ConfidenceLevel.MEDIUM
    )
    
    selected = f"Strobe candela {strobe_candela} adequate" if is_valid else "Strobe candela insufficient"
    
    return DecisionProvenance.new(
        decision_type="ada_check",
        value={
            "device_id": device_id,
            "room_area_m2": room_area_m2,
            "ceiling_height_m": ceiling_height_m,
            "strobe_candela": strobe_candela,
            "min_required_candela": needed,
            "within_range": is_valid
        },
        inputs={
            "room_area_m2": room_area_m2,
            "ceiling_height_m": ceiling_height_m,
            "strobe_candela": strobe_candela
        },
        rules_applied=rules,
        algorithm={"name": "candela_check", "version": "v8.0.0", "parameters": {"seed": seed}},
        confidence=conf,
        selected_because=selected,
        alternatives_top_3=alternatives[:3],
        feasible_alternatives_considered=len(alternatives),
        warnings=[] if is_valid else [f"Upgrade to ≥{needed}cd strobe or add additional units"],
        violations=violations
    )


def audit_devices(
    devices: list,
    room_areas: dict | None = None,
    code_authority=None
) -> DecisionProvenance:
    """
    Audit multiple devices for ADA compliance.
    
    devices: list of dicts with keys:
      - id: device identifier
      - kind: device type (manual_call_point, strobe, horn_strobe, emergency_light, access_reader, control_panel)
      - mount_h_m: mounting height in meters
      - ceiling_h_m: ceiling height (for strobe)
      - candela: candela rating (for strobe)
      - room_id: room identifier (for candela check)
    """
    input_str = str(devices) + str(room_areas)
    seed = int(hashlib.sha256(input_str.encode()).hexdigest()[:8], 16) % (2**31)
    
    if not devices:
        return DecisionProvenance.new(
            decision_type="ada_audit",
            value={"devices_checked": 0, "findings": []},
            inputs={"device_count": 0},
            rules_applied=[],
            algorithm={"name": "ada_audit", "version": "v8.0.0", "parameters": {}},
            confidence=ConfidenceScore(
                input_quality_score=0.0,
                rule_coverage=0.0,
                geometry_certainty=0.0,
                overall=ConfidenceLevel.REFUSE
            ),
            selected_because="No devices provided",
            feasible_alternatives_considered=0
        )
    
    room_areas = room_areas or {}
    all_findings = []
    total_violations = 0
    critical_count = 0
    
    for d in devices:
        did = d.get("id", "?")
        kind = d.get("kind", "")
        h = float(d.get("mount_h_m", 0.0))
        ceil = float(d.get("ceiling_h_m", 2.8))
        
        if kind == "manual_call_point":
            result = check_pull_station_height(did, h, code_authority)
            if result.violations_detected:
                total_violations += len(result.violations_detected)
                if any(v.severity == "CRITICAL" for v in result.violations_detected):
                    critical_count += 1
                all_findings.append(result.to_dict())
                
        elif kind in ("strobe", "horn_strobe", "emergency_light"):
            result = check_strobe_height(did, h, ceil, code_authority)
            if result.violations_detected:
                total_violations += len(result.violations_detected)
                all_findings.append(result.to_dict())
            
            # Candela check if room_id provided
            cd = d.get("candela")
            room_id = d.get("room_id")
            if cd and room_id and room_id in room_areas:
                result2 = check_strobe_candela(
                    room_areas[room_id], ceil, int(cd),
                    code_authority, did
                )
                if result2.violations_detected:
                    total_violations += len(result2.violations_detected)
                    all_findings.append(result2.to_dict())
                    
        elif kind in ("access_reader", "thermostat", "control_panel"):
            result = check_reach_ranges(did, h, "forward", code_authority)
            if result.violations_detected:
                total_violations += len(result.violations_detected)
                all_findings.append(result.to_dict())
    
    # Overall assessment
    has_critical = critical_count > 0
    conf_level = (
        ConfidenceLevel.LOW if has_critical 
        else ConfidenceLevel.MEDIUM if total_violations > 0 
        else ConfidenceLevel.HIGH
    )
    
    violations = []
    if critical_count > 0:
        violations.append(Violation(
            severity="CRITICAL",
            citation="ADA AUDIT",
            description=f"Found {critical_count} critical ADA violations",
        ))
    
    rules = [
        RuleApplied(
            citation="NFPA 72-2022 §17.14.8.4",
            constant_id="NFPA72.17.14.8.4",
            value_used=0,
            unit="N/A"
        ),
        RuleApplied(
            citation="NFPA 72-2022 §18.5.5.6",
            constant_id="NFPA72.18.5.5.6",
            value_used=0,
            unit="N/A"
        ),
        RuleApplied(
            citation="ICC A117.1 §308",
            constant_id="ICC.308",
            value_used=0,
            unit="N/A"
        )
    ]
    
    return DecisionProvenance.new(
        decision_type="ada_audit",
        value={
            "devices_checked": len(devices),
            "total_violations": total_violations,
            "critical_count": critical_count,
            "all_findings": all_findings
        },
        inputs={"device_count": len(devices)},
        rules_applied=rules,
        algorithm={"name": "ada_audit", "version": "v8.0.0", "parameters": {"seed": seed}},
        confidence=ConfidenceScore(
            input_quality_score=1.0,
            rule_coverage=1.0,
            geometry_certainty=1.0,
            overall=conf_level
        ),
        selected_because=f"Audited {len(devices)} devices - {total_violations} violations found",
        feasible_alternatives_considered=0,
        warnings=[] if total_violations == 0 else [f"{total_violations} ADA violations require remediation"],
        violations=violations
    )