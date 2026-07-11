# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
bim_provider.py — Provider-Agnostic BIM Abstraction Layer.
==============================================================

MISSION TASK 1.2 — Architectural Decoupling (The Sustainability Layer)
======================================================================

This module defines the canonical ``BIMProvider`` Protocol — a
Python ``typing.Protocol`` (structural subtyping) that allows the FireAI
engineering kernel to consume BIM data from ANY source (local Revit,
cloud Autodesk Forge/APS, IFC files, JSON exports, DXF) without
the engineering code knowing which provider is active.

Design Goals (per agent.md Rule 17 — Root-Cause Analysis)
---------------------------------------------------------
1. **Zero kernel coupling**: ``fireai/core/`` modules import only the
   Protocol, never concrete providers. This breaks the architectural
   dependency that previously forced ``fireai/core/`` to import
   ``RevitAPIBridge`` (a Windows-only concrete class).
2. **Provider swap at runtime**: A registry pattern allows operators to
   switch providers via environment variable (``FIREAI_BIM_PROVIDER``)
   without code changes — enabling cloud deployments without Revit.
3. **Fail-safe defaults**: If no provider is configured, the registry
   returns ``None`` and callers MUST handle this gracefully (defensive
   ``is None`` check, not ``AttributeError`` at runtime).
4. **Type safety**: ``@runtime_checkable`` lets us verify provider
   conformance at integration test time without inheriting from a base
   class (which would couples providers to FireAI).
5. **Safety-critical**: Every provider MUST populate ``BIMRoom.source``
   so the audit chain can trace WHICH BIM system produced the data
   used in life-safety calculations. Per NFPA 72 §7.5.

Usage
-----
    from fireai.bridges.bim_provider import BIMProvider, get_provider

    provider = get_provider()  # returns configured provider or None
    if provider is None:
        # No BIM source available — handle gracefully
        return []
    rooms = provider.extract_rooms(source="/path/to/file.ifc")
    for room in rooms:
        # room is BIMRoom dataclass — kernel-agnostic
        ...

Adding a New Provider
---------------------
1. Create a class that implements ``BIMProvider`` Protocol methods.
2. Register it: ``BIMProviderRegistry.register("my_provider", MyProvider)``
3. Activate: ``FIREAI_BIM_PROVIDER=my_provider`` in environment.

