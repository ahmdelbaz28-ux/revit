## SECTION 3: FIX CODES

---

### VULN-001: docker-compose.yml — Remove Hardcoded Credentials

```yaml
# revit-main/revit-main/fire-alarm-db/docker-compose.yml
version: '3.8'

services:
  db:
    image: postgres:15
    container_name: firealarm-db
    environment:
      # Security Fix: Use environment variable references instead of hardcoded credentials
      POSTGRES_USER: ${POSTGRES_USER:-firealarm}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}
      POSTGRES_DB: ${POSTGRES_DB:-firealarmdb}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    # Security Fix: Do not expose DB port to host; use internal Docker networking
    # If needed for development, bind to localhost only:
    # ports:
    #   - "127.0.0.1:5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-firealarm}"]
      interval: 5s
      timeout: 5s
      retries: 5

  app:
    build:
      context: .
      dockerfile: fire-alarm-db/Dockerfile
    container_name: firealarm-app
    depends_on:
      db:
        condition: service_healthy
    environment:
      # Security Fix: Use environment variable references instead of hardcoded URL
      DATABASE_URL: postgresql://${POSTGRES_USER:-firealarm}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB:-firealarmdb}
      MODEL_PATH: ./best.pt
      HOST: 127.0.0.1  # Security Fix: Bind to localhost, not 0.0.0.0
      PORT: 8000
    ports:
      - "8000:8000"
    volumes:
      - ./fire-alarm-db:/app/fire-alarm-db
    restart: unless-stopped

volumes:
  postgres_data:
```

---

### VULN-002: ci-cd.yml — Use GitHub Secrets

```yaml
# revit-main/revit-main/.github/workflows/ci-cd.yml
name: "FireAlarmAI CI/CD Pipeline"
on:
  push:
    branches: ["main"]
  pull_request:
    branches: ["main"]

env:
  PYTHONUNBUFFERED: "1"

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    services:
      postgres:
        image: postgres:15-alpine
        env:
          # Security Fix: Use GitHub Secrets for database credentials
          POSTGRES_USER: ${{ secrets.TEST_POSTGRES_USER }}
          POSTGRES_PASSWORD: ${{ secrets.TEST_POSTGRES_PASSWORD }}
          POSTGRES_DB: ${{ secrets.TEST_POSTGRES_DB }}
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
          --tmpfs /var/lib/postgresql/data

    env:
      # Security Fix: Use GitHub Secrets for DATABASE_URL
      DATABASE_URL: "postgresql://${{ secrets.TEST_POSTGRES_USER }}:${{ secrets.TEST_POSTGRES_PASSWORD }}@localhost:5432/${{ secrets.TEST_POSTGRES_DB }}"

    steps:
      - name: "Checkout repository"
        uses: actions/checkout@v4
        with:
          fetch-depth: 1
          lfs: false

      - name: "Setup Python"
        uses: actions/setup-python@v5
        with:
          python-version: "3.10"
          cache: "pip"
          cache-dependency-path: "fire-alarm-db/database-design/requirements.txt"

      - name: "Install system dependencies"
        run: |
          sudo apt-get update -qq
          sudo apt-get install -y -qq libgomp1 libgl1 libglib2.0-0 tesseract-ocr tesseract-ocr-ara

      - name: "Install Python dependencies"
        run: |
          python -m pip install --upgrade pip setuptools wheel
          pip install -r fire-alarm-db/database-design/requirements.txt
          pip install pytest pytest-cov pytest-xdist pytest-timeout

      - name: "Run unit tests with coverage"
        run: |
          pytest fire-alarm-db/database-design/test_ai_design.py \
            fire-alarm-db/database-design/test_multi_domain.py \
            -v --tb=short --timeout=120 \
            --cov=fire-alarm-db/database-design \
            --cov-report=xml \
            --cov-report=term-missing \
            -n auto || echo "Tests completed with warnings"
        timeout-minutes: 15

      - name: "Upload coverage to artifact"
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: "coverage-report"
          path: "coverage.xml"
          retention-days: 7

  lint:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    continue-on-error: true

    steps:
      - name: "Checkout repository"
        uses: actions/checkout@v4

      - name: "Setup Python"
        uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: "Install linters"
        run: |
          python -m pip install --upgrade pip
          pip install flake8

      - name: "Run flake8 (critical errors only)"
        run: |
          flake8 fire-alarm-db/ --count --select=E9,F63,F7,F82 --show-source --statistics || echo "Lint check completed with warnings"
```

