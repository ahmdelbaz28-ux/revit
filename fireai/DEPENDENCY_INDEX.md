# FireAI — Module Dependency Index

**Generated:** 2026-06-13
**Purpose:** Map module dependencies to prevent circular imports

---

## 📊 Summary

| Metric | Count |
|--------|-------|
| Total core modules | 72 |
| Layer 1 (Foundation) | 1 |
| Layer 2 (Standards) | 2 |
| Layer 3 (Engineering) | 4 |
| Layer 4 (Integration) | 6 |
| Circular imports | 0 |
| Layer violations | 19 |

---

## 🏗️ Architecture Layers

```
Layer 4 (Integration):    digital_twin, floor_orchestrator, analysis_pipeline
        │
Layer 3 (Engineering):    qomn_kernel, device_placement, density_optimizer
        │
Layer 2 (Standards):      nfpa72_coverage, nfpa72_engine, voltage_drop
        │
Layer 1 (Foundation):     contracts, nfpa72_models, nfpa72_calculations
```


## ⚠️ Layer Violations

| Module | Imports | Violation |
|--------|---------|----------|
| `polygon_optimizer` | `nfpa72_calculations` | Layer 0 imports Layer 1 |
| `boq_generator` | `nfpa72_calculations` | Layer 0 imports Layer 1 |
| `fire_cli` | `nfpa72_calculations` | Layer 0 imports Layer 1 |
| `fire_cli` | `building_engine` | Layer 0 imports Layer 4 |
| `cable_routing_engine` | `voltage_drop` | Layer 0 imports Layer 2 |
| `cable_routing_engine` | `circuit_topology` | Layer 0 imports Layer 3 |
| `pathway_survivability_engine` | `contracts` | Layer 0 imports Layer 1 |
| `floor_analyser` | `nfpa72_technology_dispatcher` | Layer 0 imports Layer 2 |
| `floor_analyser` | `nfpa72_calculations` | Layer 0 imports Layer 1 |
| `api_server` | `nfpa72_models` | Layer 0 imports Layer 1 |
| `density_optimizer_v2` | `nfpa72_models` | Layer 0 imports Layer 1 |
| `fire_expert_system` | `nfpa72_calculations` | Layer 0 imports Layer 1 |
| `compliance_proof_document` | `nfpa72_models` | Layer 0 imports Layer 1 |
| `room_templates` | `nfpa72_models` | Layer 0 imports Layer 1 |
| `cable_router` | `constraint_engine` | Layer 0 imports Layer 3 |
| `cable_router` | `nfpa72_engine` | Layer 0 imports Layer 2 |
| `fireai_core` | `nfpa72_models` | Layer 0 imports Layer 1 |
| `pdf_report` | `building_engine` | Layer 0 imports Layer 4 |
| `digital_twin_sync` | `digital_twin` | Layer 0 imports Layer 4 |


## 📦 Module Dependencies

