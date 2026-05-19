# FireAI Security Guide

## Overview

FireAI implements a defense-in-depth security model with tamper-evident audit logging, ensuring that all design decisions are traceable and cannot be modified after the fact.

## Security Model

### HMAC Chain

FireAI uses HMAC-SHA256 to create a tamper-evident event chain:

```
Event N
  ↓
HMAC-SHA256(key, Event N || Signature N-1)
  ↓
Signature N
  ↓
Event N+1
  ↓
...
```

Each event includes the previous signature creating an immutable chain.

### Key Components

1. **AUDIT_HMAC_KEY**: Secret key for signing events (32+ characters)
2. **Event Chain**: Linked list of HMAC-signed events
3. **Verification**: Checks integrity of entire chain

## How It Works

### Event Signing

```python
import hmac
import hashlib
import json

def sign_event(event: dict, previous_sig: str, key: str) -> str:
    """Sign event with HMAC."""
    # Include previous signature to create chain
    payload = json.dumps(event, sort_keys=True) + previous_sig
    return hmac.new(
        key.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
```

### Event Structure

```python
{
    "event_id": "uuid",
    "event_type": "room_analysis",
    "room_id": "room_1",
    "timestamp": "2026-05-16T10:00:00Z",
    "details": {...},
    "signature": "abc123...",
    "previous_signature": "def456..."
}
```

## Verifying Integrity

### Python

```python
from fireai.core.fireai_core import FireAISystem

system = FireAISystem(db_path='/path/to/audit.db')
is_valid, details = system.verify_audit_integrity()

if is_valid:
    print("Audit chain is valid - results trustworthy")
else:
    print(f"Audit compromised: {details}")
```

### API

```bash
curl http://localhost:8000/audit/verify -H "X-Api-Key: your-key"
# Returns: {"valid": true, "message": "Audit chain is valid"}
```

### Manual Verification

```python
import sqlite3

conn = sqlite3.connect('audit.db')
cursor = conn.cursor()
cursor.execute("SELECT event_id, event_type, signature FROM events ORDER BY timestamp")

events = cursor.fetchall()
for event in events:
    print(f"{event[0]}: {event[1]} -> {event[2][:16]}...")
```

## Detecting Tampering

### What HMAC Detects

- Modifying event details after creation
- Deleting events from chain
- Reordering events
- Adding fake events

### What HMAC Does NOT Detect

- Extracting events (read-only)
- Reading past events
- Initial key compromise (key must be rotated)

## Key Rotation

### When to Rotate

- Keys exposed or leaked
- Quarterly (recommended)
- After security incident
- Before long downtime

### Rotation Process

1. **Export current events** (read-only):
```bash
curl http://localhost:8000/audit/trail > audit_backup.json
```

2. **Generate new key**:
```bash
export NEW_AUDIT_HMAC_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
```

3. **Update system**:
```bash
export AUDIT_HMAC_KEY="$NEW_AUDIT_HMAC_KEY"
# Restart services
```

4. **New events signed with new key**

### Key Management Best Practices

- **Never** commit keys to version control
- Use secrets manager (AWS Secrets Manager, HashiCorp Vault)
- Rotate quarterly minimum
- Use 32+ random characters
- Store key in environment variable or secrets manager

## API Security

### Authentication

All endpoints require `X-Api-Key` header:

```bash
curl http://localhost:8000/analyse/room/v10 \
  -H "X-Api-Key: your-valid-key"
```

### Rate Limiting

| Endpoint | Limit |
|----------|-------|
| `/analyse/room/v10` | 30/min |
| `/analyse/floor/v10` | 10/min |
| `/analyse/floor/async` | 20/min |

### Response Codes

| Code | Meaning |
|------|--------|
| 200 | Success |
| 401 | Invalid API key |
| 422 | Validation error |
| 429 | Rate limited |
| 503 | Timeout |

## Production Security Checklist

- [ ] AUDIT_HMAC_KEY set (32+ random chars, not committed)
- [ ] FIREAI_API_KEYS configured
- [ ] All API keys use HTTPS
- [ ] Rate limiting enabled
- [ ] Audit verify tested and passing
- [ ] Key rotation procedure documented
- [ ] Secrets in manager (not env files)

---

## Incident Response

### If Audit Compromised

1. **DO NOT** use current results
2. **Export** all events for forensic
3. **Rotate** HMAC key
4. **Verify** key was not in code repo
5. **Re-run** critical analyses

### If API Key Compromised

1. **Remove** key from FIREAI_API_KEYS
2. **Generate** new key
3. **Update** all clients

---

*Generated: 2026-05-16 | Version: 10.0.0*