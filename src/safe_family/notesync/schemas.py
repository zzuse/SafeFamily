"""Pydantic schemas for notesync payloads."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MediaPayload(BaseModel):
    id: str
    noteId: str
    kind: Literal["image", "audio"]
    filename: str
    contentType: str
    checksum: str
    dataBase64: str


class NotePayload(BaseModel):
    id: str
    text: str
    isPinned: bool
    tags: list[str]
    createdAt: datetime
    updatedAt: datetime
    deletedAt: datetime | None = None


class OperationPayload(BaseModel):
    opId: str
    opType: Literal["create", "update", "delete", "upsert"]
    note: NotePayload
    media: list[MediaPayload] = Field(default_factory=list)


class SyncRequest(BaseModel):
    ops: list[OperationPayload]


class SyncNoteResult(BaseModel):
    noteId: str
    result: Literal["applied", "skipped", "conflict"]
    note: NotePayload


class SyncResponse(BaseModel):
    results: list[SyncNoteResult]


class AuthExchangeRequest(BaseModel):
    code: str


class UserInfo(BaseModel):
    id: str
    username: str | None = None
    email: str | None = None


class AuthExchangeResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: UserInfo
