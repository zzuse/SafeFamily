"""Tests for miscellaneous routes like notes view/media."""

from datetime import datetime

from flask_jwt_extended import create_access_token

from src.safe_family.core.extensions import db
from src.safe_family.core.models import Media, Note, User
from src.safe_family.urls import miscellaneous


def _login_session(app, client, user_id):
    with app.app_context():
        token = create_access_token(identity=user_id)
    with client.session_transaction() as sess:
        sess["access_token"] = token


def test_notes_view_requires_login(notesync_app, notesync_client, monkeypatch):
    monkeypatch.setattr(miscellaneous, "render_template", lambda *a, **k: ("ok", 200))

    resp = notesync_client.get("/notes")

    assert resp.status_code == 302
    assert resp.location.endswith("/auth/login-ui")


def test_notes_view_renders(notesync_app, notesync_client, monkeypatch):
    with notesync_app.app_context():
        user = User(id="u-notes", username="alice", email="a@example.com")
        user.set_password("secret")
        note = Note(
            id="n1",
            user_id="u-notes",
            text="hello",
            is_pinned=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            deleted_at=None,
        )
        db.session.add_all([user, note])
        db.session.commit()

    _login_session(notesync_app, notesync_client, "u-notes")
    monkeypatch.setattr(miscellaneous, "render_template", lambda *a, **k: ("ok", 200))

    resp = notesync_client.get("/notes")

    assert resp.status_code == 200


def test_notes_media_404(notesync_app, notesync_client):
    with notesync_app.app_context():
        user = User(id="u-media", username="alice", email="a@example.com")
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()

    _login_session(notesync_app, notesync_client, "u-media")

    resp = notesync_client.get("/notes/media/missing")

    assert resp.status_code == 404


def test_notes_media_success(notesync_app, notesync_client):
    with notesync_app.app_context():
        user = User(id="u-media2", username="alice", email="a@example.com")
        user.set_password("secret")
        note = Note(
            id="n2",
            user_id="u-media2",
            text="hello",
            is_pinned=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            deleted_at=None,
        )
        media = Media(
            id="m1",
            note_id="n2",
            user_id="u-media2",
            kind="image",
            filename="photo.jpg",
            content_type="image/jpeg",
            checksum="sha256:abc",
            data=b"hello",
            created_at=datetime.utcnow(),
        )
        db.session.add_all([user, note, media])
        db.session.commit()

    _login_session(notesync_app, notesync_client, "u-media2")

    resp = notesync_client.get("/notes/media/m1")

    assert resp.status_code == 200
    assert resp.mimetype == "image/jpeg"
