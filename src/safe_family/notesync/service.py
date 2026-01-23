"""Notesync service logic with last-write-wins semantics."""

import base64
import binascii
import logging
import uuid
from datetime import datetime

from src.safe_family.core.extensions import db
from src.safe_family.core.models import Media, Note, NoteSyncOp, Tag

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.utcnow()


def _naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.replace(tzinfo=None)


def _should_apply(existing: Note | None, incoming_ts: datetime) -> bool:
    if existing is None:
        return True
    return _naive(existing.updated_at) < incoming_ts


def _normalize_tags(tags: list[str]) -> list[str]:
    cleaned = []
    seen = set()
    for tag in tags:
        name = tag.strip()
        if not name or name in seen:
            continue
        cleaned.append(name)
        seen.add(name)
    return cleaned


def _max_timestamp(*values: datetime | None) -> datetime | None:
    timestamps = [value for value in values if value is not None]
    if not timestamps:
        return None
    return max(timestamps)


def _apply_delete(existing: Note | None, payload, user_id: str) -> tuple[Note, str]:
    incoming_ts = _max_timestamp(
        _naive(payload.updatedAt),
        _naive(payload.deletedAt),
    )
    deleted_at = _naive(payload.deletedAt) or incoming_ts
    existing_ts = _max_timestamp(
        _naive(existing.updated_at) if existing else None,
        _naive(existing.deleted_at) if existing else None,
    )
    if existing is not None and incoming_ts is not None and existing_ts is not None:
        should_apply = existing_ts < incoming_ts
    else:
        should_apply = existing is None
    if not should_apply:
        return existing, "skipped"
    if existing is None:
        note = Note(
            id=payload.id,
            user_id=user_id,
            text=payload.text or "",
            is_pinned=payload.isPinned,
            created_at=_naive(payload.createdAt),
            updated_at=incoming_ts,
            deleted_at=deleted_at,
        )
        db.session.add(note)
        return note, "applied"
    existing.updated_at = incoming_ts
    existing.deleted_at = deleted_at
    return existing, "applied"


def _apply_upsert(existing: Note | None, payload, user_id: str) -> tuple[Note, str]:
    incoming_ts = _naive(payload.updatedAt)
    if not _should_apply(existing, incoming_ts):
        return existing, "skipped"
    if existing is None:
        note = Note(
            id=payload.id,
            user_id=user_id,
            text=payload.text,
            is_pinned=payload.isPinned,
            created_at=_naive(payload.createdAt),
            updated_at=incoming_ts,
            deleted_at=_naive(payload.deletedAt),
        )
        db.session.add(note)
        return note, "applied"
    existing.text = payload.text
    existing.is_pinned = payload.isPinned
    existing.updated_at = incoming_ts
    existing.deleted_at = _naive(payload.deletedAt)
    return existing, "applied"


def _sync_tags(note: Note, tags: list[str], user_id: str) -> None:
    tag_names = _normalize_tags(tags)
    note.tags.clear()
    for name in tag_names:
        tag = Tag.query.filter_by(user_id=user_id, name=name).first()
        if tag is None:
            tag = Tag(id=uuid.uuid4().hex, user_id=user_id, name=name)
            db.session.add(tag)
        note.tags.append(tag)


def _sync_media(note: Note, media_payloads: list) -> None:
    existing_media = Media.query.filter_by(note_id=note.id, user_id=note.user_id).all()
    seen_checksums = {media.checksum for media in existing_media if media.checksum}
    for payload in media_payloads:
        checksum = payload.checksum.strip()
        media = Media.query.filter_by(id=payload.id, user_id=note.user_id).first()
        if media is None and checksum and checksum in seen_checksums:
            continue
        if checksum:
            seen_checksums.add(checksum)

        should_decode = media is None or media.checksum != checksum
        data = None
        if should_decode:
            try:
                data = base64.b64decode(
                    payload.dataBase64.encode("utf-8"),
                    validate=True,
                )
            except (ValueError, TypeError, binascii.Error):
                raise ValueError("invalid_base64") from None

        if media is None:
            media = Media(
                id=payload.id,
                note_id=note.id,
                user_id=note.user_id,
                kind=payload.kind,
                filename=payload.filename,
                content_type=payload.contentType,
                checksum=checksum,
                data=data,
                created_at=_now_utc(),
            )
            db.session.add(media)
        else:
            media.note_id = note.id
            media.kind = payload.kind
            media.filename = payload.filename
            media.content_type = payload.contentType
            media.checksum = checksum
            if data is not None:
                media.data = data


def apply_sync_ops(ops, user_id: str) -> list[tuple[Note | None, str, object]]:
    """Apply sync ops and return (note, result, op_note_payload) tuples."""
    results: list[tuple[Note | None, str, object]] = []
    for op in ops:
        incoming_updated_at = _naive(op.note.updatedAt)
        incoming_deleted_at = _naive(op.note.deletedAt)
        existing_op = NoteSyncOp.query.filter_by(
            user_id=user_id,
            op_id=op.opId,
        ).first()
        if existing_op is not None:
            note = Note.query.filter_by(id=op.note.id, user_id=user_id).first()
            if op.opType == "delete":
                logger.info(
                    "notesync skip user=%s op_id=%s note_id=%s op_type=%s reason=duplicate_op incoming_updated_at=%s incoming_deleted_at=%s",
                    user_id,
                    op.opId,
                    op.note.id,
                    op.opType,
                    incoming_updated_at,
                    incoming_deleted_at,
                )
            results.append((note, "skipped", op.note))
            continue

        note = Note.query.filter_by(id=op.note.id, user_id=user_id).first()
        if op.opType == "delete":
            note, result = _apply_delete(note, op.note, user_id)
        else:
            note, result = _apply_upsert(note, op.note, user_id)

        if result == "skipped" and op.opType == "delete":
            existing_updated_at = _naive(note.updated_at) if note else None
            existing_deleted_at = _naive(note.deleted_at) if note else None
            logger.info(
                "notesync skip user=%s op_id=%s note_id=%s op_type=%s reason=stale_update incoming_updated_at=%s incoming_deleted_at=%s existing_updated_at=%s existing_deleted_at=%s",
                user_id,
                op.opId,
                op.note.id,
                op.opType,
                incoming_updated_at,
                incoming_deleted_at,
                existing_updated_at,
                existing_deleted_at,
            )

        if result == "applied" and note is not None and op.opType != "delete":
            _sync_tags(note, op.note.tags, user_id)
            _sync_media(note, op.media)

        db.session.add(
            NoteSyncOp(
                user_id=user_id,
                op_id=op.opId,
                note_id=op.note.id,
                result=result,
                applied_at=_now_utc(),
            ),
        )
        results.append((note, result, op.note))

    db.session.commit()
    return results
