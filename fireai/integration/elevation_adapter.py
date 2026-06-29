"""
fireai/integration/elevation_adapter.py.
=========================================
Open Topo Data Elevation Adapter — Hydraulic Pressure Calculations.

PURPOSE:
  Hydraulic calculations in NFPA 13-2022 §23 require the elevation
  difference between the water source (tank, city main) and the highest
  sprinkler to compute static pressure. Currently FireAI hardcodes
  elevation offsets in conduit_fill_analyzer.py and hydraulic_solver.py;
  this adapter provides accurate SRTM-30m elevation data so those
  calculations can use real elevations.

  Also used by:
    - Battery cabinet placement (NFPA 72 §10.6.10 — flood-zone avoidance)
    - Cable routing (V14 Bug 13 — AABB Rotation Trap considered terrain)
    - Water tank sizing (gravity-fed systems)

DATA SOURCE:
  Open Topo Data — https://www.opentopodata.org/
  Free, no API key required, SRTM-30m dataset (NASA).

  Endpoint:
    GET https://api.opentopodata.org/v1/srtm30m?locations=lat,lon

SAFETY CONTRACT:
  This adapter is used to populate elevation fields in hydraulic
  calculations. If the API fails, the caller MUST fall back to a
  user-provided elevation (not a hardcoded default — that would be a
  fabrication). The fallback returns NaN so the caller can detect
  missing data and refuse to produce a hydraulic calculation that
  could be wrong by 100 kPa (10 m head).

NFPA REFERENCES:
  - NFPA 13-2022 §23.4.2 — Elevation head in hydraulic calculations
  - NFPA 72-2022 §10.6.10 — Battery cabinet placement
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from fireai.integration.external_api_base import ExternalApiAdapter

logger = logging.getLogger(__name__)


DEFAULT_BASE_URL = "https://api.opentopodata.org/v1/srtm30m"


@dataclass(frozen=True)
class ElevationReading:
    """
    Elevation at a single point.

    Attributes:
        elevation_m:    Elevation in meters above sea level.
                        NaN if API failed and fallback was used.
        lat:            Latitude queried.
        lon:            Longitude queried.
        data_source:    URL of the API call.
        resolution_m:   Dataset resolution (SRTM-30m ≈ 30 m at equator).
    """

    elevation_m: float
    lat: float
    lon: float
    data_source: str
    resolution_m: int = 30


class ElevationAdapter(ExternalApiAdapter):
    """
    Fetch elevation from Open Topo Data (SRTM-30m).

    Usage:
        adapter = ElevationAdapter()
        result = await adapter.call(lat=30.04, lon=31.23)
        if result.ok:
            elevation = result.value.elevation_m
        else:
            # caller MUST prompt user for elevation — do NOT use 0.0
            elevation = None
    """

    source_name = "open_topo_data"
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
        self._base_url = base_url or os.environ.get(
            "OPEN_TOPO_DATA_URL", DEFAULT_BASE_URL
        )

    async def _fetch(self, lat: float, lon: float) -> ElevationReading:
        if not (-90.0 <= lat <= 90.0):
            raise ValueError(f"latitude out of range: {lat}")
        if not (-180.0 <= lon <= 180.0):
            raise ValueError(f"longitude out of range: {lon}")

        # SRTM coverage is -56° to +60° latitude. Outside this range
        # the API returns "null" results; we treat that as a parse
        # error so the caller falls back gracefully.
        if not (-56.0 <= lat <= 60.0):
            raise ValueError(
                f"latitude {lat} outside SRTM coverage (-56° to +60°)"
            )

        params = {"locations": f"{lat},{lon}"}
        client = await self._get_client()
        resp = await client.get(self._base_url, params=params)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        if not results:
            raise ValueError("Open Topo Data returned no results")
        elev = results[0].get("elevation")
        if elev is None:
            raise ValueError("Open Topo Data returned null elevation")

        return ElevationReading(
            elevation_m=float(elev),
            lat=lat,
            lon=lon,
            data_source=self._base_url,
        )

    def _fallback(self, lat: float, lon: float) -> ElevationReading:
        """
        Conservative fallback when Open Topo Data is unavailable.

        ROOT-CAUSE RATIONALE (Rule 17):
          The conservative choice is elevation=NaN, NOT elevation=0.0.
          Returning 0.0 would silently corrupt hydraulic calculations
          by up to 100 kPa per 10 m of head. NaN forces the caller to
          detect missing data and either prompt the user or refuse to
          compute — exactly what NFPA 13 §23.4.2 requires.
        """
        return ElevationReading(
            elevation_m=float("nan"),
            lat=lat,
            lon=lon,
            data_source=self._base_url,
        )