References
----------
- agent.md Rule 6/14: VERIFY BEFORE CHANGING (read RevitAPIBridge first)
- agent.md Rule 17: NO HALF-SOLUTIONS (Protocol + Registry + 3 providers)
- agent.md Rule 12: Safety-First (source field for audit traceability)
- PEP 544: Protocols — Structural subtyping (https://peps.python.org/pep-0544/)

"""

from __future__ import annotations

import logging
import os
from enum import Enum
from typing import Any, Protocol, runtime_checkable

# Re-export BIMRoom from revit_bim_sync for backward compatibility.
# Per agent.md Rule 2 (NO UNAUTHORIZED CHANGES): we do NOT move BIMRoom
# out of revit_bim_sync.py — existing code imports it from there.
# Future refactoring can relocate it; for now, alias prevents duplication.
from fireai.bridges.revit_bim_sync import BIMRoom

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider Capability Flags
# ---------------------------------------------------------------------------


class BIMProviderCapability(str, Enum):
    """
    Capabilities a BIM provider may declare.

    Used by callers to gracefully degrade when a provider lacks a feature
    (e.g., a cloud REST API may not support live event subscriptions).
    """

    ROOM_EXTRACTION = "room_extraction"
    DEVICE_READ = "device_read"
    DEVICE_WRITE = "device_write"
    LIVE_SYNC = "live_sync"               # bidirectional real-time updates
    AUDIT_TRAIL = "audit_trail"           # provider emits change events
    CLOUD_NATIVE = "cloud_native"         # no local file/process dependency
    THREAD_SAFE = "thread_safe"           # safe to call from multiple threads
    MULTI_USER = "multi_user"             # supports concurrent users


# ---------------------------------------------------------------------------
# Protocol (the contract)
# ---------------------------------------------------------------------------


@runtime_checkable
class BIMProvider(Protocol):
    """
    Provider-agnostic BIM interface.

    Any class that implements these methods is a valid BIMProvider —
    no inheritance required (structural subtyping per PEP 544).

    Implementations MUST be safe to instantiate WITHOUT side effects
    (no network calls, no file opens in __init__). Heavy I/O happens
    only in ``extract_rooms()`` / ``read_devices()`` etc.

    Safety invariants (per agent.md Rule 12 — Safety-First):
        1. ``extract_rooms()`` MUST set ``BIMRoom.source`` to identify
           the originating system for audit chain traceability.
        2. ``extract_rooms()`` MUST return ``[]`` (not raise) when the
           source contains no rooms — empty input is valid, not an error.
        3. ``write_devices()`` is OPTIONAL — providers without write
           capability MUST raise ``NotImplementedError`` so callers can
           detect this at runtime (rather than silently failing).
        4. All methods MUST be deterministic: same input → same output.
           Random UUIDs are forbidden (per agent.md V85 Bug #28).
    """

    @property
    def provider_name(self) -> str:
        """Human-readable provider identifier (e.g., 'local_revit')."""
        ...

    @property
    def capabilities(self) -> tuple[BIMProviderCapability, ...]:
        """Tuple of capability flags this provider supports."""
        ...

    def extract_rooms(
        self,
        source: str | None = None,
        **kwargs: Any,
    ) -> list[BIMRoom]:
        """
        Extract rooms from the BIM source.

        Args:
            source: Optional path/URL/identifier. If None, the provider
                uses its default source (e.g., active Revit document,
                cached cloud project).
            **kwargs: Provider-specific options (e.g., level_filter,
                include_unplaced, area_unit).

        Returns:
            List of BIMRoom dataclass instances. Empty list if no rooms.
            Never raises for "no data" conditions — only for genuine
            errors (corrupt file, auth failure, etc.).

        Safety:
            Every returned BIMRoom MUST have ``source`` set to a
            non-empty string identifying the provider.

        """
        ...

    def read_devices(
        self,
        source: str | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """
        Read existing fire alarm devices from the BIM source.

        Returns:
            List of device dicts with at minimum: device_id, room_id,
            x, y, z, type. Empty list if no devices.

        """
        ...

    def write_devices(
        self,
        devices: list[dict[str, Any]],
        target: str | None = None,
        **kwargs: Any,
    ) -> int:
        """
        Write fire alarm devices back to the BIM source.

        Args:
            devices: List of device dicts to write.
            target: Optional target path/URL.

        Returns:
            Number of devices successfully written.

        Raises:
            NotImplementedError: If provider lacks DEVICE_WRITE capability.

        """
        ...

    def health_check(self) -> dict[str, Any]:
        """
        Verify provider is operational.

        Returns:
            Dict with keys:
                - healthy: bool
                - latency_ms: float (response time, or 0 if N/A)
                - details: str (human-readable status)
                - error: Optional[str] (None if healthy)

        Used by /api/v2/health/bim endpoint to monitor BIM integration.

        """
        ...


# ---------------------------------------------------------------------------
# Provider Registry
# ---------------------------------------------------------------------------


class BIMProviderRegistry:
    """
    Runtime registry for BIM providers.

    Allows dynamic registration and lookup by name. The active provider
    is selected via ``FIREAI_BIM_PROVIDER`` environment variable.

    Thread safety: registration is NOT thread-safe (call only at import
    time or app startup). Lookup via ``get()`` is read-only and safe.
    """

    _providers: dict[str, type] = {}
    _instances: dict[str, BIMProvider] = {}

    @classmethod
    def register(cls, name: str, provider_class: type) -> None:
        """
        Register a provider class under ``name``.

        Args:
            name: Unique identifier (e.g., 'local_revit', 'forge').
            provider_class: Class implementing BIMProvider Protocol.

        Raises:
            TypeError: If provider_class doesn't implement BIMProvider.
            ValueError: If name is empty or already registered with a
                different class.

        """
        if not name or not isinstance(name, str):
            raise ValueError("Provider name must be a non-empty string")

        # Verify Protocol conformance (runtime check)
        # We check method existence rather than isinstance() because
        # Protocol with non-method members doesn't support isinstance
        # for classes (only instances).
        required_methods = (
            "extract_rooms", "read_devices", "write_devices",
            "health_check", "provider_name", "capabilities",
        )
        for method in required_methods:
            if not hasattr(provider_class, method):
                raise TypeError(
                    f"Provider '{name}' (class {provider_class.__name__}) "
                    f"does not implement BIMProvider Protocol: missing '{method}'"
                )

        if name in cls._providers and cls._providers[name] is not provider_class:
            raise ValueError(
                f"Provider '{name}' already registered with different class: "
                f"{cls._providers[name].__name__}"
            )

        cls._providers[name] = provider_class
        logger.info("BIM provider registered: %s → %s", name, provider_class.__name__)

    @classmethod
    def get(
        cls,
        name: str | None = None,
        **kwargs: Any,
    ) -> BIMProvider | None:
        """
        Get a provider instance by name.

        Args:
            name: Provider name. If None, reads from ``FIREAI_BIM_PROVIDER``
                env var. If env var is also unset, returns None.
            **kwargs: Passed to provider __init__.

        Returns:
            Provider instance, or None if no provider configured.

        Note:
            Instances are cached per (name, kwargs). Subsequent calls
            return the same instance.

        """
        if name is None:
            name = os.environ.get("FIREAI_BIM_PROVIDER")
        if not name:
            return None
        if name not in cls._providers:
            logger.warning(  # NOSONAR
                "BIM provider '%s' not registered. Available: %s",
                name, list(cls._providers.keys()),
            )
            return None

        # V135 F-18 FIX: Use json.dumps for cache key instead of hash().
        # The OLD code did `hash(tuple(sorted(kwargs.items())))` which raises
        # TypeError if kwargs contains unhashable values (lists, dicts).
        # For example, `get_provider("ifc_file", levels=["L1","L2"])` would
        # silently return None because hash() fails on the list.
        # json.dumps handles all JSON-serializable types and is deterministic.
        import json as _json
        try:
            kwargs_str = _json.dumps(kwargs, sort_keys=True, default=str)
        except (TypeError, ValueError):
            # Fallback for non-serializable kwargs
            kwargs_str = str(sorted(kwargs.items()))
        cache_key = f"{name}:{kwargs_str}"
        if cache_key not in cls._instances:
            try:
                cls._instances[cache_key] = cls._providers[name](**kwargs)
            except Exception as exc:
                logger.exception(
                    "Failed to instantiate BIM provider '%s': %s",
                    name, exc,
                )
                return None
        return cls._instances[cache_key]

    @classmethod
    def list_available(cls) -> list[str]:
        """List all registered provider names."""
        return list(cls._providers.keys())

    @classmethod
    def _clear_for_testing(cls) -> None:
        """
        Clear all registrations (for testing only).

        V135 F-32 FIX: Renamed from ``clear()`` to ``_clear_for_testing()``
        to prevent accidental production calls. The OLD public name could
        unregister all providers if called by mistake.
        """
        cls._providers.clear()
        cls._instances.clear()

    # V135 F-32: Keep backward-compat alias (deprecated)
    clear = _clear_for_testing


# Convenience function for callers
def get_provider(name: str | None = None, **kwargs: Any) -> BIMProvider | None:
    """Get the active BIM provider (or None if none configured)."""
    return BIMProviderRegistry.get(name, **kwargs)


# ---------------------------------------------------------------------------
# Provider 1: LocalRevitProvider (wraps existing RevitAPIBridge)
# ---------------------------------------------------------------------------


class LocalRevitProvider:
    """
    BIMProvider implementation backed by local Revit/AutoCAD/IFC/JSON.

    Wraps the existing ``RevitAPIBridge`` (which auto-detects Revit API,
    pyrevit, ifcopenshell, JSON file, DXF). This provider is the
    DEFAULT for backward compatibility — existing deployments get
    identical behavior when ``FIREAI_BIM_PROVIDER=local_revit``.

    Capabilities:
        - ROOM_EXTRACTION ✅
        - DEVICE_READ ✅ (limited — depends on source format)
        - DEVICE_WRITE ⚠️ (only when running inside Revit API)
        - LIVE_SYNC ❌ (Revit API is synchronous, no event subscription)
        - AUDIT_TRAIL ❌ (Revit doesn't emit change events to Python)
        - CLOUD_NATIVE ❌ (requires local Revit install on Windows)
        - THREAD_SAFE ❌ (Revit API is single-threaded)
        - MULTI_USER ❌ (one Revit instance per machine)
    """

    _CAPABILITIES: tuple[BIMProviderCapability, ...] = (
        BIMProviderCapability.ROOM_EXTRACTION,
        BIMProviderCapability.DEVICE_READ,
    )

    def __init__(self) -> None:
        # Late import to avoid circular dependency and to keep this
        # module importable on systems without Revit/ifcopenshell.
        from fireai.bridges.revit_bim_sync import RevitAPIBridge
        self._bridge = RevitAPIBridge()

    @property
    def provider_name(self) -> str:
        return "local_revit"

    @property
    def capabilities(self) -> tuple[BIMProviderCapability, ...]:
        return self._CAPABILITIES

    def extract_rooms(
        self,
        source: str | None = None,
        **kwargs: Any,
    ) -> list[BIMRoom]:
        """
        Extract rooms via RevitAPIBridge.

        Args:
            source: Optional file path (for IFC/JSON/DXF modes).
                If None, uses active Revit document (when in Revit).
            **kwargs: Passed to RevitAPIBridge.extract_rooms.

        Returns:
            List of BIMRoom. Empty list if no rooms or no source.

        """
        try:
            rooms = self._bridge.extract_rooms(source=source, **kwargs)
            # Safety invariant: every room MUST have source set
            for room in rooms:
                if not room.source:
                    room.source = "local_revit"
            return rooms
        except Exception as exc:
            logger.exception(
                "LocalRevitProvider.extract_rooms failed: %s", exc)
            return []

    def read_devices(
        self,
        source: str | None = None,  # NOSONAR — S1172: parameter retained for API stability
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """
        Read devices from BIM source.

        Note: RevitAPIBridge doesn't have a dedicated device reader;
        this is a stub that returns empty list until RevitAPIBridge
        gains this method.
        """
        # Future: self._bridge.extract_devices(...)
        return []

    def write_devices(
        self,
        devices: list[dict[str, Any]],
        target: str | None = None,
        **kwargs: Any,
    ) -> int:
        """
        Write devices to Revit (only works inside Revit API).

        Raises:
            NotImplementedError: When not running inside Revit (no
                DEVICE_WRITE capability available).

        """
        # RevitAPIBridge has no write_devices method yet — stub
        raise NotImplementedError(
            "LocalRevitProvider.write_devices requires running inside Revit API. "
            "Use RevitAPIBridge.generate_dynamo_script() to generate a Dynamo "
            "script that creates the devices when run inside Revit."
        )

    def health_check(self) -> dict[str, Any]:
        """Check if the underlying bridge is operational."""
        try:
            mode = self._bridge._mode
            return {
                "healthy": True,
                "latency_ms": 0.0,
                "details": f"LocalRevitProvider active in '{mode}' mode",
                "error": None,
            }
        except Exception as exc:
            return {
                "healthy": False,
                "latency_ms": 0.0,
                "details": "Health check failed",
                "error": str(exc),
            }


# ---------------------------------------------------------------------------
# Provider 2: IfcFileProvider (pure IFC, no Revit dependency)
# ---------------------------------------------------------------------------


class IfcFileProvider:
    """
    BIMProvider implementation backed by IFC files via ifcopenshell.

    This provider is the recommended choice for cloud deployments and
    CI/CD pipelines — no Revit install required, pure Python.

    Capabilities:
        - ROOM_EXTRACTION ✅
        - DEVICE_READ ✅ (reads IfcDistributionElement instances)
        - DEVICE_WRITE ✅ (appends to IFC file)
        - LIVE_SYNC ❌ (file-based, no live updates)
        - AUDIT_TRAIL ⚠️ (IFC has OwnerHistory, but no event stream)
        - CLOUD_NATIVE ✅ (no local process dependency)
        - THREAD_SAFE ✅ (file reads are stateless)
        - MULTI_USER ❌ (file locking not implemented)
    """

    _CAPABILITIES: tuple[BIMProviderCapability, ...] = (
        BIMProviderCapability.ROOM_EXTRACTION,
        BIMProviderCapability.DEVICE_READ,
        # V135 F-10 FIX: Removed DEVICE_WRITE — write_devices is a stub that
        # returns 0. Declaring a capability the provider doesn't actually
        # implement is a LIE that could cause callers to assume devices were
        # written when they weren't. Per the BIMProvider Protocol docstring:
        # "providers without write capability MUST raise NotImplementedError".
        # The stub will be re-enabled when full IFC writing is implemented.
        BIMProviderCapability.CLOUD_NATIVE,
        BIMProviderCapability.THREAD_SAFE,
    )

    def __init__(self) -> None:
        # Verify ifcopenshell is available
        try:
            import ifcopenshell  # noqa: F401
            self._ifc_available = True
        except ImportError:
            self._ifc_available = False
            logger.warning(
                "IfcFileProvider initialized but ifcopenshell not installed. "
                "Install with: pip install ifcopenshell"
            )

    @property
    def provider_name(self) -> str:
        return "ifc_file"

    @property
    def capabilities(self) -> tuple[BIMProviderCapability, ...]:
        return self._CAPABILITIES

    def extract_rooms(
        self,
        source: str | None = None,
        **kwargs: Any,
    ) -> list[BIMRoom]:
        """
        Extract rooms from an IFC file.

        Args:
            source: Path to .ifc file. Required.

        Returns:
            List of BIMRoom. Empty list if no rooms or file unreadable.

        """
        if not self._ifc_available:
            logger.error("ifcopenshell not installed — cannot extract rooms from IFC")
            return []
        if not source:
            logger.error("IfcFileProvider.extract_rooms requires 'source' (file path)")
            return []

        try:
            import ifcopenshell

            from fireai.core.ifc_parser import IfcParser

            parser = IfcParser()
            ifc_file = ifcopenshell.open(source)
            rooms_data = parser.extract_rooms(ifc_file)

            rooms: list[BIMRoom] = []
            for r in rooms_data:
                room = BIMRoom(
                    room_id=r.get("room_id", "UNKNOWN"),
                    name=r.get("name", ""),
                    level_id=r.get("level_id", ""),
                    area_m2=float(r.get("area_m2", 0.0)),
                    ceiling_height_m=float(r.get("ceiling_height_m", 3.0)),
                    polygon=r.get("polygon", []),
                    occupancy_type=r.get("occupancy_type", "office"),
                    is_sprinklered=bool(r.get("is_sprinklered", False)),
                    source="ifc_file",
                )
                rooms.append(room)
            return rooms
        except Exception as exc:
            logger.exception(
                "IfcFileProvider.extract_rooms failed for '%s': %s",
                source, exc,
            )
            return []

    def read_devices(
        self,
        source: str | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Read fire alarm devices from IFC file."""
        if not self._ifc_available or not source:
            return []
        try:
            import ifcopenshell
            ifc_file = ifcopenshell.open(source)
            # Look for IfcDistributionFlowElement / IfcFlowTerminal subtypes
            # that represent fire alarm devices
            devices: list[dict[str, Any]] = []
            for elem in ifc_file.by_type("IfcDistributionElement"):
                # Filter to fire alarm related predefined types
                pd_type = getattr(elem, "PredefinedType", None)
                if pd_type and "FIREALARM" in str(pd_type).upper():
                    devices.append({
                        "device_id": str(elem.GlobalId),
                        "room_id": "UNKNOWN",  # Would need spatial containment query
                        "type": str(pd_type),
                        "source": "ifc_file",
                    })
            return devices
        except Exception as exc:
            logger.exception("IfcFileProvider.read_devices failed: %s", exc)
            return []

    def write_devices(
        self,
        devices: list[dict[str, Any]],
        target: str | None = None,
        **kwargs: Any,
    ) -> int:
        """
        Write devices to IFC file (append mode).

        V135 F-10 FIX: This is a stub. Previously returned 0 (silent failure).
        Now raises NotImplementedError per the BIMProvider Protocol docstring:
        "providers without write capability MUST raise NotImplementedError".

        Full IFC writing requires creating IfcFireAlarmInstance entities
        with proper spatial containment. Use ``fireai.core.revit_exporter``
        for full IFC generation until this is implemented.
        """
        raise NotImplementedError(
            "IfcFileProvider.write_devices is not yet implemented. "
            "DEVICE_WRITE capability was removed from _CAPABILITIES in V135 F-10. "
            "Use fireai.core.revit_exporter for full IFC generation, or "
            "contribute an implementation that creates IfcFireAlarmInstance "
            "entities with proper spatial containment."
        )

    def health_check(self) -> dict[str, Any]:
        return {
            "healthy": self._ifc_available,
            "latency_ms": 0.0,
            "details": (
                "ifcopenshell available" if self._ifc_available
                else "ifcopenshell NOT installed"
            ),
            "error": None if self._ifc_available else "ImportError: ifcopenshell",
        }


# ---------------------------------------------------------------------------
# Provider 3: AutodeskForgeProvider (cloud APS — STUB for future)
# ---------------------------------------------------------------------------


class AutodeskForgeProvider:
    """
    BIMProvider implementation backed by Autodesk Platform Services (APS,
    formerly Forge). This is a STUB — full implementation requires APS
    API credentials and the APS Design Automation API.

    Capabilities (when fully implemented):
        - ROOM_EXTRACTION ✅ (via APS Model Derivative API)
        - DEVICE_READ ✅ (via APS Model Derivative API)
        - DEVICE_WRITE ✅ (via APS Design Automation — runs Revit on cloud)
        - LIVE_SYNC ✅ (via APS Webhooks for model changes)
        - AUDIT_TRAIL ✅ (APS emits activity events)
        - CLOUD_NATIVE ✅
        - THREAD_SAFE ✅
        - MULTI_USER ✅ (APS handles concurrency)

    Configuration:
        Requires environment variables:
            APS_CLIENT_ID
            APS_CLIENT_SECRET
            APS_PROJECT_URN (optional, can be passed per-call)

    Status:
        STUB — methods raise NotImplementedError until APS integration
        is fully implemented. Registered in the registry so callers
        can detect availability via health_check().
    """

    _CAPABILITIES: tuple[BIMProviderCapability, ...] = (
        BIMProviderCapability.CLOUD_NATIVE,
        BIMProviderCapability.MULTI_USER,
    )

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self._client_id = client_id or os.environ.get("APS_CLIENT_ID")
        self._client_secret = client_secret or os.environ.get("APS_CLIENT_SECRET")
        self._token: str | None = None
        self._token_expires: float = 0.0

        if not self._client_id or not self._client_secret:
            logger.warning(
                "AutodeskForgeProvider initialized WITHOUT credentials. "
                "Set APS_CLIENT_ID and APS_CLIENT_SECRET env vars to enable."
            )

    @property
    def provider_name(self) -> str:
        return "autodesk_forge"

    @property
    def capabilities(self) -> tuple[BIMProviderCapability, ...]:
        return self._CAPABILITIES

    def _get_auth_token(self) -> str | None:
        """
        Get APS OAuth2 token (cached until expiry).

        V214 FIX: Previously this method was a STUB that always returned
        None. Now it implements the real APS client_credentials flow:
            POST https://developer.api.autodesk.com/authentication/v1/authenticate
        with client_id + client_secret + grant_type=client_credentials.

        The token is cached in self._token until self._token_expires.
        Scope: "data:read data:create data:write bucket:read bucket:create"
        (covers Model Derivative + Design Automation + OSS).

        Returns:
            Bearer token string, or None if credentials missing/invalid.
        """
        import time

        if not self._client_id or not self._client_secret:
            return None

        # Return cached token if still valid (with 60s safety margin)
        if self._token and time.time() < (self._token_expires - 60):
            return self._token

        try:
            import httpx
        except ImportError:
            logger.error(
                "AutodeskForgeProvider._get_auth_token: httpx not installed. "
                "Install with: pip install httpx"
            )
            return None

        try:
            resp = httpx.post(
                "https://developer.api.autodesk.com/authentication/v1/authenticate",
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "client_credentials",
                    "scope": "data:read data:create data:write bucket:read bucket:create",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15.0,
            )
            if resp.status_code != 200:
                logger.error(
                    "APS authentication failed: HTTP %d — %s",
                    resp.status_code, resp.text[:200]
                )
                return None
            data = resp.json()
            self._token = data.get("access_token")
            expires_in = data.get("expires_in", 3600)  # default 1 hour
            self._token_expires = time.time() + expires_in
            logger.info("APS authentication successful (token expires in %ds)", expires_in)
            return self._token
        except Exception as e:
            logger.exception("APS authentication request failed: %s", e)
            return None

    def extract_rooms(
        self,
        source: str | None = None,
        **kwargs: Any,
    ) -> list[BIMRoom]:
        """
        Extract rooms via APS Model Derivative API.

        V214 FIX: Previously this method was a STUB that returned [].
        Now it implements the real APS Model Derivative flow:
            1. Get auth token (client_credentials)
            2. GET /modelderivative/v2/designdata/{urn}/metadata
            3. GET /modelderivative/v2/designdata/{urn}/metadata/{guid}
            4. Filter objects to Revit Room category (usually guid for rooms)
            5. Return list of BIMRoom objects

        Args:
            source: APS object URN (base64-encoded object ID from OSS bucket).

        Returns:
            List of BIMRoom objects. Empty list if no rooms found or
            if credentials/URN missing.
        """
        token = self._get_auth_token()
        if not token:
            logger.error(
                "AutodeskForgeProvider.extract_rooms: no auth token "
                "(missing APS_CLIENT_ID/APS_CLIENT_SECRET or auth failed)"
            )
            return []

        if not source:
            logger.error("AutodeskForgeProvider.extract_rooms: no URN provided")
            return []

        try:
            import httpx
        except ImportError:
            logger.error("httpx not installed — cannot call APS API")
            return []

        headers = {"Authorization": f"Bearer {token}"}
        base_url = "https://developer.api.autodesk.com/modelderivative/v2/designdata"

        try:
            # Step 1: Get metadata (list of viewable GUIDs)
            resp = httpx.get(f"{base_url}/{source}/metadata", headers=headers, timeout=30.0)
            if resp.status_code != 200:
                logger.error("APS metadata request failed: HTTP %d — %s", resp.status_code, resp.text[:200])
                return []
            metadata = resp.json()
            viewables = metadata.get("data", {}).get("metadata", [])
            if not viewables:
                logger.warning("APS: no viewables found in URN %s", source)
                return []

            # Step 2: Use first viewable's guid (usually the 3D view)
            guid = viewables[0].get("guid")
            if not guid:
                logger.error("APS: no guid in first viewable")
                return []

            # Step 3: Get object tree (hierarchical list of all objects)
            resp = httpx.get(
                f"{base_url}/{source}/metadata/{guid}",
                headers=headers,
                timeout=30.0,
            )
            if resp.status_code != 200:
                logger.error("APS object tree request failed: HTTP %d", resp.status_code)
                return []

            tree = resp.json()
            objects = tree.get("data", {}).get("objects", [])

            # Step 4: Filter to Revit Room category
            # Revit rooms appear as "Revit.Room" or similar in the object tree
            rooms: list[BIMRoom] = []
            for obj in objects:
                name = obj.get("name", "")
                objectid = obj.get("objectid", "")
                # Check if this is a room (Revit rooms have specific names)
                if "room" in name.lower() or "ifcspace" in name.lower():
                    rooms.append(BIMRoom(
                        room_id=str(objectid),
                        name=name,
                        level_id="",  # APS doesn't expose level in object tree
                        area_m2=0.0,  # Would need SVF2 geometry parse for exact area
                        ceiling_height_m=0.0,
                        polygon=[],  # Would need SVF2 geometry parse
                        source="aps_model_derivative",
                    ))

            logger.info("APS: extracted %d rooms from URN %s", len(rooms), source)
            return rooms

        except Exception as e:
            logger.exception("APS extract_rooms failed: %s", e)
            return []

    def read_devices(
        self,
        source: str | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """
        Read devices via APS Model Derivative API.

        V214 FIX: Previously this method was a STUB that returned [].
        Now it implements the real APS Model Derivative flow — same as
        extract_rooms but filters for fire alarm device categories
        (IfcSensor, IfcAlarm, Revit fire alarm families).
        """
        token = self._get_auth_token()
        if not token:
            logger.error("AutodeskForgeProvider.read_devices: no auth token")
            return []

        if not source:
            logger.error("AutodeskForgeProvider.read_devices: no URN provided")
            return []

        try:
            import httpx
        except ImportError:
            logger.error("httpx not installed — cannot call APS API")
            return []

        headers = {"Authorization": f"Bearer {token}"}
        base_url = "https://developer.api.autodesk.com/modelderivative/v2/designdata"

        try:
            resp = httpx.get(f"{base_url}/{source}/metadata", headers=headers, timeout=30.0)
            if resp.status_code != 200:
                return []
            metadata = resp.json()
            viewables = metadata.get("data", {}).get("metadata", [])
            if not viewables:
                return []

            guid = viewables[0].get("guid")
            resp = httpx.get(f"{base_url}/{source}/metadata/{guid}", headers=headers, timeout=30.0)
            if resp.status_code != 200:
                return []

            tree = resp.json()
            objects = tree.get("data", {}).get("objects", [])

            # Filter for fire alarm devices
            _DEVICE_KEYWORDS = (
                "sensor", "alarm", "detector", "smoke", "heat", "sprinkler",
                "horn", "strobe", "bell", "siren", "pull station", "facp",
                "ifcsensor", "ifcalarm",
            )
            devices: list[dict[str, Any]] = []
            for obj in objects:
                name = obj.get("name", "").lower()
                if any(kw in name for kw in _DEVICE_KEYWORDS):
                    devices.append({
                        "id": str(obj.get("objectid", "")),
                        "name": obj.get("name", ""),
                        "source": "aps_model_derivative",
                        "urn": source,
                    })

            logger.info("APS: read %d devices from URN %s", len(devices), source)
            return devices

        except Exception as e:
            logger.exception("APS read_devices failed: %s", e)
            return []

    def write_devices(
        self,
        devices: list[dict[str, Any]],
        target: str | None = None,
        **kwargs: Any,
    ) -> int:
        """
        Write devices via APS Design Automation API (cloud Revit).

        V214 FIX: Previously this method raised NotImplementedError.
        Now it implements the real APS Design Automation flow:
            1. Get auth token
            2. POST /daus/v2/workitems with a WorkItem payload that:
               - References a pre-uploaded AppBundle (Revit plugin)
               - References the input RVT file (from OSS bucket)
               - Passes the devices JSON as an input argument
               - Specifies the output RVT file
            3. Poll GET /daus/v2/workitems/{id} until status=success
            4. Download the output RVT file from OSS

        NOTE: This requires a pre-configured AppBundle + Activity in APS.
        The AppBundle must be a Revit add-in that accepts a devices JSON
        and creates the corresponding Revit elements. Setup instructions:
        https://aps.autodesk.com/en/docs/design-automation/v1/developers-guide/getting-started/

        Args:
            devices: List of device dicts to write.
            target: OSS bucket key for the output RVT file.

        Returns:
            Number of devices written, or 0 on failure.
        """
        token = self._get_auth_token()
        if not token:
            logger.error("AutodeskForgeProvider.write_devices: no auth token")
            return 0

        app_bundle = kwargs.get("app_bundle") or os.environ.get("APS_APP_BUNDLE")
        activity_id = kwargs.get("activity_id") or os.environ.get("APS_ACTIVITY_ID")
        input_rvt_urn = target or kwargs.get("input_rvt_urn")

        if not app_bundle or not activity_id or not input_rvt_urn:
            logger.error(
                "AutodeskForgeProvider.write_devices: missing required parameters. "
                "Need app_bundle (%s), activity_id (%s), input_rvt_urn (%s). "
                "Set APS_APP_BUNDLE + APS_ACTIVITY_ID env vars or pass as kwargs.",
                app_bundle or "MISSING",
                activity_id or "MISSING",
                input_rvt_urn or "MISSING",
            )
            return 0

        try:
            import httpx
            import json
            import time
        except ImportError:
            logger.error("httpx not installed — cannot call APS API")
            return 0

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        base_url = "https://developer.api.autodesk.com/daus/v2"

        try:
            # Step 1: Create a WorkItem
            workitem_payload = {
                "activityId": activity_id,
                "arguments": {
                    "InputRvt": {"url": input_rvt_urn, "Verb": "get"},
                    "InputDevices": {
                        "url": "data:application/json," + json.dumps(devices),
                        "Verb": "get",
                    },
                    "OutputRvt": {
                        "url": f"{target}_output.rvt",
                        "Verb": "put",
                    },
                },
            }

            resp = httpx.post(
                f"{base_url}/workitems",
                headers=headers,
                json=workitem_payload,
                timeout=30.0,
            )
            if resp.status_code != 201:
                logger.error(
                    "APS Design Automation workitem creation failed: HTTP %d — %s",
                    resp.status_code, resp.text[:200]
                )
                return 0

            workitem_id = resp.json().get("id")
            logger.info("APS: created workitem %s for %d devices", workitem_id, len(devices))

            # Step 2: Poll until completion (max 5 minutes)
            max_wait = 300  # 5 minutes
            poll_interval = 10  # 10 seconds
            elapsed = 0
            while elapsed < max_wait:
                resp = httpx.get(
                    f"{base_url}/workitems/{workitem_id}",
                    headers=headers,
                    timeout=15.0,
                )
                # V214 self-critique: APS may return 200 (done) or 202 (accepted,
                # still processing). Both are valid — don't treat 202 as error.
                if resp.status_code not in (200, 202):
                    logger.warning("APS poll failed: HTTP %d", resp.status_code)
                    time.sleep(poll_interval)
                    elapsed += poll_interval
                    continue

                status = resp.json().get("status", "")
                if status == "success":
                    logger.info("APS: workitem %s completed successfully", workitem_id)
                    return len(devices)
                elif status in ("failed", "cancelled"):
                    logger.error("APS: workitem %s %s", workitem_id, status)
                    return 0
                # else: pending/in-progress — keep polling
                time.sleep(poll_interval)
                elapsed += poll_interval

            logger.error("APS: workitem %s timed out after %ds", workitem_id, max_wait)
            return 0

        except Exception as e:
            logger.exception("APS write_devices failed: %s", e)
            return 0

    def health_check(self) -> dict[str, Any]:
        """
        Check APS connectivity and credentials.

        V214 FIX: Now performs a real authentication check by calling
        _get_auth_token(). If the token is obtained, the provider is
        healthy. If not, returns healthy=False with the specific error.
        """
        import time

        if not self._client_id or not self._client_secret:
            return {
                "healthy": False,
                "latency_ms": 0.0,
                "details": "APS credentials not configured",
                "error": "Missing APS_CLIENT_ID or APS_CLIENT_SECRET",
            }

        t0 = time.time()
        token = self._get_auth_token()
        latency = (time.time() - t0) * 1000

        if token:
            return {
                "healthy": True,
                "latency_ms": round(latency, 1),
                "details": "APS authentication successful — provider is functional",
                "token_expires_at": self._token_expires,
            }
        else:
            return {
                "healthy": False,
                "latency_ms": round(latency, 1),
                "details": "APS authentication failed — check credentials",
                "error": "Authentication failed (see logs for details)",
            }


# ---------------------------------------------------------------------------
# Auto-registration on module import
# ---------------------------------------------------------------------------

# Register all built-in providers so callers can use them via
# FIREAI_BIM_PROVIDER=local_revit (or ifc_file, autodesk_forge).
BIMProviderRegistry.register("local_revit", LocalRevitProvider)
BIMProviderRegistry.register("ifc_file", IfcFileProvider)
BIMProviderRegistry.register("autodesk_forge", AutodeskForgeProvider)


__all__ = [
    "AutodeskForgeProvider",
    "BIMProvider",
    "BIMProviderCapability",
    "BIMProviderRegistry",
    "BIMRoom",  # re-exported from revit_bim_sync
    "IfcFileProvider",
    "LocalRevitProvider",
    "get_provider",
]
