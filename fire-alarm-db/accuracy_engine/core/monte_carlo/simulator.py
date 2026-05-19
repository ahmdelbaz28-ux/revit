from core.monte_carlo.scenario_generator import generate_scenario, get_remaining_devices


def run_monte_carlo(rooms: list, devices: list, validation: dict, iterations: int = 1000) -> list:
    results = []

    for _ in range(iterations):
        scenario_results = []

        for room in rooms:
            room_devices = [d for d in devices if d.get("room_id") == room.get("id")]
            scenario = generate_scenario(room_devices, room)
            remaining = get_remaining_devices(room_devices, scenario)

            coverage_after_failure = 0.0
            if room_devices:
                coverage_before = validation.get("coverage", validation.get("overall_coverage", 0.95))
                survival_ratio = len(remaining) / len(room_devices) if room_devices else 0
                coverage_after_failure = coverage_before * survival_ratio
            else:
                coverage_after_failure = 0.0

            is_valid = coverage_after_failure >= 0.90

            if scenario.get("exit_blocked") and room.get("exit_count", 2) <= 1:
                is_valid = False

            if scenario.get("power_failed") and len(remaining) == 0:
                is_valid = False

            scenario_results.append({
                "room_id": room.get("id"),
                "failed_devices": scenario["failed_count"],
                "remaining_devices": len(remaining),
                "coverage_before": validation.get("coverage", validation.get("overall_coverage", 0.95)),
                "coverage_after_failure": coverage_after_failure,
                "exit_blocked": scenario["exit_blocked"],
                "power_failed": scenario["power_failed"],
                "is_valid": is_valid
            })

        all_valid = all(r["is_valid"] for r in scenario_results)
        results.append({
            "scenario_valid": all_valid,
            "rooms": scenario_results
        })

    return results