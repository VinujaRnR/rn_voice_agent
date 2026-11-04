"""Caregivers, care plans, and medication management API."""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.database.session import get_db_session, transaction
from app.middleware.request_context import RequestContext, get_request_context
from app.middleware.authorization import require_authenticated
from app.services.care.care_service import CareService
from app.database.repositories.care_repository import CareRepository

router = APIRouter(prefix="/api/v1/care", tags=["Elderly Care & Medication"])


class CaregiverRegisterRequest(BaseModel):
    user_id: str
    agency_name: Optional[str] = None
    license_number: Optional[str] = None
    specialty: str = "elderly_care"


class CaregiverAssignmentRequest(BaseModel):
    caregiver_id: str
    resident_id: str
    scope: str = "full_care"


class CarePlanUpdateRequest(BaseModel):
    routine_details: Dict[str, Any] = Field(default_factory=dict)
    dietary_notes: Optional[str] = None
    emergency_instructions: Optional[str] = None


class MedicationScheduleCreate(BaseModel):
    medication_name: str = Field(..., description="Prescription drug name")
    dosage: str = Field(..., description="Exact dose, e.g. 500mg, 1 tablet")
    scheduled_time: str = Field(..., description="Time of day, e.g. '08:00', '20:00'")
    instructions: Optional[str] = Field(None, description="e.g. 'Take with food'")
    requires_food: bool = False


class MedicationEventCreate(BaseModel):
    event_type: str = Field(..., description="reminded, acknowledged, dispenser_removed, caregiver_confirmed, missed")
    notes: Optional[str] = None


@router.post("/caregivers", status_code=status.HTTP_201_CREATED)
async def register_caregiver(
    payload: CaregiverRegisterRequest,
    ctx: RequestContext = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session)
):
    async with transaction(session):
        cg = await CareService.register_caregiver(
            session=session,
            ctx=ctx,
            user_id=payload.user_id,
            agency_name=payload.agency_name,
            license_number=payload.license_number,
            specialty=payload.specialty
        )
    return {"status": "success", "caregiver_id": cg.id, "user_id": cg.user_id}


@router.post("/assignments", status_code=status.HTTP_201_CREATED)
async def assign_caregiver(
    payload: CaregiverAssignmentRequest,
    ctx: RequestContext = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session)
):
    async with transaction(session):
        assign = await CareService.assign_caregiver(
            session=session,
            ctx=ctx,
            caregiver_id=payload.caregiver_id,
            resident_id=payload.resident_id,
            scope=payload.scope
        )
    return {"status": "success", "assignment_id": assign.id, "resident_id": assign.resident_id}


@router.get("/residents/{resident_id}/plan")
async def get_care_plan(
    resident_id: str,
    ctx: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session)
):
    plan = await CareService.get_care_plan(session=session, ctx=ctx, resident_id=resident_id)
    if not plan:
        return {"routine_details": {}, "dietary_notes": None, "emergency_instructions": None}
    return {
        "id": plan.id,
        "resident_id": plan.resident_id,
        "routine_details": plan.routine_details,
        "dietary_notes": plan.dietary_notes,
        "emergency_instructions": plan.emergency_instructions
    }


@router.put("/residents/{resident_id}/plan")
async def update_care_plan(
    resident_id: str,
    payload: CarePlanUpdateRequest,
    ctx: RequestContext = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session)
):
    async with transaction(session):
        plan = await CareService.upsert_care_plan(
            session=session,
            ctx=ctx,
            resident_id=resident_id,
            routine_details=payload.routine_details,
            dietary_notes=payload.dietary_notes,
            emergency_instructions=payload.emergency_instructions
        )
    return {"status": "success", "id": plan.id, "routine_details": plan.routine_details}


@router.post("/residents/{resident_id}/medications", status_code=status.HTTP_201_CREATED)
async def create_medication_schedule(
    resident_id: str,
    payload: MedicationScheduleCreate,
    ctx: RequestContext = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session)
):
    async with transaction(session):
        med = await CareService.create_medication_schedule(
            session=session,
            ctx=ctx,
            resident_id=resident_id,
            medication_name=payload.medication_name,
            dosage=payload.dosage,
            scheduled_time=payload.scheduled_time,
            instructions=payload.instructions,
            requires_food=payload.requires_food
        )
    return {
        "status": "success",
        "id": med.id,
        "medication_name": med.medication_name,
        "dosage": med.dosage,
        "scheduled_time": med.scheduled_time
    }


@router.get("/residents/{resident_id}/medications")
async def list_medications(
    resident_id: str,
    ctx: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session)
):
    meds = await CareService.list_medications(session=session, ctx=ctx, resident_id=resident_id)
    return [
        {
            "id": m.id,
            "medication_name": m.medication_name,
            "dosage": m.dosage,
            "scheduled_time": m.scheduled_time,
            "instructions": m.instructions,
            "requires_food": m.requires_food
        }
        for m in meds
    ]


@router.post("/residents/{resident_id}/medications/{schedule_id}/events")
async def log_medication_event(
    resident_id: str,
    schedule_id: str,
    payload: MedicationEventCreate,
    ctx: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session)
):
    async with transaction(session):
        evt = await CareService.log_adherence_event(
            session=session,
            ctx=ctx,
            resident_id=resident_id,
            schedule_id=schedule_id,
            event_type=payload.event_type,
            notes=payload.notes
        )
    return {"status": "success", "event_id": evt.id, "event_type": evt.event_type}
