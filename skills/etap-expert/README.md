# ETAP Expert Skill

> **Production-grade ETAP (Electrical Transient Analyzer Program) consultant skill**
> covering ALL 60+ ETAP modules across 33 sections including ADMS, GIS, Power
> System Analysis, Protection, Arc Flash, Transients, Renewables, Marine, and
> Industrial applications.

## Quick Facts

| Property | Value |
|---|---|
| **Skill Name** | `etap-expert` |
| **Version** | 1.0.0 |
| **Skill File Size** | 4,417 lines (SKILL.md) |
| **Sections** | 33 (Core Identity → DER/PV comprehensive guide) |
| **Author** | FireAI Project |
| **Last Updated** | 2026-06-23 |
| **License** | MIT (inherits from project) |

## Three Modes of Operation

| Mode | Trigger | Behavior |
|---|---|---|
| **Expert Mode** | User asks correctly | Direct answer + ETAP steps + validation |
| **Clarification Mode** | User is incomplete | Ask 1-3 specific technical questions |
| **Correction Mode** | User is wrong | Explain WHY + show correct approach + guide |

## The 6-Step Expert Workflow

```
STEP 1: PARSE & CLASSIFY
├── Identify: Study Type? Equipment? Standard? Region?
├── Extract: Numerical values, equipment names, voltages
└── Classify: Complete / Incomplete / Wrong

STEP 2: SEARCH INTERNAL KNOWLEDGE
├── Query: Equipment properties, study requirements
├── Check: Missing data, dependencies, standards
└── Retrieve: Formulas, typical values, ETAP menu paths

STEP 3: FEASIBILITY & VALIDATION
├── Data Completeness: All parameters available?
├── Physical Reality: Is the request possible?
├── Standard Compliance: IEEE/IEC/NEC rules?
└── ETAP Capability: Can ETAP do this?

STEP 4: INTERNAL SIMULATION (MENTAL MODEL)
├── Calculate: Step-by-step with formulas
├── Check: Against limits and standards
├── Validate: Does result make physical sense?
└── Flag: Any warnings or caveats

STEP 5: FORMULATE RESPONSE
├── If COMPLETE → Direct Answer + ETAP Steps
├── If INCOMPLETE → Ask 1-3 clarifying questions
└── If WRONG → Explain WHY + Correct Approach

STEP 6: QUALITY ASSURANCE
├── Verify: Units correct? Significant figures?
├── Cross-check: Alternative calculation method?
└── Document: Assumptions, limitations, references
```

## Files

```
skills/etap-expert/
├── SKILL.md                          # Main skill content (4,417 lines)
├── manifest.yaml                     # SkillManifest compatible with skill_validator.py
├── README.md                         # This file
├── references/
│   └── system-prompt.md              # ETAP Expert AI Agent System Prompt
├── scripts/
│   ├── __init__.py
│   ├── skill_loader.py               # Python loader + YAML front-matter validator
│   ├── internal_simulation_engine.py # 5 numerical simulation examples
│   └── stress_test_runner.py         # Stress test runner (orchestrator)
└── tests/
    ├── __init__.py
    ├── test_skill_structure.py       # Gate 1: Static validation
    ├── test_skill_loader.py          # Gate 2: Runtime validation
    ├── test_workflow_routing.py      # Gate 3: Behavioral validation
    ├── test_internal_simulations.py  # Gate 4: Regression validation (numerical)
    └── test_property_based.py        # Gate 5: Adversarial audit (property-based)
```

## Coverage Summary

### ETAP Modules Covered
- **A. Core Analysis**: Load Flow, Short Circuit (ANSI/IEC 60909/IEC 61363), Motor Starting, Transient Stability, eMT, Harmonics
- **B. ADMS**: eSCADA, DMS, OMS, DERMS, DSE, VVO, FLISR, iDLS, eOTS, Predictive Simulation
- **C. GIS**: ESRI ArcGIS integration, geospatial electrical modeling
- **D. Renewables**: Solar PV, Wind (Type 1-4), BESS, Hydrogen, Smart Inverters
- **E. Industrial**: Marine (IEC 60092/61363), Traction (DC 750V-3000V, AC 15-50kV), Data Centers (Tier I-IV), Oil & Gas, Mining, Nuclear
- **F. Design Tools**: One-Line Diagram, Equipment Libraries, etapAPI (REST), Python scripting, COM interface
- **G. Emerging**: ETAP CoPilot (AI), eSI Situational Intelligence, eAPM Asset Performance, eProtect

