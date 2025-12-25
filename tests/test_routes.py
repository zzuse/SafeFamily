"""Route and CLI tests using shared fixtures."""

from src.safe_family.cli import gentags
from .conftest import FakeConnection


def test_root_redirects_to_todo(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/todo")


def test_store_sum_renders_when_logged_in(client, monkeypatch):
    # Bypass JWT validation and provide a session token
    monkeypatch.setattr(
        "src.safe_family.core.auth.decode_token",
        lambda token: {"sub": "user"},
    )
    with client.session_transaction() as sess:
        sess["access_token"] = "token"

    resp = client.get("/store_sum")
    assert resp.status_code == 200


def test_gentags_main_updates_tags(monkeypatch):
    fake_conn = FakeConnection(rows=[("math study", 1)])
    monkeypatch.setattr(gentags, "get_db_connection", lambda: fake_conn)

    gentags.main([])

    queries = fake_conn.cursor_obj.queries
    assert any("UPDATE todo_list" in q[0] for q in queries)
    assert fake_conn.commits == 1

