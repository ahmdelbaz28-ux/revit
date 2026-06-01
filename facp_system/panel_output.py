"""
FACP EXPORT & SUBMITTAL WRAPPER
Formats compliance schedules and generates CSI-format construction specs.
"""

from facp_system.panel_selector import PanelRecommendation, ProjectRequirements

class OutputGenerator:
    @staticmethod
    def generate_dxf_schedule(rec: PanelRecommendation, qty: int = 1) -> str:
        """Generates formatting-ready table structures for Model Space CAD viewports."""
        border = "=" * 80
        schedule = [
            border,
            "                     FIRE ALARM CONTROL PANEL SCHEDULE                     ",
            border,
            f"  MODEL NO.           : {rec.recommended_model:<25} QTY: {qty}",
            f"  MANUFACTURER        : {rec.manufacturer:<30}",
            f"  POWER SUPPLY UNIT   : {rec.power_supply_watts} Watts, 24VDC Nom.",
            f"  POINTS UTILIZATION  : {rec.capacity_utilization:.2%} used space",
            f"  NAC UTILIZATION     : {rec.nac_utilization:.2%} circuit space",
            f"  MANDATORY BATTERY   : {rec.battery_size_ah} Ah, Lead-Acid, Qty: 2",
            f"  BATTERY DERATING    : {rec.battery_derating_details.get('method', 'N/A')}",
            f"  REGULATORY LISTINGS : {', '.join(rec.listings)}",
            f"  SHA-256 SIGNATURE   : {rec.signature_hash}",
            border
        ]
        return "\n".join(schedule)

    @staticmethod
    def generate_csi_specification(req: ProjectRequirements, rec: PanelRecommendation) -> str:
        """Generates precise, ready-to-print submittal paragraphs for fire protection bids."""
        voice_str = "with integrated, multichannel emergency voice evacuation communications," if req.requires_voice else "with standard tone/alarm notification capabilities,"
        net_str = "network-enabled and capable of linking with peer transponders" if req.requires_network else "non-networked, standalone"
        releasing_str = "The panel shall be rated for releasing service per UL 864 and NFPA 72 SS21.7, supporting cross-zone verification and abort capabilities." if req.requires_releasing else ""

        battery_derating = rec.battery_derating_details.get("method", "NFPA 72 SS10.6.7")

        spec = (
            f"SECTION 28 31 11 - FIRE ALARM CONTROL PANEL SPECIFICATION\n\n"
            f"1.1 SYSTEM OVERVIEW\n"
            f"  The contractor shall furnish and install a central {rec.manufacturer} Model {rec.recommended_model} "
            f"analog addressable Fire Alarm Control Panel (FACP). The panel shall be {net_str}, {voice_str} "
            f"complying with UL 864 10th Edition and NFPA 72 standards.\n\n"
            f"1.2 DESIGN METRICS\n"
            f"  A. Addressable Point Capacity: Sized for {req.device_count} points plus 20% future capacity margin.\n"
            f"  B. Standby Power: Provided via dual sealed lead-acid batteries sized for {rec.battery_size_ah} Ah "
            f"complying with NFPA 72 SS10.6.7, ensuring 24 hours of standby operation followed by "
            f"{'15 minutes' if req.requires_voice else '5 minutes'} of continuous alarm. "
            f"Battery sizing method: {battery_derating}.\n"
            f"  C. Power Supply: Evaluated with {rec.power_supply_watts} Watts total output power.\n\n"
            f"1.3 CODE CERTIFICATION\n"
            f"  FACP shall be approved for use in '{req.jurisdiction}' jurisdictions, carrying standard: {', '.join(rec.listings)} listings.\n"
        )
        if releasing_str:
            spec += f"\n1.4 RELEASING SERVICE\n  {releasing_str}\n"
        return spec

    @staticmethod
    def generate_alternatives_table(rec: PanelRecommendation) -> str:
        """Renders clear, engineering-backed alternatives for design optimization."""
        table = [
            "=" * 80,
            "                      ENGINEERING ALTERNATIVES EVALUATION                     ",
            "=" * 80,
            f"  CURRENT DESIGN SELECTION: {rec.recommended_model}",
            f"  COMPATIBLE UPGRADE OPTIONS:"
        ]

        if rec.alternatives:
            for idx, alt in enumerate(rec.alternatives, 1):
                if alt:
                    table.append(f"    Alternative {idx}: Model {alt}")
                    table.append(f"      - Engineering Pro: Larger headroom margin to absorb expansion.")
                    table.append(f"      - Engineering Con: Higher initial capital expense.")
        else:
            table.append("    No alternative panels available in the database that meet all requirements.")
            table.append("    Consider specifying a different manufacturer or relaxing constraints.")

        table.append("=" * 80)
        return "\n".join(table)
