def generate_risk_assessment(rooms: list, devices: list, fire_load_results: dict, failure_results: dict, evacuation_results: dict, compliance_results: dict, confidence_results: dict) -> dict:
    critical_rooms = []
    for room in rooms:
        room_id = room["id"]
        fire_risk = fire_load_results.get(room_id, {}).get("level", "unknown")
        evac_risk = evacuation_results.get(room_id, {}).get("level", "unknown")
        
        if fire_risk == "critical" or evac_risk == "critical":
            critical_rooms.append({
                "room_id": room_id,
                "room_type": room.get("type", "unknown"),
                "fire_risk": fire_risk,
                "evacuation_risk": evac_risk,
                "hazards": [f"Fire risk: {fire_risk}", f"Evacuation risk: {evac_risk}"],
                "recommendations": [
                    "Add redundant smoke detector" if fire_risk == "critical" else "Monitor regularly",
                    "Increase exit capacity" if evac_risk == "critical" else "Existing egress adequate"
                ]
            })

    single_point_failures = [f for f in failure_results.get("failures", []) if f.get("single_point_of_failure")]

    return {
        "risk_matrix": {
            "critical_rooms": len(critical_rooms),
            "total_rooms": len(rooms),
            "high_risk_devices": len(single_point_failures)
        },
        "hazard_list": [h for room in critical_rooms for h in room["hazards"]],
        "critical_areas": critical_rooms,
        "single_point_failures": single_point_failures,
        "compliance_gaps": compliance_results.get("violations", []),
        "recommended_mitigations": [r for room in critical_rooms for r in room["recommendations"]],
        "confidence_level": confidence_results.get("level", "unknown"),
        "overall_assessment": "APPROVED" if confidence_results.get("action") == "export_ready" else "REVIEW_REQUIRED"
    }