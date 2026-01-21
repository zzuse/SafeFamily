"""Tests for auth routes and helpers."""

from types import SimpleNamespace

from flask import Flask, session

from src.safe_family.core import auth


def _bypass_jwt(monkeypatch):
    monkeypatch.setattr(
        "flask_jwt_extended.view_decorators.verify_jwt_in_request",
        lambda *a, **k: None,
    )


def test_register_user_success(client, monkeypatch):
    monkeypatch.setattr(auth.User, "get_user_by_username", lambda username: None)
    saved = {}

    def _save(self):
        saved["user"] = self

    monkeypatch.setattr(auth.User, "save", _save)
    resp = client.post(
        "/auth/register",
        json={
            "username": "alice",
            "email": "a@a.com",
            "role": "user",
            "password": "secret",
        },
    )
    assert resp.status_code == 201
    assert saved["user"].username == "alice"


def test_register_user_duplicate(client, monkeypatch):
    monkeypatch.setattr(auth.User, "get_user_by_username", lambda username: object())
    resp = client.post(
        "/auth/register",
        json={
            "username": "alice",
            "email": "a@a.com",
            "role": "user",
            "password": "secret",
        },
    )
    assert resp.status_code == 400


def test_login_user_success(client, monkeypatch):
    fake_user = SimpleNamespace(id="u1", check_password=lambda pw: True)
    monkeypatch.setattr(auth.User, "get_user_by_username", lambda username: fake_user)
    monkeypatch.setattr(auth, "create_access_token", lambda identity: "access")
    monkeypatch.setattr(auth, "create_refresh_token", lambda identity: "refresh")

    resp = client.post(
        "/auth/login",
        json={"username": "alice", "password": "secret"},
    )
    assert resp.status_code == 200
    tokens = resp.get_json()["tokens"]
    assert tokens["access_token"] == "access"
    assert tokens["refresh_token"] == "refresh"


def test_change_password_success(client, monkeypatch):
    _bypass_jwt(monkeypatch)
    monkeypatch.setattr(auth, "get_jwt_identity", lambda: "u1")

    fake_user = SimpleNamespace(change_password=lambda old, new: True)
    monkeypatch.setattr(
        auth,
        "User",
        SimpleNamespace(query=SimpleNamespace(get=lambda user_id: fake_user)),
        raising=False,
    )

    resp = client.post(
        "/auth/change-password",
        json={"old_password": "old", "new_password": "new"},
    )
    assert resp.status_code == 200


def test_change_password_invalid_old(client, monkeypatch):
    _bypass_jwt(monkeypatch)
    monkeypatch.setattr(auth, "get_jwt_identity", lambda: "u1")

    fake_user = SimpleNamespace(change_password=lambda old, new: False)
    monkeypatch.setattr(
        auth,
        "User",
        SimpleNamespace(query=SimpleNamespace(get=lambda user_id: fake_user)),
        raising=False,
    )

    resp = client.post(
        "/auth/change-password",
        json={"old_password": "bad", "new_password": "new"},
    )
    assert resp.status_code == 400


def test_refresh_access(client, monkeypatch):
    _bypass_jwt(monkeypatch)
    monkeypatch.setattr(auth, "get_jwt_identity", lambda: "u1")
    monkeypatch.setattr(auth, "create_access_token", lambda identity: "new-access")

    resp = client.get("/auth/refresh")
    assert resp.status_code == 200
    assert resp.get_json()["access_token"] == "new-access"


def test_whoami(client, monkeypatch):
    _bypass_jwt(monkeypatch)
    monkeypatch.setattr(auth, "get_jwt", lambda: {"is_admin": "user"})
    monkeypatch.setattr(
        auth,
        "current_user",
        SimpleNamespace(username="alice", email="a@a.com"),
    )

    resp = client.get("/auth/whoami")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["user"] == "alice"
    assert data["email"] == "a@a.com"


def test_logout_revokes_token(client, monkeypatch):
    _bypass_jwt(monkeypatch)
    monkeypatch.setattr(auth, "get_jwt", lambda: {"jti": "token1", "type": "access"})
    saved = {}

    def _save(self):
        saved["jti"] = self.jti

    monkeypatch.setattr(auth.TokenBlocklist, "save", _save)

    resp = client.get("/auth/logout")
    assert resp.status_code == 200
    assert saved["jti"] == "token1"


def test_login_providers_unconfigured_redirect(client, monkeypatch):
    monkeypatch.setattr(auth.settings, "GITHUB_CLIENT_ID", None)
    monkeypatch.setattr(auth.settings, "GITHUB_CLIENT_SECRET", None)
    monkeypatch.setattr(auth.settings, "GOOGLE_CLIENT_ID", None)
    monkeypatch.setattr(auth.settings, "GOOGLE_CLIENT_SECRET", None)
    monkeypatch.setattr(auth.settings, "GOOGLE_CLIENT_PROJECT_ID", None)

    resp = client.get("/auth/login/github")
    assert resp.status_code == 302
    assert resp.location.endswith("/auth/login-ui")

    resp = client.get("/auth/login/google")
    assert resp.status_code == 302
    assert resp.location.endswith("/auth/login-ui")


def test_oauth_start_invalid_provider(client):
    resp = client.get("/auth/oauth_start?provider=unknown")
    assert resp.status_code == 400
    assert "Invalid provider" in resp.get_data(as_text=True)


def test_oauth_start_sets_ios_client(client):
    resp = client.get("/auth/oauth_start?provider=google&client=ios")
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get("oauth_client") == "ios"


def test_oauth_start_renders_page(client):
    resp = client.get("/auth/oauth_start")
    assert resp.status_code == 200
    assert "Continue with a provider" in resp.get_data(as_text=True)


def test_get_current_username_sets_role(monkeypatch):
    monkeypatch.setattr(
        auth,
        "decode_token",
        lambda token: {"sub": "u1", "is_admin": "user"},
    )
    fake_user = SimpleNamespace(id="u1", username="alice", role="admin", email="a@a.com")
    monkeypatch.setattr(
        auth,
        "User",
        SimpleNamespace(query=SimpleNamespace(get=lambda user_id: fake_user)),
        raising=False,
    )
    app = Flask(__name__)
    app.secret_key = "test"
    with app.test_request_context("/"):
        session["access_token"] = "token"
        result = auth.get_current_username()
        assert result.username == "alice"
        assert result.role == "user"
