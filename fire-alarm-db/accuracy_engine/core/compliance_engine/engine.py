from core.compliance_engine.compliance_runner import ComplianceRunner
from core.compliance_engine.rule_registry import RuleRegistry


def run_compliance_verification(rooms: list, devices: list, coverage: float, design_confidence: float) -> dict:
    runner = ComplianceRunner()

    room_results = []
    for room in rooms:
        room_devices = [d for d in devices if d.get("room_id") == room.get("id")]
        validation = {
            "coverage": coverage,
            "overall_coverage": coverage,
            "device_count": len(room_devices)
        }
        result = runner.run(room, room_devices, validation)
        room_results.append(result)

    summary = runner.get_summary()
    report = runner.generate_report()
    all_metadata = RuleRegistry.get_all_metadata()

    return {
        "overall": summary["overall"],
        "all_passed": summary["all_passed"],
        "has_critical_failures": summary["critical_violations"] > 0,
        "summary": summary,
        "room_results": room_results,
        "report": report,
        "rules_executed": summary["rules_executed"],
        "rules_metadata": all_metadata,
        "design_confidence": design_confidence,
        "traceable": True
    }