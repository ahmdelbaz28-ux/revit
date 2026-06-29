"""
fireai/integration/ais_vessel_adapter.py.
==========================================
AIS Hub Vessel Tracking Adapter — Marine Fire-Safety Proximity Alarm.

PURPOSE:
  The Marine Module (SOLAS II-2, NFPA 302, IEC 60092-502) currently has
  no awareness of vessels operating near the protected site. This is a
  safety gap: a tanker carrying Class 3 flammable cargo (IMO tankers
  with ship_type 70-79) anchored 200 m from a fire-alarm-protected
  facility changes the fire-load calculation and may justify:
    - Activating additional fire divisions (SOLAS II-2/7)
    - Increasing detector density (NFPA 302 §6.4)
    - Pre-arming deluge systems (NFPA 302 §8.4)

  This adapter queries the AIS Hub real-time vessel feed and returns a
  typed `VesselProximityAssessment` that the marine workflow can use as
  an ADVISORY pre-check.

DATA SOURCE:
  AIS Hub — http://www.aishub.net/api
  Free API key required (register at https://www.aishub.net/).
  Free tier: 1 request per minute, returns all vessels within radius.

  Endpoint:
    GET http://data.aishub.net/ws.php?username=KEY&format=1&lat=..&lon=..&radius=..

  Response format (CSV-like JSON):
    [[metadata], [vessel1], [vessel2], ...]
    vessel = [MMSI, NAME, LAT, LON, SOG, COG, HEADING, NAVSTAT, ...,
              SHIPTYPE, ...]

SAFETY CONTRACT:
  Advisory ONLY. Does NOT auto-activate fire divisions or deluge
  systems. The returned `proximity_alert` flag is a HINT to operators.
  NFPA 302 §4.2 requires a human decision before any active suppression.

NFPA / SOLAS REFERENCES:
  - SOLAS II-2/7          — Fire division activation criteria
  - NFPA 302-2021 §6.4    — Detector density in hazardous-cargo proximity
  - NFPA 302-2021 §8.4    — Deluge system pre-arming
  - IMO Resolution A.1106 — AIS ship-type codes
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from fireai.integration.external_api_base import ExternalApiAdapter

logger = logging.getLogger(__name__)


# ===========================================================================
# Constants
# ===========================================================================

DEFAULT_BASE_URL = "http://data.aishub.net/ws.php"
DEFAULT_RADIUS_NM = 50  # nautical miles

# IMO ship-type codes — tankers and hazardous-cargo vessels.
# Source: IMO Resolution A.1106(29) Annex 5.
HAZARDOUS_SHIP_TYPES = frozenset({
    70, 71, 72, 73, 74, 75, 76, 77, 78, 79,  # Tankers (all)
    80, 81, 82, 83, 84, 85, 86, 87, 88, 89,  # Tankers (continued)
})

# Vessel fields per AIS Hub schema (1-based index in their docs).
# Indices are 0-based in the JSON array returned by the API.
FIELD_MMSI = 0
FIELD_NAME = 1
FIELD_LAT = 2
FIELD_LON = 3
FIELD_SOG = 4       # speed over ground (knots)
FIELD_COG = 5       # course over ground (degrees)
FIELD_HEADING = 6
FIELD_NAVSTAT = 7
FIELD_SHIPTYPE = 15 # may not exist on all vessels

# Proximity thresholds (nautical miles)
PROXIMITY_CRITICAL_NM = 1.0    # < 1 NM → CRITICAL
PROXIMITY_HIGH_NM = 5.0        # < 5 NM → HIGH
PROXIMITY_MEDIUM_NM = 25.0     # < 25 NM → MEDIUM


# ===========================================================================
# Result Types
# ===========================================================================


@dataclass(frozen=True)
class VesselSighting:
    """One vessel returned by AIS Hub."""
    mmsi: str
    name: str
    lat: float
    lon: float
    speed_knots: float
    course_deg: float
    heading_deg: float
    ship_type_code: int
    is_hazardous_cargo: bool
    distance_nm: float         # great-circle distance from query point


@dataclass(frozen=True)
class VesselProximityAssessment:
    """
    Advisory assessment of nearby vessel traffic.

    Attributes:
        vessels:            All vessels within the query radius.
        hazardous_vessels:  Subset carrying hazardous cargo (tankers).
        nearest_vessel:     Closest vessel, or None if no vessels.
        nearest_hazardous:  Closest hazardous-cargo vessel, or None.
        proximity_alert:    "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN"
        advisory_note:      Short human-readable advisory.
        nfpa_reference:     NFPA 302 / SOLAS section that motivates this check.
        data_source:        URL of the API call.
        coordinates:        (lat, lon) used for the query.
        radius_nm:          Search radius in nautical miles.
    """

    vessels: list[VesselSighting]
    hazardous_vessels: list[VesselSighting]
    nearest_vessel: VesselSighting | None
    nearest_hazardous: VesselSighting | None
    proximity_alert: str
    advisory_note: str
    nfpa_reference: str
    data_source: str
    coordinates: tuple[float, float]
    radius_nm: int


# ===========================================================================
# Math — Haversine in nautical miles
# ===========================================================================

import math

_EARTH_RADIUS_NM = 3440.065  # mean Earth radius in nautical miles


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in nautical miles."""
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(min(1.0, math.sqrt(a)))
    return _EARTH_RADIUS_NM * c


