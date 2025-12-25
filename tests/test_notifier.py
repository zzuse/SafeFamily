"""Tests for notification helpers."""

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
