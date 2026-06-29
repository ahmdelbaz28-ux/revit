# FireAI Platform Troubleshooting Guide

## Table of Contents
- [Overview](#overview)
- [Common Issues](#common-issues)
- [Database Issues](#database-issues)
- [Cache Issues](#cache-issues)
- [API Issues](#api-issues)
- [Authentication Issues](#authentication-issues)
- [Performance Issues](#performance-issues)
- [Security Issues](#security-issues)
- [Network Issues](#network-issues)
- [Deployment Issues](#deployment-issues)
- [Diagnostic Tools](#diagnostic-tools)
- [Recovery Procedures](#recovery-procedures)

## Overview

This guide provides systematic approaches to diagnose and resolve common issues with the FireAI platform. Each section includes symptoms, causes, and step-by-step solutions.

## Common Issues

### Application Won't Start

**Symptoms:**
- Container fails to start
- Error messages during startup
- Health checks failing

**Possible Causes:**
- Missing environment variables
- Invalid configuration
- Dependency service unavailable

**Solutions:**
1. Verify all required environment variables are set:
   ```bash
   docker-compose exec api env | grep -E "(FIREAI_API_KEY|FIREAI_EVIDENCE_HMAC_KEY|DATABASE_URL|REDIS_URL)"
   ```
2. Check dependency services:
   ```bash
   docker-compose ps
   ```
3. Review startup logs:
   ```bash
   docker-compose logs api
   ```

### API Returns 500 Errors

**Symptoms:**
- HTTP 500 Internal Server Error
- Unexpected server errors

**Possible Causes:**
- Database connection issues
- Internal application errors
- Resource exhaustion

**Solutions:**
1. Check API logs for detailed error messages
2. Verify database connectivity
3. Check system resources (CPU, memory, disk)
4. Review application configuration

## Database Issues

### Connection Failures

**Symptoms:**
- "Connection refused" errors
- "Database unavailable" messages
- Slow response times

**Solutions:**
1. Check if PostgreSQL is running:
   ```bash
   docker-compose exec db pg_isready
   ```
2. Verify connection string format in DATABASE_URL
3. Check PostgreSQL logs:
   ```bash
   docker-compose logs db
   ```
4. Confirm network connectivity between services

### Slow Queries

**Symptoms:**
- Slow API responses
- Timeout errors
- High database CPU usage

**Solutions:**
1. Enable query logging in PostgreSQL:
   ```sql
   ALTER SYSTEM SET log_min_duration_statement = 1000;
   SELECT pg_reload_conf();
   ```
2. Check for missing indexes:
   ```sql
   EXPLAIN ANALYZE SELECT * FROM your_table WHERE your_condition;
   ```
3. Optimize queries by adding appropriate indexes
4. Consider query caching for frequently accessed data

### Database Locks

**Symptoms:**
- Requests hanging
- Deadlock errors
- Concurrent operation failures

**Solutions:**
1. Check for active locks:
   ```sql
   SELECT * FROM pg_stat_activity WHERE state = 'active';
   ```
2. Identify blocking processes:
   ```sql
   SELECT * FROM pg_locks WHERE NOT granted;
   ```
3. Terminate problematic connections if necessary:
   ```sql
   SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle in transaction';
   ```

## Cache Issues

### Redis Connection Errors

**Symptoms:**
- "Connection refused" to Redis
- Cache-related errors
- Session problems

**Solutions:**
1. Verify Redis is running:
   ```bash
   docker-compose exec redis redis-cli ping
   ```
2. Check Redis logs:
   ```bash
   docker-compose logs redis
   ```
3. Verify Redis URL format and credentials
4. Check Redis memory usage and eviction policies

### Cache Inconsistency

**Symptoms:**
- Stale data in responses
- Inconsistent application behavior
- Data not refreshing as expected

**Solutions:**
1. Clear Redis cache:
   ```bash
   docker-compose exec redis redis-cli FLUSHALL
   ```
2. Verify cache TTL settings
3. Check for race conditions in cache updates
4. Implement proper cache invalidation strategies

## API Issues

### Rate Limiting Problems

**Symptoms:**
- HTTP 429 Too Many Requests
- Requests being blocked unexpectedly

**Solutions:**
1. Check current rate limit configuration
2. Verify API key usage and quotas
3. Adjust rate limits if necessary in configuration
4. Check for distributed rate limiting across multiple instances

### Endpoint Not Found

**Symptoms:**
- HTTP 404 errors
- API endpoints returning "Not Found"

**Solutions:**
1. Verify API routes are properly registered
2. Check API version compatibility
3. Confirm endpoint paths and HTTP methods
4. Review router configuration files

## Authentication Issues

### API Key Rejection

**Symptoms:**
- HTTP 401 Unauthorized errors
- API key validation failures

**Solutions:**
1. Verify API key format and length
2. Check for correct header format: `X-API-Key: your_api_key`
3. Confirm API key is properly stored and hashed
4. Check for timing attack prevention affecting validation

### JWT Token Issues

**Symptoms:**
- Token validation failures
- Expired token errors
- Invalid signature errors

**Solutions:**
1. Verify JWT secret matches between services
2. Check token expiration times
3. Confirm JWT algorithm compatibility
4. Validate token payload and claims

## Performance Issues

### High Memory Usage

**Symptoms:**
- High RAM consumption
- Out of memory errors
- Container crashes

**Solutions:**
1. Monitor memory usage:
   ```bash
   docker stats
   ```
2. Check for memory leaks in application code
3. Optimize data structures and reduce object creation
4. Implement proper resource cleanup

### Slow Response Times

**Symptoms:**
- High latency responses
- Poor user experience
- Timeout errors

**Solutions:**
1. Profile application performance
2. Optimize database queries
3. Implement caching strategies
4. Scale services horizontally if needed

### High CPU Usage

**Symptoms:**
- High CPU consumption
- Slow processing
- Resource contention

**Solutions:**
1. Monitor CPU usage patterns
2. Profile application for bottlenecks
3. Optimize algorithms and reduce computational overhead
4. Consider horizontal scaling

## Security Issues

### Security Header Violations

**Symptoms:**
- Browser security warnings
- CSP violations
- Security scanner alerts

**Solutions:**
1. Review security header configuration
2. Update CSP policies as needed
3. Verify SSL/TLS certificate validity
4. Address any identified vulnerabilities

### Unauthorized Access

**Symptoms:**
- Unauthorized users accessing protected endpoints
- Security breaches
- Privilege escalation

**Solutions:**
1. Review authentication and authorization logic
2. Verify RBAC implementation
3. Check for insecure direct object references
4. Implement proper access controls

## Network Issues

### Service Discovery Problems

**Symptoms:**
- Services unable to communicate
- DNS resolution failures
- Network timeouts

**Solutions:**
1. Check Docker network configuration
2. Verify service names and ports
3. Test connectivity between services
4. Review firewall rules

### Load Balancer Issues

**Symptoms:**
- Uneven traffic distribution
- Service unavailability
- Health check failures

**Solutions:**
1. Verify load balancer configuration
2. Check service health endpoints
3. Review routing rules
4. Test failover scenarios

## Deployment Issues

### Container Startup Failures

**Symptoms:**
- Containers failing to start
- Init errors
- Dependency failures

**Solutions:**
1. Check container logs for specific errors
2. Verify image integrity and tags
3. Review container resource limits
4. Check dependency services and volumes

### Configuration Drift

**Symptoms:**
- Inconsistent behavior across environments
- Configuration differences
- Unexpected behavior

**Solutions:**
1. Implement configuration management
2. Use environment-specific configuration files
3. Implement configuration validation
4. Document all configuration changes

## Diagnostic Tools

### Built-in Diagnostics

The platform includes several built-in diagnostic endpoints:

#### Health Check
```
GET /api/v1/health
```
Returns overall system health status.

#### Detailed Health
```
GET /api/v1/health/detail
```
Provides detailed health information for all components.

#### Metrics
```
GET /api/v1/metrics
```
Returns application metrics in Prometheus format.

### Command Line Tools

#### Docker Diagnostics
```bash
# Check all container statuses
docker-compose ps

# View logs for specific service
docker-compose logs SERVICE_NAME

# Monitor resource usage
docker stats

# Execute commands inside containers
docker-compose exec SERVICE_NAME COMMAND
```

#### Database Diagnostics
```sql
-- Check database connections
SELECT * FROM pg_stat_activity;

-- Monitor database performance
SELECT * FROM pg_stat_database;

-- Check table sizes
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) 
FROM pg_tables 
WHERE schemaname = 'public';
```

#### Application Diagnostics
```bash
# Test API connectivity
curl -H "X-API-Key: YOUR_API_KEY" http://localhost/api/v1/health

# Check specific endpoints
curl -v -H "X-API-Key: YOUR_API_KEY" http://localhost/api/v1/projects

# Test authentication
curl -I http://localhost/api/v1/health
```

## Recovery Procedures

### Service Recovery

#### Restart Specific Service
```bash
docker-compose restart SERVICE_NAME
```

#### Full System Restart
```bash
docker-compose down
docker-compose up -d
```

### Data Recovery

#### Database Backup
```bash
docker-compose exec db pg_dump -U fireai fireai > backup_$(date +%Y%m%d_%H%M%S).sql
```

#### Database Restore
```bash
cat backup.sql | docker-compose exec -T db psql -U fireai fireai
```

### Configuration Recovery

#### Rollback Configuration
1. Keep backup copies of working configuration files
2. Replace current configuration with known good version
3. Restart affected services

### Incident Response Steps

1. **Identify**: Determine the scope and impact of the issue
2. **Contain**: Isolate the problem to prevent further impact
3. **Diagnose**: Use diagnostic tools to identify root cause
4. **Resolve**: Implement appropriate solution
5. **Verify**: Confirm the issue is resolved
6. **Document**: Record the incident and solution for future reference

## Preventive Measures

### Monitoring and Alerts

1. Set up health checks for all services
2. Monitor resource utilization
3. Implement log analysis and alerting
4. Track performance metrics
5. Monitor security events

### Regular Maintenance

1. Update dependencies regularly
2. Rotate API keys and secrets
3. Clean up old logs and temporary files
4. Optimize database performance
5. Test backup and recovery procedures