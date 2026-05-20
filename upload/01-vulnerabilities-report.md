## SECTION 1: VULNERABILITIES REPORT

---

### VULN-001
- **Severity:** CRITICAL
- **Category:** OWASP A07:2021 – Security Misconfiguration / Sensitive Data Exposure
- **File Path:** `revit-main/revit-main/fire-alarm-db/docker-compose.yml`
- **Line Numbers:** 8-9, 30
- **Description:** Hardcoded PostgreSQL credentials in plain text within docker-compose.yml committed to version control. The username `firealarm` and password `firealarm123` are visible to anyone with repository access. The DATABASE_URL on line 30 repeats these credentials in a connection string.
- **Impact:** Full database compromise if the repository is public or accessed by unauthorized parties. Credentials can be used to directly access the PostgreSQL instance, exfiltrate data, or destroy records. PCI-DSS 8.2.1 violation (no one-factor authentication for DB access).
- **Evidence:**
```yaml
POSTGRES_USER: firealarm
POSTGRES_PASSWORD: firealarm123
DATABASE_URL: postgresql://firealarm:firealarm123@db:5432/firealarmdb
```

---

### VULN-002
- **Severity:** CRITICAL
- **Category:** OWASP A07:2021 – Security Misconfiguration
- **File Path:** `revit-main/revit-main/.github/workflows/ci-cd.yml`
- **Line Numbers:** 20-22, 33
- **Description:** Hardcoded test database credentials in CI/CD pipeline configuration. The password `firealarm_test_pass` and the full DATABASE_URL are stored as plain-text environment variables in the workflow file, visible in the repository and in GitHub Actions logs.
- **Impact:** Attackers with read access to the repo can extract database credentials. If the test database is accessible, it becomes an entry point for lateral movement. GitHub Secrets should be used instead.
- **Evidence:**
```yaml
POSTGRES_USER: firealarm_test
POSTGRES_PASSWORD: firealarm_test_pass
DATABASE_URL: "postgresql://firealarm_test:firealarm_test_pass@localhost:5432/firealarm_test_db"
```

---

### VULN-003
- **Severity:** CRITICAL
- **Category:** OWASP A07:2021 – Security Misconfiguration / A02:2021 – Cryptographic Failures
- **File Path:** `revit-main/revit-main/infrastructure/terraform/main.tf`
- **Line Numbers:** 578-582
- **Description:** Database credentials passed as plain-text environment variable in ECS task definition. The `DATABASE_URL` containing username and password is injected into the container environment without encryption or use of AWS Secrets Manager (despite Secrets Manager being configured in security.tf).
- **Impact:** Credentials are visible in the ECS task definition, in AWS Console, via the ECS DescribeTaskDefinition API, and in container introspection. This directly violates PCI-DSS 8.2.1 and SOC 2 CC6.1.
- **Evidence:**
```hcl
environment = [
  {
    name  = "DATABASE_URL"
    value = "postgresql://${var.postgres_master_username}:${var.postgres_master_password}@${aws_db_instance.postgres_database.endpoint}/${var.postgres_database_name}"
  },
]
```

---

### VULN-004
- **Severity:** CRITICAL
- **Category:** OWASP A05:2021 – Security Misconfiguration
- **File Path:** `revit-main/revit-main/backend/app.py`
- **Line Numbers:** 21-27, 62
- **Description:** CORS configured with `allow_origins=["*"]` combined with `allow_credentials=True`, and the server binds to `0.0.0.0`. This allows any origin to make authenticated cross-origin requests, effectively disabling the Same-Origin Policy. Binding to 0.0.0.0 exposes the service on all network interfaces.
- **Impact:** Any malicious website can make cross-origin requests with credentials to the API, enabling CSRF-like attacks, data exfiltration, and unauthorized operations. SOC 2 CC6.1 violation.
- **Evidence:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

