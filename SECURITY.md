# Security Policy for FireAI Platform

## 🚨 Critical Safety Notice

FireAI is a **safety-critical system** designed for fire protection engineering. Security vulnerabilities in this system could lead to failures that compromise life safety systems. All security considerations must be evaluated not only for their cybersecurity implications but also for their potential impact on safety-critical functions.

Security policies and procedures have been established by **Eng. Ahmed Elbaz** to ensure the highest levels of protection for this safety-critical system.

## Security Overview

FireAI implements defense-in-depth security measures across all layers of the system:

- **Application Security**: Secure coding practices, input validation, and access controls
- **Network Security**: Encrypted communications and network segmentation
- **Data Security**: Encryption at rest and in transit, integrity verification
- **Physical Security**: Secure deployment guidelines and hardware security
- **Safety Security**: Safety-critical system protections and failure modes

*Security architecture by Eng. Ahmed Elbaz*

## Supported Versions

The following versions of FireAI receive security updates:

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | ✅ Yes (Recommended) |
| < 1.0   | ❌ No (Deprecated)   |

*Version support policy by Eng. Ahmed Elbaz*

## Reporting a Vulnerability

### Safety-Critical Vulnerabilities
If you discover a vulnerability that could compromise the safety functions of FireAI (incorrect calculations, false compliance reports, etc.), please contact us immediately:

- **Email**: security@fireai.org
- **PGP Key**: Available upon request for sensitive disclosures
- **Response Time**: We aim to respond to safety-critical vulnerabilities within 24 hours

### Standard Security Vulnerabilities
For standard security vulnerabilities (not affecting safety functions), please:

1. **Submit via GitHub Issues** with the "security-vulnerability" label
2. **Use responsible disclosure** practices
3. **Allow time for remediation** before public disclosure

### What Constitutes a Safety-Critical Vulnerability?

- Incorrect fire safety calculations
- Bypass of compliance verification
- Tampering with safety-critical algorithms
- False safety assurance claims
- Availability attacks on safety functions

*Vulnerability classification by Eng. Ahmed Elbaz*

## Security Measures

### Authentication & Authorization
- Multi-factor authentication for administrative access
- Role-based access control (RBAC)
- Principle of least privilege
- Session management with secure tokens

### Data Protection
- AES-256 encryption for data at rest
- TLS 1.3 for data in transit
- Integrity checking for safety-critical data
- Secure backup and recovery procedures

### Input Validation
- Strict input sanitization
- Boundary checks on all calculations
- Type validation for all parameters
- Safe defaults for all configurable parameters

### Audit & Logging
- Comprehensive audit trails
- Tamper-evident logging
- Security event correlation
- Compliance reporting capabilities

*Security implementations by Eng. Ahmed Elbaz*

## Safety Security Guidelines

### Calculation Integrity
- All safety calculations must be independently verifiable
- Deterministic execution for safety-critical functions
- Checksums and digital signatures for critical data
- Redundant calculation verification where possible

### Fail-Safe Principles
- Systems must fail to a safe state
- Conservative defaults for safety parameters
- Explicit safety checks before deployment
- Human oversight for critical decisions

*Safety security principles by Eng. Ahmed Elbaz*

## Security Best Practices for Users

### Deployment Security
- Deploy in isolated, secured environments
- Regular security patching
- Network segmentation
- Access controls and monitoring

### Operational Security
- Regular security audits
- Change management procedures
- Incident response planning
- Personnel security training

### Data Security
- Protect building and occupancy data
- Secure transmission of sensitive information
- Regular backup verification
- Access logging and monitoring

*Best practices established by Eng. Ahmed Elbaz*

## Incident Response

### During a Security Incident
1. **Isolate affected systems** to prevent spread
2. **Preserve evidence** for forensic analysis
3. **Assess safety impact** immediately
4. **Notify stakeholders** based on severity
5. **Implement workarounds** to maintain safety

### Post-Incident Activities
- Root cause analysis
- Security measure improvements
- Knowledge sharing with community
- Documentation updates

*Incident response procedures by Eng. Ahmed Elbaz*

## Compliance & Certifications

FireAI aims to meet or exceed the following security standards:
- NIST Cybersecurity Framework
- ISO/IEC 27001
- OWASP Top 10
- IEC 61508 (Functional Safety)
- ISO 26262 (Road Vehicle Functional Safety)

