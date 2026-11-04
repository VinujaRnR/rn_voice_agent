"""Universal IoT and hardware device repository."""
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.database.models.devices import Device, DeviceCapability, Gateway, DeviceBinding
from app.database.base import utc_now
from app.database.repositories.base import BaseRepository


class DeviceRepository(BaseRepository[Device]):
    """Repository handling universal hardware device registration and state."""

    def __init__(self, session: AsyncSession):
        super().__init__(Device, session)

    async def get_by_hardware_id(self, device_id: str) -> Optional[Device]:
        stmt = select(Device).where((Device.device_id == device_id) | (Device.id == device_id))
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def register_device(
        self,
        name: str,
        device_id: str,
        type: str = "device",
        node_id: Optional[str] = None,
        household_id: Optional[str] = None,
        connection_type: str = "WiFi",
        location: Optional[str] = None,
        auth_token: Optional[str] = None
    ) -> Device:
        existing = await self.get_by_hardware_id(device_id)
        if existing:
            existing.name = name
            existing.type = type
            if node_id:
                existing.node_id = node_id
            if household_id:
                existing.household_id = household_id
            if location:
                existing.location = location
            if auth_token:
                existing.auth_token = auth_token
            existing.updated_at = utc_now()
            await self.session.flush()
            return existing

        dev = Device(
            id=device_id,
            name=name,
            device_id=device_id,
            type=type,
            node_id=node_id,
            household_id=household_id,
            connection_type=connection_type,
            location=location,
            power_state="off",
            online_status="online",
            is_enrolled=True,
            auth_token=auth_token
        )
        self.session.add(dev)
        await self.session.flush()
        return dev

    async def update_power_state(self, device_id: str, power_state: str) -> Optional[Device]:
        dev = await self.get_by_hardware_id(device_id)
        if dev:
            dev.power_state = power_state.lower()
            dev.updated_at = utc_now()
            await self.session.flush()
        return dev

    async def add_capability(
        self,
        device_id: str,
        action_name: str,
        parameter_schema: Optional[Dict[str, Any]] = None
    ) -> DeviceCapability:
        cap = DeviceCapability(
            device_id=device_id,
            action_name=action_name,
            parameter_schema=parameter_schema or {}
        )
        self.session.add(cap)
        await self.session.flush()
        return cap

    async def get_capabilities(self, device_id: str) -> List[DeviceCapability]:
        stmt = select(DeviceCapability).where(DeviceCapability.device_id == device_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def register_gateway(
        self,
        household_id: str,
        gateway_identifier: str,
        gateway_name: str,
        ip_address: Optional[str] = None,
        mac_address: Optional[str] = None
    ) -> Gateway:
        gateway = Gateway(
            household_id=household_id,
            gateway_identifier=gateway_identifier,
            gateway_name=gateway_name,
            ip_address=ip_address,
            mac_address=mac_address,
            status="online"
        )
        self.session.add(gateway)
        await self.session.flush()
        return gateway

    async def bind_device(
        self,
        device_id: str,
        gateway_id: Optional[str] = None,
        sub_device_id: Optional[str] = None,
        channel_key: Optional[str] = None,
        binding_metadata: Optional[Dict[str, Any]] = None
    ) -> DeviceBinding:
        binding = DeviceBinding(
            device_id=device_id,
            gateway_id=gateway_id,
            sub_device_id=sub_device_id,
            channel_key=channel_key,
            binding_metadata=binding_metadata or {}
        )
        self.session.add(binding)
        await self.session.flush()
        return binding

    async def list_devices(self, household_id: Optional[str] = None) -> List[Device]:
        stmt = select(Device)
        if household_id:
            stmt = stmt.where(Device.household_id == household_id)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

