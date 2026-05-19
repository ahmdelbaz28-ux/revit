from core.monte_carlo.failure_models import detector_failed, exit_blocked, power_failed


def generate_scenario(devices: list, room: dict) -> dict:
    failed_devices = []

    for d in devices:
        if d.get("room_id") == room.get("id"):
            if detector_failed():
                failed_devices.append(d)

    return {
        "failed_devices": failed_devices,
        "exit_blocked": exit_blocked(),
        "power_failed": power_failed(),
        "total_devices": len(devices),
        "failed_count": len(failed_devices)
    }


def get_remaining_devices(devices: list, scenario: dict) -> list:
    failed = scenario.get("failed_devices", [])
    failed_positions = [(d.get("x"), d.get("y")) for d in failed]
    return [d for d in devices if (d.get("x"), d.get("y")) not in failed_positions]