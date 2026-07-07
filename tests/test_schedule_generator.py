# NOSONAR
"""
tests/test_schedule_generator.py
==================================
Tests for fireai.core.schedule_generator (cable schedule output).

Covers system requirement §4:
  Schedule: Device_ID, From_Location, To_Location, Length, Type, Voltage_Drop
  Report:   Total cable length, bends, max circuit length

References: NFPA 72 §23.6.2, NEC 760.24(A)
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fireai.core.schedule_generator import (
    _NFPA72_23_6_2_MAX_LEN_M,
    ScheduleGenerator,
    ScheduleRow,
)


@pytest.fixture
def sg():
    return ScheduleGenerator()


@pytest.fixture
def sample_rows():
    return [
        ScheduleRow("FACP->SD-01", "(0,0,0)", "(5,0,2.7)", 5.2, '14 AWG in 3/4" RED EMT',
                    0.043, 23.957, 1, True),
        ScheduleRow("FACP->SD-02", "(0,0,0)", "(5,5,2.7)", 7.8, '14 AWG in 3/4" RED EMT',
                    0.065, 23.935, 2, True),
        ScheduleRow("FACP->SD-03", "(0,0,0)", "(0,10,2.7)", 1600.0, '14 AWG in 3/4" RED EMT',
                    13.3, 10.7, 0, False),  # Non-compliant long circuit
    ]


class TestScheduleGeneratorCSV:
    def test_csv_has_header_columns(self, sg, sample_rows):
        csv = sg.to_csv(sample_rows)
        assert "Device_ID" in csv
        assert "From_Location" in csv
        assert "To_Location" in csv
        assert "Length_m" in csv
        assert "Voltage_Drop_V" in csv

    def test_csv_row_count(self, sg, sample_rows):
        csv = sg.to_csv(sample_rows)
        lines = [l for l in csv.strip().splitlines() if l]
        assert len(lines) == 4  # header + 3 routes

    def test_csv_compliance_column(self, sg, sample_rows):
        csv = sg.to_csv(sample_rows)
        assert "YES" in csv   # compliant routes
        assert "NO" in csv    # non-compliant route

    def test_csv_code_refs_column(self, sg, sample_rows):
        csv = sg.to_csv(sample_rows)
        assert "NFPA72" in csv

    def test_empty_csv(self, sg):
        csv = sg.to_csv([])
        lines = [l for l in csv.strip().splitlines() if l]
        assert len(lines) == 1  # header only


class TestScheduleReport:
    def test_report_totals(self, sg, sample_rows):
        rep = sg.to_report(sample_rows)
        assert rep.route_count == 3
        assert rep.total_cable_length_m == pytest.approx(5.2 + 7.8 + 1600.0)
        assert rep.total_bends == 1 + 2 + 0

    def test_report_not_all_compliant(self, sg, sample_rows):
        rep = sg.to_report(sample_rows)
        assert not rep.all_compliant
        assert rep.violations_count == 1

    def test_report_min_voltage(self, sg, sample_rows):
        rep = sg.to_report(sample_rows)
        assert rep.min_end_voltage_v == pytest.approx(10.7)

    def test_report_max_circuit(self, sg, sample_rows):
        rep = sg.to_report(sample_rows)
        assert rep.max_circuit_length_m == pytest.approx(1600.0)

    def test_report_nfpa72_limits(self, sg, sample_rows):
        rep = sg.to_report(sample_rows)
        assert "14 AWG" in rep.nfpa72_limits
        assert rep.nfpa72_limits["14 AWG"] == pytest.approx(1524.0)

    def test_report_code_refs(self, sg, sample_rows):
        rep = sg.to_report(sample_rows)
        refs = " ".join(rep.code_refs)
        assert "NFPA 72" in refs
        assert "NEC" in refs

    def test_empty_report(self, sg):
        rep = sg.to_report([])
        assert rep.route_count == 0
        assert rep.total_cable_length_m == 0.0  # NOSONAR — S1244: import retained for re-export / API surface
        # V97 FIX: Empty schedule reports all_compliant=False (fail-safe)
        assert not rep.all_compliant

    def test_single_route_report(self, sg):
        rows = [ScheduleRow("A->B","(0,0)","(1,0)", 50.0, "14 AWG", 0.41, 23.59, 0, True)]
        rep = sg.to_report(rows)
        assert rep.route_count == 1
        assert rep.max_circuit_length_m == pytest.approx(50.0)


class TestScheduleJSON:
    def test_json_output(self, sg, sample_rows):
        import json
        j = sg.to_json(sample_rows)
        data = json.loads(j)
        assert "schedule" in data
        assert "report" in data
        assert len(data["schedule"]) == 3

    def test_json_compliant_field(self, sg, sample_rows):
        import json
        j = sg.to_json(sample_rows)
        data = json.loads(j)
        assert data["report"]["violations_count"] == 1


class TestScheduleTextReport:
    def test_text_report_has_totals(self, sg, sample_rows):
        text = sg.to_text_report(sample_rows)
        assert "Total Routes" in text
        assert "Total Cable Length" in text
        assert "Max Circuit Length" in text

    def test_text_report_violation_flag(self, sg, sample_rows):
        text = sg.to_text_report(sample_rows)
        assert "VIOLATION" in text or "NO" in text.upper()

    def test_text_report_code_refs(self, sg, sample_rows):
        text = sg.to_text_report(sample_rows)
        assert "NFPA" in text
        assert "NEC" in text


class TestNFPA72Limits:
    """NFPA 72 §23.6.2 limits are correctly defined."""

    def test_12awg_limit(self):
        assert _NFPA72_23_6_2_MAX_LEN_M["12 AWG"] == pytest.approx(2286.0)

    def test_14awg_limit(self):
        assert _NFPA72_23_6_2_MAX_LEN_M["14 AWG"] == pytest.approx(1524.0)

    def test_16awg_limit(self):
        assert _NFPA72_23_6_2_MAX_LEN_M["16 AWG"] == pytest.approx(914.0)

    def test_18awg_limit(self):
        assert _NFPA72_23_6_2_MAX_LEN_M["18 AWG"] == pytest.approx(610.0)
