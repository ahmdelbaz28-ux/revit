## SECTION 2: REMEDIATION PLAN

---

### VULN-001: Hardcoded DB Credentials in docker-compose.yml
- **Priority:** P0 (Critical)
- **Steps:**
  1. Remove hardcoded credentials from docker-compose.yml
  2. Use Docker secrets or `.env` file (not committed to VCS) for credential injection
  3. Change `POSTGRES_USER` and `POSTGRES_PASSWORD` to reference environment variables: `${POSTGRES_USER}`, `${POSTGRES_PASSWORD}`
  4. Create a `.env.example` file with placeholder values
  5. Ensure `.env` is in `.gitignore`
  6. Rotate the compromised `firealarm123` password immediately
- **Effort:** 1 hour
- **Verification:** Grep the repository for `firealarm123` — should return zero results. Verify `.env` is in `.gitignore`.
- **Regression Risk:** Low

---

### VULN-002: Hardcoded DB Credentials in CI/CD Pipeline
- **Priority:** P0 (Critical)
- **Steps:**
  1. Replace hardcoded credentials in ci-cd.yml with GitHub Secrets: `${{ secrets.POSTGRES_USER }}`, `${{ secrets.POSTGRES_PASSWORD }}`, `${{ secrets.DATABASE_URL }}`
  2. Add the secrets in the GitHub repository settings (Settings → Secrets and variables → Actions)
  3. Rotate the test database password
- **Effort:** 30 minutes
- **Verification:** Check that ci-cd.yml contains no plaintext passwords. Run the CI/CD pipeline to confirm it works with secrets.
- **Regression Risk:** Low

---

### VULN-003: DB Credentials in ECS Task Definition
- **Priority:** P0 (Critical)
- **Steps:**
  1. Remove the `DATABASE_URL` from the `environment` block in the ECS task definition
  2. Add it as a `secrets` block referencing AWS Secrets Manager:
     ```hcl
     secrets = [{
       name      = "DATABASE_URL"
       valueFrom = aws_secretsmanager_secret.database_secret.arn
     }]
     ```
  3. Store the DATABASE_URL value in AWS Secrets Manager using the already-provisioned `aws_secretsmanager_secret.database_secret`
  4. Ensure the ECS task execution role has `secretsmanager:GetSecretValue` permission (already configured)
- **Effort:** 2 hours
- **Verification:** `aws ecs describe-task-definition` should show the secret ARN reference, not the plaintext URL.
- **Regression Risk:** Medium (requires ECS task redeployment)

---

### VULN-004: Wildcard CORS + Credentials + 0.0.0.0 Binding
- **Priority:** P0 (Critical)
- **Steps:**
  1. Replace `allow_origins=["*"]` with an explicit list of allowed origins read from environment variable
  2. Remove `allow_credentials=True` when using wildcard origins, or use specific origins
  3. Change `host="0.0.0.0"` to `host="127.0.0.1"` for local development, or use a reverse proxy in production
  4. Example: `allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")`
- **Effort:** 30 minutes
- **Verification:** Run the server and verify that cross-origin requests from unauthorized domains are rejected.
- **Regression Risk:** Low

---

### VULN-005: Same as VULN-004 (database-design/main.py)
- **Priority:** P1 (High)
- **Steps:** Same remediation as VULN-004
- **Effort:** 30 minutes
- **Verification:** Same as VULN-004
- **Regression Risk:** Low

---

### VULN-006: Wildcard CORS (fireai_api.py)
- **Priority:** P1 (High)
- **Steps:**
  1. Replace `allow_origins=["*"]` with environment-variable-driven origin list
  2. The `api_server.py` file already has a better pattern reading `FIREAI_CORS_ORIGINS` — adopt that pattern
- **Effort:** 15 minutes
- **Verification:** Test that only specified origins can make cross-origin requests
- **Regression Risk:** Low

---

### VULN-007: Wildcard CORS + No Auth (accuracy_engine)
- **Priority:** P1 (High)
- **Steps:**
  1. Add CORS origin restrictions (same as VULN-004)
  2. Add authentication middleware (API key verification) to all endpoints — use the pattern from `auth.py`
  3. At minimum, protect all POST endpoints that trigger computation
