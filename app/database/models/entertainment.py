"""Music entertainment, tracks, playlists, and resident favourites models."""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base, UUIDPrimaryKeyMixin, TimestampMixin, utc_now


class Track(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Catalogued musical track with streaming or audio playback URI."""
    __tablename__ = "tracks"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    artist: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    album: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    genre: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=180, nullable=False)
    media_url: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="local", nullable=False)


class Playlist(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Personal playlist created by or curated for an elderly resident."""
    __tablename__ = "playlists"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    household_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("households.id", ondelete="SET NULL"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Relationships
    tracks: Mapped[List["PlaylistTrack"]] = relationship("PlaylistTrack", back_populates="playlist", cascade="all, delete-orphan")


class PlaylistTrack(Base, UUIDPrimaryKeyMixin):
    """Association of tracks within a playlist in designated playback order."""
    __tablename__ = "playlist_tracks"

    playlist_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("playlists.id", ondelete="CASCADE"), index=True, nullable=False
    )
    track_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tracks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Relationships
    playlist: Mapped["Playlist"] = relationship("Playlist", back_populates="tracks")
    track: Mapped["Track"] = relationship("Track")


class UserFavorite(Base, UUIDPrimaryKeyMixin):
    """User favourite track indicator."""
    __tablename__ = "user_favorites"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    track_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tracks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)
