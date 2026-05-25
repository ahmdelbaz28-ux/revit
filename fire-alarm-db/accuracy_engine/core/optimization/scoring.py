from math import sqrt

DEVICE_COSTS = {
    "smoke": 40.0,
    "heat": 55.0,
    "sounder": 35.0,
    "manual_call_point": 25.0
}

DEFAULT_WEIGHTS = {
    "coverage": 0.50,
    "cost": 0.25,
    "routing": 0.15,
    "redundancy": 0.10
}

def total_device_cost(devices: list) -> float:
    return sum(DEVICE_COSTS.get(d.get("type", "smoke"), 40.0) for d in devices)

def layout_score(coverage: float, devices: list, cable_length: float, weights: dict = None) -> float:
    if weights is None:
        weights = DEFAULT_WEIGHTS

    cost = total_device_cost(devices)
    normalized_cost = min(cost / 5000.0, 1.0)
    normalized_cable = min(cable_length / 1000.0, 1.0)

    score = (
        weights["coverage"] * coverage * 100.0
        - weights["cost"] * normalized_cost * 50.0
        - weights["routing"] * normalized_cable * 30.0
    )

    return score

def overlap_penalty(devices: list, min_distance: float = 3.0) -> float:
    penalty = 0.0
    for i, d1 in enumerate(devices):
        for j, d2 in enumerate(devices):
            if j <= i:
                continue
            dist = sqrt((d1["x"] - d2["x"])**2 + (d1["y"] - d2["y"])**2)
            if dist < min_distance:
                penalty += (min_distance - dist) * 5.0
    return penalty