- **Effort:** 2 hours
- **Verification:** Unauthenticated requests to `/api/safety-assessment` should return 401
- **Regression Risk:** Medium (existing clients will need API keys)

---

### VULN-008: IDOR / No User Ownership (project_api.py)
- **Priority:** P1 (High)
- **Steps:**
  1. Add `owner_id` field to `ProjectInDB`, `DeviceInDB`, `ConnectionInDB`, `ReportInDB` models
  2. Set `owner_id` from the authenticated user context on creation
  3. Add ownership checks to all GET/PUT/DELETE endpoints: verify `resource.owner_id == current_user_id`
  4. Replace in-memory storage with a persistent database
- **Effort:** 8 hours (significant refactoring)
- **Verification:** User A cannot access User B's projects by UUID
- **Regression Risk:** High (requires data model changes)

---

### VULN-009: No Authentication on Accuracy Engine
- **Priority:** P1 (High)
- **Steps:**
  1. Add FastAPI `Depends(verify_api_key)` to all endpoints
  2. Import and use the `verify_api_key` function from `auth.py` or implement a similar pattern
  3. Add rate limiting to compute-intensive endpoints (monte carlo, risk assessment)
- **Effort:** 2 hours
- **Verification:** All endpoints return 401 without valid API key
- **Regression Risk:** Medium (existing unauthenticated clients will break)

---

### VULN-010 & VULN-011: SQL Injection in upsert_symbol
- **Priority:** P1 (High)
- **Steps:**
  1. Replace dynamic column name construction with a whitelist of allowed column names
  2. Validate all `kw.keys()` against the schema before interpolation
  3. Alternatively, use an ORM (SQLAlchemy) that handles SQL construction safely
- **Effort:** 2 hours
- **Verification:** Attempt to inject SQL via column name (e.g., `upsert_symbol("test", **{"name; DROP TABLE symbols--": "value"})`) — should raise ValueError
- **Regression Risk:** Low

---

### VULN-012: XSS in HTML Report Generation
- **Priority:** P1 (High)
- **Steps:**
  1. Import `html.escape` at the top of `report_bridge.py`
  2. Wrap all user-controlled data in `html.escape()` before interpolation into HTML
  3. Apply to: `data['project_name']`, `dtype`, `f.get('code', '')`, `f.get('message', ...)`, `r['name']`, `r['type']`
- **Effort:** 1 hour
- **Verification:** Create a project with name `<script>alert(1)</script>` and verify the HTML output escapes it
- **Regression Risk:** Low

---

### VULN-013: XSS in Proof Viewer
- **Priority:** P1 (High)
- **Steps:**
  1. Create a `sanitize(str)` function that escapes `<`, `>`, `&`, `"`, `'`
  2. Apply it to all data from `proofData` and `snapshotData` before inserting into `innerHTML`
  3. Alternatively, use `textContent` or DOM manipulation instead of `innerHTML`
- **Effort:** 1 hour
- **Verification:** Upload a proof.json with `clause_id: "<img onerror=alert(1) src=x>"` — should not execute
- **Regression Risk:** Low

---

### VULN-014: XSS in Accuracy Engine UI
- **Priority:** P1 (High)
- **Steps:**
  1. Sanitize all API response data before inserting into `innerHTML`
  2. Use `textContent` for error messages instead of `innerHTML`
  3. Escape all dynamic content using a DOM text node approach or a sanitization library
- **Effort:** 1 hour
- **Verification:** Same approach as VULN-013
- **Regression Risk:** Low

---

### VULN-015: API Key Logged to Console
- **Priority:** P1 (High)
- **Steps:**
  1. Remove the plaintext key from the log message
  2. Log only a warning that `FIREAI_API_KEYS` is not set, without revealing the generated key
  3. If the key must be communicated, write it to a file with restricted permissions instead of logging
- **Effort:** 30 minutes
- **Verification:** Start the server without `FIREAI_API_KEYS` — the generated key should not appear in logs
- **Regression Risk:** Low

---