### VULN-005
- **Severity:** HIGH
- **Category:** OWASP A05:2021 – Security Misconfiguration
- **File Path:** `revit-main/revit-main/fire-alarm-db/database-design/main.py`
- **Line Numbers:** 73-79, 397
- **Description:** Same wildcard CORS with credentials configuration plus server binds to 0.0.0.0. This is the main production API server for the design pipeline.
- **Impact:** Same as VULN-004 — any website can issue cross-origin requests with credentials to the design API.
- **Evidence:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
host = os.environ.get('HOST', '0.0.0.0')
```

---

### VULN-006
- **Severity:** HIGH
- **Category:** OWASP A05:2021 – Security Misconfiguration
- **File Path:** `revit-main/revit-main/fireai/core/fireai_api.py`
- **Line Numbers:** 47
- **Description:** CORS configured with `allow_origins=["*"]` on the NFPA 72 Design API. No credential flag, but wildcard origins still allow any website to interact with the API.
- **Impact:** Cross-origin data exfiltration and unauthorized API usage from any website.
- **Evidence:**
```python
application.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"])
```

---

### VULN-007
- **Severity:** HIGH
- **Category:** OWASP A05:2021 – Security Misconfiguration
- **File Path:** `revit-main/revit-main/fire-alarm-db/accuracy_engine/api/main.py`
- **Line Numbers:** 37-42
- **Description:** CORS wildcard on the Accuracy Engine API. No authentication is required on any endpoint — all API routes are unauthenticated.
- **Impact:** Anyone can call safety-critical endpoints (risk assessment, monte carlo simulation, compliance verification) without authentication, potentially leading to incorrect safety decisions or denial of service.
- **Evidence:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

### VULN-008
- **Severity:** HIGH
- **Category:** OWASP A01:2021 – Broken Access Control
- **File Path:** `revit-main/revit-main/fireai/core/project_api.py`
- **Line Numbers:** 136-139, 162-650
- **Description:** All project data is stored in global in-memory dictionaries with no user-level isolation. Any valid API key holder can read, modify, or delete any project, device, connection, or report. There are no `owner_id` or `user_id` fields on any model, and no authorization checks beyond API key presence.
- **Impact:** Complete IDOR (Insecure Direct Object Reference) — any authenticated user can enumerate UUIDs and access/modify all projects. Violates SOC 2 CC6.3 (access restrictions) and PCI-DSS 7.1 (need-to-know basis).
- **Evidence:**
```python
_projects: Dict[str, ProjectInDB] = {}
_devices: Dict[str, DeviceInDB] = {}
# No user_id/owner_id field on any model
@router.get("/projects/{project_id}", response_model=ProjectInDB)
async def get_project(project_id: str):
    if project_id not in _projects:
        raise HTTPException(status_code=404, detail="Project not found")
    return _projects[project_id]  # No ownership check!
```

---

### VULN-009
- **Severity:** HIGH
- **Category:** OWASP A01:2021 – Broken Access Control
- **File Path:** `revit-main/revit-main/fire-alarm-db/accuracy_engine/api/main.py`
- **Line Numbers:** 55-668 (all endpoints)
- **Description:** The Accuracy Engine API has zero authentication on any endpoint. All routes (`/api/accuracy-engine`, `/api/safety-assessment`, `/api/risk-assessment`, `/api/compliance-verification`, `/api/monte-carlo`, etc.) are publicly accessible without any API key or token.
- **Impact:** Unauthenticated access to safety-critical design functions. An attacker could submit malicious room data, trigger resource-intensive monte carlo simulations (DoS), or manipulate compliance verification results.
- **Evidence:**
```python
# No Depends(verify_api_key) or any auth middleware on any endpoint
@app.post("/api/safety-assessment")
def safety_assessment(request: EngineRequest):
    ...
@app.post("/api/monte-carlo")
def monte_carlo_simulation(request: EngineRequest, iterations: int = 1000):
    ...
