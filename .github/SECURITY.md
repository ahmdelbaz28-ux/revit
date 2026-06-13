# Security Policy

FireAI is a safety-critical fire alarm engineering system. Bugs in our
code can produce incorrect engineering results that may endanger lives
in real buildings. We take security seriously.

## Reporting a Vulnerability

**Do NOT open a public GitHub issue for security vulnerabilities.**

Email: <set-this-to-real-address@example.com>
PGP key: <upload-key-to-this-link>

Expected response time: 7 days.

## Scope

In-scope:
- Authentication/authorization bypass in `backend/`
- Path traversal / argument injection in `parsers/`
- Insecure deserialization
- Server-side request forgery
- Engineering calculation errors that could mislead a user
  (use the audit report pattern: see `SMOKE_SPACING_AUDIT_FINDING_1.md`)

Out-of-scope:
- Issues requiring physical access to the server
- Social engineering of the owner/maintainers
- Issues in third-party dependencies (report those upstream and
  notify us)

## Currently Enabled GitHub Security Features

Run this command to check the live state:
```
curl -H "Authorization: Bearer $GH_TOKEN" \
  https://api.github.com/repos/ahmdelbaz28-ux/revit \
  | grep -E '"security_and_analysis"|"secret_scanning"|"dependabot"'
```

Recommended (operator action — see OPERATOR_ACTION_ITEMS.md):
- [ ] Dependabot vulnerability alerts: **ENABLE**
- [ ] Secret scanning: **ENABLE** (would have caught the leaked PAT
  during the V117–V125 session)
- [ ] Code scanning (CodeQL): **ENABLE**
- [ ] Branch protection on main: **ENABLE** (require PR + 1 review)
- [ ] Required signed commits: **CONSIDER**

## Past Security Hardening Cycles

| Cycle | Scope |
|-------|-------|
| V83  | 27 vulnerabilities (Z User audit) |
| V100+ | Tamper-evident security audit logging |
| V116 | `_handle_error` import vulnerability, info leak in health.py |
| V117 | Heat detector area physics guard |
| V118 | API/kernel single source of truth for AWG validation |
| V119 | CSP `unsafe-eval` secure-by-default in production |
| V120 | Smoke detector spacing audit (Phase A safety net) |
| V122 | DWG parser path security (argument injection, DoS, etc.) |
| V123 | DDC adapter refactored to shared `_path_security` helper |
| V125 | Path security extended to PDF/Image/Excel/Word/IFC parsers |

## Threat Model References

- `agent.md` Priority #1 (Safety), Priority #8 (Security)
- `SMOKE_SPACING_AUDIT_FINDING_1.md` (audit-report pattern)
- `VULNERABILITY_TRIAGE.md` (severity scoring matrix used by V117–V125)
- OWASP Top 10 (Web Application Security Risks)
- NFPA 72 §17.7.1.11 (engineering safety rules)
