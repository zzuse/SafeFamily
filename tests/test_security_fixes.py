"""Regression tests for the November 2026 security audit fixes.

1. Registration is closed unless ALLOW_REGISTRATION is on; passwords need 8+ chars.
2. Todo routes act only for the owner or an admin.
3. State-changing admin routes are POST-only; cross-site writes are refused.
4. Note media that a browser could run as a page is sent as a download.
5. /auth/callback never reflects its code parameter as HTML.
"""

import io
from datetime import datetime
from types import SimpleNamespace

import pytest
from flask_jwt_extended import create_access_token

from src.safe_family.core import auth
from src.safe_family.core.extensions import db
from src.safe_family.core.models import Media, Note, Tag, User
from src.safe_family.todo import todo
from src.safe_family.urls import blocker

SETTINGS = "config.settings.settings"


def _make_user(user_id, username):
    user = User(id=user_id, username=username, email=f"{username}@example.com", role="user", is_approved=True)
    user.set_password("long-enough-password")
    db.session.add(user)
    db.session.commit()
    return user


def _login(app, client, user_id):
    with app.app_context():
        token = create_access_token(identity=user_id)
    with client.session_transaction() as sess:
        sess["access_token"] = token


# ---- 1. registration ------------------------------------------------------


def test_registration_is_closed_by_default(notesync_app, notesync_client, monkeypatch):
    monkeypatch.setattr(f"{SETTINGS}.ALLOW_REGISTRATION", False)
    body = {"username": "stranger", "email": "s@evil.test", "password": "long-enough-password"}

    assert notesync_client.post("/auth/register", json=body).status_code == 403
    assert User.query.count() == 0

    page = notesync_client.get("/auth/session-register", follow_redirects=True).get_data(as_text=True)
    assert "Registration is closed" in page
    topbar = page.split('<header class="sf-topbar">', 1)[1].split("</header>", 1)[0]
    assert "Register" not in topbar

    form = {"username": "s", "email": "s@evil.test", "password": "x" * 12, "confirm_password": "x" * 12}
    assert notesync_client.post("/auth/session-register", data=form).status_code == 302
    assert User.query.count() == 0


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"username": "a", "email": "a@a.test", "password": "1"}, "at least 8"),
        ({"username": "a", "email": "a@a.test"}, "at least 8"),
        ({"username": "", "email": "a@a.test", "password": "long-enough"}, "required"),
        ({"username": "a", "password": "long-enough"}, "required"),
        ({"username": "other", "email": "alice@example.com", "password": "long-enough"}, "Email already in use"),
    ],
)
def test_open_registration_validates_input(notesync_client, body, message):
    _make_user("u1", "alice")
    response = notesync_client.post("/auth/register", json=body)
    assert response.status_code == 400
    assert message in response.get_json()["message"]
    assert User.query.count() == 1


def test_register_rejects_non_json_body_without_crashing(notesync_client):
    response = notesync_client.post("/auth/register", data="not json", content_type="text/plain")
    assert response.status_code == 400


def test_register_form_shows_errors_instead_of_crashing(notesync_client):
    form = {"username": "bob", "email": "b@b.test", "password": "long-enough", "confirm_password": "different"}
    response = notesync_client.post("/auth/session-register", data=form)
    assert response.status_code == 200
    assert "Passwords do not match" in response.get_data(as_text=True)

    form["confirm_password"] = form["password"] = "short"
    response = notesync_client.post("/auth/session-register", data=form)
    assert response.status_code == 200
    assert "at least 8 characters" in response.get_data(as_text=True)
    assert User.query.count() == 0


class _FakeResp:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload

    def json(self):
        return self._payload


def test_first_time_github_login_refused_when_registration_closed(notesync_client, monkeypatch):
    monkeypatch.setattr(f"{SETTINGS}.ALLOW_REGISTRATION", False)
    monkeypatch.setattr(auth, "_oauth_provider_available", lambda name: True)
    monkeypatch.setattr(auth, "_read_oauth_state", lambda state: {"client": "web"})
    monkeypatch.setattr(auth.requests, "post", lambda *a, **k: _FakeResp({"access_token": "t"}))
    user_info = {"id": 4242, "email": "new@person.test", "name": "New", "login": "new"}
    monkeypatch.setattr(
        auth.requests,
        "get",
        lambda url, **k: _FakeResp([] if url.endswith("/emails") else user_info),
    )

    response = notesync_client.get("/auth/github/callback?state=s&code=c")

    assert response.headers["Location"].endswith("/auth/login-ui")
    assert User.query.count() == 0
    with notesync_client.session_transaction() as sess:
        assert "access_token" not in sess


