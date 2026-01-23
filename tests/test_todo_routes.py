"""Additional tests for todo routes."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pandas as pd

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
    cursor = SeqCursor(fetchone_values=[("badslot",)])
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


def test_notify_current_task_success(client, monkeypatch):
    now = datetime.now(todo.local_tz)
    start = (now - timedelta(minutes=5)).strftime("%H:%M")
    end = (now + timedelta(minutes=10)).strftime("%H:%M")
    time_slot = f"{start} - {end}"
    cursor = SeqCursor(fetchall_values=[[(time_slot, "Read")]])
    conn = SeqConnection(cursor)
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    monkeypatch.setattr(
        todo,
        "get_current_username",
        lambda: SimpleNamespace(username="alice", role="user"),
    )
    sent = {}
    monkeypatch.setattr(
        todo,
        "send_hammerspoon_task",
        lambda *a, **k: sent.__setitem__("task", a),
    )
    _login_session(client, monkeypatch)

    resp = client.post("/todo/notify_current_task", json={})

    assert resp.status_code == 200
    assert resp.get_json()["success"] is True
    assert "task" in sent


def test_notify_current_task_requires_login(client, monkeypatch):
    monkeypatch.setattr(todo, "get_current_username", lambda: None)
    _login_session(client, monkeypatch)

    resp = client.post("/todo/notify_current_task", json={})

    assert resp.status_code == 401
    assert resp.get_json()["error"] == "not logged in"


def test_unknown_metadata_filters(client, monkeypatch):
    yesterday = datetime.now(todo.local_tz).date() - timedelta(days=1)
    cursor = SeqCursor(
        fetchall_values=[
            [
                (1, "09:00 - 10:00", "Task", "", yesterday, ""),
                (2, "09:00 - 10:00", "Task2", "unknown", yesterday, None),
            ]
        ],
    )
    conn = SeqConnection(cursor)
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    monkeypatch.setattr(todo, "gentags", SimpleNamespace(main=lambda *_: None))
    monkeypatch.setattr(
        todo,
        "get_current_username",
        lambda: SimpleNamespace(username="alice", role="user"),
    )
    _login_session(client, monkeypatch)

    resp = client.get("/todo/unknown_metadata")

    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["unknown_tags"]) == 2
    assert len(data["unknown_status"]) == 2


def test_update_tag_forbidden(client, monkeypatch):
    cursor = SeqCursor(fetchone_values=[("bob",)])
    conn = SeqConnection(cursor)
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    monkeypatch.setattr(
        todo,
        "get_current_username",
        lambda: SimpleNamespace(username="alice", role="user"),
    )
    _login_session(client, monkeypatch)

    resp = client.post("/todo/update_tag", json={"id": 1, "tag": "math"})

    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"


def test_update_tag_success(client, monkeypatch):
    cursor = SeqCursor(fetchone_values=[("alice",)])
    conn = SeqConnection(cursor)
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    monkeypatch.setattr(
        todo,
        "get_current_username",
        lambda: SimpleNamespace(username="alice", role="admin"),
    )
    _login_session(client, monkeypatch)

    resp = client.post("/todo/update_tag", json={"id": 1, "tag": "math"})

    assert resp.status_code == 200
    assert resp.get_json()["success"] is True
    assert conn.commits == 1


def test_exec_rules_no_lock(client, monkeypatch):
    class DummyLock:
        def acquire(self, blocking=False):
            return False

        def release(self):
            return None

    monkeypatch.setattr(todo, "RULE_EXEC_LOCK", DummyLock())
    monkeypatch.setattr(todo, "flash", lambda *a, **k: None)
    _login_session(client, monkeypatch)

    resp = client.post("/exec_rules/u1")

    assert resp.status_code == 302


def test_exec_rules_disable_all_triggers_schedule(client, monkeypatch):
    class DummyLock:
        def acquire(self, blocking=False):
            return True

        def release(self):
            return None

    cursor = SeqCursor(fetchone_values=[("Rule disable all",)])
    conn = SeqConnection(cursor)
    monkeypatch.setattr(todo, "RULE_EXEC_LOCK", DummyLock())
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    monkeypatch.setattr(todo, "flash", lambda *a, **k: None)
    monkeypatch.setattr(todo.time_module, "monotonic", lambda: 100.0)
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


def test_notify_feedback_sends_alert(client, monkeypatch):
    monkeypatch.setattr(todo, "send_hammerspoon_alert", lambda *a, **k: None)
    _login_session(client, monkeypatch)

    resp = client.post("/todo/notify_feedback", json={"time_slot": "09:00 - 10:00", "task": "Read"})

    assert resp.status_code == 200
    assert resp.get_json()["success"] is True


def test_weekly_summary_returns_payload(client, monkeypatch):
    today = datetime(2025, 1, 8)
    monkeypatch.setattr(todo, "gentags", SimpleNamespace(main=lambda *_: None))
    monkeypatch.setattr(
        todo,
        "get_current_username",
        lambda: SimpleNamespace(username="alice", role="user"),
    )
    monkeypatch.setattr(todo.weekly_metrics, "_parse_iso_week", lambda week: (today.date(), today.date()))
    monkeypatch.setattr(todo.weekly_metrics, "_fetch_week_df", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(
        todo.weekly_metrics,
        "_compute_metrics",
        lambda *a, **k: SimpleNamespace(
            completion_rate=0.5,
            avg_tasks_per_day=1.0,
            avg_planned_minutes=30.0,
            by_category={},
            by_category_minutes={},
        ),
    )
    monkeypatch.setattr(todo.weekly_diff, "_format_output", lambda *a, **k: "summary")
    monkeypatch.setattr(todo, "send_discord_summary", lambda *a, **k: None)
    _login_session(client, monkeypatch)

    resp = client.get("/todo/weekly_summary")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["summary"] == "summary"


def test_get_long_term_returns_rows(client, monkeypatch):
    cursor = SeqCursor(fetchall_values=[[(1, "Task", 1, False, "2025-01-01T00:00:00", 0, False)]])
    conn = SeqConnection(cursor)
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    _login_session(client, monkeypatch)

    resp = client.get("/todo/long_term_list/u1")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload[0]["goal_id"] == 1


def test_add_long_term_inserts(client, monkeypatch):
    cursor = SeqCursor()
    conn = SeqConnection(cursor)
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
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
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
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
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    _login_session(client, monkeypatch)

    resp = client.post("/todo/long_term_reorder", json={"order": [2, 1]})

    assert resp.status_code == 200
    assert len([sql for sql, _ in cursor.queries if "UPDATE long_term_goals" in sql]) == 2


def test_start_goal_tracking_updates(client, monkeypatch):
    cursor = SeqCursor()
    conn = SeqConnection(cursor)
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    _login_session(client, monkeypatch)

    resp = client.post("/todo/longterm_start/1")

    assert resp.status_code == 200
    assert any("UPDATE long_term_goals" in sql for sql, _ in cursor.queries)


def test_update_due_updates(client, monkeypatch):
    cursor = SeqCursor()
    conn = SeqConnection(cursor)
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)

    resp = client.post("/todo/longterm_update_due/1", json={"due_date": "2025-01-01"})

    assert resp.status_code == 200
    assert any("UPDATE long_term_goals" in sql for sql, _ in cursor.queries)


def test_stop_goal_tracking_not_tracking(client, monkeypatch):
    goal = SimpleNamespace(tracking_start=None)
    monkeypatch.setattr(todo.LongTermGoal, "query", SimpleNamespace(get=lambda gid: goal))
    _login_session(client, monkeypatch)

    resp = client.post("/todo/longterm_stop/1")

    assert resp.status_code == 400


def test_stop_goal_tracking_success(client, monkeypatch):
    goal = SimpleNamespace(tracking_start=datetime.utcnow(), time_spent=120)
    goal.stop_tracking = lambda: goal
    monkeypatch.setattr(todo.LongTermGoal, "query", SimpleNamespace(get=lambda gid: goal))
    _login_session(client, monkeypatch)

    resp = client.post("/todo/longterm_stop/1")

    assert resp.status_code == 200
    assert resp.get_json()["time_spent"] == 120


def test_longterm_delete_not_found(client, monkeypatch):
    monkeypatch.setattr(todo.LongTermGoal, "query", SimpleNamespace(get=lambda gid: None))

    resp = client.post("/todo/longterm_delete/1")

    assert resp.status_code == 404


def test_longterm_delete_success(client, monkeypatch):
    goal = SimpleNamespace(delete_goal=lambda: None)
    monkeypatch.setattr(todo.LongTermGoal, "query", SimpleNamespace(get=lambda gid: goal))

    resp = client.post("/todo/longterm_delete/1")

    assert resp.status_code == 200
