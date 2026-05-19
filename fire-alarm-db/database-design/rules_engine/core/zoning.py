def group_rooms_by_type(rooms):
    zones = {}
    for room in rooms:
        room_type = room.get("type", "general")
        if room_type not in zones:
            zones[room_type] = []
        zones[room_type].append(room["id"])

    return [
        {"id": f"zone_{zone_type}", "room_ids": room_ids}
        for zone_type, room_ids in zones.items()
    ]