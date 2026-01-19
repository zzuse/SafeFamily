"""Tests for auth code exchange endpoint."""

from src.safe_family.core.auth import create_auth_code
from src.safe_family.core.extensions import db
from src.safe_family.core.models import User


def _create_user(user_id="u1"):
    user = User(id=user_id, username="alice", email="a@a.com")
    user.set_password("secret")
    db.session.add(user)
    db.session.commit()
    return user


def test_auth_exchange_success(notesync_app, notesync_client):
    with notesync_app.app_context():
        user = _create_user()
        code = create_auth_code(user.id)

    resp = notesync_client.post("/api/auth/exchange", json={"code": code})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["access_token"]
    assert data["token_type"] == "Bearer"
    assert data["user"]["id"] == "u1"


def test_auth_exchange_rejects_invalid_code(notesync_client):
    resp = notesync_client.post("/api/auth/exchange", json={"code": "invalid"})
    assert resp.status_code == 400


def test_auth_exchange_rejects_reuse(notesync_app, notesync_client):
    with notesync_app.app_context():
        user = _create_user("u2")
        code = create_auth_code(user.id)

    first = notesync_client.post("/api/auth/exchange", json={"code": code})
    assert first.status_code == 200

    second = notesync_client.post("/api/auth/exchange", json={"code": code})
    assert second.status_code == 400
