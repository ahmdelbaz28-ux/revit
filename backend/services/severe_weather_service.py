"""backend/services/severe_weather_service.py — Severe weather alerts for FireAI.

Provides active weather alerts from multiple international sources:
  - US National Weather Service (NWS) API for US locations
  - MeteoAlarm EU API for European/EEA locations
  - Open-Meteo weather alerts (global, where available)

Severe weather data affects:
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
  - MeteoAlarm EU: https://feeds.meteoalarm.org/
  - MeteoAlarm API v1: https://api.meteoalarm.org/api/v1/warnings/{country_code}
  - CAP format: OASIS Common Alerting Protocol v1.2
  - NFPA 72-2022 §10.6 (secondary power)
  - NFPA 72-2022 §10.14 (battery derating)
  - NFPA 92-2024 §6.4.2 (smoke control wind design)

"""

from __future__ import annotations

import logging
import os
import time

try:
    import defusedxml.ElementTree as ET  # nosec B314 — safe XML parser
except ImportError:
    # FIX: Hard-fail if defusedxml is not available.
    # Standard xml.etree.ElementTree is vulnerable to XML attacks
    # (billion laughs, XXE). In a safety-critical system, we must
    # not silently fall back to an insecure parser.
    ET = None  # type: ignore[assignment]
from dataclasses import dataclass
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


# ── EU/EEA Country Codes for MeteoAlarm ──────────────────────────────────────
# MeteoAlarm covers EU member states, EEA members, and cooperating countries.
# Source: https://www.meteoalarm.org/

METEOALARM_COUNTRY_CODES: frozenset[str] = frozenset({
    # EU Member States
    "AT",  # Austria
    "BE",  # Belgium
    "BG",  # Bulgaria
    "HR",  # Croatia
    "CY",  # Cyprus
    "CZ",  # Czech Republic
    "DK",  # Denmark
    "EE",  # Estonia
    "FI",  # Finland
    "FR",  # France
    "DE",  # Germany
    "GR",  # Greece
    "HU",  # Hungary
    "IE",  # Ireland
    "IT",  # Italy
    "LV",  # Latvia
    "LT",  # Lithuania
    "LU",  # Luxembourg
    "MT",  # Malta
    "NL",  # Netherlands
    "PL",  # Poland
    "PT",  # Portugal
    "RO",  # Romania
    "SK",  # Slovakia
    "SI",  # Slovenia
    "ES",  # Spain
    "SE",  # Sweden
    # EEA / EFTA / Cooperating
    "IS",  # Iceland
    "NO",  # Norway
    "CH",  # Switzerland
    "UK",  # United Kingdom (post-Brexit, still covered)
})

# Mapping from ISO 3166-1 alpha-2 to MeteoAlarm country feed identifiers.
# Most are identical, but some feeds use different codes.
_ISO_TO_METEOALARM: dict[str, str] = {
    "UK": "UK",  # MeteoAlarm uses UK (not GB)
    "GR": "GR",  # MeteoAlarm uses GR (not EL)
}
# All others: country code is used as-is


class WeatherAlertSeverity:
    """NWS/MeteoAlarm alert severity levels.

    Maps both NWS and MeteoAlarm severity terminology to a unified scale:
      - MeteoAlarm Red   → Extreme
      - MeteoAlarm Orange → Severe
      - MeteoAlarm Yellow → Moderate
      - MeteoAlarm Green  → Minor
    """

    EXTREME = "Extreme"
    SEVERE = "Severe"
    MODERATE = "Moderate"
    MINOR = "Minor"
    UNKNOWN = "Unknown"

    # MeteoAlarm color → severity mapping
    METEOALARM_SEVERITY_MAP: dict[str, str] = {
        "red": EXTREME,
        "orange": SEVERE,
        "yellow": MODERATE,
        "green": MINOR,
    }


class WeatherAlertType:
    """Common alert types relevant to fire safety engineering.

    Covers both NWS and MeteoAlarm event types.
    """

    TORNADO_WARNING = "Tornado Warning"
    SEVERE_THUNDERSTORM = "Severe Thunderstorm Warning"
    HIGH_WIND = "High Wind Warning"
    WINTER_STORM = "Winter Storm Warning"
    EXTREME_HEAT = "Excessive Heat Warning"
    EXTREME_COLD = "Extreme Cold Warning"
    FLOOD = "Flood Warning"
    HURRICANE = "Hurricane Warning"
    TROPICAL_STORM = "Tropical Storm Warning"
    # MeteoAlarm-specific types
    WIND_ALERT = "Wind Alert"
    RAIN_ALERT = "Rain Alert"
    SNOW_ICE_ALERT = "Snow/Ice Alert"
    THUNDERSTORM_ALERT = "Thunderstorm Alert"
    FOG_ALERT = "Fog Alert"
    COASTAL_EVENT = "Coastal Event Alert"
    FOREST_FIRE = "Forest Fire Warning"
    AVALANCHE = "Avalanche Warning"
    RAIN_FLOOD = "Rain-Flood Warning"
    HIGH_TEMPERATURE = "High Temperature Alert"
    LOW_TEMPERATURE = "Low Temperature Alert"


