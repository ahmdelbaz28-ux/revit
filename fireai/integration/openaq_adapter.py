"""
fireai/integration/openaq_adapter.py.
======================================
OpenAQ Air Quality Adapter — Government-Backed Pollution Data.

PURPOSE:
  Replaces the WAQI / AQICN adapters (which require a personal API
  token and are subject to commercial rate limits) with OpenAQ — a
  non-profit aggregator of GOVERNMENT air-quality data from 100+
  countries. OpenAQ data is the same data used by EPA, EEA, and WHO.

  Why this matters for FireAI:
    - Smoke detector calibration depends on ambient PM2.5 (NFPA 72
      §17.7 — see wildfire_smoke_adapter.py).
    - CO accumulation affects HVAC duct detector placement (NFPA 72
      §17.7.4.2).
    - The WildfireSmokeAdapter forecasts future PM2.5; this adapter
      reports CURRENT observations from official stations — a useful
      cross-check when the forecast API is unavailable.

DATA SOURCE:
  OpenAQ v3 API — https://docs.openaq.org/
  Free API key required (register at https://docs.openaq.org/api-key).
  Free tier: 1000 requests/hour per key.

  Endpoint:
    GET https://api.openaq.org/v3/measurements
    ?coordinates=lat,lon&radius=..&parameter=pm25,pm10,co,...

SAFETY CONTRACT:
  Advisory ONLY. Same contract as WildfireSmokeAdapter — never blocks
  detector signals, never modifies FACP state.

NFPA REFERENCES:
  - NFPA 72-2022 §17.7     — Detector ambient conditions
  - NFPA 72-2022 §17.7.4.2 — Duct detector placement (HVAC)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from fireai.integration.external_api_base import ExternalApiAdapter

logger = logging.getLogger(__name__)


# ===========================================================================
# Constants
# ===========================================================================

DEFAULT_BASE_URL = "https://api.openaq.org/v3/measurements"
DEFAULT_RADIUS_M = 25_000     # 25 km
DEFAULT_LIMIT = 100

# Same breakpoints as wildfire_smoke_adapter for consistency.
PM25_HIGH_THRESHOLD = 35.5   # EPA "Unhealthy for Sensitive Groups"


# ===========================================================================
# Result Types
# ===========================================================================


@dataclass(frozen=True)
class AirQualityReading:
    """One measurement from one OpenAQ station."""
    parameter: str           # "pm25", "pm10", "co", "no2", "so2", "o3"
    value: float             # µg/m³ (or ppm for CO — check `unit`)
    unit: str
    station_name: str
    station_id: str
    timestamp_utc: str       # ISO-8601
    coordinates: tuple[float, float]
    distance_m: int          # distance from query point


@dataclass(frozen=True)
class AirQualityAssessment:
    """
    Advisory assessment of current air quality near a site.

    Attributes:
        readings:          List of AirQualityReading (may be empty).
        current_pm25:      Most recent PM2.5 reading (µg/m³) or NaN.
        current_pm10:      Most recent PM10 reading (µg/m³) or NaN.
        current_co:        Most recent CO reading (µg/m³) or NaN.
        false_alarm_risk:  "LOW" | "MODERATE" | "HIGH" | "UNKNOWN"
        data_source:       URL of the API call.
        nfpa_reference:    NFPA 72 section that motivates this check.
        coordinates:       (lat, lon) used for the query.
        stations_reported: Number of unique stations that reported.
    """

    readings: list[AirQualityReading]
    current_pm25: float
    current_pm10: float
    current_co: float
    false_alarm_risk: str
    data_source: str
    nfpa_reference: str
    coordinates: tuple[float, float]
    stations_reported: int


# ===========================================================================
# Adapter
# ===========================================================================


class OpenAQAdapter(ExternalApiAdapter):
    """
    Fetch current air-quality observations from OpenAQ.

    Usage:
        adapter = OpenAQAdapter()
        result = await adapter.call(lat=30.04, lon=31.23)
        if result.ok:
            assessment = result.value
            if assessment.false_alarm_risk == "HIGH":
                # log advisory, do NOT silence alarms
                ...
    """

    source_name = "openaq"
    timeout_seconds = 12.0
    failure_threshold = 5
    cooldown_seconds = 300.0

    def __init__(
        self,
        base_url: str | None = None,
        *,
        failure_threshold: int | None = None,
        cooldown_seconds: float | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        super().__init__(
            failure_threshold=failure_threshold,
            cooldown_seconds=cooldown_seconds,
            timeout_seconds=timeout_seconds,
        )
        self._base_url = base_url or os.environ.get("OPENAQ_URL", DEFAULT_BASE_URL)
        # API key is mandatory for OpenAQ v3. Fail-safe: if missing,
        # adapter still constructs but every call returns fallback.
        self._api_key = os.environ.get("OPENAQ_API_KEY", "")

    async def _fetch(
        self,
        lat: float,
        lon: float,
        *,
        radius_m: int = DEFAULT_RADIUS_M,
        limit: int = DEFAULT_LIMIT,
    ) -> AirQualityAssessment:
        if not (-90.0 <= lat <= 90.0):
            raise ValueError(f"latitude out of range: {lat}")
        if not (-180.0 <= lon <= 180.0):
            raise ValueError(f"longitude out of range: {lon}")
        if not (1000 <= radius_m <= 200_000):
            raise ValueError(f"radius_m must be 1000..200000, got {radius_m}")
        if not self._api_key:
            # Treat missing API key as a soft failure — return fallback.
            # This is NOT a parse_error (which wouldn't trip the breaker)
            # nor a network error (which would). We use ValueError, which
            # base class catches as parse_error and does NOT trip breaker
            # (since the service may be fine, just our config).
            raise ValueError("OPENAQ_API_KEY environment variable not set")

        params = {
            "coordinates": f"{lat},{lon}",
            "radius": radius_m,
            "parameter": "pm25,pm10,co,no2,so2,o3",
            "limit": limit,
            "order_by": "datetime",
            "sort": "desc",
        }
        headers = {"X-API-Key": self._api_key}
        client = await self._get_client()
        resp = await client.get(self._base_url, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        # OpenAQ v3 returns {"results": [...]}
        results = data.get("results", data.get("data", []))
        if not isinstance(results, list):
            raise ValueError(f"unexpected OpenAQ response shape: {type(results)}")

        readings: list[AirQualityReading] = []
        for r in results:
            try:
                parameter = r.get("parameter") or r.get("parameterId")
                value = r.get("value")
                if value is None or parameter is None:
                    continue
                readings.append(AirQualityReading(
                    parameter=str(parameter),
                    value=float(value),
                    unit=r.get("unit", "µg/m³"),
                    station_name=str(r.get("location", "") or r.get("city", "") or ""),
                    station_id=str(r.get("locationId", "") or r.get("id", "")),
                    timestamp_utc=str(r.get("date", {}).get("utc", "") or ""),
                    coordinates=(
                        float(r.get("coordinates", {}).get("latitude", lat)),
                        float(r.get("coordinates", {}).get("longitude", lon)),
                    ),
                    distance_m=int(r.get("distanceMeters", 0) or 0),
                ))
            except (KeyError, ValueError, TypeError) as e:
                logger.debug("Skipping malformed OpenAQ reading: %s", e)
                continue

        # Extract most-recent value per parameter
        def latest(param: str) -> float:
            for r in readings:
                if r.parameter == param:
                    return r.value
            return float("nan")

        pm25 = latest("pm25")
        pm10 = latest("pm10")
        co = latest("co")

        if pm25 != pm25:  # NaN check
            risk = "UNKNOWN"
        elif pm25 >= PM25_HIGH_THRESHOLD:
            risk = "HIGH"
        elif pm25 >= 9.1:  # EPA "Moderate"
            risk = "MODERATE"
        else:
            risk = "LOW"

        # Count unique stations
        station_ids = {r.station_id for r in readings if r.station_id}

        return AirQualityAssessment(
            readings=readings,
            current_pm25=round(pm25, 2) if pm25 == pm25 else float("nan"),
            current_pm10=round(pm10, 2) if pm10 == pm10 else float("nan"),
            current_co=round(co, 2) if co == co else float("nan"),
            false_alarm_risk=risk,
            data_source=self._base_url,
            nfpa_reference="NFPA 72-2022 §17.7 / §17.7.4.2",
            coordinates=(lat, lon),
            stations_reported=len(station_ids),
        )

    def _fallback(
        self,
        lat: float,
        lon: float,
        *,
        radius_m: int = DEFAULT_RADIUS_M,
        limit: int = DEFAULT_LIMIT,
    ) -> AirQualityAssessment:
        """
        Conservative fallback when OpenAQ is unavailable.

        ROOT-CAUSE RATIONALE (Rule 17):
          The conservative choice is `risk=UNKNOWN`, NOT `risk=LOW`.
          OpenAQ returns NaN for missing values; we propagate that as
          UNKNOWN so the operator knows the data is missing.
        """
        return AirQualityAssessment(
            readings=[],
            current_pm25=float("nan"),
            current_pm10=float("nan"),
            current_co=float("nan"),
            false_alarm_risk="UNKNOWN",
            data_source=self._base_url,
            nfpa_reference="NFPA 72-2022 §17.7 / §17.7.4.2",
            coordinates=(lat, lon),
            stations_reported=0,
        )
