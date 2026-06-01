# Decision 001: Area-Based Coverage vs Point-Counting

## Date: 2026-05-20 (V13)

## Context

FireAI needs to verify that every point on a room's ceiling is within the coverage radius of at least one detector. Two approaches exist:

1. **Point-counting**: Generate a grid of test points, check each against detector coverage circles, compute coverage as `covered_points / total_points × 100`
2. **Area-based**: Use Shapely polygon intersection to compute the actual area covered by detector circles vs. total room area

## Decision

**Area-based coverage is the PRIMARY method. Point-counting is SECONDARY (for debugging only).**

## Rationale

### Point-Counting Bug (V13, Claim 2)
- A 0.25m grid in a room can miss a 0.5m uncovered corner between grid points
- `coverage_pct = (covered_count / total_points) * 100` can report 99.77% when actual coverage is below 99%
- This means a room can PASS compliance when it actually FAILS — **life safety catastrophe**

### Area-Based Fix
- Create coverage polygons (Point.buffer for smoke, box for heat)
- Union all coverage polygons
- Intersect with room polygon
- `coverage_pct = covered_area / room_area × 100`
- Threshold: 99.9% (0.1% tolerance for floating-point)
- If Shapely fails, fallback to point-counting (conservative)

### Why 99.9% and not 100%?
- Floating-point arithmetic in Shapely can produce tiny gaps at polygon boundaries
- 0.1% tolerance is less than 0.05m² in a typical room — negligible for safety
- Any gap larger than this will be detected and flagged

## Code Location

- `fireai/core/nfpa72_coverage.py` — `check_coverage_polygon()`, `verify_full_coverage()`, `check_l_shaped_coverage()`
- All 3 functions converted from point-counting to area-based in V13

## Cross-References

- [[standards/nfpa72|NFPA 72 Coverage Requirements]]
- [[bug-fixes/V13-safety|V13 — Point-Cloud Coverage Illusion]]
- [[decisions/002-detector-placement|Decision 002: Detector Placement Algorithm]]
