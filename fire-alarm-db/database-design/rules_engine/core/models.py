from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class Room:
    id: str
    type: str
    area: float
    polygon: List[Tuple[float, float]]

@dataclass
class Device:
    type: str
    x: float
    y: float

@dataclass
class Zone:
    id: str
    room_ids: List[str]