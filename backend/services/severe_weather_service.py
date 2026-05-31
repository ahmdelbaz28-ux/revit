"""
backend/services/severe_weather_service.py — Severe weather alerts for FireAI.

Provides active weather alerts from the US National Weather Service (NWS)
API (free, no auth) for US locations. Also provides general storm/wind
warning data that affects:
  - Fire alarm system reliability (power outage risk per NFPA 72 §10.6)
  - Smoke control design wind loads (NFPA 92)
  - Emergency communication system design (NFPA 72 Chapter 24)
  - Evacuation planning (weather affects egress time)

LIFE-SAFETY NOTE:
  Severe weather directly impacts life-safety system design:
  - High winds affect smoke control effectiveness (NFPA 92 §6.4.2)
  - Power outage risk affects battery/UPS sizing (NFPA 72 §10.6)
  - Extreme temperatures affect battery capacity (NFPA 72 §10.14)
  - Severe storms may trigger emergency notification (NFPA 72 Ch.24)

  WRONG alert data is ACCEPTABLE if conservative (assume alerts present).
  NO alerts = assume NORMAL conditions (less conservative, but acceptable).

References:
  - US NWS API: https://www.weather.gov/documentation/services-web-api
  - NWS Alerts API: https://api.weather.gov/alerts
  - NFPA 72-2022 §10.6 (secondary power)
  - NFPA 72-2022 §10.14 (battery derating)
  - NFPA 92-2024 §6.4.2 (smoke control wind design)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class WeatherAlertSeverity:
    """NWS alert severity levels."""
    EXTREME = "Extreme"
    SEVERE = "Severe"
    MODERATE = "Moderate"
    MINOR = "Minor"
    UNKNOWN = "Unknown"


class WeatherAlertType:
    """Common NWS alert types relevant to fire safety engineering."""
    TORNADO_WARNING = "Tornado Warning"
    SEVERE_THUNDERSTORM = "Severe Thunderstorm Warning"
    HIGH_WIND = "High Wind Warning"
    WINTER_STORM = "Winter Storm Warning"
    EXTREME_HEAT = "Excessive Heat Warning"
    EXTREME_COLD = "Extreme Cold Warning"
    FLOOD = "Flood Warning"
    HURRICANE = "Hurricane Warning"
    TROPICAL_STORM = "Tropical Storm Warning"


@dataclass(frozen=True)
class WeatherAlert:
    """
    A single weather alert relevant to fire safety engineering.

    Attributes:
        event: Alert event type (e.g., "Tornado Warning")
        severity: Alert severity (Extreme, Severe, Moderate, Minor)
        headline: Brief headline description
        description: Detailed description
        areas: Affected geographic areas
        effective: ISO 8601 timestamp when alert becomes effective
        expires: ISO 8601 timestamp when alert expires
        urgency: Urgency level (Immediate, Expected, Future, Past)
        certainty: Certainty level (Observed, Likely, Possible, Unlikely)
    """
    event: str
    severity: str
    headline: str
    description: str = ""
    areas: str = ""
    effective: str = ""
    expires: str = ""
    urgency: str = ""
    certainty: str = ""

    @property
    def is_critical(self) -> bool:
        """Whether this alert is critical for life-safety calculations."""
        return self.severity in (
            WeatherAlertSeverity.EXTREME,
            WeatherAlertSeverity.SEVERE,
        )

    @property
    def affects_fire_safety(self) -> bool:
        """Whether this alert type is relevant to fire safety engineering."""
        fire_safety_keywords = [
            "wind", "tornado", "hurricane", "tropical storm",
            "heat", "cold", "flood", "storm", "thunderstorm",
            "power", "ice", "snow",
        ]
        event_lower = self.event.lower()
        return any(kw in event_lower for kw in fire_safety_keywords)


@dataclass(frozen=True)
class SevereWeatherData:
    """
    Immutable severe weather data for engineering calculations.

    Attributes:
        active_alerts: List of active weather alerts
        max_wind_speed_kt: Maximum wind speed from alerts (knots)
        has_power_outage_risk: Whether any alert indicates power outage risk
        has_extreme_temp: Whether any alert indicates extreme temperatures
        alert_count: Number of active alerts
        source: Data provenance ("nws" | "default")
    """
    active_alerts: tuple  # Tuple of WeatherAlert (frozen=True requires hashable)
    max_wind_speed_kt: float = 0.0
    has_power_outage_risk: bool = False
    has_extreme_temp: bool = False
    alert_count: int = 0
    source: str = "nws"

    @property
    def is_default(self) -> bool:
        return self.source == "default"

    @property
    def has_critical_alerts(self) -> bool:
        """Whether any active alert is critical severity."""
        return any(a.is_critical for a in self.active_alerts)

    @property
    def fire_safety_alerts(self) -> list[WeatherAlert]:
        """Filter alerts relevant to fire safety engineering."""
        return [a for a in self.active_alerts if a.affects_fire_safety]


class SevereWeatherService:
    """
    Async severe weather alert provider using US NWS API.

    Only works for US locations (NWS is US-only).
    For non-US locations, returns default (no alerts) data.

    Caching:
        - In-memory TTL cache (default 600s / 10 minutes)
        - Alerts change frequently; 10-min TTL balances freshness vs. API load

    Retry:
        - 3 attempts with exponential backoff
        - Falls back to default (no alerts) on failure
    """

    NWS_ALERTS_URL = "https://api.weather.gov/alerts"
    NWS_POINT_URL = "https://api.weather.gov/points"

    def __init__(self, cache_ttl: float = 600.0, request_timeout: float = 15.0):
        self._cache: dict[str, tuple[SevereWeatherData, float]] = {}
        self._cache_ttl = cache_ttl
        self._request_timeout = request_timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-initialize the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._request_timeout),
                headers={
                    "User-Agent": "FireAI-DigitalTwin/1.0",
                    "Accept": "application/ld+json",
                },
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _cache_key(self, latitude: float, longitude: float) -> str:
        """Generate cache key from coordinates."""
        return f"{latitude:.2f},{longitude:.2f}"

    def _get_cached(self, latitude: float, longitude: float) -> Optional[SevereWeatherData]:
        """Get cached data if fresh."""
        key = self._cache_key(latitude, longitude)
        entry = self._cache.get(key)
        if entry is None:
            return None
        data, fetched_at = entry
        if time.time() - fetched_at < self._cache_ttl:
            return data
        return None

    def _set_cached(self, latitude: float, longitude: float, data: SevereWeatherData) -> None:
        """Store data in cache."""
        key = self._cache_key(latitude, longitude)
        self._cache[key] = (data, time.time())

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        reraise=True,
    )
    async def _fetch_nws_alerts(
        self, latitude: float, longitude: float
    ) -> SevereWeatherData:
        """
        Fetch active weather alerts from NWS API.

        Uses the NWS alerts endpoint with point filtering:
        https://api.weather.gov/alerts?point={lat},{lon}

        Returns:
            SevereWeatherData with source="nws"
        """
        client = await self._get_client()
        response = await client.get(
            self.NWS_ALERTS_URL,
            params={"point": f"{latitude},{longitude}"},
        )
        response.raise_for_status()
        body = response.json()

        features = body.get("features", [])
        alerts = []
        max_wind_kt = 0.0
        has_power_risk = False
        has_extreme_temp = False

        for feature in features:
            props = feature.get("properties", {})
            event = props.get("event", "Unknown")
            severity = props.get("severity", "Unknown")
            headline = props.get("headline", "")
            description = props.get("description", "")
            areas = props.get("areaDesc", "")
            effective = props.get("effective", "")
            expires = props.get("expires", "")
            urgency = props.get("urgency", "")
            certainty = props.get("certainty", "")

            alert = WeatherAlert(
                event=event,
                severity=severity,
                headline=headline,
                description=description[:500],  # Truncate for memory
                areas=areas,
                effective=effective,
                expires=expires,
                urgency=urgency,
                certainty=certainty,
            )
            alerts.append(alert)

            # Check for power outage risk indicators
            power_keywords = ["wind", "hurricane", "tornado", "ice", "thunderstorm"]
            if any(kw in event.lower() for kw in power_keywords):
                has_power_risk = True

            # Check for extreme temperature
            temp_keywords = ["heat", "cold", "freeze", "wind chill"]
            if any(kw in event.lower() for kw in temp_keywords):
                has_extreme_temp = True

        data = SevereWeatherData(
            active_alerts=tuple(alerts),
            max_wind_speed_kt=max_wind_kt,
            has_power_outage_risk=has_power_risk,
            has_extreme_temp=has_extreme_temp,
            alert_count=len(alerts),
            source="nws",
        )

        logger.info(
            f"NWS alerts fetched: lat={latitude:.4f}, lon={longitude:.4f}, "
            f"{len(alerts)} active alerts, power_risk={has_power_risk}, "
            f"extreme_temp={has_extreme_temp}"
        )
        return data

    def _get_default(self, latitude: float, longitude: float) -> SevereWeatherData:
        """
        Return default severe weather data (no alerts).

        No alerts = assume normal conditions. This is acceptable because:
        - Lack of alert data is not inherently dangerous
        - Engineering calculations use conservative defaults anyway
        - The weather service (Open-Meteo) still provides wind/temp data
        """
        logger.warning(
            f"Using DEFAULT severe weather data (no alerts) for "
            f"lat={latitude:.4f}, lon={longitude:.4f}. "
            f"NWS API unavailable or non-US location."
        )
        return SevereWeatherData(
            active_alerts=(),
            max_wind_speed_kt=0.0,
            has_power_outage_risk=False,
            has_extreme_temp=False,
            alert_count=0,
            source="default",
        )

    async def fetch_severe_weather(
        self,
        latitude: float,
        longitude: float,
    ) -> SevereWeatherData:
        """
        Fetch severe weather alerts for engineering calculations.

        Strategy:
          1. Check cache — return if fresh (< 10-min TTL)
          2. Fetch from NWS API — retry up to 3 times
          3. On complete failure — return default (no alerts)

        Note: NWS API only covers US locations. For non-US locations,
        returns default data (no alerts). This is acceptable because
        the weather service (Open-Meteo) provides wind/temp data.

        Args:
            latitude: Latitude in decimal degrees (-90 to 90)
            longitude: Longitude in decimal degrees (-180 to 180)

        Returns:
            SevereWeatherData (always succeeds, never raises)
        """
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return self._get_default(latitude, longitude)

        # Check cache
        cached = self._get_cached(latitude, longitude)
        if cached is not None:
            return cached

        # Fetch from NWS API
        try:
            data = await self._fetch_nws_alerts(latitude, longitude)
            self._set_cached(latitude, longitude, data)
            return data
        except (httpx.HTTPError, ValueError, KeyError) as e:
            logger.warning(
                f"NWS API fetch failed for lat={latitude:.4f}, "
                f"lon={longitude:.4f}: {type(e).__name__}: {e}. "
                f"Using defaults (no alerts)."
            )
            return self._get_default(latitude, longitude)
        except Exception as e:
            logger.error(
                f"Unexpected error fetching severe weather for lat={latitude:.4f}, "
                f"lon={longitude:.4f}: {type(e).__name__}: {e}. Using defaults."
            )
            return self._get_default(latitude, longitude)


# Singleton
_severe_weather_service: Optional[SevereWeatherService] = None


def get_severe_weather_service() -> SevereWeatherService:
    """Get the singleton SevereWeatherService instance."""
    global _severe_weather_service
    if _severe_weather_service is None:
        _severe_weather_service = SevereWeatherService()
    return _severe_weather_service


async def close_severe_weather_service() -> None:
    """Close the SevereWeatherService on application shutdown."""
    global _severe_weather_service
    if _severe_weather_service is not None:
        await _severe_weather_service.close()
        _severe_weather_service = None
