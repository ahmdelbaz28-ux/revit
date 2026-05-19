"""Risk Assessment Engine - orchestrates all analyzers."""

from core.risk_engine.analyzers.occupancy import occupancy_risk
from core.risk_engine.analyzers.fire_load import fire_load_risk
from core.risk_engine.analyzers.evacuation import evacuation_risk
from core.risk_engine.analyzers.redundancy import redundancy_risk
from core.risk_engine.analyzers.failure_modes import detector_failure_risk
from core.risk_engine.analyzers.compliance import compliance_risk
from core.risk_engine.scoring.matrix import classify_risk
from core.risk_engine.scoring.confidence import confidence_score
from core.risk_engine.models.risk_models import RiskResult, Hazard


class ManualReviewRequired(Exception):
    """Exception raised when design confidence is too low."""
    pass


def analyze_room(room: dict, devices: list, validation: dict) -> RiskResult:
    """Analyze a single room for risk assessment.
    
    Args:
        room: Room configuration dictionary
        devices: List of detection devices in the room
        validation: Validation result dictionary
        
    Returns:
        RiskResult with complete risk assessment
    """
    total_score = 0.0

    # Run all 6 analyzers
    total_score += occupancy_risk(room)
    total_score += fire_load_risk(room)
    total_score += evacuation_risk(room)
    total_score += redundancy_risk(room, devices)
    total_score += detector_failure_risk(room, devices)
    total_score += compliance_risk(validation)

    # Classify risk level
    level = classify_risk(total_score)
    
    # Calculate confidence
    confidence = confidence_score(room, validation)

    # Generate recommendations and hazards
    recommendations = []
    hazards = []

    # Add hazards based on risk level
    if level == "CRITICAL":
        recommendations.append("Immediate engineering review required")
        hazards.append(Hazard(
            name="critical_risk_level",
            severity="CRITICAL",
            probability="HIGH",
            mitigation="Manual engineering review mandatory"
        ))

    # Coverage hazard
    coverage = validation.get("coverage", validation.get("overall_coverage", 0))
    if coverage < 0.9:
        recommendations.append("Increase detector coverage to meet 90% NFPA requirement")
        hazards.append(Hazard(
            name="insufficient_coverage",
            severity="HIGH",
            probability="MEDIUM",
            mitigation="Add more detectors or adjust placement"
        ))

    # Redundancy hazard
    if len(devices) <= 1:
        recommendations.append("Add redundant detectors for critical area")
        hazards.append(Hazard(
            name="single_point_of_failure",
            severity="HIGH",
            probability="MEDIUM",
            mitigation="Install backup detector within 7.5m"
        ))

    # Evacuation hazard
    if room.get("exit_count", 1) < 2:
        recommendations.append("Add additional exit for safe evacuation")
        hazards.append(Hazard(
            name="limited_evacuation",
            severity="MEDIUM",
            probability="LOW",
            mitigation="Provide second exit route"
        ))

    # Enforce manual review for low confidence
    if confidence < 0.7:
        raise ManualReviewRequired()

    return RiskResult(
        room_id=room.get("id", "unknown"),
        risk_level=level,
        score=total_score,
        hazards=hazards,
        recommendations=recommendations,
        confidence=confidence
    )


def run_risk_engine(rooms: list, devices: list, validation: dict) -> list:
    """Run risk assessment on all rooms.
    
    Args:
        rooms: List of room configuration dictionaries
        devices: List of all detection devices
        validation: Validation result dictionary
        
    Returns:
        List of RiskResult objects
    """
    results = []

    for room in rooms:
        room_devices = [d for d in devices if d.get("room_id") == room.get("id")]
        try:
            result = analyze_room(room, room_devices, validation)
            results.append(result)
        except ManualReviewRequired:
            # Add CRITICAL result for manual review
            results.append(RiskResult(
                room_id=room.get("id", "unknown"),
                risk_level="CRITICAL",
                score=10.0,
                hazards=[Hazard(
                    name="manual_review_required",
                    severity="CRITICAL",
                    probability="CERTAIN",
                    mitigation="Stop all automated decisions"
                )],
                recommendations=["MANUAL ENGINEERING REVIEW REQUIRED"],
                confidence=0.0
            ))

    return results
