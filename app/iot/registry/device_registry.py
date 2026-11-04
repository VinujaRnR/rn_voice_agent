"""Universal IoT device registry service."""
from typing import Optional, List, Dict, Any
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.database.models.devices import Device, DeviceCapability
from app.database.repositories.iot_repository import IoTRepository
from app.middleware.request_context import RequestContext
from app.middleware.tenant_isolation import enforce_household_isolation


class UniversalDeviceRegistry:
    """Multi-tenant device registry allowing devices to be enrolled into households."""

    @classmethod
    async def register_device(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        household_id: str,
        name: str,
        device_id: str,
        device_type: str = "switch",
        location: Optional[str] = None,
        connection_type: str = "WiFi",
        capabilities: Optional[List[str]] = None
    ) -> Device:
        """Register a new device into a household."""
        enforce_household_isolation(ctx, household_id)
        repo = IoTRepository(session)

        # Check existing device_id
        existing = await repo.get_by_device_id(device_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Device with ID '{device_id}' already registered"
            )

        dev = Device(
            id=f"dev_{uuid.uuid4().hex[:12]}",
            household_id=household_id,
            name=name,
            device_id=device_id,
            type=device_type,
            location=location,
            connection_type=connection_type,
            power_state="off",
            online_status="online",
            is_enrolled=True
        )
        session.add(dev)
        await session.flush()

        # Add capabilities
        caps = capabilities or ["set_power", "turn_on", "turn_off"]
        for cap_name in caps:
            cap = DeviceCapability(
                device_id=dev.id,
                action_name=cap_name,
                parameter_schema={"state": "string"}
            )
            session.add(cap)

        # Initialize default state
        await repo.upsert_device_state(
            device_id=dev.id,
            reported_state={"power": "off"},
            desired_state={"power": "off"},
            is_online=True
        )

        return dev

    @classmethod
    async def list_devices(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        household_id: Optional[str] = None
    ) -> List[Device]:
        target_hh = household_id or ctx.household_id
        enforce_household_isolation(ctx, target_hh)
        repo = IoTRepository(session)
        if target_hh:
            return await repo.get_household_devices(target_hh)
        return await repo.list_all(limit=100)

    @classmethod
    async def get_device(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        device_id: str
    ) -> Optional[Device]:
        repo = IoTRepository(session)
        dev = await repo.get_by_device_id(device_id)
        if not dev:
            # Fallback check by primary key
            dev = await repo.get_by_id(device_id)
        if dev and dev.household_id:
            enforce_household_isolation(ctx, dev.household_id)
        return dev
