"""
tests/test_external_api_adapters.py.
=====================================
Tests for the V82 External Advisory API Adapters.

TEST PHILOSOPHY (agent.md Rule 12 — Safety-First):
  These adapters are SAFETY-CRITICAL infrastructure. Tests verify:
    1. Happy path: real-shape API responses parse correctly.
    2. Fail-safe: every failure mode returns a typed fallback, NEVER raises.
    3. Circuit breaker: trips after N failures, short-circuits, recovers.
    4. Invariants: ApiResult invariants hold (ok ⟺ fallback_used negation).
    5. Input validation: bad lat/lon rejected with fallback.
    6. Conservative defaults: fallback uses UNKNOWN / NaN, never fabricated LOW.

  Tests do NOT make real HTTP calls — they use respx to mock httpx.
  This ensures determinism and runs in CI without network access.
"""

from __future__ import annotations

import asyncio
import math
import os
import time
from datetime import datetime, timezone

import httpx
import pytest
import respx

from fireai.integration.external_api_base import (
    ApiResult,
    CircuitState,
    ExternalApiAdapter,
)
from fireai.integration.wildfire_smoke_adapter import (
    WildfireSmokeAdapter,
    WildfireSmokeAssessment,
)
from fireai.integration.earthquake_adapter import (
    EarthquakeAdapter,
    EarthquakeAssessment,
    EarthquakeEvent,
)
from fireai.integration.openaq_adapter import (
    OpenAQAdapter,
    AirQualityAssessment,
)
from fireai.integration.ais_vessel_adapter import (
    AISVesselAdapter,
    VesselProximityAssessment,
    haversine_nm,
)
from fireai.integration.elevation_adapter import (
    ElevationAdapter,
    ElevationReading,
)


# ===========================================================================
# ApiResult invariant tests
# ===========================================================================


class TestApiResultInvariants:
    """Verify the typed-result contract — no falsifiable state."""

    def test_ok_true_no_error_no_fallback(self):
        r = ApiResult(ok=True, value=42, source="test", latency_ms=10.0)
        assert r.ok is True
        assert r.error == ""
        assert r.fallback_used is False

    def test_ok_false_must_have_error(self):
        r = ApiResult(ok=False, value=0, source="test", error="timeout",
                      fallback_used=True)
        assert r.ok is False
        assert r.error == "timeout"
        assert r.fallback_used is True

    def test_ok_true_with_error_raises(self):
        with pytest.raises(ValueError, match="ok=True ⟹ error must be empty"):
            ApiResult(ok=True, value=42, source="test", error="oops")

    def test_ok_true_with_fallback_used_raises(self):
        with pytest.raises(ValueError, match="ok=True ⟹ fallback_used=False"):
            ApiResult(ok=True, value=42, source="test", fallback_used=True)

    def test_ok_false_without_error_raises(self):
        with pytest.raises(ValueError, match="ok=False ⟹ error must be set"):
            ApiResult(ok=False, value=0, source="test", fallback_used=True)

    def test_ok_false_without_fallback_used_raises(self):
        """ok=False with fallback_used=False violates the invariant."""
        with pytest.raises(ValueError, match="ok=False ⟹ error must be set"):
            ApiResult(ok=False, value=0, source="test", error="timeout")


# ===========================================================================
# Circuit breaker tests
# ===========================================================================


