"""fireai/integration — External system integration bridges."""

from fireai.integration.autocad_bridge import AutoCADBridge
from fireai.integration.bentley_bridge import BentleyBridge
from fireai.integration.field_data_service import FieldDataService
from fireai.integration.iot_pipeline import IoTPipeline
from fireai.integration.mobile_api import MobileAPI

# V82 — External advisory API adapters (safety-critical, fail-safe).
# Each adapter is ADVISORY ONLY — never blocks detector signals.
from fireai.integration.external_api_base import (
    ApiResult,
    CircuitState,
    ExternalApiAdapter,
)
from fireai.integration.wildfire_smoke_adapter import (
    WildfireSmokeAdapter,
    WildfireSmokeAssessment,
)
from fireai.integration.earthquake_adapter import (
    EarthquakeAdapter,
    EarthquakeAssessment,
)
from fireai.integration.openaq_adapter import (
    OpenAQAdapter,
    AirQualityAssessment,
)
from fireai.integration.ais_vessel_adapter import (
    AISVesselAdapter,
    VesselProximityAssessment,
)
from fireai.integration.elevation_adapter import (
    ElevationAdapter,
    ElevationReading,
)

__all__ = [
    # Original bridges
    "AutoCADBridge",
    "BentleyBridge",
    "FieldDataService",
    "IoTPipeline",
    "MobileAPI",
    # V82 — External advisory API adapters
    "ApiResult",
    "CircuitState",
    "ExternalApiAdapter",
    "WildfireSmokeAdapter",
    "WildfireSmokeAssessment",
    "EarthquakeAdapter",
    "EarthquakeAssessment",
    "OpenAQAdapter",
    "AirQualityAssessment",
    "AISVesselAdapter",
    "VesselProximityAssessment",
    "ElevationAdapter",
    "ElevationReading",
]
