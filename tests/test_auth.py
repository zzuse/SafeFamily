"""Tests for auth utilities and routes."""

from types import SimpleNamespace

from src.safe_family.core import auth


def _set_session_token(client):
    with client.session_transaction() as sess:
        sess["access_token"] = "token"


def test_login_required_redirects_without_token():
    @auth.login_required
    def protected():
        return "ok"

    from flask import Flask

    app = Flask(__name__)
    app.secret_key = "test"
    with app.test_request_context("/"):
        resp = protected()
        assert resp.status_code == 302
        assert "/auth/login-ui" in resp.location


def test_admin_required_blocks_non_admin(client, monkeypatch):
    monkeypatch.setattr(
        auth,
        "decode_token",
        lambda token: {"sub": "user", "is_admin": "user"},
    )
    _set_session_token(client)

    resp = client.get("/rules_toggle/enable_all")
    assert resp.status_code == 302
    assert "/auth/login-ui" in resp.location


def test_login_user_invalid_credentials(client, monkeypatch):
    fake_user = SimpleNamespace(check_password=lambda pw: False)
    monkeypatch.setattr(auth.User, "get_user_by_username", lambda username: fake_user)

    resp = client.post("/auth/login", json={"username": "bob", "password": "bad"})

    assert resp.status_code == 401
    assert resp.get_json()["message"] == "Invalid username or password"
