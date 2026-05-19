from core.engine import run_fire_alarm_engine


def test_office_smoke_detector():
    rooms = [
        {
            "id": "office1",
            "type": "office",
            "area": 120,
            "polygon": [(0, 0), (10, 0), (10, 12), (0, 12)]
        }
    ]

    result = run_fire_alarm_engine(rooms)
    assert len(result["devices"]) >= 2
    assert result["validation"]["is_valid"] is True


def test_corridor_linear_placement():
    rooms = [
        {
            "id": "corridor1",
            "type": "corridor",
            "area": 60,
            "polygon": [(0, 0), (30, 0), (30, 2), (0, 2)]
        }
    ]

    result = run_fire_alarm_engine(rooms)
    devices = result["devices"]
    assert len(devices) >= 3


def test_staircase():
    rooms = [
        {
            "id": "stair1",
            "type": "stair",
            "area": 9,
            "polygon": [(0, 0), (3, 0), (3, 3), (0, 3)]
        }
    ]

    result = run_fire_alarm_engine(rooms)
    devices = result["devices"]
    assert len(devices) >= 1


def test_coverage_score():
    rooms = [
        {
            "id": "room1",
            "type": "office",
            "area": 100,
            "polygon": [(0, 0), (10, 0), (10, 10), (0, 10)]
        }
    ]

    result = run_fire_alarm_engine(rooms)
    assert result["validation"]["is_valid"] is True
    assert result["validation"]["coverage_score"] >= 0.90


def test_no_room_without_device():
    rooms = [
        {
            "id": "small_office",
            "type": "office",
            "area": 9,
            "polygon": [(0, 0), (3, 0), (3, 3), (0, 3)]
        }
    ]

    result = run_fire_alarm_engine(rooms)
    assert len(result["devices"]) >= 1