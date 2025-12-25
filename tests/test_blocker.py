"""Tests for blocker rules."""

from src.safe_family.urls import blocker


def test_rule_enable_ai_posts(monkeypatch, patch_requests):
    monkeypatch.setattr(blocker.settings, "ADGUARD_HOSTPORT", "localhost")
    monkeypatch.setattr(blocker.settings, "ADGUARD_USERNAME", "user")
    monkeypatch.setattr(blocker.settings, "ADGUARD_PASSWORD", "pass")

    blocker.rule_enable_ai()

    assert patch_requests
    call = patch_requests[0]
    assert "/control/filtering/set_url" in call.args[0]
    assert call.kwargs["json"]["data"]["name"] == "AI"
