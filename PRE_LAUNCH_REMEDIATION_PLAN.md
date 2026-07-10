# 🔴 PRE-LAUNCH SECURITY & COMPLIANCE REMEDIATION PLAN
## OWASP + Best Practices Checklist - Action Items

**Date Generated:** 2026-06-16  
**Current Environment:** Python 3.8.4  
**Required Environment:** Python 3.12+  
**Status:** BLOCKED - Runtime Version Non-Compliance

---

## 🚨 CRITICAL BLOCKER

### Python Version Compliance
**Status:** ❌ FAILED  
**Detected:** `Python 3.8.4`  
**Required:** `Python 3.12+` per project specification memory  
**Impact:** All build, test, and code generation operations prohibited below 3.12+  

**Resolution Steps:**
```powershell
# Option 1: Install Python 3.12+ locally
# Download from: https://www.python.org/downloads/
# Verify: python --version  (should output 3.12.x or higher)

# Option 2: Use Docker (project includes Dockerfile)
docker build -t revit-dev .

# Option 3: Use pyenv for version management
winget install Python.Python.3.12
```

---

## 🔐 1. SECURITY (OWASP Top 10 + Best Practices)

### ✅ COMPLETED SECURITY MEASURES
The following protections are **already implemented**:

| Security Control | Status | Evidence |
|-----------------|--------|----------|
| **API Key Authentication** | ✅ Implemented | `backend/app.py` - ApiKeyMiddleware validates X-API-Key on all requests |
| **Role-Based Access Control (RBAC)** | ✅ Implemented | `backend/rbac.py` - Permission matrix with Role enum |
| **Rate Limiting** | ✅ Implemented | `backend/app.py` - PerPathRateLimitMiddleware with longest-prefix match |
| **CORS Configuration** | ✅ Implemented | Fail-closed CORS with explicit origin list |
| **Security Headers** | ✅ Implemented | CSP, HSTS, X-Frame-Options, X-Content-Type-Options |
| **CSRF Protection** | ⚠️ Partially | CSRFMiddleware skeleton exists but needs production implementation |
| **WebSocket Auth** | ✅ Implemented | `backend/routers/sync.py` - HMAC-based auth before connection tracking |
| **Input Validation** | ✅ Partially | Pydantic models in routers (e.g., `backend/routers/qomn.py`) |
| **Correlation IDs** | ✅ Implemented | `backend/request_context.py` - X-Correlation-ID middleware |
| **Request Body Size Limits** | ✅ Implemented | RequestBodySizeMiddleware (10MB JSON, 100MB multipart) |
| **Security Logging** | ✅ Implemented | `fireai/core/tests/test_security_logging.py` - mask_sensitive() function |

### ⚠️ REMEDIATION REQUIRED

#### Item 1.1: Complete CSRF Middleware Implementation
**Risk Level:** HIGH  
**File:** `backend/app.py` (CSRFMiddleware class)  
**Current State:** Placeholder implementation with comment: `"For now, we'll implement a basic check"`  

**Fix Required:**
```python
# Current placeholder at line ~507
if not csrf_token:
    response = Response(
        content=json.dumps({
            "success": False, 
            "error": "Missing CSRF token"
        }),
        status_code=403,
        media_type="application/json"
    )
```

**Action Plan:**
1. Implement secure CSRF token generation using `secrets.token_urlsafe()`
2. Store tokens server-side (Redis/session store)
3. Add validation middleware that checks token against request session
4. Rotate tokens on state-changing operations
5. Document CSRF protection in API documentation

**Verification Command:**
```bash
python -c "from backend.app import CSRFMiddleware; print('CSRFMiddleware importable')"
```

---

#### Item 1.2: Verify No Hardcoded Secrets
**Risk Level:** CRITICAL  
**Files to Audit:**
- `fireai/core/tests/test_security_logging.py`
- `tests/test_security.py`
- `tests/test_security_logging_v2.py`
- `backend/api_keys.py`
- `blackbox_mcp_settings.json`

