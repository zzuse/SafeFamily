"""Pydantic schemas for notesync payloads."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_serializer


class MediaPayload(BaseModel):
    """Media attachment payload from the mobile app."""

    id: str
    noteId: str
    kind: Literal["image", "audio"]
    filename: str
    contentType: str
    checksum: str
    dataBase64: str


class NotePayload(BaseModel):
    """Note payload from the mobile app."""

    id: str
    text: str
    isPinned: bool
    tags: list[str]
    createdAt: datetime
    updatedAt: datetime
    deletedAt: datetime | None = None

    @field_serializer("createdAt", "updatedAt", "deletedAt", when_used="json")
    def _serialize_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        else:
            value = value.astimezone(UTC)
        return value.isoformat().replace("+00:00", "Z")


class OperationPayload(BaseModel):
    """One sync operation (op id, type, note, media)."""

    opId: str
    opType: Literal["create", "update", "delete", "upsert"]
    note: NotePayload
    media: list[MediaPayload] = Field(default_factory=list)


class SyncRequest(BaseModel):
    """Body of POST /api/notesync."""

    ops: list[OperationPayload]


class SyncNoteResult(BaseModel):
    """Per-note outcome of a sync operation."""

    noteId: str
    result: Literal["applied", "skipped", "conflict"]
    note: NotePayload


class SyncResponse(BaseModel):
    """Response body of POST /api/notesync."""

    results: list[SyncNoteResult]


class AuthExchangeRequest(BaseModel):
    """Body of POST /api/auth/exchange."""

    code: str


class UserInfo(BaseModel):
    """Minimal user identity returned to the mobile app."""

    id: str
    username: str | None = None
    email: str | None = None


class AuthExchangeResponse(BaseModel):
    """JWT token pair returned by the auth exchange."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: UserInfo