# ===========================================================================
# Adapter
# ===========================================================================


class AISVesselAdapter(ExternalApiAdapter):
    """
    Fetch real-time vessel positions from AIS Hub.

    Usage:
        adapter = AISVesselAdapter()
        result = await adapter.call(lat=25.0, lon=55.0)  # Dubai
        if result.ok and result.value.proximity_alert == "CRITICAL":
            # alert operator — do NOT auto-activate deluge
            ...
    """

    source_name = "ais_vessel"
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
        self._base_url = base_url or os.environ.get("AISHUB_URL", DEFAULT_BASE_URL)
        self._api_key = os.environ.get("AISHUB_API_KEY", "")

    async def _fetch(
        self,
        lat: float,
        lon: float,
        *,
        radius_nm: int = DEFAULT_RADIUS_NM,
    ) -> VesselProximityAssessment:
        if not (-90.0 <= lat <= 90.0):
            raise ValueError(f"latitude out of range: {lat}")
        if not (-180.0 <= lon <= 180.0):
            raise ValueError(f"longitude out of range: {lon}")
        if not (1 <= radius_nm <= 500):
            raise ValueError(f"radius_nm must be 1..500, got {radius_nm}")
        if not self._api_key:
            raise ValueError("AISHUB_API_KEY environment variable not set")

        params = {
            "username": self._api_key,
            "format": "1",   # JSON
            "lat": lat,
            "lon": lon,
            "radius": radius_nm,
        }
        client = await self._get_client()
        resp = await client.get(self._base_url, params=params)
        resp.raise_for_status()
        data = resp.json()

        # AIS Hub format: data[0] = metadata, data[1+] = vessel arrays
        if not isinstance(data, list) or len(data) < 1:
            raise ValueError(f"unexpected AIS Hub response shape: {type(data)}")
        if len(data) == 1:
            # metadata only, no vessels
            vessels_raw = []
        else:
            vessels_raw = data[1] if isinstance(data[1], list) else []

        vessels: list[VesselSighting] = []
        for v in vessels_raw:
            try:
                if not isinstance(v, list) or len(v) < 7:
                    continue
                ship_type = int(v[FIELD_SHIPTYPE]) if (
                    len(v) > FIELD_SHIPTYPE and v[FIELD_SHIPTYPE] is not None
                ) else 0
                distance = haversine_nm(
                    lat, lon,
                    float(v[FIELD_LAT]), float(v[FIELD_LON]),
                )
                vessels.append(VesselSighting(
                    mmsi=str(v[FIELD_MMSI]),
                    name=str(v[FIELD_NAME] or ""),
                    lat=float(v[FIELD_LAT]),
                    lon=float(v[FIELD_LON]),
                    speed_knots=float(v[FIELD_SOG] or 0.0),
                    course_deg=float(v[FIELD_COG] or 0.0),
                    heading_deg=float(v[FIELD_HEADING] or 0.0),
                    ship_type_code=ship_type,
                    is_hazardous_cargo=ship_type in HAZARDOUS_SHIP_TYPES,
                    distance_nm=round(distance, 2),
                ))
            except (KeyError, ValueError, TypeError, IndexError) as e:
                logger.debug("Skipping malformed AIS vessel: %s", e)
                continue

        # Sort by distance
        vessels.sort(key=lambda x: x.distance_nm)
        hazardous = [v for v in vessels if v.is_hazardous_cargo]

        nearest = vessels[0] if vessels else None
        nearest_haz = hazardous[0] if hazardous else None

        # Proximity alert priority — based on NEAREST HAZARDOUS vessel,
        # not just nearest vessel. A fishing boat 100m away is less
        # concerning than a tanker 2 NM away.
        if nearest_haz is None:
            alert = "LOW"
            note = (
                f"{len(vessels)} vessel(s) within {radius_nm} NM, none "
                f"carrying hazardous cargo. No marine fire-load advisory."
            )
        elif nearest_haz.distance_nm <= PROXIMITY_CRITICAL_NM:
            alert = "CRITICAL"
            note = (
                f"Hazardous-cargo vessel '{nearest_haz.name}' (MMSI "
                f"{nearest_haz.mmsi}, type {nearest_haz.ship_type_code}) "
                f"at {nearest_haz.distance_nm:.2f} NM. Consider activating "
                f"additional fire divisions per SOLAS II-2/7."
            )
        elif nearest_haz.distance_nm <= PROXIMITY_HIGH_NM:
            alert = "HIGH"
            note = (
                f"Hazardous-cargo vessel '{nearest_haz.name}' at "
                f"{nearest_haz.distance_nm:.2f} NM. Increase detector "
                f"density review per NFPA 302 §6.4."
            )
        elif nearest_haz.distance_nm <= PROXIMITY_MEDIUM_NM:
            alert = "MEDIUM"
            note = (
                f"Hazardous-cargo vessel '{nearest_haz.name}' at "
                f"{nearest_haz.distance_nm:.2f} NM. Monitor."
            )
        else:
            alert = "LOW"
            note = (
                f"Nearest hazardous-cargo vessel at "
                f"{nearest_haz.distance_nm:.2f} NM. No advisory."
            )

        return VesselProximityAssessment(
            vessels=vessels,
            hazardous_vessels=hazardous,
            nearest_vessel=nearest,
            nearest_hazardous=nearest_haz,
            proximity_alert=alert,
            advisory_note=note,
            nfpa_reference="SOLAS II-2/7 / NFPA 302 §6.4 / §8.4",
            data_source=self._base_url,
            coordinates=(lat, lon),
            radius_nm=radius_nm,
        )

    def _fallback(
        self,
        lat: float,
        lon: float,
        *,
        radius_nm: int = DEFAULT_RADIUS_NM,
    ) -> VesselProximityAssessment:
        """
        Conservative fallback when AIS Hub is unavailable.

        ROOT-CAUSE RATIONALE (Rule 17):
          The conservative choice is `proximity_alert=UNKNOWN`, NOT
          `LOW`. Claiming "LOW" without data would be a fabrication
          that could cause an operator to skip a marine fire-load
          review — and SOLAS II-2/7 explicitly requires that review
          when hazardous cargo may be nearby. `UNKNOWN` is honest.
        """
        return VesselProximityAssessment(
            vessels=[],
            hazardous_vessels=[],
            nearest_vessel=None,
            nearest_hazardous=None,
            proximity_alert="UNKNOWN",
            advisory_note=(
                "AIS Hub API unavailable. Vessel proximity could not "
                "be verified. If hazardous-cargo operations are known "
                "to be nearby, apply SOLAS II-2/7 review regardless."
            ),
            nfpa_reference="SOLAS II-2/7 / NFPA 302 §6.4 / §8.4",
            data_source=self._base_url,
            coordinates=(lat, lon),
            radius_nm=radius_nm,
        )
