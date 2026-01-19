"""Tests for notesync auth enforcement."""

from flask_jwt_extended import create_access_token

from src.safe_family.core.extensions import db
from src.safe_family.core.models import User


def _auth_headers(app, user_id, api_key="test-api-key"):
    with app.app_context():
        token = create_access_token(identity=user_id)
    return {"Authorization": f"Bearer {token}", "X-API-Key": api_key}


def test_notesync_requires_api_key(notesync_client):
    resp = notesync_client.post("/api/notesync", json={"ops": []})
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "unauthorized"


def test_notesync_requires_jwt(notesync_client):
    resp = notesync_client.post(
        "/api/notesync",
        json={"ops": []},
        headers={"X-API-Key": "test-api-key"},
    )
    assert resp.status_code == 401


def test_notesync_accepts_auth(notesync_app, notesync_client, monkeypatch):
    monkeypatch.setattr(
        "src.safe_family.api.routes.apply_sync_ops",
        lambda ops, user_id: [],
    )
    with notesync_app.app_context():
        user = User(id="user-1", username="user", email="user@example.com")
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()
    headers = _auth_headers(notesync_app, "user-1")
    resp = notesync_client.post("/api/notesync", json={"ops": []}, headers=headers)
    assert resp.status_code == 200
    assert resp.get_json() == {"results": []}
