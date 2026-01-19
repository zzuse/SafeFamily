"""Tests for notesync-related auth helpers."""

from datetime import datetime, timedelta

from flask import Flask

from config.settings import settings
from src.safe_family.core import auth
from src.safe_family.core.extensions import db


def test_require_api_key_rejects_missing_key():
    app = Flask(__name__)
    app.secret_key = "test"

    @app.get("/protected")
    @auth.require_api_key
    def protected():
        return "ok"

    settings.NOTESYNC_API_KEY = "expected"
    client = app.test_client()
    resp = client.get("/protected")
    assert resp.status_code == 401


def test_require_api_key_accepts_key():
    app = Flask(__name__)
    app.secret_key = "test"

    @app.get("/protected")
    @auth.require_api_key
    def protected():
        return "ok"

    settings.NOTESYNC_API_KEY = "expected"
    client = app.test_client()
    resp = client.get("/protected", headers={"X-API-Key": "expected"})
    assert resp.status_code == 200
    assert resp.get_data(as_text=True) == "ok"


def test_build_notesync_callback_url_adds_code(monkeypatch):
    monkeypatch.setattr(
        settings,
        "NOTESYNC_CALLBACK_URL",
        "https://example.com/auth/callback",
    )
    url = auth.build_notesync_callback_url("abc123")
    assert url == "https://example.com/auth/callback?code=abc123"


def test_build_notesync_callback_url_handles_query(monkeypatch):
    monkeypatch.setattr(
        settings,
        "NOTESYNC_CALLBACK_URL",
        "https://example.com/auth/callback?from=oauth",
    )
    url = auth.build_notesync_callback_url("abc123")
    assert url == "https://example.com/auth/callback?from=oauth&code=abc123"


def test_auth_code_lifecycle(notesync_app):
    with notesync_app.app_context():
        code = auth.create_auth_code("user-1")
        record = auth.consume_auth_code(code)
        assert record is not None
        assert record.used_at is not None
        assert auth.consume_auth_code(code) is None


def test_auth_code_expired(notesync_app):
    with notesync_app.app_context():
        code = auth.create_auth_code("user-2")
        record = auth.AuthCode.query.first()
        record.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()
        assert auth.consume_auth_code(code) is None


def test_notesync_callback_fallback(notesync_app):
    client = notesync_app.test_client()
    missing = client.get("/auth/callback")
    assert missing.status_code == 400

    resp = client.get("/auth/callback?code=testcode")
    assert resp.status_code == 200
    assert "testcode" in resp.get_data(as_text=True)
