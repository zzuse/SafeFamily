"""Tests for analyzer utilities."""

from datetime import datetime

import pandas as pd

from src.safe_family.urls import analyzer


class AnalysisCursor:
    """Cursor stub for log_analysis."""

    def __init__(self):
        self.executed = []
        self.last_sql = ""

    def execute(self, sql, params=None):
        self.last_sql = sql
        self.executed.append((sql, params))

    def fetchall(self):
        if "filter_rule" in self.last_sql:
            return [("allowed*",)]
        return []

    def close(self):
        return None


class AnalysisConn:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.commits = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def close(self):
        return None


def test_log_analysis_inserts(monkeypatch):
    cursor = AnalysisCursor()
    conn = AnalysisConn(cursor)
    monkeypatch.setattr(analyzer, "get_db_connection", lambda: conn)

    df = pd.DataFrame({"qh": ["blocked.com", "allowed.com", "blocked.com"]})
    monkeypatch.setattr(pd, "read_sql", lambda *a, **k: df)

    start = datetime(2025, 1, 1, 0, 0)
    end = datetime(2025, 1, 2, 0, 0)

    analyzer.log_analysis(start, end)

    assert any("logs_daily" in sql for sql, _ in cursor.executed)
    assert any("suspicious" in sql for sql, _ in cursor.executed)
    assert conn.commits >= 1
