"""Tests for the weekly audit matrix on /todo."""

from datetime import date, datetime
from types import SimpleNamespace

import pytest

from src.safe_family.core import auth
from src.safe_family.core.extensions import db
from src.safe_family.core.models import AuditItem, AuditMark, User
from src.safe_family.todo import todo

# Wednesday; the current week runs Mon 2026-09-14 .. Sun 2026-09-20.
TODAY = date(2026, 9, 16)


class FixedDatetime(datetime):
    """datetime whose now() is pinned to TODAY at noon."""

    @classmethod
    def now(cls, tz=None):
        return cls(TODAY.year, TODAY.month, TODAY.day, 12, 0, tzinfo=tz)


class SeqCursor:
    """Cursor that returns queued values for fetchone/fetchall."""

    def __init__(self, fetchone_values=None, fetchall_values=None):
        self.fetchone_values = list(fetchone_values or [])
        self.fetchall_values = list(fetchall_values or [])

    def execute(self, sql, params=None):
        return None

    def fetchone(self):
        return self.fetchone_values.pop(0) if self.fetchone_values else None

    def fetchall(self):
        return self.fetchall_values.pop(0) if self.fetchall_values else []

    def close(self):
        return None


class SeqConnection:
    """Connection wrapper for SeqCursor."""

    def __init__(self, cursor):
        self.cursor_obj = cursor

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        return None

    def close(self):
        return None


@pytest.fixture
def seeded(app):
    """Seed the default audit rows and a kid user."""
    items = [
        AuditItem(name="Hang Socks", sort_order=3),
        AuditItem(name="Piano", sort_order=1),
        AuditItem(name="Math", sort_order=2),
    ]
    db.session.add_all(items)
    db.session.add(User(id="kid-id", username="kid", email="kid@example.com", password_hash="x"))
    db.session.commit()
    return {item.name: item.id for item in items}


def _admin_session(client, monkeypatch):
    monkeypatch.setattr(auth, "decode_token", lambda token: {"sub": "admin", "is_admin": "admin"})
    with client.session_transaction() as sess:
        sess["access_token"] = "token"


def _user_session(client, monkeypatch):
    monkeypatch.setattr(auth, "decode_token", lambda token: {"sub": "kid-id"})
    with client.session_transaction() as sess:
        sess["access_token"] = "token"


def _post_mark(client, item_id, value, mark_date="2026-09-15", user_id="kid-id"):
    return client.post(
        "/todo/audit_mark",
        json={"item_id": item_id, "user_id": user_id, "date": mark_date, "value": value},
    )


@pytest.mark.parametrize(
    ("today", "monday"),
    [
        (date(2026, 9, 14), date(2026, 9, 14)),
        (date(2026, 9, 16), date(2026, 9, 14)),
        (date(2026, 9, 20), date(2026, 9, 14)),
    ],
)
def test_current_week_start(today, monday):
    assert todo.current_week_start(today) == monday


def test_build_audit_matrix_shows_only_this_weeks_marks(seeded):
    db.session.add_all(
        [
            AuditMark(item_id=seeded["Piano"], user_id="kid-id", mark_date=date(2026, 9, 15), value="yes"),
            AuditMark(item_id=seeded["Math"], user_id="kid-id", mark_date=date(2026, 9, 20), value="no"),
            # last Sunday: before this Monday, never shown
            AuditMark(item_id=seeded["Piano"], user_id="kid-id", mark_date=date(2026, 9, 13), value="no"),
            # another user's mark in the same week
            AuditMark(item_id=seeded["Math"], user_id="other-id", mark_date=date(2026, 9, 16), value="yes"),
        ],
    )
    db.session.commit()

    matrix = todo.build_audit_matrix("kid-id", TODAY)

    assert [d["label"] for d in matrix["days"]] == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    assert matrix["days"][0]["date"] == "2026-09-14"
    assert [d["is_today"] for d in matrix["days"]] == [False, False, True, False, False, False, False]
    assert [row["name"] for row in matrix["rows"]] == ["Piano", "Math", "Hang Socks"]
    cells = {row["name"]: row["cells"] for row in matrix["rows"]}
    assert cells["Piano"] == [None, "yes", None, None, None, None, None]
    assert cells["Math"] == [None, None, None, None, None, None, "no"]
    assert cells["Hang Socks"] == [None] * 7


def test_build_audit_matrix_is_all_null_on_a_new_monday(seeded):
    db.session.add(AuditMark(item_id=seeded["Piano"], user_id="kid-id", mark_date=date(2026, 9, 20), value="yes"))
    db.session.commit()

    matrix = todo.build_audit_matrix("kid-id", date(2026, 9, 21))

    assert matrix["days"][0]["date"] == "2026-09-21"
    assert all(cell is None for row in matrix["rows"] for cell in row["cells"])


