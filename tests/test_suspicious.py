"""Tests for suspicious routes."""

from datetime import date

import pytest

from src.safe_family.urls import suspicious


class CursorQueue:
    """Cursor that returns queued results for fetchone/fetchall."""

    def __init__(self, fetchone_values, fetchall_values):
        self.fetchone_values = list(fetchone_values)
        self.fetchall_values = list(fetchall_values)
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self.fetchone_values.pop(0)

    def fetchall(self):
        return self.fetchall_values.pop(0)

    def close(self):
        return None


class ConnQueue:
    """Connection wrapper for CursorQueue."""

    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        return None

    def close(self):
        self.closed = True


@pytest.fixture
def admin_session(monkeypatch, client):
    """Inject admin session token by bypassing JWT decode."""
    monkeypatch.setattr(
        "src.safe_family.core.auth.decode_token",
        lambda token: {"sub": "user", "is_admin": "admin"},
    )
    with client.session_transaction() as sess:
        sess["access_token"] = "token"
    return client


def test_view_suspicious_renders(monkeypatch, admin_session):
    """Ensure view_suspicious returns 200 with mocked DB and template."""
    today = date.today().strftime("%Y-%m-%d")
    cursor = CursorQueue(
        fetchone_values=[
            (1,),  # total suspicious count
            (2,),  # total_blocks
            (3,),  # total_rules
            (0,),  # count_yesterday
        ],
        fetchall_values=[
            [("2025-01-01", "qh1", 5)],  # suspicious_data
            [("block",)],  # block_list
            [("filter_rule",)],  # filter_rules
            [("typeA",)],  # block_types
        ],
    )
    conn = ConnQueue(cursor)
    monkeypatch.setattr(suspicious, "get_db_connection", lambda: conn)
    monkeypatch.setattr(suspicious, "render_template", lambda *a, **k: ("ok", 200))

    resp = admin_session.get("/suspicious", query_string={"date": today})

    assert resp.status_code == 200
    assert conn.closed
    # validate at least the first query used the provided date
    assert cursor.executed[0][1][0] == today


def test_update_filter_rule_inserts(monkeypatch, admin_session):
    class SimpleCursor:
        def __init__(self):
            self.executed = []

        def execute(self, sql, params=None):
            self.executed.append((sql, params))

        def close(self):
            return None

    class SimpleConn:
        def __init__(self):
            self.cursor_obj = SimpleCursor()
            self.commits = 0

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            self.commits += 1

        def close(self):
            return None

    conn = SimpleConn()
    monkeypatch.setattr(suspicious, "get_db_connection", lambda: conn)

    resp = admin_session.post(
        "/update_filter_rule",
        data={"rule": ["example.com"], "date": "2025-01-01"},
    )

    assert resp.status_code == 302
    assert any("INSERT INTO filter_rule" in sql for sql, _ in conn.cursor_obj.executed)


def test_delete_block_deletes_row(monkeypatch, admin_session):
    class SimpleCursor:
        def __init__(self):
            self.executed = []

        def execute(self, sql, params=None):
            self.executed.append((sql, params))

        def close(self):
            return None

    class SimpleConn:
        def __init__(self):
            self.cursor_obj = SimpleCursor()

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            return None

        def close(self):
            return None

    conn = SimpleConn()
    monkeypatch.setattr(suspicious, "get_db_connection", lambda: conn)

    resp = admin_session.get("/delete_block/10")

    assert resp.status_code == 302
    assert any("DELETE FROM block_list" in sql for sql, _ in conn.cursor_obj.executed)


def test_tag_block_inserts(monkeypatch, client):
    class SimpleCursor:
        def __init__(self):
            self.executed = []

        def execute(self, sql, params=None):
            self.executed.append((sql, params))

        def close(self):
            return None

    class SimpleConn:
        def __init__(self):
            self.cursor_obj = SimpleCursor()

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            return None

        def close(self):
            return None

    conn = SimpleConn()
    monkeypatch.setattr(suspicious, "get_db_connection", lambda: conn)
    monkeypatch.setattr(suspicious, "flash", lambda *a, **k: None)

    resp = client.post(
        "/tag_block",
        data={"qh": "example.com", "type": "game", "date": "2025-01-01"},
    )

    assert resp.status_code == 302
    assert any("INSERT INTO block_list" in sql for sql, _ in conn.cursor_obj.executed)


def test_add_block_inserts(monkeypatch, admin_session):
    class SimpleCursor:
        def __init__(self):
            self.executed = []

        def execute(self, sql, params=None):
            self.executed.append((sql, params))

        def close(self):
            return None

    class SimpleConn:
        def __init__(self):
            self.cursor_obj = SimpleCursor()

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            return None

        def close(self):
            return None

    conn = SimpleConn()
    monkeypatch.setattr(suspicious, "get_db_connection", lambda: conn)

    resp = admin_session.post(
        "/add_block?date=2025-01-01",
        data={"qh": "example.com", "type": "game"},
    )

    assert resp.status_code == 302
    assert any("INSERT INTO block_list" in sql for sql, _ in conn.cursor_obj.executed)


def test_delete_filter_rule_deletes(monkeypatch, admin_session):
    class SimpleCursor:
        def __init__(self):
            self.executed = []

        def execute(self, sql, params=None):
            self.executed.append((sql, params))

        def close(self):
            return None

    class SimpleConn:
        def __init__(self):
            self.cursor_obj = SimpleCursor()

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            return None

        def close(self):
            return None

    conn = SimpleConn()
    monkeypatch.setattr(suspicious, "get_db_connection", lambda: conn)
    monkeypatch.setattr(suspicious, "flash", lambda *a, **k: None)

    resp = admin_session.post("/delete_filter_rule/rule-1?date=2025-01-01")

    assert resp.status_code == 302
    assert any("DELETE FROM filter_rule" in sql for sql, _ in conn.cursor_obj.executed)


def test_modify_block_updates(monkeypatch, admin_session):
    class SimpleCursor:
        def __init__(self):
            self.executed = []

        def execute(self, sql, params=None):
            self.executed.append((sql, params))

        def close(self):
            return None

    class SimpleConn:
        def __init__(self):
            self.cursor_obj = SimpleCursor()

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            return None

        def close(self):
            return None

    conn = SimpleConn()
    monkeypatch.setattr(suspicious, "get_db_connection", lambda: conn)
    monkeypatch.setattr(suspicious, "flash", lambda *a, **k: None)

    resp = admin_session.post(
        "/modify_block/10?date=2025-01-01",
        data={"qh": "example.com", "type": "game"},
    )

    assert resp.status_code == 302
    assert any("UPDATE block_list" in sql for sql, _ in conn.cursor_obj.executed)
