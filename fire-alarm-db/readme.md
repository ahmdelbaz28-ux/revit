# 🔥 Fire Alarm System Design Database

## Overview
Professional-grade reference database for fire alarm system design software.  
Built on international standards (NFPA 72, BS 5839, EN 54, ISO 7240, Egyptian Code).  
Target accuracy: **zero tolerance for safety-critical errors**.

---

## Directory Structure

```
fire-alarm-db/
├── README.md                          ← You are here
├── standards/
│   ├── nfpa72-rules.json              ← NFPA 72 core design rules
│   ├── bs5839-rules.json              ← BS 5839 Part 1 design rules
│   ├── en54-product-specs.json        ← EN 54 product certification requirements
│   └── egyptian-code.json             ← Egyptian fire protection code
├── devices/
│   ├── detector-types.json            ← All detector categories & specs
│   ├── notification-appliances.json   ← Horns, strobes, speakers, bells
│   ├── initiating-devices.json        ← Pull stations, duct detectors, beam
│   ├── control-panels.json            ← Panel types & specifications
│   └── modules-accessories.json       ← Relays, isolators, interfaces
├── rules/
│   ├── coverage-spacing.json          ← Spacing & placement rules per standard
│   ├── zone-mapping.json              ← Zone division & labeling rules
│   ├── circuit-loading.json           ← NAC/SLC current limits & loading
│   └── integration-interfaces.json    ← Elevator, HVAC, door release, etc.
├── calculations/
│   ├── voltage-drop.json              ← Vdrop formulas, wire tables, examples
│   ├── battery-calculations.json      ← Standby & alarm battery sizing
│   └── candela-calculations.json      ← Strobe intensity & spacing
├── building-types/
│   ├── occupancy-classification.json  ← NFPA/IBC occupancy types
│   └── risk-categories.json           ← BS 5839 risk categories (L/M/P)
└── manufacturers/
    ├── supported-brands.json          ← Major brand registry
    └── product-data-template.json     ← Template for adding new products
```

---

## Design Philosophy

### Why This Exists
A fire alarm design tool is **safety-critical software**. Every number, every rule, every
calculation must be traceable to an authoritative source. This database serves as the single
source of truth for the design engine.

### Accuracy Standards
- All numerical values traceable to specific code sections
- Imperial (ft/in) and Metric (m/mm) values provided
- Safety margins built into calculations where codes allow interpretation
- Conservative defaults (always err on the side of over-protection)

### Compliance Priority (for Egypt/Middle East)
1. **Local Code** (Egyptian Code for Fire Protection) — always takes precedence
2. **NFPA 72** — most commonly adopted in MENA region
3. **BS 5839 Part 1** — widely used in Gulf/Egypt projects
4. **EN 54** — product certification standard
5. **ISO 7240** — international reference

---

## How to Use This Database

### For Software Developers
Each JSON file is structured for direct import:
- `id` fields serve as primary keys
- `rules` arrays contain conditions with `if`/`then`/`reference` structure
- `tables` arrays contain lookup data
- All measurements include both metric and imperial

### For Design Engineers
- Reference the `source_code` and `source_section` fields for code compliance
- Check `notes` and `exceptions` for edge cases
- Use `calculation_methods` for step-by-step procedures

### For Project Managers
- `building-types/` for scope definition
- `standards/` for contract compliance requirements
- `manufacturers/` for product selection

---

## Version Control

| Version | Date       | Changes                        | Author    |
|---------|------------|--------------------------------|-----------|
| 1.0.0   | 2026-05-09 | Initial database creation      | baz / AI  |
|         |            |                                |           |

---

## ⚠️ Disclaimer

This database is a design **reference tool**. Final designs must be:
1. Reviewed by a licensed fire protection engineer
2. Approved by local authorities having jurisdiction (AHJ)
3. Compliant with the specific edition of codes adopted locally
4. Verified through field commissioning and testing

**No software can replace professional engineering judgment.**
