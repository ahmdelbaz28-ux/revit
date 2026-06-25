# PRODUCTION DEPLOYMENT GUIDE - FIREAI DIGITAL TWIN

## OVERVIEW

This guide provides step-by-step instructions for deploying the FireAI Digital Twin platform in a production environment. The system is designed for high availability, security, and performance in mission-critical fire safety engineering applications.

## PREREQUISITES

### Infrastructure Requirements
- **Operating System**: Linux (Ubuntu 20.04 LTS or CentOS 8+)
- **Architecture**: x86_64 (AMD64)
- **Container Runtime**: Docker 20.10+ with containerd
- **Orchestration**: Kubernetes 1.21+ (optional for single-node deployments)
- **Storage**: Persistent volumes with minimum 100GB available space
- **Network**: Load balancer with TLS termination capability

### Hardware Requirements
- **CPU**: Minimum 8 cores, recommended 16+ cores
- **RAM**: Minimum 16GB, recommended 32GB+
- **Storage**: SSD storage with minimum 100GB, recommended 500GB+
- **Network**: Gigabit Ethernet or better

### Software Dependencies
- **Python**: 3.12+ (required for all engineering calculations)
- **Database**: PostgreSQL 13+ or equivalent
- **Message Queue**: Redis 6+ for caching and job queues
- **Reverse Proxy**: NGINX or Traefik for TLS termination
- **Monitoring**: Prometheus and Grafana for observability

## DEPLOYMENT ARCHITECTURE

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Load Balancer │────│   TLS Termination│────│   Application   │
│     (HTTPS)     │    │   & Reverse      │    │   Services      │
└─────────────────┘    │      Proxy       │    └─────────────────┘
                       └──────────────────┘    │  ┌─────────────┐ │
                                               │  │ Core Engine │ │
┌─────────────────┐                           │  └─────────────┘ │
│   Monitoring    │                           │  ┌─────────────┐ │
│   & Logging     │                           │  │ API Gateway │ │
│   Services      │                           │  └─────────────┘ │
└─────────────────┘                           │  ┌─────────────┐ │
                                              │  │ Auth Layer  │ │
┌─────────────────┐                           │  └─────────────┘ │
│   Database &    │                           │  ┌─────────────┐ │
│   Cache Layer   │                           │  │ Integration │ │
└─────────────────┘                           │  └─────────────┘ │
                                              └─────────────────┘
```

## DEPLOYMENT STEPS

### Step 1: Environment Setup

1. Verify Python 3.12+ is installed:
```bash
python3 --version  # Should show Python 3.12.x or higher
```

2. Install system dependencies:
```bash
sudo apt update
sudo apt install -y python3-dev python3-pip postgresql-client redis-tools
```

3. Set up virtual environment:
```bash
python3 -m venv fireai_env
source fireai_env/bin/activate
pip install --upgrade pip setuptools wheel
```

### Step 2: Configuration Management

1. Create production configuration directory:
```bash
mkdir -p /opt/fireai/config
```

2. Copy configuration templates:
```bash
cp config/templates/production.env /opt/fireai/config/.env
cp config/templates/nginx.conf /opt/fireai/config/nginx.conf
cp config/templates/prometheus.yml /opt/fireai/config/prometheus.yml
```

3. Configure environment variables:
```bash
# Edit /opt/fireai/config/.env with appropriate values
# Database connection strings
# API keys and secrets
# Feature flags
# Logging configuration
```

### Step 3: Database Setup

1. Initialize database schema:
```bash
cd /opt/fireai/
source fireai_env/bin/activate
python -m fireai.db.migrate --production
```

2. Create initial admin user:
```bash
python -c "from fireai.admin import create_admin_user; create_admin_user()"
```

### Step 4: Service Installation

1. Install the FireAI Digital Twin:
```bash
pip install -e .
```

2. Install systemd services:
```bash
sudo cp deploy/systemd/fireai.service /etc/systemd/system/
sudo systemctl daemon-reload
```

### Step 5: TLS Certificate Setup

1. Obtain TLS certificates (using Let's Encrypt):
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

2. Configure certificate auto-renewal:
```bash
sudo crontab -e
# Add: 0 12 * * * /usr/bin/certbot renew --quiet
```

### Step 6: Application Deployment

1. Deploy application services:
```bash
sudo systemctl enable fireai
sudo systemctl start fireai
```

2. Verify service status:
```bash
sudo systemctl status fireai
```

### Step 7: Monitoring Configuration

1. Deploy monitoring stack:
```bash
kubectl apply -f deploy/monitoring/  # If using Kubernetes
# OR
docker-compose -f deploy/monitoring/docker-compose.yml up -d  # If using Docker
```

2. Configure alerting rules:
```bash
cp deploy/monitoring/alerts.yml /opt/fireai/config/
```

## SECURITY CONFIGURATION

### Network Security
- Configure firewall rules to allow only necessary ports (443, 80)
- Implement IP whitelisting for administrative access
- Enable fail2ban for SSH and web access protection

### Application Security
- Enforce HTTPS-only access
- Implement rate limiting at the proxy level
- Configure secure headers (HSTS, CSP, etc.)
- Enable audit logging for all engineering operations

### Data Security
- Encrypt data at rest using database encryption
- Implement secure backup encryption
- Enable audit trails for all engineering calculations
- Configure secure secrets management

## BACKUP AND RECOVERY

### Backup Procedures
```bash
# Daily backup script
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/opt/fireai/backups/$DATE"

