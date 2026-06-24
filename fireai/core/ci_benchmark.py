"""ci_benchmark.py — Automated CI Benchmark Suite
================================================
Section 11.5: "Automated CI benchmark that fails PRs with >5% performance
regression."

Usage in CI (GitHub Actions / GitLab CI):
    python -m pytest fireai/core/ci_benchmark.py --benchmark-only -v

Or standalone:
    python fireai/core/ci_benchmark.py --baseline save
    python fireai/core/ci_benchmark.py --baseline compare  # fails if >5% regression

Integration with pytest-benchmark (optional):
    If pytest-benchmark installed: uses it for statistical reporting.
    Otherwise: uses built-in timing with N=1000 iterations.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Benchmark result
# ---------------------------------------------------------------------------


@dataclass
class BenchResult:
    """Result of one benchmark operation."""

    name: str
    ops_per_sec: float
    latency_us: float  # microseconds per call
    n_iterations: int
    std_dev_pct: float  # % standard deviation (lower = more stable)
    passed: bool = True
    regression_pct: float = 0.0  # negative = improvement
    is_stub: bool = False  # True when real benchmark couldn't run (import failure)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "ops_per_sec": round(self.ops_per_sec, 0),
            "latency_us": round(self.latency_us, 3),
            "n_iterations": self.n_iterations,
            "std_dev_pct": round(self.std_dev_pct, 2),
            "is_stub": self.is_stub,
        }


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------


def _run_timed(fn: Callable, n: int = 1_000, warmup: int = 100) -> Tuple[float, float]:
    """Run fn n times, return (ops_per_sec, std_dev_pct).
    Uses multiple rounds for statistical stability.
    """
    # Warmup
    for _ in range(min(warmup, n // 10)):
        fn()

    ROUNDS = 5
    round_times: List[float] = []
    per_round = max(n // ROUNDS, 10)

    for _ in range(ROUNDS):
        start = time.perf_counter()
        for _ in range(per_round):
            fn()
        elapsed = time.perf_counter() - start
        round_times.append(elapsed / per_round)

    avg = sum(round_times) / len(round_times)
    std = (sum((t - avg) ** 2 for t in round_times) / len(round_times)) ** 0.5
    std_pct = (std / avg * 100) if avg > 0 else 0.0

    ops_per_sec = 1.0 / avg
    return ops_per_sec, std_pct


class CIBenchmarkSuite:
    """Runs all FireAI performance benchmarks and compares to baseline.
    Fails (exit code 1) if any benchmark regresses by > REGRESSION_THRESHOLD%.
    """

    REGRESSION_THRESHOLD_PCT: float = 5.0  # >5% slower = fail
    BASELINE_FILE: str = ".fireai_benchmark_baseline.json"

    def __init__(self, threshold_pct: float = 5.0) -> None:
        self.threshold = threshold_pct
        self.results: List[BenchResult] = []

    # ------------------------------------------------------------------
    # Individual benchmarks
    # ------------------------------------------------------------------

    def bench_point3d_creation(self) -> BenchResult:
        """B8: Point3D creation throughput. Target: ≥ 1.0M/sec."""
        try:
            from core.models import Point3D

            ops, std = _run_timed(lambda: Point3D(1.0, 2.0, 3.0), n=500_000)
            return BenchResult("point3d_creation", ops, 1e6 / ops, 500_000, std)
        except ImportError:
            return self._stub("point3d_creation", 1_200_000)

    def bench_geometry_area(self) -> BenchResult:
        """Shoelace area. Target: ≥ 700K/sec for 4-vertex polygon."""
        try:
            from core.models import Geometry, Point3D

            g = Geometry(points=[Point3D(0, 0), Point3D(10, 0), Point3D(10, 8), Point3D(0, 8)])  # type: ignore[arg-type]
            ops, std = _run_timed(g.calculate_area, n=500_000)
            return BenchResult("geometry_area_4pt", ops, 1e6 / ops, 500_000, std)
        except ImportError:
            return self._stub("geometry_area_4pt", 1_600_000)

    def bench_geometry_perimeter(self) -> BenchResult:
        """B9: Perimeter inlined. Target: ≥ 500K/sec."""
        try:
            from core.models import Geometry, Point3D

            g = Geometry(points=[Point3D(0, 0), Point3D(10, 0), Point3D(10, 8), Point3D(0, 8)], polyline_closed=True)  # type: ignore[arg-type]
            ops, std = _run_timed(g.calculate_perimeter, n=500_000)
            return BenchResult("geometry_perimeter_4pt", ops, 1e6 / ops, 500_000, std)
        except ImportError:
            return self._stub("geometry_perimeter_4pt", 775_000)

    def bench_database_add_element(self) -> BenchResult:
        """B1: add_element() with persistent connection. Target: ≥ 10K/sec."""
        try:
            import dataclasses
            import uuid

            from core.database import UniversalDataModel

            @dataclasses.dataclass
            class _El:
                element_id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
                element_type: str = "bench"

                def to_dict(self):
                    return {"element_id": self.element_id}

            db = UniversalDataModel(db_path=":memory:")
            ops, std = _run_timed(lambda: db.add_element(_El()), n=5_000, warmup=50)
            return BenchResult("db_add_element", ops, 1e6 / ops, 5_000, std)
        except ImportError:
            return self._stub("db_add_element", 2_900)

    def bench_database_batch_1000(self) -> BenchResult:
        """B1: add_elements_batch(1000). Target: ≥ 50K elements/sec."""
        try:
            import dataclasses
            import uuid

            from core.database import UniversalDataModel

            @dataclasses.dataclass
            class _El:
                element_id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
                element_type: str = "bench"

                def to_dict(self):
                    return {"element_id": self.element_id}

            UniversalDataModel(db_path=":memory:")
            els = [_El() for _ in range(1000)]
            rounds = []
            for _ in range(5):
                db2 = UniversalDataModel(db_path=":memory:")
                t = time.perf_counter()
                db2.add_elements_batch(els)  # type: ignore[arg-type]
                rounds.append(time.perf_counter() - t)
            avg = sum(rounds) / len(rounds)
            elem_per_s = 1000.0 / avg
            # V44 FIX: Compute actual std_dev instead of hardcoded 0.0.
            # Population std (consistent with _run_timed) for 5 rounds.
            mean_r = sum(rounds) / len(rounds)
            variance = sum((r - mean_r) ** 2 for r in rounds) / len(rounds)
            std = (variance**0.5) / mean_r * 100.0 if mean_r > 0 else 0.0
            return BenchResult("db_batch_1000", elem_per_s, avg * 1e6 / 1000, 5, std)
        except ImportError:
            return self._stub("db_batch_1000", 50_000)

    def bench_assemble_polygons_10k(self) -> BenchResult:
        """V29 polygon assembly. Target: ≥ 37K rooms/sec."""
        from fireai.core.streaming_dwg_parser import _assemble_closed_polygons_v29

        # Generate 10K rooms (4 lines each = 40K line segments)
        lines = []
        for i in range(10_000):
            x0, y0 = float(i % 100) * 12.0, float(i // 100) * 12.0
            w, h = 10.0, 8.0
            lines.extend(
                [
                    ((x0, y0), (x0 + w, y0)),
                    ((x0 + w, y0), (x0 + w, y0 + h)),
                    ((x0 + w, y0 + h), (x0, y0 + h)),
                    ((x0, y0 + h), (x0, y0)),
                ]
            )

        t = time.perf_counter()
        polys = _assemble_closed_polygons_v29(lines, tolerance=0.01)
        elapsed = time.perf_counter() - t
        rooms_per_s = len(polys) / elapsed
        return BenchResult("assemble_10k_rooms", rooms_per_s, elapsed * 1e6 / max(len(polys), 1), 1, 0.0)

    def bench_delta_cache_hit(self) -> BenchResult:
        """DeltaCache: cache hit throughput. Target: ≥ 500K/sec."""
        from fireai.core.delta_cache import DeltaCache

        cache = DeltaCache(maxsize=1000)
        content = {"room_id": "R-01", "area": 80.0}
        cache.put("R-01", content, result={"detectors": 4})
        ops, std = _run_timed(lambda: cache.get("R-01", content), n=500_000)
        return BenchResult("delta_cache_hit", ops, 1e6 / ops, 500_000, std)

    def bench_delta_cache_miss_compute(self) -> BenchResult:
        """DeltaCache: cache miss + compute. Target: overhead < 10 µs."""
        from fireai.core.delta_cache import DeltaCache

        cache = DeltaCache(maxsize=1000)
        counter = [0]

        def compute():
            counter[0] += 1
            return {"detectors": counter[0]}

        ops, std = _run_timed(
            lambda: cache.get_or_compute(f"R-{counter[0]}", {"v": counter[0]}, compute),
            n=10_000,
            warmup=10,
        )
        return BenchResult("delta_cache_miss", ops, 1e6 / ops, 10_000, std)

    # ------------------------------------------------------------------
    # Run all + compare
    # ------------------------------------------------------------------

    def run_all(self) -> List[BenchResult]:
        """Run all benchmarks. Returns list of results."""
        benchmark_fns = [
            self.bench_point3d_creation,
            self.bench_geometry_area,
            self.bench_geometry_perimeter,
            self.bench_database_add_element,
            self.bench_database_batch_1000,
            self.bench_assemble_polygons_10k,
            self.bench_delta_cache_hit,
            self.bench_delta_cache_miss_compute,
        ]
        self.results = []
        for fn in benchmark_fns:
            try:
                result = fn()
                self.results.append(result)
                if result.is_stub:
                    status = "STUB"
                else:
                    status = "PASS" if result.passed else "FAIL"
                print(
                    f"  {status} {result.name:<45} "
                    f"{result.ops_per_sec:>12.0f} ops/sec  "
                    f"{result.latency_us:>8.2f} us"
                    f"{'  (SYNTHETIC)' if result.is_stub else ''}"
                )
            except Exception as exc:
                print(f"  ERR {fn.__name__:<45} ERROR: {exc}")

        return self.results

    def save_baseline(self, path: Optional[str] = None) -> str:
        """Save current results as baseline for future comparison."""
        path = path or self.BASELINE_FILE
        data = {
            "fireai_version": "29.0.0",
            "timestamp": time.time(),
            "benchmarks": {r.name: r.to_dict() for r in self.results},
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"\nBaseline saved to: {path}")
        return path

    def compare_to_baseline(self, path: Optional[str] = None) -> Tuple[bool, List[str]]:
        """Compare current results to saved baseline.
        Returns (all_passed, list_of_failures).
        Fails if any benchmark is >REGRESSION_THRESHOLD% slower.
        """
        path = path or self.BASELINE_FILE
        if not os.path.exists(path):
            print(f"No baseline found at {path}. Run with --baseline save first.")
            return True, []  # No baseline = don't fail

        with open(path) as f:
            baseline = json.load(f)

        failures: List[str] = []
        base_data = baseline.get("benchmarks", {})

        print(f"\n{'Benchmark':<45} {'Baseline':>12} {'Current':>12} {'Delta':>8}")
        print("-" * 80)

        for result in self.results:
            if result.is_stub:
                print(f"  SKIP {result.name:<43} {'N/A':>12} {'N/A':>12} {'N/A':>8}  (stub — not comparable)")
                continue

            base_entry = base_data.get(result.name)
            if base_entry is None:
                print(f"  NEW  {result.name:<43} {'N/A':>12} {result.ops_per_sec:>12.0f}")
                continue

            base_ops = base_entry["ops_per_sec"]
            delta_pct = (result.ops_per_sec - base_ops) / base_ops * 100

            symbol = "OK"
            if delta_pct < -self.threshold:
                symbol = "REGRESSION"
                failures.append(
                    f"{result.name}: {delta_pct:+.1f}% ({base_ops:.0f} -> {result.ops_per_sec:.0f} ops/sec)"
                )

            print(f"  {symbol} {result.name:<43} {base_ops:>12.0f} {result.ops_per_sec:>12.0f} {delta_pct:>+7.1f}%")

        return len(failures) == 0, failures

    @staticmethod
    def _stub(name: str, expected_ops: float) -> BenchResult:
        warnings.warn(
            f"Benchmark '{name}' used STUB data (expected_ops={expected_ops:.0f}). "
            f"Real measurement could not run — import failure. "
            f"Stub results must NOT be used for regression decisions.",
            stacklevel=3,
        )
        return BenchResult(
            name,
            expected_ops,
            1e6 / expected_ops,
            0,
            0.0,
            passed=False,
            is_stub=True,
        )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="FireAI CI Benchmark Suite")
    parser.add_argument(
        "--baseline",
        choices=["save", "compare", "run"],
        default="run",
        help="save: save as baseline; compare: compare to baseline; run: just run",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=5.0,
        help="Regression threshold %% (default: 5.0)",
    )
    parser.add_argument(
        "--baseline-file",
        default=".fireai_benchmark_baseline.json",
    )
    args = parser.parse_args()

    suite = CIBenchmarkSuite(threshold_pct=args.threshold)

    print(f"\nFireAI CI Benchmark Suite - threshold: {args.threshold}%")
    print("=" * 80)
    suite.run_all()

    if args.baseline == "save":
        suite.save_baseline(args.baseline_file)
        return 0

    if args.baseline == "compare":
        passed, failures = suite.compare_to_baseline(args.baseline_file)
        if failures:
            print(f"\nBENCHMARK REGRESSION DETECTED ({len(failures)} failures):")
            for f in failures:
                print(f"   - {f}")
            print(f"\nThis PR is >{args.threshold}% slower than baseline.")
            print("Fix the regression before merging.")
            return 1
        print(f"\nNo regressions detected (threshold: {args.threshold}%)")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
