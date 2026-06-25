# Traefik Reverse Proxy Configuration

This directory contains Traefik configuration for dynamic reverse proxy and load balancing.

## Files
- `traefik.yml` - Main Traefik configuration
- `dynamic/` - Dynamic configuration (middleware, routers)
- `tls/` - TLS certificate configuration

## Usage
For Kubernetes/Docker Swarm deployments:
```bash
# Start Traefik
traefik --configfile=traefik.yml
```

## Features
- Automatic SSL/TLS with Let's Encrypt
- Load balancing
- Rate limiting
- Circuit breaking
- Distributed tracing

## Note
This is a placeholder directory. Full Traefik integration coming in v1.1.0