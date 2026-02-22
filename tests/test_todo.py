"""Tests for todo routes and helpers."""

from types import SimpleNamespace

from src.safe_family.core import auth
from src.safe_family.todo import todo


class SeqCursor:
    """Cursor that returns queued fetchone/fetchall results."""

    def __init__(self, fetchone_values, fetchall_values):
        self.fetchone_values = list(fetchone_values)
        self.fetchall_values = list(fetchall_values)
        self.queries = []

    def execute(self, sql, params=None):
        self.queries.append((sql, params))

    def fetchone(self):
        return self.fetchone_values.pop(0)

    def fetchall(self):
        return self.fetchall_values.pop(0)

    def close(self):
        return None


class SeqConnection:
    """Connection wrapper for SeqCursor."""

    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.commits = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def close(self):
        return None


def _login_session(client, monkeypatch):
    monkeypatch.setattr(auth, "decode_token", lambda token: {"sub": "user"})
    with client.session_transaction() as sess:
        sess["access_token"] = "token"


def test_todo_page_admin_renders(client, monkeypatch):
    cursor = SeqCursor(
        fetchone_values=[("admin", "1")],
        fetchall_values=[
            [("admin",), ("user",)],  # users_list
            [(1, "09:00 - 10:00", "Task", False)],  # today_tasks
        ],
    )
    conn = SeqConnection(cursor)
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    monkeypatch.setattr(
        todo,
        "get_current_username",
        lambda: SimpleNamespace(username="admin", role="admin"),
    )
    monkeypatch.setattr(todo, "render_template", lambda *a, **k: ("ok", 200))
    _login_session(client, monkeypatch)

    resp = client.get("/todo")

    assert resp.status_code == 200
    assert conn.commits == 0


def test_update_todo_sends_notifications(client, monkeypatch):
    from .conftest import FakeConnection

    conn = FakeConnection(rows=[("09:00 - 10:00", "Read", "")])
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    sent_email = []
    sent_discord = []
    monkeypatch.setattr(todo, "send_email_notification", lambda *a: sent_email.append(a))
    monkeypatch.setattr(
        todo,
        "send_discord_notification",
        lambda *a: sent_discord.append(a),
    )
    _login_session(client, monkeypatch)

    resp = client.post(
        "/update_todo/alice",
        data={"todo_id": ["1"], "task_1": "Read"},
    )

    assert resp.status_code == 302
    assert sent_email
    assert sent_discord


def test_done_todo_updates_status(client, monkeypatch):
    from .conftest import FakeConnection

    conn = FakeConnection(rows=[("09:00 - 10:00",)])
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    monkeypatch.setattr(todo, "flash", lambda *a, **k: None)
    _login_session(client, monkeypatch)

    resp = client.post("/todo/mark_done", json={"id": 5, "completed": True})

    assert resp.status_code == 200
    assert any(
        "UPDATE todo_list" in sql and params == (True, 5)
        for sql, params in conn.cursor_obj.queries
    )


def test_todo_page_uses_parameterized_date(client, monkeypatch):
    cursor = SeqCursor(
        fetchone_values=[("user", "1")],
        fetchall_values=[
            [],  # today_tasks
        ],
    )
    conn = SeqConnection(cursor)
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    monkeypatch.setattr(
        todo,
        "get_current_username",
        lambda: SimpleNamespace(username="user", role="user"),
    )
    monkeypatch.setattr(todo, "render_template", lambda *a, **k: ("ok", 200))
    _login_session(client, monkeypatch)

    resp = client.get("/todo")

    assert resp.status_code == 200
    # Verify that the SELECT query uses %s for date and passes a date object
    found_query = False
    for sql, params in cursor.queries:
        if "SELECT id, time_slot, task, completed" in sql:
            assert "WHERE date = %s" in sql
            from datetime import date
            assert isinstance(params[0], date)
            found_query = True
    assert found_query