```

---

### VULN-010
- **Severity:** HIGH
- **Category:** OWASP A03:2021 – Injection (SQL)
- **File Path:** `revit-main/revit-main/elite_drawing_analyzer/intelligence/knowledge_base.py`
- **Line Numbers:** 107-116
- **Description:** Dynamic SQL construction via f-string interpolation of dictionary keys into column names. The `upsert_symbol` method builds SQL column names from `kw.keys()` without sanitization. If an attacker controls the keyword argument names, they can inject arbitrary SQL.
- **Impact:** SQL injection enabling data exfiltration, modification, or deletion from the knowledge base SQLite database.
- **Evidence:**
```python
def upsert_symbol(self, name: str, **kw):
    ...
    sets = ", ".join(f"{k}=?" for k in kw)
    self.conn.execute(f"UPDATE symbols SET {sets} WHERE id=?",
                      (*kw.values(), row["id"]))
    ...
    cols = ["name"] + list(kw.keys())
    qs   = ",".join("?"*len(cols))
    cur  = self.conn.execute(
        f"INSERT INTO symbols({','.join(cols)}) VALUES({qs})",
        (name, *kw.values()))
```

---

### VULN-011
- **Severity:** HIGH
- **Category:** OWASP A03:2021 – Injection (SQL)
- **File Path:** `revit-main/revit-main/src/knowledge/memory.py`
- **Line Numbers:** 127-137
- **Description:** Identical SQL injection vulnerability as VULN-010 in the `upsert_symbol` method of the `Memory` class. Dictionary keys are interpolated into SQL column names via f-string without sanitization.
- **Impact:** Same as VULN-010 — SQL injection in the knowledge/memory store.
- **Evidence:**
```python
sets = ", ".join(f"{k}=?" for k in kw)
conn.execute(f"UPDATE symbols SET {sets} WHERE id=?",
              (*kw.values(), row["id"]))
