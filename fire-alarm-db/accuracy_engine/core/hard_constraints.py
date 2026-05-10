from math import sqrt

def distance(p1, p2):
    return sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

class Constraint:
    def check(self, context):
        pass

class MaxSpacingConstraint(Constraint):
    def __init__(self, max_distance):
        self.max_distance = max_distance

    def check(self, devices):
        for i, d1 in enumerate(devices):
            for j, d2 in enumerate(devices):
                if j <= i:
                    continue
                if distance((d1["x"], d1["y"]), (d2["x"], d2["y"])) > self.max_distance:
                    return False
        return True

class MinCoverageConstraint(Constraint):
    def __init__(self, min_coverage=0.90):
        self.min_coverage = min_coverage

    def check(self, coverage_score):
        return coverage_score >= self.min_coverage

class AllRoomsCoveredConstraint(Constraint):
    def check(self, rooms, devices):
        room_ids_with_devices = set(d.get("room_id") for d in devices if d.get("room_id"))
        all_room_ids = set(r.get("id") for r in rooms)
        return all_room_ids.issubset(room_ids_with_devices)

def evaluate_constraints(devices, rooms, coverage_score) -> dict:
    constraints = [
        MaxSpacingConstraint(15.0),
        MinCoverageConstraint(0.90),
        AllRoomsCoveredConstraint()
    ]

    results = {}
    all_passed = True

    for constraint in constraints:
        if isinstance(constraint, MaxSpacingConstraint):
            passed = constraint.check(devices)
        elif isinstance(constraint, MinCoverageConstraint):
            passed = constraint.check(coverage_score)
        elif isinstance(constraint, AllRoomsCoveredConstraint):
            passed = constraint.check(rooms, devices)
        else:
            passed = True

        results[constraint.__class__.__name__] = passed
        if not passed:
            all_passed = False

    return {"all_passed": all_passed, "results": results}