"""backend/services/geocoding_service.py — Geocoding service for FireAI.

Provides forward geocoding (address → lat/lon) using Nominatim
(OpenStreetMap) — a free, no-auth API.

LIFE-SAFETY NOTE:
  Building location determines:
  1. Weather data for smoke control design (NFPA 92)
  2. Jurisdiction for code selection (NFPA 72, IEC 60079, local codes)
  3. Elevation for stack-effect calculations (atmospheric pressure)
  4. Seismic zone for cable routing (NEC 300.4(D))

  Wrong location data = wrong environmental inputs = wrong calculations.
  Conservative: If geocoding fails, require manual coordinate entry.

References:
  - Nominatim API: https://nominatim.org/release-docs/latest/api/Search/
  - Usage policy: Max 1 request/second, User-Agent required

"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeocodingResult:
    """Immutable geocoding result for engineering use.

    Attributes:
        latitude: Latitude in decimal degrees
        longitude: Longitude in decimal degrees
        display_name: Human-readable address
        country_code: ISO 3166-1 alpha-2 country code (e.g., "EG", "US", "SA")
        source: Data provenance ("nominatim" | "manual" | "default")

    """

    latitude: float
    longitude: float
    display_name: str = ""
    country_code: str = ""
    source: str = "nominatim"

    @property
    def is_valid(self) -> bool:
        """Check if coordinates are within valid range."""
        return -90 <= self.latitude <= 90 and -180 <= self.longitude <= 180


class GeocodingService:
    """Async geocoding service using Nominatim (OpenStreetMap).

    Rate Limiting:
        Nominatim requires max 1 request/second. This service enforces
        a minimum interval of 1.1 seconds between requests.

    Caching:
        - In-memory cache with 24-hour TTL (addresses don't change)
        - Cache key: lowercase address string
    """

    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

    def __init__(self, cache_ttl: float = 86400.0):
        self._cache: dict[str, tuple[GeocodingResult, float]] = {}
        self._cache_ttl = cache_ttl
        self._last_request_time: float = 0.0
        self._min_interval: float = 1.1  # Nominatim rate limit
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-initialize the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0),
                headers={"User-Agent": "FireAI-DigitalTwin/1.0"},
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _cache_key(self, address: str) -> str:
        """Normalize address for caching."""
        return address.strip().lower()

    def _get_cached(self, address: str) -> Optional[GeocodingResult]:
        """Get cached result if fresh."""
        key = self._cache_key(address)
        entry = self._cache.get(key)
        if entry is None:
            return None
        result, fetched_at = entry
        if time.time() - fetched_at < self._cache_ttl:
            return result
        return None

    def _set_cached(self, address: str, result: GeocodingResult) -> None:
        """Store result in cache."""
        key = self._cache_key(address)
        self._cache[key] = (result, time.time())

    async def _enforce_rate_limit(self) -> None:
        """Enforce Nominatim's 1 request/second rate limit."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            import asyncio
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(min=1, max=5),
        reraise=True,
    )
    async def _fetch_nominatim(self, address: str) -> GeocodingResult:
        """Fetch geocoding from Nominatim."""
        await self._enforce_rate_limit()
        client = await self._get_client()
        response = await client.get(
            self.NOMINATIM_URL,
            params={
                "q": address,
                "format": "json",
                "limit": 1,
                "addressdetails": 1,
            },
        )
        response.raise_for_status()
        results = response.json()

        if not results:
            raise ValueError(f"Nominatim returned no results for: {address}")

        first = results[0]
        lat = float(first["lat"])
        lon = float(first["lon"])
        display_name = first.get("display_name", "")
        address_details = first.get("address", {})
        country_code = address_details.get("country_code", "").upper()

        result = GeocodingResult(
            latitude=lat,
            longitude=lon,
            display_name=display_name,
            country_code=country_code,
            source="nominatim",
        )

        logger.info(
            f"Geocoding: '{address}' → lat={lat:.6f}, lon={lon:.6f}, "
            f"country={country_code}"
        )
        return result

    async def geocode(self, address: str) -> Optional[GeocodingResult]:
        """Geocode an address to coordinates.

        Strategy:
          1. Check cache
          2. Fetch from Nominatim (with rate limiting)
          3. Return None on failure (caller must handle)

        Args:
            address: Human-readable address (e.g., "Cairo, Egypt")

        Returns:
            GeocodingResult or None if geocoding fails

        """
        if not address or not address.strip():
            return None

        # Check cache
        cached = self._get_cached(address)
        if cached is not None:
            return cached

        # Fetch from API
        try:
            result = await self._fetch_nominatim(address)
            self._set_cached(address, result)
            return result
        except (httpx.HTTPError, ValueError, KeyError) as e:
            logger.warning(
                f"Geocoding failed for '{address}': "
                f"{type(e).__name__}: {e}"
            )
            return None
        except Exception as e:
            logger.error(
                f"Unexpected geocoding error for '{address}': "
                f"{type(e).__name__}: {e}"
            )
            return None

    async def reverse_geocode(
        self, latitude: float, longitude: float
    ) -> Optional[GeocodingResult]:
        """Reverse geocode coordinates to address.

        Args:
            latitude: Latitude in decimal degrees
            longitude: Longitude in decimal degrees

        Returns:
            GeocodingResult or None if reverse geocoding fails

        """
        await self._enforce_rate_limit()
        client = await self._get_client()
        try:
            response = await client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={
                    "lat": latitude,
                    "lon": longitude,
                    "format": "json",
                    "addressdetails": 1,
                },
            )
            response.raise_for_status()
            data = response.json()
            address_details = data.get("address", {})
            country_code = address_details.get("country_code", "").upper()
            display_name = data.get("display_name", "")

            return GeocodingResult(
                latitude=latitude,
                longitude=longitude,
                display_name=display_name,
                country_code=country_code,
                source="nominatim-reverse",
            )
        except Exception as e:
            logger.warning(
                f"Reverse geocoding failed for lat={latitude}, lon={longitude}: "
                f"{type(e).__name__}: {e}"
            )
            return None


# ── Singleton ──────────────────────────────────────────────────────────────

_geocoding_service: Optional[GeocodingService] = None


def get_geocoding_service() -> GeocodingService:
    """Get the singleton GeocodingService instance."""
    global _geocoding_service
    if _geocoding_service is None:
        _geocoding_service = GeocodingService()
    return _geocoding_service


async def close_geocoding_service() -> None:
    """Close the GeocodingService on application shutdown."""
    global _geocoding_service
    if _geocoding_service is not None:
        await _geocoding_service.close()
        _geocoding_service = None