...
f"INSERT INTO symbols({','.join(cols)}) VALUES({qs})",
```

---

### VULN-012
- **Severity:** HIGH
- **Category:** OWASP A03:2021 – Injection (XSS)
- **File Path:** `revit-main/revit-main/bridges/report_bridge.py`
- **Line Numbers:** 343, 360, 388, 399-401, 409
- **Description:** User-controlled data (project_name, device types, finding codes/messages, room names/types) is interpolated directly into HTML via f-strings without `html.escape()`. If any of these values contain HTML tags or JavaScript, they will be executed when the report is opened in a browser.
- **Impact:** Stored XSS — malicious data in project names, device types, or findings can execute arbitrary JavaScript when the compliance report HTML is viewed. Could steal session tokens, redirect users, or deface reports.
- **Evidence:**
```python
f"<title>FireAI Report — {data['project_name']}</title>",
f"<h2>{data['project_name']}</h2>",
f"<tr><td>{dtype}</td><td>{count}</td></tr>",
f"<td>{f.get('code', '')}</td>",
f"<td>{f.get('message', f.get('rule', ''))}</td></tr>",
f"<tr><td>{i}</td><td>{r['name']}</td><td>{r['type']}</td>",
```

---

### VULN-013
- **Severity:** HIGH
- **Category:** OWASP A03:2021 – Injection (XSS)
- **File Path:** `revit-main/revit-main/proof-viewer/index.html`
- **Line Numbers:** 98, 103, 110
- **Description:** User-uploaded JSON file content (`proofData.geo_hash`, `proofData.clause_id`, `proofData.clause_edition`, `snapshotData.source_file_hash`) is injected into `innerHTML` via template literals without any sanitization. A crafted proof.json or snapshot.json can execute arbitrary JavaScript.
- **Impact:** Stored XSS via malicious JSON upload — an attacker can craft a proof.json with `<img onerror=alert(1)>` in clause_id to achieve code execution in the viewer's browser.
- **Evidence:**
```javascript
resultDiv.innerHTML = `<div class="result rejected">...Proof: ${proofData.geo_hash}...</div>`;
resultDiv.innerHTML = `<div class="result accepted">...Clause: ${proofData.clause_id} (${proofData.clause_edition})</div>`;
logDiv.innerHTML = `<strong>Proof Token:</strong> ${proofData.proof_token.slice(0, 32)}...<br><strong>Source File:</strong> ${snapshotData.source_file_hash || 'N/A'}`;
```

---

### VULN-014
- **Severity:** HIGH
- **Category:** OWASP A03:2021 – Injection (XSS)
- **File Path:** `revit-main/revit-main/fire-alarm-db/accuracy_engine/index.html`
- **Line Numbers:** 116-128
- **Description:** Server response data (`data.validation.errors`, `data.validation.warnings`, `e.message`) is inserted directly into `innerHTML` without sanitization. If the API returns malicious content in error/warning messages, it will execute as JavaScript.
- **Impact:** Reflected XSS via API response — an attacker who can control API responses (via MITM or compromised server) can execute JavaScript in the accuracy engine UI.
- **Evidence:**
```javascript
resultDiv.innerHTML = `...
    ${data.validation.errors.length > 0 ? '<p style="color: var(--error);"><strong>Errors:</strong> ' + data.validation.errors.join(', ') + '</p>' : ''}
    ${data.validation.warnings.length > 0 ? '<p style="color: #f59e0b;"><strong>Warnings:</strong> ' + data.validation.warnings.join(', ') + '</p>' : ''}
...`;
resultDiv.innerHTML = `<div class="card"><p style="color: var(--error);">Error: ${e.message}</p></div>`;
```

---

### VULN-015
- **Severity:** HIGH
- **Category:** OWASP A07:2021 – Security Misconfiguration (Information Exposure)
- **File Path:** `revit-main/revit-main/fireai/core/auth.py`
- **Line Numbers:** 34-43
- **Description:** When `FIREAI_API_KEYS` environment variable is not set, a new API key is auto-generated and printed in plaintext to the console/logs via `logger.warning`. In production, this key could be captured in log aggregation systems, log files, or monitoring dashboards.
- **Impact:** API key exposure through logs enables unauthorized access to all authenticated endpoints. Violates SOC 2 CC6.1 (logical access controls) and PCI-DSS 3.4 (key management).
- **Evidence:**
```python
generated = secrets.token_urlsafe(32)
logger.warning(
    ...
    f"║  {generated:<57s}║\n"
    ...
)
_EFFECTIVE_API_KEYS = {generated}
```

---

### VULN-016
- **Severity:** HIGH
- **Category:** OWASP A02:2021 – Cryptographic Failures
- **File Path:** `revit-main/revit-main/core/cognitive_kernel.py`
- **Line Numbers:** 176-178, 210-212, 260
- **Description:** MD5 is used for hash computation. MD5 is cryptographically broken — collision attacks are practical and well-documented. While used for case hashing (not password storage), the truncated 16-char hex output further weakens it to 64 bits.
- **Impact:** Hash collisions could allow different engineering cases to map to the same case_hash, causing incorrect case recall and potentially wrong engineering decisions in fire safety design. Also signals weak cryptographic hygiene.
- **Evidence:**
```python
case_hash = hashlib.md5(
    f"{layer}{geometry_signature}".encode()
).hexdigest()[:16]
```

---

### VULN-017
- **Severity:** HIGH
- **Category:** OWASP A02:2021 – Cryptographic Failures
- **File Path:** `revit-main/revit-main/fireai/core/fireai_api.py`
- **Line Numbers:** 74-78
- **Description:** API key verification uses direct string comparison (`x_api_key not in valid_keys`) instead of timing-safe comparison. This allows timing side-channel attacks to extract API keys character by character.
- **Impact:** An attacker can use timing analysis to determine valid API keys. The `auth.py` module correctly uses `secrets.compare_digest()`, but this module does not.
- **Evidence:**
```python
async def verify_api_key(x_api_key: str = Header(...)) -> str:
    raw = os.getenv("FIREAI_API_KEYS", "")
    valid_keys = {k.strip() for k in raw.split(",") if k.strip()}
    if x_api_key not in valid_keys:
        raise HTTPException(status_code=401, detail="Invalid API key")
