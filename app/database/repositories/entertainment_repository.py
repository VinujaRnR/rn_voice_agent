"""Tracks, playlists, and resident favourites repository."""
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models.entertainment import Track, Playlist, PlaylistTrack, UserFavorite
from app.database.repositories.base import BaseRepository


class EntertainmentRepository(BaseRepository[Track]):
    """Repository handling resident playlists and music catalog."""

    def __init__(self, session: AsyncSession):
        super().__init__(Track, session)

    async def add_track(
        self,
        title: str,
        artist: str,
        media_url: str,
        album: Optional[str] = None,
        genre: Optional[str] = None,
        duration_seconds: int = 180,
        source_type: str = "local"
    ) -> Track:
        track = Track(
            title=title,
            artist=artist,
            album=album,
            genre=genre,
            duration_seconds=duration_seconds,
            media_url=media_url,
            source_type=source_type
        )
        self.session.add(track)
        await self.session.flush()
        return track

    async def search_tracks(self, query: str) -> List[Track]:
        stmt = (
            select(Track)
            .where((Track.title.ilike(f"%{query}%")) | (Track.artist.ilike(f"%{query}%")) | (Track.genre.ilike(f"%{query}%")))
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def create_playlist(
        self,
        user_id: str,
        name: str,
        household_id: Optional[str] = None,
        description: Optional[str] = None
    ) -> Playlist:
        pl = Playlist(
            user_id=user_id,
            household_id=household_id,
            name=name,
            description=description
        )
        self.session.add(pl)
        await self.session.flush()
        return pl

    async def list_user_playlists(self, user_id: str) -> List[Playlist]:
        stmt = select(Playlist).where(Playlist.user_id == user_id)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def add_track_to_playlist(self, playlist_id: str, track_id: str, position: int = 1) -> PlaylistTrack:
        item = PlaylistTrack(playlist_id=playlist_id, track_id=track_id, position=position)
        self.session.add(item)
        await self.session.flush()
        return item