**Detection Command:**
```powershell
grep -rni "(?i)(password|secret|api_key|token)\s*=\s*['\"][^'\"]+['\"]" --include="*.py" --exclude-dir=tests .
```

**Current Findings:**
- Test files contain example secrets (acceptable if clearly marked as test data)
- Production configuration must use environment variables only

**Fix Required:**
1. Create `.env.example` with all required environment variables
2. Verify `backend/app.py` loads config via `os.getenv()` or `python-decouple`
3. Add pre-commit hook to scan for secrets using `git-secrets` or `detect-secrets`

**Documentation Update:**
Create `docs/ENVIRONMENT_VARIABLES.md`:
```markdown
## Required Environment Variables

### Authentication
- `FIREAI_API_KEY` - Master API key for all requests (required in production)
- `FIREAI_ENV` - Deployment environment: "development" or "production"

### Database
- `DATABASE_URL` - PostgreSQL connection string

### Third-Party Services
- `GEMINI_API_KEY` - Google Gemini LLM API key
- `OPENAI_API_KEY` - OpenAI API key (optional, for fallback)

### CORS
- `CORS_ORIGINS` - Comma-separated list of allowed origins (production only)
```

---

#### Item 1.3: Error Message Sanitization
**Risk Level:** MEDIUM  
**Scope:** All router files in `backend/routers/`  

**Audit Checklist:**
- [ ] Verify no stack traces returned to clients
- [ ] Confirm exception handlers catch all `Exception` types
- [ ] Check logging contains debug info, responses contain generic messages
- [ ] Validate error formatting in `backend/response.py`

**Standard Error Response Format:**
```python
from backend.response import error_response

# Instead of:
raise HTTPException(status_code=500, detail=str(e))

# Use:
logger.error(f"Internal error: {e}", exc_info=True, extra={"path": scope.get("path")})
raise HTTPException(
    status_code=500,
    detail="An unexpected error occurred. Please contact support."
)
```

**Verification Test:**
```python
def test_error_sanitization(client):
    """Ensure errors don't leak internal details."""
    resp = client.post("/api/v1/nonexistent-endpoint", json={})
    assert 500 not in [200, 201, 204]  # Triggers error path
    body = resp.json()
    assert "traceback" not in str(body).lower()
    assert "stack" not in str(body).lower()
```

---

#### Item 1.4: HTTPS Everywhere (Production)
**Risk Level:** CRITICAL  
**Status:** Need verification in deployment configuration

**Fix Required:**
1. Configure TLS termination at reverse proxy level (nginx/Traefik)
2. Enable HSTS header (already present in `backend/app.py`):
   ```python
   headers.append([b"strict-transport-security", b"max-age=31536000; includeSubDomains"])
   ```
3. Redirect all HTTP → HTTPS in load balancer
4. Set secure flag on all cookies (frontend)

**Verification:**
```bash
curl -I http://your-domain.com/api/v1/health
# Should redirect to https:// or return 403
```

---

#### Item 1.5: Dependency Vulnerability Scanning
**Risk Level:** HIGH  
**Tools Required:**
- `pip-audit` (Python)
- `npm audit` (frontend)
- Snyk or Semgrep (optional, advanced)

**Execution Commands:**
```powershell
# Python dependencies
pip install pip-audit
pip-audit

# Frontend dependencies
cd frontend
npm audit
npm audit fix

# Advanced scanning (Semgrep)
semgrep --config=auto .
```

**Remediation Workflow:**
1. Scan all dependencies
2. Categorize vulnerabilities by CVSS score (>9.0 = critical)
3. Update packages with vulnerable versions
4. Document unpatched risks with justification
5. Create ticket for next patch cycle

---

## ⚡ 2. PERFORMANCE

### Item 2.1: Database Query Optimization (N+1 Prevention)
**Risk Level:** HIGH  
**Files to Review:**
- `backend/db_service.py`
- All router files with database access

