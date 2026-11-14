"""Tests for open sign-up with admin approval, OAuth account matching and unique usernames."""

from types import SimpleNamespace

import pytest
from flask import render_template
from flask_jwt_extended import create_access_token

from src.safe_family.core import auth
from src.safe_family.core.extensions import db
from src.safe_family.core.models import BlogPost, User
from src.safe_family.todo import todo
from src.safe_family.urls import blocker

SETTINGS = "config.settings.settings"


def _make_user(user_id, username, *, approved=False, email=None):
    user = User(
        id=user_id,
        username=username,
        email=email or f"{username}@example.com",
        role="user",
        is_approved=approved,
    )
    user.set_password("long-enough-password")
    db.session.add(user)
    db.session.commit()
    return user


def _login(app, client, user_id):
    with app.app_context():
        token = create_access_token(identity=user_id)
    with client.session_transaction() as sess:
        sess["access_token"] = token


@pytest.fixture
def newcomer(notesync_app, notesync_client):
    """A logged-in account nobody has approved yet."""
    _make_user("11111111-aaaa-bbbb-cccc-000000000001", "newcomer")
    _login(notesync_app, notesync_client, "11111111-aaaa-bbbb-cccc-000000000001")
    return notesync_client


@pytest.fixture
def relative(notesync_app, notesync_client):
    """A logged-in account the admin approved."""
    _make_user("fam1", "relative", approved=True)
    _login(notesync_app, notesync_client, "fam1")
    return notesync_client


# ---- sign-up is open, new accounts are unapproved --------------------------


def test_registration_is_open_by_default():
    from config.settings import Settings

    assert Settings.ALLOW_REGISTRATION is True


def test_new_account_starts_unapproved(notesync_client):
    body = {"username": "anyone", "email": "anyone@example.com", "password": "long-enough-password"}
    assert notesync_client.post("/auth/register", json=body).status_code == 201
    user = User.query.filter_by(username="anyone").one()
    assert user.is_approved is False
    assert not auth.is_family(user)


def test_is_family():
    assert auth.is_family(SimpleNamespace(role="admin", is_approved=False))
    assert auth.is_family(SimpleNamespace(role="user", is_approved=True))
    assert not auth.is_family(SimpleNamespace(role="user", is_approved=False))
    assert not auth.is_family(SimpleNamespace(role="user"))
    assert not auth.is_family(None)


def test_login_tells_unapproved_account_it_is_waiting(notesync_client):
    _make_user("11111111-aaaa-bbbb-cccc-000000000002", "waiting")
    form = {"username": "waiting", "password": "long-enough-password"}
    notesync_client.post("/auth/session-login", data=form)
    with notesync_client.session_transaction() as sess:
        messages = [text for _category, text in sess.get("_flashes", [])]
    assert auth.NOT_APPROVED in messages


# ---- what an unapproved account cannot do ----------------------------------


def _watch_disable_ai(monkeypatch):
    called = []
    monkeypatch.setattr(
        blocker,
        "rule_disable_ai",
        lambda: (called.append(1), SimpleNamespace(status_code=200))[1],
    )
    monkeypatch.setitem(blocker.DISABLE_AI_STATE, "last_run", -1e9)
    return called


def test_unapproved_account_cannot_change_the_filter(newcomer, monkeypatch):
    called = _watch_disable_ai(monkeypatch)
    response = newcomer.post("/rules_toggle/disable_ai")
    assert response.status_code == 302
    assert called == []


def test_approved_account_can_use_its_rule_button(relative, monkeypatch):
    called = _watch_disable_ai(monkeypatch)
    relative.post("/rules_toggle/disable_ai")
    assert called == [1]


def test_disable_ai_still_requires_login(notesync_client, monkeypatch):
    called = _watch_disable_ai(monkeypatch)
    response = notesync_client.post("/rules_toggle/disable_ai")
    assert "/auth/login-ui" in response.headers["Location"]
    assert called == []


class _Conn:
    def __init__(self):
        self.queries = []

    def cursor(self):
        return self

    def execute(self, sql, params=None):
        self.queries.append(sql)

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def commit(self):
        return None

    def close(self):
        return None


def test_unapproved_account_cannot_run_rules_or_notify(newcomer, monkeypatch):
    conn = _Conn()
    sent = []
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    monkeypatch.setattr(todo, "send_email_notification", lambda *a, **k: sent.append("email"))
    monkeypatch.setattr(todo, "send_discord_notification", lambda *a, **k: sent.append("discord"))

    own_id = "11111111-aaaa-bbbb-cccc-000000000001"
    assert newcomer.post(f"/exec_rules/{own_id}").status_code == 302
    assert conn.queries == []

    # Their own todo list still works, but nothing is sent to the family's inbox.
    assert newcomer.post("/update_todo/newcomer", data={"todo_id": "1", "task_1": "x"}).status_code == 302
    assert any(q.strip().startswith("UPDATE") for q in conn.queries)
    assert sent == []


