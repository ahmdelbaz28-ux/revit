"""room_templates.py — Ready-made RoomSpec templates
=========================================
Usage:
    from fireai.core.room_templates import office, warehouse, corridor
    room = office(width=10, depth=10)
"""

from fireai.core.nfpa72_models import CeilingSpec, CeilingType, RoomSpec


def office(width: float = 10, depth: float = 10, height: float = 3.0) -> RoomSpec:
    """Standard office room."""
    return RoomSpec(
        room_id=f"office_{width}x{depth}",
        width_m=width,
        depth_m=depth,
        occupancy_type="office",
        ceiling_spec=CeilingSpec.create_safe(
            height_at_low_point_m=height,
            ceiling_type=CeilingType.FLAT,
        ),
    )


def warehouse(width: float = 20, depth: float = 30, height: float = 6.0) -> RoomSpec:
    """Warehouse storage area."""
    return RoomSpec(
        room_id=f"warehouse_{width}x{depth}",
        width_m=width,
        depth_m=depth,
        occupancy_type="warehouse",
        ceiling_spec=CeilingSpec.create_safe(
            height_at_low_point_m=height,
            ceiling_type=CeilingType.FLAT,
        ),
    )


def corridor(width: float = 6, depth: float = 3, height: float = 2.4) -> RoomSpec:
    """Corridor/hallway."""
    return RoomSpec(
        room_id=f"corridor_{width}x{depth}",
        width_m=width,
        depth_m=depth,
        occupancy_type="corridor",
        ceiling_spec=CeilingSpec.create_safe(
            height_at_low_point_m=height,
            ceiling_type=CeilingType.FLAT,
        ),
    )


def kitchen(width: float = 5, depth: float = 5, height: float = 2.7) -> RoomSpec:
    """Commercial kitchen."""
    return RoomSpec(
        room_id=f"kitchen_{width}x{depth}",
        width_m=width,
        depth_m=depth,
        occupancy_type="office",
        ceiling_spec=CeilingSpec.create_safe(
            height_at_low_point_m=height,
            ceiling_type=CeilingType.FLAT,
        ),
    )


def meeting(width: float = 8, depth: float = 8, height: float = 2.7) -> RoomSpec:
    """Meeting room."""
    return RoomSpec(
        room_id=f"meeting_{width}x{depth}",
        width_m=width,
        depth_m=depth,
        occupancy_type="office",
        ceiling_spec=CeilingSpec.create_safe(
            height_at_low_point_m=height,
            ceiling_type=CeilingType.FLAT,
        ),
    )


def bathroom(width: float = 4, depth: float = 4, height: float = 2.4) -> RoomSpec:
    """Bathroom (low ceiling)."""
    return RoomSpec(
        room_id=f"bathroom_{width}x{depth}",
        width_m=width,
        depth_m=depth,
        occupancy_type="bathroom",
        ceiling_spec=CeilingSpec.create_safe(
            height_at_low_point_m=height,
            ceiling_type=CeilingType.FLAT,
        ),
    )


def storage(width: float = 5, depth: float = 5, height: float = 3.0) -> RoomSpec:
    """Storage room."""
    return RoomSpec(
        room_id=f"storage_{width}x{depth}",
        width_m=width,
        depth_m=depth,
        occupancy_type="storage",
        ceiling_spec=CeilingSpec.create_safe(
            height_at_low_point_m=height,
            ceiling_type=CeilingType.FLAT,
        ),
    )


def high_ceiling_office(width: float = 10, depth: float = 10, height: float = 4.5) -> RoomSpec:
    """Office with high ceiling."""
    return RoomSpec(
        room_id=f"high_office_{width}x{depth}",
        width_m=width,
        depth_m=depth,
        occupancy_type="office",
        ceiling_spec=CeilingSpec.create_safe(
            height_at_low_point_m=height,
            ceiling_type=CeilingType.FLAT,
        ),
    )


# All templates
TEMPLATES = {
    "office": office,
    "warehouse": warehouse,
    "corridor": corridor,
    "kitchen": kitchen,
    # "meeting": meeting,  # Not valid
    "bathroom": bathroom,
    "storage": storage,
    "high_ceiling": high_ceiling_office,
}


def get_template(name: str, **kwargs) -> RoomSpec:
    """Get template by name."""
    if name not in TEMPLATES:
        raise ValueError(f"Unknown template: {name}. Available: {list(TEMPLATES.keys())}")
    return TEMPLATES[name](**kwargs)
