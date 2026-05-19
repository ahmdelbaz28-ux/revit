def risk_score(room: dict) -> float:
    score = 1.0

    room_type = room.get("type")
    if room_type == "storage":
        score += 0.5
    if room_type == "electrical":
        score += 0.6
    if room_type == "mechanical":
        score += 0.4
    if room_type == "assembly":
        score += 0.7

    area = room.get("area", 0)
    if area > 200:
        score += 0.3

    height = room.get("height", 3.0)
    if height > 6:
        score += 0.4
    elif height > 3:
        score += 0.2

    return score

def risk_level(score: float) -> str:
    if score >= 2.0:
        return "critical"
    if score >= 1.5:
        return "high"
    if score >= 1.2:
        return "medium"
    return "low"