def test_audit_mark_sets_updates_and_clears(client, monkeypatch, seeded):
    monkeypatch.setattr(todo, "datetime", FixedDatetime)
    _admin_session(client, monkeypatch)
    piano = seeded["Piano"]

    resp = _post_mark(client, piano, "YES")
    assert resp.status_code == 200
    assert resp.get_json() == {"success": True, "value": "yes"}
    assert AuditMark.query.one().value == "yes"

    assert _post_mark(client, piano, "no").status_code == 200
    assert AuditMark.query.one().value == "no"

    resp = _post_mark(client, piano, "")
    assert resp.get_json() == {"success": True, "value": None}
    assert AuditMark.query.count() == 0

    # clearing an already-null cell is a no-op
    assert _post_mark(client, piano, "").status_code == 200


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"value": "maybe"}, (400, "invalid value")),
        ({"item_id": "abc"}, (400, "invalid item or date")),
        ({"mark_date": "not-a-date"}, (400, "invalid item or date")),
        ({"mark_date": "2026-09-13"}, (403, "date outside this week")),
        ({"mark_date": "2026-09-21"}, (403, "date outside this week")),
        ({"user_id": ""}, (403, "date outside this week")),
        ({"item_id": 9999}, (404, "item or user not found")),
        ({"user_id": "ghost-id"}, (404, "item or user not found")),
    ],
)
def test_audit_mark_rejects_bad_input(client, monkeypatch, seeded, overrides, expected):
    monkeypatch.setattr(todo, "datetime", FixedDatetime)
    _admin_session(client, monkeypatch)
    args = {"item_id": seeded["Piano"], "value": "yes", **overrides}

    resp = _post_mark(client, **args)

    assert (resp.status_code, resp.get_json()["error"]) == expected
    assert AuditMark.query.count() == 0


def test_audit_mark_requires_admin(client, monkeypatch, seeded):
    monkeypatch.setattr(todo, "datetime", FixedDatetime)
    _user_session(client, monkeypatch)

    resp = _post_mark(client, seeded["Piano"], "yes")

    assert resp.status_code == 302
    assert AuditMark.query.count() == 0


def _render_todo(client, monkeypatch, role, fetchall_values):
    cursor = SeqCursor(fetchone_values=[("kid", "kid-id")], fetchall_values=fetchall_values)
    monkeypatch.setattr(todo, "datetime", FixedDatetime)
    monkeypatch.setattr(todo, "get_db_connection", lambda: SeqConnection(cursor))
    monkeypatch.setattr(todo, "get_agile_config", lambda k, d="": d)
    monkeypatch.setattr(todo, "get_current_username", lambda: SimpleNamespace(username="kid", role=role))
    monkeypatch.setattr(todo, "generate_time_slots", lambda *a, **k: ["09:00 - 10:00"])
    monkeypatch.setattr(
        todo,
        "build_week_strip_and_heatmap",
        lambda *a, **k: ([], {"start": "", "weeks": [], "month_labels": []}),
    )
    monkeypatch.setattr(auth, "decode_token", lambda token: {"sub": "kid-id"})
    with client.session_transaction() as sess:
        sess["access_token"] = "token"
    resp = client.get("/todo")
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def test_todo_page_shows_read_only_audit_for_user(client, monkeypatch, seeded):
    db.session.add(AuditMark(item_id=seeded["Math"], user_id="kid-id", mark_date=TODAY, value="yes"))
    db.session.commit()

    html = _render_todo(client, monkeypatch, "user", [[]])

    assert "Weekly audit" in html
    assert "2026-09-14 → 2026-09-20" in html
    assert '<span class="sf-audit-value" data-value="yes">yes</span>' in html
    assert html.count('<span class="sf-audit-value" data-value="">null</span>') == 20
    assert '<select class="sf-audit-select"' not in html


def test_todo_page_shows_editable_audit_for_admin(client, monkeypatch, seeded):
    html = _render_todo(client, monkeypatch, "admin", [[("kid",)], []])

    assert html.count('<select class="sf-audit-select"') == 21
    assert f'data-item-id="{seeded["Piano"]}" data-user-id="kid-id"' in html
    assert 'data-date="2026-09-20"' in html
    assert '<span class="sf-audit-value"' not in html


def test_todo_page_shows_empty_audit_message_without_items(client, monkeypatch):
    html = _render_todo(client, monkeypatch, "user", [[]])

    assert "No audit items yet." in html
