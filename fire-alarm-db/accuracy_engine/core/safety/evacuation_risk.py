def evacuation_risk(room: dict) -> dict:
    risk_score = 0
    factors = []

    exit_count = room.get("exit_count", 1)
    if exit_count < 2:
        risk_score += 2
        factors.append("single_exit")

    travel_distance = room.get("travel_distance", 10)
    if travel_distance > 30:
        risk_score += 2
        factors.append("long_travel_distance")

    corridor_width = room.get("width", room.get("corridor_width", 2))
    if corridor_width < 2:
        risk_score += 1
        factors.append("narrow_passage")

    occupancy = room.get("occupancy", 10)
    area = room.get("area", 100)
    density = occupancy / area if area > 0 else 0
    if density > 0.3:
        risk_score += 1
        factors.append("high_occupancy_density")

    if risk_score >= 4:
        level = "critical"
    elif risk_score >= 2:
        level = "high"
    elif risk_score >= 1:
        level = "medium"
    else:
        level = "low"

    return {
        "score": risk_score,
        "level": level,
        "factors": factors
    }