mkdir -p $BACKUP_DIR

# Database backup
pg_dump --clean --no-owner --no-privileges fireai_db > $BACKUP_DIR/db_backup.sql

# Configuration backup
tar -czf $BACKUP_DIR/config.tar.gz /opt/fireai/config/

# Logs backup (last 7 days)
find /var/log/fireai/ -name "*.log" -mtime -7 -exec tar -rf $BACKUP_DIR/logs.tar {} \;

# Encrypt backup
gpg --symmetric --cipher-algo AES256 $BACKUP_DIR/*.tar $BACKUP_DIR/*.sql

# Cleanup old backups (older than 30 days)
find /opt/fireai/backups/ -type d -mtime +30 -exec rm -rf {} +
```

### Recovery Procedures
```bash
# Recovery script
#!/bin/bash
BACKUP_FILE=$1
RESTORE_DATE=$2

# Decrypt backup
gpg --decrypt $BACKUP_FILE > decrypted_backup.tar

# Extract backup
tar -xzf decrypted_backup.tar -C /tmp/restore/

# Restore database
psql fireai_db < /tmp/restore/db_backup.sql

# Restore configuration
tar -xzf /tmp/restore/config.tar.gz -C /opt/fireai/config/

# Restore logs
tar -xzf /tmp/restore/logs.tar -C /var/log/fireai/

# Clean up
rm -rf /tmp/restore/
```

## MONITORING AND HEALTH CHECKS

### Health Endpoints
- **Liveness**: `GET /health/live` - Basic service availability
- **Readiness**: `GET /health/ready` - Service ready for traffic
- **Metrics**: `GET /metrics` - Prometheus-formatted metrics
- **Status**: `GET /status` - Detailed system status

### Key Metrics
- Engineering calculation throughput
- Response times for critical operations
- Database connection pool utilization
- Memory and CPU usage
- Error rates and failure counts
- Security event counts

### Alerting Rules
- High error rate (>5% of requests)
- Slow response times (>5s for critical operations)
- Database connection pool exhaustion
- Memory usage >80%
- Failed authentication attempts
- Unauthorized access attempts

## MAINTENANCE OPERATIONS

### Routine Maintenance
```bash
# Weekly maintenance script
#!/bin/bash

# Log rotation
logrotate -f /etc/logrotate.d/fireai

# Database maintenance
psql fireai_db -c "VACUUM ANALYZE; REINDEX DATABASE fireai_db;"

# Clean temporary files
find /tmp/ -name "fireai_*" -mtime +1 -delete

# Update security patches
apt update && apt upgrade -y
```

### Update Procedures
```bash
# Staged update procedure
systemctl stop fireai
git pull origin main
pip install -e .
python -m fireai.db.migrate --upgrade
systemctl start fireai
```

## TROUBLESHOOTING

### Common Issues

1. **Python Version Incompatibility**
   - Symptom: Union type syntax errors
   - Solution: Ensure Python 3.12+ is used
   - Verification: `python3 --version`

2. **Database Connection Failures**
   - Symptom: Connection refused errors
   - Solution: Check database service and credentials
   - Verification: `psql -h hostname -U username -d database`

3. **Memory Exhaustion**
   - Symptom: Out of memory errors during calculations
   - Solution: Increase memory limits and optimize queries
   - Monitoring: Watch memory usage metrics

4. **Authentication Failures**
   - Symptom: Unauthorized access errors
   - Solution: Verify API keys and permissions
   - Audit: Check authentication logs

### Diagnostic Commands
```bash
# System diagnostics
journalctl -u fireai -f  # View service logs
curl http://localhost:8000/health/ready  # Check readiness
ps aux | grep fireai  # Check running processes
df -h  # Check disk space
free -h  # Check memory usage
```

## PERFORMANCE TUNING

### Database Tuning
- Connection pool size: 20-50 connections
- Query timeout: 30 seconds
- Index optimization for frequently queried tables
- Partitioning for large datasets

### Application Tuning
- Worker processes: Match CPU cores
- Memory limits: 80% of available RAM
- Request timeout: 60 seconds for complex operations
- Caching: Enable Redis-based caching

### Network Tuning
- Keep-alive connections: Enabled
- Compression: Enabled for JSON responses
- CDN: Recommended for static assets
- Load balancing: Round-robin or least connections

## CONTINGENCY PLANS

### Service Degradation
1. Switch to read-only mode
2. Disable non-critical features
3. Increase monitoring frequency
4. Prepare for emergency maintenance

### Data Corruption
1. Activate backup systems
2. Restore from last known good backup
3. Validate data integrity
4. Resume operations with monitoring

### Security Incident
1. Isolate affected systems
2. Preserve forensic data
3. Activate incident response team
4. Notify stakeholders
5. Implement containment measures

## SUPPORT CONTACTS

- **Technical Operations**: ops@fireai-digital-twin.com
- **Engineering Support**: eng-support@fireai-digital-twin.com
- **Emergency Response**: emergency@fireai-digital-twin.com
- **Documentation**: docs.fireai-digital-twin.com

## APPENDICES

### A. Configuration Reference
Complete list of configuration parameters and their meanings

### B. API Documentation
Detailed API endpoints and usage examples

### C. Troubleshooting Matrix
Common problems and solutions

### D. Compliance Checklist
Regulatory compliance requirements and verification steps

---
**Document Version**: 1.0  
**Last Updated**: 2026-06-10  
**Classification**: Production Deployment Guide - Internal Use