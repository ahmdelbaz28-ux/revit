"""
marine/__init__.py — Marine Fire Safety & Ship Electrical Module
=================================================================
V130 MARINE MODULE (2026-06-18): Dedicated package for ship/marine fire
protection engineering per IMO SOLAS Chapter II-2, IEC 60092 series,
ISO 15370, Lloyd's Register Rules, and NFPA 302.

This package is the marine counterpart to ``fireai/`` (which targets
buildings per NFPA 72/13). The two packages share the same FastAPI
backend (``backend/routers/marine.py``) and the same integration
bridges (Revit, AutoCAD, SCADA, ETAP).

Subpackages:
    core/         — Domain types, constants, errors (single source of truth)
    solas/        — IMO SOLAS Chapter II-2 compliance engine
    iec60092/     — IEC 60092-502 (fire detection) & 60092-504 (dangerous goods)
    iso15370/     — ISO 15370 thermal alarms (passenger ships)
    lr_rules/     — Lloyd's Register Rules for Fire Protection
    nfpa302/      — NFPA 302 (small craft fire protection)
    engine/       — Core engines: zone_mapper, detector_selector,
                    fire_resistance, extinguishment, alarm_logic, ship_power
    integration/  — SCADA (MQTT/OPC-UA/Modbus), ETAP, Revit, AutoCAD bridges
    output/       — DXF generator, BOM generator, test procedures
    tests/        — Unit + property-based tests

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

__version__ = "1.0.0"
__all__ = ["__version__"]