---

### VULN-003: main.tf — Use Secrets Manager for DB Credentials

```hcl
# revit-main/revit-main/infrastructure/terraform/main.tf
# Replace the environment block in aws_ecs_task_definition.api (around line 567-608)

  container_definitions = jsonencode([
    {
      name  = "api"
      image = "${aws_ecr_repository.api_repository.repository_url}:latest"
      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
        }
      ]
      # Security Fix: Use secrets from AWS Secrets Manager instead of plaintext env vars
      secrets = [
        {
          name      = "DATABASE_URL"
          valueFrom = "${aws_secretsmanager_secret.database_secret.arn}:DATABASE_URL::"
        }
      ]
      environment = [
        {
          name  = "MODEL_PATH"
          value = "/app/models/best.pt"
        },
        {
          name  = "OUTPUT_DIR"
          value = "/app/outputs"
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/${var.project_name}-${var.environment_name}-api"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/healthz || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])
```

Additionally, add a Secrets Manager secret version resource:

```hcl
# Add to main.tf or security.tf
resource "aws_secretsmanager_secret_version" "database_secret_value" {
  secret_id = aws_secretsmanager_secret.database_secret.id
  secret_string = jsonencode({
    DATABASE_URL = "postgresql://${var.postgres_master_username}:${var.postgres_master_password}@${aws_db_instance.postgres_database.endpoint}/${var.postgres_database_name}"
  })
}
```

---

### VULN-004 & VULN-005: CORS + 0.0.0.0 Fix (backend/app.py and database-design/main.py)

```python
# revit-main/revit-main/backend/app.py
"""FireAI Digital Twin - Main Application Entry Point
Security Fix: Restricted CORS origins and localhost binding
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="FireAI Digital Twin",
    description="Digital Twin for BIM coordination",
    version="1.0.0"
)

# Security Fix: Read allowed CORS origins from environment variable
# In production, set CORS_ORIGINS=https://your-domain.com,https://app.your-domain.com
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

# Import core modules
try:
    from core.database import UniversalDataModel
    logger.info("Core modules loaded successfully")
except ImportError as e:
    logger.error(f"Failed to load core modules: {e}")

@app.on_event("startup")
async def startup():
    """Initialize on startup"""
    logger.info("FireAI Digital Twin started")

@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown"""
    logger.info("FireAI Digital Twin stopped")

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "FireAI Digital Twin API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health():
    """Health check endpoint — no internal data exposed"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    # Security Fix: Bind to localhost by default; use reverse proxy in production
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
```

```python
# revit-main/revit-main/fire-alarm-db/database-design/main.py
# Replace lines 72-79 and 397 with:
import os

# Security Fix: Restricted CORS origins
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

# ... (later in the file, line 397):
    # Security Fix: Bind to localhost by default
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', 8000))
```

---

### VULN-008: IDOR Fix — Add Ownership Checks (project_api.py)