def test_approved_account_still_notifies(relative, monkeypatch):
    sent = []
    monkeypatch.setattr(todo, "get_db_connection", _Conn)
    monkeypatch.setattr(todo, "send_email_notification", lambda *a, **k: sent.append("email"))
    monkeypatch.setattr(todo, "send_discord_notification", lambda *a, **k: sent.append("discord"))
    relative.post("/update_todo/relative", data={"todo_id": "1", "task_1": "x"})
    assert sent == ["email", "discord"]


def test_unapproved_account_cannot_publish_publicly(newcomer, notesync_client):
    form = {"title": "Hello", "markdown": "spam", "is_public": "on"}
    response = newcomer.post("/blog/new", data=form, follow_redirects=True)
    assert "publishing needs the admin" in response.get_data(as_text=True)
    post = BlogPost.query.one()
    assert post.is_public is False

    newcomer.post(f"/blog/{post.id}/edit", data=form)
    assert BlogPost.query.one().is_public is False


def test_approved_account_can_publish(relative):
    relative.post("/blog/new", data={"title": "Hello", "markdown": "news", "is_public": "on"})
    assert BlogPost.query.one().is_public is True


# ---- admin approval ---------------------------------------------------------


def test_admin_approves_and_removes_approval(notesync_app, notesync_client):
    _make_user("admin", "boss")
    target = _make_user("11111111-aaaa-bbbb-cccc-000000000003", "cousin")
    _login(notesync_app, notesync_client, "admin")

    response = notesync_client.post(f"/users/{target.id}/approve")
    assert response.headers["Location"].endswith("/suspicious")
    assert db.session.get(User, target.id).is_approved is True

    notesync_client.post(f"/users/{target.id}/approve", data={"approved": "0"})
    assert db.session.get(User, target.id).is_approved is False

    assert notesync_client.post("/users/nobody/approve").status_code == 404
    assert notesync_client.get(f"/users/{target.id}/approve").status_code == 405


def test_only_admin_can_approve(relative):
    target = _make_user("11111111-aaaa-bbbb-cccc-000000000004", "friend")
    response = relative.post(f"/users/{target.id}/approve")
    assert "/auth/login-ui" in response.headers["Location"]
    assert db.session.get(User, target.id).is_approved is False
    # ...and not themselves either.
    relative.post("/users/fam1/approve", data={"approved": "1"})
    assert db.session.get(User, target.id).is_approved is False


def test_mgmt_page_lists_accounts_waiting_first(notesync_app):
    from src.safe_family.users.users import accounts_for_admin

    _make_user("fam1", "aaron", approved=True)
    _make_user("11111111-aaaa-bbbb-cccc-000000000005", "zoe")
    accounts = accounts_for_admin()
    assert [a.username for a in accounts] == ["zoe", "aaron"]

    with notesync_app.test_request_context("/suspicious"):
        html = render_template(
            "rules/suspicious_view.html",
            accounts=accounts, suspicious_data=[], block_list=[], filter_rules=[], block_types=[],
            page=1, total=0, limit=10, block_page=1, total_blocks=0, block_limit=10,
            rule_page=1, total_rules=0, rule_limit=10, date="2026-11-14", error=None,
        )  # fmt: skip
    card = html.split("mgmt-accounts", 1)[1].split("Suspicious Logs", 1)[0]
    assert card.index("zoe") < card.index("aaron")
    assert "Waiting" in card
    assert "/users/fam1/approve" in card
    assert 'name="approved" value="0"' in card
    assert 'name="approved" value="1"' in card


# ---- OAuth account matching -------------------------------------------------


def test_find_oauth_user_matches_provider_id_first(notesync_app):
    known = _make_user("12345", "known")
    assert auth.find_oauth_user("12345", "other@example.com", email_verified=False) == (known, None)


def test_find_oauth_user_links_verified_email_to_provider_created_account(notesync_app):
    google_account = _make_user("109876543210987654321", "me", email="me@gmail.com")
    assert auth.find_oauth_user("4242", "me@gmail.com", email_verified=True) == (google_account, None)
    # The same address, but GitHub has not verified it: no match.
    assert auth.find_oauth_user("4242", "me@gmail.com", email_verified=False) == (None, auth.EMAIL_TAKEN)


def test_find_oauth_user_never_lands_in_a_password_account(notesync_app):
    # An attacker signed up with the victim's address and a password they know.
    _make_user("11111111-aaaa-bbbb-cccc-000000000006", "squatter", email="victim@gmail.com")
    assert auth.find_oauth_user("4242", "victim@gmail.com", email_verified=True) == (None, auth.EMAIL_TAKEN)


def test_find_oauth_user_unknown_person(notesync_app):
    assert auth.find_oauth_user("4242", "new@example.com", email_verified=True) == (None, None)


