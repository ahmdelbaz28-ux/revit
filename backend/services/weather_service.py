"""backend/services/weather_service.py — Real-time weather data for FireAI.

Provides ambient temperature, wind speed, and relative humidity from
Open-Meteo (https://open-meteo.com) — a free, no-auth, CORS-enabled API.

LIFE-SAFETY NOTE:
  Weather data feeds directly into engineering calculations:
  - Battery derating (voltage_drop.py) — temperature_c affects Ah capacity
  - Smoke control (stairwell_smoke_control.py) — wind speed for pressurization
  - Fire scenario (scenario_engine.py) — ambient temp for ASET/RSET
  - HAC classification (hac_classification_engine.py) — temp affects LFL

  WRONG weather data is BETTER than NO data (conservative defaults are safe).
  STALE data is ACCEPTABLE for engineering design (10-min TTL is sufficient).

References:
  - Open-Meteo API: https://open-meteo.com/en/docs
  - NFPA 72-2022 §10.14 (battery derating)
  - NFPA 92-2024 §6.4.2 (smoke control design)
  - IEC 60079-10-1:2015 Annex B (ambient temperature effect on LFL)

"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


# ── Conservative defaults per NFPA / engineering practice ──────────────────
# These are used when the API is unavailable or returns invalid data.
# Values are CONSERVATIVE (safer than optimistic).

DEFAULT_INDOOR_TEMP_C = 40.0       # Industrial indoor per IEC 60079-10-1
DEFAULT_OUTDOOR_TEMP_C = 20.0      # Standard conditions per ISO 2533
DEFAULT_WIND_SPEED_M_S = 0.5       # Stagnant indoor (conservative for zone extent)
DEFAULT_HUMIDITY_PCT = 50.0        # Mid-range (conservative for acoustic propagation)


@dataclass(frozen=True)
class WeatherData:
    """Immutable weather snapshot for engineering calculations.

    Attributes:
        temperature_c: Ambient temperature in Celsius
        wind_speed_m_s: Wind speed at 10m height in m/s
        relative_humidity_pct: Relative humidity in percent
        fetched_at: Unix timestamp when data was fetched
        source: Data provenance ("open-meteo" | "default")
        latitude: Latitude of weather observation
        longitude: Longitude of weather observation
        is_stale: Whether this data is from cache beyond TTL

    """

    temperature_c: float
    wind_speed_m_s: float
    relative_humidity_pct: float
    fetched_at: float
    source: str  # "open-meteo" | "default"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_stale: bool = False

    @property
    def temperature_k(self) -> float:
        """Temperature in Kelvin (for IEC Annex B calculations)."""
        return self.temperature_c + 273.15

    @property
    def air_density_kg_m3(self) -> float:
        """Air density at current conditions (ideal gas approximation).
        Used for smoke control and zone extent calculations.
        """
        # rho = P / (R * T) where P=101325 Pa, R=287.05 J/(kg*K)
        return 101325.0 / (287.05 * self.temperature_k)

    @property
    def is_default(self) -> bool:
        """Whether this data came from conservative defaults."""
        return self.source == "default"


class WeatherService:
    """Async weather data provider with TTL caching and fail-safe defaults.

    Uses Open-Meteo (free, no auth, CORS-enabled) as the primary source.
    Falls back to conservative defaults on any failure.

    Caching:
        - In-memory TTL cache (default 600s / 10 minutes)
        - Weather changes slowly; 10-min TTL is safe for engineering design
        - Cache key: f"{lat:.2f},{lon:.2f}" (0.01° ≈ 1.1 km resolution)

    Retry:
        - 3 attempts with exponential backoff (1s, 2s, 4s)
        - Only retries on network errors (httpx.HTTPError)
        - Does NOT retry on 4xx errors (bad request = our fault)

    Thread Safety:
        - Cache is a simple dict — safe for single-process FastAPI
        - For multi-worker deployment, use Redis-backed cache instead
    """

    def __init__(
        self,
        cache_ttl: float = 600.0,
        request_timeout: float = 10.0,
    ):
        self._cache: dict[str, tuple[WeatherData, float]] = {}
        self._cache_ttl = cache_ttl
        self._request_timeout = request_timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-initialize the HTTP client (connection pooling)."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._request_timeout),
                headers={"User-Agent": "FireAI-DigitalTwin/1.0"},
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client. Call on application shutdown."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _cache_key(self, latitude: float, longitude: float) -> str:
        """Generate cache key from coordinates (0.01° ≈ 1.1 km)."""
        return f"{latitude:.2f},{longitude:.2f}"

    def _get_cached(self, latitude: float, longitude: float) -> Optional[WeatherData]:
        """Get cached weather data if fresh (< TTL)."""
        key = self._cache_key(latitude, longitude)
        entry = self._cache.get(key)
        if entry is None:
            return None
        data, fetched_at = entry
        age = time.time() - fetched_at
        if age < self._cache_ttl:
            # Return cached data with stale flag if approaching TTL
            return WeatherData(
                temperature_c=data.temperature_c,
                wind_speed_m_s=data.wind_speed_m_s,
                relative_humidity_pct=data.relative_humidity_pct,
                fetched_at=data.fetched_at,
                source=data.source,
                latitude=data.latitude,
                longitude=data.longitude,
                is_stale=age > self._cache_ttl * 0.8,
            )
        return None

    def _set_cached(self, latitude: float, longitude: float, data: WeatherData) -> None:
        """Store weather data in cache."""
        key = self._cache_key(latitude, longitude)
        self._cache[key] = (data, time.time())

    @retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        reraise=True,
    )
    async def _fetch_open_meteo(
        self, latitude: float, longitude: float
    ) -> WeatherData:
        """Fetch current weather from Open-Meteo API.

        API: https://api.open-meteo.com/v1/forecast
        Parameters:
          - latitude, longitude: Location
          - current: temperature_2m, wind_speed_10m, relative_humidity_2m

        Returns:
            WeatherData with source="open-meteo"

        """
        client = await self._get_client()
        response = await client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": "temperature_2m,wind_speed_10m,relative_humidity_2m",
            },
        )
        response.raise_for_status()
        body = response.json()

        current = body.get("current", {})
        temperature_c = current.get("temperature_2m")
        wind_speed_m_s = current.get("wind_speed_10m")
        humidity_pct = current.get("relative_humidity_2m")

        # Validate all values are present and finite
        if (
            temperature_c is None
            or wind_speed_m_s is None
            or humidity_pct is None
            or math.isnan(temperature_c)
            or math.isnan(wind_speed_m_s)
            or math.isnan(humidity_pct)
            or math.isinf(temperature_c)
            or math.isinf(wind_speed_m_s)
            or math.isinf(humidity_pct)
        ):
            raise ValueError(f"Open-Meteo returned invalid data: {current}")

        weather = WeatherData(
            temperature_c=float(temperature_c),
            wind_speed_m_s=float(wind_speed_m_s),
            relative_humidity_pct=float(humidity_pct),
            fetched_at=time.time(),
            source="open-meteo",
            latitude=latitude,
            longitude=longitude,
        )

        logger.info(
            f"Weather fetched from Open-Meteo: "
            f"lat={latitude:.4f}, lon={longitude:.4f}, "
            f"T={weather.temperature_c:.1f}°C, "
            f"WS={weather.wind_speed_m_s:.1f}m/s, "
            f"RH={weather.relative_humidity_pct:.0f}%"
        )
        return weather

    def _get_default(self, latitude: float, longitude: float) -> WeatherData:
        """Return conservative default weather data.

        These defaults are SAFER than no data:
        - 40°C indoor temp (conservative for HAC/battery)
        - 0.5 m/s wind (stagnant = conservative for zone extent)
        - 50% humidity (mid-range for acoustic propagation)
        """
        logger.warning(
            f"Using CONSERVATIVE DEFAULT weather data for "
            f"lat={latitude:.4f}, lon={longitude:.4f}. "
            f"External API unavailable. Calculations proceed with safe defaults."
        )
        return WeatherData(
            temperature_c=DEFAULT_OUTDOOR_TEMP_C,
            wind_speed_m_s=DEFAULT_WIND_SPEED_M_S,
            relative_humidity_pct=DEFAULT_HUMIDITY_PCT,
            fetched_at=time.time(),
            source="default",
            latitude=latitude,
            longitude=longitude,
        )

    async def fetch_weather(
        self,
        latitude: float,
        longitude: float,
    ) -> WeatherData:
        """Fetch current weather for engineering calculations.

        Strategy:
          1. Check cache — return if fresh (< TTL)
          2. Fetch from Open-Meteo — retry up to 3 times
          3. On complete failure — return conservative defaults

        Args:
            latitude: Latitude in decimal degrees (-90 to 90)
            longitude: Longitude in decimal degrees (-180 to 180)

        Returns:
            WeatherData (always succeeds, never raises)

        """
        # Validate coordinates
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            logger.warning(
                f"Invalid coordinates: lat={latitude}, lon={longitude}. "
                f"Using defaults."
            )
            return self._get_default(latitude, longitude)

        # Check cache first
        cached = self._get_cached(latitude, longitude)
        if cached is not None:
            return cached

        # Fetch from API
        try:
            weather = await self._fetch_open_meteo(latitude, longitude)
            self._set_cached(latitude, longitude, weather)
            return weather
        except (httpx.HTTPError, ValueError, KeyError) as e:
            logger.warning(
                f"Open-Meteo fetch failed for lat={latitude:.4f}, "
                f"lon={longitude:.4f}: {type(e).__name__}: {e}. "
                f"Using conservative defaults."
            )
            return self._get_default(latitude, longitude)
        except Exception as e:
            # Catch-all: external API must NEVER crash the calculation engine
            logger.error(
                f"Unexpected error fetching weather for lat={latitude:.4f}, "
                f"lon={longitude:.4f}: {type(e).__name__}: {e}. "
                f"Using conservative defaults."
            )
            return self._get_default(latitude, longitude)

    async def get_environmental_context(
        self,
        latitude: float,
        longitude: float,
        is_indoor: bool = True,
    ):
        """Get EnvironmentalContext for core calculations.

        Bridges weather data → fireai.core.models_v21.EnvironmentalContext

        Args:
            latitude: Building latitude
            longitude: Building longitude
            is_indoor: Whether the calculation is for indoor environment

        Returns:
            dict with keys matching EnvironmentalContext fields

        """
        weather = await self.fetch_weather(latitude, longitude)

        if is_indoor:
            # Indoor: use industrial default temperature (40°C) for HAC,
            # but ambient weather for battery derating comparison
            temp_c = DEFAULT_INDOOR_TEMP_C
        else:
            # Outdoor: use actual weather temperature
            temp_c = weather.temperature_c

        return {
            "ambient_temp_c": temp_c,
            "wind_speed_m_s": weather.wind_speed_m_s,
            "relative_humidity_pct": weather.relative_humidity_pct,
            "weather_source": weather.source,
            "weather_fetched_at": weather.fetched_at,
            "outdoor_temp_c": weather.temperature_c,
            "is_indoor": is_indoor,
        }


# ── Singleton instance for application-wide use ────────────────────────────

_weather_service: Optional[WeatherService] = None


import threading

_weather_lock = threading.Lock()


def get_weather_service() -> WeatherService:
    """Get the singleton WeatherService instance.

    V65 FIX: Added thread-safe double-checked locking, matching the pattern
    used in database.py and qomn.py. Old code was not thread-safe — two
    concurrent startup requests could both see _weather_service is None and
    create separate instances, leaking the first instance's HTTP connections.
    """
    global _weather_service
    if _weather_service is None:
        with _weather_lock:
            if _weather_service is None:
                _weather_service = WeatherService()
    return _weather_service


async def close_weather_service() -> None:
    """Close the WeatherService on application shutdown."""
    global _weather_service
    if _weather_service is not None:
        await _weather_service.close()
        _weather_service = None