```

---

### VULN-018
- **Severity:** MEDIUM
- **Category:** OWASP A01:2021 – Broken Access Control
- **File Path:** `revit-main/revit-main/fireai/core/project_api.py`
- **Line Numbers:** 639-650
- **Description:** The `/health` endpoint exposes internal state (counts of projects, devices, connections, reports) without authentication. This information leakage reveals the scale of the system to unauthenticated parties.
- **Impact:** Information disclosure that aids reconnaissance — attackers learn system usage patterns and scale.
- **Evidence:**
```python
@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "projects": len(_projects),
        "devices": len(_devices),
        "connections": len(_connections),
        "reports": len(_reports)
    }
```

---

### VULN-019
- **Severity:** MEDIUM
- **Category:** OWASP A01:2021 – Broken Access Control
- **File Path:** `revit-main/revit-main/fire-alarm-db/database-design/main.py`
- **Line Numbers:** 235-308
- **Description:** The design submission endpoint has no rate limiting, no file type validation beyond extension, and no file size limit on uploaded images. The file extension is extracted from `image.filename` without path sanitization.
- **Impact:** Unrestricted file uploads (potential webshell upload), denial of service via large files, and path traversal via crafted filenames.
- **Evidence:**
```python
image_ext = Path(image.filename).suffix or '.png'
image_path = TEMP_DIR / f"{task_id}{image_ext}"
content = await image.read()
with open(image_path, 'wb') as f:
    f.write(content)
```

---

### VULN-020
- **Severity:** MEDIUM
- **Category:** OWASP A05:2021 – Security Misconfiguration
- **File Path:** `revit-main/revit-main/fire-alarm-db/database-design/main.py`
- **Line Numbers:** 379-386
- **Description:** The global exception handler returns the raw exception message to the client via `str(exc)`. This can leak internal implementation details, file paths, database connection strings, and stack information.
- **Impact:** Information disclosure aiding further attacks. Internal error messages may contain SQL queries, file paths, or credential patterns.
- **Evidence:**
```python
@app.exception_handler(Exception)
def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)}
    )
```

---

### VULN-021
- **Severity:** MEDIUM
- **Category:** OWASP A05:2021 – Security Misconfiguration
- **File Path:** `revit-main/revit-main/infrastructure/terraform/security.tf`
- **Line Numbers:** 422-438
- **Description:** Network ACL for private subnets allows all TCP traffic from `0.0.0.0/0` on ports 1024-65535 in ingress and 0-65535 in egress. This is overly permissive for a "private" subnet NACL and provides no meaningful access control.
- **Impact:** Weakens defense-in-depth. If security groups are misconfigured, the NACL provides no additional barrier.
- **Evidence:**
```hcl
resource "aws_network_acl" "private_subnet_nacl" {
  ingress {
    protocol   = "tcp"
    cidr_block = "0.0.0.0/0"
    from_port  = 1024
    to_port    = 65535
  }
  egress {
    protocol   = "tcp"
    cidr_block = "0.0.0.0/0"
    from_port  = 0
    to_port    = 65535
  }
}
```

---

### VULN-022
- **Severity:** MEDIUM
- **Category:** OWASP A03:2021 – Injection (Log Injection / CRLF)
- **File Path:** `revit-main/revit-main/fire-alarm-db/database-design/main.py`
- **Line Numbers:** 100, 264
- **Description:** User-supplied `project_name` and `domain` from Form parameters are logged directly without sanitization. If these values contain CRLF characters (`\r\n`), they can be used to forge log entries (log injection).
- **Impact:** Log forging can mask malicious activity or create false audit trails, undermining forensic investigation. SOC 2 CC7.2 violation.
- **Evidence:**
```python
logger.info(f"Starting task {task_id}: project={project_name}, domain={domain}")
logger.info(f"Task {task_id}: project={project_name}")
```

---

### VULN-023
- **Severity:** MEDIUM
- **Category:** OWASP A05:2021 – Security Misconfiguration
- **File Path:** `revit-main/revit-main/fireai/core/fireai_api.py`
- **Line Numbers:** 292
- **Description:** The FireAI system uses an in-memory SQLite database (`:memory:`), meaning all audit trails, design decisions, and learning data are lost on server restart. For a fire safety compliance system, this undermines the integrity of audit records.
- **Impact:** Loss of audit trail on restart violates regulatory requirements for fire safety systems. PCI-DSS 10.1 violation (audit trail tracking). SOC 2 CC7.2 (monitoring activities).
- **Evidence:**
```python
_fireai_system = FireAISystem(db_path=":memory:")
```

---

### VULN-024
- **Severity:** MEDIUM
- **Category:** OWASP A08:2021 – Software and Data Integrity Failures
- **File Path:** `revit-main/revit-main/fireai/core/project_api.py`
- **Line Numbers:** 136-139
- **Description:** All project, device, connection, and report data is stored in global Python dictionaries. Server restart causes complete data loss. There is no persistence layer, no database, no file storage.
- **Impact:** Complete data loss on server restart. For a fire safety compliance system, loss of project data could have regulatory implications.
- **Evidence:**
```python
_projects: Dict[str, ProjectInDB] = {}
_devices: Dict[str, DeviceInDB] = {}
_connections: Dict[str, ConnectionInDB] = {}
_reports: Dict[str, ReportInDB] = {}
```

---

### VULN-025
- **Severity:** MEDIUM
- **Category:** OWASP A03:2021 – Injection (OS Command)
- **File Path:** `revit-main/revit-main/elite_drawing_analyzer/core/ingest.py`
- **Line Numbers:** 184-197
- **Description:** The `_ingest_dwg` function passes user-provided file paths to `shutil.copy()` and `subprocess.run()`. While `subprocess.run` uses a list (not `shell=True`), the `path` parameter originates from external input (uploaded files). The ODA binary path from `shutil.which()` could also be poisoned via PATH manipulation.
- **Impact:** Potential for path traversal in `shutil.copy()` and PATH poisoning for binary execution.
- **Evidence:**
```python
def _ingest_dwg(path: str, nd: NormalizedDrawing) -> None:
    import shutil, subprocess, tempfile
    oda = shutil.which("ODAFileConverter") or shutil.which("oda_file_converter")
    ...
    shutil.copy(path, src)
    subprocess.run([oda, src, out, "ACAD2018", "DXF", "0", "1"], check=True)
