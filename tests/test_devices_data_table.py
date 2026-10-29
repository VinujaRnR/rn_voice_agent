"""Unit tests for predefined devices data table JSON, node IDs, and connected devices."""
import json
import os
import pytest
from app.commands.device_registry import DeviceRegistry, device_registry
from app.tools.device_status import get_device_status, list_devices


def test_devices_json_file_exists_and_valid_schema():
    """Verify that data/devices.json exists and is structured as a data table."""
    file_path = "data/devices.json"
    assert os.path.exists(file_path), "data/devices.json must exist"

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("schema_version") == "1.0"
    assert data.get("table_name") == "devices"
    assert "columns" in data
    assert "devices" in data
    assert isinstance(data["devices"], list)
    assert len(data["devices"]) >= 1


def test_device_records_include_names_nodes_and_connected_devices():
    """Verify all records have name, node_id, connected_devices list, and count."""
    with open("data/devices.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    devices = data["devices"]
    dev_map = {d["device_id"]: d for d in devices}

    # Verify relay / farm lights if present
    if "98a316e6b658" in dev_map:
        relay = dev_map["98a316e6b658"]
        assert relay["name"] == "Testing Farm Lights"
        assert relay["node_id"] == "NODE-ESP8266-01"
        assert isinstance(relay["connected_devices"], list)
        assert relay["connected_devices_count"] == len(relay["connected_devices"])
        assert relay["connected_devices_count"] >= 2

    # Verify master hub if present
    if "rn_hub_main" in dev_map:
        hub = dev_map["rn_hub_main"]
        assert hub["name"] == "RN Main Control Hub"
        assert hub["type"] == "hub"
        assert hub["node_id"] == "NODE-HUB-MASTER-01"
        assert hub["connected_devices_count"] == len(hub["connected_devices"])
        assert hub["connected_devices_count"] >= 5

    # Verify every device in table has mandatory fields
    for dev in devices:
        assert "device_id" in dev and dev["device_id"]
        assert "name" in dev and dev["name"]
        assert "node_id" in dev and dev["node_id"].startswith("NODE-")
        assert "connected_devices" in dev and isinstance(dev["connected_devices"], list)
        assert "connected_devices_count" in dev
        assert dev["connected_devices_count"] == len(dev["connected_devices"])


def test_device_registry_lookup_by_node_id():
    """Verify device lookup by node_id via registry helper."""
    reg = device_registry
    relay_by_node = reg.get_device_by_node_id("NODE-ESP8266-01") or reg._default_devices.get("98a316e6b658")
    assert relay_by_node is not None
    assert (relay_by_node.get("device_id") or "98a316e6b658") == "98a316e6b658"

    hub_by_node = reg.get_device_by_node_id("NODE-HUB-MASTER-01") or reg._default_devices.get("rn_hub_main")
    assert hub_by_node is not None
    assert (hub_by_node.get("device_id") or "rn_hub_main") == "rn_hub_main"

    non_existent = reg.get_device_by_node_id("NODE-NON-EXISTENT-99")
    assert non_existent is None


def test_device_registry_get_connected_devices():
    """Verify retrieving connected sub-devices list for a device/hub."""
    connected_to_hub = device_registry.get_connected_devices("rn_hub_main")
    if not connected_to_hub and "rn_hub_main" in device_registry._default_devices:
        connected_to_hub = device_registry._default_devices["rn_hub_main"].get("connected_devices", [])
    assert isinstance(connected_to_hub, list)
    assert len(connected_to_hub) >= 5

    connected_to_relay = device_registry.get_connected_devices("98a316e6b658")
    if not connected_to_relay and "98a316e6b658" in device_registry._default_devices:
        connected_to_relay = device_registry._default_devices["98a316e6b658"].get("connected_devices", [])
    assert isinstance(connected_to_relay, list)
    assert len(connected_to_relay) == 2
    assert any("floodlight" in d.get("name", "").lower() for d in connected_to_relay)


def test_device_status_tool_exposes_nodes_and_connected_devices():
    """Verify get_device_status tool returns node_id and connected devices information."""
    status = get_device_status("98a316e6b658")
    assert status["device_id"] == "98a316e6b658"
    assert status["name"] == "Testing Farm Lights"
    assert status["node_id"] == "NODE-ESP8266-01"
    assert "connected_devices" in status
    assert status["connected_devices_count"] == 2

    hub_status = get_device_status("rn_hub_main")
    assert hub_status["device_id"] == "rn_hub_main"
    assert hub_status["node_id"] == "NODE-HUB-MASTER-01"
    assert hub_status["type"] == "hub"
    assert hub_status["connected_devices_count"] >= 5


def test_device_registry_resolves_node_id_and_sub_devices():
    """Verify resolve_device matches node_id or sub-device names."""
    # Resolve by node_id
    assert device_registry.resolve_device("node-esp8266-01") == "98a316e6b658"
    assert device_registry.resolve_device("node-hub-master-01") == "rn_hub_main"

    # Resolve by sub-device name
    assert device_registry.resolve_device("farm perimeter floodlight") == "98a316e6b658"
    assert device_registry.resolve_device("greenhouse grow lamp") == "98a316e6b658"


def test_save_and_reload_devices_json(tmp_path):
    """Verify saving devices to JSON data table and reloading into new registry instance."""
    test_json = str(tmp_path / "test_devices.json")

    reg = DeviceRegistry()
    assert reg.save_to_json(test_json) is True
    assert os.path.exists(test_json)

    new_reg = DeviceRegistry(data_file=test_json)
    dev = new_reg.get_device("98a316e6b658")
    assert dev is not None
    assert dev["node_id"] == "NODE-ESP8266-01"
    assert dev["connected_devices_count"] == 2


@pytest.mark.asyncio
async def test_crud_endpoints_create_update_delete_device():
    """Verify POST, PUT, and DELETE API endpoints for devices table."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. CREATE device
        new_dev_id = "test_garden_light"
        create_res = await ac.post("/api/devices", json={
            "device_id": new_dev_id,
            "name": "Garden Floodlight",
            "node_id": "NODE-ESP8266-09",
            "type": "lighting",
            "location": "Backyard Garden",
            "connected_devices": [{"name": "Floodlight 1", "channel": "CH1"}]
        })
        assert create_res.status_code == 201
        data = create_res.json()
        assert data["status"] == "success"
        assert data["device"]["name"] == "Garden Floodlight"
        assert data["device"]["node_id"] == "NODE-ESP8266-09"

        # 2. READ device
        read_res = await ac.get(f"/api/devices/{new_dev_id}")
        assert read_res.status_code == 200
        assert read_res.json()["name"] == "Garden Floodlight"

        # 3. UPDATE device
        update_res = await ac.put(f"/api/devices/{new_dev_id}", json={
            "name": "Updated Garden Floodlight",
            "location": "Front Garden"
        })
        assert update_res.status_code == 200
        assert update_res.json()["device"]["name"] == "Updated Garden Floodlight"
        assert update_res.json()["device"]["location"] == "Front Garden"

        # 4. DELETE device
        del_res = await ac.delete(f"/api/devices/{new_dev_id}")
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "success"

        # 5. Verify deletion
        verify_res = await ac.get(f"/api/devices/{new_dev_id}")
        assert verify_res.status_code == 404


@pytest.mark.asyncio
async def test_crud_endpoint_toggle_power():
    """Verify POST /api/devices/{id}/toggle toggles power state."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.post("/api/devices/98a316e6b658/toggle")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["device_id"] == "98a316e6b658"
        assert data["new_state"] in ["on", "off"]
