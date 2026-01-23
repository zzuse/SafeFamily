"""Tests for notesync tag and media syncing."""

import base64
from datetime import datetime

from src.safe_family.core.extensions import db
from src.safe_family.core.models import Media, Note, Tag
from src.safe_family.notesync.schemas import SyncRequest
from src.safe_family.notesync.service import apply_sync_ops


def test_notesync_creates_tags_and_media(notesync_app):
    user_id = "user-tags"
    now = datetime.utcnow()
    raw_data = b"hello"
    encoded = base64.b64encode(raw_data).decode("utf-8")
    payload = {
        "ops": [
            {
                "opId": "op-tags",
                "opType": "create",
                "note": {
                    "id": "note-tags",
                    "text": "note",
                    "isPinned": False,
                    "tags": ["Work", "home", "Work"],
                    "createdAt": now,
                    "updatedAt": now,
                    "deletedAt": None,
                },
                "media": [
                    {
                        "id": "media-1",
                        "noteId": "note-tags",
                        "kind": "image",
                        "filename": "photo.jpg",
                        "contentType": "image/jpeg",
                        "checksum": "sha256:abc",
                        "dataBase64": encoded,
                    },
                ],
            },
        ],
    }
    req = SyncRequest.model_validate(payload)
    with notesync_app.app_context():
        results = apply_sync_ops(req.ops, user_id=user_id)
        assert results[0][1] == "applied"

        note = Note.query.filter_by(id="note-tags", user_id=user_id).first()
        assert note is not None

        tags = Tag.query.filter_by(user_id=user_id).all()
        tag_names = sorted(tag.name for tag in tags)
        assert tag_names == ["Work", "home"]
        assert sorted(tag.name for tag in note.tags) == ["Work", "home"]

        media = Media.query.filter_by(id="media-1", user_id=user_id).first()
        assert media is not None
        assert media.data == raw_data
        assert media.note_id == "note-tags"


def test_notesync_media_updates(notesync_app):
    user_id = "user-media"
    now = datetime.utcnow()
    raw_data = b"first"
    encoded = base64.b64encode(raw_data).decode("utf-8")
    payload = {
        "ops": [
            {
                "opId": "op-media",
                "opType": "create",
                "note": {
                    "id": "note-media",
                    "text": "note",
                    "isPinned": False,
                    "tags": [],
                    "createdAt": now,
                    "updatedAt": now,
                    "deletedAt": None,
                },
                "media": [
                    {
                        "id": "media-2",
                        "noteId": "note-media",
                        "kind": "audio",
                        "filename": "clip.m4a",
                        "contentType": "audio/mp4",
                        "checksum": "sha256:one",
                        "dataBase64": encoded,
                    },
                ],
            },
        ],
    }
    req = SyncRequest.model_validate(payload)
    with notesync_app.app_context():
        apply_sync_ops(req.ops, user_id=user_id)

        updated_data = b"second"
        payload["ops"][0]["opId"] = "op-media-2"
        payload["ops"][0]["note"]["updatedAt"] = datetime.utcnow()
        payload["ops"][0]["media"][0]["checksum"] = "sha256:two"
        payload["ops"][0]["media"][0]["dataBase64"] = base64.b64encode(updated_data).decode("utf-8")

        req = SyncRequest.model_validate(payload)
        apply_sync_ops(req.ops, user_id=user_id)

        media = Media.query.filter_by(id="media-2", user_id=user_id).first()
        assert media is not None
        assert media.data == updated_data


def test_notesync_skips_duplicate_checksum(notesync_app):
    user_id = "user-dup"
    now = datetime.utcnow()
    raw_data = b"dup"
    encoded = base64.b64encode(raw_data).decode("utf-8")
    payload = {
        "ops": [
            {
                "opId": "op-dup-1",
                "opType": "create",
                "note": {
                    "id": "note-dup",
                    "text": "note",
                    "isPinned": False,
                    "tags": [],
                    "createdAt": now,
                    "updatedAt": now,
                    "deletedAt": None,
                },
                "media": [
                    {
                        "id": "media-dup-1",
                        "noteId": "note-dup",
                        "kind": "image",
                        "filename": "photo.jpg",
                        "contentType": "image/jpeg",
                        "checksum": "sha256:same",
                        "dataBase64": encoded,
                    },
                ],
            },
        ],
    }
    req = SyncRequest.model_validate(payload)
    with notesync_app.app_context():
        apply_sync_ops(req.ops, user_id=user_id)

        payload["ops"][0]["opId"] = "op-dup-2"
        payload["ops"][0]["note"]["updatedAt"] = datetime.utcnow()
        payload["ops"][0]["media"][0]["id"] = "media-dup-2"
        req = SyncRequest.model_validate(payload)
        apply_sync_ops(req.ops, user_id=user_id)

        media = Media.query.filter_by(user_id=user_id).all()

    assert len(media) == 1
