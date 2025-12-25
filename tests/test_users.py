"""Tests for user routes."""

from types import SimpleNamespace

import pytest

from src.safe_family.users import users


@pytest.fixture(autouse=True)
def patch_jwt(monkeypatch):
    """Bypass JWT verification for tests."""

    monkeypatch.setattr(
        "flask_jwt_extended.view_decorators.verify_jwt_in_request",
        lambda *a, **k: None,
    )


def test_get_all_users_admin(client, monkeypatch):
    """Admin can list users with pagination."""
    monkeypatch.setattr(users, "get_jwt", lambda: {"is_admin": "admin"})

    fake_users = [SimpleNamespace(id="1", username="alice", email="a@a.com")]

    class FakeQuery:
        def paginate(self, page, per_page):
            return SimpleNamespace(items=fake_users)

    monkeypatch.setattr(users.User, "query", FakeQuery())

    resp = client.get("/users/all")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["users"][0]["username"] == "alice"


def test_get_all_users_forbidden_for_non_admin(client, monkeypatch):
    """Non-admins receive 403."""
    monkeypatch.setattr(users, "get_jwt", lambda: {"is_admin": "user"})

    resp = client.get("/users/all")

    assert resp.status_code == 403
    assert resp.get_json()["msg"] == "Admins only!"
