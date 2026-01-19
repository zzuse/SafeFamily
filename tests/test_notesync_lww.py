"""Tests for notesync last-write-wins behavior."""

from datetime import datetime, timedelta

from src.safe_family.core.extensions import db
from src.safe_family.core.models import Note
from src.safe_family.notesync.schemas import SyncRequest
from src.safe_family.notesync.service import apply_sync_ops


def test_lww_skips_older_update(notesync_app):
    user_id = "user-1"
    now = datetime.utcnow()
    older = now - timedelta(minutes=5)
    with notesync_app.app_context():
        note = Note(
            id="n1",
            user_id=user_id,
            text="newer",
            is_pinned=False,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        db.session.add(note)
        db.session.commit()

        payload = {
            "ops": [
                {
                    "opId": "op1",
                    "opType": "update",
                    "note": {
                        "id": "n1",
                        "text": "older",
                        "isPinned": False,
                        "tags": [],
                        "createdAt": now,
                        "updatedAt": older,
                        "deletedAt": None,
                    },
                    "media": [],
                },
            ],
        }
        req = SyncRequest.model_validate(payload)
        results = apply_sync_ops(req.ops, user_id=user_id)

        db.session.refresh(note)

    assert results[0][1] == "skipped"
    assert note.text == "newer"


def test_delete_tombstone_applies(notesync_app):
    user_id = "user-2"
    now = datetime.utcnow()
    newer = now + timedelta(minutes=5)
    with notesync_app.app_context():
        note = Note(
            id="n2",
            user_id=user_id,
            text="hello",
            is_pinned=False,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        db.session.add(note)
        db.session.commit()

        payload = {
            "ops": [
                {
                    "opId": "op2",
                    "opType": "delete",
                    "note": {
                        "id": "n2",
                        "text": "hello",
                        "isPinned": False,
                        "tags": [],
                        "createdAt": now,
                        "updatedAt": newer,
                        "deletedAt": None,
                    },
                    "media": [],
                },
            ],
        }
        req = SyncRequest.model_validate(payload)
        results = apply_sync_ops(req.ops, user_id=user_id)
        db.session.refresh(note)

    assert results[0][1] == "applied"
    assert note.deleted_at == newer


def test_idempotent_ops_skip(notesync_app):
    user_id = "user-3"
    now = datetime.utcnow()
    with notesync_app.app_context():
        payload = {
            "ops": [
                {
                    "opId": "op3",
                    "opType": "create",
                    "note": {
                        "id": "n3",
                        "text": "hello",
                        "isPinned": False,
                        "tags": ["work"],
                        "createdAt": now,
                        "updatedAt": now,
                        "deletedAt": None,
                    },
                    "media": [],
                },
            ],
        }
        req = SyncRequest.model_validate(payload)
        results = apply_sync_ops(req.ops, user_id=user_id)
        assert results[0][1] == "applied"

        results = apply_sync_ops(req.ops, user_id=user_id)

    assert results[0][1] == "skipped"
