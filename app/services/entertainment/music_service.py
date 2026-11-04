"""Music catalog, playlist management, and playback state service."""
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.database.models.entertainment import Track, Playlist, PlaylistTrack
from app.database.repositories.entertainment_repository import EntertainmentRepository
from app.middleware.request_context import RequestContext


# Sample catalog tracks favored by elderly residents
SAMPLE_ELDERLY_TRACKS = [
    {"title": "Can't Help Falling in Love", "artist": "Elvis Presley", "genre": "Classic Pop", "duration_seconds": 182, "media_url": "/audio/relaxing_music.wav"},
    {"title": "We'll Meet Again", "artist": "Vera Lynn", "genre": "Nostalgia", "duration_seconds": 204, "media_url": "/audio/relaxing_music.wav"},
    {"title": "Moon River", "artist": "Audrey Hepburn", "genre": "Soundtrack", "duration_seconds": 125, "media_url": "/audio/relaxing_music.wav"},
    {"title": "What a Wonderful World", "artist": "Louis Armstrong", "genre": "Jazz", "duration_seconds": 139, "media_url": "/audio/relaxing_music.wav"},
    {"title": "Waltzing Matilda", "artist": "Slim Dusty", "genre": "Australian Folk", "duration_seconds": 218, "media_url": "/audio/relaxing_music.wav"},
]


class MusicEntertainmentService:
    """Service managing music playback, search, and personal playlists."""

    _current_playback_state = {
        "status": "stopped",
        "current_track": None,
        "media_url": "/audio/relaxing_music.wav",
        "volume": 0.8,
        "is_playing": False
    }

    @classmethod
    async def seed_default_tracks(cls, session: AsyncSession) -> None:
        repo = EntertainmentRepository(session)
        existing = await repo.list_all(limit=1)
        if not existing:
            for t in SAMPLE_ELDERLY_TRACKS:
                await repo.add_track(**t)

    @classmethod
    async def search_music(cls, session: AsyncSession, query: str) -> List[Track]:
        repo = EntertainmentRepository(session)
        return await repo.search_tracks(query)

    @classmethod
    async def create_playlist(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        name: str,
        description: Optional[str] = None
    ) -> Playlist:
        repo = EntertainmentRepository(session)
        return await repo.create_playlist(
            user_id=ctx.actor_id,
            household_id=ctx.household_id,
            name=name,
            description=description
        )

    @classmethod
    async def list_playlists(cls, session: AsyncSession, ctx: RequestContext) -> List[Playlist]:
        repo = EntertainmentRepository(session)
        return await repo.list_user_playlists(ctx.actor_id)

    @classmethod
    async def add_track_to_playlist(
        cls,
        session: AsyncSession,
        playlist_id: str,
        track_id: str
    ) -> PlaylistTrack:
        repo = EntertainmentRepository(session)
        return await repo.add_track_to_playlist(playlist_id=playlist_id, track_id=track_id)

    @classmethod
    def execute_playback_command(
        cls,
        action: str,
        track_title_or_artist: Optional[str] = None,
        volume: Optional[float] = None
    ) -> Dict[str, Any]:
        """Execute playback action: play, pause, next, previous, volume, stop."""
        act = (action or "play").lower().strip()
        if act in ["play", "start", "resume"]:
            target = track_title_or_artist or "Can't Help Falling in Love by Elvis Presley"
            media_url = "/audio/relaxing_music.wav"
            for t in SAMPLE_ELDERLY_TRACKS:
                if t["title"].lower() in target.lower() or t["artist"].lower() in target.lower():
                    target = f"{t['title']} by {t['artist']}"
                    media_url = t["media_url"]
                    break

            cls._current_playback_state.update({
                "status": "playing",
                "current_track": target,
                "media_url": media_url,
                "is_playing": True
            })
            return {
                "status": "playing",
                "action": "play",
                "track": target,
                "media_url": media_url,
                "volume": cls._current_playback_state["volume"],
                "speech": f"Now playing {target}."
            }
        elif act == "pause":
            cls._current_playback_state.update({"status": "paused", "is_playing": False})
            return {"status": "paused", "action": "pause", "speech": "Music paused."}
        elif act in ["next", "skip"]:
            target = "What a Wonderful World by Louis Armstrong"
            media_url = "/audio/relaxing_music.wav"
            cls._current_playback_state.update({
                "status": "playing",
                "current_track": target,
                "media_url": media_url,
                "is_playing": True
            })
            return {
                "status": "playing",
                "action": "next",
                "track": target,
                "media_url": media_url,
                "volume": cls._current_playback_state["volume"],
                "speech": f"Skipping to the next track: {target}."
            }
        elif act in ["stop", "off"]:
            cls._current_playback_state.update({"status": "stopped", "is_playing": False})
            return {"status": "stopped", "action": "stop", "speech": "Music stopped."}
        elif act in ["volume", "volume_up", "volume_down"] or volume is not None:
            if volume is None:
                current_vol = cls._current_playback_state.get("volume", 0.8)
                volume = min(1.0, current_vol + 0.2) if "up" in act else max(0.1, current_vol - 0.2)
            cls._current_playback_state["volume"] = max(0.0, min(1.0, volume))
            return {
                "status": "volume_adjusted",
                "action": "volume",
                "volume": cls._current_playback_state["volume"],
                "speech": f"Volume set to {int(cls._current_playback_state['volume'] * 100)} percent."
            }

        return {"status": "error", "action": act, "message": f"Unsupported playback action '{action}'", "state": cls._current_playback_state}
