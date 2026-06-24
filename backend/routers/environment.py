"""backend/routers/environment.py — Environmental data endpoints for FireAI.

Provides real-time weather, geocoding, regulatory region, elevation,
air quality, severe weather alerts, and hazardous material data
for engineering calculations.

Endpoints:
  Phase 1:
  - GET /api/environment/weather?lat=...&lon=...
  - GET /api/environment/geocode?address=...
  - GET /api/environment/region?country_code=...
  - GET /api/environment/context?lat=...&lon=...

  Phase 2:
  - GET /api/environment/elevation?lat=...&lon=...
  - GET /api/environment/air-quality?lat=...&lon=...
  - GET /api/environment/severe-weather?lat=...&lon=...
  - GET /api/environment/hazmat?material=...
  - GET /api/environment/hazmat/known
  - GET /api/environment/full-context?lat=...&lon=...

LIFE-SAFETY NOTE:
  All endpoints return conservative defaults when external APIs are
  unavailable. Engineering calculations MUST NEVER be blocked by
  external API failures.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, Query

from backend.auth import require_permission
from backend.rbac import Permission
from backend.services.air_quality_service import get_air_quality_service
from backend.services.elevation_service import get_elevation_service
from backend.services.geocoding_service import GeocodingResult, get_geocoding_service
from backend.services.hazmat_service import get_hazmat_service
from backend.services.region_service import (
    ElectricalCode,
    RegionContext,
    RegulatoryFramework,
    get_region_service,
)
from backend.services.severe_weather_service import (
    get_severe_weather_service,
)
from backend.services.weather_service import get_weather_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/environment", tags=["environment"],
                dependencies=[Depends(require_permission(Permission.QOMN_READ))])


# ── Phase 1 Endpoints ───────────────────────────────────────────────────────

@router.get("/countries")
async def get_countries():
    """List supported countries and their regulatory frameworks.

    Returns the full country → regulatory framework mapping used by FireAI
    to determine applicable fire/electrical codes for each jurisdiction.
    """
    from backend.services.region_service import (
        _COUNTRY_FRAMEWORK_MAP,
    )
    countries = []
    for code, (framework, electrical) in sorted(_COUNTRY_FRAMEWORK_MAP.items()):
        countries.append({
            "country_code": code,
            "regulatory_framework": framework.value,
            "electrical_code": electrical.value,
        })
    return {
        "success": True,
        "data": {
            "total": len(countries),
            "countries": countries,
        },
    }


@router.get("/weather")
async def get_weather(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude"),
):
    """Get current weather data for engineering calculations.

    Returns ambient temperature, wind speed, and relative humidity.
    Falls back to conservative defaults when API is unavailable.

    Sources:
      - Primary: Open-Meteo (free, no auth)
      - Fallback: Conservative defaults per NFPA/engineering practice
    """
    weather_svc = get_weather_service()
    weather = await weather_svc.fetch_weather(lat, lon)

    return {
        "success": True,
        "data": {
            "temperature_c": weather.temperature_c,
            "wind_speed_m_s": weather.wind_speed_m_s,
            "relative_humidity_pct": weather.relative_humidity_pct,
            "outdoor_temp_c": weather.temperature_c,
            "air_density_kg_m3": round(weather.air_density_kg_m3, 4),
            "temperature_k": round(weather.temperature_k, 2),
            "source": weather.source,
            "is_default": weather.is_default,
            "is_stale": weather.is_stale,
            "fetched_at": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(weather.fetched_at)
            ),
            "location": {
                "latitude": weather.latitude,
                "longitude": weather.longitude,
            },
        },
    }


@router.get("/geocode")
async def geocode_address(
    address: str = Query(
        ..., min_length=2, max_length=500,
        description="Address to geocode (e.g., 'Cairo, Egypt')"
    ),
):
    """Geocode an address to coordinates.

    Uses Nominatim (OpenStreetMap) — free, no auth.
    Returns latitude, longitude, display name, and country code.
    """
    geo_svc = get_geocoding_service()
    result = await geo_svc.geocode(address)

    if result is None:
        return {
            "success": False,
            "error": f"Could not geocode address: {address}",
            "data": None,
        }

    return {
        "success": True,
        "data": {
            "latitude": result.latitude,
            "longitude": result.longitude,
            "display_name": result.display_name,
            "country_code": result.country_code,
            "source": result.source,
        },
    }


@router.get("/region")
async def get_region(
    country_code: str = Query(
        ..., min_length=2, max_length=2,
        description="ISO 3166-1 alpha-2 country code (e.g., 'US', 'EG', 'SA')"
    ),
):
    """Get regulatory region context for a country.

    Returns applicable fire/electrical codes and regulatory framework.
    Essential for determining which standards to apply in calculations.
    """
    region_svc = get_region_service()
    context = await region_svc.get_region_context(country_code)

    return {
        "success": True,
        "data": {
            "country_code": context.country_code,
            "country_name": context.country_name,
            "regulatory_framework": context.regulatory_framework.value,
            "electrical_code": context.electrical_code.value,
            "region_name": context.region_name,
            "is_gulf_state": context.is_gulf_state,
            "is_eu": context.is_eu,
            "source": context.source,
        },
    }


# ── Phase 2 Endpoints ───────────────────────────────────────────────────────

@router.get("/elevation")
async def get_elevation(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude"),
):
    """Get terrain elevation and atmospheric pressure for engineering calculations.

    Elevation affects:
      - Atmospheric pressure (barometric formula per ISO 2533)
      - Battery derating (altitude correction per NFPA 72 §10.14)
      - Smoke control pressurization (NFPA 92 §6.4.2)
      - HAC zone extent (IEC 60079-10-1 Annex B)

    Source: Open Topo Data (ASTER GDEM 30m resolution)
    Fallback: Sea level defaults (standard atmospheric pressure)
    """
    elev_svc = get_elevation_service()
    data = await elev_svc.fetch_elevation(lat, lon)

    return {
        "success": True,
        "data": {
            "elevation_m": data.elevation_m,
            "atmospheric_pressure_pa": data.atmospheric_pressure_pa,
            "pressure_correction_factor": data.pressure_correction_factor,
            "source": data.source,
            "is_default": data.is_default,
            "location": {
                "latitude": data.latitude,
                "longitude": data.longitude,
            },
            "engineering_notes": {
                "battery_derating": (
                    f"Pressure correction factor {data.pressure_correction_factor:.4f} "
                    f"applies to battery capacity per NFPA 72 §10.14"
                ),
                "smoke_control": (
                    f"Atmospheric pressure {data.atmospheric_pressure_pa:.0f} Pa "
                    f"affects pressurization design per NFPA 92 §6.4.2"
                ),
            },
        },
    }


@router.get("/air-quality")
async def get_air_quality(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude"),
):
    """Get air quality data for engineering calculations.

    AQI affects:
      - Tenability baseline (pre-existing air quality)
      - Smoke detection response time (ambient particulate levels)
      - Occupant vulnerability assessment (AQI > 150 = sensitive)
      - ASET/RSET margins (poor baseline = shorter tenability)

    Source: WAQI (World Air Quality Index, free demo token)
    Fallback: Moderate AQI (100) — conservative but not alarmist
    """
    aq_svc = get_air_quality_service()
    data = await aq_svc.fetch_air_quality(lat, lon)

    return {
        "success": True,
        "data": {
            "aqi": data.aqi,
            "aqi_level": data.aqi_level,
            "pm25_ug_m3": data.pm25_ug_m3,
            "pm10_ug_m3": data.pm10_ug_m3,
            "is_unhealthy_baseline": data.is_unhealthy_baseline,
            "source": data.source,
            "is_default": data.is_default,
            "is_stale": data.is_stale,
            "location": {
                "latitude": data.latitude,
                "longitude": data.longitude,
            },
            "engineering_notes": {
                "tenability": (
                    f"Baseline AQI={data.aqi} ({data.aqi_level}). "
                    f"{'UNHEALTHY baseline — increase tenability margins' if data.is_unhealthy_baseline else 'Acceptable baseline for tenability calculations'}."
                ),
                "detection": (
                    f"PM2.5={data.pm25_ug_m3}µg/m³ affects "
                    f"smoke detector response time estimation."
                ),
            },
        },
    }


def _build_coverage_note(coverage_area: str, source: str) -> str:
    """Build a human-readable coverage note for the severe-weather response.

    Informs the user when severe weather data may be incomplete or
    unavailable for their location, and suggests checking local
    meteorological services.

    Args:
        coverage_area: Geographic coverage indicator ("us", "eu", "global", "none")
        source: Data source that was used ("nws", "meteoalarm", "openmeteo", "default")

    Returns:
        Coverage note string for the API response

    """
    if source != "default" and coverage_area != "none":
        # We have a real source — note is informational only
        coverage_labels = {
            "us": "US National Weather Service (NWS)",
            "eu": "MeteoAlarm (EU/EEA)",
            "global": "Open-Meteo (limited global coverage)",
        }
        label = coverage_labels.get(coverage_area, "Unknown")
        return (
            f"Severe weather alerts sourced from {label}. "
            f"This source covers the requested location. "
            f"For additional local weather information, consult your "
            f"national meteorological service."
        )

    # No alert source available
    if coverage_area == "us":
        return (
            "Severe weather alert data is currently unavailable for this "
            "US location (NWS API unreachable). Check weather.gov for "
            "current alerts. Per NFPA 72 §10.6, assume normal conditions "
            "but verify with local NWS forecasts for power outage risk."
        )
    if coverage_area == "eu":
        return (
            "Severe weather alert data is currently unavailable for this "
            "European location (MeteoAlarm API unreachable). Check "
            "meteoalarm.org or your national meteorological service for "
            "current alerts. Per NFPA 72 §10.6 / EN 54-13, assume normal "
            "conditions but verify with local weather services."
        )
    if coverage_area == "global":
        return (
            "No dedicated severe weather alert source is available for "
            "this location. Open-Meteo provides limited weather data only. "
            "Please check your local meteorological service for active "
            "weather alerts. For fire protection engineering, apply "
            "conservative assumptions per NFPA 72 §10.6 (power outage risk) "
            "and §10.14 (temperature derating) until local alert data "
            "can be confirmed."
        )
    return (
        "No severe weather alert source covers this location. "
        "Please check your local meteorological service for active "
        "weather warnings. For fire protection engineering calculations, "
        "apply conservative assumptions per applicable standards "
        "(NFPA 72 §10.6, §10.14; NFPA 92 §6.4.2) until local "
        "alert data can be confirmed."
    )


@router.get("/severe-weather")
async def get_severe_weather(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude"),
):
    """Get active severe weather alerts for engineering calculations.

    Severe weather affects:
      - Power outage risk (battery/UPS sizing per NFPA 72 §10.6)
      - Smoke control wind loads (NFPA 92 §6.4.2)
      - Emergency notification design (NFPA 72 Chapter 24)
      - Evacuation planning (weather affects egress time)

    Sources (international dispatch):
      - US: National Weather Service (NWS) — continental US
      - EU/EEA: MeteoAlarm — EU member states + EEA/EFTA
      - Global: Open-Meteo (limited, WMO weather codes)
      - Default: No alerts (assume normal conditions)

    The `coverage_area` field indicates which source covers the location.
    The `coverage_note` field provides guidance when no alert source
    is available for the requested location.
    """
    sw_svc = get_severe_weather_service()
    data = await sw_svc.fetch_severe_weather(lat, lon)

    alerts_list = []
    for alert in data.active_alerts:
        alerts_list.append({
            "event": alert.event,
            "severity": alert.severity,
            "headline": alert.headline,
            "effective": alert.effective,
            "expires": alert.expires,
            "is_critical": alert.is_critical,
            "affects_fire_safety": alert.affects_fire_safety,
        })

    fire_safety_alerts = [
        a for a in data.active_alerts if a.affects_fire_safety
    ]

    # Determine coverage note based on coverage area
    coverage_area = getattr(data, "coverage_area", "none")
    coverage_note = _build_coverage_note(coverage_area, data.source)

    return {
        "success": True,
        "data": {
            "alert_count": data.alert_count,
            "active_alerts": alerts_list,
            "has_critical_alerts": data.has_critical_alerts,
            "has_power_outage_risk": data.has_power_outage_risk,
            "has_extreme_temp": data.has_extreme_temp,
            "fire_safety_alert_count": len(fire_safety_alerts),
            "source": data.source,
            "is_default": data.is_default,
            "coverage_area": coverage_area,
            "coverage_note": coverage_note,
            "engineering_notes": {
                "power": (
                    f"Power outage risk: {'YES — ensure secondary power per NFPA 72 §10.6' if data.has_power_outage_risk else 'No active power outage risk alerts'}."
                ),
                "battery": (
                    f"Extreme temperature: {'YES — apply temperature derating per NFPA 72 §10.14' if data.has_extreme_temp else 'No extreme temperature alerts'}."
                ),
                "evacuation": (
                    f"Critical alerts: {data.alert_count} active. "
                    f"{'Factor weather into egress time calculations' if data.has_critical_alerts else 'Normal evacuation planning applies'}."
                ),
            },
        },
    }


@router.get("/hazmat")
async def get_hazmat_data(
    material: str = Query(
        ..., min_length=2, max_length=200,
        description="Material name (e.g., 'methane', 'propane', 'hydrogen')"
    ),
):
    """Get hazardous material properties for engineering calculations.

    Material properties determine:
      - Zone 0/1/2 extent (LFL per IEC 60079-10-1 §6.3)
      - Temperature class (auto-ignition temp per IEC 60079-0)
      - Equipment group (gas group per IEC 60079-0 Table 1)
      - Flash point classification (NFPA 497 §4.3)

    Sources:
      - Primary: Internal database (12 common materials, IEC/NFPA data)
      - Secondary: PubChem API (broader coverage, limited properties)
      - Fallback: Conservative defaults (most restrictive classification)
    """
    hazmat_svc = get_hazmat_service()
    data = await hazmat_svc.get_material_data(material)

    return {
        "success": True,
        "data": {
            "name": data.name,
            "cas_number": data.cas_number,
            "lfl_vol_pct": data.lfl_vol_pct,
            "ufl_vol_pct": data.ufl_vol_pct,
            "flammable_range_vol_pct": data.flammable_range_vol_pct,
            "flash_point_c": data.flash_point_c,
            "auto_ignition_c": data.auto_ignition_c,
            "material_group": data.material_group.value,
            "temperature_class": data.temperature_class.value,
            "molecular_weight": data.molecular_weight,
            "vapor_density": data.vapor_density,
            "source": data.source,
            "is_default": data.is_default,
            "is_conservative": data.is_conservative,
            "engineering_notes": {
                "hac": (
                    f"LFL={data.lfl_vol_pct}% determines zone extent "
                    f"per IEC 60079-10-1 §6.3. "
                    f"{'CONSERVATIVE default — verify with actual material data' if data.is_conservative else 'Verified data from standards tables'}."
                ),
                "equipment": (
                    f"Material group {data.material_group.value}, "
                    f"Temperature class {data.temperature_class.value} "
                    f"per IEC 60079-0."
                ),
            },
        },
    }


@router.get("/hazmat/known")
async def list_known_materials():
    """List all materials in the internal hazardous materials database.

    The internal DB contains verified data from IEC 60079-10-1 Table B.1
    and NFPA 497 for the most common hazardous materials in fire alarm
    engineering.
    """
    hazmat_svc = get_hazmat_service()
    materials = hazmat_svc.list_known_materials()

    return {
        "success": True,
        "data": {
            "material_count": len(materials),
            "materials": materials,
            "source": "internal_db (IEC 60079-10-1, NFPA 497)",
        },
    }


# ── Comprehensive Context Endpoints ─────────────────────────────────────────

@router.get("/context")
async def get_full_environmental_context(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude"),
    is_indoor: bool = Query(True, description="Indoor or outdoor environment"),
):
    """Get complete environmental context for engineering calculations (Phase 1).

    Combines weather data, geocoding, and regulatory region in one call.
    This is the primary endpoint for the calculation engine.

    Returns all data needed to populate EnvironmentalContext:
      - Weather: temperature, wind, humidity
      - Location: lat/lon, country, display name
      - Regulatory: applicable codes, framework
    """
    weather_svc = get_weather_service()
    geo_svc = get_geocoding_service()
    region_svc = get_region_service()

    weather_task = weather_svc.fetch_weather(lat, lon)
    reverse_geo_task = geo_svc.reverse_geocode(lat, lon)

    # Wait for weather and geocoding
    weather, geo_result = await asyncio.gather(
        weather_task, reverse_geo_task, return_exceptions=True
    )

    # Handle weather errors
    if isinstance(weather, Exception):
        logger.warning("Weather fetch failed: %s", weather)
        weather = weather_svc._get_default(lat, lon)

    # Get region context
    country_code = ""
    region_context = None
    if isinstance(geo_result, GeocodingResult) and geo_result.country_code:
        country_code = geo_result.country_code
        region_context = await region_svc.get_region_context(country_code)
    else:
        region_context = RegionContext(
            country_code="",
            country_name="Unknown",
            regulatory_framework=RegulatoryFramework.STANDARD_IEC,
            electrical_code=ElectricalCode.IEC,
            source="default",
        )

    # Build comprehensive response
    env_data = await weather_svc.get_environmental_context(lat, lon, is_indoor)

    return {
        "success": True,
        "data": {
            "weather": {
                "temperature_c": weather.temperature_c,
                "wind_speed_m_s": weather.wind_speed_m_s,
                "relative_humidity_pct": weather.relative_humidity_pct,
                "air_density_kg_m3": round(weather.air_density_kg_m3, 4),
                "source": weather.source,
                "is_default": weather.is_default,
            },
            "location": {
                "latitude": lat,
                "longitude": lon,
                "display_name": geo_result.display_name if isinstance(geo_result, GeocodingResult) else "",
                "country_code": country_code,
            },
            "regulatory": {
                "framework": region_context.regulatory_framework.value,
                "electrical_code": region_context.electrical_code.value,
                "country_name": region_context.country_name,
                "is_gulf_state": region_context.is_gulf_state,
            },
            "engineering": {
                "ambient_temp_c": env_data["ambient_temp_c"],
                "outdoor_temp_c": env_data["outdoor_temp_c"],
                "wind_speed_m_s": env_data["wind_speed_m_s"],
                "relative_humidity_pct": env_data["relative_humidity_pct"],
                "is_indoor": env_data["is_indoor"],
            },
        },
    }


@router.get("/full-context")
async def get_full_phase2_context(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude"),
    is_indoor: bool = Query(True, description="Indoor or outdoor environment"),
    material: Optional[str] = Query(
        None, max_length=200,
        description="Optional hazardous material name for HAC data"
    ),
):
    """Get COMPLETE environmental context including all Phase 1 + Phase 2 data.

    This is the ULTIMATE endpoint for the calculation engine. It returns
    ALL environmental data needed for comprehensive engineering calculations:

    Phase 1:
      - Weather: temperature, wind, humidity (Open-Meteo)
      - Location: lat/lon, country (Nominatim)
      - Regulatory: applicable codes (REST Countries + internal map)

    Phase 2:
      - Elevation: terrain height, atmospheric pressure (Open Topo Data)
      - Air quality: AQI, PM2.5, PM10 (WAQI)
      - Severe weather: active NWS alerts (US only)
      - Hazmat: material properties (internal DB / PubChem)

    All data is fetched in parallel where possible.
    All services return conservative defaults on failure.
    """
    # Initialize all services
    weather_svc = get_weather_service()
    geo_svc = get_geocoding_service()
    region_svc = get_region_service()
    elev_svc = get_elevation_service()
    aq_svc = get_air_quality_service()
    sw_svc = get_severe_weather_service()

    # Phase 1: Weather + Geocoding (parallel)
    weather_task = asyncio.create_task(weather_svc.fetch_weather(lat, lon))
    geo_task = asyncio.create_task(geo_svc.reverse_geocode(lat, lon))

    # Phase 2: Elevation + Air Quality + Severe Weather (parallel)
    elev_task = asyncio.create_task(elev_svc.fetch_elevation(lat, lon))
    aq_task = asyncio.create_task(aq_svc.fetch_air_quality(lat, lon))
    sw_task = asyncio.create_task(sw_svc.fetch_severe_weather(lat, lon))

    # Wait for all Phase 1 + Phase 2 parallel tasks
    results = await asyncio.gather(
        weather_task, geo_task, elev_task, aq_task, sw_task,
        return_exceptions=True,
    )

    weather, geo_result, elevation, air_quality, severe_weather = results

    # Handle exceptions from parallel fetches
    if isinstance(weather, Exception):
        logger.warning("Weather fetch failed: %s", weather)
        weather = weather_svc._get_default(lat, lon)

    if isinstance(elevation, Exception):
        logger.warning("Elevation fetch failed: %s", elevation)
        elevation = elev_svc._get_default(lat, lon)

    if isinstance(air_quality, Exception):
        logger.warning("Air quality fetch failed: %s", air_quality)
        air_quality = aq_svc._get_default(lat, lon)

    if isinstance(severe_weather, Exception):
        logger.warning("Severe weather fetch failed: %s", severe_weather)
        severe_weather = sw_svc._get_default(lat, lon)

    # Get region context (depends on geocoding)
    country_code = ""
    region_context = None
    if isinstance(geo_result, GeocodingResult) and geo_result.country_code:
        country_code = geo_result.country_code
        region_context = await region_svc.get_region_context(country_code)
    else:
        region_context = RegionContext(
            country_code="",
            country_name="Unknown",
            regulatory_framework=RegulatoryFramework.STANDARD_IEC,
            electrical_code=ElectricalCode.IEC,
            source="default",
        )

    # Get hazmat data if requested (optional)
    hazmat_data = None
    if material:
        hazmat_svc = get_hazmat_service()
        hazmat_data = await hazmat_svc.get_material_data(material)

    # Get engineering context
    env_data = await weather_svc.get_environmental_context(lat, lon, is_indoor)

    # Build comprehensive response
    response = {
        "success": True,
        "data": {
            # Phase 1: Weather
            "weather": {
                "temperature_c": weather.temperature_c,
                "wind_speed_m_s": weather.wind_speed_m_s,
                "relative_humidity_pct": weather.relative_humidity_pct,
                "air_density_kg_m3": round(weather.air_density_kg_m3, 4),
                "source": weather.source,
                "is_default": weather.is_default,
            },
            # Phase 1: Location
            "location": {
                "latitude": lat,
                "longitude": lon,
                "display_name": geo_result.display_name if isinstance(geo_result, GeocodingResult) else "",
                "country_code": country_code,
            },
            # Phase 1: Regulatory
            "regulatory": {
                "framework": region_context.regulatory_framework.value,
                "electrical_code": region_context.electrical_code.value,
                "country_name": region_context.country_name,
                "is_gulf_state": region_context.is_gulf_state,
            },
            # Phase 2: Elevation
            "elevation": {
                "elevation_m": elevation.elevation_m,
                "atmospheric_pressure_pa": elevation.atmospheric_pressure_pa,
                "pressure_correction_factor": elevation.pressure_correction_factor,
                "source": elevation.source,
                "is_default": elevation.is_default,
            },
            # Phase 2: Air Quality
            "air_quality": {
                "aqi": air_quality.aqi,
                "aqi_level": air_quality.aqi_level,
                "pm25_ug_m3": air_quality.pm25_ug_m3,
                "pm10_ug_m3": air_quality.pm10_ug_m3,
                "is_unhealthy_baseline": air_quality.is_unhealthy_baseline,
                "source": air_quality.source,
                "is_default": air_quality.is_default,
            },
            # Phase 2: Severe Weather
            "severe_weather": {
                "alert_count": severe_weather.alert_count,
                "has_critical_alerts": severe_weather.has_critical_alerts,
                "has_power_outage_risk": severe_weather.has_power_outage_risk,
                "has_extreme_temp": severe_weather.has_extreme_temp,
                "source": severe_weather.source,
                "is_default": severe_weather.is_default,
                "coverage_area": getattr(severe_weather, "coverage_area", "none"),
                "coverage_note": _build_coverage_note(
                    getattr(severe_weather, "coverage_area", "none"),
                    severe_weather.source,
                ),
            },
            # Engineering context (computed from weather)
            "engineering": {
                "ambient_temp_c": env_data["ambient_temp_c"],
                "outdoor_temp_c": env_data["outdoor_temp_c"],
                "wind_speed_m_s": env_data["wind_speed_m_s"],
                "relative_humidity_pct": env_data["relative_humidity_pct"],
                "is_indoor": env_data["is_indoor"],
                "atmospheric_pressure_pa": elevation.atmospheric_pressure_pa,
                "pressure_correction_factor": elevation.pressure_correction_factor,
                "baseline_aqi": air_quality.aqi,
            },
        },
    }

    # Add hazmat data if requested
    if hazmat_data:
        response["data"]["hazmat"] = {
            "name": hazmat_data.name,
            "lfl_vol_pct": hazmat_data.lfl_vol_pct,
            "ufl_vol_pct": hazmat_data.ufl_vol_pct,
            "flash_point_c": hazmat_data.flash_point_c,
            "auto_ignition_c": hazmat_data.auto_ignition_c,
            "material_group": hazmat_data.material_group.value,
            "temperature_class": hazmat_data.temperature_class.value,
            "source": hazmat_data.source,
        }

    return response
