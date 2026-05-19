"""
reasoning/compliance.py
=======================
Applies code rules from the KB to the analyzed drawing.

The output is a list of Findings — each with severity, citation, evidence,
and a recommended remediation. Findings under "advisory" must NEVER be
silently converted to PASS — they require explicit human sign-off.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from .spatial import pairwise_min_distance, uncovered_area_estimate, max_gap_to_neighbour
from ..knowledge.memory import KnowledgeBase


SEVERITY = ("critical", "major", "minor", "advisory", "info")


@dataclass
class Finding:
    severity: str
    code: str
    rule: str
    message: str
    evidence: dict = field(default_factory=dict)
    citation: str = ""
    recommendation: str = ""


class ComplianceEngine:
    def __init__(self, kb: KnowledgeBase, units_to_m: float = 0.001):
        """units_to_m: multiplier to convert drawing units to metres (mm → 0.001)."""
        self.kb = kb
        self.k = units_to_m

    # ── Fire alarm: smoke / heat detector spacing
    def check_detector_spacing(self,
                               kind: str,                 # 'smoke_detector' or 'heat_detector'
                               positions: list[tuple[float,float]],
                               room_bounds: Optional[tuple] = None,
                               ) -> list[Finding]:
        out = []
        rule = self.kb.get_rule(f"{kind}.max_spacing_m", "NFPA72")
        if not rule:
            return [Finding("advisory","SYS","missing_rule",
                            f"No max-spacing rule for {kind}",
                            citation="", recommendation="Define rule in KB")]
        max_m = rule["value"]
        if len(positions) < 2:
            out.append(Finding("advisory","NFPA72",f"{kind}.coverage",
                               f"Only {len(positions)} {kind}(s) — too few to evaluate.",
                               citation=rule["citation"]))
            return out
        # convert + check
        for i, j, d_units in pairwise_min_distance(positions):
            d_m = d_units * self.k
            if d_m > max_m:
                out.append(Finding(
                    "critical", "NFPA72", f"{kind}.max_spacing_m",
                    f"{kind} #{i} → #{j}: {d_m:.2f} m > allowed {max_m} m",
                    evidence={"i":i,"j":j,"distance_m":round(d_m,2),"limit_m":max_m},
                    citation=rule["citation"],
                    recommendation=f"Add an additional {kind} between #{i} and #{j} "
                                   f"or relocate to ≤ {max_m} m spacing."))
        # gross coverage check if we have room bounds
        sym = self.kb.get_symbol(kind)
        if sym and sym.get("coverage_radius_m") and room_bounds:
            radius_units = sym["coverage_radius_m"] / self.k
            uncov = uncovered_area_estimate(positions, radius_units, room_bounds)
            if uncov > 0.05:
                out.append(Finding(
                    "major","NFPA72",f"{kind}.coverage",
                    f"Approx {uncov*100:.1f}% of area is outside detector coverage radius "
                    f"({sym['coverage_radius_m']} m).",
                    evidence={"uncovered_fraction":round(uncov,3)},
                    citation=rule["citation"],
                    recommendation="Add detector(s) in uncovered zones."))
        return out

    # ── Sprinkler spacing (NFPA 13 light hazard)
    def check_sprinkler_spacing(self, positions, room_bounds=None) -> list[Finding]:
        out = []
        rule_sp = self.kb.get_rule("sprinkler.light_hazard.max_spacing_m", "NFPA13")
        rule_ar = self.kb.get_rule("sprinkler.light_hazard.max_area_m2", "NFPA13")
        if not rule_sp or len(positions) < 2:
            return out
        max_m = rule_sp["value"]
        for i, j, d_units in pairwise_min_distance(positions):
            d_m = d_units * self.k
            if d_m > max_m:
                out.append(Finding(
                    "critical","NFPA13","sprinkler.max_spacing_m",
                    f"Sprinklers #{i}↔#{j}: {d_m:.2f} m > {max_m} m",
                    evidence={"i":i,"j":j,"distance_m":round(d_m,2),"limit_m":max_m},
                    citation=rule_sp["citation"],
                    recommendation="Add intermediate sprinkler or reduce spacing."))
        # area per head
        if room_bounds and rule_ar:
            x0,y0,x1,y1 = room_bounds
            area_m2 = abs((x1-x0)*(y1-y0)) * (self.k**2)
            per_head = area_m2 / len(positions)
            if per_head > rule_ar["value"]:
                out.append(Finding(
                    "major","NFPA13","sprinkler.max_area_per_head",
                    f"{per_head:.1f} m²/sprinkler > {rule_ar['value']} m² allowed.",
                    evidence={"area_m2":round(area_m2,1),"heads":len(positions),
                              "per_head":round(per_head,2)},
                    citation=rule_ar["citation"],
                    recommendation="Increase sprinkler count for this zone."))
        return out

    # ── Egress: travel distances
    def check_egress(self, occupant_points, exit_points, walls=None,
                     occupancy="business") -> list[Finding]:
        from .spatial import travel_distance
        rule = self.kb.get_rule("exit.max_travel_distance_m", "NFPA101")
        if not rule or not exit_points: return []
        out = []
        for idx, p in enumerate(occupant_points):
            d_units = min(travel_distance(p, e, walls or []) for e in exit_points)
            d_m = d_units * self.k
            if d_m > rule["value"]:
                out.append(Finding(
                    "critical","NFPA101","exit.max_travel_distance_m",
                    f"Point #{idx} travel to nearest exit ≈ {d_m:.1f} m > {rule['value']} m",
                    evidence={"point":p,"distance_m":round(d_m,1)},
                    citation=rule["citation"],
                    recommendation="Add an exit or reroute corridor."))
        return out

    # ── Electrical / MEP separation
    def check_cable_separation(self, cable_segments, hot_pipe_segments) -> list[Finding]:
        rule = self.kb.get_rule("cable_tray.from_hot_pipe_m", "MEP")
        if not rule: return []
        out = []
        sep = rule["value"] / self.k
        for i,(ax,ay,bx,by) in enumerate(cable_segments):
            for j,(cx,cy,dx,dy) in enumerate(hot_pipe_segments):
                # crude midpoint distance — replace with seg-seg distance for production
                mx1,my1 = (ax+bx)/2, (ay+by)/2
                mx2,my2 = (cx+dx)/2, (cy+dy)/2
                d = ((mx1-mx2)**2 + (my1-my2)**2) ** 0.5
                if d < sep:
                    out.append(Finding(
                        "major","MEP","cable_tray.from_hot_pipe_m",
                        f"Cable run #{i} runs {d*self.k*1000:.0f} mm from hot pipe #{j} "
                        f"(< {rule['value']*1000:.0f} mm).",
                        evidence={"cable":i,"pipe":j,"distance_mm":round(d*self.k*1000,0)},
                        citation=rule["citation"],
                        recommendation="Re-route cable or add thermal barrier."))
        return out
