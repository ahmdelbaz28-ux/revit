# Nginx Reverse Proxy Configuration

This directory contains Nginx configuration for TLS termination and reverse proxy setup.

## Files
- `nginx.conf` - Main Nginx configuration
- `sites-available/fireai` - FireAI site configuration
- `ssl/` - TLS certificates (production)

## Usage
For production deployment with TLS:
```bash
# Generate self-signed certificate (development only)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/fireai.key -out ssl/fireai.crt

# Start Nginx
nginx -c /path/to/nginx.conf
```

## Production Setup
In production, use Let's Encrypt or your preferred CA for TLS certificates.

## Note
This is a placeholder directory. Full Nginx integration coming in v1.1.0