```python
# revit-main/revit-main/fireai/core/project_api.py
# Add owner_id field to models and ownership checks to endpoints

# === Add to model definitions (after line 44) ===

class ProjectInDB(ProjectBase):
    id: str
    owner_id: str = ""  # Security Fix: Track who owns this project
    createdAt: datetime
    updatedAt: datetime
    status: str = "active"
    deviceCount: int = 0
    connectionCount: int = 0

class DeviceInDB(DeviceBase):
    id: str
    projectId: str
    owner_id: str = ""  # Security Fix: Track ownership
    createdAt: datetime
    updatedAt: datetime

# === Modify verify_api_key to return user identity ===

async def verify_api_key_with_identity(api_key: str = Security(API_KEY_HEADER)) -> str:
    """Verify API key and return a user identity string.
    Security Fix: Maps API keys to user identities for ownership tracking.
    """
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required.")
    
    # Map API key to user identity (extend this with your user management)
    import hashlib
    user_id = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    
    if not any(secrets.compare_digest(api_key, valid_key) for valid_key in _EFFECTIVE_API_KEYS):
        raise HTTPException(status_code=401, detail="Invalid API key.")
    
    return user_id

# === Add ownership check helper ===

def _check_ownership(resource, user_id: str):
    """Security Fix: Verify the authenticated user owns this resource."""
    if resource.owner_id and resource.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied: resource belongs to another user")

# === Example: Updated endpoint with ownership check ===

@router.get("/projects/{project_id}", response_model=ProjectInDB)
async def get_project(project_id: str, user_id: str = Depends(verify_api_key_with_identity)):
    """Get a specific project by ID — ownership verified."""
    if project_id not in _projects:
        raise HTTPException(status_code=404, detail="Project not found")
    project = _projects[project_id]
    _check_ownership(project, user_id)  # Security Fix
    return project
```

---

### VULN-009: Add Authentication to Accuracy Engine

```python
# revit-main/revit-main/fire-alarm-db/accuracy_engine/api/main.py
# Add at top of file, after imports:

import os
import secrets
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

# Security Fix: Add API key authentication
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

def _get_valid_api_keys() -> set:
    """Load API keys from environment variable."""
    raw = os.getenv("FIREAI_API_KEYS", "")
    return {k.strip() for k in raw.split(",") if k.strip()}

async def verify_api_key(api_key: str = Security(API_KEY_HEADER)) -> str:
    """Security Fix: Verify API key for all endpoints."""
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required. Pass X-API-Key header.")
    valid_keys = _get_valid_api_keys()
    if not valid_keys:
        raise HTTPException(status_code=503, detail="Service not configured: FIREAI_API_KEYS not set.")
    if not any(secrets.compare_digest(api_key, k) for k in valid_keys):
        raise HTTPException(status_code=401, detail="Invalid API key.")
    return api_key

# Then add `dependencies=[Depends(verify_api_key)]` to each route:
@app.post("/api/accuracy-engine", dependencies=[Depends(verify_api_key)])
def run_engine(request: EngineRequest):
    ...

@app.post("/api/safety-assessment", dependencies=[Depends(verify_api_key)])
def safety_assessment(request: EngineRequest):
    ...

# Apply to ALL endpoints similarly
```

---

### VULN-010 & VULN-011: SQL Injection Fix in upsert_symbol

```python
# revit-main/revit-main/elite_drawing_analyzer/intelligence/knowledge_base.py
# Replace upsert_symbol method (lines 102-118) with:

# Security Fix: Whitelist of allowed column names to prevent SQL injection
_SYMBOL_COLUMNS = frozenset({
    "category", "description", "standard_spacing_m", "coverage_radius_m", "meta"
})

def upsert_symbol(self, name: str, **kw):
    # Security Fix: Validate column names against whitelist
    invalid_keys = set(kw.keys()) - _SYMBOL_COLUMNS
    if invalid_keys:
        raise ValueError(
            f"Invalid symbol columns: {invalid_keys}. "
            f"Allowed: {_SYMBOL_COLUMNS}"
        )
    
    cur = self.conn.execute("SELECT id FROM symbols WHERE name=?", (name,))
    row = cur.fetchone()
    if row:
        if kw:
            # Security Fix: Column names are now validated against whitelist
            sets = ", ".join(f"{k}=?" for k in kw)
            self.conn.execute(f"UPDATE symbols SET {sets} WHERE id=?",
                              (*kw.values(), row["id"]))
            self.conn.commit()
        return row["id"]
    cols = ["name"] + list(kw.keys())
    qs   = ",".join("?"*len(cols))
    cur  = self.conn.execute(
        f"INSERT INTO symbols({','.join(cols)}) VALUES({qs})",
        (name, *kw.values()))
    self.conn.commit()
    return cur.lastrowid
```

Apply the identical fix to `revit-main/revit-main/src/knowledge/memory.py` lines 121-138.

