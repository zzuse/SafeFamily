"""Tests for the daily gas price / weather Telegram report."""

from unittest.mock import MagicMock

from src.safe_family.notifications import gas_weather


def _configure_telegram(monkeypatch):
    monkeypatch.setattr(gas_weather.settings, "TELEGRAM_BOT", "bot-token")
    monkeypatch.setattr(gas_weather.settings, "TELEGRAM_CHAT_ID", "chat-1")


def test_prepare_weather_message(monkeypatch):
    monkeypatch.setattr(gas_weather.settings, "LONGTITUDE_LATITUDE", "49.9,-97.1")
    link = gas_weather.prepare_weather_message()
    assert link == "https://weather.gc.ca/en/forecast/hourly/index.html?coords=49.9,-97.1"


def test_send_telegram_message_posts(monkeypatch, patch_requests):
    _configure_telegram(monkeypatch)
    gas_weather.send_telegram_message("hello")
    assert patch_requests
    call = patch_requests[0]
    assert call.args[0] == "https://api.telegram.org/botbot-token/sendMessage"
    assert call.kwargs["data"] == {"chat_id": "chat-1", "text": "hello"}


def test_send_telegram_message_swallows_request_error(monkeypatch):
    _configure_telegram(monkeypatch)

    def _raise(*args, **kwargs):
        raise gas_weather.requests.RequestException("boom")

    monkeypatch.setattr(gas_weather.requests, "post", _raise)
    gas_weather.send_telegram_message("hello")


def test_send_telegram_photo_posts(monkeypatch, patch_requests, tmp_path):
    _configure_telegram(monkeypatch)
    photo = tmp_path / "gas.png"
    photo.write_bytes(b"png-bytes")

    gas_weather.send_telegram_photo(photo, caption="today")

    assert patch_requests
    call = patch_requests[0]
    assert call.args[0] == "https://api.telegram.org/botbot-token/sendPhoto"
    assert call.kwargs["data"] == {"chat_id": "chat-1", "caption": "today"}
    assert "photo" in call.kwargs["files"]


def test_send_telegram_photo_swallows_request_error(monkeypatch, tmp_path):
    _configure_telegram(monkeypatch)
    photo = tmp_path / "gas.png"
    photo.write_bytes(b"png-bytes")

    def _raise(*args, **kwargs):
        raise gas_weather.requests.RequestException("boom")

    monkeypatch.setattr(gas_weather.requests, "post", _raise)
    gas_weather.send_telegram_photo(photo)


def test_take_gas_snapshot_uses_playwright(monkeypatch, tmp_path):
    playwright_cm = MagicMock()
    monkeypatch.setattr(
        "playwright.sync_api.sync_playwright",
        lambda: playwright_cm,
    )
    p = playwright_cm.__enter__.return_value
    browser = p.firefox.launch.return_value
    page = browser.new_page.return_value

    out_file = gas_weather.take_gas_snapshot(out_dir=tmp_path)

    assert out_file.parent == tmp_path
    assert out_file.name.startswith("gas_")
    assert out_file.suffix == ".png"
    page.goto.assert_called_once()
    assert page.goto.call_args.args[0] == gas_weather.GAS_URL
    page.screenshot.assert_called_once_with(path=str(out_file))
    browser.close.assert_called_once()


def test_report_skips_when_not_configured(monkeypatch, patch_requests):
    monkeypatch.setattr(gas_weather.settings, "TELEGRAM_BOT", "")
    monkeypatch.setattr(gas_weather.settings, "TELEGRAM_CHAT_ID", "")
    gas_weather.send_gas_weather_report()
    assert patch_requests == []


def test_report_sends_weather_and_photo(monkeypatch, patch_requests, tmp_path):
    _configure_telegram(monkeypatch)
    photo = tmp_path / "gas.png"
    photo.write_bytes(b"png-bytes")
    monkeypatch.setattr(gas_weather, "take_gas_snapshot", lambda: photo)

    gas_weather.send_gas_weather_report()

    assert len(patch_requests) == 2
    assert patch_requests[0].args[0].endswith("/sendMessage")
    assert patch_requests[1].args[0].endswith("/sendPhoto")
    assert gas_weather.GAS_URL in patch_requests[1].kwargs["data"]["caption"]


def test_report_falls_back_when_snapshot_fails(monkeypatch, patch_requests):
    _configure_telegram(monkeypatch)

    def _raise():
        raise RuntimeError("browser crashed")

    monkeypatch.setattr(gas_weather, "take_gas_snapshot", _raise)

    gas_weather.send_gas_weather_report()

    assert len(patch_requests) == 2
    assert patch_requests[1].kwargs["data"]["text"] == "gas price not available"
