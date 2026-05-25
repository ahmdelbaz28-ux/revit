def analyze_results(results: list) -> dict:
    total_runs = len(results)
    successful_runs = sum(1 for r in results if r["scenario_valid"])
    failed_runs = total_runs - successful_runs

    reliability_index = successful_runs / total_runs if total_runs > 0 else 0

    all_coverages = []
    worst_coverage = 1.0
    for run in results:
        for room in run.get("rooms", []):
            cov = room.get("coverage_after_failure", 0)
            all_coverages.append(cov)
            if cov < worst_coverage:
                worst_coverage = cov

    avg_coverage = sum(all_coverages) / len(all_coverages) if all_coverages else 0

    critical_failures = 0
    for run in results:
        for room in run.get("rooms", []):
            if room.get("coverage_after_failure", 0) < 0.70:
                critical_failures += 1

    num_rooms = len(results[0]["rooms"]) if results else 1
    critical_failure_probability = critical_failures / (total_runs * num_rooms) if total_runs > 0 and results else 0

    recommendations = []
    if reliability_index < 0.95:
        recommendations.append("increase_redundancy")
    if critical_failure_probability > 0.05:
        recommendations.append("add_detectors_in_critical_areas")
    if avg_coverage < 0.90:
        recommendations.append("improve_overall_coverage")

    return {
        "total_simulations": total_runs,
        "successful_runs": successful_runs,
        "failed_runs": failed_runs,
        "reliability_index": reliability_index,
        "failure_probability": 1 - reliability_index,
        "average_coverage_after_failure": avg_coverage,
        "worst_case_coverage": worst_coverage,
        "critical_failure_probability": critical_failure_probability,
        "recommended_actions": recommendations
    }