# FireAI Project Documentation

**Version:** 1.0  
**Date:** 2026-05-15  
**Project:** FireAI - Fire Alarm System Design & Verification Engine

---

## 1. Project Overview

FireAI is an intelligent fire alarm system design and verification engine that analyzes CAD drawings, extracts fire safety device locations, validates coverage per NFPA 72 standards, and generates bill of quantities (BOQ).

### Core Capabilities
- **CAD/DXF/PDF Parsing** - Extract walls, devices, symbols from architectural drawings
- **Coverage Validation** - Verify detector coverage per NFPA 72 room coverage rules
- **Spatial Planning** - Optimize device placement using constraint solving
- **BOQ Generation** - Generate material and cost lists

---

## 2. Directory Structure

```
/workspace/project/revit/
├── AGENTS.md                    # Agent guidelines & safety rules
├── ARCHITECTURE.md             # System architecture
├── ARCHITECTURE_FREEZE.md     # Frozen architecture v1.0
├── README.md                   # Main documentation
├── FIREAI_SAFETY_ASSESSMENT_REPORT.md    # Safety compliance report
├── CONTRIBUTING.md            # Contribution guidelines
├── ROADMAP.md                # Project roadmap
├── WHITEPAPER.md             # Technical whitepaper
│
├── adapters/                  # CAD format adapters
│   ├── autocad_adapter.py    # AutoCAD connectivity
│   └── revit_adapter.py    # Revit connectivity
│
├── parsers/                  # Input parsers
│   ├── parser_confidence.py # Drawing quality gate
│   ├── geometry_extractor.py # Wall extraction
│   ├── symbol_extractor.py  # NFPA device symbols
│   ├── pdf_input_layer.py # PDF processing
│   ├── dwg_parser.py      # DWG files
│   ├── dxf_parser.py      # DXF files
│   ├── pdf_parser.py      # PDF files
│   ├── ifc_parser.py      # IFC BIM files
│   └── excel_parser.py    # Excel BOQ
│
├── spatial_engine/          # Spatial reasoning
│   ├── constraint_solver.py # Constraint satisfaction
│   └── mip_solver.py       # Mixed-integer programming
│
├── validation/              # Validation layer
│   ├── compliance_oracle.py # NFPA compliance
│   ├── geometry_repair.py    # Geometry fixing
│   └── vision_validator.py  # Drawing quality
│
├── src/
│   ├── core/               # Core engine
│   ├── domain/             # Domain models
│   ├── application/        # Application layer
│   ├── pipeline.py         # Main pipeline
│   └── cli.py              # Command-line interface
│
├── tests/                   # Test suite (80+ tests)
│   ├── test_*.py           # Various protocol tests
│   └── integration/        # Integration tests
│
├── fire-alarm-db/          # Fire alarm database
│   ├── accuracy_engine/    # Coverage calculation
│   ├── master-workflow.md # Workflow definition
│   └── database-design/   # Database schemas
│
├── audit/                  # Audit logs (JSON)
├── test_data/             # Test drawings
├── sample_outputs/         # Example outputs
└── requirements.txt     # Python dependencies
```

---

## 3. Key Components

### 3.1 ParserConfidence Gate
Evaluates drawings BEFORE processing to ensure quality:

```python
# Location: parsers/parser_confidence.py
class ParserConfidence:
    """Quality gate - rejects unqualified drawings"""
    
    def evaluate(self, pdf_path) -> ConfidenceLevel:
        # REJECT: < 5 walls or < 3 devices
        # CAUTION: 5-15 walls, 3-10 devices
        # HIGH: > 15 walls, > 10 devices
```

**Key Insight:** Zero tolerance for unqualified drawings. Engine REJECTS drawings that don't meet minimum quality thresholds.

### 3.2 GeometryExtractor
Extracts wall geometry from PDF vector paths:

```python
# Location: parsers/geometry_extractor.py
class GeometryExtractor:
    """Extract walls from vector paths"""
    
    def extract_walls(self, page) -> List[Wall]:
        # PyMuPDF draw_rect() returns type='s' (stroke)
        # Use bounding rect for wall extraction
```

**Key Insight:** PyMuPDF `draw_rect()` returns `'s'` (stroke), not `'re'`. Use bounding rect.

### 3.3 CoverageEngine
Calculates device coverage per NFPA 72:

```python
# Location: fire-alarm-db/accuracy_engine/core/validation_engine.py
class ValidationEngine:
    """NFPA 72 coverage validation"""
    
    MAX_AREA_PER_DETECTOR = {
        # Smoke detectors: 100m² per detector
        # Heat detectors: 120m² per detector
    }
```

### 3.4 SpatialConstraintSolver
Optimizes device placement:

```python
# Location: spatial_engine/constraint_solver.py
class ConstraintSolver:
    """MIP-based constraint solving"""
    
    def solve(self, constraints) -> Placement:
        # Minimize cost under coverage constraints
```

---

## 4. Engineering Standards

### Safety Rules (from AGENTS.md)
1. **Honesty** - Flag errors immediately, no sugarcoating
2. **Human Lives** - Engineering errors = potential casualties
3. **Commit Reporting** - Always provide commit hash + link
4. **Code Review** - Verify before submitting
5. **Instruction Validation** - STOP if instructions are harmful

### Quality Standards
- Minimum 15 walls AND 10 devices for HIGH confidence
- Zero tolerance for unqualified drawings
- All tests pass before commit
- No fake/fraudulent results

---

## 5. API Reference

### Main Pipeline
```python
from src.pipeline import FireAIPipeline

pipeline = FireAIPipeline()
result = pipeline.analyze drawing.dxf

# Returns:
# {
#   "coverage": {...},
#   "devices": [...],
#   "boq": {...},
#   "violations": [...]
# }
```

### ParserConfidence
```python
from parsers.parser_confidence import ParserConfidence

confidence = ParserConfidence()
level = confidence.evaluate("drawing.pdf")
# Returns: REJECT | CAUTION | HIGH
```

### GeometryExtractor
```python
from parsers.geometry_extractor import GeometryExtractor

extractor = GeometryExtractor()
walls = extractor.extract_walls(page)
# Returns: List[Wall]
```

---

## 6. Dependencies

```
# requirements.txt
pymupdf>=1.23.0      # PDF processing
ezdxf>=1.0.0         # DXF processing
numpy>=1.24.0         # Numerical computing
scipy>=1.10.0         # Optimization
pulp>=2.7.0           # Linear programming
cryptography>=41.0     # Security
```

---

## 7. Testing

Run tests:
```bash
pytest tests/ -v
```

Test categories:
- **Unit Tests** - Individual components
- **Integration** - Full pipeline
- **Protocol Tests** - Edge cases (oblivion, apocalypse, omega protocols)

---

## 8. License & Contact

**License:** Proprietary  
**Repository:** https://github.com/ahmdelbaz28-ux/revit  
**Safety Contact:** For critical issues, flag immediately

---

*This documentation was auto-generated on 2026-05-15*