"""
FACP IMMUTABLE DATA SHEET STORAGE
Contains accurate, verified product datasheet values for selection.

V54 FIX F4: Added supports_releasing field to FireAlarmPanel dataclass.
  Root cause: Original code defined requires_releasing in ProjectRequirements
  but never checked it because FireAlarmPanel had no matching field.
  Impact: Releasing (suppression) service panels could be paired with
  non-releasing-rated panels — direct NFPA 72 SS21.7 violation.
"""

from dataclasses import dataclass
from typing import List

@dataclass(frozen=True)
class FireAlarmPanel:
    model: str
    manufacturer: str
    points_capacity: int
    nac_capacity: int
    supports_networking: bool
    supports_voice: bool
    supports_releasing: bool  # V54 FIX F4: Was missing
    max_slc_loops: int
    listings: List[str]
    standby_current_amps: float
    alarm_current_amps: float
    power_supply_watts: int

# Immutable manufacturer master FACP parameters
NOTIFIER_PANELS = [
    FireAlarmPanel(
        model="NFS-320",
        manufacturer="NOTIFIER",
        points_capacity=250,
        nac_capacity=2,
        supports_networking=False,
        supports_voice=False,
        supports_releasing=False,
        max_slc_loops=1,
        listings=["UL", "ULC"],
        standby_current_amps=0.200,
        alarm_current_amps=0.350,
        power_supply_watts=144
    ),
    FireAlarmPanel(
        model="NFS-640",
        manufacturer="NOTIFIER",
        points_capacity=640,
        nac_capacity=4,
        supports_networking=True,
        supports_voice=True,
        supports_releasing=False,
        max_slc_loops=4,
        listings=["UL", "ULC"],
        standby_current_amps=0.250,
        alarm_current_amps=0.450,
        power_supply_watts=144
    ),
    FireAlarmPanel(
        model="NFS2-3030",
        manufacturer="NOTIFIER",
        points_capacity=3180,
        nac_capacity=10,
        supports_networking=True,
        supports_voice=True,
        supports_releasing=True,  # NFS2-3030 supports releasing
        max_slc_loops=10,
        listings=["UL", "ULC", "FM"],
        standby_current_amps=0.350,
        alarm_current_amps=0.650,
        power_supply_watts=288
    )
]

SIEMENS_PANELS = [
    FireAlarmPanel(
        model="FC901",
        manufacturer="SIEMENS",
        points_capacity=50,
        nac_capacity=2,
        supports_networking=False,
        supports_voice=False,
        supports_releasing=False,
        max_slc_loops=1,
        listings=["UL", "FM", "FDNY"],
        standby_current_amps=0.120,
        alarm_current_amps=0.250,
        power_supply_watts=170
    ),
    FireAlarmPanel(
        model="FC922",
        manufacturer="SIEMENS",
        points_capacity=252,
        nac_capacity=4,
        supports_networking=True,
        supports_voice=True,
        supports_releasing=False,
        max_slc_loops=2,
        listings=["UL", "FM", "FDNY"],
        standby_current_amps=0.180,
        alarm_current_amps=0.350,
        power_supply_watts=170
    ),
    FireAlarmPanel(
        model="FC924",
        manufacturer="SIEMENS",
        points_capacity=504,
        nac_capacity=6,
        supports_networking=True,
        supports_voice=True,
        supports_releasing=True,  # FC924 supports releasing
        max_slc_loops=4,
        listings=["UL", "FM", "FDNY"],
        standby_current_amps=0.220,
        alarm_current_amps=0.450,
        power_supply_watts=300
    )
]

SIMPLEX_PANELS = [
    FireAlarmPanel(
        model="4100ES",
        manufacturer="SIMPLEX",
        points_capacity=3000,
        nac_capacity=10,
        supports_networking=True,
        supports_voice=True,
        supports_releasing=True,  # 4100ES supports releasing
        max_slc_loops=10,
        listings=["UL", "FM", "FDNY"],
        standby_current_amps=0.450,
        alarm_current_amps=0.850,
        power_supply_watts=360
    )
]

MASTER_PANEL_DATABASE = NOTIFIER_PANELS + SIEMENS_PANELS + SIMPLEX_PANELS
