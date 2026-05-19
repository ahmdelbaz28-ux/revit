def fire_load_risk(room: dict) -> dict:
    risk = 1.0
    factors = []

    room_type = room.get("type")
    if room_type == "storage":
        risk += 0.5
        factors.append("storage_materials")
    if room_type == "electrical":
        risk += 0.7
        factors.append("electrical_equipment")
    if room_type == "mechanical":
        risk += 0.4
        factors.append("mechanical_equipment")
    
    area = room.get("area", 0)
    if area > 200:
        risk += 0.3
        factors.append("large_area")
    
    height = room.get("height", 3.0)
    if height > 6:
        risk += 0.2
        factors.append("high_ceiling")

    if risk >= 2.0:
        level = "critical"
    elif risk >= 1.5:
        level = "high"
    elif risk >= 1.2:
        level = "medium"
    else:
        level = "low"

    return {
        "score": risk,
        "level": level,
        "factors": factors
    }