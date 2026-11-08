"""Tests for scheduler lock helpers and routes."""

from datetime import UTC, datetime, time
from types import SimpleNamespace

import pytest

from src.safe_family.core import auth
from src.safe_family.rules import scheduler


class LockCursor:
    def __init__(self, locked=True, rows=None):
        self.locked = locked
        self.rows = rows or []
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return (self.locked,)

    def fetchall(self):
        return list(self.rows)

    def close(self):
        return None


class LockConn:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.closed = 0
        self.autocommit = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        return None

    def close(self):
        self.closed = 1


def _login_admin(client, monkeypatch):
    monkeypatch.setattr(
        auth,
        "decode_token",
        lambda token: {"sub": "admin", "is_admin": "admin"},
    )
    with client.session_transaction() as sess:
        sess["access_token"] = "token"


def test_ensure_scheduler_leader_acquires_lock(monkeypatch):
    cursor = LockCursor(locked=True)
    conn = LockConn(cursor)
    monkeypatch.setattr(scheduler, "get_db_connection", lambda: conn)
    scheduler._IS_SCHEDULER_LEADER = False
    scheduler._SCHEDULER_LEADER_CONN = None

    assert scheduler._ensure_scheduler_leader() is True
    assert scheduler._IS_SCHEDULER_LEADER is True
    assert scheduler._SCHEDULER_LEADER_CONN is conn


def test_ensure_scheduler_leader_not_acquired(monkeypatch):
    cursor = LockCursor(locked=False)
    conn = LockConn(cursor)
    monkeypatch.setattr(scheduler, "get_db_connection", lambda: conn)
    scheduler._IS_SCHEDULER_LEADER = False
    scheduler._SCHEDULER_LEADER_CONN = None

    assert scheduler._ensure_scheduler_leader() is False
    assert conn.closed == 1


def test_ensure_job_lock_sets_connection(monkeypatch):
    cursor = LockCursor(locked=True)
    conn = LockConn(cursor)
    monkeypatch.setattr(scheduler, "get_db_connection", lambda: conn)
    scheduler._JOB_LOCKS.clear()

    assert scheduler._ensure_job_lock("job-1") is True
    assert "job-1" in scheduler._JOB_LOCKS


def test_ensure_job_lock_returns_false(monkeypatch):
    cursor = LockCursor(locked=False)
    conn = LockConn(cursor)
    monkeypatch.setattr(scheduler, "get_db_connection", lambda: conn)
    scheduler._JOB_LOCKS.clear()

    assert scheduler._ensure_job_lock("job-2") is False
    assert conn.closed == 1


def test_wrap_job_skips_when_not_leader(monkeypatch):
    monkeypatch.setattr(scheduler, "_ensure_scheduler_leader", lambda: False)
    monkeypatch.setattr(scheduler, "_ensure_job_lock", lambda job_id: True)

    wrapped = scheduler._wrap_job("job-3", lambda: "ok")
    result = wrapped()

    assert result is scheduler._JOB_SKIPPED


def test_release_unused_job_locks_closes_connections():
    conn = LockConn(LockCursor())
    scheduler._JOB_LOCKS.clear()
    scheduler._JOB_LOCKS["job-4"] = conn

    scheduler._release_unused_job_locks(set())

    assert conn.closed == 1


def test_notify_schedule_change_executes_query(monkeypatch):
    cursor = LockCursor()
    conn = LockConn(cursor)
    monkeypatch.setattr(scheduler, "get_db_connection", lambda: conn)

    scheduler.notify_schedule_change()

    assert any("pg_notify" in sql for sql, _ in cursor.executed)


def _run_task_notifier(monkeypatch, rows, now):
    cursor = LockCursor(rows=rows)
    conn = LockConn(cursor)
    monkeypatch.setattr(scheduler, "get_db_connection", lambda: conn)
    sent = []
    monkeypatch.setattr(scheduler, "send_hammerspoon_alert", sent.append)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(scheduler, "datetime", FixedDatetime)
    scheduler.notify_overdue_task_feedback()
    return sent


def _reset_task_notifier_state():
    scheduler._NOTIFIED_TASK_IDS.clear()
    scheduler._STARTED_TASK_IDS.clear()
    scheduler._NOTIFIED_DATE = None


def test_notify_overdue_task_feedback_sends_alert(monkeypatch):
    _reset_task_notifier_state()
    now = datetime(2026, 1, 1, 10, 30, tzinfo=UTC)
    sent = _run_task_notifier(monkeypatch, [(1, "alice", "09:00 - 10:00", "Task", "")], now)

    assert sent == ["09:00 - 10:00 - Task"]


