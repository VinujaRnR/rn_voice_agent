"""Tests for Admin Console device management and dataset-to-MySQL dual synchronization."""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app


def test_dataset_to_mysql_sync():
    """Verify POST /api/devices/sync synchronizes all dataset devices with MySQL database."""
    client = TestClient(app)
    res = client.post("/api/devices/sync")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["synced_count"] >= 9


def test_create_and_sync_device_with_full_fields():
    """Verify registering a device with all 9 fields specified by user."""
    test_device_id = "test_garden_pathway_01"
    payload = {
        "device_id": test_device_id,
        "name": "Garden Pathway Lights",
        "node_id": "NODE-ESP8266-02",
        "type": "Relay",
        "location": "Living Room",
        "actions": ["set_power", "turn_on", "turn_off", "get_status"],
        "params": {"state": "on"},
        "aliases": ["garden lights", "pathway lights", "garden lamp"],
        "connected_devices": [
            {"name": "Lamp 1", "channel": "CH1"},
            {"name": "Lamp 2", "channel": "CH2"}
        ]
    }

    client = TestClient(app)
    # Ensure clean slate
    client.delete(f"/api/devices/{test_device_id}")

    try:
        # 1. Create device
        res = client.post("/api/devices", json=payload)
        assert res.status_code == 201
        created = res.json()
        assert created["device"]["name"] == "Garden Pathway Lights"
        assert created["device"]["node_id"] == "NODE-ESP8266-02"
        assert len(created["device"]["connected_devices"]) == 2

        # 2. Toggle Power with mocked IoT hardware broker
        with patch("app.api.devices.control_device") as mock_ctrl:
            mock_ctrl.return_value = {"status": "success", "published": True}
            toggle_res = client.post(f"/api/devices/{test_device_id}/toggle")
            assert toggle_res.status_code == 200
            assert toggle_res.json()["new_state"] == "on"
    finally:
        # 3. Clean up
        client.delete(f"/api/devices/{test_device_id}")
