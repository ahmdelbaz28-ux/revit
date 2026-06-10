"""
FACP COMPLIANCE VERIFICATION LAYER
Enforces physical and electrical safety thresholds against NFPA constraints.

V54 FIX F4: Added releasing service verification.
  Root cause: requires_releasing was never validated in compliance checks.
  Impact: A suppression system could pass compliance with a non-releasing panel.
"""

from facp_system.panel_database import FireAlarmPanel
from facp_system.panel_selector import ProjectRequirements, PanelRecommendation

class ComplianceVerifier:
    @staticmethod
    def verify_national_code_rules(req: ProjectRequirements, rec: PanelRecommendation) -> list:
        """
        Runs programmatic compliance validation checks.
        """
        violations = []

        # 1. UL Listing validation
        if "UL" not in rec.listings:
            violations.append("Violation: Panel does not carry mandatory UL 864 compliance listing.")

        # 2. Battery safety margin validation (NFPA 72 SS10.6.10)
        if rec.battery_size_ah <= 0.0:
            violations.append("Violation: Back-up battery size cannot be zero or negative.")

        # 3. Voice evacuation validation — general check against database
        if req.requires_voice:
            from facp_system.panel_database import MASTER_PANEL_DATABASE
            panel = next((p for p in MASTER_PANEL_DATABASE if p.model == rec.recommended_model), None)
            if panel and not panel.supports_voice:
                violations.append(
                    "Violation: Project requires voice evacuation but selected panel "
                    f"({rec.recommended_model}) does not support integrated voice evacuation."
                )

        # 4. Local FDNY listing validation
        if req.jurisdiction == "FDNY" and "FDNY" not in rec.listings:
            violations.append("Violation: FACP is missing FDNY Certificate of Approval.")

        # V54 FIX F4: Releasing service verification
        # Root cause: requires_releasing was defined but never checked in verifier.
        # Impact: Non-releasing panel could pass compliance for suppression systems.
        # Reference: NFPA 72-2022 SS21.7, UL 864 releasing service listing
        if req.requires_releasing:
            # Check if the recommended panel is in the database and supports releasing
            from facp_system.panel_database import MASTER_PANEL_DATABASE
            panel = next((p for p in MASTER_PANEL_DATABASE if p.model == rec.recommended_model), None)
            if panel and not panel.supports_releasing:
                violations.append(
                    "Violation: Project requires releasing service (suppression control) "
                    "but selected panel does not support releasing per NFPA 72 SS21.7. "
                    "A releasing panel must have UL 864 listing for releasing service "
                    "and support cross-zone verification before agent release."
                )

        # V54 FIX F5: Battery derating method verification
        # Ensure battery sizing uses proper derating, not flat 1.2x
        derating_method = rec.battery_derating_details.get("method", "unknown")
        if "1.2" in derating_method or derating_method == "unknown":
            violations.append(
                "Warning: Battery sizing uses simplified 1.2x multiplier instead of "
                "NFPA 72 SS10.6.7 compliant derating (temperature + aging + Peukert). "
                "Battery may be undersized at low temperatures or end of service life."
            )

        return violations