def test_notify_task_start_sends_alert_once(monkeypatch):
    _reset_task_notifier_state()
    rows = [(2, "alice", "10:00 - 11:00", "Math", "")]
    now = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

    first = _run_task_notifier(monkeypatch, rows, now)
    second = _run_task_notifier(monkeypatch, rows, now.replace(minute=1))

    assert first == ["Starting: 10:00 - 11:00 - Math"]
    assert second == []


def test_notify_task_start_waits_one_minute_after_finished_alert(monkeypatch):
    _reset_task_notifier_state()
    rows = [
        (7, "alice", "09:00 - 10:00", "Read", ""),
        (8, "alice", "10:00 - 11:00", "Math", ""),
    ]
    at_ten = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

    first = _run_task_notifier(monkeypatch, rows, at_ten)
    second = _run_task_notifier(monkeypatch, rows, at_ten.replace(minute=1))

    assert first == ["09:00 - 10:00 - Read"]
    assert second == ["Starting: 10:00 - 11:00 - Math"]


def test_notify_task_start_skips_future_and_past_slots(monkeypatch):
    _reset_task_notifier_state()
    rows = [
        (3, "alice", "11:00 - 12:00", "Later", ""),
        (4, "alice", "08:00 - 09:00", "Earlier", "done"),
        (5, "alice", "bad slot", "Broken", ""),
    ]
    now = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

    assert _run_task_notifier(monkeypatch, rows, now) == []


def test_notify_task_state_resets_on_new_day(monkeypatch):
    _reset_task_notifier_state()
    rows = [(6, "alice", "10:00 - 11:00", "", "")]
    day1 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    _run_task_notifier(monkeypatch, rows, day1)

    sent = _run_task_notifier(monkeypatch, rows, day1.replace(day=2))

    assert sent == ["Starting: 10:00 - 11:00"]


def test_schedule_rules_add_rule(client, monkeypatch):
    cursor = LockCursor(rows=[])
    cursor.fetchone = lambda: (42,)
    conn = LockConn(cursor)
    monkeypatch.setattr(scheduler, "get_db_connection", lambda: conn)
    monkeypatch.setattr(scheduler, "load_schedules", lambda: None)
    monkeypatch.setattr(scheduler, "notify_schedule_change", lambda: None)
    _login_admin(client, monkeypatch)

    resp = client.post(
        "/schedule_rules",
        data={
            "action": "add",
            "rule_name": "Rule enable all",
            "start_time": "09:00",
            "end_time": "",
        },
    )

    assert resp.status_code == 302
    assert any("INSERT INTO schedule_rules" in sql for sql, _ in cursor.executed)


@pytest.mark.parametrize(
    ("form", "expected_sql"),
    [
        ({"action": "update", "rule_id": "1", "start_time": "09:00", "end_time": "10:00", "day_of_week": ["0", "1"]},
         "UPDATE schedule_rules SET start_time"),
        ({"action": "update", "rule_id": "1", "start_time": "", "end_time": ""}, "UPDATE schedule_rules SET start_time"),
        ({"action": "delete", "rule_id": "1"}, "DELETE FROM schedule_rules"),
        ({"action": "enable", "rule_id": "1"}, "SET enabled = TRUE"),
        ({"action": "disable", "rule_id": "1"}, "SET enabled = FALSE"),
        ({"action": "assign", "rule_u1": "Rule enable all"}, "INSERT INTO user_rule_assignment"),
    ],
)
def test_schedule_rules_post_actions(client, monkeypatch, form, expected_sql):
    cursor = LockCursor(rows=[])
    conn = LockConn(cursor)
    monkeypatch.setattr(scheduler, "get_db_connection", lambda: conn)
    monkeypatch.setattr(scheduler, "load_schedules", lambda: None)
    monkeypatch.setattr(scheduler, "notify_schedule_change", lambda: None)
    monkeypatch.setattr(scheduler, "remove_job", lambda rule_id: None)
    _login_admin(client, monkeypatch)

    resp = client.post("/schedule_rules", data=form)

    assert resp.status_code == 302
    assert any(expected_sql in sql for sql, _ in cursor.executed)


@pytest.mark.parametrize("calc_ok", [True, False])
def test_schedule_rules_agile_config_actions(client, monkeypatch, calc_ok):
    monkeypatch.setattr(scheduler, "get_db_connection", lambda: LockConn(LockCursor()))
    saved = {}
    monkeypatch.setattr(scheduler, "set_agile_config", saved.__setitem__)
    monkeypatch.setattr(scheduler, "update_agile_config_by_timestamp", lambda *a: calc_ok)
    _login_admin(client, monkeypatch)

    resp1 = client.post("/schedule_rules", data={"action": "update_agile_config", "config_focus": "25"})
    resp2 = client.post(
        "/schedule_rules",
        data={"action": "calc_agile_config", "timestamp_input": "08:00", "delay_input": "5", "eating_input": ""},
    )

    assert resp1.status_code == resp2.status_code == 302
    assert saved == {"focus": "25"}


