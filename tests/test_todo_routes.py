"""Additional tests for todo routes."""

from datetime import datetime
from types import SimpleNamespace

from src.safe_family.core import auth
from src.safe_family.todo import todo


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


def test_todo_page_saves_tasks_and_notifies(client, monkeypatch):
    cursor = SeqCursor(
        fetchone_values=[("alice", "u1")],
        fetchall_values=[[(1, "09:00 - 10:00", "Read", False, "")]],
    )
    conn = SeqConnection(cursor)
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    monkeypatch.setattr(todo, "get_agile_config", lambda k, d="": d)
    monkeypatch.setattr(
        todo,
        "get_current_username",
        lambda: SimpleNamespace(username="alice", role="user"),
    )
    monkeypatch.setattr(todo, "generate_time_slots", lambda *a, **k: ["09:00 - 10:00"])
    monkeypatch.setattr(todo, "render_template", lambda *a, **k: ("ok", 200))
    sent = {"email": 0, "discord": 0}
    monkeypatch.setattr(todo, "send_email_notification", lambda *a, **k: sent.__setitem__("email", sent["email"] + 1))
    monkeypatch.setattr(todo, "send_discord_notification", lambda *a, **k: sent.__setitem__("discord", sent["discord"] + 1))
    _login_session(client, monkeypatch)

    resp = client.post(
        "/todo",
        data={
            "save_todo": "1",
            "slot_type": "60",
            "schedule_mode": "weekday",
            "09:00 - 10:00": "Read",
        },
    )

    assert resp.status_code == 200
    assert sent["email"] == 1
    assert sent["discord"] == 1
    assert conn.commits == 1


def test_todo_page_highlights_current_task_by_time(client, monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 7, 12, 12, 0, tzinfo=tz)

    tasks = [
        (1, "09:00 - 10:00", "Read", False, ""),
        (2, "11:30 - 12:30", "Math", False, ""),
        (3, "14:00 - 15:00", "Piano", False, ""),
    ]
    cursor = SeqCursor(
        fetchone_values=[("alice", "u1")],
        fetchall_values=[tasks],
    )
    conn = SeqConnection(cursor)
    monkeypatch.setattr(todo, "datetime", FixedDatetime)
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    monkeypatch.setattr(todo, "get_agile_config", lambda k, d="": d)
    monkeypatch.setattr(
        todo,
        "get_current_username",
        lambda: SimpleNamespace(username="alice", role="user"),
    )
    monkeypatch.setattr(todo, "generate_time_slots", lambda *a, **k: ["09:00 - 10:00"])
    monkeypatch.setattr(
        todo,
        "build_week_strip_and_heatmap",
        lambda *a, **k: ([], {"start": "", "weeks": [], "month_labels": []}),
    )
    _login_session(client, monkeypatch)

    resp = client.get("/todo")

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    # The 11:30-12:30 slot spans the fixed 12:00 clock, so Math is current,
    # not the earlier overdue Read task.
    assert "MATH · CURRENT" in html
    assert "READ · CURRENT" not in html


def test_delete_todo_executes_delete(client, monkeypatch):
    cursor = SeqCursor()
    conn = SeqConnection(cursor)
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    monkeypatch.setattr(todo, "flash", lambda *a, **k: None)
    _login_session(client, monkeypatch)

    resp = client.post("/delete_todo/alice/5")

    assert resp.status_code == 302
    assert any("DELETE FROM todo_list" in sql for sql, _ in cursor.queries)


def test_done_todo_not_found(client, monkeypatch):
    cursor = SeqCursor(fetchone_values=[None])
    conn = SeqConnection(cursor)
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    _login_session(client, monkeypatch)

    resp = client.post("/todo/mark_done", json={"id": 1, "completed": True})

    assert resp.status_code == 404
    assert resp.get_json()["error"] == "not found"


def test_done_todo_invalid_time_slot(client, monkeypatch):
    cursor = SeqCursor(fetchone_values=[("badslot", "Task", "")])
    conn = SeqConnection(cursor)
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    _login_session(client, monkeypatch)

    resp = client.post("/todo/mark_done", json={"id": 2, "completed": False})

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid time slot"


def test_split_slot_success(client, monkeypatch):
    cursor = SeqCursor(
        fetchone_values=[
            ("alice", "09:00 - 10:00", "Task", False),
            None,
        ],
    )
    conn = SeqConnection(cursor)
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    monkeypatch.setattr(todo, "get_agile_config", lambda k, d="": d)
    monkeypatch.setattr(
        todo,
        "get_current_username",
        lambda: SimpleNamespace(username="alice", role="user"),
    )
    _login_session(client, monkeypatch)

    resp = client.post("/todo/split_slot", json={"id": 1, "username": "alice"})

    assert resp.status_code == 200
    assert resp.get_json()["success"] is True


