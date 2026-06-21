#!/usr/bin/env python3
"""
FireAI Performance Testing Script

Tests the FireAI backend under load to verify it meets performance requirements:
- API response time < 200ms (p95)
- Throughput > 100 req/s
- No errors under concurrent load

Usage:
    python scripts/performance_test.py --base-url http://localhost:8000 --duration 60

Requirements:
    pip install httpx pytest
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)


# ─── Test endpoints ────────────────────────────────────────────────────────

ENDPOINTS = [
    ("GET", "/api/health", None),
    ("GET", "/api/v1/projects", None),
    ("GET", "/api/v1/devices", None),
    ("GET", "/api/v1/connections", None),
    ("GET", "/api/v1/reports", None),
    ("GET", "/api/v1/ml/predictive-maintenance/health", None),
    ("GET", "/api/v1/ml/predictive-maintenance/models", None),
]


# ─── Performance test runner ───────────────────────────────────────────────

async def make_request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    headers: dict[str, str],
) -> dict[str, Any]:
    """Make a single request and return timing data."""
    start = time.perf_counter()
    try:
        if method == "GET":
            response = await client.get(path, headers=headers)
        else:
            response = await client.post(path, headers=headers)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "path": path,
            "status": response.status_code,
            "elapsed_ms": elapsed_ms,
            "success": 200 <= response.status_code < 400,
        }
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "path": path,
            "status": 0,
            "elapsed_ms": elapsed_ms,
            "success": False,
            "error": str(e),
        }


async def run_load_test(
    base_url: str,
    api_key: str,
    duration_seconds: int,
    concurrency: int,
) -> dict[str, Any]:
    """Run load test for specified duration."""
    headers = {"X-API-Key": api_key} if api_key else {}
    results: list[dict[str, Any]] = []

    print(f"\n{'='*60}")
    print(f"  FireAI Performance Test")
    print(f"{'='*60}")
    print(f"  Base URL: {base_url}")
    print(f"  Duration: {duration_seconds}s")
    print(f"  Concurrency: {concurrency}")
    print(f"  Endpoints: {len(ENDPOINTS)}")
    print(f"{'='*60}\n")

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        start_time = time.time()
        request_count = 0

        while time.time() - start_time < duration_seconds:
            tasks = []
            for _ in range(concurrency):
                for method, path, _ in ENDPOINTS:
                    tasks.append(make_request(client, method, path, headers))

            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)
            request_count += len(batch_results)

            elapsed = time.time() - start_time
            print(f"  [{elapsed:5.1f}s] Requests: {request_count:5d} | "
                  f"Avg: {statistics.mean(r['elapsed_ms'] for r in batch_results):.1f}ms")

    return analyze_results(results)


def analyze_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze test results and return summary."""
    if not results:
        return {"error": "No results collected"}

    response_times = [r["elapsed_ms"] for r in results]
    success_count = sum(1 for r in results if r["success"])
    error_count = len(results) - success_count

    # Percentiles
    sorted_times = sorted(response_times)
    p50 = sorted_times[len(sorted_times) // 2]
    p95 = sorted_times[int(len(sorted_times) * 0.95)]
    p99 = sorted_times[int(len(sorted_times) * 0.99)]

    summary = {
        "total_requests": len(results),
        "successful": success_count,
        "failed": error_count,
        "error_rate": (error_count / len(results)) * 100,
        "response_time_ms": {
            "min": min(response_times),
            "max": max(response_times),
            "mean": statistics.mean(response_times),
            "median": p50,
            "p95": p95,
            "p99": p99,
            "stdev": statistics.stdev(response_times) if len(response_times) > 1 else 0,
        },
        "throughput_req_s": len(results) / (max(response_times) / 1000),
    }

    return summary


def print_summary(summary: dict[str, Any]) -> None:
    """Print human-readable summary."""
    print(f"\n{'='*60}")
    print(f"  Performance Test Summary")
    print(f"{'='*60}")
    print(f"  Total requests:    {summary['total_requests']:>8}")
    print(f"  Successful:        {summary['successful']:>8}")
    print(f"  Failed:            {summary['failed']:>8}")
    print(f"  Error rate:        {summary['error_rate']:>7.2f}%")
    print(f"{'─'*60}")
    print(f"  Response Time (ms):")
    print(f"    Min:             {summary['response_time_ms']['min']:>8.1f}")
    print(f"    Max:             {summary['response_time_ms']['max']:>8.1f}")
    print(f"    Mean:            {summary['response_time_ms']['mean']:>8.1f}")
    print(f"    Median (p50):    {summary['response_time_ms']['median']:>8.1f}")
    print(f"    p95:             {summary['response_time_ms']['p95']:>8.1f}")
    print(f"    p99:             {summary['response_time_ms']['p99']:>8.1f}")
    print(f"    Stdev:           {summary['response_time_ms']['stdev']:>8.1f}")
    print(f"{'─'*60}")
    print(f"  Throughput:        {summary['throughput_req_s']:>8.1f} req/s")
    print(f"{'='*60}")

    # Performance gates
    print(f"\n  Performance Gates:")
    p95_pass = summary['response_time_ms']['p95'] < 200
    error_pass = summary['error_rate'] < 1.0
    print(f"    {'✅' if p95_pass else '❌'} p95 < 200ms: {summary['response_time_ms']['p95']:.1f}ms")
    print(f"    {'✅' if error_pass else '❌'} Error rate < 1%: {summary['error_rate']:.2f}%")
    print(f"{'='*60}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="FireAI Performance Test")
    parser.add_argument("--base-url", default="http://localhost:8000",
                        help="Base URL of the FireAI backend")
    parser.add_argument("--api-key", default="",
                        help="API key for authenticated endpoints")
    parser.add_argument("--duration", type=int, default=60,
                        help="Test duration in seconds (default: 60)")
    parser.add_argument("--concurrency", type=int, default=10,
                        help="Number of concurrent requests (default: 10)")
    parser.add_argument("--output", default="",
                        help="Output file for JSON results (optional)")

    args = parser.parse_args()

    summary = asyncio.run(run_load_test(
        base_url=args.base_url,
        api_key=args.api_key,
        duration_seconds=args.duration,
        concurrency=args.concurrency,
    ))

    print_summary(summary)

    if args.output:
        Path(args.output).write_text(json.dumps(summary, indent=2))
        print(f"  Results saved to: {args.output}")

    # Exit code based on performance gates
    p95_pass = summary['response_time_ms']['p95'] < 200
    error_pass = summary['error_rate'] < 1.0
    return 0 if (p95_pass and error_pass) else 1


if __name__ == "__main__":
    sys.exit(main())
