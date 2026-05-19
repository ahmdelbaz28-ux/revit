"""Monte Carlo Risk Stress Layer - Probabilistic safety analysis."""

from core.monte_carlo.simulator import run_monte_carlo
from core.monte_carlo.statistics import analyze_results
from core.monte_carlo.reporting import generate_risk_report
from core.monte_carlo.failure_models import (
    detector_failed,
    cable_failed,
    power_failed,
    exit_blocked
)

__all__ = [
    "run_monte_carlo",
    "analyze_results",
    "generate_risk_report",
    "detector_failed",
    "cable_failed",
    "power_failed",
    "exit_blocked"
]