**Detection Pattern:**
```python
# BAD (N+1 query)
for project in projects:
    owner = db.query(User).filter(id=project.owner_id).first()  # N queries!

# GOOD (Eager loading)
projects = db.query(Project).options(joinedload(Project.owner)).all()
```

**Fix Required:**
1. Search for `.first()` or `.all()` inside loops
2. Replace with SQLAlchemy `joinedload()` or `subqueryload()`
3. Add query count assertions in integration tests

---

### Item 2.2: Caching Strategy
**Risk Level:** MEDIUM  
**Current State:** Partial caching in `backend/services/geocoding_service.py`

**Recommended Caching Layers:**
1. **In-Memory Cache** (L1): For frequently accessed, rarely changing data
   ```python
   from functools import lru_cache
   
   @lru_cache(maxsize=1024)
   def get_standard_code(region_code: str) -> StandardConfig:
       ...
   ```

2. **Redis Cache** (L2): For API responses, user sessions
   ```python
   import redis
   r = redis.Redis(host='localhost', port=6379, db=0)
   
   def cached_get(endpoint: str):
       key = f"cache:{endpoint}"
       data = r.get(key)
       if data:
           return json.loads(data)
       result = fetch_data(endpoint)
       r.setex(key, 300, json.dumps(result))  # 5 min TTL
       return result
   ```

3. **CDN Cache** (L3): For static assets (frontend)

---

### Item 2.3: Memory Leak Detection
**Risk Level:** HIGH  
**Testing Required:**
```bash
# Run under memory profiler for 1 hour
python -m tracemalloc backend/server.py
# Monitor for unbounded growth
```

**Common Causes to Audit:**
- Circular references in middleware
- Unclosed database connections
- Event listeners not cleaned up
- Large datasets loaded without pagination

---

### Item 2.4: Load Testing
**Risk Level:** CRITICAL (Safety-Critical System)  
**Tool:** Locust or k6

**Example Locust Script:**
```python
from locust import HttpUser, task, between

class APIUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(3)
    def get_health(self):
        self.client.get("/api/v1/health")
    
    @task(1)
    def parse_drawing(self):
        # Simulate heavy operation
        pass
```

**Execute:**
```bash
pip install locust
locust -f tests/load_test.py --host=http://localhost:8000
```

**Target Metrics:**
- 95th percentile response time < 500ms
- 99th percentile response time < 2s
- Error rate < 0.1%
- Concurrent users: 100+

---

## 🛡️ 3. RELIABILITY

### Item 3.1: Error Handling for Edge Cases
**Audit Points:**
- Network timeouts (external APIs: weather, geocoding)
- Invalid PDF/DXF file formats
- Empty or malformed JSON payloads
- Database connection failures

**Retry Pattern (tenacity library):**
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(httpx.Timeout)
)
async def fetch_weather_data(lat: float, lon: float):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"https://api.weather.com/...", params={"lat": lat, "lon": lon})
        resp.raise_for_status()
        return resp.json()
```

---

### Item 3.2: Circuit Breaker Pattern
**Use Case:** External services (OpenWeather, Nominatim, etc.)

**Implementation:**
```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failures = 0
        self.threshold = failure_threshold
        self.last_failure = None
        self.recovery_timeout = recovery_timeout
    
    async def call(self, func, *args, **kwargs):
        if self.should_fail():
            raise CircuitOpenError("Service temporarily unavailable")
        
        try:
            result = await func(*args, **kwargs)
            self.reset()
            return result
        except Exception as e:
            self.record_failure()
            raise

# Usage
breaker = CircuitBreaker()

async def get_air_quality(lat, lon):
    return await breaker.call(fetch_air_quality_api, lat, lon)
