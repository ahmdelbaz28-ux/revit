from dataclasses import dataclass
from typing import List, Dict


@dataclass
class ComplianceContext:
    room: dict
    devices: List[dict]
    geometry: dict
    validation: dict
    constraints: dict

    def get_room_type(self) -> str:
        return self.room.get("type", "office")

    def get_device_count(self) -> int:
        return len([d for d in self.devices if d.get("room_id") == self.room.get("id")])

    def get_coverage(self) -> float:
        return self.validation.get("coverage", self.validation.get("overall_coverage", 0))

    def get_exit_count(self) -> int:
        return self.room.get("exit_count", 1)

    def get_travel_distance(self) -> float:
        return self.room.get("travel_distance", 20)

    def get_ceiling_height(self) -> float:
        return self.room.get("height", 3.0)