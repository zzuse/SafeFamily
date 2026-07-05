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
            [],  # week strip / heatmap history
        ],
    )
    conn = SeqConnection(cursor)
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    monkeypatch.setattr(todo, "get_agile_config", lambda k, d="": d)
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
            [],  # week strip / heatmap history
        ],
    )
    conn = SeqConnection(cursor)
    monkeypatch.setattr(todo, "get_db_connection", lambda: conn)
    monkeypatch.setattr(todo, "get_agile_config", lambda k, d="": d)
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


class HistoryCursor:
    """Cursor stub returning fixed rows for the history query."""

    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def execute(self, sql, params=None):
        self.queries.append((sql, params))

    def fetchall(self):
        return self.rows


def test_daily_completion_map_counts_only_mandatory_minutes():
    from datetime import date

    d = date(2026, 6, 29)
    cur = HistoryCursor(
        [
            (d, "18:00 - 19:00", "math[fractions]", True, "done"),
            (d, "19:00 - 20:00", "piano[scales]", True, "half done"),
            (d, "20:00 - 21:00", "books[novel]", True, "done"),
            (d, "21:00 - 22:00", "leasure[games]", False, "skipped"),
        ],
    )

    result = todo.daily_completion_map(cur, "kid", d, d)

    # books/leasure earn nothing; math 60 + piano 30 = 90 min of the
    # 120-minute daily target
    assert result[d]["pct"] == 75
    assert result[d]["tasks"] == [
        "math[fractions] · done",
        "piano[scales] · half done",
        "books[novel] · done",
        "leasure[games] · skipped",
    ]


def test_daily_completion_map_caps_at_200():
    from datetime import date

    d = date(2026, 6, 29)
    cur = HistoryCursor(
        [
            (d, "17:00 - 18:00", "math", True, "done"),
            (d, "18:00 - 19:00", "science", True, "done"),
            (d, "19:00 - 20:00", "language", True, "done"),
            (d, "20:00 - 21:00", "piano", True, "done"),
            (d, "21:00 - 22:00", "math[extra]", True, "done"),
        ],
    )

    result = todo.daily_completion_map(cur, "kid", d, d)

    # 300 mandatory minutes = 250% of target, capped at 200
    assert result[d]["pct"] == 200


def test_daily_completion_map_empty_status_falls_back_to_checkbox():
    from datetime import date

    d = date(2026, 6, 29)
    cur = HistoryCursor(
        [
            (d, "18:00 - 19:00", "math", True, ""),
            (d, "19:00 - 20:00", "science", False, ""),
        ],
    )

    result = todo.daily_completion_map(cur, "kid", d, d)

    # checked math earns its 60 minutes; unchecked science earns nothing
    assert result[d]["pct"] == 50
    # empty status: hover label falls back to the checkbox state
    assert result[d]["tasks"] == ["math · done", "science · not done"]


def test_daily_completion_map_unparseable_slot_counts_tasks():
    from datetime import date

    d = date(2026, 6, 29)
    cur = HistoryCursor(
        [
            (d, "whenever", "math", True, "done"),
            (d, None, "piano", False, "skipped"),
        ],
    )

    result = todo.daily_completion_map(cur, "kid", d, d)

    # unparseable slots assume DEFAULT_SLOT_MINUTES (60)
    assert result[d]["pct"] == 50


def test_daily_completion_map_day_without_plan_is_none():
    from datetime import date, timedelta

    d = date(2026, 6, 29)
    cur = HistoryCursor([(d, "18:00 - 19:00", "math", True, "done")])

    result = todo.daily_completion_map(cur, "kid", d, d + timedelta(days=1))

    assert result[d]["pct"] == 50  # one done math hour = half the 120-min target
    assert result[d + timedelta(days=1)] == {"pct": None, "tasks": []}


def test_build_week_strip_and_heatmap_shapes():
    from datetime import date, timedelta

    today = date(2026, 7, 4)  # Saturday
    week_monday = date(2026, 6, 29)
    start = week_monday - timedelta(weeks=todo.HEATMAP_WEEKS - 1)
    cur = HistoryCursor([(date(2026, 7, 1), "18:00 - 19:00", "math", True, "done")])

    week_strip, heatmap = todo.build_week_strip_and_heatmap(cur, "kid", today)

    assert [day["label"] for day in week_strip] == list("MTWTFSS")
    assert week_strip[0]["date"] == week_monday.isoformat()
    assert week_strip[2]["pct"] == 50  # one done math hour vs the 120-min target
    assert week_strip[5]["is_today"] is True
    assert week_strip[6]["is_future"] is True

    assert len(heatmap["weeks"]) == todo.HEATMAP_WEEKS
    assert all(len(week) == 7 for week in heatmap["weeks"])
    assert heatmap["start"] == start.isoformat()
    assert heatmap["weeks"][-1][2]["pct"] == 50
    assert heatmap["weeks"][-1][6]["is_future"] is True

    # hover shows task details, never the percentage
    assert heatmap["weeks"][-1][2]["tooltip"] == "Wed 2026-07-01\nmath · done"
    assert heatmap["weeks"][-1][0]["tooltip"] == "Mon 2026-06-29 · no plan"
    assert week_strip[2]["tooltip"] == "Wed 2026-07-01\nmath · done"
    assert heatmap["month_labels"][0] == {"col": 0, "text": start.strftime("%b")}

    # single query spanning exactly HEATMAP_WEEKS ISO weeks
    sql, params = cur.queries[0]
    assert "BETWEEN" in sql
    assert params == ("kid", start, week_monday + timedelta(days=6))
