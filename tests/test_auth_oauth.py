"""Tests for OAuth and session auth flows."""

from types import SimpleNamespace

from flask import Flask, jsonify, session

from src.safe_family.core import auth


def test_session_login_success_sets_session(client, monkeypatch):
    def fake_login_user():
        return (
            jsonify({"tokens": {"access_token": "access", "refresh_token": "refresh"}}),
            200,
        )

    monkeypatch.setattr(auth, "login_user", fake_login_user)

    resp = client.post(
        "/auth/session-login",
        data={"username": "alice", "password": "secret"},
    )

    assert resp.status_code == 302
    assert resp.location.endswith("/")
    with client.session_transaction() as sess:
        assert sess["access_token"] == "access"
        assert sess["refresh_token"] == "refresh"


def test_session_login_invalid_redirects(client, monkeypatch):
    def fake_login_user():
        return (jsonify({"message": "Invalid"}), 401)

    monkeypatch.setattr(auth, "login_user", fake_login_user)

    resp = client.post(
        "/auth/session-login",
        data={"username": "alice", "password": "bad"},
    )

    assert resp.status_code == 302
    assert resp.location.endswith("/auth/login-ui")


def test_session_logout_clears_session(client):
    with client.session_transaction() as sess:
        sess["access_token"] = "token"
        sess["refresh_token"] = "refresh"
        sess["state"] = "state"

    resp = client.get("/auth/logout-ui")

    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get("access_token") is None
        assert sess.get("refresh_token") is None
        assert sess.get("state") is None


def test_login_required_invalid_token_clears_session(monkeypatch):
    @auth.login_required
    def protected():
        return "ok"

    app = Flask(__name__)
    app.secret_key = "test"

    def _raise_invalid(*_args, **_kwargs):
        raise auth.jwt_inner.InvalidTokenError("bad")

    monkeypatch.setattr(auth, "decode_token", _raise_invalid)

    with app.test_request_context("/"):
        session["access_token"] = "bad"
        resp = protected()

        assert resp.status_code == 302
        assert session.get("access_token") is None


def test_admin_required_invalid_token_clears_session(monkeypatch):
    @auth.admin_required
    def protected():
        return "ok"

    app = Flask(__name__)
    app.secret_key = "test"

    def _raise_invalid(*_args, **_kwargs):
        raise auth.jwt_inner.InvalidTokenError("bad")

    monkeypatch.setattr(auth, "decode_token", _raise_invalid)

    with app.test_request_context("/"):
        session["access_token"] = "bad"
        resp = protected()

        assert resp.status_code == 302
        assert session.get("access_token") is None


def test_oauth_state_roundtrip(client):
    app = client.application
    with app.test_request_context("/"):
        state = auth._build_oauth_state("ios")
        payload = auth._read_oauth_state(state)
        assert payload["client"] == "ios"


def test_login_github_redirects_when_configured(client, monkeypatch):
    monkeypatch.setattr(auth.settings, "GITHUB_CLIENT_ID", "client-id")
    monkeypatch.setattr(auth.settings, "GITHUB_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(auth, "_oauth_provider_available", lambda name: True)
    monkeypatch.setattr(auth, "_build_oauth_state", lambda client: "state123")

    resp = client.get("/auth/login/github")

    assert resp.status_code == 302
    assert "github.com/login/oauth/authorize" in resp.location
    assert "client-id" in resp.location
    assert "state123" in resp.location


def test_login_google_redirects_when_configured(client, monkeypatch):
    class FakeFlow:
        def authorization_url(self, **_kwargs):
            return ("https://accounts.google.com/o/oauth2/auth?x=1", "state123")

    monkeypatch.setattr(auth, "_oauth_provider_available", lambda name: True)
    monkeypatch.setattr(auth.Flow, "from_client_config", lambda *a, **k: FakeFlow())
    monkeypatch.setattr(auth, "_build_oauth_state", lambda client: "state123")

    resp = client.get("/auth/login/google")

    assert resp.status_code == 302
    assert "accounts.google.com" in resp.location


def test_github_callback_ios_redirects_to_app(client, monkeypatch):
    class FakeResp:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    def fake_get(url, **_kwargs):
        if url.endswith("/user/emails"):
            return FakeResp(
                200, [{"email": "user@example.com", "primary": True, "verified": True}]
            )
        return FakeResp(
            200, {"id": 1, "email": "user@example.com", "name": "User", "login": "user"}
        )

    fake_user = SimpleNamespace(id="1", username="user", email="user@example.com")

    class FakeQuery:
        def filter_by(self, **_kwargs):
            return SimpleNamespace(first=lambda: fake_user)

    monkeypatch.setattr(auth, "_oauth_provider_available", lambda name: True)
    monkeypatch.setattr(auth, "_read_oauth_state", lambda state: {"client": "ios"})
    monkeypatch.setattr(
        auth.requests, "post", lambda *a, **k: FakeResp(200, {"access_token": "token"})
    )
    monkeypatch.setattr(auth.requests, "get", fake_get)
    monkeypatch.setattr(auth.User, "query", FakeQuery(), raising=False)
    monkeypatch.setattr(auth, "create_auth_code", lambda user_id: "code123")
    monkeypatch.setattr(
        auth,
        "build_notesync_callback_url",
        lambda code, client="ios": f"app://callback?code={code}",
    )

    resp = client.get("/auth/github/callback?state=abc&code=123")

    assert resp.status_code == 302
    assert resp.location == "app://callback?code=code123"


def test_google_callback_web_sets_session(client, monkeypatch):
    class FakeFlow:
        def __init__(self):
            self.credentials = SimpleNamespace(id_token="token")

        def fetch_token(self, **_kwargs):
            return None

    fake_user = SimpleNamespace(id="g1", username="user", email="user@example.com")

    class FakeQuery:
        def filter_by(self, **_kwargs):
            return SimpleNamespace(first=lambda: fake_user)

    monkeypatch.setattr(auth, "_read_oauth_state", lambda state: {"client": "web"})
    monkeypatch.setattr(auth.Flow, "from_client_config", lambda *a, **k: FakeFlow())
    monkeypatch.setattr(
        auth.id_token,
        "verify_oauth2_token",
        lambda *a, **k: {"sub": "g1", "email": "user@example.com", "name": "User"},
    )
    monkeypatch.setattr(auth.User, "query", FakeQuery(), raising=False)
    monkeypatch.setattr(auth, "create_access_token", lambda identity: "access")
    monkeypatch.setattr(auth, "create_refresh_token", lambda identity: "refresh")

    resp = client.get("/auth/google/callback?state=abc")

    assert resp.status_code == 302
    assert resp.location.endswith("/")
    with client.session_transaction() as sess:
        assert sess["access_token"] == "access"
        assert sess["refresh_token"] == "refresh"


def test_notesync_callback_requires_code(client):
    resp = client.get("/auth/callback")
    assert resp.status_code == 400

    resp = client.get("/auth/callback?code=abc")
    assert resp.status_code == 200