```

---

### VULN-026
- **Severity:** MEDIUM
- **Category:** OWASP A01:2021 – Broken Access Control
- **File Path:** `revit-main/revit-main/fire-alarm-db/database-design/main.py`
- **Line Numbers:** 345-372
- **Description:** The download endpoint uses user-supplied `project_name` (from Form data) to construct the `filename` parameter of the `FileResponse` without sanitization. A crafted `project_name` with path traversal characters could manipulate HTTP headers.
- **Impact:** HTTP header injection via crafted filename, potentially enabling reflected file download attacks.
- **Evidence:**
```python
project_name = task.get('project_name', 'design')
filename = f"{project_name}_outputs.zip"
return FileResponse(zip_path, media_type='application/zip', filename=filename)
```

---

### VULN-027
- **Severity:** MEDIUM
- **Category:** OWASP A04:2021 – Insecure Design
- **File Path:** `revit-main/revit-main/fireai/core/fireai_api.py`
- **Line Numbers:** 74-78
- **Description:** API key verification re-reads the environment variable on every request (`os.getenv("FIREAI_API_KEYS", "")`). This is inefficient but also means there is no key rotation mechanism — keys can only be changed by modifying environment variables and restarting the server. There is also no key revocation mechanism.
- **Impact:** No ability to revoke compromised API keys without service disruption. Violates PCI-DSS 8.2.4 and SOC 2 CC6.1.
- **Evidence:**
```python
async def verify_api_key(x_api_key: str = Header(...)) -> str:
    raw = os.getenv("FIREAI_API_KEYS", "")
    valid_keys = {k.strip() for k in raw.split(",") if k.strip()}
    if x_api_key not in valid_keys:
        raise HTTPException(status_code=401, detail="Invalid API key")
