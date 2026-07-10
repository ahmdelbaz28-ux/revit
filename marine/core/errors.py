"""
marine/core/errors.py — Marine Module Exceptions
=================================================
Centralized exception hierarchy. Distinct from fireai/core/errors.py to
keep the marine domain model self-contained.
"""

from __future__ import annotations


class MarineError(Exception):
    """Base exception for all marine-module errors."""


class InvalidShipTypeError(MarineError):
    """Raised when an unsupported ShipType is used for an operation."""


class SOLASComplianceError(MarineError):
    """Raised when a design violates SOLAS II-2 requirements."""


class IEC60092ComplianceError(MarineError):
    """Raised when electrical design violates IEC 60092 series."""


class InsufficientDataError(MarineError):
    """Raised when required ship/zone data is missing for an engine."""


class ExtinguishingDesignError(MarineError):
    """
    Raised when extinguishing-system sizing fails (insufficient data,
    impossible geometry, etc.).
    """


class FireClassAssignmentError(MarineError):
    """Raised when fire-division class cannot be determined from SOLAS matrix."""


class HazardousZoneError(MarineError):
    """Raised when a hazardous-zone rule is violated (e.g. Zone 0 release)."""
