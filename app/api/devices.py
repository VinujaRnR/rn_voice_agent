"""API endpoints for device registry discovery, node inspection, and CRUD management."""
import logging
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from app.commands.device_registry import device_registry
from app.tools.device_control import control_device
from app.database.session import get_async_session, transaction
from app.database.models.devices import Device as DBDevice, DeviceCapability as DBCapability
from app.database.models.identity import Household
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/devices", tags=["devices"])


async def sync_single_device_to_db(dev_data: Dict[str, Any], household_id: Optional[str] = None) -> None:
    """Synchronize a device record from dataset into MySQL database."""
    try:
        dev_id = dev_data.get("device_id")
        if not dev_id:
            return
        async with get_async_session() as session:
            async with transaction(session):
                # Retrieve default household if not provided
                if not household_id:
                    res = await session.execute(select(Household.id).order_by(Household.created_at.desc()).limit(1))
                    household_id = res.scalar()

                stmt = select(DBDevice).where((DBDevice.device_id == dev_id) | (DBDevice.id == dev_id) | (DBDevice.id == f"dev_{dev_id}"))
                db_dev = (await session.execute(stmt)).scalars().first()
                if db_dev:
                    db_dev.name = dev_data.get("name") or db_dev.name
                    db_dev.type = dev_data.get("type") or db_dev.type
                    db_dev.node_id = dev_data.get("node_id") or db_dev.node_id
                    db_dev.location = dev_data.get("location") or db_dev.location
                    db_dev.connection_type = dev_data.get("connection") or db_dev.connection_type or "WiFi"
                    db_dev.power_state = dev_data.get("power_state") or db_dev.power_state or "off"
                    db_dev.online_status = dev_data.get("status") or db_dev.online_status or "online"
                    if household_id and not db_dev.household_id:
                        db_dev.household_id = household_id
                else:
                    db_dev = DBDevice(
                        id=f"dev_{dev_id}",
                        device_id=dev_id,
                        name=dev_data.get("name") or dev_id,
                        type=dev_data.get("type") or "generic",
                        node_id=dev_data.get("node_id"),
                        household_id=household_id,
                        connection_type=dev_data.get("connection") or "WiFi",
                        location=dev_data.get("location") or "Living Room",
                        power_state=dev_data.get("power_state") or "off",
                        online_status=dev_data.get("status") or "online",
                        is_enrolled=True
                    )
                    session.add(db_dev)

                await session.flush()

                # Sync capabilities/actions
                actions = dev_data.get("allowed_actions") or dev_data.get("actions") or []
                params = dev_data.get("params") or {}
                if actions:
                    cap_stmt = select(DBCapability).where(DBCapability.device_id == db_dev.id)
                    existing_caps = (await session.execute(cap_stmt)).scalars().all()
                    existing_acts = {c.action_name for c in existing_caps}
                    for act in actions:
                        if act not in existing_acts:
                            session.add(DBCapability(
                                device_id=db_dev.id,
                                action_name=act,
                                parameter_schema=params
                            ))
    except Exception as e:
        logger.warning(f"Failed to sync device '{dev_data.get('device_id')}' to MySQL: {e}")


async def delete_device_from_db(dev_id: str) -> None:
    """Remove device record from MySQL database."""
    try:
        async with get_async_session() as session:
            async with transaction(session):
                stmt = select(DBDevice).where((DBDevice.device_id == dev_id) | (DBDevice.id == dev_id) | (DBDevice.id == f"dev_{dev_id}"))
                db_devs = (await session.execute(stmt)).scalars().all()
                for d in db_devs:
                    await session.delete(d)
    except Exception as e:
        logger.warning(f"Failed to delete device '{dev_id}' from MySQL: {e}")


async def update_device_power_in_db(dev_id: str, power_state: str) -> None:
    """Update power state of device record in MySQL database."""
    try:
        async with get_async_session() as session:
            async with transaction(session):
                stmt = select(DBDevice).where((DBDevice.device_id == dev_id) | (DBDevice.id == dev_id) | (DBDevice.id == f"dev_{dev_id}"))
                db_devs = (await session.execute(stmt)).scalars().all()
                for d in db_devs:
                    d.power_state = power_state.lower()
    except Exception as e:
        logger.warning(f"Failed to update power state for '{dev_id}' in MySQL: {e}")


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
    """Add a new device or hub to the data table, persist to JSON, and sync to MySQL."""
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

    # Sync to MySQL database
    if created:
        await sync_single_device_to_db(created)

    return {
        "status": "success",
        "message": f"Device '{created.get('name')}' created successfully.",
        "device": created
    }


@router.put("/{device_id}", response_model=Dict[str, Any])
async def update_device(device_id: str, request: DeviceUpdateRequest):
    """Update details of an existing device in the data table, persist to JSON, and sync to MySQL."""
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

    # Sync to MySQL database
    await sync_single_device_to_db(updated)

    return {
        "status": "success",
        "message": f"Device '{updated.get('name')}' updated successfully.",
        "device": updated
    }


@router.delete("/{device_id}", response_model=Dict[str, Any])
async def delete_device(device_id: str):
    """Delete a device from the data table, persist to JSON, and remove from MySQL."""
    dev = device_registry.get_device(device_id)
    if not dev:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found.")

    deleted = device_registry.unregister_device(dev["device_id"], auto_save=True)
    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete device record.")

    # Remove from MySQL database
    await delete_device_from_db(dev["device_id"])

    return {
        "status": "success",
        "message": f"Device '{dev.get('name')}' deleted successfully.",
        "device_id": dev["device_id"]
    }


@router.post("/{device_id}/toggle", response_model=Dict[str, Any])
async def toggle_device_power(device_id: str):
    """Toggle device power state (on/off), publish command to RabbitMQ, and sync to MySQL."""
    dev = device_registry.get_device(device_id)
    if not dev:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found.")

    current_state = dev.get("power_state", "off").lower()
    new_state = "off" if current_state == "on" else "on"

    res = control_device(
        device_id=dev["device_id"],
        action="set_power",
        parameters={"state": new_state},
        user_id="admin",
        session_id="admin_console_toggle"
    )

    # Sync state to MySQL
    await update_device_power_in_db(dev["device_id"], new_state)

    return {
        "status": "success",
        "device_id": dev["device_id"],
        "device_name": dev.get("name"),
        "node_id": dev.get("node_id"),
        "previous_state": current_state,
        "new_state": new_state,
        "execution": res
    }


@router.post("/sync", response_model=Dict[str, Any])
async def sync_all_dataset_devices():
    """Synchronize all devices from devices.json dataset into the MySQL database."""
    devices = device_registry.list_devices()
    synced_count = 0
    for dev in devices:
        await sync_single_device_to_db(dev)
        synced_count += 1

    return {
        "status": "success",
        "message": f"Successfully synchronized {synced_count} dataset devices with MySQL database.",
        "synced_count": synced_count,
        "total_devices": len(devices)
    }
