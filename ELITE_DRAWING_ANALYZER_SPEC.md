# Elite Drawing Analyzer - Technical Specification

**Version:** V2.0  
**Date:** 2026-05-13

---

## 1. Overview

| Aspect | Value |
|--------|-------|
| Purpose | Analyze fire alarm drawings (DXF/DWG/PDF/IFC/images) |
| Features | Auto-extract layout, compare with BOQ, apply NFPA rules |
| Learning | Continuous from user corrections |
| Output | HTML report + annotated PNG overlays |

---

## 2. Architecture

```
elite_drawing_analyzer/
├── core/
│   ├── ingest.py      # DXF/DWG/PDF/IFC/images → unified model
│   ├── vectorize.py   # Repair broken/faded lines (CLAHE + morphology + LSD)
│   └── ocr.py        # Hybrid Arabic/English OCR for legends
├── intelligence/
│   ├── knowledge_base.py  # SQLite - all learned knowledge persists
│   └── classifier.py     # 3-layer: name → embedding k-NN → heuristic
├── reasoning/
│   ├── spatial.py        # Distances / coverage / line-of-sight
│   ├── compliance.py     # NFPA 72 / 13 / 101 / NEC / MEP
│   └── schedule_match.py # BOQ vs drawing reconciliation
├── reporting/
│   ├── overlay.py       # Draw findings over drawing (PNG)
│   └── html_report.py  # Standalone HTML report
├── safety/
│   └── fire.py         # Safety gates: pass/fail/review_required
├── pipeline.py        # End-to-end orchestrator
├── cli.py             # Command-line interface
└── tests/             # 9 tests passing
```

---

## 3. Workflow

### Complete Pipeline (One Command)

```bash
python -m elite_drawing_analyzer.cli analyze project.pdf \
    --html report.html \
    --overlays out/
```

**System does in ONE step:**
1. Read all layers/blocks/text
2. Repair broken/faded lines
3. OCR legends automatically
4. Extract BOQ schedule automatically (no manual JSON needed)
5. Classify every symbol (3-layer: name → embedding → heuristic)
6. Compare schedule vs drawing
7. Apply NFPA rules to distances
8. Generate HTML report + annotated PNG

### Review Uncertain Items

```bash
python -m elite_drawing_analyzer.cli review --max-conf 0.6

# Output:
# ID   Conf  Symbol            Page  Bbox
# 142  0.35  unknown            2    [120,340,180,400]
```

### Correct + Teach

```bash
python -m elite_drawing_analyzer.cli feedback 142 \
    --correction camera_dome \
    --crop crops/142.png

# System learns → next time recognizes directly
```

### Measure Improvement

```bash
python -m elite_drawing_analyzer.cli metrics

# Output:
# {
#   "total_judged": 47,
#   "accuracy": 0.872,
#   "by_confidence_bucket": {
#     "0.0-0.4": {"accuracy": 0.41},   # Embedder weak
#     "0.6-0.8": {"accuracy": 0.93},
#     "0.8-1.01": {"accuracy": 0.99}
#   }
# }
```

---

## 4. Pre-loaded Rules

| Code | Rule | Value |
|------|------|-------|
| NFPA 72 | Smoke detector spacing | 9.1m |
| NFPA 72 | Heat detector spacing | 7.0m |
| NFPA 13 | Sprinkler spacing (Light) | 4.6m |
| NFPA 13 | Area per head | 20.9m² |
| NFPA 101 | Max egress travel | 61m |
| NEC 110.26 | Panel clearance | 0.9m |
| MEP | Cable from hot pipe | 0.3m |

**Can modify directly:** `kb.set_rule("NFPA_72_smoke_spacing", 9.2)`

---

## 5. API Usage

```python
from elite_drawing_analyzer import analyze_file, KnowledgeBase

kb = KnowledgeBase()
report = analyze_file(
    "fire_alarm_layout.pdf",
    kb=kb,
    auto_schedule=True,      # Auto-read BOQ table
    units_to_m=0.001,        # Drawing in mm
    overlay_dir="out/",      # PNG per page
    html_out="out/report.html",
)

print(f"Critical: {sum(1 for f in report['findings'] if f['severity']=='critical')}")
for r in report['reconciliation']:
    if r["status"] != "match":
        print(f"⚠️  {r['item']}: BOQ {r['scheduled_qty']} ≠ drawing {r['actual_qty']}")
```

---

## 6. Limitations & Warnings

### ⚠️ Honest Limitations

| Limitation | Severity | Workaround |
|------------|----------|------------|
| No 3D analysis | Medium | Manual review for ceiling obstacles |
| No fire simulation | High | CFD not included |
| Cable routing approximate | High | Verify physically |
| No CFD analysis | High | Manual engineering |

### Required Engineer Review

- ✅ Approve final panel locations
- ✅ Review cable routing
- ✅ Verify power sources
- ✅ Approve loop design
- ✅ Review evacuation systems
- ✅ Verify ADA compliance

### Disclaimer

**This system is an ANALYSIS TOOL - NOT a replacement for professional engineering judgment.**

All results require review and approval by licensed engineer before implementation.

---

## 7. Test Results

**9/9 tests PASSED**

| Test Category | Tests | Status |
|--------------|-------|--------|
| Core Ingest | 3 | ✅ |
| Intelligence | 3 | ✅ |
| Reasoning | 2 | ✅ |
| Safety | 1 | ✅ |

---

## 8. Dependencies

```bash
# Install
pip install -r requirements.txt

# Optional for DWG support
# Requires: ODA File Converter (free)

# Optional for Arabic OCR
apt install tesseract-ocr-ara

# Optional for higher accuracy (CLIP)
pip install transformers torch
```

---

## 9. Honest Note

> Any finding with critical or major severity MUST be reviewed by licensed engineer.

> The phrase "the machine does not make mistakes" is the opposite of safety - it's what kills people.

> The system says "I am X% confident" - not "I am 100% certain."

> This system is a TOOL to ASSIST engineers, not REPLACE them.

---

**Document for Consultant Review**

Date: 2026-05-13  
Status: Technical Specification V2.0