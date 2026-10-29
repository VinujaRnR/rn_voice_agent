"""API endpoints for device registry discovery, node inspection, and CRUD management."""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from app.commands.device_registry import device_registry
from app.tools.device_control import control_device

router = APIRouter(prefix="/api/devices", tags=["devices"])


class DeviceCreateRequest(BaseModel):
    device_id: str = Field(..., description="Unique device ID or MAC address (e.g. 98a316e6b658 or room_lights)")
    name: str = Field(..., description="Device friendly name")
    node_id: Optional[str] = Field(default="NODE-STANDALONE", description="Hardware Node ID (e.g. NODE-ESP8266-01)")
    type: str = Field(default="generic", description="Device type (hub, relay, lighting, robot, climate)")
    connection: Optional[str] = Field(default="WiFi", description="Hardware connection/protocol")
    location: Optional[str] = Field(default="General", description="Physical room or location")
    connected_devices: Optional[List[Dict[str, Any]]] = Field(default=[], description="Auxiliary peripherals or sub-devices")
    actions: Optional[List[str]] = Field(default=["set_power", "get_status", "turn_on", "turn_off"], description="Predefined actions")
    params: Optional[Dict[str, Any]] = Field(default_factory=lambda: {"state": "on"}, description="Predefined parameters")
    allowed_actions: Optional[List[str]] = Field(default=["set_power", "get_status", "turn_on", "turn_off"])
    status: Optional[str] = Field(default="online")
    power_state: Optional[str] = Field(default="off")
    aliases: Optional[List[str]] = Field(default=[])


class DeviceUpdateRequest(BaseModel):
    name: Optional[str] = None
    node_id: Optional[str] = None
    type: Optional[str] = None
    connection: Optional[str] = None
    location: Optional[str] = None
    connected_devices: Optional[List[Dict[str, Any]]] = None
    actions: Optional[List[str]] = None
    params: Optional[Dict[str, Any]] = None
    allowed_actions: Optional[List[str]] = None
    status: Optional[str] = None
    power_state: Optional[str] = None
    aliases: Optional[List[str]] = None


@router.get("", response_model=Dict[str, Any])
@router.get("/", response_model=Dict[str, Any])
async def list_registered_devices():
    """Retrieve full data table of registered devices, hubs, and node topologies."""
    devices = device_registry.list_devices()
    total_devices = len(devices)
    online_devices = sum(1 for d in devices if d.get("status") == "online")
    total_sub_devices = sum(d.get("connected_devices_count", len(d.get("connected_devices", []))) for d in devices)
    total_nodes = len(set(d.get("node_id") for d in devices if d.get("node_id")))

    return {
        "status": "success",
        "total_devices": total_devices,
        "online_devices": online_devices,
        "total_nodes": total_nodes,
        "total_connected_sub_devices": total_sub_devices,
        "devices": devices
    }


@router.get("/{device_id}", response_model=Dict[str, Any])
async def get_device_details(device_id: str):
    """Retrieve single device record by ID, MAC, or Node ID."""
    dev = device_registry.get_device(device_id) or device_registry.get_device_by_node_id(device_id)
    if not dev:
        raise HTTPException(status_code=404, detail=f"Device or node '{device_id}' not found.")
    return dev


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Dict[str, Any])
@router.post("/", status_code=status.HTTP_201_CREATED, response_model=Dict[str, Any])
async def create_device(request: DeviceCreateRequest):
    """Add a new device or hub to the data table and persist to JSON."""
    clean_id = request.device_id.strip()
    if device_registry.get_device(clean_id):
        raise HTTPException(status_code=400, detail=f"Device with ID '{clean_id}' already exists.")

    metadata = request.model_dump()
    metadata.pop("device_id", None)
    if "actions" in metadata and not metadata.get("allowed_actions"):
        metadata["allowed_actions"] = metadata["actions"]
    elif "allowed_actions" in metadata and not metadata.get("actions"):
        metadata["actions"] = metadata["allowed_actions"]
    registered_id = device_registry.register_device(clean_id, metadata, auto_save=True)
    created = device_registry.get_device(registered_id)

    return {
        "status": "success",
        "message": f"Device '{created.get('name')}' created successfully.",
        "device": created
    }


@router.put("/{device_id}", response_model=Dict[str, Any])
async def update_device(device_id: str, request: DeviceUpdateRequest):
    """Update details of an existing device in the data table and persist to JSON."""
    dev = device_registry.get_device(device_id)
    if not dev:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found.")

    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    if "actions" in updates and "allowed_actions" not in updates:
        updates["allowed_actions"] = updates["actions"]
    elif "allowed_actions" in updates and "actions" not in updates:
        updates["actions"] = updates["allowed_actions"]
    updated = device_registry.update_device(dev["device_id"], updates, auto_save=True)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update device record.")

    return {
        "status": "success",
        "message": f"Device '{updated.get('name')}' updated successfully.",
        "device": updated
    }


@router.delete("/{device_id}", response_model=Dict[str, Any])
async def delete_device(device_id: str):
    """Delete a device from the data table and persist to JSON."""
    dev = device_registry.get_device(device_id)
    if not dev:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found.")

    deleted = device_registry.unregister_device(dev["device_id"], auto_save=True)
    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete device record.")

    return {
        "status": "success",
        "message": f"Device '{dev.get('name')}' deleted successfully.",
        "device_id": dev["device_id"]
    }


@router.post("/{device_id}/toggle", response_model=Dict[str, Any])
async def toggle_device_power(device_id: str):
    """Toggle device power state (on/off) and publish command to RabbitMQ."""
    dev = device_registry.get_device(device_id)
    if not dev:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found.")

    current_state = dev.get("power_state", "off").lower()
    new_state = "off" if current_state == "on" else "on"

    res = control_device(
        device_id=dev["device_id"],
        action="set_power",
        parameters={"state": new_state},
        user_id="web_dashboard",
        session_id="devices_page_toggle"
    )

    return {
        "status": "success",
        "device_id": dev["device_id"],
        "device_name": dev.get("name"),
        "node_id": dev.get("node_id"),
        "previous_state": current_state,
        "new_state": new_state,
        "execution": res
    }