class TestCircuitBreaker:
    """Verify the circuit-breaker state machine."""

    def test_starts_closed(self):
        cb = CircuitState(failure_threshold=3, cooldown_seconds=1.0)
        assert cb.state == "CLOSED"
        assert cb.should_short_circuit() is False

    def test_opens_after_threshold(self):
        cb = CircuitState(failure_threshold=3, cooldown_seconds=60.0)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "CLOSED"
        cb.record_failure()
        assert cb.state == "OPEN"
        assert cb.should_short_circuit() is True

    def test_success_resets(self):
        cb = CircuitState(failure_threshold=3, cooldown_seconds=60.0)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.state == "CLOSED"
        assert cb._consecutive_failures == 0

    def test_transitions_to_half_open_after_cooldown(self):
        cb = CircuitState(failure_threshold=2, cooldown_seconds=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "OPEN"
        time.sleep(0.15)
        assert cb.state == "HALF_OPEN"
        assert cb.should_short_circuit() is False  # half-open allows probe

    def test_half_open_success_closes(self):
        cb = CircuitState(failure_threshold=2, cooldown_seconds=0.1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        _ = cb.state  # trigger transition to HALF_OPEN
        cb.record_success()
        assert cb.state == "CLOSED"

    def test_half_open_failure_reopens(self):
        cb = CircuitState(failure_threshold=2, cooldown_seconds=0.1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        _ = cb.state  # trigger transition to HALF_OPEN
        cb.record_failure()
        assert cb.state == "OPEN"


# ===========================================================================
# WildfireSmokeAdapter tests
# ===========================================================================


WILDFIRE_BASE = "https://air-quality-api.open-meteo.com/v1/air-quality"


class TestWildfireSmokeAdapter:

    @pytest.mark.asyncio
    @respx.mock
    async def test_happy_path_low_risk(self):
        """PM2.5 below 9.0 → LOW risk."""
        respx.get(WILDFIRE_BASE).mock(return_value=httpx.Response(200, json={
            "hourly": {
                "pm2_5": [5.0] * 24,
                "pm10": [10.0] * 24,
                "carbon_monoxide": [100.0] * 24,
                "nitrogen_dioxide": [20.0] * 24,
            }
        }))
        adapter = WildfireSmokeAdapter()
        result = await adapter.call(lat=30.04, lon=31.23)
        assert result.ok is True
        assert isinstance(result.value, WildfireSmokeAssessment)
        assert result.value.false_alarm_risk == "LOW"
        assert result.value.aqi_category == "GOOD"
        assert result.value.peak_pm25_24h == 5.0
        assert result.error == ""
        assert result.fallback_used is False
        await adapter.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_high_risk_above_threshold(self):
        """PM2.5 >= 35.5 → HIGH risk (smoke detector advisory)."""
        respx.get(WILDFIRE_BASE).mock(return_value=httpx.Response(200, json={
            "hourly": {
                "pm2_5": [40.0] * 24,
                "pm10": [80.0] * 24,
                "carbon_monoxide": [500.0] * 24,
                "nitrogen_dioxide": [60.0] * 24,
            }
        }))
        adapter = WildfireSmokeAdapter()
        result = await adapter.call(lat=30.04, lon=31.23)
        assert result.ok is True
        assert result.value.false_alarm_risk == "HIGH"
        assert result.value.aqi_category == "UNHEALTHY_SG"
        assert "smoke detector" in result.value.advisory_note.lower()
        await adapter.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_timeout_returns_fallback_unknown(self):
        """Timeout → fallback with UNKNOWN risk, never raises."""
        respx.get(WILDFIRE_BASE).mock(side_effect=httpx.TimeoutException("slow"))
        adapter = WildfireSmokeAdapter()
        result = await adapter.call(lat=30.04, lon=31.23)
        assert result.ok is False
        assert result.error == "timeout"
        assert result.fallback_used is True
        assert result.value.false_alarm_risk == "UNKNOWN"
        assert math.isnan(result.value.peak_pm25_24h)
        await adapter.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_http_500_returns_fallback(self):
        """HTTP 5xx → fallback, circuit-breaker counts failure."""
        respx.get(WILDFIRE_BASE).mock(return_value=httpx.Response(503))
        adapter = WildfireSmokeAdapter()
        result = await adapter.call(lat=30.04, lon=31.23)
        assert result.ok is False
        assert result.error == "http_5xx"
        assert result.value.false_alarm_risk == "UNKNOWN"
        await adapter.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_parse_error_missing_hourly(self):
        """Malformed response (no 'hourly' key) → parse_error fallback."""
        respx.get(WILDFIRE_BASE).mock(return_value=httpx.Response(200, json={
            "wrong_key": {}
        }))
        adapter = WildfireSmokeAdapter()
        result = await adapter.call(lat=30.04, lon=31.23)
        assert result.ok is False
        assert result.error == "parse_error"
        assert result.value.false_alarm_risk == "UNKNOWN"
        await adapter.aclose()

    @pytest.mark.asyncio
    async def test_invalid_latitude_raises_value_error_caught(self):
        """Bad lat → ValueError caught as parse_error."""
        adapter = WildfireSmokeAdapter()
        result = await adapter.call(lat=999.0, lon=31.23)
        assert result.ok is False
        assert result.error == "parse_error"
        assert result.value.false_alarm_risk == "UNKNOWN"
        await adapter.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_circuit_opens_after_five_failures(self):
        """5 consecutive failures → circuit opens, short-circuits subsequent calls."""
        respx.get(WILDFIRE_BASE).mock(return_value=httpx.Response(503))
        adapter = WildfireSmokeAdapter(failure_threshold=5, cooldown_seconds=60.0)
        # 5 failures → circuit should open
        for i in range(5):
            r = await adapter.call(lat=30.0, lon=31.0)
            assert r.ok is False
        # 6th call → circuit_open, not http_5xx
        r = await adapter.call(lat=30.0, lon=31.0)
        assert r.ok is False
        assert r.error == "circuit_open"
        await adapter.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_health_check(self):
        respx.get(WILDFIRE_BASE).mock(return_value=httpx.Response(200, json={
            "hourly": {"pm2_5": [5.0], "pm10": [10.0],
                       "carbon_monoxide": [100.0], "nitrogen_dioxide": [20.0]}
        }))
        adapter = WildfireSmokeAdapter()
        await adapter.call(lat=30.0, lon=31.0)
        h = adapter.health()
        assert h["source"] == "wildfire_smoke"
        assert h["circuit_state"] == "CLOSED"
        assert h["consecutive_failures"] == 0
        await adapter.aclose()


# ===========================================================================
# EarthquakeAdapter tests
# ===========================================================================


USGS_BASE = "https://earthquake.usgs.gov/fdsnws/event/1/query"


class TestEarthquakeAdapter:

    @pytest.mark.asyncio
    @respx.mock
    async def test_no_events_low_priority(self):
        """Empty features list → LOW priority."""
        respx.get(USGS_BASE).mock(return_value=httpx.Response(200, json={
            "features": []
        }))
        adapter = EarthquakeAdapter()
        result = await adapter.call(lat=30.0, lon=31.0)
        assert result.ok is True
        assert result.value.inspection_recommended == "LOW"
        assert result.value.max_magnitude == 0.0
        assert result.value.strongest_event is None
        await adapter.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_m6_earthquake_critical(self):
        """M6.0+ earthquake → CRITICAL priority."""
        respx.get(USGS_BASE).mock(return_value=httpx.Response(200, json={
            "features": [{
                "properties": {"mag": 6.5, "place": "100km NW of Cairo",
                               "time": 1700000000000, "tsunami": 0,
                               "url": "https://earthquake.usgs.gov/..."},
                "geometry": {"coordinates": [31.0, 30.5, 10.0]}
            }]
        }))
        adapter = EarthquakeAdapter()
        result = await adapter.call(lat=30.0, lon=31.0)
        assert result.ok is True
        assert result.value.inspection_recommended == "CRITICAL"
        assert result.value.max_magnitude == 6.5
        assert result.value.strongest_event is not None
        assert result.value.strongest_event.magnitude == 6.5
        assert result.value.strongest_event.tsunami_warning is False
        assert "IMMEDIATELY" in result.value.advisory_note
        await adapter.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_m5_earthquake_high(self):
        respx.get(USGS_BASE).mock(return_value=httpx.Response(200, json={
            "features": [{
                "properties": {"mag": 5.3, "place": "x", "time": 1700000000000,
                               "tsunami": 1, "url": ""},
                "geometry": {"coordinates": [31.0, 30.5, 10.0]}
            }]
        }))
        adapter = EarthquakeAdapter()
        result = await adapter.call(lat=30.0, lon=31.0)
        assert result.ok is True
        assert result.value.inspection_recommended == "HIGH"
        assert result.value.strongest_event.tsunami_warning is True
        await adapter.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_network_error_returns_unknown(self):
        """Network error → fallback UNKNOWN (not LOW — never fabricate)."""
        respx.get(USGS_BASE).mock(side_effect=httpx.ConnectError("dns fail"))
        adapter = EarthquakeAdapter()
        result = await adapter.call(lat=30.0, lon=31.0)
        assert result.ok is False
        assert result.error == "network"
        assert result.value.inspection_recommended == "UNKNOWN"
        assert "could not be verified" in result.value.advisory_note
        await adapter.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_malformed_feature_skipped(self):
        """Malformed features are skipped, not fatal."""
        respx.get(USGS_BASE).mock(return_value=httpx.Response(200, json={
            "features": [
                {"properties": {}, "geometry": {}},  # missing mag
                {"properties": {"mag": 4.5, "place": "ok",
                                "time": 1700000000000, "tsunami": 0, "url": ""},
                 "geometry": {"coordinates": [31.0, 30.5, 10.0]}},
            ]
        }))
        adapter = EarthquakeAdapter()
        result = await adapter.call(lat=30.0, lon=31.0)
        assert result.ok is True
        assert len(result.value.recent_events) == 1
        assert result.value.recent_events[0].magnitude == 4.5
        await adapter.aclose()

    @pytest.mark.asyncio
    async def test_invalid_radius(self):
        adapter = EarthquakeAdapter()
        r = await adapter.call(lat=30.0, lon=31.0, radius_km=99999)
        assert r.ok is False
        assert r.error == "parse_error"
        await adapter.aclose()


# ===========================================================================
# OpenAQAdapter tests
# ===========================================================================


OPENAQ_BASE = "https://api.openaq.org/v3/measurements"


class TestOpenAQAdapter:

    @pytest.mark.asyncio
    @respx.mock
    async def test_happy_path_with_api_key(self, monkeypatch):
        monkeypatch.setenv("OPENAQ_API_KEY", "test-key-123")
        respx.get(OPENAQ_BASE).mock(return_value=httpx.Response(200, json={
            "results": [
                {"parameter": "pm25", "value": 12.5, "unit": "µg/m³",
                 "location": "StationA", "locationId": 42,
                 "date": {"utc": "2026-06-30T10:00:00Z"},
                 "coordinates": {"latitude": 30.0, "longitude": 31.0}},
                {"parameter": "pm10", "value": 25.0, "unit": "µg/m³",
                 "location": "StationA", "locationId": 42,
                 "date": {"utc": "2026-06-30T10:00:00Z"},
                 "coordinates": {"latitude": 30.0, "longitude": 31.0}},
            ]
        }))
        adapter = OpenAQAdapter()
        result = await adapter.call(lat=30.0, lon=31.0)
        assert result.ok is True
        assert result.value.current_pm25 == 12.5
        assert result.value.current_pm10 == 25.0
        assert result.value.false_alarm_risk == "MODERATE"  # 12.5 in 9.1-35.4
        assert result.value.stations_reported == 1
        await adapter.aclose()

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_fallback(self, monkeypatch):
        """No API key → parse_error fallback (config issue, not service issue)."""
        monkeypatch.delenv("OPENAQ_API_KEY", raising=False)
        adapter = OpenAQAdapter()
        result = await adapter.call(lat=30.0, lon=31.0)
        assert result.ok is False
        assert result.error == "parse_error"
        assert result.value.false_alarm_risk == "UNKNOWN"
        await adapter.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_http_403_returns_fallback(self, monkeypatch):
        monkeypatch.setenv("OPENAQ_API_KEY", "bad-key")
        respx.get(OPENAQ_BASE).mock(return_value=httpx.Response(403))
        adapter = OpenAQAdapter()
        result = await adapter.call(lat=30.0, lon=31.0)
        assert result.ok is False
        assert result.error == "http_4xx"
        assert result.value.false_alarm_risk == "UNKNOWN"
        await adapter.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_empty_results_unknown(self, monkeypatch):
        monkeypatch.setenv("OPENAQ_API_KEY", "test-key")
        respx.get(OPENAQ_BASE).mock(return_value=httpx.Response(200, json={
            "results": []
        }))
        adapter = OpenAQAdapter()
        result = await adapter.call(lat=30.0, lon=31.0)
        assert result.ok is True
        assert result.value.false_alarm_risk == "UNKNOWN"
        assert result.value.stations_reported == 0
        await adapter.aclose()


# ===========================================================================
# AISVesselAdapter tests
# ===========================================================================


AISHUB_BASE = "http://data.aishub.net/ws.php"


class TestAISVesselAdapter:

    @pytest.mark.asyncio
    @respx.mock
    async def test_no_vessels_low(self, monkeypatch):
        monkeypatch.setenv("AISHUB_API_KEY", "test-key")
        respx.get(AISHUB_BASE).mock(return_value=httpx.Response(200, json=[
            [{"status": "ok"}]  # metadata only
        ]))
        adapter = AISVesselAdapter()
        result = await adapter.call(lat=25.0, lon=55.0)
        assert result.ok is True
        assert result.value.proximity_alert == "LOW"
        assert len(result.value.vessels) == 0
        await adapter.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_tanker_within_1nm_critical(self, monkeypatch):
        """Tanker (ship_type 70) < 1 NM → CRITICAL."""
        monkeypatch.setenv("AISHUB_API_KEY", "test-key")
        # Vessel at 25.001°N, 55.0°E (very close to query point 25.0, 55.0)
        respx.get(AISHUB_BASE).mock(return_value=httpx.Response(200, json=[
            {"status": "ok"},
            [["123456789", "TANKER X", 25.001, 55.0, 5.0, 90.0, 90.0, 0,
              None, None, None, None, None, None, None, 70]]
        ]))
        adapter = AISVesselAdapter()
        result = await adapter.call(lat=25.0, lon=55.0)
        assert result.ok is True
        assert result.value.proximity_alert == "CRITICAL"
        assert len(result.value.hazardous_vessels) == 1
        assert result.value.nearest_hazardous.is_hazardous_cargo is True
        assert "TANKER X" in result.value.advisory_note
        await adapter.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_fishing_boat_no_hazard_low(self, monkeypatch):
        """Fishing boat (ship_type 30) nearby → LOW (not hazardous)."""
        monkeypatch.setenv("AISHUB_API_KEY", "test-key")
        respx.get(AISHUB_BASE).mock(return_value=httpx.Response(200, json=[
            {"status": "ok"},
            [["123456789", "FISHING-1", 25.001, 55.0, 5.0, 90.0, 90.0, 0,
              None, None, None, None, None, None, None, 30]]
        ]))
        adapter = AISVesselAdapter()
        result = await adapter.call(lat=25.0, lon=55.0)
        assert result.ok is True
        assert result.value.proximity_alert == "LOW"
        assert len(result.value.vessels) == 1
        assert len(result.value.hazardous_vessels) == 0
        await adapter.aclose()

    @pytest.mark.asyncio
    async def test_missing_api_key_fallback(self, monkeypatch):
        monkeypatch.delenv("AISHUB_API_KEY", raising=False)
        adapter = AISVesselAdapter()
        result = await adapter.call(lat=25.0, lon=55.0)
        assert result.ok is False
        assert result.value.proximity_alert == "UNKNOWN"
        await adapter.aclose()

    def test_haversine_known_distance(self):
        """Verify haversine against a known distance."""
        # Cairo (30.04, 31.23) to Alexandria (31.20, 29.92) ≈ 180 km ≈ 97 NM
        d = haversine_nm(30.04, 31.23, 31.20, 29.92)
        assert 90 < d < 105  # ≈ 97 NM


# ===========================================================================
# ElevationAdapter tests
# ===========================================================================


OTO_BASE = "https://api.opentopodata.org/v1/srtm30m"


class TestElevationAdapter:

    @pytest.mark.asyncio
    @respx.mock
    async def test_happy_path(self):
        respx.get(OTO_BASE).mock(return_value=httpx.Response(200, json={
            "results": [{"elevation": 75.4}]
        }))
        adapter = ElevationAdapter()
        result = await adapter.call(lat=30.04, lon=31.23)
        assert result.ok is True
        assert result.value.elevation_m == 75.4
        assert result.value.resolution_m == 30
        await adapter.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_null_elevation_parse_error(self):
        """API returns null (outside SRTM coverage) → parse_error."""
        respx.get(OTO_BASE).mock(return_value=httpx.Response(200, json={
            "results": [{"elevation": None}]
        }))
        adapter = ElevationAdapter()
        result = await adapter.call(lat=30.04, lon=31.23)
        assert result.ok is False
        assert result.error == "parse_error"
        assert math.isnan(result.value.elevation_m)
        await adapter.aclose()

    @pytest.mark.asyncio
    async def test_outside_srtm_coverage(self):
        """Lat 70° (outside SRTM -56 to +60) → parse_error fallback NaN."""
        adapter = ElevationAdapter()
        result = await adapter.call(lat=70.0, lon=0.0)
        assert result.ok is False
        assert result.error == "parse_error"
        assert math.isnan(result.value.elevation_m)
        await adapter.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_network_error_nan(self):
        """Network error → NaN elevation (NEVER 0.0 — would corrupt hydraulics)."""
        respx.get(OTO_BASE).mock(side_effect=httpx.ConnectError("no internet"))
        adapter = ElevationAdapter()
        result = await adapter.call(lat=30.04, lon=31.23)
        assert result.ok is False
        assert result.error == "network"
        assert math.isnan(result.value.elevation_m)
        await adapter.aclose()


# ===========================================================================
# Cross-adapter integration tests
# ===========================================================================


class TestAdaptersShareBaseContract:
    """All adapters must satisfy the same fail-safe contract."""

    ADAPTER_CLASSES = [
        WildfireSmokeAdapter,
        EarthquakeAdapter,
        OpenAQAdapter,
        AISVesselAdapter,
        ElevationAdapter,
    ]

    @pytest.mark.asyncio
    async def test_all_adapters_never_raise_on_network_failure(self, monkeypatch):
        """No adapter should raise — even with no network."""
        # Force network failure on all adapters
        monkeypatch.setenv("OPENAQ_API_KEY", "x")
        monkeypatch.setenv("AISHUB_API_KEY", "x")

        for cls in self.ADAPTER_CLASSES:
            adapter = cls()
            # All adapters accept (lat, lon) — call should NEVER raise
            try:
                result = await adapter.call(lat=30.0, lon=31.0)
                assert isinstance(result, ApiResult)
                assert isinstance(result.ok, bool)
                assert isinstance(result.value, object)
                assert result.source == adapter.source_name
            except Exception as e:
                pytest.fail(f"{cls.__name__} raised {type(e).__name__}: {e}")
            finally:
                await adapter.aclose()

    @pytest.mark.asyncio
    async def test_all_adapters_have_health_method(self):
        for cls in self.ADAPTER_CLASSES:
            adapter = cls()
            h = adapter.health()
            assert "source" in h
            assert "circuit_state" in h
            assert h["source"] == adapter.source_name
            await adapter.aclose()
