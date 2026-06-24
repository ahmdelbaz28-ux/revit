"""mep_sync_injector.py — MEP Interface Module Synchronizer for Fire Alarm Integration
====================================================================================
CRITICAL LIFE-SAFETY MODULE

Synchronises fire alarm system interfaces with Mechanical, Electrical, and
Plumbing (MEP) subsystems per NFPA 72 requirements. This module ensures that
elevator recall, HVAC shutdown, suppression monitoring, and egress control
are correctly integrated into the fire alarm design.

Key NFPA References:
    - NFPA 72-2022 §21.3   — Elevator recall for fire alarm
    - NFPA 72-2022 §21.3.4 — Phase I recall: designated level
    - NFPA 72-2022 §21.3.7 — Phase I recall: alternate level
    - NFPA 72-2022 §21.3.8 — Phase II recall: non-interference (requires PE verification)
    - NFPA 72-2022 §21.4   — Sprinkler / suppression monitoring
    - NFPA 72-2022 §21.6   — Supervisory signals
    - NFPA 72-2022 §21.7   — HVAC shutdown on duct smoke detection
    - NFPA 90A-2024 §5.3   — Smoke detectors in air distribution systems
    - NFPA 90A-2024 §6.4.1 — AHU shutdown above 2000 CFM
    - NFPA 101-2021 §7.2.1 — Egress route monitoring

CRITICAL DESIGN DECISIONS:
    1. Phase II elevator recall is NOT auto-enabled — requires PE verification
       per ASME A17.1 / NFPA 72 §21.3.8. Auto-enabling would be dangerous.
    2. AHU_CFM_THRESHOLD = 2000.0 per NFPA 90A-2024 §6.4.1 — any AHU above
       this capacity MUST have duct smoke detection and automatic shutdown.
    3. All MEP interface modules are added to BOQ with unit costs.
    4. All MEP interface modules expose as_loop_device_dict() for
       fault_isolator_injector compatibility.

Usage:
    from fireai.core.mep_sync_injector import (
        MEPSyncInjector, MEPElement, MEPInterfaceModule,
        ElevatorRecallSpec, HVACShutdownSpec,
    )

    injector = MEPSyncInjector(mep_elements=elements)
    result = injector.sync()
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Tuple

# ============================================================================
# Constants — NFPA 72 / NFPA 90A
# ============================================================================

AHU_CFM_THRESHOLD: float = 2000.0
"""NFPA 90A-2024 §6.4.1: Air-handling systems exceeding 2000 CFM must have
automatic smoke detection and shutdown capability."""

# Unit costs for BOQ integration (USD, 2024 market)
MEP_UNIT_COSTS: Dict[str, float] = {
    "elevator_recall_module": 285.0,
    "hvac_shutdown_module": 195.0,
    "suppression_monitor_module": 165.0,
    "egress_control_module": 210.0,
    "duct_smoke_detector": 120.0,
    "supervisory_module": 75.0,
}


# ============================================================================
# Enums
# ============================================================================


class ModuleType(str, Enum):
    """Types of MEP interface modules per NFPA 72 Chapter 21."""

    ELEVATOR_RECALL = "ELEVATOR_RECALL"
    HVAC_SHUTDOWN = "HVAC_SHUTDOWN"
    SUPPRESSION_MONITOR = "SUPPRESSION_MONITOR"
    EGRESS_CONTROL = "EGRESS_CONTROL"
    SUPERVISORY = "SUPERVISORY"


class MEPElementType(str, Enum):
    """Types of MEP elements found in building models."""

    AHU = "AHU"  # Air Handling Unit
    FCU = "FCU"  # Fan Coil Unit
    ELEVATOR = "ELEVATOR"
    SPRINKLER_SYSTEM = "SPRINKLER_SYSTEM"
    SMOKE_DAMPER = "SMOKE_DAMPER"
    FIRE_DAMPER = "FIRE_DAMPER"
    EGRESS_DOOR = "EGRESS_DOOR"
    DUCT = "DUCT"


class AddressType(str, Enum):
    """Addressing mode for MEP interface modules."""

    ANALOG = "ANALOG"
    ADDRESSABLE = "ADDRESSABLE"


class ElevatorPhase(str, Enum):
    """Elevator recall phases per NFPA 72 §21.3 / ASME A17.1."""

    PHASE_I = "PHASE_I"  # Automatic recall to designated/alternate floor
    PHASE_II = "PHASE_II"  # Firefighter's service — manual control


# ============================================================================
# Data Structures — Frozen (Immutable)
# ============================================================================


@dataclass(frozen=True)
class MEPElement:
    """A single MEP element extracted from the building model.

    Attributes:
        element_id: Unique identifier (from BIM/IFC).
        element_type: Type of MEP element (AHU, ELEVATOR, etc.).
        location: (x, y) position in metres.
        floor_id: Floor identifier.
        zone_id: Fire zone identifier.
        capacity_cfm: For AHU/FCU — airflow capacity in CFM.
        elevator_bank: For ELEVATOR — bank identifier.
        designated_floor: For ELEVATOR — Phase I recall target (default lobby/ground).
        alternate_floor: For ELEVATOR — Phase I alternate recall target.
        sprinkler_system_id: For SPRINKLER_SYSTEM — system identifier.
        is_fire_rated: For EGRESS_DOOR — whether door is fire-rated.
        nfpa_reference: Applicable NFPA code reference.

    """

    element_id: str
    element_type: MEPElementType
    location: Tuple[float, float] = (0.0, 0.0)
    floor_id: str = ""
    zone_id: str = ""
    capacity_cfm: float = 0.0
    elevator_bank: str = ""
    designated_floor: str = "LOBBY_GROUND"
    alternate_floor: str = "LOBBY_ALTERNATE"
    sprinkler_system_id: str = ""
    is_fire_rated: bool = False
    nfpa_reference: str = ""


@dataclass(frozen=True)
class ElevatorRecallSpec:
    """Elevator recall specification per NFPA 72 §21.3.

    CRITICAL: Phase II (firefighter's service) is NOT auto-enabled.
    Per §21.3.8 and ASME A17.1, Phase II requires explicit PE verification.
    Setting phase_ii_enabled=True without PE sign-off is a SAFETY VIOLATION.

    Attributes:
        elevator_bank: Bank identifier.
        designated_floor: Phase I recall target per §21.3.4.
        alternate_floor: Phase I alternate target per §21.3.7.
        phase_ii_enabled: Whether Phase II is verified by PE. Default False.
        phase_i_nfpa_ref: NFPA reference for Phase I.
        phase_ii_nfpa_ref: NFPA reference for Phase II.

    """

    elevator_bank: str
    designated_floor: str = "LOBBY_GROUND"
    alternate_floor: str = "LOBBY_ALTERNATE"
    phase_ii_enabled: bool = False  # NEVER auto-set True
    phase_i_nfpa_ref: str = "NFPA 72-2022 §21.3.4/§21.3.7"
    phase_ii_nfpa_ref: str = "NFPA 72-2022 §21.3.8 / ASME A17.1"


@dataclass(frozen=True)
class HVACShutdownSpec:
    """HVAC shutdown specification per NFPA 72 §21.7 / NFPA 90A §6.4.

    Attributes:
        ahu_id: AHU identifier.
        capacity_cfm: Airflow capacity in CFM.
        requires_shutdown: True if capacity > AHU_CFM_THRESHOLD.
        requires_duct_detector: True if duct smoke detection needed.
        shutdown_nfpa_ref: NFPA reference for shutdown requirement.
        duct_detector_nfpa_ref: NFPA reference for duct detection.

    """

    ahu_id: str
    capacity_cfm: float
    requires_shutdown: bool = False
    requires_duct_detector: bool = False
    shutdown_nfpa_ref: str = "NFPA 72-2022 §21.7 / NFPA 90A-2024 §6.4.1"
    duct_detector_nfpa_ref: str = "NFPA 90A-2024 §5.3"


@dataclass(frozen=True)
class MEPInterfaceModule:
    """A fire alarm interface module for an MEP element.

    Each module represents a physical device (monitor module, control module,
    relay, etc.) that connects the fire alarm system to an MEP subsystem.

    Attributes:
        module_id: Unique identifier.
        module_type: Type of MEP interface.
        target_element_id: ID of the MEP element being interfaced.
        address_type: Addressing mode (addressable or analog).
        nfpa_reference: Applicable NFPA code reference.
        zone_id: Fire zone assignment.
        floor_id: Floor assignment.
        description: Human-readable description.

    """

    module_id: str
    module_type: ModuleType
    target_element_id: str
    address_type: AddressType = AddressType.ADDRESSABLE
    nfpa_reference: str = ""
    zone_id: str = ""
    floor_id: str = ""
    description: str = ""

    def as_loop_device_dict(self) -> Dict[str, Any]:
        """Convert to device dict compatible with fault_isolator_injector.

        Returns:
            Dictionary with device_type, device_idx, position, zone_id
            keys compatible with the fault isolator injection algorithm.

        """
        return {
            "device_type": f"MEP_{self.module_type.value}",
            "device_idx": self.module_id,
            "position": (0.0, 0.0),  # Position set during loop layout
            "zone_id": self.zone_id,
            "floor_id": self.floor_id,
            "target_element_id": self.target_element_id,
            "nfpa_reference": self.nfpa_reference,
        }


@dataclass(frozen=True)
class MEPSyncResult:
    """Complete result of MEP synchronisation.

    Attributes:
        interface_modules: All generated interface modules.
        elevator_specs: Elevator recall specifications.
        hvac_specs: HVAC shutdown specifications.
        warnings: Non-blocking issues found during sync.
        errors: Blocking issues that prevent proper integration.
        total_modules: Count of interface modules generated.
        total_elevator_banks: Count of elevator banks processed.
        total_ahu_shutdowns: Count of AHUs requiring shutdown.

    """

    interface_modules: Tuple[MEPInterfaceModule, ...]
    elevator_specs: Tuple[ElevatorRecallSpec, ...]
    hvac_specs: Tuple[HVACShutdownSpec, ...]
    warnings: Tuple[str, ...]
    errors: Tuple[str, ...]
    total_modules: int = 0
    total_elevator_banks: int = 0
    total_ahu_shutdowns: int = 0


# ============================================================================
# Validation
# ============================================================================


def validate_mep_elements(elements: List[MEPElement]) -> List[str]:
    """Validate MEP elements before synchronisation.

    Checks:
        1. No NaN or Inf values in numeric fields.
        2. No duplicate element IDs.
        3. AHU capacity is specified and positive for AHU elements.
        4. Elevator elements have designated_floor specified.

    Args:
        elements: List of MEPElement to validate.

    Returns:
        List of error strings (empty if all valid).

    """
    errors: List[str] = []
    seen_ids: set = set()

    for elem in elements:
        # 1. NaN / Inf check on location
        x, y = elem.location
        if not (math.isfinite(x) and math.isfinite(y)):
            errors.append(f"Element '{elem.element_id}': location ({x}, {y}) contains NaN or Inf")

        # 1b. NaN / Inf check on capacity
        if not math.isfinite(elem.capacity_cfm):
            errors.append(f"Element '{elem.element_id}': capacity_cfm={elem.capacity_cfm} is NaN or Inf")

        # 2. Duplicate ID check
        if elem.element_id in seen_ids:
            errors.append(f"Duplicate element_id: '{elem.element_id}'")
        seen_ids.add(elem.element_id)

        # 3. AHU capacity check
        if elem.element_type == MEPElementType.AHU:
            if elem.capacity_cfm <= 0:
                errors.append(
                    f"AHU '{elem.element_id}': capacity_cfm must be > 0 "
                    f"(got {elem.capacity_cfm}). Per NFPA 90A, AHU capacity "
                    f"is required to determine shutdown requirements."
                )
            elif elem.capacity_cfm > AHU_CFM_THRESHOLD:
                # This is expected — just needs shutdown module
                pass
            # FCU below threshold does NOT require shutdown per NFPA 90A §6.4.1

        # 4. Elevator designated_floor check
        if elem.element_type == MEPElementType.ELEVATOR:
            if not elem.designated_floor:
                errors.append(
                    f"Elevator '{elem.element_id}': designated_floor is empty. "
                    f"Per NFPA 72 §21.3.4, a designated recall level is required."
                )

    return errors


# ============================================================================
# BOQ Integration
# ============================================================================


def extend_boq_with_mep_modules(
    mep_result: MEPSyncResult,
) -> List[Dict[str, Any]]:
    """Generate BOQ line items for MEP interface modules.

    Creates costed BOQ entries for each interface module generated during
    MEP synchronisation. Unit costs are from MEP_UNIT_COSTS table.

    Args:
        mep_result: Complete MEPSyncResult from synchronisation.

    Returns:
        List of BOQ item dicts with item_type, description, quantity,
        unit, unit_cost_usd, total_cost_usd, nfpa_reference.

    """
    # Aggregate by module type
    type_counts: Dict[str, int] = {}
    type_refs: Dict[str, str] = {}

    for mod in mep_result.interface_modules:
        key = mod.module_type.value
        type_counts[key] = type_counts.get(key, 0) + 1
        if key not in type_refs and mod.nfpa_reference:
            type_refs[key] = mod.nfpa_reference

    items: List[Dict[str, Any]] = []
    for mtype, count in sorted(type_counts.items()):
        cost_key = mtype.lower()
        unit_cost = MEP_UNIT_COSTS.get(cost_key, 100.0)
        items.append(
            {
                "item_type": f"mep_{mtype.lower()}",
                "description": f"MEP Interface Module — {mtype.replace('_', ' ').title()}",
                "quantity": count,
                "unit": "ea",
                "unit_cost_usd": unit_cost,
                "total_cost_usd": round(count * unit_cost, 2),
                "nfpa_reference": type_refs.get(mtype, "NFPA 72 Chapter 21"),
            }
        )

    # Add duct smoke detectors for HVAC shutdown
    duct_count = sum(1 for spec in mep_result.hvac_specs if spec.requires_duct_detector)
    if duct_count > 0:
        unit_cost = MEP_UNIT_COSTS["duct_smoke_detector"]
        items.append(
            {
                "item_type": "mep_duct_smoke_detector",
                "description": "Duct Smoke Detector for AHU Shutdown",
                "quantity": duct_count,
                "unit": "ea",
                "unit_cost_usd": unit_cost,
                "total_cost_usd": round(duct_count * unit_cost, 2),
                "nfpa_reference": "NFPA 90A-2024 §5.3",
            }
        )

    return items


# ============================================================================
# Core Synchroniser
# ============================================================================


class MEPSyncInjector:
    """Synchronises fire alarm interfaces with MEP subsystems.

    For each MEP element that requires a fire alarm interface (elevator recall,
    HVAC shutdown, suppression monitoring, egress control), this module:
        1. Validates the element data.
        2. Generates the appropriate interface module(s).
        3. Produces specifications (ElevatorRecallSpec, HVACShutdownSpec).
        4. Creates BOQ entries for all modules.
        5. Exposes loop-compatible device dicts for fault isolator integration.

    Args:
        mep_elements: List of MEPElement from building model.
        default_address_type: Default addressing for interface modules.

    """

    def __init__(
        self,
        mep_elements: List[MEPElement],
        default_address_type: AddressType = AddressType.ADDRESSABLE,
    ) -> None:
        self._elements = mep_elements
        self._default_address_type = default_address_type

    def sync(self) -> MEPSyncResult:
        """Run full MEP synchronisation.

        Returns:
            MEPSyncResult with all interface modules, specs, warnings, errors.

        """
        # Validate inputs
        validation_errors = validate_mep_elements(self._elements)
        if validation_errors:
            return MEPSyncResult(
                interface_modules=(),
                elevator_specs=(),
                hvac_specs=(),
                warnings=(),
                errors=tuple(validation_errors),
            )

        modules: List[MEPInterfaceModule] = []
        elevator_specs: List[ElevatorRecallSpec] = []
        hvac_specs: List[HVACShutdownSpec] = []
        warnings: List[str] = []

        for elem in self._elements:
            if elem.element_type == MEPElementType.ELEVATOR:
                emods, espec = self._process_elevator(elem, warnings)
                modules.extend(emods)
                elevator_specs.append(espec)

            elif elem.element_type in (MEPElementType.AHU, MEPElementType.FCU):
                emods, hspec = self._process_hvac(elem, warnings)
                modules.extend(emods)
                hvac_specs.append(hspec)

            elif elem.element_type == MEPElementType.SPRINKLER_SYSTEM:
                emods = self._process_suppression(elem, warnings)
                modules.extend(emods)

            elif elem.element_type == MEPElementType.EGRESS_DOOR:
                emods = self._process_egress(elem, warnings)
                modules.extend(emods)

            elif elem.element_type in (MEPElementType.SMOKE_DAMPER, MEPElementType.FIRE_DAMPER):
                emods = self._process_damper(elem, warnings)
                modules.extend(emods)

            elif elem.element_type == MEPElementType.DUCT:
                emods = self._process_duct(elem, warnings)
                modules.extend(emods)

        return MEPSyncResult(
            interface_modules=tuple(modules),
            elevator_specs=tuple(elevator_specs),
            hvac_specs=tuple(hvac_specs),
            warnings=tuple(warnings),
            errors=(),
            total_modules=len(modules),
            total_elevator_banks=len(elevator_specs),
            total_ahu_shutdowns=sum(1 for s in hvac_specs if s.requires_shutdown),
        )

    # --- Private processors ---

    def _process_elevator(
        self,
        elem: MEPElement,
        warnings: List[str],
    ) -> Tuple[List[MEPInterfaceModule], ElevatorRecallSpec]:
        """Process elevator element per NFPA 72 §21.3.

        Generates:
            - One elevator recall module (Phase I)
            - ElevatorRecallSpec with Phase II NOT auto-enabled

        Phase II non-interference is NEVER auto-set to True.
        Per §21.3.8 and ASME A17.1, this requires PE verification.
        """
        # Phase I recall module
        recall_module = MEPInterfaceModule(
            module_id=f"ELEV-RECALL-{elem.element_id}",
            module_type=ModuleType.ELEVATOR_RECALL,
            target_element_id=elem.element_id,
            address_type=self._default_address_type,
            nfpa_reference="NFPA 72-2022 §21.3.4/§21.3.7",
            zone_id=elem.zone_id,
            floor_id=elem.floor_id,
            description=(
                f"Elevator recall module for bank '{elem.elevator_bank}'. "
                f"Phase I recall to {elem.designated_floor}, "
                f"alternate {elem.alternate_floor}."
            ),
        )

        # Recall specification — Phase II NOT auto-enabled
        spec = ElevatorRecallSpec(
            elevator_bank=elem.elevator_bank or elem.element_id,
            designated_floor=elem.designated_floor,
            alternate_floor=elem.alternate_floor,
            phase_ii_enabled=False,  # NEVER auto-set True per §21.3.8
        )

        # Warning if no elevator bank specified
        if not elem.elevator_bank:
            warnings.append(
                f"Elevator '{elem.element_id}': no elevator_bank specified. Using element_id as bank identifier."
            )

        return [recall_module], spec

    def _process_hvac(
        self,
        elem: MEPElement,
        warnings: List[str],
    ) -> Tuple[List[MEPInterfaceModule], HVACShutdownSpec]:
        """Process HVAC (AHU/FCU) element per NFPA 72 §21.7 / NFPA 90A §6.4.

        AHUs above AHU_CFM_THRESHOLD (2000 CFM) require:
            - Automatic shutdown on duct smoke detection
            - Duct smoke detector in supply and return

        FCUs below threshold do NOT require automatic shutdown per NFPA 90A.
        """
        requires_shutdown = elem.capacity_cfm > AHU_CFM_THRESHOLD
        requires_duct_detector = requires_shutdown

        modules: List[MEPInterfaceModule] = []

        if requires_shutdown:
            shutdown_module = MEPInterfaceModule(
                module_id=f"HVAC-SHUTDOWN-{elem.element_id}",
                module_type=ModuleType.HVAC_SHUTDOWN,
                target_element_id=elem.element_id,
                address_type=self._default_address_type,
                nfpa_reference="NFPA 72-2022 §21.7 / NFPA 90A-2024 §6.4.1",
                zone_id=elem.zone_id,
                floor_id=elem.floor_id,
                description=(
                    f"AHU shutdown module for '{elem.element_id}' "
                    f"({elem.capacity_cfm:.0f} CFM > {AHU_CFM_THRESHOLD:.0f} CFM threshold). "
                    f"Per NFPA 90A §6.4.1, automatic shutdown required."
                ),
            )
            modules.append(shutdown_module)

            # Supervisory module for duct detector status
            supervisory = MEPInterfaceModule(
                module_id=f"HVAC-SUPV-{elem.element_id}",
                module_type=ModuleType.SUPERVISORY,
                target_element_id=elem.element_id,
                address_type=self._default_address_type,
                nfpa_reference="NFPA 90A-2024 §5.3",
                zone_id=elem.zone_id,
                floor_id=elem.floor_id,
                description=(
                    f"Duct smoke detector supervisory for '{elem.element_id}'. "
                    f"Monitors duct detector status per NFPA 90A §5.3."
                ),
            )
            modules.append(supervisory)
        else:
            warnings.append(
                f"AHU/FCU '{elem.element_id}': capacity {elem.capacity_cfm:.0f} CFM "
                f"<= {AHU_CFM_THRESHOLD:.0f} CFM threshold. "
                f"Automatic shutdown not required per NFPA 90A §6.4.1. "
                f"Verify with local AHJ requirements."
            )

        spec = HVACShutdownSpec(
            ahu_id=elem.element_id,
            capacity_cfm=elem.capacity_cfm,
            requires_shutdown=requires_shutdown,
            requires_duct_detector=requires_duct_detector,
        )

        return modules, spec

    def _process_suppression(
        self,
        elem: MEPElement,
        warnings: List[str],
    ) -> List[MEPInterfaceModule]:
        """Process sprinkler/suppression system per NFPA 72 §21.4."""
        module = MEPInterfaceModule(
            module_id=f"SUPP-MON-{elem.element_id}",
            module_type=ModuleType.SUPPRESSION_MONITOR,
            target_element_id=elem.element_id,
            address_type=self._default_address_type,
            nfpa_reference="NFPA 72-2022 §21.4",
            zone_id=elem.zone_id,
            floor_id=elem.floor_id,
            description=(
                f"Suppression monitoring module for '{elem.element_id}'. "
                f"Monitors sprinkler system tamper and flow switches per §21.4."
            ),
        )
        return [module]

    def _process_egress(
        self,
        elem: MEPElement,
        warnings: List[str],
    ) -> List[MEPInterfaceModule]:
        """Process egress door per NFPA 101 §7.2.1."""
        if not elem.is_fire_rated:
            warnings.append(
                f"Egress door '{elem.element_id}': not marked as fire-rated. "
                f"Egress control modules are typically for fire-rated doors "
                f"per NFPA 101 §7.2.1. Verify with egress plan."
            )

        module = MEPInterfaceModule(
            module_id=f"EGRESS-CTL-{elem.element_id}",
            module_type=ModuleType.EGRESS_CONTROL,
            target_element_id=elem.element_id,
            address_type=self._default_address_type,
            nfpa_reference="NFPA 101-2021 §7.2.1",
            zone_id=elem.zone_id,
            floor_id=elem.floor_id,
            description=(
                f"Egress control module for door '{elem.element_id}'. "
                f"Monitors door holder/magnetic lock release per NFPA 101 §7.2.1."
            ),
        )
        return [module]

    def _process_damper(
        self,
        elem: MEPElement,
        warnings: List[str],
    ) -> List[MEPInterfaceModule]:
        """Process smoke/fire damper per NFPA 72 §21.7."""
        module = MEPInterfaceModule(
            module_id=f"DAMPER-CTL-{elem.element_id}",
            module_type=ModuleType.SUPERVISORY,
            target_element_id=elem.element_id,
            address_type=self._default_address_type,
            nfpa_reference="NFPA 72-2022 §21.7",
            zone_id=elem.zone_id,
            floor_id=elem.floor_id,
            description=(
                f"Damper supervisory module for '{elem.element_id}' "
                f"({elem.element_type.value}). Monitors damper position per §21.7."
            ),
        )
        return [module]

    def _process_duct(
        self,
        elem: MEPElement,
        warnings: List[str],
    ) -> List[MEPInterfaceModule]:
        """Process duct element per NFPA 90A §5.3."""
        module = MEPInterfaceModule(
            module_id=f"DUCT-DET-{elem.element_id}",
            module_type=ModuleType.SUPERVISORY,
            target_element_id=elem.element_id,
            address_type=self._default_address_type,
            nfpa_reference="NFPA 90A-2024 §5.3",
            zone_id=elem.zone_id,
            floor_id=elem.floor_id,
            description=(
                f"Duct detector supervisory for '{elem.element_id}'. "
                f"Per NFPA 90A §5.3, duct smoke detection required in "
                f"air distribution systems."
            ),
        )
        return [module]


__all__ = [
    "AHU_CFM_THRESHOLD",
    "MEP_UNIT_COSTS",
    "AddressType",
    "ElevatorPhase",
    "ElevatorRecallSpec",
    "HVACShutdownSpec",
    "MEPElement",
    "MEPElementType",
    "MEPInterfaceModule",
    "MEPSyncInjector",
    "MEPSyncResult",
    "ModuleType",
    "extend_boq_with_mep_modules",
    "validate_mep_elements",
]
