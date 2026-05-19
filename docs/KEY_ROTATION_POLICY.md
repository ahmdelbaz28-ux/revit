# Key Rotation Policy - V8 Security

## Overview
This document defines the key rotation policy for FireCalc V8 security modules.

## Key Types & Rotation Intervals

| Key Type | Location | Rotation Interval | Notes |
|---------|----------|------------------|-------|
| Master Encryption | `.keys/master.key` | 90 days | Primary encryption key |
| Override Tokens | DB `override_tokens` table | Per-use, 24h expiry | Single-use only |
| HMAC Keys | `.keys/hmac.key` | 90 days | Decision signatures |
| Code Signatures | DB `code_constants` | Annual | FPE review required |

## Rotation Procedure

### 90-Day Keys (Master, HMAC)

1. Generate new key: `python3 -c "import os; print(os.urandom(32).hex())"`
2. Store in `.keys/` with date suffix: `master.key.2026-05-14`
3. Update reference in code: `.keys/master.key` → symlink to new
4. Re-encrypt all encrypted data with new key
5. Verify: decrypt sample, compare
6. Archive old key: move to `.keys/archived/`
7. Document rotation in audit_trail

### Override Tokens
- Generated per-request
- Maximum 24-hour validity
- Single-use only (consumed on use)
- No manual rotation needed

## Expiration Monitoring

```bash
# Check key age (90 days = expired)
key_age_days() {
    key="$1"
    if [ -f ".keys/$key" ]; then
        age=$(($(date +%s) - $(stat -c %Y ".keys/$key")))
        days=$((age / 86400))
        if [ $days -gt 90 ]; then
            echo "EXPIRED: $key ($days days)"
        else
            echo "OK: $key ($days days)"
        fi
    fi
}
```

## Emergency Rotation

If key compromise suspected:
1. **IMMEDIATELY** revoke all active tokens: `revoke_all_tokens()`
2. Rotate master key within 24 hours
3. Document incident in audit_trail
4. Notify PE and legal

## Key Backup

- Encrypted backup: USB, stored in safe
- Access: PE + 1 witness
- Recovery: 2-of-3 key fragment

## Compliance

- NEC 2023 §110.5: Conductor insulation, rotation documented
- NFPA 72-2019 §26: System integrity, key management

---
**Document:** KEY_ROTATION_POLICY.md
**Last Updated:** 2026-05-14
**Owner:** PE (Professional Engineer)