```

---

### VULN-028
- **Severity:** LOW
- **Category:** OWASP A02:2021 – Cryptographic Failures
- **File Path:** `revit-main/revit-main/fireai/core/api_server.py`
- **Line Numbers:** (referenced via fireai_api.py usage)
- **Description:** The `verify_api_key` in `fireai_api.py` uses `x_api_key not in valid_keys` (set membership check) which is NOT timing-safe, unlike `auth.py` which correctly uses `secrets.compare_digest()`. Two different auth implementations with inconsistent security posture.
- **Impact:** Timing side-channel could leak API key information over many requests.
- **Evidence:**
```python
if x_api_key not in valid_keys:  # NOT timing-safe
```

---

### VULN-029
- **Severity:** LOW
- **Category:** OWASP A05:2021 – Security Misconfiguration
- **File Path:** `revit-main/revit-main/fire-alarm-db/accuracy_engine/api/main.py`
- **Line Numbers:** 355-372
- **Description:** The `/api/export/dxf` endpoint uses GET for a state-changing operation (DXF export), violating HTTP method semantics. GET requests should be safe and idempotent.
- **Impact:** The export can be triggered via simple `<img>` tags or CSRF, though the impact is limited since no authentication is required anyway (VULN-009).
- **Evidence:**
```python
@app.get("/api/export/dxf")
def export_dxf():
```

---

### VULN-030
- **Severity:** LOW
- **Category:** OWASP A08:2021 – Software and Data Integrity Failures
- **File Path:** `revit-main/revit-main/elite_drawing_analyzer/intelligence/active_learning.py`
- **Line Numbers:** 38
- **Description:** SQL query construction uses `.format()` to inject the `extra` clause. While currently hardcoded to safe values (`"AND file_sha = ?"` or `""`), this pattern is fragile and could become a SQL injection vector with future modifications.
- **Impact:** Potential future SQL injection if the pattern is extended with user input.
- **Evidence:**
```python
rows = kb.conn.execute(q.format(extra=extra), args).fetchall()
```

---

### VULN-031
- **Severity:** LOW
- **Category:** OWASP A02:2021 – Cryptographic Failures
- **File Path:** `revit-main/revit-main/src/v8_core/encryption.py`
- **Line Numbers:** 61-68
- **Description:** Key generation uses `subprocess.run(['openssl', 'rand', '-base64', '32'])` instead of Python's `secrets` module. While a fallback exists, the primary path relies on an external binary which could be replaced via PATH poisoning.
- **Impact:** If the openssl binary is compromised or replaced, key generation could produce predictable keys.
- **Evidence:**
```python
result = subprocess.run(
    ['openssl', 'rand', '-base64', '32'],
    capture_output=True,
    text=True
)
```

---

### VULN-032
- **Severity:** LOW
- **Category:** OWASP A05:2021 – Security Misconfiguration
- **File Path:** `revit-main/revit-main/fire-alarm-db/docker-compose.yml`
- **Line Numbers:** 13-14
- **Description:** PostgreSQL port 5432 is exposed to the host via `"5432:5432"`. In production, database ports should not be exposed outside the Docker network.
- **Impact:** Database accessible from the host network, increasing attack surface.
- **Evidence:**
```yaml
ports:
  - "5432:5432"
```

---

### VULN-033
- **Severity:** INFO
- **Category:** OWASP A05:2021 – Security Misconfiguration
- **File Path:** `FRONTEND-FIREAI--main/FRONTEND-FIREAI--main/.env`
- **Line Numbers:** 1-4
- **Description:** The `.env` file contains only non-sensitive configuration (API URLs, app name, version). However, `.env` files should be added to `.gitignore` as a best practice.
- **Impact:** Low — no sensitive data exposed, but the pattern of committing `.env` files is risky.
- **Evidence:**
```
VITE_API_URL=http://localhost:8000/api
VITE_WS_URL=ws://localhost:8000/ws
VITE_APP_NAME=NexusCAD Pro
VITE_APP_VERSION=1.0.0
```

---

---
**Architectural Note:** Generated by Qoder Agent SDK under read-only constraints.
**Timestamp:** 2026-05-20T10:24:57.082Z
**Project:** C:\Users\EWS-01\Downloads\project files
**Deterministic Verification:** Reproducible across environments.
