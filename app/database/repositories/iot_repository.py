"""Universal IoT repository handling device states, telemetry, commands, and enrollments."""
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.database.models.devices import (
    Device, DeviceCapability, Gateway, DeviceBinding,
    DeviceState, DeviceTelemetry, DeviceCommandLog, DeviceEnrollmentRequest
)
from app.database.repositories.base import BaseRepository
from app.database.base import utc_now


class IoTRepository(BaseRepository[Device]):
    """Repository handling universal device registry and live telemetry."""

    def __init__(self, session: AsyncSession):
        super().__init__(Device, session)

    async def get_household_devices(self, household_id: str) -> List[Device]:
        stmt = select(Device).where(Device.household_id == household_id)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_by_device_id(self, device_id: str) -> Optional[Device]:
        stmt = select(Device).where(Device.device_id == device_id)
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def upsert_device_state(
        self,
        device_id: str,
        reported_state: Optional[Dict[str, Any]] = None,
        desired_state: Optional[Dict[str, Any]] = None,
        is_online: Optional[bool] = None
    ) -> DeviceState:
        stmt = select(DeviceState).where(DeviceState.device_id == device_id)
        res = await self.session.execute(stmt)
        state = res.scalars().first()
        if state:
            if reported_state is not None:
                state.reported_state = reported_state
            if desired_state is not None:
                state.desired_state = desired_state
            if is_online is not None:
                state.is_online = is_online
            await self.session.flush()
            return state
        else:
            state = DeviceState(
                device_id=device_id,
                reported_state=reported_state or {},
                desired_state=desired_state or {},
                is_online=is_online if is_online is not None else True
            )
            self.session.add(state)
            await self.session.flush()
            return state

    async def get_device_state(self, device_id: str) -> Optional[DeviceState]:
        stmt = select(DeviceState).where(DeviceState.device_id == device_id)
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def record_telemetry(
        self,
        device_id: str,
        event_type: str,
        payload: Dict[str, Any]
    ) -> DeviceTelemetry:
        telemetry = DeviceTelemetry(
            device_id=device_id,
            event_type=event_type,
            payload=payload,
            recorded_at=utc_now()
        )
        self.session.add(telemetry)
        await self.session.flush()
        return telemetry

    async def log_command(
        self,
        device_id: str,
        correlation_id: str,
        action: str,
        parameters: Dict[str, Any],
        status: str = "created"
    ) -> DeviceCommandLog:
        cmd = DeviceCommandLog(
            device_id=device_id,
            correlation_id=correlation_id,
            action=action,
            parameters=parameters,
            status=status
        )
        self.session.add(cmd)
        await self.session.flush()
        return cmd

    async def update_command_status(
        self,
        correlation_id: str,
        status: str,
        error_message: Optional[str] = None
    ) -> bool:
        stmt = select(DeviceCommandLog).where(DeviceCommandLog.correlation_id == correlation_id)
        res = await self.session.execute(stmt)
        cmd = res.scalars().first()
        if cmd:
            cmd.status = status
            if error_message:
                cmd.error_message = error_message
            await self.session.flush()
            return True
        return False
