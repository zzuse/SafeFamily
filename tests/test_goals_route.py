"""Tests for the goals route."""

from datetime import datetime
from types import SimpleNamespace
from src.safe_family.core import auth
from src.safe_family.todo import goals

class SeqCursor:
    """Cursor that returns queued values for fetchone/fetchall."""

    def __init__(self, fetchone_values=None, fetchall_values=None):
        self.fetchone_values = list(fetchone_values or [])
        self.fetchall_values = list(fetchall_values or [])
        self.queries = []

    def execute(self, sql, params=None):
        self.queries.append((sql, params))

    def fetchone(self):
        return self.fetchone_values.pop(0) if self.fetchone_values else None

    def fetchall(self):
        return self.fetchall_values.pop(0) if self.fetchall_values else []

    def close(self):
        return None


class SeqConnection:
    """Connection wrapper for SeqCursor."""

    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.commits = 0
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True

def _login_session(client, monkeypatch):
    monkeypatch.setattr(auth, "decode_token", lambda token: {"sub": "user"})
    with client.session_transaction() as sess:
        sess["access_token"] = "token"

def test_goals_page_renders(client, monkeypatch):
    cursor = SeqCursor(
        fetchone_values=[("u1",)], # for get user id
    )
    conn = SeqConnection(cursor)
    monkeypatch.setattr(goals, "get_db_connection", lambda: conn)
    
    monkeypatch.setattr(
        goals,
        "get_current_username",
        lambda: SimpleNamespace(username="alice", role="user"),
    )
    
    captured_templates = []
    def _capture_render(template, **context):
        captured_templates.append((template, context))
        return "ok"
    
    monkeypatch.setattr(goals, "render_template", _capture_render)
    _login_session(client, monkeypatch)

    resp = client.get("/goals")

    assert resp.status_code == 200
    assert len(captured_templates) == 1
    template, context = captured_templates[0]
    assert template == "todo/goals.html"
    assert context["user_name"] == "alice"
    assert context["selected_user"] == "alice"
    assert context["selected_user_row_id"] == "u1"

def test_goals_page_admin_view_user(client, monkeypatch):
    cursor = SeqCursor(
        fetchone_values=[("u2",)], # for get user id
    )
    conn = SeqConnection(cursor)
    monkeypatch.setattr(goals, "get_db_connection", lambda: conn)
    
    monkeypatch.setattr(
        goals,
        "get_current_username",
        lambda: SimpleNamespace(username="admin", role="admin"),
    )
    
    captured_templates = []
    def _capture_render(template, **context):
        captured_templates.append((template, context))
        return "ok"
    
    monkeypatch.setattr(goals, "render_template", _capture_render)
    _login_session(client, monkeypatch)

    resp = client.get("/goals?view_user=bob")

    assert resp.status_code == 200
    assert len(captured_templates) == 1
    template, context = captured_templates[0]
    assert context["user_name"] == "admin"
    assert context["selected_user"] == "bob"
    assert context["selected_user_row_id"] == "u2"

def test_get_long_term_returns_rows(client, monkeypatch):
    cursor = SeqCursor(fetchall_values=[[(1, "Task", 1, False, "2025-01-01T00:00:00", 0, False)]])
    conn = SeqConnection(cursor)
    monkeypatch.setattr(goals, "get_db_connection", lambda: conn)
    _login_session(client, monkeypatch)

    resp = client.get("/todo/long_term_list/u1")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload[0]["goal_id"] == 1


def test_add_long_term_inserts(client, monkeypatch):
    cursor = SeqCursor()
    conn = SeqConnection(cursor)
    monkeypatch.setattr(goals, "get_db_connection", lambda: conn)
    _login_session(client, monkeypatch)

    resp = client.post(
        "/todo/long_term_add",
        json={"user_id": "u1", "task": "Task", "priority": 2},
    )

    assert resp.status_code == 200
    assert any("INSERT INTO long_term_goals" in sql for sql, _ in cursor.queries)


def test_update_long_term_complete_updates(client, monkeypatch):
    cursor = SeqCursor()
    conn = SeqConnection(cursor)
    monkeypatch.setattr(goals, "get_db_connection", lambda: conn)
    _login_session(client, monkeypatch)

    resp = client.post(
        "/todo/long_term_update",
        json={"goal_id": 1, "task": "Task", "priority": 2, "completed": True, "color_length": 3},
    )

    assert resp.status_code == 200
    assert any("UPDATE long_term_goals" in sql for sql, _ in cursor.queries)


def test_reorder_long_term_updates(client, monkeypatch):
    cursor = SeqCursor()
    conn = SeqConnection(cursor)
    monkeypatch.setattr(goals, "get_db_connection", lambda: conn)
    _login_session(client, monkeypatch)

    resp = client.post("/todo/long_term_reorder", json={"order": [2, 1]})

    assert resp.status_code == 200
    assert len([sql for sql, _ in cursor.queries if "UPDATE long_term_goals" in sql]) == 2


def test_start_goal_tracking_updates(client, monkeypatch):
    cursor = SeqCursor()
    conn = SeqConnection(cursor)
    monkeypatch.setattr(goals, "get_db_connection", lambda: conn)
    _login_session(client, monkeypatch)

    resp = client.post("/todo/longterm_start/1")

    assert resp.status_code == 200
    assert any("UPDATE long_term_goals" in sql for sql, _ in cursor.queries)


def test_update_due_updates(client, monkeypatch):
    cursor = SeqCursor()
    conn = SeqConnection(cursor)
    monkeypatch.setattr(goals, "get_db_connection", lambda: conn)

    resp = client.post("/todo/longterm_update_due/1", json={"due_date": "2025-01-01"})

    assert resp.status_code == 200
    assert any("UPDATE long_term_goals" in sql for sql, _ in cursor.queries)


def test_stop_goal_tracking_not_tracking(client, monkeypatch):
    goal = SimpleNamespace(tracking_start=None)
    monkeypatch.setattr(goals.LongTermGoal, "query", SimpleNamespace(get=lambda gid: goal))
    _login_session(client, monkeypatch)

    resp = client.post("/todo/longterm_stop/1")

    assert resp.status_code == 400


def test_stop_goal_tracking_success(client, monkeypatch):
    goal = SimpleNamespace(tracking_start=datetime.utcnow(), time_spent=120)
    goal.stop_tracking = lambda: goal
    monkeypatch.setattr(goals.LongTermGoal, "query", SimpleNamespace(get=lambda gid: goal))
    _login_session(client, monkeypatch)

    resp = client.post("/todo/longterm_stop/1")

    assert resp.status_code == 200
    assert resp.get_json()["time_spent"] == 120


def test_longterm_delete_not_found(client, monkeypatch):
    monkeypatch.setattr(goals.LongTermGoal, "query", SimpleNamespace(get=lambda gid: None))

    resp = client.post("/todo/longterm_delete/1")

    assert resp.status_code == 404


def test_longterm_delete_success(client, monkeypatch):
    goal = SimpleNamespace(delete_goal=lambda: None)
    monkeypatch.setattr(goals.LongTermGoal, "query", SimpleNamespace(get=lambda gid: goal))

    resp = client.post("/todo/longterm_delete/1")

    assert resp.status_code == 200