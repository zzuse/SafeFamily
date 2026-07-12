"""Tests for scheduler utilities."""

from datetime import time
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
    # One DB job + analyze_logs + gas_weather_report + notify_overdue_task_feedback + run_adguard_pull
    assert len(fake_scheduler.jobs) == 5
    assert fake_scheduler.jobs[0].id == "rule_1"
    assert "gas_weather_report" in {job.id for job in fake_scheduler.jobs}
