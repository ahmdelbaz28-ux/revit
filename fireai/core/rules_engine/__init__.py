"""FireAI NFPA 72 Rules Engine — Safety-Critical Declarative Rules System
======================================================================

A pure-Python forward-chaining rules engine designed specifically for
NFPA 72 fire alarm compliance. Inspired by the Rete algorithm from
durable_rules (jruizgit/rules) but rebuilt from scratch with:

1. Full audit trail for every rule evaluation (safety-critical requirement)
2. Truth Maintenance System (TMS) — derived conclusions retract when
   base facts change
3. Priority-based conflict resolution with deterministic ordering
4. Thread-safe operation for concurrent analysis sessions
5. No C dependencies — pure Python for memory safety and auditability
6. Structured rule definitions with NFPA section references
7. Type-safe API contract system (tRPC-inspired)
8. Compliance bridge for backward-compatible integration

Architecture:
    Fact → Alpha Network (condition matching) → Beta Network (join evaluation)
    → Action Scheduling → Conflict Resolution → Action Execution → TMS Update

Reference: NFPA 72-2022, IEC 60079-10-1:2015, NEC Chapter 9
"""

from fireai.core.rules_engine.api_contract import (
    APIContract,
    ContractSeverity,
    ContractValidator,
    ContractViolationDetail,
    create_contract_aware_router,
    generate_typescript_config,
)
from fireai.core.rules_engine.compliance_bridge import (
    ComplianceReport,
    NFPA72ComplianceChecker,
    detector_to_fact,
    elevator_to_fact,
    hvac_to_fact,
    results_to_report,
    room_to_facts,
)
from fireai.core.rules_engine.engine import (
    Fact,
    Rule,
    RuleAuditEntry,
    RulePriority,
    RuleResult,
    RulesEngine,
)
from fireai.core.rules_engine.nfpa72_rules import NFPA72RuleSet
from fireai.core.rules_engine.truth_maintenance import (
    DependencyRecord,
    TruthMaintenanceSystem,
)

__all__ = [
    # Engine core
    "RulesEngine",
    "Rule",
    "Fact",
    "RulePriority",
    "RuleResult",
    "RuleAuditEntry",
    # Truth Maintenance
    "TruthMaintenanceSystem",
    "DependencyRecord",
    # NFPA 72 Rules
    "NFPA72RuleSet",
    # Compliance Bridge
    "NFPA72ComplianceChecker",
    "ComplianceReport",
    "room_to_facts",
    "detector_to_fact",
    "hvac_to_fact",
    "elevator_to_fact",
    "results_to_report",
    # API Contract
    "APIContract",
    "ContractValidator",
    "ContractSeverity",
    "ContractViolationDetail",
    "create_contract_aware_router",
    "generate_typescript_config",
]

__version__ = "1.0.0"
