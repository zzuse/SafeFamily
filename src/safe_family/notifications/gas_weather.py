"""Daily gas price snapshot and weather report sent to Telegram.

Replaces the old GasBuddy scraper: takes a full-page screenshot of the
CBC Manitoba gas prices page with Playwright and sends it as a photo,
along with the weather.gc.ca hourly forecast link.
"""

import logging
from datetime import datetime
from pathlib import Path

import requests

from config.settings import BASE_DIR, settings
from src.safe_family.core.extensions import local_tz

logger = logging.getLogger(__name__)

GAS_URL = "https://www.cbc.ca/manitoba/features/gasprices/"
SNAPSHOT_DIR = BASE_DIR / "logs" / "snapshots"
TELEGRAM_TIMEOUT = 10


def _telegram_url(method: str) -> str:
    return f"https://api.telegram.org/bot{settings.TELEGRAM_BOT}/{method}"


def _today() -> str:
    return datetime.now(local_tz).date().isoformat()


def prepare_weather_message() -> str:
    """Return the weather.gc.ca hourly forecast link for the configured location."""
    return (
        "https://weather.gc.ca/en/forecast/hourly/index.html"
        f"?coords={settings.LONGTITUDE_LATITUDE}"
    )


def take_gas_snapshot(out_dir: Path = SNAPSHOT_DIR) -> Path:
    """Screenshot the CBC gas prices page and return the PNG path.

    Uses Firefox: cbc.ca's CDN rejects headless Chromium with
    net::ERR_HTTP2_PROTOCOL_ERROR.
    """
    # Lazy import: keeps the app importable in environments without Playwright.
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"gas_{_today()}.png"

    with sync_playwright() as p:
        browser = p.firefox.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 1600})
        page.goto(GAS_URL, wait_until="domcontentloaded", timeout=60_000)
        # Give the price widget a moment to finish drawing.
        page.wait_for_timeout(4_000)
        _dismiss_privacy_banner(page)
        page.screenshot(path=str(out_file))
        browser.close()

    logger.info("Saved gas snapshot %s", out_file)
    return out_file


def _dismiss_privacy_banner(page) -> None:  # noqa: ANN001
    """Close the cookie-consent banner so it does not cover the price chart."""
    try:
        page.get_by_role("button", name="Close").click(timeout=2_000)
        page.wait_for_timeout(500)
    except Exception:
        logger.info("No privacy banner to dismiss.")


def send_telegram_message(text: str) -> None:
    """Send a plain text message to the configured Telegram chat."""
    data = {"chat_id": settings.TELEGRAM_CHAT_ID, "text": text}
    try:
        requests.post(_telegram_url("sendMessage"), data=data, timeout=TELEGRAM_TIMEOUT)
    except requests.RequestException:
        logger.exception("❌ Telegram message failed:")


def send_telegram_photo(photo_path: Path, caption: str = "") -> None:
    """Send a photo to the configured Telegram chat."""
    data = {"chat_id": settings.TELEGRAM_CHAT_ID, "caption": caption}
    try:
        with photo_path.open("rb") as fh:
            requests.post(
                _telegram_url("sendPhoto"),
                data=data,
                files={"photo": fh},
                timeout=TELEGRAM_TIMEOUT,
            )
    except requests.RequestException:
        logger.exception("❌ Telegram photo failed:")


def send_gas_weather_report() -> None:
    """Scheduled job: send the weather link and a gas price snapshot to Telegram."""
    if not settings.TELEGRAM_BOT or not settings.TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured; skipping gas/weather report.")
        return

    send_telegram_message(prepare_weather_message())

    try:
        snapshot = take_gas_snapshot()
    except Exception:
        logger.exception("Gas snapshot failed:")
        send_telegram_message("gas price not available")
        return

    send_telegram_photo(snapshot, caption=f"Gas prices {_today()} — {GAS_URL}")
