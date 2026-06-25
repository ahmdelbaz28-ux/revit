#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# FireAI — Local Validation Matrix Execution Script
# ═══════════════════════════════════════════════════════════════════════════
# PDF Audit Phase 4: Evidence Capture and Reporting
# Per "From Prototype to Production-Grade" §Phase 4, Appendix D:
#   "The validation scripts should capture evidence from each check into a
#   timestamped directory. After a successful build, a script should package
#   this evidence into a compressed archive with a checksum."
#
# Usage:
#   chmod +x scripts/run_validation_matrix.sh
#   scripts/run_validation_matrix.sh
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

# === CONFIGURATION ===
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
EVIDENCE_BASE_DIR="logs/validation_run_${TIMESTAMP}"
mkdir -p "${EVIDENCE_BASE_DIR}"

LOG_FILE="${EVIDENCE_BASE_DIR}/execution_log.txt"
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "[*] Starting validation matrix execution at $(date)"
echo "[*] Evidence will be stored in: ${EVIDENCE_BASE_DIR}"
echo ""

# === TRACK EXIT CODES ===
RUFF_EXIT=0
MYPY_EXIT=0
PYTEST_EXIT=0
PIP_AUDIT_EXIT=0

# === HELPER FUNCTIONS ===
log_status() {
    echo "[*] $1"
}

capture_output() {
    local cmd_name="$1"; shift
    local cmd=("$@")
    local output_file="${EVIDENCE_BASE_DIR}/${cmd_name}.log"
    echo "[*] Running: ${cmd[*]}"
    if ! "${cmd[@]}" > "${output_file}" 2>&1; then
        echo "[-] Command '${cmd_name}' failed. Output saved to '${output_file}'."
        return 1
    else
        echo "[+] Command '${cmd_name}' succeeded. Output saved to '${output_file}'."
        return 0
    fi
}

# === EXECUTE VALIDATION MATRIX ===

# Gate 1: Static Analysis
log_status "=== Gate 1: Static Analysis ==="

if command -v ruff &>/dev/null; then
    capture_output "ruff_check" ruff check fireai/ --format=json || RUFF_EXIT=$?
    capture_output "ruff_format" ruff format --check fireai/ || RUFF_EXIT=$?
else
    log_status "ruff not installed — skipping lint check"
fi

# Gate 2: Test Suite
log_status "=== Gate 2: Test Suite ==="

if command -v pytest &>/dev/null; then
    if pytest tests/ -v --tb=short --cov=fireai --cov-report=term-missing \
        -o "addopts=" \
        --junitxml="${EVIDENCE_BASE_DIR}/pytest_results.xml" \
        > "${EVIDENCE_BASE_DIR}/pytest.log" 2>&1; then
        echo "[+] Test suite passed."
    else
        PYTEST_EXIT=$?
        echo "[-] Test suite failed with exit code ${PYTEST_EXIT}."
    fi
else
    log_status "pytest not installed — skipping test suite"
fi

# Gate 3: Dependency Audit
log_status "=== Gate 3: Dependency Audit ==="

if command -v pip-audit &>/dev/null; then
    capture_output "pip_audit" pip-audit -r requirements.txt --format=json || PIP_AUDIT_EXIT=$?
else
    log_status "pip-audit not installed — skipping dependency audit"
fi

# Gate 4: Environment Verification
log_status "=== Gate 4: Environment Verification ==="
{
    echo "=== ENVIRONMENT DETAILS ==="
    echo "Python Version:"
    python3 --version 2>/dev/null || python --version
    echo ""
    echo "=== INSTALLED PACKAGES ==="
    pip list 2>/dev/null || pip3 list 2>/dev/null
} > "${EVIDENCE_BASE_DIR}/environment_details.log"

# === GENERATE SUMMARY ===
log_status "=== Generating Summary ==="

SUMMARY_FILE="${EVIDENCE_BASE_DIR}/SUMMARY.md"
cat > "${SUMMARY_FILE}" << EOF
# Validation Run Summary
- **Timestamp:** ${TIMESTAMP}
- **Git Commit Hash:** $(git rev-parse HEAD 2>/dev/null || echo "unknown")
- **Ruff Exit Code:** ${RUFF_EXIT}
- **Pytest Exit Code:** ${PYTEST_EXIT}
- **Pip-audit Exit Code:** ${PIP_AUDIT_EXIT}

## Overall Result
EOF

if [ "${RUFF_EXIT}" -eq 0 ] && [ "${PYTEST_EXIT}" -eq 0 ] && [ "${PIP_AUDIT_EXIT}" -eq 0 ]; then
    echo "The validation matrix has **PASSED**. All checks have passed successfully." >> "${SUMMARY_FILE}"
    echo "[+] SUCCESS: All validation checks passed."
else
    echo "The validation matrix has **FAILED**. At least one check has failed." >> "${SUMMARY_FILE}"
    echo "[-] FAILURE: One or more validation checks have failed. Do not commit."
fi

# Package the evidence directory
ARCHIVE_NAME="${EVIDENCE_BASE_DIR}.tar.gz"
tar -czf "${ARCHIVE_NAME}" "${EVIDENCE_BASE_DIR}" 2>/dev/null || true

# Calculate SHA256 checksum
SHA256_CHECKSUM=$(sha256sum "${ARCHIVE_NAME}" 2>/dev/null | cut -d' ' -f1 || echo "checksum_unavailable")

cat >> "${SUMMARY_FILE}" << EOF

## Archive Details
- **Archive Name:** ${ARCHIVE_NAME}
- **SHA256 Checksum:** \`${SHA256_CHECKSUM}\`
EOF

echo ""
echo "[*] Validation completed."
echo "[*] Evidence package created: ${ARCHIVE_NAME}"
echo "[*] SHA256 Checksum: ${SHA256_CHECKSUM}"
echo "[*] Please review the full logs in ${EVIDENCE_BASE_DIR} and the SUMMARY.md."

# Exit with proper code — V117 FIX: ALL gates must pass, not just pytest
# Previous version only checked PYTEST_EXIT, allowing ruff/pip-audit failures
# to go undetected. For a safety-critical system, ALL gates are mandatory.
if [ "${RUFF_EXIT}" -ne 0 ] || [ "${PYTEST_EXIT}" -ne 0 ] || [ "${PIP_AUDIT_EXIT}" -ne 0 ]; then
    echo "[-] FAILURE: Gate failures detected:"
    [ "${RUFF_EXIT}" -ne 0 ] && echo "  - Ruff (lint/format): FAILED (exit ${RUFF_EXIT})"
    [ "${PYTEST_EXIT}" -ne 0 ] && echo "  - Pytest (test suite): FAILED (exit ${PYTEST_EXIT})"
    [ "${PIP_AUDIT_EXIT}" -ne 0 ] && echo "  - Pip-audit (dependencies): FAILED (exit ${PIP_AUDIT_EXIT})"
    exit 1
fi
exit 0
