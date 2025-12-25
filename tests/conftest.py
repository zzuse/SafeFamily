"""Pytest fixtures for SafeFamily tests."""

import contextlib
from types import SimpleNamespace

import pytest

from src.safe_family.app import create_app


class FakeCursor:
    """Minimal DB cursor stub that records executed statements."""

    def __init__(self, rows=None):
        self.queries = []
        self._rows = rows or []

    def execute(self, sql, params=None):
        self.queries.append((sql, params))

    def fetchone(self):
        return self._rows[0] if self._rows else (0,)

    def fetchall(self):
        return self._rows

    def close(self):
        return None


class FakeConnection:
    """Minimal DB connection stub returning FakeCursor."""

    def __init__(self, rows=None):
        self.cursor_obj = FakeCursor(rows)
        self.commits = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def close(self):
        return None


@pytest.fixture
def app(monkeypatch):
    """Flask application with patched DB connection."""
    fake_conn = FakeConnection()
    from src.safe_family import core

    monkeypatch.setattr(core.extensions, "get_db_connection", lambda: fake_conn)
    monkeypatch.setattr(
        "config.settings.settings.SQLALCHEMY_DATABASE_URI",
        "sqlite:///:memory:",
    )
    flask_app = create_app()
    flask_app.config["SECRET_KEY"] = "test"
    with flask_app.app_context():
        yield flask_app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def fake_db():
    """Provide a fresh fake DB connection and cursor."""
    return FakeConnection()


@pytest.fixture
def patch_requests(monkeypatch):
    """Patch requests.post/get to prevent network calls."""
    calls = []

    def _record(method, *args, **kwargs):
        calls.append(SimpleNamespace(method=method, args=args, kwargs=kwargs, status_code=200, text="ok"))
        return calls[-1]

    monkeypatch.setattr("requests.post", lambda *a, **kw: _record("post", *a, **kw))
    monkeypatch.setattr("requests.get", lambda *a, **kw: _record("get", *a, **kw))
    return calls


@pytest.fixture
def patch_mail(monkeypatch):
    """Patch Flask-Mail send to capture messages."""
    sent = []

    def _send(message):
        sent.append(message)

    monkeypatch.setattr("src.safe_family.notifications.notifier.mail.send", _send)
    return sent
