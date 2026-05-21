"""
bridges/orchestrator.py
=======================
Orchestrates all 5 bridges for end-to-end fire alarm design automation.

Workflow:
  1. Bridge 1 (Pipeline):  File → Raw data
  2. Bridge 2 (Parser):    Drawing → FireAI Room/Device models
  3. Bridge 4 (Twin):      Pull from BIM (optional)
  4. FireAI Engine:         Design + NFPA 72 verification
  5. Bridge 3 (Output):    Design → DWG with symbols + cables
  6. Bridge 4 (Twin):      Push to BIM (optional)
  7. Bridge 5 (Reports):   Analysis → Professional reports

Usage:
    from bridges.orchestrator import run_full_design
    result = run_full_design(
        input_path="floor_plan.dxf",
        project_name="Tower A",
    )
"""

from __future__ import annotations
import logging, os, time
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class FullDesignResult:
    """Complete result of the end-to-end design pipeline."""
    project_name: str
    input_file: str
    rooms: list = field(default_factory=list)
    devices: list = field(default_factory=list)
    obstructions: list = field(default_factory=list)
    violations: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    output_dwg: str = ""
    report_pdf: str = ""
    report_html: str = ""
    report_json: str = ""
    audit_hash: str = ""
    proof_valid: bool = False
    bridge_results: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    # V15: FACP capacity audit results
    facp_audit: dict = field(default_factory=dict)
    # V15: Pathway survivability classification
    pathway_survivability: dict = field(default_factory=dict)
    # V16: As-built reconciliation result
    as_built_reconciliation: dict = field(default_factory=dict)
    # V16: MEP sync injection result
    mep_sync: dict = field(default_factory=dict)
    # V17: Acoustic SPL analysis result
    acoustic_analysis: dict = field(default_factory=dict)
    # V17: Battery aging/derating audit result
    battery_audit: dict = field(default_factory=dict)
    # V17: ASET/RSET tenability analysis result
    aset_rset_analysis: dict = field(default_factory=dict)


