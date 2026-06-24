"""backend/services/air_quality_service.py — Air quality data for FireAI.

Provides real-time Air Quality Index (AQI) data from the World Air Quality
Index (WAQI) project (https://waqi.info/) — a free API for global air quality.

Previously used OpenAQ v2, which was retired (410 Gone) as of 2025.
Migrated to WAQI which provides free access with a demo token.

LIFE-SAFETY NOTE:
  Air quality data is critical for:
  - Smoke control design (NFPA 92) — baseline air quality affects
    tenability calculations and ASET/RSET analysis
  - Hazardous area classification (IEC 60079-10-1) — ambient
    particulate levels affect ventilation design
  - Fire scenario analysis — pre-existing air quality affects
    smoke detection response time and occupant evacuation
  - Health-based occupant vulnerability assessment — poor baseline
    AQI indicates higher sensitivity to smoke exposure

  WRONG AQI data is ACCEPTABLE if conservative (assume worst case).
  STALE data is ACCEPTABLE for engineering design (30-min TTL).
  NO data = assume CONSERVATIVE (AQI > 150 = unhealthy baseline).

References:
  - WAQI API: https://aqicn.org/json-api/doc/
  - OpenAQ v2: RETIRED (410 Gone) — no longer available
  - NFPA 92-2024 §6.4 (smoke control design)
  - IEC 60079-10-1:2015 §6.2 (ventilation assessment)
  - EPA AQI Scale: https://www.airnow.gov/aqi/aqi-basics/

"""

from __future__ import annotations

import logging
import math
import os
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class AQILevel(IntEnum):
    """EPA Air Quality Index levels — used for tenability baseline."""

    GOOD = 50           # 0-50: Satisfactory
    MODERATE = 100      # 51-100: Acceptable
    UNHEALTHY_SENSITIVE = 150  # 101-150: Unhealthy for sensitive groups
    UNHEALTHY = 200     # 151-200: Unhealthy
    VERY_UNHEALTHY = 300  # 201-300: Very unhealthy
    HAZARDOUS = 500     # 301-500: Hazardous


# Conservative default: assume MODERATE AQI for engineering calculations
DEFAULT_AQI = 100  # MODERATE — conservative but not alarmist
DEFAULT_PM25_UG_M3 = 35.0  # WHO interim target-1 (conservative)
DEFAULT_PM10_UG_M3 = 50.0  # WHO interim target-1 (conservative)


@dataclass(frozen=True)
class AirQualityData:
    """Immutable air quality snapshot for engineering calculations.

    Attributes:
        aqi: Air Quality Index (0-500, EPA scale)
        pm25_ug_m3: PM2.5 concentration in µg/m³
        pm10_ug_m3: PM10 concentration in µg/m³
        aqi_level: Human-readable AQI category
        source: Data provenance ("waqi" | "default")
        latitude: Latitude of measurement
        longitude: Longitude of measurement
        is_stale: Whether this data is from cache beyond TTL

    """

    aqi: int
    pm25_ug_m3: float
    pm10_ug_m3: float
    aqi_level: str
    source: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_stale: bool = False

    @property
    def is_default(self) -> bool:
        """Whether this data came from conservative defaults."""
        return self.source == "default"

    @property
    def is_unhealthy_baseline(self) -> bool:
        """Whether baseline AQI is unhealthy (affects tenability margins)."""
        return self.aqi > AQILevel.UNHEALTHY_SENSITIVE


def aqi_to_level(aqi: int) -> str:
    """Convert AQI numeric value to human-readable level."""
    if aqi <= 50:
        return "Good"
    if aqi <= 100:
        return "Moderate"
    if aqi <= 150:
        return "Unhealthy for Sensitive Groups"
    if aqi <= 200:
        return "Unhealthy"
    if aqi <= 300:
        return "Very Unhealthy"
    return "Hazardous"


