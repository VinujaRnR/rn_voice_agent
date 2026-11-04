"""Universal IoT device registration, command dispatch, and telemetry API."""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.database.session import get_db_session, transaction
from app.middleware.request_context import RequestContext, get_request_context
from app.middleware.authorization import require_authenticated
from app.iot.registry.device_registry import UniversalDeviceRegistry
from app.iot.commands.command_service import UniversalCommandService
from app.database.repositories.iot_repository import IoTRepository

router = APIRouter(prefix="/api/v1/devices", tags=["Universal IoT Devices"])


class DeviceRegisterRequest(BaseModel):
    name: str = Field(..., description="Device friendly name, e.g. 'Living Room Lamp'")
    device_id: str = Field(..., description="Unique hardware address or ID")
    household_id: Optional[str] = Field(None, description="Target household")
    device_type: str = Field("light", description="Device type: light, switch, thermostat, radar, actuator")
    location: Optional[str] = Field("Living Room", description="Room name")
    connection_type: str = Field("WiFi", description="Protocol: WiFi, Zigbee, Bluetooth, RN_Hub")
    capabilities: List[str] = Field(default_factory=lambda: ["turn_on", "turn_off", "set_power"])


class DeviceCommandRequest(BaseModel):
    action: str = Field(..., description="Action name, e.g. turn_on, turn_off, set_power")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Action parameters")


class TelemetryIngestRequest(BaseModel):
    event_type: str = Field(..., description="Sensor event type: presence, temperature, power, motion")
    payload: Dict[str, Any] = Field(..., description="Telemetry data payload")


@router.post("", status_code=status.HTTP_201_CREATED)
async def register_device(
    payload: DeviceRegisterRequest,
    ctx: RequestContext = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session)
):
    """Enroll a new IoT device into the user's household."""
    target_hh = payload.household_id or ctx.household_id
    if not target_hh:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Household ID is required to register a device"
        )

    async with transaction(session):
        dev = await UniversalDeviceRegistry.register_device(
            session=session,
            ctx=ctx,
            household_id=target_hh,
            name=payload.name,
            device_id=payload.device_id,
            device_type=payload.device_type,
            location=payload.location,
            connection_type=payload.connection_type,
            capabilities=payload.capabilities
        )

    return {
        "status": "success",
        "id": dev.id,
        "device_id": dev.device_id,
        "name": dev.name,
        "household_id": dev.household_id,
        "type": dev.type,
        "location": dev.location
    }


@router.get("")
async def list_devices(
    household_id: Optional[str] = None,
    ctx: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session)
):
    """List devices authorized for caller's household."""
    devices = await UniversalDeviceRegistry.list_devices(
        session=session,
        ctx=ctx,
        household_id=household_id
    )
    return [
        {
            "id": d.id,
            "device_id": d.device_id,
            "name": d.name,
            "type": d.type,
            "location": d.location,
            "power_state": d.power_state,
            "online_status": d.online_status
        }
        for d in devices
    ]


@router.get("/{device_id}")
async def get_device(
    device_id: str,
    ctx: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session)
):
    """Retrieve detailed device entity and capabilities."""
    dev = await UniversalDeviceRegistry.get_device(session=session, ctx=ctx, device_id=device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Device '{device_id}' not found")

    return {
        "id": dev.id,
        "device_id": dev.device_id,
        "name": dev.name,
        "type": dev.type,
        "location": dev.location,
        "connection_type": dev.connection_type,
        "power_state": dev.power_state,
        "online_status": dev.online_status
    }


@router.post("/{device_id}/command")
async def dispatch_command(
    device_id: str,
    payload: DeviceCommandRequest,
    ctx: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session)
):
    """Send an authorized command to a registered hardware device."""
    async with transaction(session):
        result = await UniversalCommandService.dispatch_command(
            session=session,
            ctx=ctx,
            device_id=device_id,
            action=payload.action,
            parameters=payload.parameters
        )
    return result


@router.get("/{device_id}/state")
async def get_device_state(
    device_id: str,
    ctx: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session)
):
    """Fetch live reported vs desired state for device."""
    repo = IoTRepository(session)
    dev = await UniversalDeviceRegistry.get_device(session=session, ctx=ctx, device_id=device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Device '{device_id}' not found")

    state = await repo.get_device_state(dev.id)
    return {
        "device_id": dev.device_id,
        "is_online": state.is_online if state else True,
        "reported_state": state.reported_state if state else {"power": dev.power_state},
        "desired_state": state.desired_state if state else {"power": dev.power_state}
    }


@router.post("/{device_id}/telemetry")
async def ingest_telemetry(
    device_id: str,
    payload: TelemetryIngestRequest,
    ctx: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session)
):
    """Ingest sensor event and update state."""
    repo = IoTRepository(session)
    dev = await repo.get_by_device_id(device_id)
    target_id = dev.id if dev else device_id

    async with transaction(session):
        telem = await repo.record_telemetry(
            device_id=target_id,
            event_type=payload.event_type,
            payload=payload.payload
        )
        if "power" in payload.payload:
            await repo.upsert_device_state(
                device_id=target_id,
                reported_state=payload.payload
            )

    return {"status": "recorded", "telemetry_id": telem.id}