---

### VULN-012: XSS Fix in Report Bridge

```python
# revit-main/revit-main/bridges/report_bridge.py
# Add import at top (after line 29):
from html import escape as _html_escape

# Security Fix: Helper function for HTML escaping
def _h(value) -> str:
    """HTML-escape user-controlled data to prevent XSS."""
    return _html_escape(str(value))

# Then replace all f-string interpolations of user data in _generate_html:

def _generate_html(path: str, data: dict):
    """Generate HTML report (self-contained, dark theme)."""
    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        # Security Fix: Escape project_name in title
        f"<title>FireAI Report — {_h(data['project_name'])}</title>",
        "<style>",
        # ... (CSS unchanged) ...
        "</style></head><body>",
        f"<h1>FireAI — NFPA 72 Compliance Report</h1>",
        f"<div class='card'>",
        # Security Fix: Escape project_name in heading
        f"<h2>{_h(data['project_name'])}</h2>",
        f"<p>Date: {_h(data['generated_at'])}</p>",
        f"<p>Audit Hash: <code>{_h(data['audit_hash'])}</code></p>",
    ]

    # ... (proof status unchanged) ...

    # Device schedule
    parts.append("<div class='card'><h3>Device Schedule</h3><table>"
                 "<tr><th>Type</th><th>Count</th></tr>")
    for dtype, count in sorted(data["device_counts"].items()):
        # Security Fix: Escape dtype
        parts.append(f"<tr><td>{_h(dtype)}</td><td>{count}</td></tr>")
    parts.append(f"<tr><td><b>TOTAL</b></td><td><b>{data['total_devices']}</b></td></tr>")
    parts.append("</table></div>")

    # Findings
    if data["findings"]:
        parts.append("<div class='card'><h3>Compliance Findings</h3><table>"
                     "<tr><th>Severity</th><th>Code</th><th>Message</th></tr>")
        for f in data["findings"]:
            sev = f.get("severity", "info")
            parts.append(
                f"<tr><td><span class='sev {_h(sev)}'>{_h(sev)}</span></td>"
                # Security Fix: Escape code and message
                f"<td>{_h(f.get('code', ''))}</td>"
                f"<td>{_h(f.get('message', f.get('rule', '')))}</td></tr>")
        parts.append("</table></div>")

    # Room details
    parts.append("<div class='card'><h3>Room Details</h3><table>"
                 "<tr><th>#</th><th>Name</th><th>Type</th><th>Area</th><th>Devices</th></tr>")
    for i, r in enumerate(data["room_summary"], 1):
        parts.append(
            # Security Fix: Escape room name and type
            f"<tr><td>{i}</td><td>{_h(r['name'])}</td><td>{_h(r['type'])}</td>"
            f"<td>{r['area_m2']:.1f} m2</td><td>{r['device_count']}</td></tr>")
    parts.append("</table></div>")

    # ... (disclaimer unchanged) ...

    parts.append("</body></html>")
    Path(path).write_text("".join(parts), encoding="utf-8")
```

---

### VULN-013: XSS Fix in Proof Viewer

```html
<!-- revit-main/revit-main/proof-viewer/index.html -->
<!-- Replace the verifyAll function (lines 86-111) with: -->

<script>
    // Security Fix: HTML escaping function to prevent XSS
    function sanitize(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // ... (canonicalJSON, computeGeoHash, setupDropZone unchanged) ...

    function verifyAll() {
        if (!proofData || !snapshotData) return;
        
        const geom = snapshotData.snapshot || snapshotData;
        const computedGeoHash = computeGeoHash(geom);
        
        const resultDiv = document.getElementById('result');
        const logDiv = document.getElementById('log');
        const mapContainer = document.getElementById('map-container');
        
        if (computedGeoHash !== proofData.geo_hash) {
            // Security Fix: Escape all dynamic content
            resultDiv.innerHTML = `<div class="result rejected">&#x274C; REJECTED - Geometry Hash Mismatch<br><span class="hash">Proof: ${sanitize(proofData.geo_hash)}</span><br><span class="hash">Computed: ${sanitize(computedGeoHash)}</span></div>`;
            mapContainer.style.display = 'none';
            return;
        }

        // Security Fix: Escape clause_id and clause_edition
        resultDiv.innerHTML = `<div class="result accepted">&#x2705; ACCEPTED - Proof is Mathematically Valid<br>Clause: ${sanitize(proofData.clause_id)} (${sanitize(proofData.clause_edition)})</div>`;
        
        renderMap(geom);
        mapContainer.style.display = 'block';
        
        logDiv.style.display = 'block';
        // Security Fix: Escape proof_token and source_file_hash
        logDiv.innerHTML = `<strong>Proof Token:</strong> ${sanitize(proofData.proof_token.slice(0, 32))}...<br><strong>Source File:</strong> ${sanitize(snapshotData.source_file_hash || 'N/A')}`;
    }
