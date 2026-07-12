"""Tests for miscellaneous routes like notes view/media."""

import io
from datetime import datetime

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


def test_upload_note_with_text_and_tags(notesync_app, notesync_client):
    with notesync_app.app_context():
        user = User(id="u-up1", username="alice", email="a@example.com")
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()

    _login_session(notesync_app, notesync_client, "u-up1")

    resp = notesync_client.post(
        "/notes/upload",
        data={"text": "from the browser", "tags": "Web, ideas , web"},
    )

    assert resp.status_code == 302
    assert resp.location.endswith("/notes")
    with notesync_app.app_context():
        note = Note.query.filter_by(user_id="u-up1").one()
        assert note.text == "from the browser"
        assert note.deleted_at is None
        assert sorted(tag.name for tag in note.tags) == ["ideas", "web"]


def test_upload_note_with_media_file(notesync_app, notesync_client):
    with notesync_app.app_context():
        user = User(id="u-up2", username="bob", email="b@example.com")
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()

    _login_session(notesync_app, notesync_client, "u-up2")

    resp = notesync_client.post(
        "/notes/upload",
        data={
            "text": "",
            "media": (io.BytesIO(b"fake-image-bytes"), "photo.jpg", "image/jpeg"),
        },
        content_type="multipart/form-data",
    )

    assert resp.status_code == 302
    with notesync_app.app_context():
        note = Note.query.filter_by(user_id="u-up2").one()
        media = Media.query.filter_by(note_id=note.id).one()
        assert media.kind == "image"
        assert media.filename == "photo.jpg"
        assert media.content_type == "image/jpeg"
        assert media.data == b"fake-image-bytes"
        assert media.checksum.startswith("sha256:")


def test_upload_note_audio_kind(notesync_app, notesync_client):
    with notesync_app.app_context():
        user = User(id="u-up4", username="dave", email="d@example.com")
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()

    _login_session(notesync_app, notesync_client, "u-up4")

    resp = notesync_client.post(
        "/notes/upload",
        data={"media": (io.BytesIO(b"fake-audio"), "memo.m4a", "audio/mp4")},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 302
    with notesync_app.app_context():
        media = Media.query.filter_by(user_id="u-up4").one()
        assert media.kind == "audio"


def test_delete_note_removes_note_and_media(notesync_app, notesync_client):
    with notesync_app.app_context():
        user = User(id="u-del", username="erin", email="e@example.com")
        user.set_password("secret")
        note = Note(
            id="n-del",
            user_id="u-del",
            text="to delete",
            is_pinned=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            deleted_at=None,
        )
        media = Media(
            id="m-del",
            note_id="n-del",
            user_id="u-del",
            kind="image",
            filename="gone.jpg",
            content_type="image/jpeg",
            checksum="sha256:xyz",
            data=b"bytes",
            created_at=datetime.utcnow(),
        )
        db.session.add_all([user, note, media])
        db.session.commit()

    _login_session(notesync_app, notesync_client, "u-del")

    resp = notesync_client.post("/notes/delete/n-del")

    assert resp.status_code == 302
    with notesync_app.app_context():
        assert Note.query.get("n-del") is None
        assert Media.query.get("m-del") is None


def test_delete_note_404_for_other_users_note(notesync_app, notesync_client):
    with notesync_app.app_context():
        owner = User(id="u-del-o", username="frank", email="f@example.com")
        owner.set_password("secret")
        intruder = User(id="u-del-i", username="grace", email="g@example.com")
        intruder.set_password("secret")
        note = Note(
            id="n-del-2",
            user_id="u-del-o",
            text="not yours",
            is_pinned=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            deleted_at=None,
        )
        db.session.add_all([owner, intruder, note])
        db.session.commit()

    _login_session(notesync_app, notesync_client, "u-del-i")

    resp = notesync_client.post("/notes/delete/n-del-2")

    assert resp.status_code == 404
    with notesync_app.app_context():
        assert Note.query.get("n-del-2") is not None


def test_upload_note_rejects_empty_submission(notesync_app, notesync_client):
    with notesync_app.app_context():
        user = User(id="u-up3", username="carol", email="c@example.com")
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()

    _login_session(notesync_app, notesync_client, "u-up3")

    resp = notesync_client.post("/notes/upload", data={"text": "   "})

    assert resp.status_code == 302
    with notesync_app.app_context():
        assert Note.query.filter_by(user_id="u-up3").count() == 0
