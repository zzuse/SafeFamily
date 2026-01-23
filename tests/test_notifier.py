"""Tests for notification helpers."""

import contextlib

from src.safe_family.notifications import notifier


def test_send_email_notification(app, monkeypatch, patch_mail):
    monkeypatch.setattr(
        notifier.settings,
        "MAIL_PERSON_LIST",
        "['admin@example.com']",
    )
    with app.app_context():
        notifier.send_email_notification(
            "alice",
            [{"time_slot": "10:00 - 11:00", "task": "Read"}],
        )
    assert patch_mail
    message = patch_mail[0]
    assert "New Todo Update" in message.subject
    assert message.recipients == ["admin@example.com"]


def test_send_discord_notification_posts(monkeypatch, patch_requests):
    monkeypatch.setattr(
        notifier.settings,
        "DISCORD_WEBHOOK_URL",
        "http://example.com",
    )
    notifier.send_discord_notification(
        "bob",
        [{"time_slot": "09:00 - 10:00", "task": "Study"}],
    )
    assert patch_requests
    assert patch_requests[0].args[0] == "http://example.com"


def test_send_discord_summary_posts(monkeypatch, patch_requests):
    monkeypatch.setattr(
        notifier.settings,
        "DISCORD_WEBHOOK_URL",
        "http://example.com",
    )
    notifier.send_discord_summary("alice", "summary", "2025-W01", "2024-W52")
    assert patch_requests
    assert patch_requests[0].args[0] == "http://example.com"


def test_send_discord_summary_skips_when_disabled(monkeypatch, patch_requests):
    monkeypatch.setattr(notifier.settings, "DISCORD_WEBHOOK_URL", "")
    notifier.send_discord_summary("alice", "summary", "2025-W01", "2024-W52")
    assert patch_requests == []


def test_send_hammerspoon_alert_posts(monkeypatch, patch_requests):
    monkeypatch.setattr(notifier.settings, "HAMMERSPOON_ALERT_URL", "http://localhost:9181/alert")
    monkeypatch.setattr(notifier, "_is_hammerspoon_available", lambda url: True)
    notifier.send_hammerspoon_alert("hello")
    assert patch_requests
    assert patch_requests[0].args[0] == "http://localhost:9181/alert"


def test_send_hammerspoon_task_posts(monkeypatch, patch_requests):
    monkeypatch.setattr(notifier.settings, "HAMMERSPOON_TASK_URL", "http://localhost:9181/task")
    monkeypatch.setattr(notifier, "_is_hammerspoon_available", lambda url: True)
    notifier.send_hammerspoon_task("alice", "Read", "09:00 - 10:00")
    assert patch_requests
    assert patch_requests[0].args[0] == "http://localhost:9181/task"


def test_is_hammerspoon_available_missing_host():
    assert notifier._is_hammerspoon_available("http://") is False


def test_is_hammerspoon_available_socket_error(monkeypatch):
    monkeypatch.setattr(
        notifier.socket,
        "create_connection",
        lambda *a, **k: (_ for _ in ()).throw(OSError("fail")),
    )
    assert notifier._is_hammerspoon_available("http://localhost:9181/alert") is False


def test_is_hammerspoon_available_options_error(monkeypatch):
    monkeypatch.setattr(
        notifier.socket,
        "create_connection",
        lambda *a, **k: contextlib.nullcontext(),
    )
    monkeypatch.setattr(
        notifier.requests,
        "options",
        lambda *a, **k: (_ for _ in ()).throw(notifier.requests.RequestException("fail")),
    )
    assert notifier._is_hammerspoon_available("http://localhost:9181/alert") is False


def test_is_hammerspoon_available_success(monkeypatch):
    monkeypatch.setattr(
        notifier.socket,
        "create_connection",
        lambda *a, **k: contextlib.nullcontext(),
    )
    monkeypatch.setattr(notifier.requests, "options", lambda *a, **k: None)
    assert notifier._is_hammerspoon_available("http://localhost:9181/alert") is True