def test_existing_github_user_can_still_log_in_when_registration_closed(notesync_client, monkeypatch):
    _make_user("4242", "known")
    monkeypatch.setattr(f"{SETTINGS}.ALLOW_REGISTRATION", False)
    monkeypatch.setattr(auth, "_oauth_provider_available", lambda name: True)
    monkeypatch.setattr(auth, "_read_oauth_state", lambda state: {"client": "web"})
    monkeypatch.setattr(auth.requests, "post", lambda *a, **k: _FakeResp({"access_token": "t"}))
    user_info = {"id": 4242, "email": "known@example.com", "name": "Known", "login": "known"}
    monkeypatch.setattr(
        auth.requests,
        "get",
        lambda url, **k: _FakeResp([] if url.endswith("/emails") else user_info),
    )

    notesync_client.get("/auth/github/callback?state=s&code=c")

    with notesync_client.session_transaction() as sess:
        assert sess["access_token"]


# ---- 2. todo ownership ----------------------------------------------------


class _Cursor:
    def __init__(self, row=None):
        self.row = row
        self.queries = []

    def execute(self, sql, params=None):
        self.queries.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.row

    def fetchall(self):
        return []

    def close(self):
        return None


class _Conn:
    def __init__(self, row=None):
        self.cursor_obj = _Cursor(row)

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        return None

    def close(self):
        return None


@pytest.fixture
def mallory(notesync_app, notesync_client, monkeypatch):
    """A logged-in normal user, with the raw todo DB stubbed out."""
    _make_user("m1", "mallory")
    _login(notesync_app, notesync_client, "m1")
    monkeypatch.setattr(todo, "send_email_notification", lambda *a, **k: None)
    monkeypatch.setattr(todo, "send_discord_notification", lambda *a, **k: None)
    return notesync_client


def _writes(conn):
    return [q for q, _ in conn.cursor_obj.queries if q.startswith(("UPDATE", "DELETE", "INSERT"))]


def test_can_act_for():
    alice = SimpleNamespace(username="alice", role="user")
    admin = SimpleNamespace(username="boss", role="admin")
    assert todo.can_act_for(alice, "alice")
    assert todo.can_act_for(admin, "alice")
    assert not todo.can_act_for(alice, "bob")
    assert not todo.can_act_for(None, "alice")


def test_user_cannot_edit_or_delete_another_users_todo(mallory, monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)

    assert mallory.post("/update_todo/alice", data={"todo_id": "7", "task_7": "hacked"}).status_code == 403
    assert mallory.post("/delete_todo/alice/7").status_code == 403
    assert conn.cursor_obj.queries == []


def test_user_can_still_edit_and_delete_their_own_todo(mallory, monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)

    assert mallory.post("/update_todo/mallory", data={"todo_id": "7", "task_7": "mine"}).status_code == 302
    assert mallory.post("/delete_todo/mallory/7").status_code == 302
    assert len(_writes(conn)) == 2


def test_user_cannot_mark_another_users_todo(mallory, monkeypatch):
    conn = _Conn(row=("00:00 - 00:30", "Study", "", "alice"))
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    response = mallory.post("/todo/mark_done", json={"id": 7, "completed": True})
    assert response.status_code == 403
    assert _writes(conn) == []

    conn = _Conn(row=(None, "00:00 - 00:30", "alice", "Study", "2000-01-01 00:00:00"))
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    response = mallory.post("/todo/mark_status", json={"id": 7, "status": "done"})
    assert response.status_code == 403
    assert _writes(conn) == []


def test_user_cannot_run_another_users_assigned_rule(mallory, monkeypatch):
    conn = _Conn(row=("Rule enable all traffic",))
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    ran = []
    monkeypatch.setattr(todo, "RULE_FUNCTIONS", {"Rule enable all traffic": lambda: ran.append(1)})

    assert mallory.post("/exec_rules/someone-else").status_code == 403
    assert ran == []
    assert conn.cursor_obj.queries == []


# ---- 3. CSRF --------------------------------------------------------------

ADMIN_ACTIONS = [
    "/rules_toggle/enable_all",
    "/rules_toggle/disable_all",
    "/rules_toggle/stop_all_traffic",
    "/rules_toggle/enable_all_traffic",
    "/delete_block/1",
    "/auto_push",
    "/auto_import",
]


@pytest.fixture
def admin_client(notesync_app, notesync_client):
    _make_user("admin", "boss")
    _login(notesync_app, notesync_client, "admin")
    return notesync_client


