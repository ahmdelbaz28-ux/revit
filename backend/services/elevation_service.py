"""backend/services/elevation_service.py — Elevation data for FireAI.

Provides terrain elevation from Open Topo Data API (free, no auth).
Elevation is critical for:
  - Stack-effect calculations in stairwell pressurization (NFPA 92)
  - Atmospheric pressure correction for battery derating (IEC 60079)
  - Seismic zone classification (NEC 300.4(D))
  - Smoke control design pressure differentials

LIFE-SAFETY NOTE:
  Elevation affects atmospheric pressure, which directly impacts:
  - Battery capacity calculations (altitude derating per NFPA 72 §10.14)
  - Smoke control pressurization (NFPA 92 §6.4.2)
  - Hazardous area zone extent (IEC 60079-10-1 Annex B)

  Wrong elevation = wrong pressure = wrong calculations.
  Conservative default: 0m (sea level = standard atmospheric pressure = safest).

References:
  - Open Topo Data API: https://www.opentopodata.org/
  - NFPA 72-2022 §10.14 (battery derating)
  - NFPA 92-2024 §6.4.2 (smoke control design)
  - IEC 60079-10-1:2015 Annex B (atmospheric pressure correction)

"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Conservative defaults (sea level = standard atmospheric pressure)
DEFAULT_ELEVATION_M = 0.0  # Sea level
DEFAULT_ATM_PRESSURE_PA = 101325.0  # Standard atmosphere
GRAVITY_M_S2 = 9.80665  # Standard gravity
MOLAR_MASS_AIR = 0.0289644  # kg/mol (dry air)
UNIVERSAL_GAS_CONSTANT = 8.31447  # J/(mol·K)


@dataclass(frozen=True)
class ElevationData:
    """Immutable elevation snapshot for engineering calculations.

    Attributes:
        elevation_m: Terrain elevation above sea level in meters
        atmospheric_pressure_pa: Calculated atmospheric pressure in Pascals
        pressure_correction_factor: Ratio of actual to standard pressure
        source: Data provenance ("open-topo-data" | "default")
        latitude: Latitude of the elevation observation
        longitude: Longitude of the elevation observation

    """

    elevation_m: float
    atmospheric_pressure_pa: float
    pressure_correction_factor: float
    source: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    @property
    def is_default(self) -> bool:
        """Whether this data came from conservative defaults."""
        return self.source == "default"


def calculate_atmospheric_pressure(elevation_m: float, temperature_k: float = 288.15) -> float:
    """Calculate atmospheric pressure at a given elevation using the barometric formula.

    P = P0 * exp(-M*g*h / (R*T))

    where:
      P0 = 101325 Pa (standard atmospheric pressure at sea level)
      M = 0.0289644 kg/mol (molar mass of dry air)
      g = 9.80665 m/s² (standard gravity)
      h = elevation in meters
      R = 8.31447 J/(mol·K) (universal gas constant)
      T = 288.15 K (standard temperature)

    This is the ISO 2533:1975 barometric formula, also referenced in
    IEC 60079-10-1 for atmospheric pressure correction in HAC calculations.

    Args:
        elevation_m: Elevation above sea level in meters
        temperature_k: Temperature in Kelvin (default: 15°C = 288.15 K)

    Returns:
        Atmospheric pressure in Pascals

    """
    exponent = -(MOLAR_MASS_AIR * GRAVITY_M_S2 * elevation_m) / (
        UNIVERSAL_GAS_CONSTANT * temperature_k
    )
    return DEFAULT_ATM_PRESSURE_PA * math.exp(exponent)


class ElevationService:
    """Async elevation data provider using Open Topo Data API.

    API: https://api.opentopodata.org/v1/aster30m?locations=lat,lon

    Caching:
        - In-memory TTL cache (default 86400s / 24 hours)
        - Elevation doesn't change; 24-hour TTL is safe

    Retry:
        - 3 attempts with exponential backoff
        - Falls back to conservative defaults (sea level)
    """

    OPENTOPO_URL = "https://api.opentopodata.org/v1/aster30m"

    def __init__(self, cache_ttl: float = 86400.0, request_timeout: float = 10.0):
        self._cache: dict[str, tuple[ElevationData, float]] = {}
        self._cache_ttl = cache_ttl
        self._request_timeout = request_timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-initialize the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._request_timeout),
                headers={"User-Agent": "FireAI-DigitalTwin/1.0"},
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _cache_key(self, latitude: float, longitude: float) -> str:
        """Generate cache key from coordinates (0.01° ≈ 1.1 km)."""
        return f"{latitude:.2f},{longitude:.2f}"

    def _get_cached(self, latitude: float, longitude: float) -> Optional[ElevationData]:
        """Get cached elevation data if fresh."""
        key = self._cache_key(latitude, longitude)
        entry = self._cache.get(key)
        if entry is None:
            return None
        data, fetched_at = entry
        if time.time() - fetched_at < self._cache_ttl:
            return data
        return None

    def _set_cached(self, latitude: float, longitude: float, data: ElevationData) -> None:
        """Store elevation data in cache."""
        key = self._cache_key(latitude, longitude)
        self._cache[key] = (data, time.time())

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        reraise=True,
    )
    async def _fetch_open_topo_data(
        self, latitude: float, longitude: float
    ) -> ElevationData:
        """Fetch elevation from Open Topo Data API.

        API: https://api.opentopodata.org/v1/aster30m?locations=lat,lon
        Uses ASTER GDEM 30m resolution global DEM.

        Returns:
            ElevationData with source="open-topo-data"

        """
        client = await self._get_client()
        response = await client.get(
            self.OPENTOPO_URL,
            params={"locations": f"{latitude},{longitude}"},
        )
        response.raise_for_status()
        body = response.json()

        results = body.get("results", [])
        if not results:
            raise ValueError(f"Open Topo Data returned no results for lat={latitude}, lon={longitude}")

        elevation = results[0].get("elevation")
        if elevation is None:
            raise ValueError("Open Topo Data returned null elevation")

        elevation_m = float(elevation)
        atmo_pressure = calculate_atmospheric_pressure(elevation_m)
        correction_factor = atmo_pressure / DEFAULT_ATM_PRESSURE_PA

        data = ElevationData(
            elevation_m=elevation_m,
            atmospheric_pressure_pa=round(atmo_pressure, 2),
            pressure_correction_factor=round(correction_factor, 6),
            source="open-topo-data",
            latitude=latitude,
            longitude=longitude,
        )

        logger.info(
            f"Elevation fetched: lat={latitude:.4f}, lon={longitude:.4f}, "
            f"elev={elevation_m:.1f}m, P={atmo_pressure:.0f}Pa, "
            f"correction={correction_factor:.4f}"
        )
        return data

    def _get_default(self, latitude: float, longitude: float) -> ElevationData:
        """Return conservative default elevation data (sea level).

        Sea level = standard atmospheric pressure = safest for calculations.
        """
        logger.warning(
            f"Using CONSERVATIVE DEFAULT elevation (sea level) for "
            f"lat={latitude:.4f}, lon={longitude:.4f}. "
            f"External API unavailable. Calculations proceed with safe defaults."
        )
        return ElevationData(
            elevation_m=DEFAULT_ELEVATION_M,
            atmospheric_pressure_pa=DEFAULT_ATM_PRESSURE_PA,
            pressure_correction_factor=1.0,
            source="default",
            latitude=latitude,
            longitude=longitude,
        )

    async def fetch_elevation(
        self,
        latitude: float,
        longitude: float,
    ) -> ElevationData:
        """Fetch elevation for engineering calculations.

        Strategy:
          1. Check cache — return if fresh (< 24h TTL)
          2. Fetch from Open Topo Data — retry up to 3 times
          3. On complete failure — return conservative defaults (sea level)

        Args:
            latitude: Latitude in decimal degrees (-90 to 90)
            longitude: Longitude in decimal degrees (-180 to 180)

        Returns:
            ElevationData (always succeeds, never raises)

        """
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            logger.warning(
                f"Invalid coordinates: lat={latitude}, lon={longitude}. Using defaults."
            )
            return self._get_default(latitude, longitude)

        # Check cache
        cached = self._get_cached(latitude, longitude)
        if cached is not None:
            return cached

        # Fetch from API
        try:
            data = await self._fetch_open_topo_data(latitude, longitude)
            self._set_cached(latitude, longitude, data)
            return data
        except (httpx.HTTPError, ValueError, KeyError) as e:
            logger.warning(
                f"Open Topo Data fetch failed for lat={latitude:.4f}, "
                f"lon={longitude:.4f}: {type(e).__name__}: {e}. "
                f"Using conservative defaults."
            )
            return self._get_default(latitude, longitude)
        except Exception as e:
            logger.error(
                f"Unexpected error fetching elevation for lat={latitude:.4f}, "
                f"lon={longitude:.4f}: {type(e).__name__}: {e}. "
                f"Using conservative defaults."
            )
            return self._get_default(latitude, longitude)


# Singleton
_elevation_service: Optional[ElevationService] = None


def get_elevation_service() -> ElevationService:
    """Get the singleton ElevationService instance."""
    global _elevation_service
    if _elevation_service is None:
        _elevation_service = ElevationService()
    return _elevation_service


async def close_elevation_service() -> None:
    """Close the ElevationService on application shutdown."""
    global _elevation_service
    if _elevation_service is not None:
        await _elevation_service.close()
        _elevation_service = None
