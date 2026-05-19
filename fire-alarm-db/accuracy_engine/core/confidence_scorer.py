from core.uncertainty_detector import detect_uncertainty

def calculate_confidence(room: dict, result: dict) -> float:
    score = 1.0

    coverage = result.get("validation", {}).get("coverage_score", result.get("overall_coverage", 0))
    if coverage < 0.95:
        score -= 0.3

    issues = detect_uncertainty(room)
    if issues:
        score -= 0.4

    if len(result.get("devices", [])) < 2:
        score -= 0.2

    return max(score, 0.0)

def overall_confidence(rooms: list, results: dict) -> dict:
    scores = []
    for room in rooms:
        scores.append(calculate_confidence(room, results))

    avg_score = sum(scores) / len(scores) if scores else 0

    if avg_score >= 0.8:
        level = "HIGH_CONFIDENCE"
        action = "export_ready"
    elif avg_score >= 0.5:
        level = "MEDIUM_CONFIDENCE"
        action = "review_recommended"
    else:
        level = "LOW_CONFIDENCE"
        action = "do_not_export"

    return {
        "average_score": avg_score,
        "level": level,
        "action": action,
        "per_room_scores": {room["id"]: scores[i] for i, room in enumerate(rooms)}
    }