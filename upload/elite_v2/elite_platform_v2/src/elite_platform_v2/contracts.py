"""Strict input contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from .geometry import validate_polygon


FORBIDDEN_DERIVED_FIELDS = (
    "width_m",
    "depth_m",
    "area_m2",
    "centroid_x",
    "centroid_y",
)


class ContractViolation(ValueError):
    pass


@dataclass(frozen=True)
class RoomContract:
    room_id: str
    name: str
    floor_id: str
    polygon: List[Tuple[float, float]]
    ceiling_height_m: float
    use_type: str

    @classmethod
    def from_payload(cls, payload):
        for field_name in FORBIDDEN_DERIVED_FIELDS:
            if field_name in payload:
                raise ContractViolation(
                    "%s is derived internally and must not be supplied" % field_name
                )
        required = ("room_id", "name", "floor_id", "polygon", "ceiling_height_m")
        for field_name in required:
            if field_name not in payload:
                raise ContractViolation("missing required field: %s" % field_name)
        polygon = validate_polygon(payload["polygon"])
        ceiling_height_m = float(payload["ceiling_height_m"])
        if ceiling_height_m <= 0:
            raise ContractViolation("ceiling_height_m must be positive")
        return cls(
            room_id=str(payload["room_id"]),
            name=str(payload["name"]),
            floor_id=str(payload["floor_id"]),
            polygon=polygon,
            ceiling_height_m=ceiling_height_m,
            use_type=str(payload.get("use_type", "general")),
        )

    def to_payload(self):
        return {
            "room_id": self.room_id,
            "name": self.name,
            "floor_id": self.floor_id,
            "polygon": list(self.polygon),
            "ceiling_height_m": self.ceiling_height_m,
            "use_type": self.use_type,
        }
