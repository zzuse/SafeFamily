"""Tests for the log receiver route."""

from unittest.mock import MagicMock
from src.safe_family.urls import receiver
from .conftest import FakeConnection, FakeCursor


class MockCursor(FakeCursor):
    """Cursor that simulates rowcount."""
    def __init__(self, rows=None):
        super().__init__(rows)
        self.rowcount = 0

    def execute(self, sql, params=None):
        super().execute(sql, params)
        if "INSERT" in sql:
            self.rowcount = 1
        else:
            self.rowcount = 0


class MockConnection(FakeConnection):
    """Connection returning MockCursor."""
    def __init__(self, rows=None):
        super().__init__(rows)
        self.cursor_obj = MockCursor(rows)


def test_receive_log_success(client, monkeypatch):
    """Test successful log pull from AdGuard."""
    # Mock DB connection - return None for MAX(timestamp) so it defaults to pulling all
    conn = MockConnection(rows=[(None,)])
    monkeypatch.setattr(receiver, "get_db_connection", lambda: conn)

    # Mock AdGuard response
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": [
            {
                "question": {"name": "google.com"},
                "time": "2025-01-29T12:00:01Z",
                "client": "1.2.3.4",
                "reason": "Rewritten",
            },
            {
                "question": {"name": "bad.com"},
                "time": "2025-01-29T12:00:00Z",
                "client": "1.2.3.4",
                "reason": "FilteredBlackList",
            },
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: mock_resp)

    # Call the endpoint (POST /logs)
    resp = client.post("/logs")

    assert resp.status_code == 200
    assert resp.json == {"inserted": 2}

    # Verify DB interactions
    queries = conn.cursor_obj.queries
    # 1. SELECT MAX(timestamp)
    # 2. INSERT ... (bad.com) - oldest first
    # 3. INSERT ... (google.com) - newest last
    
    selects = [q for q in queries if "SELECT MAX" in q[0]]
    inserts = [q for q in queries if "INSERT INTO logs" in q[0]]

    assert len(selects) == 1
    assert len(inserts) == 2

    # Check oldest log (bad.com)
    sql_1, params_1 = inserts[0]
    assert params_1[2] == "bad.com"  # qh
    assert params_1[3] is True       # is_filtered (FilteredBlackList)

    # Check newest log (google.com)
    sql_2, params_2 = inserts[1]
    assert params_2[2] == "google.com"
    assert params_2[3] is False      # is_filtered (Rewritten != FilteredBlackList)

    assert conn.commits == 1


def test_receive_log_adguard_failure(client, monkeypatch):
    """Test failure when pulling from AdGuard."""
    conn = FakeConnection(rows=[(None,)])
    monkeypatch.setattr(receiver, "get_db_connection", lambda: conn)

    def _fail(*args, **kwargs):
        raise Exception("AdGuard Network Error")

    monkeypatch.setattr("requests.get", _fail)

    resp = client.post("/logs")
    assert resp.status_code == 500
    assert "AdGuard Network Error" in resp.json["error"]


def test_receive_log_db_error(client, monkeypatch):
    """Test DB connection failure."""
    def _raise():
        raise Exception("DB Connection Failed")

    monkeypatch.setattr(receiver, "get_db_connection", _raise)

    resp = client.post("/logs")

    assert resp.status_code == 500
    assert "DB Connection Failed" in resp.json["error"]