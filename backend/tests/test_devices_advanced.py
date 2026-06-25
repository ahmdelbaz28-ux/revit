"""test_devices_advanced.py — Advanced device CRUD integration tests covering
load unit conversion, watt conversion edge cases, device update paths,
and device deletion with audit trail.

Focuses on code paths NOT covered by existing test_devices.py and
test_routers.py, specifically:
  - Device creation with load_unit="mA" tracking properties
  - Device creation with load_unit="W" and voltage > 0
  - Device update with load_unit="W" using existing device voltage
  - Device update with load_unit="W" when device voltage is 0 (400 error)
  - Device update with properties
  - Device delete in nonexistent project (404)
  - Device creation with all optional fields
  - Device list with sort and order parameters
  - Device get returns all expected fields
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def _setup_env():
    """Set development environment for testing."""
    os.environ["FIREAI_ENV"] = "development"
    os.environ["FIREAI_API_KEY"] = ""


@pytest.fixture(scope="module")
def client():
    """Create a test client for the FastAPI app."""
    from backend.app import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def test_project(client):
    """Create a fresh project for device tests and return its ID."""
    resp = client.post(
        "/api/projects",
        json={"name": "Advanced Device Test Project", "description": "For device tests", "author": "pytest"},
    )
    data = resp.json().get("data", resp.json())
    return data.get("id") or data.get("project_id")


@pytest.fixture
def device_in_project(client, test_project):
    """Create a device with known electrical parameters and return (project_id, device_data)."""
    pid = test_project
    resp = client.post(
        f"/api/projects/{pid}/devices",
        json={
            "name": "Test Smoke Detector",
            "type": "FA_SMOKE",
            "category": "FIRE_ALARM",
            "x": 10.0,
            "y": 20.0,
            "z": 2.4,
            "rotation": 0.0,
            "voltage": 24.0,
            "current": 0.1,
            "load": 0.1,
            "load_unit": "A",
        },
    )
    assert resp.status_code == 201, f"Device creation failed: {resp.text}"
    dev_data = resp.json().get("data", resp.json())
    return pid, dev_data


# ══════════════════════════════════════════════════════════════════════════════
# DEVICE CREATION WITH LOAD UNIT CONVERSION
# ══════════════════════════════════════════════════════════════════════════════


class TestDeviceLoadUnitConversion:
    """Tests for load_unit conversion during device creation."""

    def test_create_device_ma_stores_amperes(self, client, test_project):
        """Device with load_unit='mA' must store load converted to Amperes."""
        pid = test_project
        resp = client.post(
            f"/api/projects/{pid}/devices",
            json={
                "name": "mA Device",
                "type": "FA_SMOKE",
                "category": "FIRE_ALARM",
                "x": 5.0, "y": 10.0,
                "voltage": 24.0,
                "load": 500.0,
                "load_unit": "mA",
            },
        )
        assert resp.status_code == 201
        data = resp.json().get("data", resp.json())
        # 500mA = 0.5A
        assert abs(data.get("load", 0) - 0.5) < 0.01

    def test_create_device_ma_stores_original_unit_in_properties(self, client, test_project):
        """Device with load_unit='mA' must store traceability info in properties."""
        pid = test_project
        resp = client.post(
            f"/api/projects/{pid}/devices",
            json={
                "name": "mA Traceability Device",
                "type": "FA_SMOKE",
                "category": "FIRE_ALARM",
                "x": 5.0, "y": 10.0,
                "voltage": 24.0,
                "load": 300.0,
                "load_unit": "mA",
            },
        )
        assert resp.status_code == 201
        data = resp.json().get("data", resp.json())
        props = data.get("properties", {})
        assert props.get("load_original_value") == 300.0
        assert props.get("load_original_unit") == "mA"

    def test_create_device_watts_stores_amperes(self, client, test_project):
        """Device with load_unit='W' must convert via voltage to Amperes."""
        pid = test_project
        resp = client.post(
            f"/api/projects/{pid}/devices",
            json={
                "name": "Watts Device",
                "type": "FA_HORN",
                "category": "FIRE_ALARM",
                "x": 15.0, "y": 25.0,
                "voltage": 24.0,
                "load": 12.0,
                "load_unit": "W",
            },
        )
        assert resp.status_code == 201
        data = resp.json().get("data", resp.json())
        # 12W / 24V = 0.5A
        assert abs(data.get("load", 0) - 0.5) < 0.01

    def test_create_device_watts_stores_traceability(self, client, test_project):
        """Device with load_unit='W' must store original value and unit."""
        pid = test_project
        resp = client.post(
            f"/api/projects/{pid}/devices",
            json={
                "name": "Watts Trace Device",
                "type": "FA_STROBE",
                "category": "FIRE_ALARM",
                "x": 20.0, "y": 30.0,
                "voltage": 24.0,
                "load": 24.0,
                "load_unit": "W",
            },
        )
        assert resp.status_code == 201
        data = resp.json().get("data", resp.json())
        props = data.get("properties", {})
        assert props.get("load_original_value") == 24.0
        assert props.get("load_original_unit") == "W"

    def test_create_device_watts_zero_voltage_fails(self, client, test_project):
        """Device with load_unit='W' and voltage=0 must return 400."""
        pid = test_project
        resp = client.post(
            f"/api/projects/{pid}/devices",
            json={
                "name": "Bad Watts Device",
                "type": "FA_HORN",
                "category": "FIRE_ALARM",
                "x": 0.0, "y": 0.0,
                "voltage": 0.0,
                "load": 12.0,
                "load_unit": "W",
            },
        )
        assert resp.status_code == 400

    def test_create_device_watts_negative_voltage_fails(self, client, test_project):
        """Device with load_unit='W' and negative voltage must return 400 or 422."""
        pid = test_project
        resp = client.post(
            f"/api/projects/{pid}/devices",
            json={
                "name": "Neg Voltage Device",
                "type": "FA_HORN",
                "category": "FIRE_ALARM",
                "x": 0.0, "y": 0.0,
                "voltage": -12.0,
                "load": 12.0,
                "load_unit": "W",
            },
        )
        assert resp.status_code in (400, 422)

    def test_create_device_default_load_unit_is_amperes(self, client, test_project):
        """Device without load_unit must store load as Amperes (no conversion)."""
        pid = test_project
        resp = client.post(
            f"/api/projects/{pid}/devices",
            json={
                "name": "Amps Device",
                "type": "FA_SMOKE",
                "category": "FIRE_ALARM",
                "x": 5.0, "y": 10.0,
                "load": 0.3,
            },
        )
        assert resp.status_code == 201
        data = resp.json().get("data", resp.json())
        assert abs(data.get("load", 0) - 0.3) < 0.01

    def test_create_device_zero_load_ma_no_conversion(self, client, test_project):
        """Device with load=0 and load_unit='mA' should store 0 (no conversion needed)."""
        pid = test_project
        resp = client.post(
            f"/api/projects/{pid}/devices",
            json={
                "name": "Zero Load Device",
                "type": "FA_MODULE",
                "category": "FIRE_ALARM",
                "x": 0.0, "y": 0.0,
                "load": 0.0,
                "load_unit": "mA",
            },
        )
        assert resp.status_code == 201
        data = resp.json().get("data", resp.json())
        assert data.get("load", 0) == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# DEVICE UPDATE WITH LOAD UNIT CONVERSION
# ══════════════════════════════════════════════════════════════════════════════


class TestDeviceUpdateLoadUnit:
    """Tests for load_unit conversion during device update."""

    def test_update_device_watts_uses_existing_voltage(self, client, device_in_project):
        """Updating device with load_unit='W' must use existing device voltage."""
        pid, dev = device_in_project
        dev_id = dev.get("id") or dev.get("device_id")
        # Device was created with voltage=24.0
        resp = client.put(
            f"/api/projects/{pid}/devices/{dev_id}",
            json={"load": 24.0, "load_unit": "W"},
        )
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        # 24W / 24V = 1.0A
        assert abs(data.get("load", 0) - 1.0) < 0.01

    def test_update_device_watts_with_zero_existing_voltage_fails(self, client, test_project):
        """Updating device with load_unit='W' when device voltage is 0 must fail."""
        pid = test_project
        # Create device with voltage=0
        create_resp = client.post(
            f"/api/projects/{pid}/devices",
            json={
                "name": "Zero Volt Device",
                "type": "FA_MODULE",
                "category": "FIRE_ALARM",
                "x": 0.0, "y": 0.0,
                "voltage": 0.0,
                "load": 0.0,
            },
        )
        dev_data = create_resp.json().get("data", create_resp.json())
        dev_id = dev_data.get("id") or dev_data.get("device_id")
        # Try to update load with watts — should fail since voltage is 0
        resp = client.put(
            f"/api/projects/{pid}/devices/{dev_id}",
            json={"load": 12.0, "load_unit": "W"},
        )
        assert resp.status_code == 400

    def test_update_device_ma_conversion(self, client, device_in_project):
        """Updating device with load_unit='mA' must convert to Amperes."""
        pid, dev = device_in_project
        dev_id = dev.get("id") or dev.get("device_id")
        resp = client.put(
            f"/api/projects/{pid}/devices/{dev_id}",
            json={"load": 250.0, "load_unit": "mA"},
        )
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert abs(data.get("load", 0) - 0.25) < 0.01

    def test_update_device_watts_with_voltage_in_same_update(self, client, test_project):
        """Updating device with load_unit='W' and voltage in same update must work."""
        pid = test_project
        # Create device
        create_resp = client.post(
            f"/api/projects/{pid}/devices",
            json={
                "name": "Dual Update Device",
                "type": "FA_MODULE",
                "category": "FIRE_ALARM",
                "x": 0.0, "y": 0.0,
                "voltage": 0.0,
                "load": 0.0,
            },
        )
        dev_data = create_resp.json().get("data", create_resp.json())
        dev_id = dev_data.get("id") or dev_data.get("device_id")
        # Update both voltage and load with watts in same request
        resp = client.put(
            f"/api/projects/{pid}/devices/{dev_id}",
            json={"voltage": 24.0, "load": 12.0, "load_unit": "W"},
        )
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        # 12W / 24V = 0.5A
        assert abs(data.get("load", 0) - 0.5) < 0.01

    def test_update_device_with_properties(self, client, device_in_project):
        """Updating device properties must merge with existing properties."""
        pid, dev = device_in_project
        dev_id = dev.get("id") or dev.get("device_id")
        resp = client.put(
            f"/api/projects/{pid}/devices/{dev_id}",
            json={"properties": {"custom_field": "test_value"}},
        )
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert data.get("properties", {}).get("custom_field") == "test_value"

    def test_update_device_position(self, client, device_in_project):
        """Updating device position (x, y, z) must succeed."""
        pid, dev = device_in_project
        dev_id = dev.get("id") or dev.get("device_id")
        resp = client.put(
            f"/api/projects/{pid}/devices/{dev_id}",
            json={"x": 50.0, "y": 60.0, "z": 3.0},
        )
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert abs(data.get("x", 0) - 50.0) < 0.01
        assert abs(data.get("y", 0) - 60.0) < 0.01
        assert abs(data.get("z", 0) - 3.0) < 0.01


# ══════════════════════════════════════════════════════════════════════════════
# DEVICE DELETION
# ══════════════════════════════════════════════════════════════════════════════


class TestDeviceDeletion:
    """Tests for device deletion paths."""

    def test_delete_device_success(self, client, test_project):
        """Deleting an existing device must return 200."""
        pid = test_project
        create_resp = client.post(
            f"/api/projects/{pid}/devices",
            json={"name": "To Delete", "type": "FA_MODULE", "category": "FIRE_ALARM", "x": 1.0, "y": 2.0},
        )
        dev_data = create_resp.json().get("data", create_resp.json())
        dev_id = dev_data.get("id") or dev_data.get("device_id")
        resp = client.delete(f"/api/projects/{pid}/devices/{dev_id}")
        assert resp.status_code == 200

    def test_delete_device_nonexistent_project_404(self, client):
        """Deleting a device in a nonexistent project must return 404."""
        resp = client.delete("/api/projects/nonexistent-proj/devices/some-device")
        assert resp.status_code == 404

    def test_delete_device_twice_second_404(self, client, test_project):
        """Deleting the same device twice must return 404 on second attempt."""
        pid = test_project
        create_resp = client.post(
            f"/api/projects/{pid}/devices",
            json={"name": "Double Delete", "type": "FA_MODULE", "category": "FIRE_ALARM", "x": 1.0, "y": 2.0},
        )
        dev_data = create_resp.json().get("data", create_resp.json())
        dev_id = dev_data.get("id") or dev_data.get("device_id")
        # First delete
        resp1 = client.delete(f"/api/projects/{pid}/devices/{dev_id}")
        assert resp1.status_code == 200
        # Second delete
        resp2 = client.delete(f"/api/projects/{pid}/devices/{dev_id}")
        assert resp2.status_code == 404

    def test_delete_device_then_get_404(self, client, test_project):
        """After deletion, getting the device must return 404."""
        pid = test_project
        create_resp = client.post(
            f"/api/projects/{pid}/devices",
            json={"name": "Get After Delete", "type": "FA_MODULE", "category": "FIRE_ALARM", "x": 1.0, "y": 2.0},
        )
        dev_data = create_resp.json().get("data", create_resp.json())
        dev_id = dev_data.get("id") or dev_data.get("device_id")
        client.delete(f"/api/projects/{pid}/devices/{dev_id}")
        resp = client.get(f"/api/projects/{pid}/devices/{dev_id}")
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# DEVICE LIST WITH SORT AND PAGINATION
# ══════════════════════════════════════════════════════════════════════════════


class TestDeviceListSortAndPagination:
    """Tests for device listing with sort, order, and pagination parameters."""

    def test_list_devices_sort_by_name(self, client, test_project):
        """Listing devices sorted by name must succeed."""
        pid = test_project
        resp = client.get(f"/api/projects/{pid}/devices?sort=name&order=asc")
        assert resp.status_code == 200

    def test_list_devices_sort_by_type(self, client, test_project):
        """Listing devices sorted by type must succeed."""
        pid = test_project
        resp = client.get(f"/api/projects/{pid}/devices?sort=type&order=desc")
        assert resp.status_code == 200

    def test_list_devices_sort_by_category(self, client, test_project):
        """Listing devices sorted by category must succeed."""
        pid = test_project
        resp = client.get(f"/api/projects/{pid}/devices?sort=category&order=asc")
        assert resp.status_code == 200

    def test_list_devices_sort_by_voltage(self, client, test_project):
        """Listing devices sorted by voltage must succeed."""
        pid = test_project
        resp = client.get(f"/api/projects/{pid}/devices?sort=voltage&order=asc")
        assert resp.status_code == 200

    def test_list_devices_invalid_sort_defaults(self, client, test_project):
        """Listing devices with unknown sort field must not crash (defaults)."""
        pid = test_project
        resp = client.get(f"/api/projects/{pid}/devices?sort=unknown_field")
        assert resp.status_code == 200

    def test_list_devices_pagination_page_2(self, client, test_project):
        """Listing devices page 2 with limit 1 must succeed."""
        pid = test_project
        # Create at least 2 devices
        client.post(
            f"/api/projects/{pid}/devices",
            json={"name": "Device A", "type": "FA_SMOKE", "category": "FIRE_ALARM", "x": 1.0, "y": 1.0},
        )
        client.post(
            f"/api/projects/{pid}/devices",
            json={"name": "Device B", "type": "FA_HORN", "category": "FIRE_ALARM", "x": 2.0, "y": 2.0},
        )
        resp = client.get(f"/api/projects/{pid}/devices?page=2&limit=1")
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# DEVICE CREATION WITH ALL FIELDS
# ══════════════════════════════════════════════════════════════════════════════


class TestDeviceCreationFullFields:
    """Tests for device creation with all optional fields specified."""

    def test_create_device_with_all_fields(self, client, test_project):
        """Creating a device with all fields must succeed and return them."""
        pid = test_project
        resp = client.post(
            f"/api/projects/{pid}/devices",
            json={
                "name": "Full Device",
                "type": "FA_SOUND_STROBE",
                "category": "FIRE_ALARM",
                "x": 100.0,
                "y": 200.0,
                "z": 3.5,
                "rotation": 45.0,
                "voltage": 24.0,
                "current": 0.5,
                "load": 0.3,
                "load_unit": "A",
                "properties": {"manufacturer": "Notifier", "model": "NFS2-3030"},
            },
        )
        assert resp.status_code == 201
        data = resp.json().get("data", resp.json())
        assert data.get("name") == "Full Device"
        assert data.get("type") == "FA_SOUND_STROBE"
        assert abs(data.get("voltage", 0) - 24.0) < 0.01
        assert data.get("properties", {}).get("manufacturer") == "Notifier"

    def test_create_device_with_custom_properties(self, client, test_project):
        """Device properties dict must be stored and returned."""
        pid = test_project
        resp = client.post(
            f"/api/projects/{pid}/devices",
            json={
                "name": "Props Device",
                "type": "FA_SMOKE",
                "category": "FIRE_ALARM",
                "x": 5.0, "y": 5.0,
                "properties": {
                    "sensitivity": "%0.5",
                    "test_frequency": "annual",
                    "nfpa_class": "A",
                },
            },
        )
        assert resp.status_code == 201
        data = resp.json().get("data", resp.json())
        props = data.get("properties", {})
        assert props.get("sensitivity") == "%0.5"
        assert props.get("test_frequency") == "annual"
        assert props.get("nfpa_class") == "A"
