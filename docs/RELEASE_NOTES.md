# FireAI Release Notes — v1.0.0

## Overview
FireAI Digital Twin v1.0.0 — Safety-critical fire alarm engineering platform for NFPA 72-2022 compliant fire detector placement, battery sizing, voltage drop calculations, and FACP selection.

## Features
- **5-layer computation pipeline**: Physics Guard → NFPA 72 Lookup → IEEE-754 Compute → Validation → Audit Log
- **Cryptographic audit trail**: HMAC-SHA256 signed hash chain for every engineering result
- **64 API endpoints**: Projects, devices, connections, reports, exports, elements, conflicts, environment, FACP, QOMN
- **International regulatory support**: NFPA (US), ATEX/IEC (EU), BS 5839-1 (UK), Saudi HCIS, UAE, Egyptian, Kuwait, Qatar codes
- **FACP selection engine**: NOTIFIER/SIEMENS/SIMPLEX panels (7 models), UL 864 10th Edition compliance
- **QOMN conduit routing**: NEC Chapter 9 compliant, fill/bend/catalog engines
- **8-stage analysis pipeline**: Including rules compliance, coverage verification, constraint solving
- **Multi-format CAD/BIM parsing**: DXF, DWG, IFC, PDF, Excel, Word, RVT, images
- **3D spatial engine**: Density optimizer, Voronoi verifier, proof certificate, MIP solver

## Bug Fixes (V131)
- **Windows path compatibility**: Fixed `_resolve_db_path` tests for cross-platform support
- **SQLite file locking**: Fixed `AuditLog` and `DeltaCache` connection cleanup on Windows
- **DeltaCache connection leak**: `_load_from_db` and `persist()` now use `finally` blocks to close connections
- **Optional dependency imports**: Workflow/Memory routers now load conditionally; app starts without langgraph/mem0
- **XML parsing security**: Switched to `defusedxml.ElementTree` for Atom feed parsing (CVE: billion laughs)
- **Missing parser dependencies**: Added pymupdf, opencv-python, pandas to requirements.txt

## Security Hardening
- API key authentication required for all mutating endpoints
- Production fails closed without FIREAI_API_KEY
- Dev HMAC key fallback blocked in production
- CORS wildcards ALWAYS rejected in production
- Security headers on every response (X-Frame-Options, X-Content-Type-Options, CSP, Permissions-Policy)
- Per-path rate limiting with longest-prefix match
- Input sanitization: sort field whitelists, null byte rejection, path traversal protection
- Parser file size caps (environment-configurable)
- Parser path security validation (all 7 parsers)

## Test Results
- **5,194 tests passing** (5,007 FireAI + 211 qomn_conduit + 58 qomn_fire)
- **1 skipped** (requires optional dependency)
- **0 failures**
- **Bandit**: 0 HIGH, 2 MEDIUM (test `/tmp` paths), 37 LOW (asserts in tests)
- **Ruff**: 4 remaining style warnings (S603 subprocess, S314 XML, SIM116 dict lookup)

## Known Limitations
- `/api/workflow` endpoints require langgraph (optional: `pip install fireai[workflow]`)
- `/api/memory` endpoints require mem0 + qdrant-client (optional: `pip install fireai[memory]`)
- IFC export requires ifcopenshell (optional: `pip install fireai[ifc]`)
- DWG/RVT conversion requires external converter binaries
- Windows: SQLite file locking requires proper connection cleanup
- Python 3.12+ required (Python 3.14 recommended for latest features)

## Dependencies
### Core
fastapi, uvicorn, pydantic, shapely, numpy, matplotlib, ezdxf, openpyxl, pymupdf, opencv-python, pandas, httpx, aiohttp, cryptography, loguru, reportlab, Pillow

### Optional
langgraph (workflow), mem0 + qdrant-client (memory), ifcopenshell (IFC), slowapi (rate limiting)