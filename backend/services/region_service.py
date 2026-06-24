"""backend/services/region_service.py — Regulatory region detection for FireAI.

Determines applicable fire/electrical codes based on country/location.
Uses REST Countries API (free, no auth) for country metadata.

LIFE-SAFETY NOTE:
  Wrong regulatory region = wrong code compliance = dangerous design.
  The system supports multiple international standards:
  - NFPA 72 (US) — National Fire Alarm and Signaling Code
  - IEC 60079-10-1 (EU/International) — Hazardous Area Classification
  - ATEX (EU) — Equipment for Explosive Atmospheres
  - BS 5839-1 (UK) — Fire detection and alarm systems
  - Saudi HCIS (KSA) — High Commission for Industrial Security
  - UAE Fire Code (UAE) — Civil Defence requirements
  - Egyptian Fire Code (EG) — Egyptian Civil Protection
  - Kuwait Fire Code (KW) — Kuwait Fire Service Directorate

  This service maps country → applicable regulatory framework.

References:
  - REST Countries API: https://restcountries.com/
  - NFPA 72-2022
  - IEC 60079-10-1:2015
  - Saudi HCIS regulations

"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class RegulatoryFramework(str, Enum):
    """International regulatory frameworks supported by FireAI."""

    NFPA = "nfpa"            # US: NFPA 72, NEC
    ATEX_IEC = "atex_iec"    # EU: ATEX 2014/34/EU, IEC 60079
    BS = "bs"                # UK: BS 5839-1, BS 7671
    SAUDI_HCIS = "saudi_hcis"  # KSA: HCIS, SASO
    UAE_FC = "uae_fc"        # UAE: UAE Fire Code, Civil Defence
    EGYPT_FC = "egypt_fc"    # EG: Egyptian Fire Code
    KUWAIT_FC = "kuwait_fc"  # KW: Kuwait Fire Code
    QATAR_FC = "qatar_fc"    # QA: QCD, QCS
    GULF_GENERAL = "gulf_general"  # General Gulf states
    STANDARD_IEC = "standard_iec"  # Default: IEC standards


class ElectricalCode(str, Enum):
    """Electrical code standards."""

    NEC = "nec"      # US: National Electrical Code (NFPA 70)
    IEC = "iec"      # International: IEC 60364
    BS7671 = "bs7671"  # UK: BS 7671 (IET Wiring Regulations)


@dataclass(frozen=True)
class RegionContext:
    """Immutable regulatory region context for engineering calculations.

    Attributes:
        country_code: ISO 3166-1 alpha-2 (e.g., "US", "EG", "SA")
        country_name: Full country name
        regulatory_framework: Applicable fire/safety code framework
        electrical_code: Applicable electrical code
        region_name: Geographic region (e.g., "Middle East", "Europe")
        source: Data provenance ("rest-countries" | "inferred" | "default")

    """

    country_code: str
    country_name: str
    regulatory_framework: RegulatoryFramework
    electrical_code: ElectricalCode
    region_name: str = ""
    source: str = "rest-countries"

    @property
    def is_gulf_state(self) -> bool:
        """Whether this is a Gulf Cooperation Council state."""
        return self.country_code in ("SA", "AE", "KW", "QA", "BH", "OM")

    @property
    def is_eu(self) -> bool:
        """Whether this is an EU member state (approximate)."""
        return self.regulatory_framework == RegulatoryFramework.ATEX_IEC


# ── Country → Regulatory Framework mapping ────────────────────────────────
# Based on FireAI's international_reg_selector.py database

_COUNTRY_FRAMEWORK_MAP: dict[str, tuple[RegulatoryFramework, ElectricalCode]] = {
    # North America
    "US": (RegulatoryFramework.NFPA, ElectricalCode.NEC),
    "CA": (RegulatoryFramework.NFPA, ElectricalCode.NEC),
    "MX": (RegulatoryFramework.NFPA, ElectricalCode.NEC),

    # European Union / EEA (ATEX/IEC)
    "GB": (RegulatoryFramework.BS, ElectricalCode.BS7671),
    "DE": (RegulatoryFramework.ATEX_IEC, ElectricalCode.IEC),
    "FR": (RegulatoryFramework.ATEX_IEC, ElectricalCode.IEC),
    "IT": (RegulatoryFramework.ATEX_IEC, ElectricalCode.IEC),
    "ES": (RegulatoryFramework.ATEX_IEC, ElectricalCode.IEC),
    "NL": (RegulatoryFramework.ATEX_IEC, ElectricalCode.IEC),
    "BE": (RegulatoryFramework.ATEX_IEC, ElectricalCode.IEC),
    "AT": (RegulatoryFramework.ATEX_IEC, ElectricalCode.IEC),
    "SE": (RegulatoryFramework.ATEX_IEC, ElectricalCode.IEC),
    "NO": (RegulatoryFramework.ATEX_IEC, ElectricalCode.IEC),
    "FI": (RegulatoryFramework.ATEX_IEC, ElectricalCode.IEC),
    "DK": (RegulatoryFramework.ATEX_IEC, ElectricalCode.IEC),
    "PL": (RegulatoryFramework.ATEX_IEC, ElectricalCode.IEC),
    "PT": (RegulatoryFramework.ATEX_IEC, ElectricalCode.IEC),
    "GR": (RegulatoryFramework.ATEX_IEC, ElectricalCode.IEC),
    "IE": (RegulatoryFramework.ATEX_IEC, ElectricalCode.IEC),
    "CZ": (RegulatoryFramework.ATEX_IEC, ElectricalCode.IEC),
    "RO": (RegulatoryFramework.ATEX_IEC, ElectricalCode.IEC),
    "HU": (RegulatoryFramework.ATEX_IEC, ElectricalCode.IEC),

    # Gulf States
    "SA": (RegulatoryFramework.SAUDI_HCIS, ElectricalCode.IEC),
    "AE": (RegulatoryFramework.UAE_FC, ElectricalCode.IEC),
    "KW": (RegulatoryFramework.KUWAIT_FC, ElectricalCode.IEC),
    "QA": (RegulatoryFramework.QATAR_FC, ElectricalCode.IEC),
    "BH": (RegulatoryFramework.GULF_GENERAL, ElectricalCode.IEC),
    "OM": (RegulatoryFramework.GULF_GENERAL, ElectricalCode.IEC),

    # Middle East / North Africa
    "EG": (RegulatoryFramework.EGYPT_FC, ElectricalCode.IEC),
    "JO": (RegulatoryFramework.GULF_GENERAL, ElectricalCode.IEC),
    "LB": (RegulatoryFramework.GULF_GENERAL, ElectricalCode.IEC),
    "IQ": (RegulatoryFramework.GULF_GENERAL, ElectricalCode.IEC),

    # Asia-Pacific
    "AU": (RegulatoryFramework.ATEX_IEC, ElectricalCode.IEC),
    "NZ": (RegulatoryFramework.ATEX_IEC, ElectricalCode.IEC),
    "JP": (RegulatoryFramework.STANDARD_IEC, ElectricalCode.IEC),
    "KR": (RegulatoryFramework.STANDARD_IEC, ElectricalCode.IEC),
    "CN": (RegulatoryFramework.STANDARD_IEC, ElectricalCode.IEC),
    "IN": (RegulatoryFramework.STANDARD_IEC, ElectricalCode.IEC),
    "SG": (RegulatoryFramework.STANDARD_IEC, ElectricalCode.IEC),

    # South America
    "BR": (RegulatoryFramework.STANDARD_IEC, ElectricalCode.IEC),
    "AR": (RegulatoryFramework.STANDARD_IEC, ElectricalCode.IEC),
    "CL": (RegulatoryFramework.STANDARD_IEC, ElectricalCode.IEC),
}

# Region inference from REST Countries API region/subregion
_REGION_INFERRED_FRAMEWORK: dict[str, RegulatoryFramework] = {
    "Europe": RegulatoryFramework.ATEX_IEC,
    "Africa": RegulatoryFramework.STANDARD_IEC,
    "Asia": RegulatoryFramework.STANDARD_IEC,
    "Americas": RegulatoryFramework.NFPA,
    "Oceania": RegulatoryFramework.ATEX_IEC,
}


class RegionService:
    """Async regulatory region detection service.

    Uses REST Countries API for country metadata, then maps to
    applicable fire/electrical codes using the internal database.
    """

    REST_COUNTRIES_URL = os.environ.get(
        "REST_COUNTRIES_API_URL",
        "https://restcountries.com/v3.1/alpha"
    )

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-initialize the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0),
                headers={"User-Agent": "FireAI-DigitalTwin/1.0"},
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def get_region_context(
        self, country_code: str
    ) -> RegionContext:
        """Get regulatory region context for a country.

        Strategy:
          1. Look up country in internal framework map
          2. If not found, fetch from REST Countries API
          3. Infer framework from geographic region
          4. Default to IEC standards (most widely applicable)

        Args:
            country_code: ISO 3166-1 alpha-2 code (e.g., "EG", "US")

        Returns:
            RegionContext (always succeeds with a valid default)

        """
        cc = country_code.strip().upper()

        # 1. Check internal map first (most accurate)
        if cc in _COUNTRY_FRAMEWORK_MAP:
            framework, electrical = _COUNTRY_FRAMEWORK_MAP[cc]
            country_name = cc  # We'll enhance with API data below

            # Try to get full country name from API (non-blocking)
            try:
                api_data = await self._fetch_country_info(cc)
                if api_data:
                    country_name = api_data.get("name", {}).get("common", cc)
                    region_name = api_data.get("region", "")
                    subregion = api_data.get("subregion", "")
                    return RegionContext(
                        country_code=cc,
                        country_name=country_name,
                        regulatory_framework=framework,
                        electrical_code=electrical,
                        region_name=f"{region_name} / {subregion}".strip(" /"),
                        source="local_map+rest-countries",
                    )
            except Exception as e:
                logger.debug("REST Countries API optional fetch failed for %s: %s", cc, e)
                # API optional — we have the framework from local map

            return RegionContext(
                country_code=cc,
                country_name=country_name,
                regulatory_framework=framework,
                electrical_code=electrical,
                source="local_map",
            )

        # 2. Fetch from REST Countries API
        try:
            api_data = await self._fetch_country_info(cc)
            if api_data:
                country_name = api_data.get("name", {}).get("common", cc)
                region = api_data.get("region", "")
                # Infer framework from region
                framework = _REGION_INFERRED_FRAMEWORK.get(
                    region, RegulatoryFramework.STANDARD_IEC
                )
                return RegionContext(
                    country_code=cc,
                    country_name=country_name,
                    regulatory_framework=framework,
                    electrical_code=ElectricalCode.IEC,  # Default for non-mapped
                    region_name=region,
                    source="rest-countries",
                )
        except Exception as e:
            logger.warning(
                f"REST Countries API failed for {cc}: {e}. "
                f"Using IEC defaults."
            )

        # 3. Default to IEC (most internationally applicable)
        logger.warning(
            f"Unknown country code '{cc}'. Defaulting to IEC standards."
        )
        return RegionContext(
            country_code=cc,
            country_name=cc,
            regulatory_framework=RegulatoryFramework.STANDARD_IEC,
            electrical_code=ElectricalCode.IEC,
            source="default",
        )

    async def _fetch_country_info(self, country_code: str) -> Optional[dict]:
        """Fetch country information from REST Countries API."""
        client = await self._get_client()
        response = await client.get(f"{self.REST_COUNTRIES_URL}/{country_code}")
        response.raise_for_status()
        data = response.json()
        if data and isinstance(data, list):
            return data[0]
        return None


# ── Singleton ──────────────────────────────────────────────────────────────

_region_service: Optional[RegionService] = None


def get_region_service() -> RegionService:
    """Get the singleton RegionService instance."""
    global _region_service
    if _region_service is None:
        _region_service = RegionService()
    return _region_service


async def close_region_service() -> None:
    """Close the RegionService on application shutdown."""
    global _region_service
    if _region_service is not None:
        await _region_service.close()
        _region_service = None
