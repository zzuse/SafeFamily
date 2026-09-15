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
        lambda token: {"sub": "admin", "is_admin": "admin"},
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


def test_tag_block_inserts(monkeypatch, admin_session):
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


class RecordingCursor:
    """Cursor that records SQL and optionally raises on execute."""

    def __init__(self, error=None):
        self.executed = []
        self.error = error

    def execute(self, sql, params=None):
        if self.error is not None:
            raise self.error
        self.executed.append((sql, params))

    def close(self):
        return None


class RecordingConn:
    def __init__(self, error=None):
        self.cursor_obj = RecordingCursor(error)
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        return None

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        return None


@pytest.fixture
def recording_conn(monkeypatch):
    conn = RecordingConn()
    monkeypatch.setattr(suspicious, "get_db_connection", lambda: conn)
    return conn


# Payloads observed from the 2026-08-25 scan.
SCANNER_PAYLOADS = [
    "; id ;",
    "||san666.com^\n;id;",
    "`id`",
    "$(id)",
    "|id",
    "x" * 8000,
]


@pytest.mark.parametrize("payload", SCANNER_PAYLOADS)
def test_update_filter_rule_rejects_scanner_payloads(recording_conn, admin_session, payload):
    resp = admin_session.post(
        "/update_filter_rule",
        data={"rule": payload, "date": "2025-01-01"},
    )

    assert resp.status_code == 302
    assert resp.location.endswith("/suspicious?date=2025-01-01")
    assert recording_conn.cursor_obj.executed == []


def test_update_filter_rule_splits_lines(recording_conn, admin_session):
    resp = admin_session.post(
        "/update_filter_rule",
        data={"rule": "a.example.com\r\n\n*.b.example.com\n", "date": "2025-01-01"},
    )

    assert resp.status_code == 302
    params = [p for sql, p in recording_conn.cursor_obj.executed if "INSERT INTO filter_rule (qh)" in sql]
    assert params == [("a.example.com",), ("*.b.example.com",)]


def test_update_filter_rule_rejects_too_many_lines(recording_conn, admin_session):
    rules = "\n".join(f"r{i}.example.com" for i in range(101))
    admin_session.post("/update_filter_rule", data={"rule": rules})
    assert recording_conn.cursor_obj.executed == []


def test_update_filter_rule_sanitizes_redirect_date(recording_conn, admin_session):
    resp = admin_session.post(
        "/update_filter_rule",
        data={"rule": "", "date": "2025-01-01&error=<script>"},
    )
    assert "<script>" not in resp.location
    assert "error=" not in resp.location


def test_tag_block_requires_admin(recording_conn, client):
    resp = client.post(
        "/tag_block",
        data={"qh": "example.com", "type": "game", "date": "2025-01-01"},
    )

    assert resp.status_code == 302
    assert "/auth/login-ui" in resp.location
    assert recording_conn.cursor_obj.executed == []


@pytest.mark.parametrize(
    ("qh", "type_"),
    [("example.com;id", "game"), ("example.com", "../tmp/x"), ("example.com", "vi deo")],
)
def test_tag_block_rejects_invalid_input(recording_conn, admin_session, qh, type_):
    admin_session.post("/tag_block", data={"qh": qh, "type": type_, "date": "2025-01-01"})
    assert recording_conn.cursor_obj.executed == []


def test_tag_block_db_error_rolls_back(monkeypatch, admin_session):
    import psycopg2

    conn = RecordingConn(error=psycopg2.Error("duplicate"))
    monkeypatch.setattr(suspicious, "get_db_connection", lambda: conn)

    resp = admin_session.post(
        "/tag_block",
        data={"qh": "example.com", "type": "game", "date": "2025-01-01"},
    )

    assert resp.status_code == 302
    assert conn.rollbacks == 1


@pytest.mark.parametrize(
    ("qh", "type_"),
    [("%medal.tv;id", "video"), ("example.com", "..\u2215tmp\u2215x"), ("example.com", "san666 ok"), ("", "game")],
)
def test_add_block_rejects_invalid_input(recording_conn, admin_session, qh, type_):
    resp = admin_session.post("/add_block?date=2025-01-01", data={"qh": qh, "type": type_})
    assert resp.status_code == 302
    assert recording_conn.cursor_obj.executed == []


def test_add_block_splits_lines_and_ignores_duplicates(recording_conn, admin_session):
    admin_session.post(
        "/add_block?date=2025-01-01",
        data={"qh": "%a.example.com\n%x.com/i/grok\n", "type": "game"},
    )

    executed = recording_conn.cursor_obj.executed
    assert [p for _, p in executed] == [("%a.example.com", "game"), ("%x.com/i/grok", "game")]
    assert all("ON CONFLICT (qh) DO NOTHING" in sql for sql, _ in executed)


def test_add_block_db_error_rolls_back(monkeypatch, admin_session):
    import psycopg2

    conn = RecordingConn(error=psycopg2.Error("boom"))
    monkeypatch.setattr(suspicious, "get_db_connection", lambda: conn)

    resp = admin_session.post("/add_block", data={"qh": "example.com", "type": "game"})

    assert resp.status_code == 302
    assert conn.rollbacks == 1


def test_modify_block_rejects_invalid_input(recording_conn, admin_session):
    admin_session.post(
        "/modify_block/1981?date=2025-01-01",
        data={"qh": "%medal.tv;id", "type": " video"},
    )
    assert recording_conn.cursor_obj.executed == []


def test_modify_block_db_error_rolls_back(monkeypatch, admin_session):
    import psycopg2

    conn = RecordingConn(error=psycopg2.Error("boom"))
    monkeypatch.setattr(suspicious, "get_db_connection", lambda: conn)

    resp = admin_session.post("/modify_block/1", data={"qh": "example.com", "type": "game"})

    assert resp.status_code == 302
    assert conn.rollbacks == 1


def test_view_suspicious_invalid_params_fall_back(monkeypatch, admin_session):
    cursor = CursorQueue(
        fetchone_values=[(0,), (0,), (0,), (1,)],
        fetchall_values=[[], [], [], []],
    )
    monkeypatch.setattr(suspicious, "get_db_connection", lambda: ConnQueue(cursor))
    monkeypatch.setattr(suspicious, "render_template", lambda *a, **k: ("ok", 200))

    resp = admin_session.get(
        "/suspicious",
        query_string={"date": "x'; --", "page": "abc", "block_page": "-3", "rule_page": "9" * 5000},
    )

    assert resp.status_code == 200
    assert cursor.executed[0][1][0] == suspicious._today()
    assert cursor.executed[1][1][2] == 0  # offset for page 1