### Standards Referenced
| Category | Standards |
|---|---|
| **IEEE** | 80, 141, 242, 399, 446, 485, 519, 738, 902, 928, 1036, 1100, 1159, 1366, 1547, 1584, C37.010, C37.13, C37.91 |
| **IEC** | 60364, 60909, 60947, 61000, 61363, 61660, 61727, 62305, 62351, 61850, 60092, 60533 |
| **NEC/NFPA** | NFPA 70 (NEC), NFPA 70E, NFPA 110, NFPA 780 |
| **Marine** | Lloyd's Register, DNV GL, ABS, SOLAS |
| **Grid Codes** | IEEE 1547-2018, ENA EREC G99/G5/5, PRC-024-2, Enedis-PRO-RES_64, RTE_DTR |

## Validation & Testing

This skill is validated through a **5-gate verification protocol** (per FireAI agent.md):

| Gate | Purpose | Test File |
|---|---|---|
| 1. Static | YAML front-matter, section count, templates | `test_skill_structure.py` |
| 2. Runtime | Loader imports cleanly, manifest parses | `test_skill_loader.py` |
| 3. Behavioral | Template A/B/C/D routing, mistake detection | `test_workflow_routing.py` |
| 4. Regression | Numerical correctness of 5 simulations | `test_internal_simulations.py` |
| 5. Adversarial | Property-based fuzzing with hypothesis | `test_property_based.py` |

### Running Tests

```bash
cd /home/z/my-project/revit
python -m pytest skills/etap-expert/tests/ -v --tb=short
```

### Running Stress Tests

```bash
python skills/etap-expert/scripts/stress_test_runner.py
```

## Integration with FireAI

This skill complements the FireAI platform in the **electrical power domain**:

| FireAI Module | ETAP Skill Section | Intersection |
|---|---|---|
| `fireai/core/atex_hazardous_arbiter.py` | Section 9 (Arc Flash IEEE 1584-2018) | Incident energy calculations |
| `fireai/core/voltage_drop.py` | Section 7.1 (Load Flow) + Section 15.2 Example 1 | Cable voltage drop formulas |
| `fireai/core/bps_allocator.py` | Section 8 (Protection Coordination) | Battery/relay coordination |
| `fireai/core/conduit_fill_analyzer.py` | Section 7 (Cable Sizing NEC Table 310.16) | Ampacity tables |
| `backend/services/marine_service.py` (V130) | Section 25 (Marine IEC 60092/61363) | Shipboard power systems |
| `fireai/core/battery_aging_derating.py` | Section 10 (Battery Sizing IEEE 485) | Battery sizing methodology |

## Critical Rules Enforced

Per Section 17 of the skill (and FireAI agent.md Rule 1 — ABSOLUTE TRUTH):

1. **NEVER guess critical values** — Ask or state assumptions CLEARLY
2. **ALWAYS validate physically** — If result seems wrong, RECALCULATE
3. **NEVER skip internal simulation** — Even for "simple" questions
4. **ALWAYS reference standards** — IEEE, IEC, NEC, NFPA when applicable
5. **GUIDE, don't just correct** — When user is wrong, TEACH them WHY
6. **Use EXACT ETAP terminology** — Bus, not node; One-Line, not schematic; Star, not relay
7. **DISTINGUISH study types clearly** — Never mix Load Flow with Short Circuit
8. **State ALL assumptions** — Voltage, PF, temperature, installation method
9. **INCLUDE units in ALL answers** — Never leave numbers without units
10. **VERIFY breaker duty** — Always check interrupting rating
11. **CHECK coordination** — Never give relay settings without coordination check
12. **FLAG safety issues** — Arc flash, grounding, protection immediately
13. **DISTINGUISH desktop vs ADMS** — Different workflows, different answers
14. **USE correct standard for region** — ANSI for US, IEC for international
15. **NEVER recommend unsafe practices** — No shortcuts on safety

## Sources

- ETAP official website (etap.com) — product pages, white papers
- IEEE Standards Association — IEEE 1584-2018, IEEE 1547-2018, IEEE 80, IEEE 519
- IEC Standards — IEC 60909, IEC 61363, IEC 62351, IEC 61850
- NFPA — NFPA 70 (NEC), NFPA 70E, NFPA 110
- Marine classification societies — Lloyd's Register, DNV GL, ABS
- Industry best practices — Tanuj Khandelwal (CEO ETAP) public statements

## License

MIT License — see project LICENSE file.
