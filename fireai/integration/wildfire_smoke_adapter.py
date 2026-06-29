"""
fireai/integration/wildfire_smoke_adapter.py.
=============================================
Wildfire Smoke & Ambient PM2.5 Advisory Adapter.

PURPOSE:
  When ambient PM2.5 rises (from wildfire smoke, dust storms, or industrial
  emissions), ionization and photoelectric smoke detectors may produce
  false alarms or, worse, drift out of calibration and FAIL TO ALARM when
  a real fire starts. NFPA 72 §17.7 explicitly warns about this:

      "Smoke detectors shall not be installed in areas where ambient
       particulate concentrations could cause false alarms or prevent
       the detector from operating correctly."

  This adapter fetches PM2.5/PM10/CO/NO2 forecasts from Open-Meteo's
  air-quality API and exposes a typed `false_alarm_risk` classification
  that the workflow service can use as an ADVISORY pre-check before
  trusting a smoke detector reading.

DATA SOURCE:
  Open-Meteo Air Quality API — https://open-meteo.com/
  Free, no API key required, CORS-enabled, ~10k daily calls per IP.

  Endpoint:
    GET https://air-quality-api.open-meteo.com/v1/air-quality
    ?latitude=..&longitude=..&hourly=pm2_5,pm10,carbon_monoxide,...

SAFETY CONTRACT:
  This adapter is ADVISORY ONLY. It NEVER blocks detector signals and
  NEVER modifies the FACP state. The returned `false_alarm_risk` field
  is a HINT that operators / inspectors should consider when reviewing
  a smoke detector alarm — it does NOT auto-silence alarms.

NFPA REFERENCES:
  - NFPA 72-2022 §17.7   — Detector placement considerations (ambient smoke)
  - NFPA 72-2022 §14.4.3 — Inspection frequency may increase in adverse env
  - EPA AQI breakpoints   — PM2.5 thresholds (35.4 µg/m³ = "Unhealthy for SG")
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from fireai.integration.external_api_base import ApiResult, ExternalApiAdapter

logger = logging.getLogger(__name__)


# ===========================================================================
# Constants — EPA AQI breakpoints for PM2.5 (µg/m³, 24-hr avg)
# ===========================================================================

# Source: EPA 2024 PM2.5 AQI breakpoints (technical document).
# These are ADVISORY thresholds, not NFPA mandates.
PM25_BREAKPOINTS = {
    "GOOD":                 (0.0,   9.0),    # AQI 0-50
    "MODERATE":             (9.1,  35.4),    # AQI 51-100
    "UNHEALTHY_SG":         (35.5, 55.4),    # AQI 101-150 — sensitive groups
    "UNHEALTHY":            (55.5, 125.4),   # AQI 151-200
    "VERY_UNHEALTHY":       (125.5, 225.4),  # AQI 201-300
    "HAZARDOUS":            (225.5, float("inf")),
}

# Threshold at which we flag HIGH false-alarm risk (above EPA "Unhealthy for SG")
FALSE_ALARM_HIGH_THRESHOLD = 35.5

# URL is overridable for tests + on-prem air-quality proxies.
DEFAULT_BASE_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"


# ===========================================================================
# Result Types
# ===========================================================================


@dataclass(frozen=True)
class WildfireSmokeAssessment:
    """
    Advisory assessment of ambient smoke impact on smoke detectors.

    Attributes:
        peak_pm25_24h:      Max PM2.5 (µg/m³) forecast over next 24h.
        peak_pm10_24h:      Max PM10 (µg/m³) forecast over next 24h.
        avg_co_24h:         Avg carbon monoxide (µg/m³) over next 24h.
        aqi_category:       EPA AQI category string for peak PM2.5.
        false_alarm_risk:   "LOW" | "MODERATE" | "HIGH"
        advisory_note:      Short human-readable advisory.
        nfpa_reference:     NFPA 72 section that motivates this check.
        data_source:        URL of the API call.
        coordinates:        (lat, lon) used for the query.
    """

    peak_pm25_24h: float
    peak_pm10_24h: float
    avg_co_24h: float
    aqi_category: str
    false_alarm_risk: str
    advisory_note: str
    nfpa_reference: str
    data_source: str
    coordinates: tuple[float, float]


def _classify_pm25(pm25: float) -> str:
    """Return EPA AQI category for a 24h PM2.5 average."""
    for cat, (lo, hi) in PM25_BREAKPOINTS.items():
        if lo <= pm25 <= hi:
            return cat
    return "UNKNOWN"


# ===========================================================================
# Adapter
# ===========================================================================


class WildfireSmokeAdapter(ExternalApiAdapter):
    """
    Fetch PM2.5 / PM10 / CO / NO2 forecasts from Open-Meteo Air Quality.

    Usage:
        adapter = WildfireSmokeAdapter()
        result = await adapter.call(lat=30.04, lon=31.23)
        if result.ok:
            assessment = result.value  # WildfireSmokeAssessment
            if assessment.false_alarm_risk == "HIGH":
                # log advisory, do NOT silence alarms
                logger.warning("High ambient PM2.5 may affect smoke detectors")
        else:
            # API failed — proceed with no advisory (fail-safe)
            ...
    """

    source_name = "wildfire_smoke"
    timeout_seconds = 10.0
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
        # Override base URL is mostly for tests; can also be set via env var
        # for on-prem air-quality proxies.
        self._base_url = (
            base_url
            or os.environ.get("OPEN_METEO_AIR_QUALITY_URL", DEFAULT_BASE_URL)
        )

    async def _fetch(self, lat: float, lon: float, *, forecast_hours: int = 24) -> WildfireSmokeAssessment:
        """
        Fetch air-quality forecast for the next `forecast_hours` hours.

        Raises:
            httpx.* — propagated to base class for circuit-breaker accounting.
            KeyError/ValueError — propagated for parse-error accounting.
        """
        if not (-90.0 <= lat <= 90.0):
            raise ValueError(f"latitude out of range: {lat}")
        if not (-180.0 <= lon <= 180.0):
            raise ValueError(f"longitude out of range: {lon}")
        if not (1 <= forecast_hours <= 168):
            raise ValueError(f"forecast_hours must be 1..168, got {forecast_hours}")

        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": "pm2_5,pm10,carbon_monoxide,nitrogen_dioxide",
            "timezone": "auto",
            "forecast_days": max(1, (forecast_hours + 23) // 24),
        }
        client = await self._get_client()
        resp = await client.get(self._base_url, params=params)
        resp.raise_for_status()
        data = resp.json()

        # Parse — fail loudly on missing keys (KeyError → parse_error)
        hourly = data["hourly"]
        pm25_series = hourly["pm2_5"][:forecast_hours]
        pm10_series = hourly["pm10"][:forecast_hours]
        co_series = hourly["carbon_monoxide"][:forecast_hours]
        # nitrogen_dioxide is queried but not currently surfaced in the
        # assessment — keep it for future AQI composite calculations.

        # Filter None values (API may return null for some hours)
        pm25_valid = [v for v in pm25_series if v is not None]
        pm10_valid = [v for v in pm10_series if v is not None]
        co_valid = [v for v in co_series if v is not None]

        if not pm25_valid:
            raise ValueError("API returned no valid PM2.5 readings")

        peak_pm25 = max(pm25_valid)
        peak_pm10 = max(pm10_valid) if pm10_valid else 0.0
        avg_co = sum(co_valid) / len(co_valid) if co_valid else 0.0

        aqi_cat = _classify_pm25(peak_pm25)
        if peak_pm25 >= FALSE_ALARM_HIGH_THRESHOLD:
            risk = "HIGH"
            note = (
                f"Ambient PM2.5 {peak_pm25:.1f} µg/m³ exceeds EPA 'Unhealthy for "
                f"Sensitive Groups' threshold. Smoke detector drift / false "
                f"alarms possible. Schedule inspection per NFPA 72 §14.4.3."
            )
        elif peak_pm25 >= PM25_BREAKPOINTS["MODERATE"][0]:
            risk = "MODERATE"
            note = (
                f"Ambient PM2.5 {peak_pm25:.1f} µg/m³ is moderate. Monitor "
                f"smoke detector calibration."
            )
        else:
            risk = "LOW"
            note = (
                f"Ambient PM2.5 {peak_pm25:.1f} µg/m³ is within normal range. "
                f"No smoke-detector advisory."
            )

        return WildfireSmokeAssessment(
            peak_pm25_24h=round(peak_pm25, 2),
            peak_pm10_24h=round(peak_pm10, 2),
            avg_co_24h=round(avg_co, 2),
            aqi_category=aqi_cat,
            false_alarm_risk=risk,
            advisory_note=note,
            nfpa_reference="NFPA 72-2022 §17.7 / §14.4.3",
            data_source=self._base_url,
            coordinates=(lat, lon),
        )

    def _fallback(self, lat: float, lon: float, *, forecast_hours: int = 24) -> WildfireSmokeAssessment:
        """
        Conservative fallback when the API is unavailable.

        ROOT-CAUSE RATIONALE (Rule 17):
          The conservative choice is `risk=UNKNOWN`, NOT `risk=LOW`.
          Claiming "LOW" without data would be a fabrication that could
          cause an operator to skip an inspection. `UNKNOWN` is honest
          and forces the operator to rely on the physical detector
          signal — which is the primary protection anyway.
        """
        return WildfireSmokeAssessment(
            peak_pm25_24h=float("nan"),
            peak_pm10_24h=float("nan"),
            avg_co_24h=float("nan"),
            aqi_category="UNKNOWN",
            false_alarm_risk="UNKNOWN",
            advisory_note=(
                "Air-quality API unavailable. Smoke detector advisory "
                "could not be computed. Rely on physical detector signal."
            ),
            nfpa_reference="NFPA 72-2022 §17.7 / §14.4.3",
            data_source=self._base_url,
            coordinates=(lat, lon),
        )
