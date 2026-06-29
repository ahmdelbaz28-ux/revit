"""
fireai/integration/earthquake_adapter.py.
=========================================
USGS Earthquake Hazards Adapter — Post-Earthquake Inspection Trigger.

PURPOSE:
  After an earthquake, NFPA 72 §14.4.3.3 requires heightened inspection
  of fire-alarm systems because:
    - Cables may have chafed against structural members (V14 Bug 13 —
      AABB Rotation Trap was found in exactly this scenario).
    - Seismic joints may have displaced beyond design tolerances
      (V19.1 Critique 3 — Seismic Joint Violation-Flagging).
    - Battery cabinets may have shifted, breaking DC return paths
      (V14 Bug 12 — DC Return Path Fallacy, life-safety critical).
    - Conduit fittings may have cracked, allowing water ingress.

  This adapter queries the USGS FDSN API for recent earthquakes within
  a configurable radius of a site, and returns a typed
  `EarthquakeAssessment` that the workflow service can use as an
  ADVISORY pre-check to schedule a post-quake inspection.

DATA SOURCE:
  USGS FDSN Web Service — https://earthquake.usgs.gov/fdsnws/event/1/query
  Free, no API key required, returns GeoJSON.

  Endpoint:
    GET https://earthquake.usgs.gov/fdsnws/event/1/query
    ?format=geojson&starttime=..&endtime=..
    &latitude=..&longitude=..&maxradiuskm=..&minmagnitude=..

SAFETY CONTRACT:
  This adapter is ADVISORY ONLY. It does NOT auto-trigger inspections
  and does NOT modify FACP state. The returned `inspection_recommended`
  flag is a HINT that an operator should review. The final decision to
  dispatch an inspection team is always made by a human.

NFPA REFERENCES:
  - NFPA 72-2022 §14.4.3.3 — Post-event inspection (earthquake)
  - NFPA 72-2022 §10.6.10  — Battery cabinet seismic anchorage
  - ASCE 7-22 §13.2        — Seismic qualification of equipment
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

# Default search window — USGS publishes preliminary data within minutes,
# but a 30-day window catches aftershocks that may affect a site that
# experienced a mainshock weeks ago.
DEFAULT_LOOKBACK_DAYS = 30

# Default radius — 200 km captures most damaging ground motion per
# USGS "Did You Feel It?" intensity decay curves.
DEFAULT_RADIUS_KM = 200

# Minimum magnitude to consider — below M4.0, ground motion at 200 km is
# typically below perceptibility threshold per USGS attestation curves.
DEFAULT_MIN_MAGNITUDE = 4.0

# Magnitude thresholds for inspection priority (USGS / FEMA P-58).
PRIORITY_MAGNITUDE_THRESHOLDS = {
    "CRITICAL": 6.0,   # M6.0+ — likely damage at moderate distance
    "HIGH":     5.0,   # M5.0+ — possible damage if shallow / close
    "MEDIUM":   4.0,   # M4.0+ — unlikely damage, but verify
}

DEFAULT_BASE_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"


# ===========================================================================
# Result Types
# ===========================================================================


@dataclass(frozen=True)
class EarthquakeEvent:
    """One earthquake returned by USGS."""
    magnitude: float
    depth_km: float
    place: str
    time_utc: str           # ISO-8601
    event_url: str          # USGS detail URL
    coordinates: tuple[float, float, float]  # (lon, lat, depth)
    tsunami_warning: bool


@dataclass(frozen=True)
class EarthquakeAssessment:
    """
    Advisory assessment of recent seismic activity near a site.

    Attributes:
        recent_events:    List of EarthquakeEvent in the lookback window.
        max_magnitude:    Largest magnitude observed (0.0 if no events).
        strongest_event:  The strongest event, or None if list is empty.
        inspection_recommended: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
                                 | "UNKNOWN" (when API failed).
        advisory_note:    Short human-readable advisory.
        nfpa_reference:   NFPA 72 section that motivates this check.
        data_source:      URL of the API call.
        coordinates:      (lat, lon) used for the query.
        lookback_days:    Lookback window in days.
        radius_km:        Search radius in km.
    """

    recent_events: list[EarthquakeEvent]
    max_magnitude: float
    strongest_event: EarthquakeEvent | None
    inspection_recommended: str
    advisory_note: str
    nfpa_reference: str
    data_source: str
    coordinates: tuple[float, float]
    lookback_days: int
    radius_km: int


def _classify_priority(max_mag: float) -> tuple[str, str]:
    """Return (priority, advisory_note) for a max magnitude."""
    if max_mag >= PRIORITY_MAGNITUDE_THRESHOLDS["CRITICAL"]:
        return (
            "CRITICAL",
            f"M{max_mag:.1f} earthquake detected. Dispatch post-quake "
            f"inspection IMMEDIATELY per NFPA 72 §14.4.3.3. Inspect: "
            f"cable chafing, seismic joints, battery anchorage, conduit.",
        )
    if max_mag >= PRIORITY_MAGNITUDE_THRESHOLDS["HIGH"]:
        return (
            "HIGH",
            f"M{max_mag:.1f} earthquake detected. Schedule post-quake "
            f"inspection within 24h per NFPA 72 §14.4.3.3.",
        )
    if max_mag >= PRIORITY_MAGNITUDE_THRESHOLDS["MEDIUM"]:
        return (
            "MEDIUM",
            f"M{max_mag:.1f} earthquake detected. Add inspection item "
            f"to next routine cycle.",
        )
    return (
        "LOW",
        f"No M4.0+ earthquakes in lookback window. No post-quake "
        f"inspection advised.",
    )


# ===========================================================================
# Adapter
# ===========================================================================


class EarthquakeAdapter(ExternalApiAdapter):
    """
    Fetch recent earthquakes from USGS FDSN.

    Usage:
        adapter = EarthquakeAdapter()
        result = await adapter.call(lat=30.04, lon=31.23)
        if result.ok and result.value.inspection_recommended == "CRITICAL":
            # dispatch inspection team — but only after human review
            ...
    """

    source_name = "usgs_earthquake"
    timeout_seconds = 15.0
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
        self._base_url = (
            base_url
            or os.environ.get("USGS_FDSN_URL", DEFAULT_BASE_URL)
        )

    async def _fetch(
        self,
        lat: float,
        lon: float,
        *,
        radius_km: int = DEFAULT_RADIUS_KM,
        min_magnitude: float = DEFAULT_MIN_MAGNITUDE,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> EarthquakeAssessment:
        if not (-90.0 <= lat <= 90.0):
            raise ValueError(f"latitude out of range: {lat}")
        if not (-180.0 <= lon <= 180.0):
            raise ValueError(f"longitude out of range: {lon}")
        if not (10 <= radius_km <= 2000):
            raise ValueError(f"radius_km must be 10..2000, got {radius_km}")
        if not (1 <= lookback_days <= 365):
            raise ValueError(f"lookback_days must be 1..365, got {lookback_days}")

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=lookback_days)
        params = {
            "format": "geojson",
            "starttime": start.strftime("%Y-%m-%d"),
            "endtime": end.strftime("%Y-%m-%d"),
            "latitude": lat,
            "longitude": lon,
            "maxradiuskm": radius_km,
            "minmagnitude": min_magnitude,
            "orderby": "magnitude",
        }
        client = await self._get_client()
        resp = await client.get(self._base_url, params=params)
        resp.raise_for_status()
        data = resp.json()

        features = data.get("features", [])
        events: list[EarthquakeEvent] = []
        for f in features:
            try:
                props = f["properties"]
                geom = f["geometry"]
                coords = geom["coordinates"]  # [lon, lat, depth_km]
                mag = props.get("mag")
                if mag is None:
                    continue
                events.append(EarthquakeEvent(
                    magnitude=float(mag),
                    depth_km=float(coords[2]) if len(coords) > 2 else 0.0,
                    place=props.get("place", "") or "",
                    time_utc=datetime.fromtimestamp(
                        props["time"] / 1000.0, tz=timezone.utc
                    ).isoformat(),
                    event_url=props.get("url", "") or "",
                    coordinates=(float(coords[0]), float(coords[1]),
                                 float(coords[2]) if len(coords) > 2 else 0.0),
                    tsunami_warning=bool(props.get("tsunami", 0)),
                ))
            except (KeyError, ValueError, TypeError) as e:
                # Skip malformed features — don't fail the whole call
                logger.debug("Skipping malformed USGS feature: %s", e)
                continue

        if not events:
            return EarthquakeAssessment(
                recent_events=[],
                max_magnitude=0.0,
                strongest_event=None,
                inspection_recommended="LOW",
                advisory_note=(
                    f"No M{min_magnitude}+ earthquakes in last "
                    f"{lookback_days}d within {radius_km}km."
                ),
                nfpa_reference="NFPA 72-2022 §14.4.3.3",
                data_source=self._base_url,
                coordinates=(lat, lon),
                lookback_days=lookback_days,
                radius_km=radius_km,
            )

        # Sort by magnitude descending
        events.sort(key=lambda e: e.magnitude, reverse=True)
        max_mag = events[0].magnitude
        priority, note = _classify_priority(max_mag)

        return EarthquakeAssessment(
            recent_events=events,
            max_magnitude=max_mag,
            strongest_event=events[0],
            inspection_recommended=priority,
            advisory_note=note,
            nfpa_reference="NFPA 72-2022 §14.4.3.3",
            data_source=self._base_url,
            coordinates=(lat, lon),
            lookback_days=lookback_days,
            radius_km=radius_km,
        )

    def _fallback(
        self,
        lat: float,
        lon: float,
        *,
        radius_km: int = DEFAULT_RADIUS_KM,
        min_magnitude: float = DEFAULT_MIN_MAGNITUDE,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> EarthquakeAssessment:
        """
        Conservative fallback when USGS API is unavailable.

        ROOT-CAUSE RATIONALE (Rule 17):
          The conservative choice is `inspection_recommended=UNKNOWN`,
          NOT `LOW`. Claiming "LOW" without data would be a fabrication
          that could cause an operator to skip a post-quake inspection
          — and NFPA 72 §14.4.3.3 explicitly requires inspection after
          ANY felt earthquake. `UNKNOWN` is honest.
        """
        return EarthquakeAssessment(
            recent_events=[],
            max_magnitude=0.0,
            strongest_event=None,
            inspection_recommended="UNKNOWN",
            advisory_note=(
                "USGS earthquake API unavailable. Seismic status could "
                "not be verified. If a felt earthquake has occurred, "
                "dispatch inspection per NFPA 72 §14.4.3.3 regardless."
            ),
            nfpa_reference="NFPA 72-2022 §14.4.3.3",
            data_source=self._base_url,
            coordinates=(lat, lon),
            lookback_days=lookback_days,
            radius_km=radius_km,
        )
