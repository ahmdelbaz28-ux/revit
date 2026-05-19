def generate_risk_report(stats: dict) -> str:
    report = "=" * 60 + "\n"
    report += "MONTE CARLO SAFETY RELIABILITY REPORT\n"
    report += "=" * 60 + "\n\n"

    report += f"Total Simulations: {stats['total_simulations']}\n"
    report += f"Successful: {stats['successful_runs']}\n"
    report += f"Failed: {stats['failed_runs']}\n\n"

    report += f"Reliability Index: {stats['reliability_index']:.1%}\n"
    report += f"Failure Probability: {stats['failure_probability']:.1%}\n\n"

    report += f"Average Coverage After Failure: {stats['average_coverage_after_failure']:.1%}\n"
    report += f"Worst-Case Coverage: {stats['worst_case_coverage']:.1%}\n"
    report += f"Critical Failure Probability: {stats['critical_failure_probability']:.1%}\n\n"

    if stats['recommended_actions']:
        report += "Recommended Actions:\n"
        for action in stats['recommended_actions']:
            report += f"  - {action}\n"

    return report