def test_split_slot_forbidden(client, monkeypatch):
    monkeypatch.setattr(
        todo,
        "get_current_username",
        lambda: SimpleNamespace(username="alice", role="user"),
    )
    _login_session(client, monkeypatch)

    resp = client.post("/todo/split_slot", json={"id": 1, "username": "bob"})

    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"


def test_mark_todo_status_invalid_status(client, monkeypatch):
    monkeypatch.setattr(
        todo,
        "get_current_username",
        lambda: SimpleNamespace(username="alice", role="user"),
    )
    _login_session(client, monkeypatch)

    resp = client.post("/todo/mark_status", json={"id": 1, "status": "bad"})

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid status"


def test_mark_todo_status_success(client, monkeypatch):
    cursor = SeqCursor(
        fetchone_values=[
            (None, "00:00 - 00:30", "bob", "Study", "2000-01-01 00:00:00"),
        ],
    )
    conn = SeqConnection(cursor)
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    monkeypatch.setattr(todo, "get_agile_config", lambda k, d="": d)
    monkeypatch.setattr(
        todo,
        "get_current_username",
        lambda: SimpleNamespace(username="alice", role="user"),
    )
    monkeypatch.setattr(todo, "send_discord_notification", lambda *a, **k: None)
    _login_session(client, monkeypatch)

    resp = client.post("/todo/mark_status", json={"id": 3, "status": "done"})

    assert resp.status_code == 200
    assert resp.get_json()["success"] is True
    assert any("UPDATE todo_list" in sql for sql, _ in cursor.queries)


def test_exec_rules_no_lock(client, monkeypatch):
    class DummyLock:
        def acquire(self, blocking=False):
            return False

        def release(self):
            return None

    monkeypatch.setattr(todo, "RULE_EXEC_LOCK", DummyLock())
    monkeypatch.setattr(todo, "flash", lambda *a, **k: None)
    monkeypatch.setattr(
        todo,
        "get_current_username",
        lambda: SimpleNamespace(username="user", role="user"),
    )
    _login_session(client, monkeypatch)

    resp = client.post("/exec_rules/u1")

    assert resp.status_code == 302


def test_exec_rules_disable_all_triggers_schedule(client, monkeypatch):
    class DummyLock:
        def acquire(self, blocking=False):
            return True

        def release(self):
            return None

    # Seq of fetchones in exec_rules:
    # 1. Assigned rule name: ("Rule disable all",)
    # 2. SELECT username FROM users WHERE id = %s: ("user",)
    # 3. SELECT 1 FROM todo_list WHERE username = %s AND date = CURRENT_DATE: (1,)
    cursor = SeqCursor(fetchone_values=[("Rule disable all",), ("user",), (1,)])
    conn = SeqConnection(cursor)
    monkeypatch.setattr(todo, "RULE_EXEC_LOCK", DummyLock())
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    monkeypatch.setattr(todo, "flash", lambda *a, **k: None)
    monkeypatch.setattr(todo.time_module, "monotonic", lambda: 100.0)
    monkeypatch.setattr(
        todo,
        "get_current_username",
        lambda: SimpleNamespace(username="user", role="user"),
    )
    
    # Mock time to be within 16:00 - 18:00
    mock_now = datetime(2026, 4, 12, 17, 0, 0)
    class MockDatetime:
        @classmethod
        def now(cls, tz=None): return mock_now
        @classmethod
        def strptime(cls, *args, **kwargs): return datetime.strptime(*args, **kwargs)
    monkeypatch.setattr(todo, "datetime", MockDatetime)
    monkeypatch.setattr(todo, "get_agile_config", lambda k, d: d)

    todo.RULE_EXEC_STATE["last_run"] = 0.0
    called = {"load": 0, "notify": 0}
    monkeypatch.setattr(todo, "load_schedules", lambda: called.__setitem__("load", called["load"] + 1))
    monkeypatch.setattr(todo, "notify_schedule_change", lambda: called.__setitem__("notify", called["notify"] + 1))
    monkeypatch.setattr(todo, "RULE_FUNCTIONS", {"Rule disable all": lambda: None})
    _login_session(client, monkeypatch)

    resp = client.post("/exec_rules/u1")

    assert resp.status_code == 302
    assert called["load"] == 1
    assert called["notify"] == 1
    assert any("UPDATE schedule_rules" in sql for sql, _ in cursor.queries)