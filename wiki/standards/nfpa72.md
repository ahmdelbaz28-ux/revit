# NFPA 72 — National Fire Alarm and Signaling Code (2022 Edition)

## Overview

NFPA 72 is the primary standard governing fire alarm system design in the United States. FireAI implements automated compliance checking against this standard. This page documents the key sections and how FireAI implements them.

## Key Sections Implemented in FireAI

### Chapter 17: Initiating Devices
- **Section 17.6.3.1.1**: Dead Air Space — detectors must be ≥ 0.1m from wall/ceiling intersection
- **Section 17.7.3**: Detector spacing — smooth ceiling spacing is 9.1m (30ft) for smoke, 7.0m for heat
- **Section 17.7.3.1**: Corridor spacing — special rules for corridors per §17.7.3
- **Section 17.7.5.6.1**: Duct detectors → Supervisory signal (NOT general alarm)
- **Coverage formula**: R = 0.7 × S (where S = listed spacing, R = coverage radius)

### Chapter 10: Notification Appliances
- NAC (Notification Appliance Circuits) must activate horns/strobes
- Voltage drop calculations per NEC 760
- DC return path: voltage drop = 2 × I × R × L (NOT just I × R × L — Bug 12!)

### Chapter 21: Emergency Communications
- Elevator recall: Phase I (recall to designated floor) + Phase II (independent service)
- Fire pump start signal required
- HVAC shutdown per zone (not building-wide)
- Door release per zone (not simultaneous)

### Chapter 12: Circuit Pathway
- Class A: Style 7 — redundant path, single fault tolerance
- Class B: Style 4 — non-redundant path
- Class C: Supervised circuit
- Class D: Signal circuit verification

### Chapter 14: Inspection, Testing, and Maintenance
- Coverage verification: every ceiling point within R=0.7×S of a detector
- Area-based verification (Shapely polygon intersection) — NOT point-counting (Bug from V13)

## Safety-Critical Implementation Notes

1. **Coverage MUST be area-based** (Shapely polygon intersection), not point-counting. Point-counting misses uncovered corners. (V13 Bug Fix)
2. **Detector type matching MUST use longest-match** — "F-DET-H" (heat) must not match "F-DET" (smoke). (V12 Bug 1)
3. **Dead air space check is mandatory** — detectors within 0.1m of wall/ceiling junction violate NFPA 72 §17.6.3.1.1
4. **Status terminology**: APPROVED / REJECTED / REQUIRES_MANUAL_REVIEW — never "PARTIAL" (V13 Fix)

## Cross-References

- [[nec|NEC Chapter 7-9]] — wiring and circuit calculations
- [[decisions/001-coverage-method|Decision 001: Area-Based Coverage]]
- [[decisions/003-status-terminology|Decision 003: Status Terminology]]
- [[bug-fixes/V13-safety|V13 — Point-Cloud Coverage Illusion]]
