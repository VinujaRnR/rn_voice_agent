"""Caregiver, care plans, medication adherence, and escalation service."""
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.database.models.care import (
    Caregiver, CaregiverAssignment, CarePlan, MedicationSchedule, MedicationEvent, CareEscalation
)
from app.database.repositories.care_repository import CareRepository
from app.middleware.request_context import RequestContext
from app.middleware.tenant_isolation import enforce_resident_access


class CareService:
    """Service handling professional elderly care, prescribed medication schedules, and adherence."""

    VALID_EVENT_TYPES = {"reminded", "acknowledged", "dispenser_removed", "caregiver_confirmed", "missed"}

    @classmethod
    async def register_caregiver(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        user_id: str,
        agency_name: Optional[str] = None,
        license_number: Optional[str] = None,
        specialty: str = "elderly_care"
    ) -> Caregiver:
        repo = CareRepository(session)
        return await repo.register_caregiver(
            user_id=user_id,
            agency_name=agency_name,
            license_number=license_number,
            specialty=specialty
        )

    @classmethod
    async def assign_caregiver(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        caregiver_id: str,
        resident_id: str,
        scope: str = "full_care"
    ) -> CaregiverAssignment:
        await enforce_resident_access(ctx, resident_id, scope="profile:write", session=session)
        repo = CareRepository(session)
        return await repo.assign_caregiver(caregiver_id, resident_id, scope)

    @classmethod
    async def upsert_care_plan(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        resident_id: str,
        routine_details: Dict[str, Any],
        dietary_notes: Optional[str] = None,
        emergency_instructions: Optional[str] = None
    ) -> CarePlan:
        await enforce_resident_access(ctx, resident_id, scope="profile:write", session=session)
        repo = CareRepository(session)
        return await repo.upsert_care_plan(
            resident_id=resident_id,
            routine_details=routine_details,
            dietary_notes=dietary_notes,
            emergency_instructions=emergency_instructions
        )

    @classmethod
    async def get_care_plan(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        resident_id: str
    ) -> Optional[CarePlan]:
        await enforce_resident_access(ctx, resident_id, scope="profile:read", session=session)
        repo = CareRepository(session)
        return await repo.get_care_plan(resident_id)

    @classmethod
    async def create_medication_schedule(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        resident_id: str,
        medication_name: str,
        dosage: str,
        scheduled_time: str,
        instructions: Optional[str] = None,
        requires_food: bool = False
    ) -> MedicationSchedule:
        """Create authorized medication schedule. Prevents LLM hallucinations on dosage."""
        await enforce_resident_access(ctx, resident_id, scope="profile:write", session=session)
        repo = CareRepository(session)
        return await repo.create_medication_schedule(
            resident_id=resident_id,
            medication_name=medication_name,
            dosage=dosage,
            scheduled_time=scheduled_time,
            instructions=instructions,
            requires_food=requires_food
        )

    @classmethod
    async def list_medications(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        resident_id: str
    ) -> List[MedicationSchedule]:
        await enforce_resident_access(ctx, resident_id, scope="profile:read", session=session)
        repo = CareRepository(session)
        return await repo.get_medication_schedules(resident_id)

    @classmethod
    async def log_adherence_event(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        resident_id: str,
        schedule_id: str,
        event_type: str,
        notes: Optional[str] = None
    ) -> MedicationEvent:
        """Record distinct adherence stage: reminded, acknowledged, dispenser_removed, caregiver_confirmed, missed."""
        if event_type not in cls.VALID_EVENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid event_type '{event_type}'. Valid types: {cls.VALID_EVENT_TYPES}"
            )
        await enforce_resident_access(ctx, resident_id, scope="profile:write", session=session)
        repo = CareRepository(session)
        evt = await repo.log_medication_event(
            schedule_id=schedule_id,
            resident_id=resident_id,
            event_type=event_type,
            notes=notes
        )

        # Escalate automatically if dose missed
        if event_type == "missed":
            await repo.create_escalation(
                resident_id=resident_id,
                incident_type="missed_medication",
                severity="high",
                details=f"Medication schedule {schedule_id} was missed."
            )

        return evt
