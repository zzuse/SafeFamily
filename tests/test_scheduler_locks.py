"""Tests for scheduler lock helpers and routes."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

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


def test_notify_overdue_task_feedback_sends_alert(monkeypatch):
    time_slot = "00:00 - 00:00"
    cursor = LockCursor(rows=[(1, "alice", time_slot, "Task")])
    conn = LockConn(cursor)
    monkeypatch.setattr(scheduler, "get_db_connection", lambda: conn)
    sent = {}
    monkeypatch.setattr(
        scheduler,
        "send_hammerspoon_alert",
        lambda msg: sent.__setitem__("msg", msg),
    )
    scheduler._NOTIFIED_TASK_IDS.clear()
    scheduler._NOTIFIED_DATE = None

    scheduler.notify_overdue_task_feedback()

    assert "msg" in sent


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


def test_schedule_rules_get_renders(client, monkeypatch):
    cursor = LockCursor(rows=[("u1", "alice", None), (1, "Rule enable all", "09:00", None, "*", True)])
    conn = LockConn(cursor)
    monkeypatch.setattr(scheduler, "get_db_connection", lambda: conn)
    monkeypatch.setattr(scheduler, "get_scheduled_job_details", lambda: [])
    monkeypatch.setattr(scheduler, "render_template", lambda *a, **k: ("ok", 200))
    _login_admin(client, monkeypatch)

    resp = client.get("/schedule_rules")

    assert resp.status_code == 200


def test_log_job_event_handles_exception():
    event = SimpleNamespace(job_id="job-x", exception=Exception("boom"), retval=None)
    scheduler._log_job_event(event)


def test_log_job_event_skips_job():
    event = SimpleNamespace(job_id="job-y", exception=None, retval=scheduler._JOB_SKIPPED)
    scheduler._log_job_event(event)


def test_get_scheduled_job_details_formats_times(monkeypatch):
    next_run = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
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
