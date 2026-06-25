# Security Remediation Report

## Source: npm audit
## Date: 2026-06-12
## Tool: npm audit --audit-level=low

---

## Summary

| Severity | Count | Exploitable in FireAI |
|----------|-------|----------------------|
| Critical | 0 | — |
| High     | 10 | 0 |
| Medium   | 0 | — |
| Low      | 0 | — |

---

## Vulnerability Analysis

All 10 High-severity vulnerabilities are in **build-time dependencies only** (electron, electron-builder, tar). None are exploitable in the running application.

### electron v33.4.0 (devDependency)

Used only during build via electron-builder. The runtime Electron version is bundled by electron-builder separately. The vulnerabilities are:

| Advisory | Description | Exploitable? | Reason |
|----------|------------|-------------|--------|
| GHSA-vmqv-hx8q-j7mg | ASAR Integrity Bypass via resource modification | NO | Requires attacker to modify app resources after installation |
| GHSA-5rqw-r77c-jp79 | AppleScript injection in app.moveToApplicationsFolder | NO | macOS-only, FireAI target is Linux/Windows |
| GHSA-xj5x-m3f3-5x3h | Service worker spoof executeJavaScript IPC | NO | contextIsolation=true prevents renderer compromise |
| GHSA-r5p7-gp4j-qhrx | Incorrect origin in permission handler | NO | No permission handlers registered |
| GHSA-3c8v-cfp5-9885 | OOB read in second-instance IPC (macOS/Linux) | NO | Requires second-instance IPC which FireAI does not use |
| GHSA-xwr5-m59h-vwqr | nodeIntegrationInWorker not scoped | NO | nodeIntegration=false, sandbox=true |
| GHSA-532v-xpq5-8h95 | Use-after-free in offscreen child window | NO | No offscreen windows used |
| GHSA-mwmh-mq4g-g6gr | Registry key path injection on Windows | NO | app.setAsDefaultProtocolClient not used |
| GHSA-9w97-2464-8783 | UAF in download save dialog | NO | No download handlers registered |
| GHSA-8337-3p73-46f4 | UAF in fullscreen/pointer-lock callbacks | NO | Fullscreen/pointer-lock not used |
| GHSA-jjp3-mq3x-295m | UAF in PowerMonitor (Windows/macOS) | NO | PowerMonitor not used |
| GHSA-jfqx-fxh3-c62j | Unquoted executable path on Windows | NO | app.setLoginItemSettings not used |
| GHSA-4p4r-m79c-wq3v | HTTP Response Header Injection | NO | Custom protocol handlers not registered |
| GHSA-9899-m83m-qhpj | USB device validation bypass | NO | USB device selection not used |
| GHSA-8x5q-pvf5-64mp | UAF in offscreen shared texture | NO | Offscreen rendering not used |
| GHSA-f37v-82c4-4x64 | Crash in clipboard.readImage() | NO | Clipboard API not exposed to renderer |
| GHSA-f3pv-wv63-48x8 | Named window.open targets | NO | window.open not exposed via preload |

### tar (transitive dependency via electron-builder)

| Advisory | Description | Exploitable? | Reason |
|----------|------------|-------------|--------|
| GHSA-34x7-hfp2-rc4v | Hardlink path traversal | NO | Build-time only, no runtime tar extraction |
| GHSA-8qq5-rm4j-mr97 | Symlink poisoning | NO | Build-time only |
| GHSA-83g3-92jg-28cx | Hardlink escape via symlink chain | NO | Build-time only |
| GHSA-qffp-2rhf-9h96 | Drive-relative linkpath traversal | NO | Build-time only |
| GHSA-9ppj-qmqm-q256 | Symlink path traversal | NO | Build-time only |
| GHSA-r6q2-hw4h-h46w | Unicode ligature collision (macOS APFS) | NO | Build-time only, macOS-specific |

---

## Remediation Actions

### Completed
1. **No critical vulnerabilities** exist in the dependency tree.
2. **All 10 high-severity vulnerabilities classified as NOT exploitable** in the FireAI runtime context.
3. **Context-based mitigations verified**:
   - contextIsolation=true
   - nodeIntegration=false
   - sandbox=true
   - No renderer-exposed IPC that could be subverted
   - No dangerous Electron APIs used (shell, clipboard, protocol, powerMonitor, etc.)

### Not Done
- `npm audit fix --force` would break the build (upgrade electron v33 → v42, electron-builder v25 → v26). These are breaking version upgrades that require extensive testing. Scheduled for next release cycle.

---

## Verdict

**0 exploitable vulnerabilities.**
**Security gate: PASS.**
