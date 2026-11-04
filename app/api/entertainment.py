"""Music entertainment, personal playlists, and voice playback API."""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.database.session import get_db_session, transaction
from app.middleware.request_context import RequestContext, get_request_context
from app.middleware.authorization import require_authenticated
from app.services.entertainment.music_service import MusicEntertainmentService

router = APIRouter(prefix="/api/v1/entertainment", tags=["Music & Playlists"])


class TrackCreateRequest(BaseModel):
    title: str = Field(..., description="Track title")
    artist: str = Field(..., description="Artist name")
    media_url: str = Field(..., description="Streaming audio URI")
    genre: Optional[str] = None
    duration_seconds: int = 180


class PlaylistCreateRequest(BaseModel):
    name: str = Field(..., description="Playlist title, e.g. 'Golden Oldies'")
    description: Optional[str] = None


class PlaybackControlRequest(BaseModel):
    action: str = Field("play", description="play, pause, next, previous, volume")
    track_title_or_artist: Optional[str] = None
    query: Optional[str] = None
    volume: Optional[float] = Field(None, ge=0.0, le=1.0)
    volume_level: Optional[float] = None


@router.get("/tracks")
async def search_tracks(
    query: str = Query(..., description="Search song title or artist"),
    session: AsyncSession = Depends(get_db_session)
):
    await MusicEntertainmentService.seed_default_tracks(session)
    tracks = await MusicEntertainmentService.search_music(session, query)
    return [
        {
            "id": t.id,
            "title": t.title,
            "artist": t.artist,
            "genre": t.genre,
            "duration_seconds": t.duration_seconds,
            "media_url": t.media_url
        }
        for t in tracks
    ]


@router.post("/playlists", status_code=status.HTTP_201_CREATED)
async def create_playlist(
    payload: PlaylistCreateRequest,
    ctx: RequestContext = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session)
):
    async with transaction(session):
        pl = await MusicEntertainmentService.create_playlist(
            session=session,
            ctx=ctx,
            name=payload.name,
            description=payload.description
        )
    return {"status": "success", "id": pl.id, "name": pl.name}


@router.get("/playlists")
async def list_playlists(
    ctx: RequestContext = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session)
):
    pls = await MusicEntertainmentService.list_playlists(session=session, ctx=ctx)
    return [{"id": p.id, "name": p.name, "description": p.description} for p in pls]


@router.post("/playlists/{playlist_id}/tracks")
async def add_track_to_playlist(
    playlist_id: str,
    track_id: str = Query(...),
    session: AsyncSession = Depends(get_db_session)
):
    async with transaction(session):
        item = await MusicEntertainmentService.add_track_to_playlist(session, playlist_id, track_id)
    return {"status": "success", "playlist_id": item.playlist_id, "track_id": item.track_id}


@router.post("/playback/control")
@router.post("/control")
async def control_playback(payload: PlaybackControlRequest):
    """Voice or UI music playback command."""
    target_track = payload.track_title_or_artist or payload.query
    target_volume = payload.volume if payload.volume is not None else (payload.volume_level / 100.0 if payload.volume_level is not None and payload.volume_level > 1.0 else payload.volume_level)
    res = MusicEntertainmentService.execute_playback_command(
        action=payload.action,
        track_title_or_artist=target_track,
        volume=target_volume
    )
    return res

