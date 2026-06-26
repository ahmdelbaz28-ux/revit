"""
backend/services/ — External API integration services for FireAI.

These services provide real-world environmental data (weather, geolocation,
regulatory context, elevation, air quality, severe weather, hazardous materials)
to the FireAI calculation engine.

LIFE-SAFETY DESIGN PRINCIPLE:
  All services follow a FAIL-SAFE pattern:
  1. Try to fetch real data from the external API
  2. On failure, return CONSERVATIVE DEFAULTS (never block calculations)
  3. Log every fallback with WARNING severity
  4. Record data provenance in every response (source="api" | "default")

A life-safety system MUST NEVER fail to produce a result because an
external API is down. Conservative defaults are always safer than
no calculation at all.

Phase 1 Services (already integrated):
  - WeatherService: Open-Meteo (temperature, wind, humidity)
  - GeocodingService: Nominatim (address → coordinates)
  - RegionService: REST Countries (regulatory framework detection)

Phase 2 Services (already integrated):
  - ElevationService: Open Topo Data (terrain elevation, atmospheric pressure)
  - AirQualityService: WAQI (AQI, PM2.5, PM10 for tenability)
  - SevereWeatherService: US NWS (weather alerts for safety calculations)
  - HazmatService: Internal DB + PubChem (hazardous material properties)

Phase 4 — Memory Layer (this release):
  - MemoryService: Mem0 + Qdrant (long-term memory for engineering context)
    Stores and retrieves: layouts, preferences, standards, calculations,
    device mappings, engineering decisions with rationale.
    CRITICAL: Memory is ADVISORY CONTEXT only — never overrides calculations.
"""

from backend.services.air_quality_service import AirQualityData, AirQualityService
from backend.services.elevation_service import ElevationData, ElevationService
from backend.services.geocoding_service import GeocodingResult, GeocodingService
from backend.services.hazmat_service import (
    HazardousMaterialData,
    HazmatService,
    MaterialGroup,
    TemperatureClass,
)
from backend.services.region_service import RegionContext, RegionService
from backend.services.severe_weather_service import (
    SevereWeatherData,
    SevereWeatherService,
    WeatherAlert,
)
from backend.services.weather_service import WeatherData, WeatherService

# Optional: Workflow Engine — requires langgraph (pip install fireai[workflow])
try:
    from backend.services.workflow_service import (
        PipelineState,
        WorkflowService,
        WorkflowStatus,
        close_workflow_service,
        get_workflow_service,
    )

    WORKFLOW_AVAILABLE = True
except ImportError:
    WORKFLOW_AVAILABLE = False
    WorkflowService = None  # type: ignore[misc]
    PipelineState = None  # type: ignore[misc]
    WorkflowStatus = None  # type: ignore[misc]
    get_workflow_service = None
    close_workflow_service = None

# Optional: Memory Layer — requires mem0 + qdrant-client (pip install fireai[memory])
try:
    from backend.services.memory_service import (
        MemoryAddRequest,
        MemoryCategory,
        MemoryResult,
        MemoryScope,
        MemorySearchRequest,
        MemorySearchResponse,
        MemoryService,
        MemoryServiceStatus,
        close_memory_service,
        get_memory_service,
    )

    MEMORY_AVAILABLE = True
except ImportError:
    MEMORY_AVAILABLE = False
    MemoryService = None  # type: ignore[misc]
    MemoryAddRequest = None  # type: ignore[misc]
    MemorySearchRequest = None  # type: ignore[misc]
    MemorySearchResponse = None  # type: ignore[misc]
    MemoryResult = None  # type: ignore[misc]
    MemoryServiceStatus = None  # type: ignore[misc]
    MemoryScope = None  # type: ignore[misc]
    MemoryCategory = None  # type: ignore[misc]
    get_memory_service = None
    close_memory_service = None

__all__ = [
    "AirQualityData",
    "AirQualityService",
    "ElevationData",
    # Phase 2
    "ElevationService",
    "GeocodingResult",
    "GeocodingService",
    "HazardousMaterialData",
    "HazmatService",
    "MaterialGroup",
    "MemoryAddRequest",
    "MemoryCategory",
    "MemoryResult",
    "MemoryScope",
    "MemorySearchRequest",
    "MemorySearchResponse",
    # Phase 4 — Memory Layer (optional)
    "MemoryService",
    "MemoryServiceStatus",
    "PipelineState",
    "RegionContext",
    "RegionService",
    "SevereWeatherData",
    "SevereWeatherService",
    "TemperatureClass",
    "WeatherAlert",
    "WeatherData",
    # Phase 1
    "WeatherService",
    # Phase 3 — Workflow Engine (optional)
    "WorkflowService",
    "WorkflowStatus",
    "close_memory_service",
    "close_workflow_service",
    "get_memory_service",
    "get_workflow_service",
]
