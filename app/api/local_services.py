"""Australian local trade, NDIS, and aged care provider discovery API."""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query
from app.integrations.places.australian_places import AustralianLocalServices

router = APIRouter(prefix="/api/v1/services", tags=["Australian Local Services & Providers"])


@router.get("/providers")
async def find_local_providers(
    category: str = Query("plumber", description="Category: plumber, electrician, handyman, aged_care, ndis"),
    suburb_or_postcode: Optional[str] = Query(None, description="Australian suburb or postcode, e.g. Parramatta, 3000")
):
    """Retrieve verified local trades and support workers. Does not automatically place bookings."""
    providers = AustralianLocalServices.find_providers(
        category=category,
        suburb_or_postcode=suburb_or_postcode
    )
    return {
        "status": "success",
        "category": category,
        "location": suburb_or_postcode or "Australia",
        "count": len(providers),
        "providers": providers
    }


@router.get("/ndis")
async def find_ndis_providers(
    suburb_or_postcode: Optional[str] = Query(None, description="Australian location")
):
    """Filter specifically for NDIS registered care and home modification providers."""
    providers = AustralianLocalServices.find_providers(category="ndis", suburb_or_postcode=suburb_or_postcode)
    return {
        "status": "success",
        "ndis_registered": True,
        "providers": providers
    }