*Compliance framework by Eng. Ahmed Elbaz*

## Security Testing

### Automated Testing
- Static Application Security Testing (SAST)
- Dynamic Application Security Testing (DAST)
- Interactive Application Security Testing (IAST)
- Software Composition Analysis (SCA)

### Manual Testing
- Penetration testing by certified professionals
- Code reviews by security experts
- Architecture reviews
- Safety requirement verification

*Testing methodology by Eng. Ahmed Elbaz*

## Supply Chain Security

### Dependency Management
- Regular dependency scanning
- Known vulnerability checks
- Software Bill of Materials (SBOM)
- Trusted source verification

### Build Security
- Reproducible builds
- Secure build environments
- Artifact signing
- Integrity verification

*Supply chain security by Eng. Ahmed Elbaz*

## Preventing Secret Leaks — Developer Guide

Accidentally committing secrets (API keys, tokens, passwords) is one of the most common security incidents in software development. This section documents the tools and practices used by this project to prevent secret leaks.

### Automated Protection

#### Pre-Commit Hooks (Gitleaks + detect-secrets)

Two complementary secret scanners run automatically on every commit:

1. **Gitleaks** — Detects hardcoded secrets using pattern matching (AWS keys, GitHub tokens, private keys, etc.)
2. **detect-secrets** — Detects secrets using entropy analysis (catches things Gitleaks might miss)

**Setup:**
```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

#### CI/CD Secret Scanning

A GitHub Actions workflow (`.github/workflows/secret-scan.yml`) runs gitleaks on every PR push to main. It uses the same `.gitleaks.toml` configuration.

### Configuration Files

| File | Purpose |
|------|---------|
| `.pre-commit-config.yaml` | Orchestrates all pre-commit hooks including secret scanning |
| `.gitleaks.toml` | Gitleaks configuration with project-specific allowlists |
| `.secrets.baseline` | detect-secrets baseline for known false positives |
| `.gitleaksignore` | (Optional) Individual finding fingerprints to ignore |

### How to Handle False Positives

If a secret scanner flags a file that contains a **non-secret** (e.g., a test fixture with a synthetic API key), use one of:

- **Inline**: Add `# gitleaks:allow` at the end of the flagged line
- **Path allowlist**: Add the file pattern to `.gitleaks.toml` under `[[allowlist]]`
- **Update baseline**: Run `detect-secrets scan --baseline .secrets.baseline`

### Prevention Checklist

- [ ] No real API keys, tokens, or passwords in the diff
- [ ] Test keys use obvious placeholder values (e.g., `sk-test-...`)
- [ ] `.env` files are in `.gitignore` and NOT committed
- [ ] Pre-commit hooks pass (`pre-commit run --all-files`)
- [ ] CI workflow secrets use `${{ secrets.SECRET_NAME }}`, not hardcoded values
- [ ] Git commands avoid embedding tokens in URLs (use `.netrc` or SSH)

### Incident Response — Secret Committed

1. **Do NOT delete the commit** (secret is still in git history)
2. **Rotate the credential immediately**
3. **Remove the secret** via `git commit --amend` (if latest commit)
4. **Report** via security@fireai.org
5. **Add file to allowlists** to prevent recurrence

### Common Pitfalls

| Scenario | Solution |
|----------|----------|
| Git remote URL contains a PAT | `git remote set-url origin https://github.com/user/repo.git` |
| CI log prints env vars | Use `echo "Key length: ${#VAR}"` instead of `echo "Key: $VAR"` |
| Test fixture has API key | Add `# gitleaks:allow` or allowlist in `.gitleaks.toml` |
| Token in git push URL | Use `.netrc` file or SSH authentication instead |
| API response in CI logs | Truncate: `echo "Body (${#BODY} chars): ${BODY:0:300}..."` |

*Secret leak prevention established by Eng. Ahmed Elbaz*

## Contact

For security inquiries:
- **General Security**: security@fireai.org
- **Emergency Response**: emergency-security@fireai.org (for active incidents)
- **PGP Key**: Available upon request
- **Security Advisory**: Published via GitHub Security Advisories

*Security contacts established by Eng. Ahmed Elbaz*

---

**Remember: In FireAI, security and safety are inseparable. All security measures must preserve the safety-critical nature of the system.**

*Security policy developed by Eng. Ahmed Elbaz*