| Module | Layer | Imports |
|--------|-------|---------|
| `acoustic_calculator` | 0 | acoustic_calculator |
| `acoustics_engine` | 0 | acoustic_calculator, acoustics_engine, ugld_acoustics, ugld_raytrace |
| `api_server` | 0 | fireai_core, nfpa72_models |
| `api_stability` | 0 | api_stability |
| `as_built_reconciliator` | 0 | as_built_reconciliator, blockchain_readiness_gate |
| `aset_rset_calculator` | 0 | aset_rset_calculator, semi_cfast_engine |
| `atex_hazardous_arbiter` | 0 | international_reg_selector, models_v21 |
| `auto_drafting_engine` | 0 | auto_drafting_engine |
| `battery_aging_derating` | 3 | battery_aging_derating, provenance |
| `blockchain_readiness_gate` | 0 | blockchain_readiness_gate |
| `boq_generator` | 0 | acoustic_calculator, fault_isolator_injector, nfpa72_calculations |
| `bps_allocator` | 0 | provenance |
| `building_engine` | 4 | building_engine, delta_cache, fire_zone_engine, floor_analyser, project_learner |
| `cable_router` | 0 | cable_routing_engine, constraint_engine, contracts_validation, ifc_parser, nfpa72_engine |
| `cable_routing_engine` | 0 | circuit_topology, voltage_drop |
| `ci_benchmark` | 0 | delta_cache, streaming_dwg_parser |
| `compliance_proof_document` | 0 | compliance_proof_document, nfpa72_models |
| `conduit_fill_analyzer` | 0 | conduit_fill_analyzer, provenance |
| `constraint_engine` | 3 | cable_routing_engine, nfpa72_engine |
| `density_optimizer_v2` | 0 | density_optimizer_v2, nfpa72_models |
| `device_placement` | 3 | qomn_kernel |
| `digital_twin` | 4 | digital_twin |
| `digital_twin_interface` | 4 | digital_twin_interface |
| `digital_twin_sync` | 0 | digital_twin, digital_twin_sync |
| `elevator_shunt_trip` | 0 | provenance |
| `event_bus` | 0 | event_bus |
| `evidence_chain` | 0 | evidence_chain |
| `facp_capacity_auditor` | 0 | provenance |
| `fault_isolator_injector` | 0 | fault_isolator_injector |
| `fire_cli` | 0 | building_engine, floor_analyser, geometry_utils, nfpa72_calculations, pdf_report, polygon_optimizer |
| `fire_expert_system` | 0 | nfpa72_calculations |
| `fireai_api` | 0 | fireai_core |
| `fireai_cli_engine` | 0 | atex_hazardous_arbiter, flame_detector_aoc_raytrace, hac_classification_engine, international_reg_selector, models_v21, safety_audit_engine |
| `fireai_core` | 0 | audit_blockchain_bridge, audit_store, fire_expert_system, kernel_v30_integration, learning_store, monte_carlo_pipeline, nfpa72_models |
| `flame_detector_aoc_raytrace` | 0 | models_v21, safety_audit_engine |
| `floor_analyser` | 0 | duct_detector, floor_analyser, geometry_utils, nfpa72_calculations, nfpa72_technology_dispatcher, polygon_optimizer, scenario_engine, sensor_physics_advisor |
| `floor_orchestrator` | 4 | nfpa72_calculations, nfpa72_models |
| `hac_classification_engine` | 0 | international_reg_selector, models_v21 |
| `hybrid_survivability` | 0 | flame_detector_aoc_raytrace, models_v21, ugld_acoustics, ugld_raytrace |
| `international_reg_selector` | 0 | models_v21 |
| `kernel_v30_integration` | 0 | kernel_v30_integration |
| `mep_sync_injector` | 0 | mep_sync_injector |
| `multi_floor_orchestrator` | 4 | cable_routing_engine, duct_detector, elevator_shunt_trip, floor_orchestrator, multi_floor_orchestrator, stairwell_smoke_control, voltage_drop |
| `network_topology` | 3 | provenance |
| `nfpa72_models` | 1 | contracts, nfpa72_models |
| `nfpa72_technology_dispatcher` | 2 | nfpa72_calculations |
| `parameter_optimizer` | 0 | parameter_optimizer |
| `pathway_survivability_engine` | 0 | contracts |
| `pdf_report` | 0 | building_engine, pdf_report, scenario_engine |
| `pipeline` | 4 | cable_router, cable_routing_engine, constraint_engine, contracts_validation, ifc_parser, nfpa72_engine, qomn_kernel, release_gates, safety_assurance, schedule_generator |
| `polygon_optimizer` | 0 | duct_detector, geometry_utils, nfpa72_calculations, polygon_optimizer |
| `project_learner` | 0 | project_learner |
| `revit_acl` | 0 | models_v21 |
| `revit_exporter` | 0 | cable_router |
| `room_lifecycle` | 0 | room_lifecycle |
| `room_templates` | 0 | nfpa72_models, room_templates |
| `routing_engine_v10` | 0 | production_config, routing_engine_v10 |
| `routing_global_class_a` | 0 | provenance, routing_engine_v10 |
| `safety_assurance` | 0 | audit_log |
| `safety_audit_engine` | 0 | models_v21 |
| `scenario_engine` | 0 | geometry_utils |
| `secret_rotation` | 0 | secret_rotation, security_logging |
| `security_logging` | 0 | security_logging |
| `seismic_joint_penalyer` | 0 | provenance |
| `sensitivity_analyzer` | 0 | sensitivity_analyzer |
| `sequence_of_operations` | 2 | provenance, sequence_of_operations |
| `slc_capacitance` | 0 | provenance |
| `stairwell_smoke_control` | 0 | building_systems_integration, provenance |
| `submittal_integrity_gate` | 0 | provenance |
| `twin_db` | 0 | twin_db |
| `ugld_acoustics` | 0 | ugld_acoustics |
| `ugld_raytrace` | 0 | ugld_acoustics, ugld_raytrace |

---

## 🚫 Circular Import Prevention Rules

1. **Never** import from `fireai/core/__init__.py` inside core modules
2. **Always** import from specific modules: `from fireai.core.nfpa72_models import ...`
3. **Avoid** importing services in models - use dependency injection
4. **Keep** `contracts.py` free of implementation dependencies

---

*Auto-generated by `fireai/tools/dependency_indexer.py`*
