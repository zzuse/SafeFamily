"""Tests for the log receiver route."""

from src.safe_family.urls import receiver

from .conftest import FakeConnection


def test_receive_log_success(client, monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(receiver, "get_db_connection", lambda: conn)

    resp = client.post(
        "/logs",
        json={
            "T": "2025-01-01T00:00:00",
            "IP": "1.1.1.1",
            "QH": "abc",
            "Result": {"IsFiltered": True},
        },
    )

    assert resp.status_code == 201
    sql, params = conn.cursor_obj.queries[0]
    assert "INSERT INTO logs" in sql
    assert params[1] == "1.1.1.1"
    assert conn.commits == 1


def test_receive_log_invalid_json(client):
    resp = client.post(
        "/logs",
        data="{}",
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Invalid JSON"