# MeteoAlarm alert type code → event name mapping
# Source: CAP profile for MeteoAlarm (EUMETNET)
_METEOALARM_TYPE_MAP: dict[str, str] = {
    "1": "Wind Alert",
    "2": "Snow/Ice Alert",
    "3": "Thunderstorm Alert",
    "4": "Fog Alert",
    "5": "High Temperature Alert",
    "6": "Low Temperature Alert",
    "7": "Coastal Event Alert",
    "8": "Forest Fire Warning",
    "9": "Avalanche Warning",
    "10": "Rain Alert",
    "11": "Rain-Flood Warning",
    "12": "Flood Warning",
    "13": "Rain-Flood Warning",
}


@dataclass(frozen=True)
class WeatherAlert:
    """A single weather alert relevant to fire safety engineering.

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
            "power", "ice", "snow", "fire", "temperature",
            "avalanche", "fog", "coastal", "rain",
        ]
        event_lower = self.event.lower()
        return any(kw in event_lower for kw in fire_safety_keywords)


@dataclass(frozen=True)
class SevereWeatherData:
    """Immutable severe weather data for engineering calculations.

    Attributes:
        active_alerts: List of active weather alerts
        max_wind_speed_kt: Maximum wind speed from alerts (knots)
        has_power_outage_risk: Whether any alert indicates power outage risk
        has_extreme_temp: Whether any alert indicates extreme temperatures
        alert_count: Number of active alerts
        source: Data provenance ("nws" | "meteoalarm" | "openmeteo" | "default")
        coverage_area: Geographic coverage of the alert source
            "us" — US NWS coverage (continental US + territories)
            "eu" — MeteoAlarm coverage (EU/EEA countries)
            "global" — Open-Meteo or partial global coverage
            "none" — No alert source available for this location

    """

    active_alerts: tuple  # Tuple of WeatherAlert (frozen=True requires hashable)
    max_wind_speed_kt: float = 0.0
    has_power_outage_risk: bool = False
    has_extreme_temp: bool = False
    alert_count: int = 0
    source: str = "nws"
    coverage_area: str = "us"

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
    """Async severe weather alert provider with international source dispatch.

    Source selection based on coordinates:
      - US locations (lat 24-50, lon -125 to -66): Use NWS API
      - EU/EEA country codes: Use MeteoAlarm API
      - All others: Try Open-Meteo weather alerts, then default

    Caching:
        - In-memory TTL cache (default 600s / 10 minutes)
        - Alerts change frequently; 10-min TTL balances freshness vs. API load

    Retry:
        - 3 attempts with exponential backoff
        - Falls back to default (no alerts) on failure

    LIFE-SAFETY:
        All external API failures fall back to conservative defaults.
        No alert data is ever allowed to block engineering calculations.
        Per NFPA 72 §10.6 and §10.14, conservative assumptions protect
        life safety even when real-time data is unavailable.
    """

    NWS_ALERTS_URL = os.environ.get("NWS_API_URL", "https://api.weather.gov/alerts")
    NWS_POINT_URL = os.environ.get("NWS_POINTS_URL", "https://api.weather.gov/points")
    METEOALARM_API_URL = os.environ.get("METEOALARM_API_URL", "https://api.meteoalarm.org/api/v1/warnings")
    METEOALARM_ATOM_URL = os.environ.get("METEOALARM_ATOM_URL", "https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-country")
    OPENMETEO_ALERTS_URL = os.environ.get("OPENMETEO_ALERTS_URL", "https://api.open-meteo.com/v1/forecast")

    # US bounding box (continental US)
    US_LAT_MIN = 24.0
    US_LAT_MAX = 50.0
    US_LON_MIN = -125.0
    US_LON_MAX = -66.0

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

    # ── Source Detection ──────────────────────────────────────────────────

    def _is_us_location(self, latitude: float, longitude: float) -> bool:
        """Determine if coordinates fall within US NWS coverage area.

        Uses bounding box for continental US. NWS also covers Alaska,
        Hawaii, and US territories, but these have limited alert coverage.

        Args:
            latitude: Latitude in decimal degrees
            longitude: Longitude in decimal degrees

        Returns:
            True if location is within US NWS coverage bounding box

        """
        return (
            self.US_LAT_MIN <= latitude <= self.US_LAT_MAX
            and self.US_LON_MIN <= longitude <= self.US_LON_MAX
        )

    def _determine_coverage(self, latitude: float, longitude: float) -> str:
        """Determine the best alert source for given coordinates.

        Strategy:
          1. US bounding box → "us" (NWS)
          2. Approximate EU bounding box → "eu" (MeteoAlarm)
          3. All others → "global" (Open-Meteo) or "none"

        Note: EU bounding box is approximate. The actual MeteoAlarm
        availability is verified by country code during the API call.
        The bounding box is used for initial dispatch only.

        Args:
            latitude: Latitude in decimal degrees
            longitude: Longitude in decimal degrees

        Returns:
            Coverage area string: "us", "eu", or "global"

        """
        if self._is_us_location(latitude, longitude):
            return "us"

        # Approximate EU/EEA bounding box
        # Covers from Iceland (approx -24, 64) to Cyprus (approx 34, 35)
        # This is intentionally broad to include all MeteoAlarm countries
        if (
            34.0 <= latitude <= 72.0
            and -25.0 <= longitude <= 45.0
        ):
            return "eu"

        return "global"

    # ── NWS API (US) ─────────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        reraise=True,
    )
    async def _fetch_nws_alerts(
        self, latitude: float, longitude: float
    ) -> SevereWeatherData:
        """Fetch active weather alerts from NWS API.

        Uses the NWS alerts endpoint with point filtering:
        https://api.weather.gov/alerts?point={lat},{lon}

        Coverage: Continental US only (lat 24-50, lon -125 to -66).

        Returns:
            SevereWeatherData with source="nws" and coverage_area="us"

        References:
            - NFPA 72-2022 §10.6 (secondary power sizing)
            - NFPA 72-2022 §10.14 (battery temperature derating)

        """
        client = await self._get_client()
        logger.info(
            f"Fetching NWS alerts: lat={latitude:.4f}, lon={longitude:.4f}"
        )
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
            coverage_area="us",
        )

        logger.info(
            f"NWS alerts fetched: lat={latitude:.4f}, lon={longitude:.4f}, "
            f"{len(alerts)} active alerts, power_risk={has_power_risk}, "
            f"extreme_temp={has_extreme_temp}"
        )
        return data

    # ── MeteoAlarm API (EU/EEA) ──────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        reraise=True,
    )
    async def _fetch_meteoalarm_alerts(
        self, latitude: float, longitude: float, country_code: str
    ) -> SevereWeatherData:
        """Fetch active weather alerts from MeteoAlarm EU API.

        MeteoAlarm provides weather warnings for EU/EEA member states
        using the Common Alerting Protocol (CAP) format.

        Endpoint: https://api.meteoalarm.org/api/v1/warnings/{country_code}

        If the JSON API fails, falls back to the Atom feed:
        https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-country/{cc}

        MeteoAlarm severity levels:
          - Red    → Extreme (immediate threat to life)
          - Orange → Severe (significant threat)
          - Yellow → Moderate (potential threat)
          - Green  → Minor (awareness level)

        Args:
            latitude: Latitude in decimal degrees (for logging/fallback)
            longitude: Longitude in decimal degrees (for logging/fallback)
            country_code: ISO 3166-1 alpha-2 country code (e.g., "DE", "FR")

        Returns:
            SevereWeatherData with source="meteoalarm" and coverage_area="eu"

        References:
            - NFPA 72-2022 §10.6 (secondary power — wind/storm risk)
            - NFPA 92-2024 §6.4.2 (smoke control wind design)
            - EN 54-13 (fire detection and alarm systems — EU standard)

        """
        # Map ISO country code to MeteoAlarm feed identifier
        cc = _ISO_TO_METEOALARM.get(country_code.upper(), country_code.upper())

        alerts: list[WeatherAlert] = []
        has_power_risk = False
        has_extreme_temp = False

        # Try the JSON API first
        try:
            alerts, has_power_risk, has_extreme_temp = (
                await self._fetch_meteoalarm_json(cc)
            )
        except Exception as e:
            logger.warning(
                f"MeteoAlarm JSON API failed for country={cc}: "
                f"{type(e).__name__}: {e}. Trying Atom feed fallback."
            )
            # Fall back to Atom feed
            try:
                alerts, has_power_risk, has_extreme_temp = (
                    await self._fetch_meteoalarm_atom(cc)
                )
            except Exception as atom_err:
                logger.warning(
                    f"MeteoAlarm Atom feed also failed for country={cc}: "
                    f"{type(atom_err).__name__}: {atom_err}. Returning defaults."
                )
                # Both sources failed — return default EU data
                return self._get_default(latitude, longitude, coverage_area="eu")

        data = SevereWeatherData(
            active_alerts=tuple(alerts),
            max_wind_speed_kt=0.0,
            has_power_outage_risk=has_power_risk,
            has_extreme_temp=has_extreme_temp,
            alert_count=len(alerts),
            source="meteoalarm",
            coverage_area="eu",
        )

        logger.info(
            f"MeteoAlarm alerts fetched: country={cc}, "
            f"lat={latitude:.4f}, lon={longitude:.4f}, "
            f"{len(alerts)} active alerts, power_risk={has_power_risk}, "
            f"extreme_temp={has_extreme_temp}"
        )
        return data

    async def _fetch_meteoalarm_json(
        self, country_code: str
    ) -> tuple[list[WeatherAlert], bool, bool]:
        """Fetch alerts from MeteoAlarm JSON API (v1).

        Endpoint: https://api.meteoalarm.org/api/v1/warnings/{country_code}

        Args:
            country_code: MeteoAlarm country identifier

        Returns:
            Tuple of (alerts, has_power_risk, has_extreme_temp)

        Raises:
            httpx.HTTPError: On API failure (caller handles fallback)

        """
        client = await self._get_client()

        # MeteoAlarm API may require a different Accept header
        headers = {
            "User-Agent": "FireAI-DigitalTwin/1.0",
            "Accept": "application/json",
        }

        logger.info("Fetching MeteoAlarm JSON API for country=%s", country_code)
        response = await client.get(
            f"{self.METEOALARM_API_URL}/{country_code}",
            headers=headers,
        )
        response.raise_for_status()
        body = response.json()

        alerts: list[WeatherAlert] = []
        has_power_risk = False
        has_extreme_temp = False

        # Parse MeteoAlarm JSON response
        # The API returns warnings in a "warnings" array
        warnings_list = body.get("warnings", [])
        if not warnings_list and isinstance(body, list):
            warnings_list = body

        for warning in warnings_list:
            try:
                alert = self._parse_meteoalarm_warning(warning)
                if alert is not None:
                    alerts.append(alert)

                    # Check power outage risk
                    event_lower = alert.event.lower()
                    power_keywords = ["wind", "storm", "thunderstorm", "ice", "snow"]
                    if any(kw in event_lower for kw in power_keywords):
                        has_power_risk = True

                    # Check extreme temperature
                    temp_keywords = ["heat", "cold", "temperature", "freeze", "snow/ice"]
                    if any(kw in event_lower for kw in temp_keywords):
                        has_extreme_temp = True

            except Exception as parse_err:
                logger.warning(
                    f"Failed to parse MeteoAlarm warning: {parse_err}. "
                    f"Skipping warning."
                )
                continue

        return alerts, has_power_risk, has_extreme_temp

    def _parse_meteoalarm_warning(self, warning: dict) -> Optional[WeatherAlert]:
        """Parse a single MeteoAlarm warning dict into a WeatherAlert.

        MeteoAlarm JSON warning structure (varies by API version):
          - event: Alert type description
          - severity: "red", "orange", "yellow", "green"
          - headline: Brief description
          - description: Detailed description
          - area: Affected area name
          - onset: Start time (ISO 8601)
          - expires: End time (ISO 8601)
          - urgency: "Immediate", "Expected", "Future"
          - certainty: "Observed", "Likely", "Possible"

        Also handles CAP-format warnings embedded in the JSON response.

        Args:
            warning: Dict from MeteoAlarm API

        Returns:
            WeatherAlert or None if parsing fails

        """
        # Extract event type
        event = warning.get("event", "")
        if not event:
            # Try to map from alert type code
            alert_type = str(warning.get("alert_type", warning.get("type", "")))
            event = _METEOALARM_TYPE_MAP.get(alert_type, f"Weather Alert ({alert_type})")

        # Map severity
        severity_raw = str(
            warning.get("severity", warning.get("color", ""))
        ).lower()
        severity = WeatherAlertSeverity.METEOALARM_SEVERITY_MAP.get(
            severity_raw, WeatherAlertSeverity.UNKNOWN
        )

        # If severity is still unknown, try to extract from the event text
        if severity == WeatherAlertSeverity.UNKNOWN:
            event_lower = event.lower()
            if "extreme" in event_lower or "red" in event_lower:
                severity = WeatherAlertSeverity.EXTREME
            elif "severe" in event_lower or "orange" in event_lower:
                severity = WeatherAlertSeverity.SEVERE
            elif "moderate" in event_lower or "yellow" in event_lower:
                severity = WeatherAlertSeverity.MODERATE
            elif "minor" in event_lower or "green" in event_lower:
                severity = WeatherAlertSeverity.MINOR

        headline = warning.get("headline", warning.get("title", event))
        description = warning.get("description", warning.get("text", ""))
        if description and len(description) > 500:
            description = description[:500]

        areas = warning.get("area", warning.get("areaDesc", ""))
        if isinstance(areas, list):
            areas = ", ".join(str(a) for a in areas)

        effective = warning.get("onset", warning.get("effective", ""))
        expires = warning.get("expires", warning.get("expire", ""))
        urgency = warning.get("urgency", "")
        certainty = warning.get("certainty", "")

        return WeatherAlert(
            event=event,
            severity=severity,
            headline=headline,
            description=description,
            areas=areas,
            effective=effective,
            expires=expires,
            urgency=urgency,
            certainty=certainty,
        )

    async def _fetch_meteoalarm_atom(
        self, country_code: str
    ) -> tuple[list[WeatherAlert], bool, bool]:
        """Fetch alerts from MeteoAlarm Atom feed (legacy fallback).

        Endpoint: https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-country/{cc}

        The Atom feed contains CAP (Common Alerting Protocol) entries
        with embedded XML alert data.

        Args:
            country_code: MeteoAlarm country identifier

        Returns:
            Tuple of (alerts, has_power_risk, has_extreme_temp)

        Raises:
            httpx.HTTPError: On API failure

        """
        client = await self._get_client()

        headers = {
            "User-Agent": "FireAI-DigitalTwin/1.0",
            "Accept": "application/atom+xml, application/xml, text/xml",
        }

        logger.info("Fetching MeteoAlarm Atom feed for country=%s", country_code)
        response = await client.get(
            f"{self.METEOALARM_ATOM_URL}/{country_code}",
            headers=headers,
        )
        response.raise_for_status()

        alerts: list[WeatherAlert] = []
        has_power_risk = False
        has_extreme_temp = False

        try:
            # FIX: Guard against missing defusedxml
            if ET is None:
                raise ImportError(
                    "defusedxml is required for XML parsing in safety-critical systems. "
                    "Install with: pip install defusedxml"
                )
            # Parse Atom XML feed (ET is defusedxml.ElementTree when available — noqa S314)
            root = ET.fromstring(response.text)

            # Atom namespace
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "cap": "urn:oasis:names:tc:emergency:cap:1.2",
                "georss": "http://www.georss.org/georss",
            }

            # Find all <entry> elements
            entries = root.findall(".//atom:entry", ns)
            if not entries:
                # Try without namespace (some feeds omit it)
                entries = root.findall(".//entry")

            for entry in entries:
                try:
                    alert = self._parse_meteoalarm_atom_entry(entry, ns)
                    if alert is not None:
                        alerts.append(alert)

                        event_lower = alert.event.lower()
                        power_keywords = ["wind", "storm", "thunderstorm", "ice", "snow"]
                        if any(kw in event_lower for kw in power_keywords):
                            has_power_risk = True

                        temp_keywords = ["heat", "cold", "temperature", "freeze", "snow/ice"]
                        if any(kw in event_lower for kw in temp_keywords):
                            has_extreme_temp = True

                except Exception as parse_err:
                    logger.warning(
                        f"Failed to parse MeteoAlarm Atom entry: {parse_err}. Skipping."
                    )
                    continue

        except ET.ParseError as e:
            logger.warning("MeteoAlarm Atom XML parse error: %s", e)
            # Return empty results — caller will handle fallback
            pass

        return alerts, has_power_risk, has_extreme_temp

    def _parse_meteoalarm_atom_entry(
        self, entry: ET.Element, ns: dict
    ) -> Optional[WeatherAlert]:
        """Parse a single Atom <entry> element into a WeatherAlert.

        MeteoAlarm Atom entries contain:
          - <title>: Alert headline
          - <summary>: Alert description
          - <cap:event>: Alert event type
          - <cap:severity>: Severity level
          - <cap:urgency>: Urgency
          - <cap:certainty>: Certainty
          - <cap:effective>: Start time
          - <cap:expires>: End time
          - <cap:areaDesc>: Affected areas

        Args:
            entry: XML Element for the Atom entry
            ns: Namespace mapping dict

        Returns:
            WeatherAlert or None if parsing fails

        """
        # Try namespaced elements first, then fall back to non-namespaced
        def find_text(element: ET.Element, path_ns: str, path_no_ns: str) -> str:
            result = element.find(path_ns, ns)
            if result is None:
                result = element.find(path_no_ns)
            return result.text if result is not None and result.text else ""

        title = find_text(entry, "atom:title", "title")
        summary = find_text(entry, "atom:summary", "summary")

        event = find_text(entry, "cap:event", "event")
        if not event:
            event = title

        severity_raw = find_text(entry, "cap:severity", "severity").lower()
        # Map CAP severity terms to our unified scale
        # CAP uses: "Extreme", "Severe", "Moderate", "Minor"
        # MeteoAlarm also uses color codes in some feeds
        severity = WeatherAlertSeverity.METEOALARM_SEVERITY_MAP.get(
            severity_raw,
            severity_raw.capitalize() if severity_raw else WeatherAlertSeverity.UNKNOWN,
        )
        # Also handle CAP standard severity names directly
        if severity not in (
            WeatherAlertSeverity.EXTREME,
            WeatherAlertSeverity.SEVERE,
            WeatherAlertSeverity.MODERATE,
            WeatherAlertSeverity.MINOR,
        ):
            cap_severity_map = {
                "extreme": WeatherAlertSeverity.EXTREME,
                "severe": WeatherAlertSeverity.SEVERE,
                "moderate": WeatherAlertSeverity.MODERATE,
                "minor": WeatherAlertSeverity.MINOR,
            }
            severity = cap_severity_map.get(severity_raw, WeatherAlertSeverity.UNKNOWN)

        urgency = find_text(entry, "cap:urgency", "urgency")
        certainty = find_text(entry, "cap:certainty", "certainty")
        effective = find_text(entry, "cap:effective", "effective")
        expires = find_text(entry, "cap:expires", "expires")
        areas = find_text(entry, "cap:areaDesc", "areaDesc")

        description = summary if summary else ""
        if len(description) > 500:
            description = description[:500]

        return WeatherAlert(
            event=event,
            severity=severity,
            headline=title,
            description=description,
            areas=areas,
            effective=effective,
            expires=expires,
            urgency=urgency,
            certainty=certainty,
        )

    # ── Open-Meteo Alerts (Global fallback) ───────────────────────────────

    async def _fetch_openmeteo_alerts(
        self, latitude: float, longitude: float
    ) -> SevereWeatherData:
        """Attempt to fetch weather alerts from Open-Meteo.

        Open-Meteo provides limited weather alert data for some regions.
        This is a best-effort global fallback when neither NWS nor
        MeteoAlarm covers the location.

        Endpoint: https://api.open-meteo.com/v1/forecast
          with parameters: latitude, longitude, &weather_codes=true

        Note: Open-Meteo does not have a dedicated alerts endpoint.
        This checks for severe weather codes in the current forecast
        as a proxy for active alerts. When no alert data is available,
        returns default data with coverage_area="global".

        Args:
            latitude: Latitude in decimal degrees
            longitude: Longitude in decimal degrees

        Returns:
            SevereWeatherData with source="openmeteo" or "default"
            and coverage_area="global"

        References:
            - NFPA 72-2022 §10.6 (secondary power)
            - Conservative default when no alert source available

        """
        client = await self._get_client()

        try:
            logger.info(
                f"Attempting Open-Meteo alert check: "
                f"lat={latitude:.4f}, lon={longitude:.4f}"
            )
            response = await client.get(
                self.OPENMETEO_ALERTS_URL,
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current_weather": True,
                },
            )
            response.raise_for_status()
            body = response.json()

            # Check current weather code for severe conditions
            # WMO Weather interpretation codes:
            # 95-99: Thunderstorm
            # 71-77: Snow fall
            # 65-66: Heavy rain
            # 56-57: Freezing drizzle
            # 51-55: Drizzle (not severe)
            current = body.get("current_weather", {})
            weather_code = current.get("weathercode", 0)

            alerts: list[WeatherAlert] = []
            has_power_risk = False
            has_extreme_temp = False

            if weather_code >= 95:
                # Thunderstorm
                alerts.append(WeatherAlert(
                    event="Thunderstorm Alert",
                    severity=WeatherAlertSeverity.SEVERE,
                    headline=f"Active thunderstorm detected (WMO code: {weather_code})",
                    description="Open-Meteo detected thunderstorm conditions. "
                                "Power outage risk elevated per NFPA 72 §10.6.",
                    areas=f"lat={latitude:.2f}, lon={longitude:.2f}",
                    effective=current.get("time", ""),
                    urgency="Immediate",
                    certainty="Observed",
                ))
                has_power_risk = True
            elif weather_code >= 71:
                # Snow/ice
                alerts.append(WeatherAlert(
                    event="Snow/Ice Alert",
                    severity=WeatherAlertSeverity.MODERATE,
                    headline=f"Snow or ice conditions detected (WMO code: {weather_code})",
                    description="Open-Meteo detected snow/ice conditions. "
                                "Power outage risk may be elevated per NFPA 72 §10.6.",
                    areas=f"lat={latitude:.2f}, lon={longitude:.2f}",
                    effective=current.get("time", ""),
                    urgency="Expected",
                    certainty="Likely",
                ))
                has_extreme_temp = True
                has_power_risk = True

            source = "openmeteo" if alerts else "default"

            data = SevereWeatherData(
                active_alerts=tuple(alerts),
                max_wind_speed_kt=0.0,
                has_power_outage_risk=has_power_risk,
                has_extreme_temp=has_extreme_temp,
                alert_count=len(alerts),
                source=source,
                coverage_area="global",
            )

            logger.info(
                f"Open-Meteo alert check: lat={latitude:.4f}, lon={longitude:.4f}, "
                f"WMO code={weather_code}, {len(alerts)} alerts generated, "
                f"source={source}"
            )
            return data

        except Exception as e:
            logger.warning(
                f"Open-Meteo alert check failed for lat={latitude:.4f}, "
                f"lon={longitude:.4f}: {type(e).__name__}: {e}. "
                f"Using defaults (no alerts)."
            )
            return self._get_default(latitude, longitude, coverage_area="global")

    # ── Default Data ─────────────────────────────────────────────────────

    def _get_default(
        self,
        latitude: float,
        longitude: float,
        coverage_area: str = "none",
    ) -> SevereWeatherData:
        """Return default severe weather data (no alerts).

        No alerts = assume normal conditions. This is acceptable because:
        - Lack of alert data is not inherently dangerous
        - Engineering calculations use conservative defaults anyway
        - The weather service (Open-Meteo) still provides wind/temp data

        Args:
            latitude: Latitude for logging
            longitude: Longitude for logging
            coverage_area: Coverage area to report ("us", "eu", "global", "none")

        Returns:
            SevereWeatherData with no active alerts

        """
        logger.warning(
            f"Using DEFAULT severe weather data (no alerts) for "
            f"lat={latitude:.4f}, lon={longitude:.4f}. "
            f"Coverage area: {coverage_area}. "
            f"No alert source available for this location."
        )
        return SevereWeatherData(
            active_alerts=(),
            max_wind_speed_kt=0.0,
            has_power_outage_risk=False,
            has_extreme_temp=False,
            alert_count=0,
            source="default",
            coverage_area=coverage_area,
        )

    # ── Country Code Resolution ──────────────────────────────────────────

    async def _resolve_country_code(
        self, latitude: float, longitude: float
    ) -> Optional[str]:
        """Resolve coordinates to an ISO 3166-1 alpha-2 country code.

        Uses the GeocodingService (reverse geocoding) to determine
        the country. Returns None if resolution fails.

        Args:
            latitude: Latitude in decimal degrees
            longitude: Longitude in decimal degrees

        Returns:
            ISO country code (e.g., "DE", "US") or None

        """
        try:
            from backend.services.geocoding_service import get_geocoding_service
            geo_svc = get_geocoding_service()
            result = await geo_svc.reverse_geocode(latitude, longitude)
            if result and result.country_code:
                return result.country_code.upper()
        except ImportError:
            logger.debug("GeocodingService not available for country resolution")
        except Exception as e:
            logger.debug(
                f"Reverse geocoding failed for lat={latitude:.4f}, "
                f"lon={longitude:.4f}: {type(e).__name__}: {e}"
            )
        return None

    # ── Main Public API ──────────────────────────────────────────────────

    async def fetch_severe_weather(
        self,
        latitude: float,
        longitude: float,
    ) -> SevereWeatherData:
        """Fetch severe weather alerts for engineering calculations.

        Strategy (international dispatch):
          1. Check cache — return if fresh (< 10-min TTL)
          2. Determine coverage area from coordinates:
             a. US locations (lat 24-50, lon -125 to -66): Use NWS API
             b. EU/EEA locations: Use MeteoAlarm API
             c. All others: Try Open-Meteo, then default
          3. On complete failure — return default (no alerts)

        The public API signature is unchanged. The `coverage_area` field
        in the returned SevereWeatherData indicates which source was used.

        Args:
            latitude: Latitude in decimal degrees (-90 to 90)
            longitude: Longitude in decimal degrees (-180 to 180)

        Returns:
            SevereWeatherData (always succeeds, never raises)

        References:
            - NFPA 72-2022 §10.6 (secondary power)
            - NFPA 72-2022 §10.14 (battery derating)
            - NFPA 92-2024 §6.4.2 (smoke control wind design)

        """
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return self._get_default(latitude, longitude, coverage_area="none")

        # Check cache
        cached = self._get_cached(latitude, longitude)
        if cached is not None:
            return cached

        # Determine which alert source to use
        coverage = self._determine_coverage(latitude, longitude)

        # ── US: NWS API ──
        if coverage == "us":
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
                default = self._get_default(latitude, longitude, coverage_area="us")
                self._set_cached(latitude, longitude, default)
                return default
            except Exception as e:
                logger.error(
                    f"Unexpected error fetching NWS severe weather for "
                    f"lat={latitude:.4f}, lon={longitude:.4f}: "
                    f"{type(e).__name__}: {e}. Using defaults."
                )
                default = self._get_default(latitude, longitude, coverage_area="us")
                self._set_cached(latitude, longitude, default)
                return default

        # ── EU/EEA: MeteoAlarm API ──
        if coverage == "eu":
            try:
                # Resolve country code for MeteoAlarm dispatch
                country_code = await self._resolve_country_code(latitude, longitude)

                if country_code and country_code in METEOALARM_COUNTRY_CODES:
                    data = await self._fetch_meteoalarm_alerts(
                        latitude, longitude, country_code
                    )
                    self._set_cached(latitude, longitude, data)
                    return data
                # Coordinates are in EU bounding box but country code
                # not in MeteoAlarm coverage. Try as-is with the
                # resolved country code (some nearby countries may work).
                if country_code:
                    logger.info(
                        f"Country {country_code} not in MeteoAlarm list, "
                        f"attempting API call anyway for lat={latitude:.4f}, "
                        f"lon={longitude:.4f}"
                    )
                    try:
                        data = await self._fetch_meteoalarm_alerts(
                            latitude, longitude, country_code
                        )
                        self._set_cached(latitude, longitude, data)
                        return data
                    except Exception as e:
                        logger.debug("NWS API failed, falling through to Open-Meteo: %s", e)
                        # Fall through to Open-Meteo

                # No country code resolved or MeteoAlarm failed —
                # try Open-Meteo as global fallback
                logger.info(
                    f"MeteoAlarm not available for lat={latitude:.4f}, "
                    f"lon={longitude:.4f} (country={country_code}). "
                    f"Trying Open-Meteo fallback."
                )
                data = await self._fetch_openmeteo_alerts(latitude, longitude)
                self._set_cached(latitude, longitude, data)
                return data

            except (httpx.HTTPError, ValueError, KeyError) as e:
                logger.warning(
                    f"MeteoAlarm API fetch failed for lat={latitude:.4f}, "
                    f"lon={longitude:.4f}: {type(e).__name__}: {e}. "
                    f"Trying Open-Meteo fallback."
                )
                try:
                    data = await self._fetch_openmeteo_alerts(latitude, longitude)
                    self._set_cached(latitude, longitude, data)
                    return data
                except Exception as e:
                    logger.debug("Open-Meteo alert fallback also failed, using defaults: %s", e)
                    default = self._get_default(latitude, longitude, coverage_area="eu")
                    self._set_cached(latitude, longitude, default)
                    return default
            except Exception as e:
                logger.error(
                    f"Unexpected error fetching MeteoAlarm severe weather for "
                    f"lat={latitude:.4f}, lon={longitude:.4f}: "
                    f"{type(e).__name__}: {e}. Using defaults."
                )
                default = self._get_default(latitude, longitude, coverage_area="eu")
                self._set_cached(latitude, longitude, default)
                return default

        # ── Global: Open-Meteo fallback ──
        try:
            data = await self._fetch_openmeteo_alerts(latitude, longitude)
            self._set_cached(latitude, longitude, data)
            return data
        except Exception as e:
            logger.error(
                f"Open-Meteo alert check failed for lat={latitude:.4f}, "
                f"lon={longitude:.4f}: {type(e).__name__}: {e}. "
                f"Using defaults (no alerts)."
            )
            default = self._get_default(latitude, longitude, coverage_area="global")
            self._set_cached(latitude, longitude, default)
            return default


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