### VULN-016: MD5 Usage in Cognitive Kernel
- **Priority:** P2 (Medium)
- **Steps:**
  1. Replace `hashlib.md5()` with `hashlib.sha256()`
  2. Keep the full hash output instead of truncating to 16 hex chars
  3. If truncation is needed for performance, use at least 32 hex chars (128 bits)
- **Effort:** 30 minutes
- **Verification:** Run cognitive kernel tests and verify hash uniqueness
- **Regression Risk:** Low (hash values will change, invalidating existing stored hashes)

---

### VULN-017: Timing-Unsafe API Key Comparison
- **Priority:** P2 (Medium)
- **Steps:**
  1. Replace `x_api_key not in valid_keys` with timing-safe comparison
  2. Use `any(secrets.compare_digest(x_api_key, k) for k in valid_keys)`
  3. Import `secrets` module if not already imported
- **Effort:** 15 minutes
- **Verification:** Verify the comparison takes constant time regardless of input
- **Regression Risk:** Low

---

### VULN-018: Information Leakage in Health Endpoint
- **Priority:** P2 (Medium)
- **Steps:**
  1. Remove the detailed counts from the health endpoint
  2. Return only `{"status": "healthy"}` 
  3. Create a separate `/stats` endpoint with authentication for internal monitoring
- **Effort:** 15 minutes
- **Verification:** `/health` returns no internal counts; `/stats` requires auth
- **Regression Risk:** Low

---

### VULN-019: Unrestricted File Upload
- **Priority:** P2 (Medium)
- **Steps:**
  1. Add file size limit (e.g., 10MB max)
  2. Validate MIME type by reading file magic bytes, not just extension
  3. Sanitize filename: strip path components, validate extension against a whitelist
  4. Store uploads in a non-executable directory
  5. Add rate limiting to the upload endpoint
- **Effort:** 2 hours
- **Verification:** Try uploading a 100MB file, a file with `.php` extension, and a file with `../` in filename
- **Regression Risk:** Low

---

### VULN-020: Verbose Error Messages
- **Priority:** P2 (Medium)
- **Steps:**
  1. Replace `str(exc)` with a generic error message: `"Internal server error"`
  2. Log the full exception server-side only
  3. Return a reference ID that can be correlated with the server log
- **Effort:** 30 minutes
- **Verification:** Trigger an error and verify the response contains no internal details
- **Regression Risk:** Low

---

### VULN-021: Permissive NACL Rules
- **Priority:** P2 (Medium)
- **Steps:**
  1. Restrict NACL ingress to the VPC CIDR block only
  2. Restrict egress to specific destinations (RDS subnet, NAT gateway)
  3. Remove `0.0.0.0/0` from private subnet NACL rules
- **Effort:** 1 hour
- **Verification:** `terraform plan` shows only restricted CIDR blocks
- **Regression Risk:** Medium (could block legitimate traffic if not careful)

---

### VULN-022: Log Injection
- **Priority:** P2 (Medium)
- **Steps:**
  1. Sanitize all user-supplied values before logging by stripping `\r` and `\n`
  2. Create a `sanitize_for_log(value)` utility function
  3. Apply it to all `logger.info(f"... {user_data} ...")` calls
- **Effort:** 2 hours (multiple files)
- **Verification:** Submit `project_name="test\r\nFAKE LOG ENTRY"` and verify no forged log entry appears
- **Regression Risk:** Low

---

### VULN-023: In-Memory Database for Audit Trail
- **Priority:** P2 (Medium)
- **Steps:**
  1. Change `db_path=":memory:"` to a file-based SQLite path
  2. Use an environment variable: `os.getenv("FIREAI_DB_PATH", "fireai_data/fireai.sqlite")`
  3. Ensure the data directory is created on startup
- **Effort:** 1 hour
- **Verification:** Restart the server and verify audit data persists
- **Regression Risk:** Low

---

### VULN-024: In-Memory Data Storage
- **Priority:** P2 (Medium)
- **Steps:**
  1. Replace in-memory dictionaries with a persistent database (PostgreSQL or SQLite)
  2. Use SQLAlchemy ORM for data models
  3. Add database migration support (Alembic)
- **Effort:** 16 hours (significant refactoring)
- **Verification:** Restart server and verify data persists
- **Regression Risk:** High (major architectural change)