</script>
```

---

### VULN-014: XSS Fix in Accuracy Engine UI

```html
<!-- revit-main/revit-main/fire-alarm-db/accuracy_engine/index.html -->
<!-- Replace the runEngine function (lines 97-130) with: -->

<script>
    // Security Fix: HTML escaping function
    function sanitize(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    async function runEngine() {
        const resultDiv = document.getElementById('result');
        resultDiv.innerHTML = '<div class="card"><p>Running...</p></div>';

        try {
            const rooms = JSON.parse(document.getElementById('roomsInput').value);
            const response = await fetch('/api/accuracy-engine', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ rooms })
            });

            const data = await response.json();

            const isValid = data.validation.is_valid;
            const badgeClass = isValid ? 'badge-success' : 'badge-error';
            const badgeText = isValid ? 'VALID' : 'INVALID';

            // Security Fix: Escape all dynamic server data before insertion
            const totalDevices = parseInt(data.total_devices) || 0;
            const coverageScore = parseFloat(data.validation.coverage_score) || 0;
            const errors = (data.validation.errors || []).map(sanitize).join(', ');
            const warnings = (data.validation.warnings || []).map(sanitize).join(', ');
            const devicesPre = sanitize(JSON.stringify(data.devices, null, 2));

            resultDiv.innerHTML = `
                <div class="card">
                    <h2>Result</h2>
                    <span class="badge ${badgeClass}">${badgeText}</span>
                    <p style="margin-top: 10px;"><strong>Devices:</strong> ${totalDevices}</p>
                    <p><strong>Coverage Score:</strong> ${coverageScore.toFixed(1)}%</p>
                    ${errors ? '<p style="color: var(--error);"><strong>Errors:</strong> ' + errors + '</p>' : ''}
                    ${warnings ? '<p style="color: #f59e0b;"><strong>Warnings:</strong> ' + warnings + '</p>' : ''}
                    <pre>${devicesPre}</pre>
                </div>
            `;
        } catch (e) {
            // Security Fix: Escape error message
            resultDiv.innerHTML = `<div class="card"><p style="color: var(--error);">Error: ${sanitize(e.message)}</p></div>`;
        }
    }
</script>
```

---

### VULN-015: API Key Logged to Console

```python
# revit-main/revit-main/fireai/core/auth.py
# Replace lines 32-43 with:

def _init_api_keys() -> None:
    """Initialize API keys from environment variable."""
    global _EFFECTIVE_API_KEYS
    keys_str = os.environ.get("FIREAI_API_KEYS", "")
    if keys_str:
        _EFFECTIVE_API_KEYS = {k.strip() for k in keys_str.split(",") if k.strip()}
    else:
        # Fallback: single key for backward compat
        single_key = os.environ.get("FIREAI_API_KEY")
        if single_key:
            _EFFECTIVE_API_KEYS = {single_key}
        else:
            # Security Fix: Generate key but DO NOT log it in plaintext
            generated = secrets.token_urlsafe(32)
            # Write the generated key to a file with restricted permissions instead
            key_file = os.path.join(os.getcwd(), ".generated_api_key")
            with open(key_file, 'w') as f:
                f.write(generated)
            os.chmod(key_file, 0o600)
            
            logger.warning(
                "\n"
                "╔══════════════════════════════════════════════════════════════╗\n"
                "║  FIREAI_API_KEYS not set — auto-generated for dev.         ║\n"
                "║  Key saved to: .generated_api_key                         ║\n"
                "║  Set FIREAI_API_KEYS=key1,key2,... for production.         ║\n"
                "║  NEVER use auto-generated keys in production!              ║\n"
                "╚══════════════════════════════════════════════════════════════╝"
            )
            _EFFECTIVE_API_KEYS = {generated}
