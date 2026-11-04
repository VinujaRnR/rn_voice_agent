"""Care, caregiver assignments, care plans, and medication repository."""
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models.care import (
    Caregiver, CaregiverAssignment, CarePlan, MedicationSchedule, MedicationEvent, CareEscalation
)
from app.database.repositories.base import BaseRepository
from app.database.base import utc_now


class CareRepository(BaseRepository[Caregiver]):
    """Repository handling elderly care plans, medications, and caregiver assignments."""

    def __init__(self, session: AsyncSession):
        super().__init__(Caregiver, session)

    async def register_caregiver(
        self,
        user_id: str,
        agency_name: Optional[str] = None,
        license_number: Optional[str] = None,
        specialty: str = "elderly_care"
    ) -> Caregiver:
        caregiver = Caregiver(
            user_id=user_id,
            agency_name=agency_name,
            license_number=license_number,
            specialty=specialty
        )
        self.session.add(caregiver)
        await self.session.flush()
        return caregiver

    async def assign_caregiver(
        self,
        caregiver_id: str,
        resident_id: str,
        scope: str = "full_care"
    ) -> CaregiverAssignment:
        assignment = CaregiverAssignment(
            caregiver_id=caregiver_id,
            resident_id=resident_id,
            scope=scope,
            is_active=True
        )
        self.session.add(assignment)
        await self.session.flush()
        return assignment

    async def get_resident_caregivers(self, resident_id: str) -> List[CaregiverAssignment]:
        stmt = (
            select(CaregiverAssignment)
            .where(CaregiverAssignment.resident_id == resident_id, CaregiverAssignment.is_active == True)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def upsert_care_plan(
        self,
        resident_id: str,
        routine_details: Dict[str, Any],
        dietary_notes: Optional[str] = None,
        emergency_instructions: Optional[str] = None
    ) -> CarePlan:
        stmt = select(CarePlan).where(CarePlan.resident_id == resident_id)
        res = await self.session.execute(stmt)
        plan = res.scalars().first()
        if plan:
            plan.routine_details = routine_details
            plan.dietary_notes = dietary_notes
            if emergency_instructions:
                plan.emergency_instructions = emergency_instructions
            await self.session.flush()
            return plan
        else:
            plan = CarePlan(
                resident_id=resident_id,
                routine_details=routine_details,
                dietary_notes=dietary_notes,
                emergency_instructions=emergency_instructions
            )
            self.session.add(plan)
            await self.session.flush()
            return plan

    async def get_care_plan(self, resident_id: str) -> Optional[CarePlan]:
        stmt = select(CarePlan).where(CarePlan.resident_id == resident_id)
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def create_medication_schedule(
        self,
        resident_id: str,
        medication_name: str,
        dosage: str,
        scheduled_time: str,
        instructions: Optional[str] = None,
        requires_food: bool = False
    ) -> MedicationSchedule:
        sched = MedicationSchedule(
            resident_id=resident_id,
            medication_name=medication_name,
            dosage=dosage,
            scheduled_time=scheduled_time,
            instructions=instructions,
            requires_food=requires_food,
            is_active=True
        )
        self.session.add(sched)
        await self.session.flush()
        return sched

    async def get_medication_schedules(self, resident_id: str) -> List[MedicationSchedule]:
        stmt = (
            select(MedicationSchedule)
            .where(MedicationSchedule.resident_id == resident_id, MedicationSchedule.is_active == True)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def log_medication_event(
        self,
        schedule_id: str,
        resident_id: str,
        event_type: str,
        notes: Optional[str] = None
    ) -> MedicationEvent:
        evt = MedicationEvent(
            schedule_id=schedule_id,
            resident_id=resident_id,
            event_type=event_type,
            recorded_at=utc_now(),
            notes=notes
        )
        self.session.add(evt)
        await self.session.flush()
        return evt

    async def create_escalation(
        self,
        resident_id: str,
        incident_type: str,
        severity: str = "medium",
        details: Optional[str] = None
    ) -> CareEscalation:
        esc = CareEscalation(
            resident_id=resident_id,
            incident_type=incident_type,
            severity=severity,
            details=details,
            status="open"
        )
        self.session.add(esc)
        await self.session.flush()
        return esc
