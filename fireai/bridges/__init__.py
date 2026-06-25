"""fireai/bridges — BIM Integration Bridges for FireAI
=====================================================
Headless bridges for reading/writing building data without
requiring active GUI applications (Revit, AutoCAD, etc.).
"""

from fireai.bridges.enterprise_pipeline import EnterpriseOrchestrator
from fireai.bridges.ifc_headless_bridge import HeadlessIFCBridge
from fireai.bridges.ifc_pipeline import IfcFirePipeline, IfcPipelineConfig

# V25 — Integration Bridge + BIM/Revit Sync
from fireai.bridges.integration_bridge import (
    AcousticConfig,
    CableRoutingResult,
    FloorData,
    IntegrationBridge,
    IntegrationConfig,
    IntegrationResult,
)
from fireai.bridges.revit_bim_sync import (
    BIMRoom,
    BIMSyncOrchestrator,
    RevitAPIBridge,
    generate_dynamo_script,
)

__all__ = [
    "HeadlessIFCBridge",
    "EnterpriseOrchestrator",
    "IfcFirePipeline",
    "IfcPipelineConfig",
    # V25 — Integration + BIM
    "IntegrationBridge",
    "IntegrationConfig",
    "IntegrationResult",
    "FloorData",
    "AcousticConfig",
    "CableRoutingResult",
    "BIMSyncOrchestrator",
    "RevitAPIBridge",
    "BIMRoom",
    "generate_dynamo_script",
]
