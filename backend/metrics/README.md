# Backend Metrics Directory

This directory contains Prometheus metrics configuration for monitoring the FireAI platform.

## Files
- `prometheus.yml` - Prometheus scrape configuration
- Custom metrics collectors for application monitoring

## Usage
Configure in docker-compose.yml:
```yaml
metrics:
  build: ./backend/metrics
  ports:
    - "9090:9090"
```

## Available Metrics
- `fireai_http_requests_total` - HTTP request counter
- `fireai_http_request_duration_seconds` - Request latency histogram
- `fireai_active_projects` - Number of active projects
- `fireai_nfpa72_validations_total` - NFPA 72 validation count

## Note
This is a placeholder directory. Full metrics implementation coming in v1.1.0