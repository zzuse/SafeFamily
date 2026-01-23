"""Tests for blocker rules."""

from types import SimpleNamespace

from src.safe_family.core import auth
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


def test_update_blocked_services_puts(monkeypatch, patch_requests):
    monkeypatch.setattr(blocker, "ADGUARD_BASE_URL", "http://adguard")

    blocker._update_blocked_services(["discord"])

    assert patch_requests
    call = patch_requests[0]
    assert "/control/blocked_services/update" in call.args[0]
    assert call.kwargs["json"]["ids"] == ["discord"]


def test_rule_stop_traffic_all_hits_router(monkeypatch, patch_requests):
    monkeypatch.setattr(blocker, "ROUTER_BASE_URL", "http://router")

    blocker.rule_stop_traffic_all()

    assert patch_requests
    call = patch_requests[0]
    assert "/cgi-bin/disablegateway.sh" in call.args[0]


def test_rules_disable_ai_cooldown(client, monkeypatch):
    monkeypatch.setattr(auth, "decode_token", lambda token: {"sub": "user"})
    with client.session_transaction() as sess:
        sess["access_token"] = "token"
    blocker.DISABLE_AI_STATE["last_run"] = 100.0
    monkeypatch.setattr(blocker.time_module, "monotonic", lambda: 105.0)
    monkeypatch.setattr(blocker, "flash", lambda *a, **k: None)

    resp = client.post("/rules_toggle/disable_ai")

    assert resp.status_code == 302


def test_rules_disable_ai_success(client, monkeypatch):
    monkeypatch.setattr(auth, "decode_token", lambda token: {"sub": "user"})
    with client.session_transaction() as sess:
        sess["access_token"] = "token"
    blocker.DISABLE_AI_STATE["last_run"] = 0.0
    monkeypatch.setattr(blocker.time_module, "monotonic", lambda: 100.0)
    monkeypatch.setattr(blocker, "flash", lambda *a, **k: None)
    monkeypatch.setattr(blocker, "rule_disable_ai", lambda: SimpleNamespace(status_code=200))

    resp = client.post("/rules_toggle/disable_ai")

    assert resp.status_code == 302


def test_rule_enable_all_except_ai_calls_updates(monkeypatch):
    calls = {"rules": None, "blocked": None}
    monkeypatch.setattr(blocker, "_run_rule_updates", lambda rules: calls.__setitem__("rules", rules))
    monkeypatch.setattr(
        blocker,
        "_update_blocked_services",
        lambda ids: calls.__setitem__("blocked", ids) or SimpleNamespace(status_code=200, text="ok"),
    )

    resp = blocker.rule_enable_all_except_ai()

    assert resp.status_code == 200
    assert calls["rules"] is not None
    assert calls["blocked"] is not None


def test_rule_disable_all_calls_updates(monkeypatch):
    calls = {"rules": None, "blocked": None}
    monkeypatch.setattr(blocker, "_run_rule_updates", lambda rules: calls.__setitem__("rules", rules))
    monkeypatch.setattr(
        blocker,
        "_update_blocked_services",
        lambda ids: calls.__setitem__("blocked", ids) or SimpleNamespace(status_code=200, text="ok"),
    )

    resp = blocker.rule_disable_all()

    assert resp.status_code == 200
    assert calls["rules"] is not None
    assert calls["blocked"] is not None