def test_unique_username(notesync_app):
    assert auth.unique_username("Alex") == "Alex"
    _make_user("1", "Alex")
    assert auth.unique_username("Alex") == "Alex-2"
    _make_user("2", "Alex-2")
    assert auth.unique_username(" Alex ") == "Alex-3"
    assert auth.unique_username("") == "user"


class _FakeResp:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload

    def json(self):
        return self._payload


def _github_login(client, monkeypatch, user_info, emails):
    monkeypatch.setattr(auth, "_oauth_provider_available", lambda name: True)
    monkeypatch.setattr(auth, "_read_oauth_state", lambda state: {"client": "web"})
    monkeypatch.setattr(auth.requests, "post", lambda *a, **k: _FakeResp({"access_token": "t"}))
    monkeypatch.setattr(
        auth.requests,
        "get",
        lambda url, **k: _FakeResp(emails if url.endswith("/emails") else user_info),
    )
    response = client.get("/auth/github/callback?state=s&code=c")
    with client.session_transaction() as sess:
        return response, sess.get("access_token")


def test_github_unverified_email_cannot_take_over_an_account(notesync_app, notesync_client, monkeypatch):
    victim = _make_user("109876543210987654321", "victim", email="victim@gmail.com", approved=True)
    # The attacker's GitHub account lists the victim's address, unverified, and
    # also shows it as the public profile email.
    response, token = _github_login(
        notesync_client,
        monkeypatch,
        {"id": 666, "email": "victim@gmail.com", "name": "Mallory", "login": "mallory"},
        [{"email": "victim@gmail.com", "primary": True, "verified": False}],
    )
    assert response.status_code == 302
    assert token
    with notesync_app.app_context():
        from flask_jwt_extended import decode_token

        assert decode_token(token)["sub"] == "666"
    attacker = db.session.get(User, "666")
    assert attacker.email == "mallory@users.noreply.github.com"
    assert attacker.is_approved is False
    assert db.session.get(User, victim.id).email == "victim@gmail.com"


def test_github_verified_email_of_password_account_is_refused(notesync_client, monkeypatch):
    _make_user("11111111-aaaa-bbbb-cccc-000000000007", "local", email="me@example.com")
    response, token = _github_login(
        notesync_client,
        monkeypatch,
        {"id": 777, "name": "Me", "login": "me"},
        [{"email": "me@example.com", "primary": True, "verified": True}],
    )
    assert response.headers["Location"].endswith("/auth/login-ui")
    assert token is None
    assert db.session.get(User, "777") is None


def test_github_prefers_primary_verified_email_and_unique_username(notesync_client, monkeypatch):
    _make_user("fam1", "Alex", approved=True)
    _, token = _github_login(
        notesync_client,
        monkeypatch,
        {"id": 888, "name": "Alex", "login": "alex"},
        [
            {"email": "old@example.com", "primary": False, "verified": True},
            {"email": "alex@example.com", "primary": True, "verified": True},
            {"email": "typo@example.com", "primary": False, "verified": False},
        ],
    )
    assert token
    created = db.session.get(User, "888")
    assert created.email == "alex@example.com"
    assert created.username == "Alex-2"


def _google_login(client, monkeypatch, id_info):
    class FakeFlow:
        credentials = SimpleNamespace(id_token="token")

        def fetch_token(self, **_kwargs):
            return None

    monkeypatch.setattr(auth, "_read_oauth_state", lambda state: {"client": "web"})
    monkeypatch.setattr(auth.Flow, "from_client_config", lambda *a, **k: FakeFlow())
    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", lambda *a, **k: id_info)
    response = client.get("/auth/google/callback?state=abc")
    with client.session_transaction() as sess:
        return response, sess.get("access_token")


def test_google_unverified_email_is_refused(notesync_client, monkeypatch):
    info = {"sub": "200000000000000000001", "email": "x@corp.example", "email_verified": False, "name": "X"}
    response, token = _google_login(notesync_client, monkeypatch, info)
    assert response.headers["Location"].endswith("/auth/login-ui")
    assert token is None
    assert User.query.count() == 0


def test_google_login_does_not_land_in_squatted_password_account(notesync_client, monkeypatch):
    _make_user("11111111-aaaa-bbbb-cccc-000000000008", "squatter", email="me@gmail.com")
    info = {"sub": "200000000000000000002", "email": "me@gmail.com", "email_verified": True, "name": "Me"}
    response, token = _google_login(notesync_client, monkeypatch, info)
    assert response.headers["Location"].endswith("/auth/login-ui")
    assert token is None


def test_google_new_user_gets_unique_username_and_starts_unapproved(notesync_client, monkeypatch):
    _make_user("fam1", "Sam Lee", approved=True)
    info = {"sub": "200000000000000000003", "email": "sam@gmail.com", "email_verified": True, "name": "Sam Lee"}
    _, token = _google_login(notesync_client, monkeypatch, info)
    assert token
    created = db.session.get(User, "200000000000000000003")
    assert created.username == "Sam Lee-2"
    assert created.is_approved is False
