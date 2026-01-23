"""Tests for miscellaneous routes like notes view/media."""

from datetime import datetime, timedelta

from flask_jwt_extended import create_access_token

from src.safe_family.core.extensions import db
from src.safe_family.core.models import Media, Note, Tag, User
from src.safe_family.urls import notes


def _login_session(app, client, user_id):
    with app.app_context():
        token = create_access_token(identity=user_id)
    with client.session_transaction() as sess:
        sess["access_token"] = token


def test_notes_view_requires_login(notesync_app, notesync_client, monkeypatch):
    monkeypatch.setattr(notes, "render_template", lambda *a, **k: ("ok", 200))

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
    monkeypatch.setattr(notes, "render_template", lambda *a, **k: ("ok", 200))

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


def test_notes_media_public_note_for_other_user(notesync_app, notesync_client):
    with notesync_app.app_context():
        owner = User(id="u-owner", username="owner", email="owner@example.com")
        owner.set_password("secret")
        viewer = User(id="u-viewer", username="viewer", email="viewer@example.com")
        viewer.set_password("secret")
        note = Note(
            id="n-public",
            user_id="u-owner",
            text="public note",
            is_pinned=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            deleted_at=None,
        )
        tag = Tag(id="t-public", user_id="u-owner", name="public")
        note.tags.append(tag)
        media = Media(
            id="m-public",
            note_id="n-public",
            user_id="u-owner",
            kind="image",
            filename="public.jpg",
            content_type="image/jpeg",
            checksum="sha256:def",
            data=b"public",
            created_at=datetime.utcnow(),
        )
        db.session.add_all([owner, viewer, note, tag, media])
        db.session.commit()

    _login_session(notesync_app, notesync_client, "u-viewer")

    resp = notesync_client.get("/notes/media/m-public")

    assert resp.status_code == 200
    assert resp.mimetype == "image/jpeg"


def test_timeline_caps_three_public_notes_per_user(
    notesync_app,
    notesync_client,
    monkeypatch,
):
    with notesync_app.app_context():
        owner = User(id="u-cap-owner", username="owner", email="owner@example.com")
        owner.set_password("secret")
        viewer = User(id="u-cap-viewer", username="viewer", email="viewer@example.com")
        viewer.set_password("secret")
        tag = Tag(id="t-cap-public", user_id="u-cap-owner", name="public")
        base = datetime.utcnow()
        notes_list = []
        for i in range(4):
            created_at = base + timedelta(minutes=i)
            note = Note(
                id=f"n-cap-{i}",
                user_id="u-cap-owner",
                text=f"note {i}",
                is_pinned=False,
                created_at=created_at,
                updated_at=created_at,
                deleted_at=None,
            )
            note.tags.append(tag)
            notes_list.append(note)
        db.session.add_all([owner, viewer, tag, *notes_list])
        db.session.commit()

    _login_session(notesync_app, notesync_client, "u-cap-viewer")

    captured = {}

    def _capture(template, **context):
        captured.update(context)
        return ("ok", 200)

    monkeypatch.setattr(notes, "render_template", _capture)

    resp = notesync_client.get("/timeline")

    assert resp.status_code == 200
    assert "entries" in captured
    assert len(captured["entries"]) == 1
    returned_ids = [note.id for note in captured["entries"][0]["notes"]]
    assert returned_ids == ["n-cap-3", "n-cap-2", "n-cap-1"]