```

---

### VULN-016: Replace MD5 with SHA-256

```python
# revit-main/revit-main/core/cognitive_kernel.py
# Replace all hashlib.md5 usage (lines 176-178, 210-212, 260) with:

# Security Fix: Replace MD5 with SHA-256 for collision resistance
case_hash = hashlib.sha256(
    f"{layer}{geometry_signature}".encode()
).hexdigest()[:32]  # Use 32 hex chars (128 bits) minimum instead of 16
```

---

### VULN-017: Timing-Safe API Key Comparison

```python
# revit-main/revit-main/fireai/core/fireai_api.py
# Replace lines 74-78 with:

import secrets

async def verify_api_key(x_api_key: str = Header(...)) -> str:
    """Verify API key using timing-safe comparison.
    Security Fix: Use secrets.compare_digest instead of set membership.
    """
    raw = os.getenv("FIREAI_API_KEYS", "")
    valid_keys = {k.strip() for k in raw.split(",") if k.strip()}
    if not valid_keys:
        raise HTTPException(status_code=503, detail="Service not configured: FIREAI_API_KEYS not set")
    # Security Fix: Timing-safe comparison to prevent timing attacks
    if not any(secrets.compare_digest(x_api_key, k) for k in valid_keys):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key
```

---

### VULN-018: Health Endpoint Information Leakage

```python
# revit-main/revit-main/fireai/core/project_api.py
# Replace lines 639-650 with:

@router.get("/health")
async def health_check():
    """Health check endpoint — minimal information only.
    Security Fix: Removed internal state counts from unauthenticated endpoint.
    """
    return {
        "status": "healthy",
        "service": "project-management-api",
        "timestamp": _now().isoformat(),
    }

# Add authenticated stats endpoint for monitoring:
@router.get("/stats", dependencies=[Depends(verify_api_key)])
async def get_stats():
    """Internal stats endpoint — requires authentication.
    Security Fix: Moved sensitive counts behind auth.
    """
    return {
        "projects": len(_projects),
        "devices": len(_devices),
        "connections": len(_connections),
        "reports": len(_reports)
    }
```

---

### VULN-019: File Upload Validation

```python
# revit-main/revit-main/fire-alarm-db/database-design/main.py
# Replace the elite_design endpoint (lines 235-308) with:

import re
from pathlib import Path

# Security Fix: Allowed file extensions and max size
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.pdf', '.dwg', '.dxf'}
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

def _sanitize_filename(filename: str) -> str:
    """Security Fix: Remove path components and validate filename."""
    # Strip directory components
    filename = os.path.basename(filename)
    # Remove any non-alphanumeric characters except dots, hyphens, underscores
    filename = re.sub(r'[^\w\s.-]', '', filename)
    return filename

@app.post("/api/elite-design")
async def elite_design(
    image: UploadFile = File(None),
    project_name: str = Form(...),
    standard: str = Form('egyptian'),
    domain: str = Form('FireAlarm')
):
    """Submit a new design task with security validations."""
    if not PIPELINE_AVAILABLE:
        raise HTTPException(status_code=500, detail="Pipeline not available")
    
    if not image:
        raise HTTPException(status_code=400, detail="Image required")
    
    # Security Fix: Sanitize filename and validate extension
    safe_filename = _sanitize_filename(image.filename or "")
    image_ext = Path(safe_filename).suffix.lower()
    if image_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{image_ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}"
        )
    
    # Security Fix: Enforce maximum upload size
    content = await image.read()
    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE_BYTES // (1024*1024)} MB"
        )
    if not content:
        raise HTTPException(status_code=400, detail="Empty file uploaded")
    
    # Generate task ID
    task_id = str(uuid.uuid4())
    logger.info(f"Task {task_id}: project=%s", re.sub(r'[\r\n]', '', project_name))
    
    # Security Fix: Use sanitized filename
    image_path = TEMP_DIR / f"{task_id}{image_ext}"
    
    try:
        with open(image_path, 'wb') as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to save image")
    
    # ... (rest of endpoint unchanged) ...
