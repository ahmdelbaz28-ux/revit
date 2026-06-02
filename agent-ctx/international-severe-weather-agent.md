# Task: Add International Severe Weather Alert Support

## Summary

Added MeteoAlarm EU integration and international dispatch logic to the `SevereWeatherService`, plus `coverage_area` and `coverage_note` fields to the API responses.

## Changes Made

### 1. `backend/services/severe_weather_service.py`

**New Constants:**
- `METEOALARM_COUNTRY_CODES` — frozenset of 31 EU/EEA country codes supported by MeteoAlarm
- `_ISO_TO_METEOALARM` — mapping for ISO→MeteoAlarm code differences (e.g., UK vs GB)
- `_METEOALARM_TYPE_MAP` — MeteoAlarm alert type codes → event name mapping (13 types)

**New/Extended Data:**
- `WeatherAlertSeverity.METEOALARM_SEVERITY_MAP` — Maps Red/Orange/Yellow/Green → Extreme/Severe/Moderate/Minor
- `WeatherAlertType` — Added MeteoAlarm-specific types (Wind, Rain, Snow/Ice, Thunderstorm, Fog, Coastal, Forest Fire, Avalanche, High/Low Temperature)
- `SevereWeatherData.coverage_area` — New field: "us", "eu", "global", or "none"
- `WeatherAlert.affects_fire_safety` — Expanded keyword list (added "fire", "temperature", "avalanche", "fog", "coastal", "rain")

**New Methods:**
- `_is_us_location()` — Bounding box check for US NWS coverage (lat 24-50, lon -125 to -66)
- `_determine_coverage()` — Dispatch logic: US→"us", EU bbox→"eu", else→"global"
- `_fetch_meteoalarm_alerts()` — Main MeteoAlarm method with JSON→Atom fallback chain
- `_fetch_meteoalarm_json()` — Parse MeteoAlarm JSON API v1 response
- `_parse_meteoalarm_warning()` — Convert single MeteoAlarm warning dict → WeatherAlert
- `_fetch_meteoalarm_atom()` — Fallback: Parse Atom XML feed with CAP entries
- `_parse_meteoalarm_atom_entry()` — Convert single Atom entry → WeatherAlert
- `_fetch_openmeteo_alerts()` — Global fallback using WMO weather codes
- `_resolve_country_code()` — Reverse geocode to get ISO country code for MeteoAlarm dispatch
- `_get_default()` — Extended with `coverage_area` parameter

**Modified Methods:**
- `fetch_severe_weather()` — Complete rewrite of dispatch logic: US→NWS, EU→MeteoAlarm, Global→Open-Meteo, all with proper fallback chains
- `_fetch_nws_alerts()` — Now sets `coverage_area="us"` in returned data
- `_get_default()` — Now accepts `coverage_area` parameter

**Preserved:**
- Public API signature of `fetch_severe_weather()` unchanged
- Singleton pattern unchanged
- Caching pattern (TTL 600s) unchanged
- `@retry` pattern from tenacity on both `_fetch_nws_alerts` and `_fetch_meteoalarm_alerts`
- All existing NWS functionality untouched

### 2. `backend/routers/environment.py`

**New Function:**
- `_build_coverage_note(coverage_area, source)` — Generates human-readable coverage note based on location/source. Provides actionable guidance for when no alert source is available, with NFPA references.

**Modified Endpoints:**
- `GET /severe-weather` — Added `coverage_area` and `coverage_note` to response data
- `GET /full-context` — Added `coverage_area` and `coverage_note` to severe_weather section

**Coverage Notes (4 scenarios):**
1. Source available: Informational note confirming coverage
2. US but NWS unreachable: Check weather.gov, NFPA 72 §10.6 guidance
3. EU but MeteoAlarm unreachable: Check meteoalarm.org, EN 54-13 reference
4. Global/none: Check local met service, conservative NFPA assumptions

## Verification

- `python -c "import backend.services.severe_weather_service"` — PASS
- Coverage dispatch tested: NYC→"us", Paris→"eu", Dubai→"global", Tokyo→"global"
- MeteoAlarm country codes: 31 EU/EEA countries verified
- Coverage note generation: All 6 scenarios tested
- SevereWeatherData.coverage_area field: Verified in dataclass fields
- Default data with coverage_area: Verified correct propagation

## Safety Compliance

- All external API failures fall back to conservative defaults ✓
- Internal error details never exposed to client ✓
- Wrong alert data is conservative (assume alerts present) ✓
- All new code has docstrings with NFPA references ✓
- All external API calls and failures are logged ✓
- Existing NWS functionality NOT broken ✓
- `@retry` pattern applied to MeteoAlarm fetch ✓
- Caching pattern maintained (TTL 600s) ✓
