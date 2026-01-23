"""Tests for notesync API routes."""

from datetime import datetime, timedelta

from flask_jwt_extended import create_access_token

from src.safe_family.core.extensions import db
from src.safe_family.core.models import Note, User


def _create_user(user_id="user-1"):
    user = User(id=user_id, username="alice", email="a@example.com")
    user.set_password("secret")
    db.session.add(user)
    db.session.commit()
    return user


def _auth_headers(app, user_id, api_key="test-api-key"):
    with app.app_context():
        token = create_access_token(identity=user_id)
    return {"Authorization": f"Bearer {token}", "X-API-Key": api_key}


def test_notesync_rejects_invalid_request(notesync_app, notesync_client):
    with notesync_app.app_context():
        _create_user("u-json")
    headers = _auth_headers(notesync_app, "u-json")
    resp = notesync_client.post(
        "/api/notesync",
        json={"ops": "bad"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_request"


def test_notesync_rejects_invalid_base64(notesync_app, notesync_client):
    now = datetime.utcnow().isoformat()
    with notesync_app.app_context():
        _create_user("u-base64")
    headers = _auth_headers(notesync_app, "u-base64")
    resp = notesync_client.post(
        "/api/notesync",
        json={
            "ops": [
                {
                    "opId": "op-base64",
                    "opType": "create",
                    "note": {
                        "id": "note-base64",
                        "text": "note",
                        "isPinned": False,
                        "tags": [],
                        "createdAt": now,
                        "updatedAt": now,
                        "deletedAt": None,
                    },
                    "media": [
                        {
                            "id": "media-base64",
                            "noteId": "note-base64",
                            "kind": "image",
                            "filename": "photo.jpg",
                            "contentType": "image/jpeg",
                            "checksum": "sha256:bad",
                            "dataBase64": "not-base64",
                        }
                    ],
                }
            ]
        },
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_base64"


def test_get_notes_rejects_invalid_limit(notesync_app, notesync_client):
    with notesync_app.app_context():
        _create_user("u-limit")
    headers = _auth_headers(notesync_app, "u-limit")
    resp = notesync_client.get("/api/notes?limit=0", headers=headers)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_limit"


def test_get_notes_rejects_non_numeric_limit(notesync_app, notesync_client):
    with notesync_app.app_context():
        _create_user("u-limit2")
    headers = _auth_headers(notesync_app, "u-limit2")
    resp = notesync_client.get("/api/notes?limit=abc", headers=headers)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_limit"


def test_get_notes_requires_identity(notesync_app, notesync_client, monkeypatch):
    with notesync_app.app_context():
        _create_user("u-none")
    headers = _auth_headers(notesync_app, "u-none")
    monkeypatch.setattr("src.safe_family.api.routes.get_jwt_identity", lambda: None)

    resp = notesync_client.get("/api/notes?limit=1", headers=headers)

    assert resp.status_code == 401


def test_get_notes_returns_recent_notes(notesync_app, notesync_client):
    user_id = "u-notes"
    now = datetime.utcnow()
    with notesync_app.app_context():
        _create_user(user_id)
        newer = Note(
            id="n1",
            user_id=user_id,
            text="new",
            is_pinned=False,
            created_at=now,
            updated_at=now + timedelta(minutes=1),
            deleted_at=None,
        )
        deleted = Note(
            id="n2",
            user_id=user_id,
            text="deleted",
            is_pinned=False,
            created_at=now,
            updated_at=now,
            deleted_at=now,
        )
        db.session.add_all([newer, deleted])
        db.session.commit()
    headers = _auth_headers(notesync_app, user_id)
    resp = notesync_client.get("/api/notes?limit=10", headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["notes"]) == 1
    assert data["notes"][0]["id"] == "n1"
    assert data["media"] == []