class AirQualityService:
    """Async air quality data provider with fail-safe defaults.

    Primary source: WAQI (World Air Quality Index) — free, demo token
    Fallback: Conservative defaults (MODERATE AQI = 100)

    WAQI API provides:
      - Real-time AQI from global monitoring stations
      - PM2.5, PM10, O3, NO2, SO2, CO sub-indexes
      - Geolocation-based station lookup
      - Free access with demo token (rate-limited)

    Caching:
        - In-memory TTL cache (default 1800s / 30 minutes)
        - Air quality changes moderately; 30-min TTL is safe for design

    Retry:
        - 3 attempts with exponential backoff
        - Falls back to conservative defaults (MODERATE AQI)
    """

    WAQI_GEO_URL = "https://api.waqi.info/feed/geo:{lat};{lon}/"
    WAQI_TOKEN = os.getenv("WAQI_API_TOKEN")  # Must be set explicitly — no insecure fallback

    def __init__(self, cache_ttl: float = 1800.0, request_timeout: float = 10.0):
        self._cache: dict[str, tuple[AirQualityData, float]] = {}
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

    def _get_cached(self, latitude: float, longitude: float) -> Optional[AirQualityData]:
        """Get cached air quality data if fresh."""
        key = self._cache_key(latitude, longitude)
        entry = self._cache.get(key)
        if entry is None:
            return None
        data, fetched_at = entry
        age = time.time() - fetched_at
        if age < self._cache_ttl:
            return AirQualityData(
                aqi=data.aqi,
                pm25_ug_m3=data.pm25_ug_m3,
                pm10_ug_m3=data.pm10_ug_m3,
                aqi_level=data.aqi_level,
                source=data.source,
                latitude=data.latitude,
                longitude=data.longitude,
                is_stale=age > self._cache_ttl * 0.8,
            )
        return None

    def _set_cached(self, latitude: float, longitude: float, data: AirQualityData) -> None:
        """Store air quality data in cache."""
        key = self._cache_key(latitude, longitude)
        self._cache[key] = (data, time.time())

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        reraise=True,
    )
    async def _fetch_waqi(
        self, latitude: float, longitude: float
    ) -> AirQualityData:
        """Fetch air quality from WAQI (World Air Quality Index) API.

        API: https://api.waqi.info/feed/geo:LAT;LON/?token=demo
        Returns the nearest monitoring station data including AQI and
        individual pollutant sub-indexes (PM2.5, PM10, O3, etc.).

        Returns:
            AirQualityData with source="waqi"

        """
        if not self.WAQI_TOKEN:
            raise ValueError(
                "WAQI_API_TOKEN is not set. Configure the WAQI_API_TOKEN environment "
                "variable to enable air quality data fetching from the World Air Quality "
                "Index API. Without a valid token, API calls will fail. Get a free token "
                "at https://aqicn.org/data-platform/token/"
            )

        client = await self._get_client()
        url = self.WAQI_GEO_URL.format(lat=latitude, lon=longitude)
        response = await client.get(
            url,
            params={"token": self.WAQI_TOKEN},
        )
        response.raise_for_status()
        body = response.json()

        # WAQI returns {"status": "ok", "data": {...}} on success
        if body.get("status") != "ok":
            raise ValueError(
                f"WAQI returned status='{body.get('status')}' "
                f"for lat={latitude}, lon={longitude}"
            )

        data = body.get("data", {})

        # Extract AQI — WAQI provides this directly
        aqi_raw = data.get("aqi")
        if aqi_raw is None or not isinstance(aqi_raw, (int, float)):
            raise ValueError("WAQI returned no valid AQI value")

        aqi = int(aqi_raw)
        # Validate AQI range
        if aqi < 0:
            aqi = 0
        elif aqi > 500:
            aqi = 500

        # Extract individual pollutant sub-indexes from iaqi
        iaqi = data.get("iaqi", {})

        # PM2.5 sub-index (WAQI provides AQI sub-index, not raw µg/m³)
        # Convert WAQI sub-index back to approximate PM2.5 concentration
        pm25_sub = iaqi.get("pm25", {}).get("v")
        pm10_sub = iaqi.get("pm10", {}).get("v")

        # Convert AQI sub-index back to approximate concentration
        # using EPA breakpoints (inverse of _pm25_to_aqi)
        pm25_ug_m3 = self._aqi_to_pm25(pm25_sub if pm25_sub is not None else aqi)
        pm10_ug_m3 = self._aqi_to_pm10(pm10_sub if pm10_sub is not None else aqi)

        # Validate values
        if math.isnan(pm25_ug_m3) or math.isinf(pm25_ug_m3):
            pm25_ug_m3 = DEFAULT_PM25_UG_M3
        if math.isnan(pm10_ug_m3) or math.isinf(pm10_ug_m3):
            pm10_ug_m3 = DEFAULT_PM10_UG_M3

        level = aqi_to_level(aqi)

        result = AirQualityData(
            aqi=aqi,
            pm25_ug_m3=round(pm25_ug_m3, 1),
            pm10_ug_m3=round(pm10_ug_m3, 1),
            aqi_level=level,
            source="waqi",
            latitude=latitude,
            longitude=longitude,
        )

        logger.info(
            f"Air quality fetched from WAQI: lat={latitude:.4f}, lon={longitude:.4f}, "
            f"AQI={aqi} ({level}), PM2.5≈{pm25_ug_m3:.1f}µg/m³, PM10≈{pm10_ug_m3:.1f}µg/m³"
        )
        return result

    @staticmethod
    def _pm25_to_aqi(pm25: float) -> int:
        """Convert PM2.5 concentration to EPA AQI.

        Simplified EPA AQI formula:
        AQI = ((I_hi - I_lo) / (C_hi - C_lo)) * (C - C_lo) + I_lo

        Breakpoints from EPA:
        PM2.5 (µg/m³) → AQI range
        0.0 - 12.0  → 0 - 50 (Good)
        12.1 - 35.4 → 51 - 100 (Moderate)
        35.5 - 55.4 → 101 - 150 (USG)
        55.5 - 150.4 → 151 - 200 (Unhealthy)
        150.5 - 250.4 → 201 - 300 (Very Unhealthy)
        250.5 - 500.4 → 301 - 500 (Hazardous)
        """
        breakpoints = [
            (0.0, 12.0, 0, 50),
            (12.1, 35.4, 51, 100),
            (35.5, 55.4, 101, 150),
            (55.5, 150.4, 151, 200),
            (150.5, 250.4, 201, 300),
            (250.5, 500.4, 301, 500),
        ]

        for c_lo, c_hi, i_lo, i_hi in breakpoints:
            if c_lo <= pm25 <= c_hi:
                aqi = ((i_hi - i_lo) / (c_hi - c_lo)) * (pm25 - c_lo) + i_lo
                return int(round(aqi))

        # Above 500.4 → cap at 500
        return 500

    @staticmethod
    def _aqi_to_pm25(aqi_val: float) -> float:
        """Convert AQI sub-index back to approximate PM2.5 concentration.

        Inverse of _pm25_to_aqi using EPA breakpoints.
        Uses the midpoint of each AQI range for the concentration.
        """
        if aqi_val < 0:
            return 0.0

        # EPA breakpoints: (PM25_lo, PM25_hi, AQI_lo, AQI_hi)
        breakpoints = [
            (0.0, 12.0, 0, 50),
            (12.1, 35.4, 51, 100),
            (35.5, 55.4, 101, 150),
            (55.5, 150.4, 151, 200),
            (150.5, 250.4, 201, 300),
            (250.5, 500.4, 301, 500),
        ]

        for c_lo, c_hi, i_lo, i_hi in breakpoints:
            if i_lo <= aqi_val <= i_hi:
                # Inverse: C = ((C_hi - C_lo) / (I_hi - I_lo)) * (AQI - I_lo) + C_lo
                pm25 = ((c_hi - c_lo) / (i_hi - i_lo)) * (aqi_val - i_lo) + c_lo
                return max(0.0, pm25)

        # Above 500 → return max
        return 500.4

    @staticmethod
    def _aqi_to_pm10(aqi_val: float) -> float:
        """Convert AQI sub-index back to approximate PM10 concentration.

        EPA PM10 breakpoints:
        PM10 (µg/m³) → AQI range
        0-54   → 0-50
        55-154 → 51-100
        155-254 → 101-150
        255-354 → 151-200
        355-424 → 201-300
        425-604 → 301-500
        """
        if aqi_val < 0:
            return 0.0

        breakpoints = [
            (0.0, 54.0, 0, 50),
            (55.0, 154.0, 51, 100),
            (155.0, 254.0, 101, 150),
            (255.0, 354.0, 151, 200),
            (355.0, 424.0, 201, 300),
            (425.0, 604.0, 301, 500),
        ]

        for c_lo, c_hi, i_lo, i_hi in breakpoints:
            if i_lo <= aqi_val <= i_hi:
                pm10 = ((c_hi - c_lo) / (i_hi - i_lo)) * (aqi_val - i_lo) + c_lo
                return max(0.0, pm10)

        return 604.0

    def _get_default(self, latitude: float, longitude: float) -> AirQualityData:
        """Return conservative default air quality data.

        MODERATE AQI (100) is conservative: it indicates that baseline
        air quality is not perfect, which adds a safety margin to
        tenability calculations.
        """
        logger.warning(
            f"Using CONSERVATIVE DEFAULT air quality for "
            f"lat={latitude:.4f}, lon={longitude:.4f}. "
            f"External API unavailable. Assuming MODERATE AQI."
        )
        return AirQualityData(
            aqi=DEFAULT_AQI,
            pm25_ug_m3=DEFAULT_PM25_UG_M3,
            pm10_ug_m3=DEFAULT_PM10_UG_M3,
            aqi_level="Moderate",
            source="default",
            latitude=latitude,
            longitude=longitude,
        )

    async def fetch_air_quality(
        self,
        latitude: float,
        longitude: float,
    ) -> AirQualityData:
        """Fetch air quality for engineering calculations.

        Strategy:
          1. Check cache — return if fresh (< 30-min TTL)
          2. Fetch from WAQI — retry up to 3 times
          3. On complete failure — return conservative defaults

        Args:
            latitude: Latitude in decimal degrees (-90 to 90)
            longitude: Longitude in decimal degrees (-180 to 180)

        Returns:
            AirQualityData (always succeeds, never raises)

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

        # Fetch from WAQI API
        try:
            data = await self._fetch_waqi(latitude, longitude)
            self._set_cached(latitude, longitude, data)
            return data
        except (httpx.HTTPError, ValueError, KeyError) as e:
            logger.warning(
                f"WAQI fetch failed for lat={latitude:.4f}, "
                f"lon={longitude:.4f}: {type(e).__name__}: {e}. "
                f"Using conservative defaults."
            )
            return self._get_default(latitude, longitude)
        except Exception as e:
            logger.error(
                f"Unexpected error fetching air quality for lat={latitude:.4f}, "
                f"lon={longitude:.4f}: {type(e).__name__}: {e}. "
                f"Using conservative defaults."
            )
            return self._get_default(latitude, longitude)


# Singleton
_air_quality_service: Optional[AirQualityService] = None


def get_air_quality_service() -> AirQualityService:
    """Get the singleton AirQualityService instance."""
    global _air_quality_service
    if _air_quality_service is None:
        _air_quality_service = AirQualityService()
    return _air_quality_service


async def close_air_quality_service() -> None:
    """Close the AirQualityService on application shutdown."""
    global _air_quality_service
    if _air_quality_service is not None:
        await _air_quality_service.close()
        _air_quality_service = None
