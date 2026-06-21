"""
Tests for backend/services/report_service.py

P2.3: Tests for the extracted report business logic.
"""

import pytest
from backend.services.report_service import (
    ALARM_DEVICE_TYPES,
    ALARM_CATEGORIES,
    count_by_category,
    classify_device_load,
    calculate_battery_capacity,
    generate_voltage_drop_report,
    generate_nfpa72_coverage_report,
    generate_nfpa72_battery_report,
    generate_cable_sizing_report,
    generate_generic_report,
    generate_report,
)


class TestCountByCategory:
    def test_empty_list(self):
        assert count_by_category([]) == {}

    def test_single_category(self):
        devices = [{"category": "FIRE_ALARM"}, {"category": "FIRE_ALARM"}]
        assert count_by_category(devices) == {"FIRE_ALARM": 2}

    def test_multiple_categories(self):
        devices = [
            {"category": "FIRE_ALARM"},
            {"category": "SECURITY"},
            {"category": "FIRE_ALARM"},
            {"category": "CCTV"},
        ]
        result = count_by_category(devices)
        assert result == {"FIRE_ALARM": 2, "SECURITY": 1, "CCTV": 1}

    def test_missing_category_defaults_to_unknown(self):
        devices = [{"name": "dev1"}]  # no category key
        assert count_by_category(devices) == {"unknown": 1}


class TestClassifyDeviceLoad:
    def test_alarm_device_type(self):
        device = {"type": "FA_HORN", "load": 0.5, "category": "FIRE_ALARM"}
        load, role = classify_device_load(device)
        assert load == 0.5
        assert role == "alarm"

    def test_standby_device_type(self):
        device = {"type": "FA_SMOKE_DETECTOR", "load": 0.05, "category": "FIRE_ALARM"}
        load, role = classify_device_load(device)
        assert load == 0.05
        assert role == "standby"

    def test_pa_system_alarm(self):
        device = {"type": "PA_CEILING_SPEAKER", "load": 0.3, "category": "PA_SYSTEM"}
        load, role = classify_device_load(device)
        assert role == "alarm"

    def test_pa_amplifier_is_standby(self):
        device = {"type": "PA_AMPLIFIER", "load": 1.0, "category": "PA_SYSTEM"}
        load, role = classify_device_load(device)
        assert role == "standby"

    def test_legacy_notification_category(self):
        device = {"type": "UNKNOWN", "load": 0.2, "category": "notification"}
        load, role = classify_device_load(device)
        assert role == "alarm"

    def test_missing_load_defaults_to_zero(self):
        device = {"type": "FA_HORN", "category": "FIRE_ALARM"}
        load, role = classify_device_load(device)
        assert load == 0.0
        assert role == "alarm"


class TestCalculateBatteryCapacity:
    def test_empty_devices(self):
        result = calculate_battery_capacity([])
        assert result["requiredAh"] == 0.0
        assert result["standbyLoadA"] == 0.0
        assert result["alarmLoadA"] == 0.0

    def test_only_standby_devices(self):
        devices = [
            {"type": "FA_SMOKE_DETECTOR", "load": 0.05, "category": "FIRE_ALARM"},
            {"type": "FA_HEAT_DETECTOR", "load": 0.03, "category": "FIRE_ALARM"},
        ]
        result = calculate_battery_capacity(devices)
        # (0.08 * 24 + 0) / 0.80 = 2.4
        assert result["standbyLoadA"] == 0.08
        assert result["alarmLoadA"] == 0.0
        assert result["requiredAh"] == 2.4

    def test_only_alarm_devices(self):
        """BUG-29: System with only horns/strobes still needs battery."""
        devices = [
            {"type": "FA_HORN", "load": 2.0, "category": "FIRE_ALARM"},
            {"type": "FA_STROBE", "load": 1.5, "category": "FIRE_ALARM"},
        ]
        result = calculate_battery_capacity(devices)
        # (0 * 24 + 3.5 * 0.25) / 0.80 = 1.09375
        assert result["standbyLoadA"] == 0.0
        assert result["alarmLoadA"] == 3.5
        assert result["requiredAh"] == pytest.approx(1.094, abs=0.01)

    def test_mixed_devices(self):
        devices = [
            {"type": "FA_SMOKE_DETECTOR", "load": 0.5, "category": "FIRE_ALARM"},
            {"type": "FA_HORN", "load": 2.0, "category": "FIRE_ALARM"},
        ]
        result = calculate_battery_capacity(devices)
        # (0.5 * 24 + 2.0 * 0.25) / 0.80 = 15.625
        assert result["standbyLoadA"] == 0.5
        assert result["alarmLoadA"] == 2.0
        assert result["requiredAh"] == pytest.approx(15.625, abs=0.01)

    def test_custom_durations(self):
        devices = [{"type": "FA_SMOKE_DETECTOR", "load": 1.0, "category": "FIRE_ALARM"}]
        result = calculate_battery_capacity(
            devices, standby_hours=60.0, alarm_minutes=5.0, derating_factor=0.85
        )
        # (1.0 * 60 + 0 * 5/60) / 0.85 = 70.588
        assert result["standbyHours"] == 60.0
        assert result["alarmMinutes"] == 5.0
        assert result["deratingFactor"] == 0.85
        assert result["requiredAh"] == pytest.approx(70.588, abs=0.01)

    def test_safety_warning_present(self):
        result = calculate_battery_capacity([])
        assert "safetyWarning" in result
        assert "Amperes" in result["safetyWarning"]


