# Performance Testing Guide

This document describes how to run performance tests against the FireAI backend.

## Prerequisites

1. FireAI backend running (default: `http://localhost:8000`)
2. Python 3.12+ with httpx installed: `pip install httpx`
3. Valid API key (set via `FIREAI_API_KEY` env var or pass `--api-key`)

## Running Tests

### Quick smoke test (10 seconds, low concurrency)

```bash
python scripts/performance_test.py \
    --base-url http://localhost:8000 \
    --api-key YOUR_API_KEY \
    --duration 10 \
    --concurrency 5
```

### Standard load test (60 seconds, 10 concurrent users)

```bash
python scripts/performance_test.py \
    --base-url http://localhost:8000 \
    --api-key YOUR_API_KEY \
    --duration 60 \
    --concurrency 10
```

### Stress test (120 seconds, 50 concurrent users)

```bash
python scripts/performance_test.py \
    --base-url http://localhost:8000 \
    --api-key YOUR_API_KEY \
    --duration 120 \
    --concurrency 50 \
    --output results/stress_test.json
```

## Performance Gates

The test verifies these performance requirements:

| Gate | Requirement | Status |
|------|------------|--------|
| p95 response time | < 200ms | Must pass |
| Error rate | < 1% | Must pass |

Exit code 0 = all gates passed, exit code 1 = at least one gate failed.

## Endpoints Tested

The script tests these endpoints:
- `GET /api/health` — health check
- `GET /api/v1/projects` — list projects
- `GET /api/v1/devices` — list devices
- `GET /api/v1/connections` — list connections
- `GET /api/v1/reports` — list reports
- `GET /api/v1/ml/predictive-maintenance/health` — ML subsystem health
- `GET /api/v1/ml/predictive-maintenance/models` — ML models list

## Interpreting Results

- **p50 (median)**: Typical response time. Should be < 50ms.
- **p95**: 95th percentile. Should be < 200ms.
- **p99**: 99th percentile. Should be < 500ms.
- **Error rate**: Percentage of failed requests. Must be < 1%.
- **Throughput**: Requests per second. Should be > 100 req/s.

## CI/CD Integration

Add this to `.github/workflows/ci.yml` to run performance tests in CI:

```yaml
- name: Performance test
  run: |
    python scripts/performance_test.py \
      --base-url http://localhost:8000 \
      --api-key ${{ secrets.FIREAI_TEST_API_KEY }} \
      --duration 30 \
      --concurrency 10
```

## Docker-based Performance Testing

For consistent results, run tests against a Docker container:

```bash
# Build and run FireAI in Docker
docker build -t fireai:perf .
docker run -d --name fireai-perf -p 8000:8000 \
    -e FIREAI_API_KEY=perf-test-key \
    fireai:perf

# Wait for startup
sleep 5

# Run performance test
python scripts/performance_test.py \
    --base-url http://localhost:8000 \
    --api-key perf-test-key \
    --duration 60

# Cleanup
docker stop fireai-perf && docker rm fireai-perf
```