```

---

### Item 3.3: Logging Standards
**Current State:** `logging.getLogger(__name__)` used throughout

**Requirements:**
1. Structured logging (JSON format in production)
2. Log levels: DEBUG < INFO < WARNING < ERROR < CRITICAL
3. Correlation ID in every log line

**Implementation:**
```python
import structlog

logger = structlog.get_logger()

# In middleware
async def __call__(self, scope, receive, send):
    correlation_id = scope["state"]["correlation_id"]
    
    logger.info(
        "request_started",
        method=scope["method"],
        path=scope["path"],
        correlation_id=correlation_id
    )
```

**Verification:**
```bash
python -c "import logging; handler = logging.StreamHandler(); logger = logging.getLogger(); logger.addHandler(handler); logger.setLevel(logging.INFO)"
```

---

## 🧪 4. TESTING

### Item 4.1: Unit Tests for Core Logic
**Coverage Target:** >70% for critical paths

**Critical Modules Needing Tests:**
- `backend/auth.py` - Authentication logic
- `backend/rbac.py` - Permission matrix
- `backend/db_service.py` - Database operations
- `parsers/dxf_parser.py` - File parsing
- `fireai/core/qomn_kernel.py` - Engineering calculations

**Test Structure:**
```python
# tests/test_auth.py
import pytest
from backend.auth import get_current_role, require_permission
from backend.rbac import Role, Permission

class TestGetCurrentRole:
    def test_returns_admin_from_state(self):
        request = Mock(spec=Request)
        request.state.fireai_role = Role.ADMIN
        assert get_current_role(request) == Role.ADMIN
    
    def test_defaults_to_viewer(self):
        request = Mock(spec=Request)
        assert get_current_role(request) == Role.VIEWER
```

---

### Item 4.2: Integration Tests for APIs
**Scope:** All endpoints in `backend/routers/`

**Template:**
```python
# tests/test_api_endpoints.py
class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert "uptime_seconds" in resp.json()
    
    def test_health_security_headers(self, client):
        resp = client.get("/api/v1/health")
        assert "x-frame-options" in resp.headers
        assert "content-security-policy" in resp.headers
```

**Run Tests:**
```bash
pip install pytest pytest-cov
pytest --cov=backend --cov-report=html --cov-fail-under=70
```

---

### Item 4.3: Edge Cases Coverage
**Test Matrix:**
- Valid inputs → Success (200/201)
- Invalid inputs → Validation error (422)
- Missing auth → Forbidden (403)
- Resource not found → Not found (404)
- Rate limit exceeded → Too many requests (429)
- Server error → Internal error (500) with sanitized message

---

## 📊 5. CODE QUALITY

### Item 5.1: SOLID Principles Audit

**Single Responsibility:**
- [ ] Each router handles one domain
- [ ] Service classes do one type of work
- [ ] Middleware functions have single purpose

**Open/Closed:**
- [ ] New permissions added without modifying existing code
- [ ] Extension points documented

**Dependency Inversion:**
- [ ] High-level modules depend on abstractions
- [ ] DI pattern used in FastAPI deps

---

### Item 5.2: DRY (Don't Repeat Yourself)
**Common Patterns to Extract:**
- Error response formatting → `backend/response.py`
- Input validation → Shared Pydantic base models
- Database session management → Context manager or dependency

---

### Item 5.3: Naming Conventions
**Standards:**
- Modules: `snake_case`
- Classes: `PascalCase`
- Functions: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private members: `_leading_underscore`

---

### Item 5.4: Dead Code Removal
**Search Command:**
```powershell
# Find unused imports
pip install flake8-unused-arguments
flake8 --select=F401,F541 .

# Find unreachable code
mypy --warn-unreachable backend/
```

---

## 📚 6. DOCUMENTATION

### Item 6.1: README Update Required
**Sections to Add:**
```markdown
## Quick Start
1. Install Python 3.12+
2. Clone repo and navigate to project
3. Create virtual environment: `python -m venv .venv`
4. Activate: `.venv\\Scripts\\activate` (Windows) or `source .venv/bin/activate` (Linux/Mac)
5. Install dependencies: `pip install -e .`
6. Copy `.env.example` to `.env` and fill in values
7. Run migrations: `alembic upgrade head`
8. Start server: `uvicorn backend.app:app --reload`