def test_schedule_rules_get_renders(client, monkeypatch):
    cursor = LockCursor(rows=[("u1", "alice", None), (1, "Rule enable all", "09:00", None, "*", True)])
    conn = LockConn(cursor)
    monkeypatch.setattr(scheduler, "get_db_connection", lambda: conn)
    monkeypatch.setattr(scheduler, "get_scheduled_job_details", list)
    monkeypatch.setattr(scheduler, "render_template", lambda *a, **k: ("ok", 200))
    _login_admin(client, monkeypatch)

    resp = client.get("/schedule_rules")

    assert resp.status_code == 200


def test_schedule_rules_get_renders_real_template(client, monkeypatch):
    class RenderCursor(LockCursor):
        def fetchall(self):
            sql = self.executed[-1][0]
            if "FROM users" in sql:
                return [("u1", "alice", "Rule enable AI")]
            if "FROM schedule_rules" in sql:
                return [
                    (1, "Rule enable AI", time(9, 0), time(11, 30), "0,1,2", True),
                    (2, "Rule disable all", time(21, 0), None, "*", False),
                ]
            return [("show_disable_button_start", "16:00")]

    cursor = RenderCursor()
    conn = LockConn(cursor)
    monkeypatch.setattr(scheduler, "get_db_connection", lambda: conn)
    monkeypatch.setattr(
        scheduler,
        "get_scheduled_job_details",
        lambda: [
            {"id": "analyze_logs", "name": "analyze_logs", "trigger": "cron", "next_run_time": "2026-07-13 00:20:00 CDT"},
            {"id": "gas_weather_report", "name": "gas_weather_report", "trigger": "cron", "next_run_time": "-"},
        ],
    )
    _login_admin(client, monkeypatch)

    resp = client.get("/schedule_rules")

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Schedule rules" in html
    assert "Rule enable AI" in html
    assert "sched-timeline" in html
    assert "1 rules active" in html
    assert "00:20" in html
    assert "— paused" in html


def test_log_job_event_handles_exception():
    event = SimpleNamespace(job_id="job-x", exception=Exception("boom"), retval=None)
    scheduler._log_job_event(event)


def test_log_job_event_skips_job():
    event = SimpleNamespace(job_id="job-y", exception=None, retval=scheduler._JOB_SKIPPED)
    scheduler._log_job_event(event)


def test_get_scheduled_job_details_formats_times(monkeypatch):
    next_run = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)
    job = SimpleNamespace(id="job-1", name="job", trigger="cron", next_run_time=next_run)
    monkeypatch.setattr(scheduler.scheduler, "get_jobs", lambda: [job])

    details = scheduler.get_scheduled_job_details()

    assert details[0]["id"] == "job-1"
    assert details[0]["next_run_time"]


def test_remove_job_handles_missing(monkeypatch):
    monkeypatch.setattr(scheduler.scheduler, "remove_job", lambda job_id: (_ for _ in ()).throw(Exception("missing")))
    scheduler.remove_job(123)


def test_schedule_rules_update_action(client, monkeypatch):
    cursor = LockCursor()
    conn = LockConn(cursor)
    monkeypatch.setattr(scheduler, "get_db_connection", lambda: conn)
    monkeypatch.setattr(scheduler, "load_schedules", lambda: None)
    monkeypatch.setattr(scheduler, "notify_schedule_change", lambda: None)
    _login_admin(client, monkeypatch)

    resp = client.post(
        "/schedule_rules",
        data={
            "action": "update",
            "rule_id": "1",
            "start_time": "09:00",
            "end_time": "",
            "day_of_week": [],
        },
    )

    assert resp.status_code == 302
    assert any("UPDATE schedule_rules" in sql for sql, _ in cursor.executed)


def test_schedule_rules_assign_action(client, monkeypatch):
    cursor = LockCursor()
    conn = LockConn(cursor)
    monkeypatch.setattr(scheduler, "get_db_connection", lambda: conn)
    _login_admin(client, monkeypatch)

    resp = client.post(
        "/schedule_rules",
        data={"action": "assign", "rule_u1": "Rule enable all"},
    )

    assert resp.status_code == 302
    assert any("INSERT INTO user_rule_assignment" in sql for sql, _ in cursor.executed)


def test_analyze_logs_calls_log_analysis(monkeypatch):
    called = {}

    monkeypatch.setattr(scheduler, "get_time_range", lambda **k: ("start", "end"))
    monkeypatch.setattr(scheduler, "log_analysis", lambda start, end: called.__setitem__("args", (start, end)))

    scheduler.analyze_logs()

    assert called["args"] == ("start", "end")
