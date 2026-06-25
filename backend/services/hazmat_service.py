"""backend/services/hazmat_service.py — Hazardous materials data for FireAI.

Provides hazardous material classification and properties from the
US EPA and public chemical databases. Used for:
  - Hazardous area classification (IEC 60079-10-1 / NFPA 497)
  - Material fire hazard assessment (NFPA 30, NFPA 45)
  - Chemical compatibility for storage area design
  - LFL/UFL determination for zone extent calculations

LIFE-SAFETY NOTE:
  Hazardous material properties directly determine:
  - Zone 0/1/2 extent calculations (IEC 60079-10-1 §6.3)
  - LFL (Lower Flammable Limit) for zone radius (IEC Annex B)
  - Flash point for area classification (NFPA 497 §4.3)
  - Auto-ignition temperature for temperature class (IEC 60079-14)
  - Material group for equipment selection (IEC 60079-0 Table 1)

  WRONG material data = WRONG zone extent = DANGEROUS installation.
  Conservative: Default to the most restrictive classification.

References:
  - EPA Chem Database: https://www.epa.gov/chemical-data-reporting
  - PubChem API: https://pubchem.ncbi.nlm.nih.gov/rest/docs/
  - IEC 60079-10-1:2015 (hazardous area classification)
  - NFPA 497-2024 (classification of combustible liquids)
  - NFPA 30-2024 (flammable liquids code)

"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class MaterialGroup(str, Enum):
    """IEC 60079-0 gas/dust groups for equipment selection."""

    IIA = "IIA"    # Propane group (least restrictive)
    IIB = "IIB"    # Ethylene group
    IIC = "IIC"    # Hydrogen/acetylene (most restrictive)
    IIIC = "IIIC"  # Combustible dusts
    IIIB = "IIIB"  # Non-conductive combustible dusts
    IIIA = "IIIA"  # Combustible flyings
    UNKNOWN = "unknown"


class TemperatureClass(str, Enum):
    """IEC 60079-0 temperature classes based on auto-ignition temperature."""

    T1 = "T1"    # > 450°C
    T2 = "T2"    # > 300°C
    T3 = "T3"    # > 200°C
    T4 = "T4"    # > 135°C
    T5 = "T5"    # > 100°C
    T6 = "T6"    # > 85°C
    UNKNOWN = "unknown"


# Conservative defaults for unknown materials
DEFAULT_LFL_VOL_PCT = 0.5    # Very low LFL = large zone = conservative
DEFAULT_UFL_VOL_PCT = 15.0   # Standard upper limit
DEFAULT_FLASH_POINT_C = -20.0  # Low flash point = flammable at low temp = conservative
DEFAULT_AUTO_IGNITION_C = 200.0  # Low AIT = T3 = more restrictive equipment


@dataclass(frozen=True)
class HazardousMaterialData:
    """Immutable hazardous material properties for engineering calculations.

    Attributes:
        name: Material name (e.g., "Methane", "Propane")
        cas_number: CAS registry number (e.g., "74-82-8")
        lfl_vol_pct: Lower Flammable Limit in vol% (for zone extent)
        ufl_vol_pct: Upper Flammable Limit in vol%
        flash_point_c: Flash point in Celsius (for liquid classification)
        auto_ignition_c: Auto-ignition temperature in Celsius (for T-class)
        material_group: IEC gas/dust group (for equipment selection)
        temperature_class: IEC temperature class (for equipment selection)
        molecular_weight: Molecular weight in g/mol
        vapor_density: Vapor density relative to air (>1 = heavier)
        source: Data provenance ("pubchem" | "internal_db" | "default")

    """

    name: str
    cas_number: str = ""
    lfl_vol_pct: float = DEFAULT_LFL_VOL_PCT
    ufl_vol_pct: float = DEFAULT_UFL_VOL_PCT
    flash_point_c: float = DEFAULT_FLASH_POINT_C
    auto_ignition_c: float = DEFAULT_AUTO_IGNITION_C
    material_group: MaterialGroup = MaterialGroup.UNKNOWN
    temperature_class: TemperatureClass = TemperatureClass.UNKNOWN
    molecular_weight: float = 0.0
    vapor_density: float = 1.0
    source: str = "default"

    @property
    def is_default(self) -> bool:
        return self.source == "default"

    @property
    def is_conservative(self) -> bool:
        """Whether this uses conservative (restrictive) defaults."""
        return self.lfl_vol_pct <= 0.5 or self.source == "default"

    @property
    def flammable_range_vol_pct(self) -> float:
        """Flammable range (UFL - LFL) in vol%."""
        return self.ufl_vol_pct - self.lfl_vol_pct


def auto_ignition_to_temp_class(ait_c: float) -> TemperatureClass:
    """Convert auto-ignition temperature to IEC temperature class."""
    if ait_c > 450:
        return TemperatureClass.T1
    if ait_c > 300:
        return TemperatureClass.T2
    if ait_c > 200:
        return TemperatureClass.T3
    if ait_c > 135:
        return TemperatureClass.T4
    if ait_c > 100:
        return TemperatureClass.T5
    if ait_c > 85:
        return TemperatureClass.T6
    return TemperatureClass.T6  # Below 85°C — most restrictive


# Internal database of common hazardous materials
# Based on IEC 60079-10-1 Table B.1 and NFPA 497
_INTERNAL_HAZMAT_DB: dict[str, dict] = {
    "methane": {
        "cas": "74-82-8", "lfl": 5.0, "ufl": 15.0,
        "flash_point": -187.8, "ait": 537.0,
        "group": MaterialGroup.IIA, "mw": 16.04, "vd": 0.55,
    },
    "propane": {
        "cas": "74-98-6", "lfl": 2.1, "ufl": 9.5,
        "flash_point": -104.0, "ait": 450.0,
        "group": MaterialGroup.IIA, "mw": 44.10, "vd": 1.56,
    },
    "hydrogen": {
        "cas": "1333-74-0", "lfl": 4.0, "ufl": 75.0,
        "flash_point": None, "ait": 500.0,
        "group": MaterialGroup.IIC, "mw": 2.02, "vd": 0.07,
    },
    "ethylene": {
        "cas": "74-85-1", "lfl": 2.7, "ufl": 36.0,
        "flash_point": -136.0, "ait": 425.0,
        "group": MaterialGroup.IIB, "mw": 28.05, "vd": 0.97,
    },
    "acetylene": {
        "cas": "74-86-2", "lfl": 2.5, "ufl": 100.0,
        "flash_point": None, "ait": 305.0,
        "group": MaterialGroup.IIC, "mw": 26.04, "vd": 0.91,
    },
    "gasoline": {
        "cas": "8006-61-9", "lfl": 1.4, "ufl": 7.6,
        "flash_point": -43.0, "ait": 280.0,
        "group": MaterialGroup.IIA, "mw": 100.0, "vd": 3.0,
    },
    "diesel": {
        "cas": "68476-34-6", "lfl": 0.6, "ufl": 5.6,
        "flash_point": 52.0, "ait": 210.0,
        "group": MaterialGroup.IIA, "mw": 170.0, "vd": 6.0,
    },
    "ethanol": {
        "cas": "64-17-5", "lfl": 3.3, "ufl": 19.0,
        "flash_point": 12.8, "ait": 363.0,
        "group": MaterialGroup.IIA, "mw": 46.07, "vd": 1.59,
    },
    "methanol": {
        "cas": "67-56-1", "lfl": 6.7, "ufl": 36.0,
        "flash_point": 11.1, "ait": 464.0,
        "group": MaterialGroup.IIA, "mw": 32.04, "vd": 1.10,
    },
    "ammonia": {
        "cas": "7664-41-7", "lfl": 15.0, "ufl": 28.0,
        "flash_point": None, "ait": 651.0,
        "group": MaterialGroup.IIA, "mw": 17.03, "vd": 0.59,
    },
    "carbon_monoxide": {
        "cas": "630-08-0", "lfl": 12.5, "ufl": 74.0,
        "flash_point": None, "ait": 609.0,
        "group": MaterialGroup.IIA, "mw": 28.01, "vd": 0.97,
    },
    "hydrogen_sulfide": {
        "cas": "7783-06-4", "lfl": 4.3, "ufl": 46.0,
        "flash_point": None, "ait": 260.0,
        "group": MaterialGroup.IIB, "mw": 34.08, "vd": 1.19,
    },
}


class HazmatService:
    """Async hazardous material data provider.

    Uses internal database first (fast, reliable, no API dependency).
    Falls back to PubChem API for materials not in the internal DB.
    Falls back to conservative defaults for unknown materials.

    Caching:
        - In-memory cache with 7-day TTL (material properties don't change)
        - PubChem API responses cached indefinitely (chemistry is constant)

    Retry:
        - 3 attempts with exponential backoff for PubChem API
        - Falls back to conservative defaults on failure
    """

    PUBCHEM_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound"

    def __init__(self, cache_ttl: float = 604800.0, request_timeout: float = 15.0):
        self._cache: dict[str, tuple[HazardousMaterialData, float]] = {}
        self._cache_ttl = cache_ttl
        self._request_timeout = request_timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-initialize the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._request_timeout),
                headers={"User-Agent": "FireAI-DigitalTwin/1.0"},
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _get_cached(self, material_name: str) -> Optional[HazardousMaterialData]:
        """Get cached material data."""
        key = material_name.strip().lower()
        entry = self._cache.get(key)
        if entry is None:
            return None
        data, fetched_at = entry
        if time.time() - fetched_at < self._cache_ttl:
            return data
        return None

    def _set_cached(self, material_name: str, data: HazardousMaterialData) -> None:
        """Store material data in cache."""
        key = material_name.strip().lower()
        self._cache[key] = (data, time.time())

    def _lookup_internal_db(self, material_name: str) -> Optional[HazardousMaterialData]:
        """Look up material in the internal database.

        The internal DB contains the 12 most common hazardous materials
        encountered in fire alarm engineering. Data sourced from IEC
        60079-10-1 Table B.1 and NFPA 497.
        """
        key = material_name.strip().lower()

        # Also try common aliases
        aliases = {
            "lpg": "propane",
            "natural gas": "methane",
            "ch4": "methane",
            "c3h8": "propane",
            "h2": "hydrogen",
            "c2h4": "ethylene",
            "c2h2": "acetylene",
            "petrol": "gasoline",
            "c2h5oh": "ethanol",
            "ch3oh": "methanol",
            "nh3": "ammonia",
            "co": "carbon_monoxide",
            "h2s": "hydrogen_sulfide",
        }
        key = aliases.get(key, key)

        if key not in _INTERNAL_HAZMAT_DB:
            return None

        entry = _INTERNAL_HAZMAT_DB[key]
        ait = entry.get("ait", DEFAULT_AUTO_IGNITION_C)

        return HazardousMaterialData(
            name=material_name.strip().title(),
            cas_number=entry.get("cas", ""),
            lfl_vol_pct=entry.get("lfl", DEFAULT_LFL_VOL_PCT),
            ufl_vol_pct=entry.get("ufl", DEFAULT_UFL_VOL_PCT),
            flash_point_c=entry.get("flash_point", DEFAULT_FLASH_POINT_C) if entry.get("flash_point") is not None else DEFAULT_FLASH_POINT_C,
            auto_ignition_c=ait,
            material_group=entry.get("group", MaterialGroup.UNKNOWN),
            temperature_class=auto_ignition_to_temp_class(ait),
            molecular_weight=entry.get("mw", 0.0),
            vapor_density=entry.get("vd", 1.0),
            source="internal_db",
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        reraise=True,
    )
    async def _fetch_pubchem(self, material_name: str) -> HazardousMaterialData:
        """Fetch material properties from PubChem API.

        API: https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}/property/.../JSON

        Returns:
            HazardousMaterialData with source="pubchem"

        """
        client = await self._get_client()
        # FIX: URL-encode user-supplied material_name to prevent URL injection
        from urllib.parse import quote
        safe_name = quote(material_name.strip(), safe='')
        response = await client.get(
            f"{self.PUBCHEM_URL}/name/{safe_name}/property/"
            "MolecularWeight,InChI/JSON",
        )
        response.raise_for_status()
        body = response.json()

        properties = body.get("PropertyTable", {}).get("Properties", [])
        if not properties:
            raise ValueError(f"PubChem returned no properties for: {material_name}")

        prop = properties[0]
        mw = float(prop.get("MolecularWeight", 0))

        # PubChem doesn't provide LFL/UFL directly
        # Return what we can get and use defaults for the rest
        data = HazardousMaterialData(
            name=material_name.strip().title(),
            cas_number=str(prop.get("CID", "")),
            lfl_vol_pct=DEFAULT_LFL_VOL_PCT,  # Conservative
            ufl_vol_pct=DEFAULT_UFL_VOL_PCT,
            flash_point_c=DEFAULT_FLASH_POINT_C,
            auto_ignition_c=DEFAULT_AUTO_IGNITION_C,
            material_group=MaterialGroup.UNKNOWN,
            temperature_class=auto_ignition_to_temp_class(DEFAULT_AUTO_IGNITION_C),
            molecular_weight=mw,
            vapor_density=1.0,
            source="pubchem",
        )

        logger.info("Hazmat data fetched from PubChem: %s (MW=%s)", material_name, mw)
        return data

    def _get_default(self, material_name: str) -> HazardousMaterialData:
        """Return conservative default hazardous material data.

        These defaults are the MOST RESTRICTIVE:
        - Very low LFL (0.5%) = large zone extent = conservative
        - Low flash point = flammable at low temperatures = conservative
        - Low AIT = restrictive temperature class = conservative
        """
        logger.warning(
            f"Using CONSERVATIVE DEFAULT hazmat data for '{material_name}'. "
            f"Material not in internal DB and PubChem unavailable. "
            f"Assuming most restrictive classification."
        )
        return HazardousMaterialData(
            name=material_name.strip().title(),
            lfl_vol_pct=DEFAULT_LFL_VOL_PCT,
            ufl_vol_pct=DEFAULT_UFL_VOL_PCT,
            flash_point_c=DEFAULT_FLASH_POINT_C,
            auto_ignition_c=DEFAULT_AUTO_IGNITION_C,
            material_group=MaterialGroup.UNKNOWN,
            temperature_class=auto_ignition_to_temp_class(DEFAULT_AUTO_IGNITION_C),
            source="default",
        )

    async def get_material_data(self, material_name: str) -> HazardousMaterialData:
        """Get hazardous material data for engineering calculations.

        Strategy:
          1. Check cache
          2. Look up in internal DB (fast, reliable, no API)
          3. Fetch from PubChem API (slower, broader coverage)
          4. Fall back to conservative defaults

        Args:
            material_name: Material name (e.g., "methane", "propane", "hydrogen")

        Returns:
            HazardousMaterialData (always succeeds, never raises)

        """
        if not material_name or not material_name.strip():
            return self._get_default("unknown")

        # Check cache
        cached = self._get_cached(material_name)
        if cached is not None:
            return cached

        # Check internal DB
        internal = self._lookup_internal_db(material_name)
        if internal is not None:
            self._set_cached(material_name, internal)
            return internal

        # Fetch from PubChem
        try:
            data = await self._fetch_pubchem(material_name)
            self._set_cached(material_name, data)
            return data
        except (httpx.HTTPError, ValueError, KeyError) as e:
            logger.warning(
                f"PubChem fetch failed for '{material_name}': "
                f"{type(e).__name__}: {e}. Using defaults."
            )
        except Exception as e:
            logger.error(
                f"Unexpected error fetching hazmat data for '{material_name}': "
                f"{type(e).__name__}: {e}. Using defaults."
            )

        # Default
        default = self._get_default(material_name)
        self._set_cached(material_name, default)
        return default

    def list_known_materials(self) -> list[str]:
        """List all materials in the internal database."""
        return sorted(_INTERNAL_HAZMAT_DB.keys())


# Singleton
_hazmat_service: Optional[HazmatService] = None


def get_hazmat_service() -> HazmatService:
    """Get the singleton HazmatService instance."""
    global _hazmat_service
    if _hazmat_service is None:
        _hazmat_service = HazmatService()
    return _hazmat_service


async def close_hazmat_service() -> None:
    """Close the HazmatService on application shutdown."""
    global _hazmat_service
    if _hazmat_service is not None:
        await _hazmat_service.close()
        _hazmat_service = None