---

### VULN-025: OS Command Injection Risk
- **Priority:** P2 (Medium)
- **Steps:**
  1. Validate file path input: ensure it doesn't contain path traversal sequences
  2. Use the existing `_validate_path()` function from `src/kernel/ingest.py`
  3. Resolve the ODA binary path once at startup rather than on each call
  4. Verify the resolved binary path is within expected directories
- **Effort:** 2 hours
- **Verification:** Try passing `../../../etc/passwd` as path and verify it's rejected
- **Regression Risk:** Low

---

### VULN-026: Filename Header Injection
- **Priority:** P2 (Medium)
- **Steps:**
  1. Sanitize `project_name` by removing any characters that are not alphanumeric, spaces, hyphens, or underscores
  2. Use `re.sub(r'[^\w\s-]', '', project_name)` or similar
  3. Validate the sanitized filename is not empty
- **Effort:** 30 minutes
- **Verification:** Submit `project_name="../../../etc"` and verify the download filename is clean
- **Regression Risk:** Low

---

### VULN-027: No API Key Rotation
- **Priority:** P2 (Medium)
- **Steps:**
  1. Cache the API keys from environment variables on startup rather than re-reading on each request
  2. Implement a key rotation endpoint that refreshes the cache
  3. Support multiple active keys simultaneously for zero-downtime rotation
- **Effort:** 2 hours
- **Verification:** Rotate API key while server is running without dropping requests
- **Regression Risk:** Low

---

### VULN-028: Inconsistent Auth Implementation
- **Priority:** P3 (Low)
- **Steps:**
  1. Consolidate all API key verification to use the `auth.py` module
  2. Remove the inline `verify_api_key` function from `fireai_api.py`
  3. Import from `fireai.core.auth` everywhere
- **Effort:** 1 hour
- **Verification:** All API endpoints use the same auth function
- **Regression Risk:** Low

---

### VULN-029: GET for State-Changing Operation
- **Priority:** P4 (Info)
- **Steps:**
  1. Change `@app.get("/api/export/dxf")` to `@app.post("/api/export/dxf")`
  2. Update any clients that call this endpoint
- **Effort:** 15 minutes
- **Verification:** Verify the endpoint only responds to POST
- **Regression Risk:** Low

---

### VULN-030: Format String in SQL Query
- **Priority:** P3 (Low)
- **Steps:**
  1. Replace `.format(extra=extra)` with a conditional query construction using `if/else`
  2. Use separate parameterized queries for each variant instead of dynamic string building
- **Effort:** 30 minutes
- **Verification:** No `.format()` calls in SQL query strings
- **Regression Risk:** Low

---

### VULN-031: Subprocess for Key Generation
- **Priority:** P3 (Low)
- **Steps:**
  1. Swap the primary and fallback: use `secrets.token_bytes(32)` as the primary method
  2. Remove the `subprocess.run(['openssl', ...])` call entirely
  3. The `secrets` module is the Python standard for cryptographic randomness
- **Effort:** 15 minutes
- **Verification:** Key generation works without `openssl` binary available
- **Regression Risk:** Low

---

### VULN-032: Exposed Database Port
- **Priority:** P3 (Low)
- **Steps:**
  1. Remove the `ports: ["5432:5432"]` mapping from docker-compose.yml
  2. Use Docker's internal networking for app-to-database communication
  3. If host access is needed for development, use `"127.0.0.1:5432:5432"` instead
- **Effort:** 10 minutes
- **Verification:** `docker compose up` — verify port 5432 is not accessible from host
- **Regression Risk:** Low

---

### VULN-033: .env File in Repository
- **Priority:** P4 (Info)
- **Steps:**
  1. Add `.env` to `.gitignore`
  2. Keep only `.env.example` with placeholder values in the repository
- **Effort:** 10 minutes
- **Verification:** `git status` does not show `.env` as a tracked file
- **Regression Risk:** Low

---

---
**Architectural Note:** Generated by Qoder Agent SDK under read-only constraints.
**Timestamp:** 2026-05-20T10:24:57.082Z
**Project:** C:\Users\EWS-01\Downloads\project files
**Deterministic Verification:** Reproducible across environments.
