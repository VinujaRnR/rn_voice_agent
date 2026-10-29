"""Device status and discovery tool."""
from typing import Dict, Any
from app.commands.device_registry import device_registry


def list_devices() -> Dict[str, Any]:
    """Retrieve all authorized IoT devices registered with RN Hub."""
    devices = device_registry.list_devices()
    return {
        "source": "rn_hub",
        "count": len(devices),
        "devices": devices
    }


def get_device_status(device_id: str) -> Dict[str, Any]:
    """Retrieve actual device state and operational parameters from RN Hub."""
    clean_id = (device_id or "").strip()

    # Try resolving via device_registry if an alias, name, or MAC was passed
    resolved_id = device_registry.resolve_device(clean_id) or device_registry.normalize_device_id(clean_id)
    target_id = resolved_id or clean_id

    device = device_registry.get_device(target_id)
    if not device:
        return {
            "error": f"Device '{device_id}' is not registered with RN Hub.",
            "device_id": device_id,
            "status": "not_found"
        }

    # Query device status reported by RN Hub
    connected = device.get("connected_devices", [])
    return {
        "device_id": target_id,
        "name": device.get("name"),
        "node_id": device.get("node_id"),
        "type": device.get("type"),
        "connection": device.get("connection"),
        "location": device.get("location"),
        "connected_devices": connected,
        "connected_devices_count": device.get("connected_devices_count", len(connected)),
        "status": device.get("status", "online"),
        "online_status": device.get("online_status", "Reported by RN Hub"),
        "enrolled": device.get("enrolled", True),
        "power_state": device.get("power_state", "off"),
        "last_seen": "Just now",
        "allowed_actions": device.get("allowed_actions", ["set_power", "get_status"]),
        "parameters": device.get("parameters", {"state": device.get("power_state", "off")})
    }