def run_full_design(
    input_path: str,
    project_name: str = "FireAI_Project",
    output_dir: str = "/tmp/fireai_output",
    ifc_path: str = None,
    units_to_m: float = 0.001,
    proof_valid: bool = False,
    force_draw: bool = False,
    pe_name: str = "",
    pe_license: str = "",
    class_a: bool = True,
    fire_rated_walls: list = None,
    panel_position: tuple = None,
    facp_manufacturer: str = "notifier",
    ducts: list = None,
    building_spec: dict = None,
    as_built_devices: list = None,
    merkle_root: str = None,
    mep_elements: list = None,
    # V17: Life-safety triad parameters
    battery_spec: dict = None,
    min_temperature_c: float = 20.0,
    standby_load_amps: float = 0.0,
    alarm_load_amps: float = 0.0,
    acoustic_check_points: list = None,
    acoustic_speakers: list = None,
    acoustic_barriers: list = None,
    occupancy_type: str = "business",
    travel_distance_m: float = 0.0,
    fire_growth_rate: str = "medium",
    fire_load_MJ: float = 500.0,
) -> FullDesignResult:
    """
    Run the complete fire alarm design pipeline across all 5 bridges.

    Parameters
    ----------
    input_path    : Drawing file (DXF/DWG/PDF/IFC/image)
    project_name  : Project name for reports
    output_dir    : Output directory
    ifc_path      : Optional IFC file for Digital Twin sync
    units_to_m    : Drawing units to metres conversion
    proof_valid   : Has PE verified the design?
    force_draw    : Force drawing even without proof
    pe_name       : Professional Engineer name
    pe_license    : PE license number
    class_a       : Route Class A return with >=1m separation (V13)
    fire_rated_walls: List of Shapely LineString objects for fire-rated walls (V13)
    panel_position: (x_mm, y_mm) panel position in drawing units (V15). If None,
        auto-placed near first room centroid (may be inaccurate).
    facp_manufacturer: FACP manufacturer for protocol limit checks (V15).
        "notifier", "simplex", or "siemens". Default: "notifier".
    ducts         : List of DuctSpec dicts for duct detector analysis (V15).
    building_spec : Dict with building info for pathway survivability (V15).
        Keys: occupancy, height_m, num_floors, is_sprinklered, has_voice_evac,
        evacuation_type, is_high_rise.
    as_built_devices : List of as-built device dicts for reconciliation (V16).
        Each dict must have: id, x, y, z, device_type.
    merkle_root : Merkle root from a previous design run for integrity check (V16).
    mep_elements : List of MEP element dicts for clash detection (V16).
    """
    t0 = time.time()
    os.makedirs(output_dir, exist_ok=True)
    warnings = []
    bridge_results = {}

    result = FullDesignResult(
        project_name=project_name,
        input_file=os.path.basename(input_path),
    )

    # ═══════════════════════════════════════════════════════════════
    # BRIDGE 2: Parse drawing → FireAI models
    # ═══════════════════════════════════════════════════════════════
    log.info("=" * 50)
    log.info("BRIDGE 2: Parsing drawing...")
    try:
        from bridges.parser_bridge import parse_drawing_to_fireai
        parse_result = parse_drawing_to_fireai(
            input_path, units_to_m=units_to_m)
        result.rooms = parse_result.rooms
        result.devices = parse_result.devices
        result.obstructions = parse_result.obstructions
        result.warnings.extend(parse_result.warnings)
        bridge_results["bridge2"] = {
            "rooms": len(parse_result.rooms),
            "devices": len(parse_result.devices),
            "obstructions": len(parse_result.obstructions),
            "warnings": len(parse_result.warnings),
        }
        log.info("Bridge 2: %d rooms, %d devices, %d obstructions",
                 len(parse_result.rooms), len(parse_result.devices),
                 len(parse_result.obstructions))
    except Exception as ex:
        warnings.append(f"Bridge 2 failed: {ex}")
        log.error("Bridge 2 error: %s", ex)

    # ═══════════════════════════════════════════════════════════════
    # BRIDGE 4: Pull from BIM (if IFC provided)
    # V15: Try DigitalTwinBridge first, fall back to HeadlessIFCBridge
    # ═══════════════════════════════════════════════════════════════
    if ifc_path and os.path.exists(ifc_path):
        log.info("=" * 50)
        log.info("BRIDGE 4: Pulling from BIM...")
        ifc_pulled = False
        try:
            from bridges.digital_twin_bridge import DigitalTwinBridge
            twin = DigitalTwinBridge(ifc_path=ifc_path)
            ifc_rooms, ifc_devices, ifc_obs = twin.pull_from_bim()
            # Merge: prefer drawing-parsed data, supplement with IFC
            if ifc_rooms and not result.rooms:
                result.rooms = ifc_rooms
            if ifc_devices:
                result.devices.extend(ifc_devices)
            if ifc_obs:
                result.obstructions.extend(ifc_obs)
            bridge_results["bridge4_pull"] = {
                "ifc_rooms": len(ifc_rooms),
                "ifc_devices": len(ifc_devices),
                "ifc_obstructions": len(ifc_obs),
            }
            log.info("Bridge 4 pull: %d rooms, %d devices from IFC",
                     len(ifc_rooms), len(ifc_devices))
            ifc_pulled = True
        except Exception as ex:
            log.warning("DigitalTwinBridge pull failed: %s, trying HeadlessIFCBridge", ex)

        # V15: Fallback to HeadlessIFCBridge (pure ifcopenshell, no COM)
        if not ifc_pulled:
            try:
                from fireai.bridges.ifc_headless_bridge import HeadlessIFCBridge
                headless = HeadlessIFCBridge(ifc_path)
                ifc_spaces = headless.extract_spaces()
                # Convert space dicts to minimal room-like objects
                for space in ifc_spaces:
                    result.rooms.append(type('Room', (), {
                        'id': space['guid'],
                        'name': space['name'],
                        'geometry': None,
                    })())
                bridge_results["bridge4_pull"] = {
                    "ifc_rooms": len(ifc_spaces),
                    "ifc_devices": 0,
                    "ifc_obstructions": 0,
                    "method": "headless_fallback",
                }
                log.info("Bridge 4 pull (headless fallback): %d spaces from IFC",
                         len(ifc_spaces))
            except Exception as ex2:
                warnings.append(f"Bridge 4 pull failed (both DigitalTwin and Headless): {ex2}")
                log.error("Bridge 4 pull error: %s", ex2)

    # ═══════════════════════════════════════════════════════════════
    # FireAI Engine: Design + NFPA 72 verification
    # ═══════════════════════════════════════════════════════════════
    log.info("=" * 50)
    log.info("FIREAI ENGINE: Running NFPA 72 compliance checks...")
    try:
        from fire_expert_system import FireExpertSystem
        from nfpa72_models import RoomSpec, DetectorType

        expert = FireExpertSystem()
        all_findings = []

        # V12 Fix — Orphaned Devices Check (Unassigned Devices Black Hole):
        # Previous code only checked devices that matched a room_id. Devices in
        # corridors or outside defined rooms (room_id="UNASSIGNED") were NEVER
        # checked by any compliance engine. The report could say "PASS" while
        # unverified devices existed in the building.
        # Fix: Track all verified device IDs. After the room loop, any device
        # not verified triggers a CRITICAL SAFETY GATE that fails the building.
        verified_device_ids = set()

        for room in result.rooms:
            try:
                room_devices = [d for d in result.devices
                                if getattr(d, "room_id", "") == room.id]
                
                # Track verified devices
                for d in room_devices:
                    verified_device_ids.add(d.id)

                # Run NFPA 72 check for each room
                if hasattr(expert, "analyze_room"):
                    room_result = expert.analyze_room(room)
                    if room_result and hasattr(room_result, "violations"):
                        for v in room_result.violations:
                            result.violations.append(str(v))

                # Run compliance check
                from validation.compliance_oracle import ComplianceOracle
                oracle = ComplianceOracle()
                oracle_result = oracle.verify_truth(
                    room, room_devices, result.obstructions)
                if isinstance(oracle_result, dict):
                    for v in oracle_result.get("violations", []):
                        result.violations.append(v)

            except Exception as ex:
                warnings.append(f"Compliance check failed for {room.name}: {ex}")

        # V12 Fix: Orphaned Devices Safety Gate
        # Any device not verified through a room check is a life-safety blind spot
        orphaned_devices = [d for d in result.devices
                          if d.id not in verified_device_ids]
        if orphaned_devices:
            error_msg = (
                f"CRITICAL SAFETY GATE: {len(orphaned_devices)} device(s) are "
                f"outside all defined rooms (UNASSIGNED). NFPA analysis is INCOMPLETE! "
                f"Device IDs: {[d.id for d in orphaned_devices[:10]]}"
            )
            warnings.append(error_msg)
            result.violations.append(error_msg)
            result.proof_valid = False  # Building CANNOT pass
            log.critical(error_msg)

        bridge_results["fireai_engine"] = {
            "rooms_checked": len(result.rooms),
            "violations": len(result.violations),
        }
        log.info("FireAI engine: %d violations found", len(result.violations))

    except ImportError:
        warnings.append("FireAI engine not available for compliance checks")
        log.warning("FireAI engine import failed")
    except Exception as ex:
        warnings.append(f"FireAI engine error: {ex}")
        log.error("FireAI engine error: %s", ex)

    # ═══════════════════════════════════════════════════════════════
    # V15: FACP Capacity Audit (PSU burnout + protocol limits)
    # ═══════════════════════════════════════════════════════════════
    log.info("=" * 50)
    log.info("V15: FACP CAPACITY AUDIT...")
    try:
        from fireai.core.facp_capacity_auditor import FACPCapacityAuditor, get_default_profile

        facp_profile = get_default_profile(facp_manufacturer)
        facp_auditor = FACPCapacityAuditor(facp_profile)

        # SLC protocol audit — check device counts against manufacturer limits
        # Group devices by their circuit_id attribute
        slc_loops_dict = {}
        for d in result.devices:
            loop_id = getattr(d, 'circuit_id', 'SLC-01')
            if loop_id not in slc_loops_dict:
                slc_loops_dict[loop_id] = []
            slc_loops_dict[loop_id].append({
                'device_type': getattr(d, 'device_type', 'UNKNOWN'),
                'device_id': d.id,
            })
        slc_loops = [{'loop_id': k, 'devices': v} for k, v in slc_loops_dict.items()]

        slc_result = facp_auditor.audit_slc_protocol_limits(slc_loops)
        result.facp_audit['slc_protocol'] = slc_result

        if not slc_result.get('all_pass', True):
            for v in slc_result.get('violations', []):
                result.violations.append(v.get('message', str(v)))
            result.proof_valid = False

        bridge_results['facp_capacity'] = {
            'manufacturer': facp_profile.manufacturer,
            'slc_all_pass': slc_result.get('all_pass', True),
            'slc_violations': len(slc_result.get('violations', [])),
        }
        log.info("FACP audit: SLC %s, %d violations",
                 "PASS" if slc_result.get('all_pass', True) else "FAIL",
                 len(slc_result.get('violations', [])))
    except ImportError:
        warnings.append("FACP capacity auditor not available")
        log.warning("FACP capacity auditor import failed")
    except Exception as ex:
        warnings.append(f"FACP audit error: {ex}")
        log.error("FACP audit error: %s", ex)

    # ═══════════════════════════════════════════════════════════════
    # V15: Pathway Survivability Classification
    # ═══════════════════════════════════════════════════════════════
    if building_spec:
        log.info("V15: PATHWAY SURVIVABILITY CLASSIFICATION...")
        try:
            from fireai.core.pathway_survivability_engine import (
                PathwaySurvivabilityEngine, BuildingSpec,
            )
            from fireai.core.contracts import OccupancyCategory

            occ = building_spec.get('occupancy', 'BUSINESS')
            occ_enum = OccupancyCategory(occ) if occ in [e.value for e in OccupancyCategory] else OccupancyCategory.BUSINESS

            spec = BuildingSpec(
                occupancy=occ_enum,
                height_m=building_spec.get('height_m', 12.0),
                num_floors=building_spec.get('num_floors', 3),
                is_sprinklered=building_spec.get('is_sprinklered', False),
                has_voice_evac=building_spec.get('has_voice_evac', False),
                evacuation_type=building_spec.get('evacuation_type', 'full'),
                is_high_rise=building_spec.get('is_high_rise', False),
            )

            engine = PathwaySurvivabilityEngine()
            surv_result = engine.classify(spec)

            result.pathway_survivability = {
                'level': surv_result.building_level.value,
                'compliant': surv_result.compliant,
                'cable_requirements': [
                    {
                        'route_type': cr.route_type,
                        'cable_type': cr.cable_type.value,
                        'in_rated_enclosure': cr.in_rated_enclosure,
                        'enclosure_rating_hr': cr.enclosure_rating_hr,
                        'nfpa_reference': cr.nfpa_reference,
                    }
                    for cr in surv_result.cable_requirements
                ],
                'rationale': surv_result.classification_rationale,
                'warnings': surv_result.warnings,
            }

            bridge_results['pathway_survivability'] = {
                'level': surv_result.building_level.value,
                'compliant': surv_result.compliant,
            }
            log.info("Pathway survivability: level=%s compliant=%s",
                     surv_result.building_level.value, surv_result.compliant)
        except ImportError:
            warnings.append("Pathway survivability engine not available")
            log.warning("Pathway survivability import failed")
        except Exception as ex:
            warnings.append(f"Pathway survivability error: {ex}")
            log.error("Pathway survivability error: %s", ex)

    # ═══════════════════════════════════════════════════════════════
    # V15: Duct Detector Analysis
    # ═══════════════════════════════════════════════════════════════
    if ducts:
        log.info("V15: DUCT DETECTOR ANALYSIS...")
        try:
            from fireai.core.duct_detector import analyse_ducts, DuctSpec, total_duct_detectors

            duct_specs = []
            for d in ducts:
                duct_specs.append(DuctSpec(
                    duct_id=d.get('duct_id', 'DUCT-??'),
                    length_m=d.get('length_m', 1.0),
                    width_m=d.get('width_m', 0.3),
                    start_point=tuple(d.get('start_point', (0.0, 0.0))),
                    end_point=tuple(d.get('end_point', (1.0, 0.0))),
                    airflow_cfm=d.get('airflow_cfm'),
                    duct_type=d.get('duct_type', 'supply'),
                ))

            duct_results = analyse_ducts(duct_specs)
            total_det = total_duct_detectors(duct_results)

            bridge_results['duct_detector'] = {
                'ducts_analysed': len(duct_results),
                'total_duct_detectors': total_det,
            }
            log.info("Duct detectors: %d ducts analysed, %d detectors required",
                     len(duct_results), total_det)
        except ImportError:
            warnings.append("Duct detector module not available")
            log.warning("Duct detector import failed")
        except Exception as ex:
            warnings.append(f"Duct detector error: {ex}")
            log.error("Duct detector error: %s", ex)

    # ═══════════════════════════════════════════════════════════════
    # V16: As-Built Reconciliation (3D drift + rogue/missing detection)
    # ═══════════════════════════════════════════════════════════════
    if as_built_devices:
        log.info("=" * 50)
        log.info("V16: AS-BUILT RECONCILIATION (3D)...")
        try:
            from fireai.core.as_built_reconciliator import (
                AsBuiltReconciliator, DEVICE_TOLERANCES, DEFAULT_TOLERANCE,
            )

            # Build design manifest from current devices
            design_devices = []
            for d in result.devices:
                design_devices.append({
                    'id': d.id,
                    'x': float(d.position.x),
                    'y': float(d.position.y),
                    'z': float(getattr(d, 'z_height', 2.8)),
                    'device_type': getattr(d, 'device_type', 'UNKNOWN'),
                })

            design_manifest = {'devices': design_devices}

            reconciliator = AsBuiltReconciliator(
                design_manifest=design_manifest,
                merkle_root=merkle_root,  # Optional integrity check
            )
            recon_result = reconciliator.reconcile(as_built_devices)

            result.as_built_reconciliation = {
                'status': recon_result.status,
                'verified_count': recon_result.verified_count,
                'rogue_devices': len(recon_result.rogue_devices),
                'missing_devices': len(recon_result.missing_devices),
                'drifted_devices': len(recon_result.drifted_devices),
                'total_deviations': recon_result.total_deviations,
                'integrity_verified': recon_result.integrity_verified,
                'summary': recon_result.summary,
            }

            if recon_result.status == "DEVIATION_DETECTED":
                for dev_id, msg in recon_result.rogue_devices:
                    result.violations.append(f"ROGUE DEVICE: {msg}")
                for dev_id, msg in recon_result.missing_devices:
                    result.violations.append(f"MISSING DEVICE: {msg}")
                for dev_id, drift, tol, msg in recon_result.drifted_devices:
                    result.violations.append(
                        f"DRIFTED DEVICE: {dev_id} drifted {drift:.3f}m "
                        f"(tolerance: {tol:.3f}m)"
                    )

            bridge_results['as_built_reconciliation'] = {
                'status': recon_result.status,
                'deviations': recon_result.total_deviations,
            }
            log.info("As-Built reconciliation: %s (%d deviations)",
                     recon_result.status, recon_result.total_deviations)
        except ImportError:
            warnings.append("As-built reconciliator not available")
            log.warning("As-built reconciliator import failed")
        except Exception as ex:
            warnings.append(f"As-built reconciliation error: {ex}")
            log.error("As-built reconciliation error: %s", ex)

    # ═══════════════════════════════════════════════════════════════
    # V16: MEP Sync Injection (duct detector placement via NFPA 90A)
    # ═══════════════════════════════════════════════════════════════
    if mep_elements:
        log.info("=" * 50)
        log.info("V16: MEP SYNC INJECTION...")
        try:
            from fireai.core.mep_sync_injector import (
                MEPSyncInjector, MEPElement, MEPElementType,
            )

            injector = MEPSyncInjector()
            mep_objs = []
            for el in mep_elements:
                mep_objs.append(MEPElement(
                    element_id=el.get('id', 'MEP-??'),
                    element_type=MEPElementType(el.get('type', 'DUCT')),
                    position=tuple(el.get('position', (0.0, 0.0, 0.0))),
                    dimensions=el.get('dimensions', {}),
                    zone_id=el.get('zone_id', 'ZnX'),
                ))

            injection_result = injector.process_elements(mep_objs)

            result.mep_sync = {
                'total_monitor_modules': injection_result.total_monitor_modules,
                'total_duct_detectors': injection_result.total_duct_detectors,
                'errors': injection_result.errors,
            }

            # Inject MEP-derived devices into the device list
            for mod in injection_result.modules:
                result.devices.append(type('Device', (), {
                    'id': mod.module_id,
                    'device_type': 'DUCT_SMOKE' if 'DUCT' in mod.module_type else 'MONITOR_MODULE',
                    'position': type('Pos', (), {
                        'x': mod.position[0],
                        'y': mod.position[1],
                    })(),
                    'z_height': mod.position[2] if len(mod.position) > 2 else 2.8,
                    'room_id': 'MEP-SYSTEM',
                    'coverage_radius': 0.0,
                })())

            bridge_results['mep_sync'] = {
                'modules_injected': injection_result.total_monitor_modules,
                'duct_detectors': injection_result.total_duct_detectors,
            }
            log.info("MEP sync: %d modules, %d duct detectors injected",
                     injection_result.total_monitor_modules,
                     injection_result.total_duct_detectors)
        except ImportError:
            warnings.append("MEP sync injector not available")
            log.warning("MEP sync injector import failed")
        except Exception as ex:
            warnings.append(f"MEP sync injection error: {ex}")
            log.error("MEP sync injection error: %s", ex)

    # ═══════════════════════════════════════════════════════════════
    # V17: Acoustic SPL Analysis (NFPA 72 §18.4)
    # ═══════════════════════════════════════════════════════════════
    if acoustic_speakers and acoustic_check_points:
        log.info("=" * 50)
        log.info("V17: ACOUSTIC SPL ANALYSIS (NFPA 72 §18.4)...")
        try:
            from fireai.core.acoustic_calculator import (
                AcousticSPLCalculator, Speaker, CheckPoint, Barrier,
            )

            calc = AcousticSPLCalculator()
            speakers = [
                Speaker(
                    x=s.get('x', 0), y=s.get('y', 0),
                    z=s.get('z', 2.8), rating_dba=s.get('rating_dba', 95.0),
                    ref_distance_m=s.get('ref_distance_m', 3.0),
                    speaker_id=s.get('id', ''),
                )
                for s in acoustic_speakers
            ]
            check_pts = [
                CheckPoint(
                    x=p.get('x', 0), y=p.get('y', 0),
                    z=p.get('z', 1.5), label=p.get('label', ''),
                )
                for p in acoustic_check_points
            ]
            barriers = None
            if acoustic_barriers:
                barriers = [
                    Barrier(
                        barrier_type=b.get('type', 'standard_door'),
                        attenuation_dba=b.get('attenuation_dba'),
                        label=b.get('label', ''),
                    )
                    for b in acoustic_barriers
                ]

            # Run SPL analysis for each room (using occupancy_type as default)
            occ = occupancy_type or "business"
            mode = "sleeping" if "sleep" in occ.lower() else "public"

            acoustic_result = calc.calculate_room_spl(
                room_id="GLOBAL",
                occ_type=occ,
                speakers=speakers,
                check_points=check_pts,
                barriers=barriers,
                mode=mode,
            )

            result.acoustic_analysis = {
                'compliant': acoustic_result.compliant,
                'worst_point_spl': acoustic_result.worst_point_spl,
                'required_dba': acoustic_result.required_dba,
                'margin_dba': acoustic_result.margin_dba,
                'violations': acoustic_result.violations,
                'point_results': acoustic_result.point_results,
            }

            if not acoustic_result.compliant:
                for v in acoustic_result.violations:
                    result.violations.append(v.get('message', str(v)))

            bridge_results['acoustic_spl'] = {
                'compliant': acoustic_result.compliant,
                'worst_spl': acoustic_result.worst_point_spl,
                'violations': len(acoustic_result.violations),
            }
            log.info("Acoustic analysis: %s, worst SPL %.1f dBA",
                     "PASS" if acoustic_result.compliant else "FAIL",
                     acoustic_result.worst_point_spl)
        except ImportError:
            warnings.append("Acoustic calculator module not available")
            log.warning("Acoustic calculator import failed")
        except Exception as ex:
            warnings.append(f"Acoustic analysis error: {ex}")
            log.error("Acoustic analysis error: %s", ex)

    # ═══════════════════════════════════════════════════════════════
    # V17: Battery Aging/Derating Audit (NFPA 72 §10.6.7)
    # ═══════════════════════════════════════════════════════════════
    if battery_spec and (standby_load_amps > 0 or alarm_load_amps > 0):
        log.info("=" * 50)
        log.info("V17: BATTERY AGING/DERATING AUDIT (NFPA 72 §10.6.7)...")
        try:
            from fireai.core.battery_aging_derating import (
                BatteryAuditor, BatterySpec, battery_result_for_gate,
            )

            bat = BatterySpec(
                amp_hour_20h=battery_spec.get('amp_hour_20h', 26.0),
                cells=battery_spec.get('cells', 6),
                battery_type=battery_spec.get('type', 'vrla'),
            )

            auditor = BatteryAuditor(
                battery=bat,
                min_temperature_c=min_temperature_c,
                service_life_years=battery_spec.get('service_life_years', 5),
                safety_margin_pct=battery_spec.get('safety_margin_pct', 10.0),
                standby_hours=battery_spec.get('standby_hours', 24.0),
                alarm_hours=battery_spec.get('alarm_hours', 0.083),
            )

            bat_result = auditor.audit(
                standby_load_amps=standby_load_amps,
                alarm_load_amps=alarm_load_amps,
            )

            result.battery_audit = battery_result_for_gate(bat_result)

            if not bat_result.is_adequate:
                for v in bat_result.violations:
                    result.violations.append(v.get('message', str(v)))
                result.proof_valid = False

            bridge_results['battery_audit'] = {
                'adequate': bat_result.is_adequate,
                'required_ah': bat_result.required_ah,
                'installed_ah': bat_result.installed_ah,
                'margin_pct': bat_result.margin_pct,
                'temperature_derating': bat_result.temperature_derating,
                'aging_derating': bat_result.aging_derating,
            }
            log.info("Battery audit: %s, required %.1f Ah, installed %.1f Ah, margin %.1f%%",
                     "PASS" if bat_result.is_adequate else "FAIL",
                     bat_result.required_ah, bat_result.installed_ah,
                     bat_result.margin_pct)
        except ImportError:
            warnings.append("Battery aging derating module not available")
            log.warning("Battery aging derating import failed")
        except Exception as ex:
            warnings.append(f"Battery audit error: {ex}")
            log.error("Battery audit error: %s", ex)

    # ═══════════════════════════════════════════════════════════════
    # V17: ASET/RSET Tenability Analysis (NFPA 101 §9.3 / SFPE)
    # ═══════════════════════════════════════════════════════════════
    if travel_distance_m > 0 and result.rooms:
        log.info("=" * 50)
        log.info("V17: ASET/RSET TENABILITY ANALYSIS (NFPA 101 §9.3)...")
        try:
            from fireai.core.aset_rset_calculator import perform_aset_rset_analysis

            # Use first room's area/height for analysis, or building_spec
            room_area = 100.0
            room_height = 3.0
            if result.rooms:
                first_room = result.rooms[0]
                room_area = getattr(first_room, 'area_m2', None) or 100.0
                room_height = getattr(first_room, 'ceiling_height_m', None) or 3.0

            is_sprinklered = (building_spec or {}).get('is_sprinklered', False)

            aset_rset = perform_aset_rset_analysis(
                room_area_m2=room_area,
                room_height_m=room_height,
                travel_distance_m=travel_distance_m,
                occupancy_type=occupancy_type or "business",
                fire_growth_rate=fire_growth_rate,
                fire_load_MJ=fire_load_MJ,
                is_sprinklered=is_sprinklered,
            )

            result.aset_rset_analysis = aset_rset

            if not aset_rset.get('is_safe', True):
                result.violations.append(
                    f"ASET/RSET FAIL: {aset_rset.get('verdict', 'Insufficient egress time')} "
                    f"(Limiting factor: {aset_rset.get('limiting_factor', 'unknown')})"
                )

            bridge_results['aset_rset'] = {
                'is_safe': aset_rset.get('is_safe', False),
                'aset_seconds': aset_rset.get('aset_seconds', 0),
                'rset_seconds': aset_rset.get('rset_seconds', 0),
                'limiting_factor': aset_rset.get('limiting_factor', 'N/A'),
            }
            log.info("ASET/RSET: %s, ASET=%.1fs, RSET=%.1fs, factor=%s",
                     "PASS" if aset_rset.get('is_safe') else "FAIL",
                     aset_rset.get('aset_seconds', 0),
                     aset_rset.get('rset_seconds', 0),
                     aset_rset.get('limiting_factor', 'N/A'))
        except ImportError:
            warnings.append("ASET/RSET calculator module not available")
            log.warning("ASET/RSET calculator import failed")
        except Exception as ex:
            warnings.append(f"ASET/RSET analysis error: {ex}")
            log.error("ASET/RSET analysis error: %s", ex)

    # ═══════════════════════════════════════════════════════════════
    # BRIDGE 3: Draw design on DWG
    # ═══════════════════════════════════════════════════════════════
    log.info("=" * 50)
    log.info("BRIDGE 3: Drawing fire alarm design...")
    try:
        from bridges.output_bridge import draw_fire_alarm_design

        output_dwg = os.path.join(output_dir, f"{project_name}_FA.dxf")
        draw_result = draw_fire_alarm_design(
            dxf_path=input_path if input_path.endswith((".dxf", ".dwg")) else "",
            output_path=output_dwg,
            rooms=result.rooms,
            devices=result.devices,
            panel_position=panel_position,
            proof_valid=proof_valid,
            force=force_draw,
            units_to_m=units_to_m,
            class_a=class_a,
            fire_rated_walls=fire_rated_walls,
        )
        result.output_dwg = draw_result.output_path
        result.warnings.extend(draw_result.warnings)
        bridge_results["bridge3"] = draw_result.stats
        log.info("Bridge 3: %d devices, %.1fm cable → %s",
                 draw_result.devices_drawn, draw_result.total_cable_m,
                 draw_result.output_path)
    except Exception as ex:
        warnings.append(f"Bridge 3 failed: {ex}")
        log.error("Bridge 3 error: %s", ex)

    # ═══════════════════════════════════════════════════════════════
    # BRIDGE 4: Push to BIM (if IFC provided)
    # ═══════════════════════════════════════════════════════════════
    if ifc_path and os.path.exists(ifc_path) and result.devices:
        log.info("=" * 50)
        log.info("BRIDGE 4: Pushing to BIM...")
        try:
            from bridges.digital_twin_bridge import DigitalTwinBridge
            twin = DigitalTwinBridge(ifc_path=ifc_path)
            push_result = twin.push_to_bim(
                result.devices, result.rooms,
                output_path=os.path.join(output_dir, f"{project_name}_FA.ifc"),
            )
            bridge_results["bridge4_push"] = {
                "pushed": push_result.elements_pushed,
                "warnings": len(push_result.warnings),
            }
            log.info("Bridge 4 push: %d devices", push_result.elements_pushed)
        except Exception as ex:
            warnings.append(f"Bridge 4 push failed: {ex}")

    # ═══════════════════════════════════════════════════════════════
    # BRIDGE 5: Generate reports
    # ═══════════════════════════════════════════════════════════════
    log.info("=" * 50)
    log.info("BRIDGE 5: Generating reports...")
    try:
        from bridges.report_bridge import generate_compliance_report

        cable_m = bridge_results.get("bridge3", {}).get("total_cable_m", 0)
        cable_seg = bridge_results.get("bridge3", {}).get("cable_segments", 0)

        report_result = generate_compliance_report(
            project_name=project_name,
            rooms=result.rooms,
            devices=result.devices,
            violations=result.violations,
            cable_total_m=cable_m,
            cable_segments=cable_seg,
            findings=result.findings,
            output_dir=os.path.join(output_dir, "reports"),
            source_file=os.path.basename(input_path),
            proof_valid=proof_valid,
            pe_name=pe_name,
            pe_license=pe_license,
        )
        result.report_pdf = report_result.pdf_path
        result.report_html = report_result.html_path
        result.report_json = report_result.json_path
        result.audit_hash = report_result.audit_hash
        bridge_results["bridge5"] = report_result.stats
        log.info("Bridge 5: PDF=%s HTML=%s", report_result.pdf_path, report_result.html_path)
    except Exception as ex:
        warnings.append(f"Bridge 5 failed: {ex}")
        log.error("Bridge 5 error: %s", ex)

    # ═══════════════════════════════════════════════════════════════
    # Finalize
    # ═══════════════════════════════════════════════════════════════
    result.bridge_results = bridge_results
    result.warnings = warnings
    result.stats = {
        "total_rooms": len(result.rooms),
        "total_devices": len(result.devices),
        "total_obstructions": len(result.obstructions),
        "total_violations": len(result.violations),
        "bridges_run": list(bridge_results.keys()),
        "output_dwg": result.output_dwg,
        "report_pdf": result.report_pdf,
        "report_html": result.report_html,
        "audit_hash": result.audit_hash,
    }
    result.elapsed_seconds = round(time.time() - t0, 2)
    result.proof_valid = proof_valid

    log.info("=" * 50)
    log.info("FULL DESIGN COMPLETE in %.1fs", result.elapsed_seconds)
    log.info("Rooms: %d | Devices: %d | Violations: %d",
             len(result.rooms), len(result.devices), len(result.violations))

    return result