class TestGenerateReports:
    def test_voltage_drop_report(self):
        devices = [
            {"id": "d1", "name": "Panel", "load": 0, "voltage": 24},
            {"id": "d2", "name": "Detector", "load": 0.05, "voltage": 24},
        ]
        connections = [
            {"id": "c1", "fromId": "d1", "toId": "d2", "cableSize": "14", "length": 50},
        ]
        result = generate_voltage_drop_report(devices, connections)
        assert result["type"] == "voltage_drop"
        assert result["totalCircuits"] == 1
        assert len(result["circuits"]) == 1
        assert result["circuits"][0]["from"] == "Panel"
        assert result["circuits"][0]["to"] == "Detector"

    def test_nfpa72_coverage_report(self):
        devices = [
            {"category": "FIRE_ALARM"},
            {"category": "FIRE_ALARM"},
            {"category": "SECURITY"},
        ]
        result = generate_nfpa72_coverage_report(devices)
        assert result["type"] == "nfpa72_coverage"
        assert result["totalDevices"] == 3
        assert result["devicesByCategory"]["FIRE_ALARM"] == 2

    def test_nfpa72_battery_report(self):
        devices = [{"type": "FA_HORN", "load": 2.0, "category": "FIRE_ALARM"}]
        result = generate_nfpa72_battery_report(devices)
        assert result["type"] == "nfpa72_battery"
        assert result["standard"] == "NFPA 72-2022 §27.6.2"
        assert result["alarmLoadA"] == 2.0

    def test_cable_sizing_report(self):
        connections = [
            {"id": "c1", "cableSize": "14", "length": 50, "type": "FA"},
        ]
        result = generate_cable_sizing_report(connections)
        assert result["type"] == "cable_sizing"
        assert result["totalConnections"] == 1

    def test_generic_report(self):
        devices = [{"category": "FIRE_ALARM"}]
        connections = [{"id": "c1"}]
        result = generate_generic_report("custom_report", devices, connections)
        assert result["type"] == "custom_report"
        assert result["totalDevices"] == 1
        assert result["totalConnections"] == 1


class TestGenerateReportDispatch:
    def test_dispatches_to_voltage_drop(self):
        result = generate_report("voltage_drop", [], [])
        assert result["type"] == "voltage_drop"

    def test_dispatches_to_nfpa72_coverage(self):
        result = generate_report("nfpa72_coverage", [], [])
        assert result["type"] == "nfpa72_coverage"

    def test_dispatches_to_nfpa72_battery(self):
        result = generate_report("nfpa72_battery", [], [])
        assert result["type"] == "nfpa72_battery"

    def test_dispatches_to_cable_sizing(self):
        result = generate_report("cable_sizing", [], [{"id": "c1", "cableSize": "14", "length": 10, "type": "FA"}])
        assert result["type"] == "cable_sizing"

    def test_dispatches_to_generic_for_unknown_type(self):
        result = generate_report("unknown_type", [], [])
        assert result["type"] == "unknown_type"
        assert result["standard"] == "General Engineering Analysis"


class TestAlarmDeviceTypes:
    def test_alarm_device_types_is_frozenset(self):
        assert isinstance(ALARM_DEVICE_TYPES, frozenset)

    def test_alarm_categories_is_frozenset(self):
        assert isinstance(ALARM_CATEGORIES, frozenset)

    def test_known_alarm_types_present(self):
        assert "FA_HORN" in ALARM_DEVICE_TYPES
        assert "FA_STROBE" in ALARM_DEVICE_TYPES
        assert "FA_SOUND_STROBE" in ALARM_DEVICE_TYPES
        assert "PA_CEILING_SPEAKER" in ALARM_DEVICE_TYPES
