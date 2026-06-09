# FireAI Backup & Recovery Guide

## Backup Strategy

### Critical Data
| Data | Location | Frequency | Method |
|------|----------|-----------|--------|
| Audit database | `data/fireai_audit.db` | Daily | File copy + WAL checkpoint |
| UDM elements | `data/udm_elements.db` | Daily | File copy |
| Project data | `data/digital_twin.db` | Daily | File copy |
| Configuration | `.env` | On change | Secure secrets manager |
| Frontend build | `frontend/dist/` | On build | Rebuild from source |

### Backup Commands
```bash
# Create backup directory
BACKUP_DIR=/backups/fireai/$(date +%Y%m%d)
mkdir -p $BACKUP_DIR

# Backup databases (with WAL checkpoint first)
sqlite3 data/fireai_audit.db "PRAGMA wal_checkpoint(TRUNCATE);"
cp data/fireai_audit.db $BACKUP_DIR/
cp data/udm_elements.db $BACKUP_DIR/
cp data/digital_twin.db $BACKUP_DIR/
```

### Docker Volume Backup
```bash
# Backup named volumes
docker run --rm -v fireai-data:/data -v $(pwd)/backups:/backup alpine \
  cp -a /data/. /backup/fireai-data-$(date +%Y%m%d)/
```

## Recovery Procedures

### Database Corruption
```bash
# 1. Stop the service
docker compose down

# 2. Attempt recovery
sqlite3 data/fireai_audit.db ".recover"

# 3. If unrecoverable, restore from backup
cp /backups/fireai/YYYYMMDD/fireai_audit.db data/fireai_audit.db

# 4. Verify integrity
sqlite3 data/fireai_audit.db "PRAGMA integrity_check;"

# 5. Restart
docker compose up -d
```

### Configuration Loss
```bash
# Regenerate from example
cp .env.example .env
# MUST re-enter production secrets (API key, HMAC key)
```

### Complete System Recovery
1. Clone repository: `git clone https://github.com/ahmdelbaz28-ux/revit.git`
2. Install dependencies: `pip install -r requirements.txt`
3. Restore .env with production secrets
4. Restore databases from backup
5. Build frontend: `cd frontend && npm install && npm run build`
6. Start service: `docker compose up -d`
7. Verify: `curl http://localhost:8000/api/health`

## Disaster Recovery

### RPO (Recovery Point Objective)
- Maximum data loss: 24 hours (based on daily backup schedule)
- Audit log: tamper-evident hash chain enables verification of any recovered data

### RTO (Recovery Time Objective)
- Target: <30 minutes for full system recovery
- Simplified: <5 minutes for service restart (no data loss)