@pytest.mark.parametrize("url", ADMIN_ACTIONS)
def test_admin_actions_cannot_be_triggered_by_get(admin_client, url):
    # A GET can be fired by an <img> in a blog post or by any link; these
    # routes change filtering, so they must only answer POST.
    assert admin_client.get(url).status_code == 405


def test_admin_action_still_works_by_post(admin_client, monkeypatch):
    called = []
    monkeypatch.setattr(
        blocker,
        "rule_disable_all",
        lambda: (called.append(1), SimpleNamespace(status_code=200))[1],
    )
    assert admin_client.post("/rules_toggle/disable_all").status_code == 302
    assert called == [1]


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ({"Origin": "https://evil.example"}, 403),
        ({"Referer": "https://evil.example/page"}, 403),
        ({"Origin": "http://localhost"}, 302),
        ({"Referer": "http://localhost/suspicious"}, 302),
        ({"Origin": "null"}, 403),
        ({"Origin": "null", "Referer": "http://localhost/suspicious"}, 403),
        ({}, 302),
    ],
)
def test_cross_site_writes_are_refused(admin_client, monkeypatch, headers, status):
    called = []
    monkeypatch.setattr(
        blocker,
        "rule_disable_all",
        lambda: (called.append(1), SimpleNamespace(status_code=200))[1],
    )
    response = admin_client.post("/rules_toggle/disable_all", headers=headers)
    assert response.status_code == status
    assert bool(called) == (status == 302)


def test_cross_site_get_is_not_blocked(notesync_client):
    response = notesync_client.get("/auth/login-ui", headers={"Referer": "https://search.example/"})
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"


# ---- 4. note media --------------------------------------------------------


def _public_media(owner_id, filename, content_type, data=b"<script>alert(1)</script>"):
    now = datetime(2026, 11, 1)
    note = Note(id=f"n-{filename}", user_id=owner_id, text="x", is_pinned=False, created_at=now, updated_at=now)
    note.tags.append(Tag(id=f"t-{filename}", user_id=owner_id, name="public"))
    db.session.add(note)
    media = Media(
        id=f"m-{filename}",
        note_id=note.id,
        user_id=owner_id,
        kind="file",
        filename=filename,
        content_type=content_type,
        checksum="sha256:x",
        data=data,
        created_at=now,
    )
    db.session.add(media)
    db.session.commit()
    return media.id


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("a.html", "text/html"),
        ("a.html", "TEXT/HTML; charset=utf-8"),
        ("a.svg", "image/svg+xml"),
        ("a.xml", "application/xml"),
        ("a.bin", ""),
    ],
)
def test_scriptable_note_media_is_downloaded_not_rendered(notesync_app, notesync_client, filename, content_type):
    _make_user("v1", "victim")
    _login(notesync_app, notesync_client, "v1")
    media_id = _public_media("attacker", filename, content_type)

    response = notesync_client.get(f"/notes/media/{media_id}")

    assert response.status_code == 200
    assert response.mimetype == "application/octet-stream"
    assert response.headers["Content-Disposition"].startswith("attachment")
    assert response.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize(
    ("filename", "content_type", "served"),
    [("a.png", "image/png", "image/png"), ("a.m4a", "audio/x-m4a", "audio/mp4"), ("a.mp4", "video/mp4", "video/mp4")],
)
def test_real_media_still_displays_inline(notesync_app, notesync_client, filename, content_type, served):
    _make_user("v1", "victim")
    _login(notesync_app, notesync_client, "v1")
    media_id = _public_media("attacker", filename, content_type, data=b"\x89PNG")

    response = notesync_client.get(f"/notes/media/{media_id}")

    assert response.mimetype == served
    assert response.headers["Content-Disposition"].startswith("inline")


def test_html_upload_through_the_notes_page_is_not_rendered(notesync_app, notesync_client):
    _make_user("v1", "victim")
    _login(notesync_app, notesync_client, "v1")
    notesync_client.post(
        "/notes/upload",
        data={"text": "x", "media": (io.BytesIO(b"<script>alert(1)</script>"), "a.html", "text/html")},
        content_type="multipart/form-data",
    )
    response = notesync_client.get(f"/notes/media/{Media.query.one().id}")
    assert response.mimetype == "application/octet-stream"


# ---- 5. /auth/callback ----------------------------------------------------


def test_auth_callback_does_not_reflect_html(notesync_client):
    payload = "<script>alert(document.domain)</script>"
    response = notesync_client.get("/auth/callback", query_string={"code": payload})

    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert payload in response.get_data(as_text=True)

    missing = notesync_client.get("/auth/callback")
    assert missing.status_code == 400
    assert missing.mimetype == "text/plain"
