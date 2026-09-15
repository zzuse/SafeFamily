"""Tests for create_app hardening."""

import pytest

from src.safe_family import app as app_module

STRONG = "s" * 40


@pytest.mark.parametrize("weak", [None, "", "your_jwt_secret_key", "your-secret-key-here"])
def test_create_app_rejects_weak_jwt_secret(monkeypatch, weak):
    monkeypatch.setattr(app_module.settings, "APP_SECRET_KEY", STRONG)
    monkeypatch.setattr(app_module.settings, "JWT_SECRET_KEY", weak)
    with pytest.raises(RuntimeError, match="FLASK_JWT_SECRET_KEY"):
        app_module.create_app()


def test_create_app_rejects_weak_app_secret(monkeypatch):
    monkeypatch.setattr(app_module.settings, "APP_SECRET_KEY", "your_secret_key")
    monkeypatch.setattr(app_module.settings, "JWT_SECRET_KEY", STRONG)
    with pytest.raises(RuntimeError, match="FLASK_APP_SECRET_KEY"):
        app_module.create_app()


def test_session_cookie_samesite_lax(app):
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
