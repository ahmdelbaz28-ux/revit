# NEC — National Electrical Code (Chapter 7-9)

## Overview

The National Electrical Code (NFPA 70) Chapters 7-9 govern fire alarm wiring, conduit fill, and circuit calculations. FireAI implements automated verification against these sections.

## Key Sections Implemented in FireAI

### Article 760: Fire Alarm Systems
- **760.154**: PLFA (Power-Limited Fire Alarm) and NPLFA (Non-Power-Limited) circuits MUST be separated — mixing is PROHIBITED
- **760.154(B)**: Cable classifications: FPLP (plenum), FPLR (riser), FPL (general)
- Conductor types: FPLP, FPLR, FPL, THHN, THWN, XHHW, shielded cables
- Conduit types: EMT, RMC, IMC with fill specifications from NEC Chapter 9 Table 4

### Article 310: Conductors
- **310.15(B)(3)(a)**: Conductor derating for more than 3 current-carrying conductors in conduit
- Ampacity tables for wire gauge sizing

### Chapter 9: Tables
- **Table 4**: Conduit fill area (EMT, RMC, IMC)
- **Table 5**: Conductor dimensions (diameter, area by AWG)
- **Table 8**: Conductor properties (resistance per 1000ft)

## Safety-Critical Calculations

### DC Voltage Drop (NEC 760 + NFPA 72 Chapter 10)
```
vdrop = 2.0 × current × resistance × (length_ft / 1000)
```
- The `×2.0` accounts for DC return path (both supply and return conductors)
- This was Bug 12 (V14) — missing ×2.0 reported 50% of actual voltage drop
- Impact: NAC horns/strobes at end-of-line may not operate during a fire

### Conduit Fill Calculation
```
fill_percentage = (total_conductor_area / conduit_internal_area) × 100
```
- Maximum fill: 40% for 3+ conductors (NEC Chapter 9 Table 1)
- PLFA and NPLFA circuits CANNOT share the same conduit (760.154)
- When conduit exceeds 4" → recommend cable tray

### Conductor Derating
```
adjusted_ampacity = base_ampacity × derating_factor
```
- 4-6 conductors: 80% (0.80)
- 7-9 conductors: 70% (0.70)
- 10-20 conductors: 50% (0.50)
- 21-30 conductors: 45% (0.45)
- 31-40 conductors: 40% (0.40)
- 41+ conductors: 35% (0.35)

## Cross-References

- [[nfpa72|NFPA 72]] — fire alarm system requirements
- [[bug-fixes/V14-fallacies|V14 — DC Return Path Bug]]
- [[bug-fixes/V18-cause-effect|V18 — Conduit Fill Analyzer (7 Errors Found)]]
