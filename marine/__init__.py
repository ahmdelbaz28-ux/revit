"""
marine/__init__.py — Marine Fire Safety & Ship Electrical Module
=================================================================
V130 MARINE MODULE (2026-06-18): Dedicated package for ship/marine fire
protection engineering per IMO SOLAS Chapter II-2, IEC 60092 series,
ISO 15370, Lloyd's Register Rules, and NFPA 302.

V2.0 (2026-06-19): 18 bug fixes (5 CRITICAL, 12 HIGH, 1 MEDIUM) including:
  - Valid IEC 61131-3 PLC script generation (was unparseable)
  - Correct inert-gas purge formula (logarithmic, not linear — was 14× low)
  - CO2 safety factor + alternative-method max (was 25% under-supplied)
  - Non-overlapping main vertical zones (was overlapping up to 15 m)
  - Passenger-ship 24 m MVZ limit (SOLAS II-2/2.2.1.1 — was 40 m uniform)
  - New size_foam_high_expansion() and size_afff() (were missing entirely)
  - dataclasses.replace() in assign_space_categories (was dropping 4 fields)
  - Proper DXF SECTION/EOF wrappers + longitudinally-offset zones
  - ETAP UPS load in kW (was kWh labelled as kW)
  - SCADA dashboard timestamp parameter (was hardcoded)
  - Per-type Modbus register widths (BOOL/INT/REAL/STRING)
  - 37 new regression tests in marine/tests/test_marine_regression_v2.py

This package is the marine counterpart to ``fireai/`` (which targets
buildings per NFPA 72/13). The two packages share the same FastAPI
backend (``backend/routers/marine.py``) and the same integration
bridges (Revit, AutoCAD, SCADA, ETAP).

Subpackages:
    core/         — Domain types, constants, errors (single source of truth)
    solas/        — IMO SOLAS Chapter II-2 compliance engine
    iec60092/     — IEC 60092-502 (fire detection) & 60092-504 (dangerous goods)
                    (also: electrical_installations for IEC 60092-3xx ship power)
    iso15370/     — ISO 15370 thermal alarms (passenger ships)
    lr_rules/     — Lloyd's Register Rules for Fire Protection
    nfpa302/      — NFPA 302 (small craft fire protection)
    engine/       — Core engines: zone_mapper, fire_resistance,
                    extinguishment, alarm_logic
                    (detector selection lives in iec60092/part_502.py;
                     ship power lives in iec60092/electrical_installations.py)
    integration/  — SCADA (MQTT/OPC-UA/Modbus), ETAP, Revit, AutoCAD bridges
    tests/        — Unit + property-based + regression tests

Standards Reference:
    - IMO SOLAS Ch. II-2 (2024 amendments) — Construction: Fire protection,
      detection, extinction
    - IEC 60092-502:1999 — Electrical installations in ships: Tankers
    - IEC 60092-504 — Electrical installations: Ships carrying dangerous goods
    - ISO 15370:2001 — Thermal alarms for passenger ships
    - Lloyd's Register Rules for Fire Protection, Detection & Extinguishment
    - NFPA 302-2020 — Fire Protection for Craft and Small Commercial Vessels
    - IMO MSC.1/Circ.1316 — CO2 total flooding system guidelines
    - IMO MSC.1/Circ.1165 — Water mist fire-extinguishing system guidelines
    - IMO FSS Code Ch. 9 — Fixed fire detection and fire alarm systems
"""

from __future__ import annotations

__version__ = "2.0.0"
__all__ = ["__version__"]