```

---

### VULN-020: Generic Error Messages

```python
# revit-main/revit-main/fire-alarm-db/database-design/main.py
# Replace lines 379-386 with:

import uuid as _uuid

@app.exception_handler(Exception)
def global_exception_handler(request, exc):
    """Global exception handler — returns generic error to client.
    Security Fix: No internal details exposed to client.
    """
    # Generate a reference ID for log correlation
    ref_id = str(_uuid.uuid4())[:8]
    logger.error(f"[{ref_id}] Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "reference_id": ref_id  # For support correlation only
        }
    )
```

---

### VULN-022: Log Injection Prevention

```python
# Add a utility function to sanitize log inputs:
# Can be added as a shared utility module

import re

def sanitize_for_log(value: str) -> str:
    """Security Fix: Remove CRLF characters to prevent log injection."""
    if not isinstance(value, str):
        value = str(value)
    # Remove carriage return and line feed characters
    return re.sub(r'[\r\n]', '_', value)

# Usage example in database-design/main.py:
# Replace: logger.info(f"Starting task {task_id}: project={project_name}, domain={domain}")
# With:
logger.info(f"Starting task {task_id}: project={sanitize_for_log(project_name)}, domain={sanitize_for_log(domain)}")
```

---

### VULN-023 & VULN-027: Persistent DB + Key Caching

```python
# revit-main/revit-main/fireai/core/fireai_api.py
# Replace line 292 with:

# Security Fix: Use file-based database for persistent audit trail
_db_path = os.getenv("FIREAI_DB_PATH", "fireai_data/fireai.sqlite")
os.makedirs(os.path.dirname(_db_path) if os.path.dirname(_db_path) else ".", exist_ok=True)
_fireai_system = FireAISystem(db_path=_db_path)
```

---

### VULN-031: Remove Subprocess for Key Generation

```python
# revit-main/revit-main/src/v8_core/encryption.py
# Replace generate_key method (lines 51-87) with:

@staticmethod
def generate_key(key_path: str) -> str:
    """Generate and save a new master key.
    Security Fix: Use secrets module instead of subprocess/openssl.
    """
    import secrets
    
    # Security Fix: Use Python's secrets module (cryptographically secure, no subprocess)
    key_bytes = secrets.token_bytes(32)
    key_b64 = base64.urlsafe_b64encode(key_bytes).decode()
    
    # Ensure directory exists
    key_dir = os.path.dirname(key_path)
    if key_dir:
        os.makedirs(key_dir, exist_ok=True)
    
    # Write key with restricted permissions
    with open(key_path, 'wb') as f:
        f.write(key_b64.encode())
    
    os.chmod(key_path, 0o600)  # Owner read/write only
    
    return key_path
```

---

**End of Security Audit Report**

**Summary Statistics:**
- Total vulnerabilities found: 33
- CRITICAL: 4
- HIGH: 13
- MEDIUM: 10
- LOW: 5
- INFO: 1

**Top Priority Actions:**
1. Rotate all hardcoded credentials immediately (VULN-001, 002, 003)
2. Restrict CORS origins on all 4 API servers (VULN-004, 005, 006, 007)
3. Add HTML escaping to all report/viewer outputs (VULN-012, 013, 014)
4. Validate SQL column names against whitelist (VULN-010, 011)
5. Add authentication to the Accuracy Engine API (VULN-009)
6. Add ownership tracking to project data (VULN-008)

---
**Architectural Note:** Generated by Qoder Agent SDK under read-only constraints.
**Timestamp:** 2026-05-20T10:24:57.082Z
**Project:** C:\Users\EWS-01\Downloads\project files
**Deterministic Verification:** Reproducible across environments.