## Environment Variables
See [ENVIRONMENT_VARIABLES.md](docs/ENVIRONMENT_VARIABLES.md)

## API Documentation
Access interactive docs at http://localhost:8000/docs

## Testing
```bash
pytest --cov=backend
```

## Security
See [SECURITY.md](SECURITY.md) for security model
```

---

### Item 6.2: API Documentation
**Current State:** OpenAPI schema auto-generated by FastAPI

**Enhancements Needed:**
1. Add detailed descriptions to all endpoints
2. Add request/response schemas with examples
3. Document error codes and meanings
4. Add authentication examples

**Implementation:**
```python
@router.get(
    "/api/v1/health",
    summary="Health check endpoint",
    description="Returns system health status and uptime",
    responses={
        200: {
            "description": "System healthy",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "uptime_seconds": 3600,
                        "version": "1.0.0"
                    }
                }
            }
        },
        503: {
            "description": "Database connection failed"
        }
    }
)
async def health_check():
    ...
```

---

### Item 6.3: Deployment Guide
**Create:** `docs/DEPLOYMENT.md`

**Sections:**
1. Prerequisites (Python 3.12+, Docker, PostgreSQL)
2. Local development setup
3. Docker deployment
4. Kubernetes deployment (helm charts exist in `deploy/helm/`)
5. Production checklist
6. Monitoring setup
7. Backup/restore procedures

---

### Item 6.4: Changelog Update
**Format:** [Keep a Changelog](https://keepachangelog.com/)

```markdown
# Changelog

## [Unreleased]

### Added
- Pre-launch security compliance documentation
- OWASP Top 10 remediation plan

### Changed
- [Nothing yet -待 release]

### Deprecated
- [Nothing yet]

### Removed
- [Nothing yet]

### Fixed
- [Pending release items]

### Security
- Enhanced API key authentication with HMAC validation
- Complete CSRF protection middleware
- Security headers updated (HSTS, CSP)
```

---

## 🔀 7. VERSION CONTROL

### Item 7.1: Commit Message Convention
**Format:**
```
<prefix>: <short description>

[optional long description]

Signed-off-by: Your Name <email@example.com>
```

**Prefixes:**
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation update
- `test:` Test addition/modification
- `refactor:` Code refactoring
- `chore:` Maintenance tasks
- `security:` Security-related changes

**Example:**
```
security: complete CSRF middleware implementation with secure token generation

- Implement token generation using secrets.token_urlsafe()
- Add server-side token storage in Redis
- Update CSRFMiddleware to validate tokens against session
- Add tests for CSRF protection

Fixes: #123
```

---

### Item 7.2: Branch Naming
**Convention:** `<type>/<short-description>`

**Types:**
- `feature/...` - New functionality
- `bugfix/...` - Bug fixes
- `hotfix/...` - Urgent production fixes
- `release/...` - Release preparation
- `security/...` - Security patches

**Examples:**
- `feature/add-battery-calculation`
- `bugfix/fix-n-plus-one-query`
- `security/patch-csrf-vulnerability`

---

### Item 7.3: Git History Security
**Check for leaked secrets:**
```powershell
# Search git history
git log -p --all -S "your-suspicious-string-here"

# Use git-secrets
git secrets --register-aws
git secrets --scan
```

**Remediation if secrets found:**
1. Immediately rotate compromised credentials
2. Use `git filter-branch` or BFG Repo Cleaner
3. Force push corrected history
4. Rotate all potentially exposed keys

---

### Item 7.4: .gitignore Verification
**Required Entries:**
```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.env
.venv/

# IDE
.vscode/
.idea/
*.swp

# Secrets
*.key
*.pem
.env.local

