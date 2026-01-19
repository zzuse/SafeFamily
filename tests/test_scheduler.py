"""Tests for scheduler utilities."""

from datetime import datetime, time, timedelta
from types import SimpleNamespace

from src.safe_family.rules import scheduler


class QueueCursor:
    """Cursor stub returning queued rows."""

    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return list(self.rows)

    def close(self):
        return None


class QueueConn:
    def __init__(self, rows):
        self.cursor_obj = QueueCursor(rows)
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


class FakeScheduler:
    def __init__(self):
        self.jobs = []
        self.removed = False

    def remove_all_jobs(self):
        self.removed = True
        self.jobs = []

    def add_job(self, func, trigger, **kwargs):
        job_id = kwargs.get("id")
        self.jobs.append(
            SimpleNamespace(
                id=job_id,
                func=func,
                trigger=trigger,
            ),
        )

    def get_jobs(self):
        return [SimpleNamespace(id=job.id, name=getattr(job.func, "__name__", ""), trigger=job.trigger, next_run_time=None) for job in self.jobs]


def test_load_schedules_adds_jobs(monkeypatch):
    rows = [
        (1, "Rule enable all except AI", time(9, 0), "1,2"),
    ]
    conn = QueueConn(rows)
    fake_scheduler = FakeScheduler()
    monkeypatch.setattr(scheduler, "get_db_connection", lambda: conn)
    monkeypatch.setattr(scheduler, "scheduler", fake_scheduler)
    monkeypatch.setattr(scheduler.logger, "info", lambda *a, **k: None)

    scheduler.load_schedules()

    assert fake_scheduler.removed
    # One DB job + archive_completed_tasks + analyze_logs + notify_overdue_task_feedback
    assert len(fake_scheduler.jobs) == 4
    assert fake_scheduler.jobs[0].id == "rule_1"


class DualCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return list(self.rows)

    def close(self):
        return None


class DualConn:
    def __init__(self, rows):
        self.cursors = [DualCursor(rows), DualCursor(rows)]
        self.index = 0
        self.closed = False

    def cursor(self):
        cur = self.cursors[self.index]
        self.index = (self.index + 1) % len(self.cursors)
        return cur

    def commit(self):
        return None

    def close(self):
        self.closed = True


def test_archive_completed_tasks_moves_rows(monkeypatch):
    completed_at = datetime.now(scheduler.local_tz) - timedelta(days=4)
    rows = [(1, "user", "task", 1, completed_at, 60)]
    conn = DualConn(rows)
    monkeypatch.setattr(scheduler, "get_db_connection", lambda: conn)
    monkeypatch.setattr(scheduler.logger, "info", lambda *a, **k: None)

    scheduler.archive_completed_tasks()

    cur_main = conn.cursors[0]
    assert any("DELETE FROM long_term_goals" in sql for sql, _ in cur_main.executed)
    cur_his = conn.cursors[1]
    assert any("INSERT INTO long_term_goals_his" in sql for sql, _ in cur_his.executed)