# OS
.DS_Store
Thumbs.db

# Dependencies
node_modules/
venv/
```

---

## 🎯 EXECUTION ROADMAP

### Phase 1: Environment Setup (BLOCKED)
**Dependencies:** Python 3.12+ installed
- [ ] Upgrade Python runtime
- [ ] Create fresh virtual environment
- [ ] Install dependencies
- [ ] Run baseline tests

### Phase 2: Critical Security Fixes (Day 1-2)
**Priority:** CRITICAL
- [ ] Complete CSRF middleware implementation
- [ ] Audit and document all environment variables
- [ ] Run dependency vulnerability scan
- [ ] Fix any hardcoded secrets found

### Phase 3: Testing Enhancement (Day 2-4)
**Priority:** HIGH
- [ ] Write unit tests for auth/rbac modules
- [ ] Add integration tests for critical endpoints
- [ ] Achieve >70% coverage on core logic
- [ ] Run load testing

### Phase 4: Documentation (Day 4-5)
**Priority:** MEDIUM
- [ ] Update README.md
- [ ] Create ENVIRONMENT_VARIABLES.md
- [ ] Enhance OpenAPI documentation
- [ ] Create DEPLOYMENT.md
- [ ] Update CHANGELOG.md

### Phase 5: Final Audit (Day 5-6)
**Priority:** HIGH
- [ ] Run full pre-launch checklist
- [ ] Security penetration test (internal)
- [ ] Performance regression testing
- [ ] Code quality review (flake8, mypy)
- [ ] Generate final compliance report

---

## 📊 SUCCESS METRICS

### Pre-Launch Gates
1. ✅ Zero CRITICAL/HIGH vulnerabilities
2. ✅ >70% code coverage on critical paths
3. ✅ All integration tests passing
4. ✅ Load test passed (100 concurrent users)
5. ✅ Documentation complete
6. ✅ Security headers verified
7. ✅ Rate limiting confirmed
8. ✅ Audit logging functional

### Quality Gates
- mypy: Zero type errors
- flake8: Zero warnings
- black: All files formatted
- prettier: Frontend formatted

---

## 🔍 VERIFICATION COMMANDS

### Environment Validation
```powershell
# Python version
python --version  # Must be 3.12.x or higher

# Dependency installation
pip install -e .

# Database migration
alembic upgrade head

# Type checking
mypy backend/

# Linting
flake8 backend/

# Code formatting
black --check backend/
```

### Security Scanning
```powershell
# Python dependency audit
pip-audit

# Frontend audit
cd frontend && npm audit

# Semgrep (if installed)
semgrep --config=auto .
```

### Testing
```powershell
# Run all tests
pytest --tb=short

# With coverage
pytest --cov=backend --cov-report=html --cov-fail-under=70

# Integration tests only
pytest tests/integration/ -v
```

---

## 📞 ESCALATION PATH

If issues encountered during remediation:

1. **Blockers:** Document with reproduction steps
2. **Architecture changes needed:** Create RFC document
3. **Security decisions:** Consult security team
4. **Third-party vulnerabilities:** Check vendor patches

---

## 📝 SIGN-OFF CHECKLIST

- [ ] Lead Developer: Code quality approved
- [ ] Security Engineer: Vulnerabilities patched
- [ ] DevOps: Deployment pipeline verified
- [ ] QA: Tests passing, coverage met
- [ ] Product Owner: Documentation complete
- [ ] Project Manager: Ready for launch

---

**Generated:** 2026-06-16T06:56:41Z  
**Next Review:** After each phase completion  
**Document Owner:** Security Team

---

## ℹ️ NOTES

This document is generated automatically based on project specification memory requirements and OWASP Top 10 guidelines. All action items reference specific files and code locations for efficient remediation.

Per project policy, no code changes were made due to Python 3.8.4 runtime non-compliance. All fixes documented here should be implemented after upgrading to Python 3.12+.
