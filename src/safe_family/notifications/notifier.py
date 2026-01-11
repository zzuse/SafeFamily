"""Notification utilities for sending updates via email and Discord."""

import ast
import logging
import socket
from urllib.parse import urlparse

import requests
from flask_mail import Message

from config.settings import settings
from src.safe_family.core.extensions import mail
from src.safe_family.utils.exceptions import NotificationError

logger = logging.getLogger(__name__)


def send_email_notification(username, tasks):
    """Send an email notification to admins about todo list updates."""
    list_literal_string = settings.MAIL_PERSON_LIST
    admin_email_list = ast.literal_eval(list_literal_string)
    subject = f"New Todo Update from {username}"
    body = f"{username} just updated their tasks:\n\n"

    for t in tasks:
        body += f"- {t['time_slot']}: {t['task']}\n"

    msg = Message(subject=subject, recipients=admin_email_list, body=body)
    mail.send(msg)


def send_discord_notification(username, tasks):
    """Send a Discord notification about todo list updates."""
    if not settings.DISCORD_WEBHOOK_URL:
        print("⚠️ Discord webhook URL not configured.")
        return

    title = f"📝 **{username}** just updated their Todo List:\n"
    content = ""
    for t in tasks:
        status = (t.get("completion_status") or "").strip()
        status_label = status.title() if status else "Pending"
        content += f"- {t['time_slot']}: {t['task']} ({status_label})\n"

    data = {
        "embeds": [
            {
                "title": f"{title}",
                "description": f"{content}",
                "color": 5814783,
            },
        ],
    }

    try:
        requests.post(settings.DISCORD_WEBHOOK_URL, json=data, timeout=5)
        logger.info(data)
    except NotificationError:
        logger.exception("❌ Discord message failed:")


def send_discord_summary(username: str, summary: str, week: str, previous_week: str):
    """Send a Discord notification for weekly summary."""
    if not settings.DISCORD_WEBHOOK_URL:
        print("⚠️ Discord webhook URL not configured.")
        return

    title = f"📊 Weekly Summary for {username}"
    content = summary or "No summary data available."
    footer_text = f"{previous_week} → {week}" if previous_week and week else None
    embed = {
        "title": title,
        "description": content,
        "color": 3447003,
    }
    if footer_text:
        embed["footer"] = {"text": footer_text}

    data = {"embeds": [embed]}

    try:
        requests.post(settings.DISCORD_WEBHOOK_URL, json=data, timeout=5)
        logger.info(data)
    except NotificationError:
        logger.exception("❌ Discord summary failed:")


def send_hammerspoon_alert(message: str):
    """Send a local desktop alert via Hammerspoon HTTP server."""
    alert_url = settings.HAMMERSPOON_ALERT_URL
    if not alert_url:
        return
    if not _is_hammerspoon_available(alert_url):
        return

    payload = {"message": message}
    try:
        requests.post(alert_url, json=payload, timeout=2)
    except requests.RequestException:
        logger.exception("❌ Hammerspoon alert failed:")


def _is_hammerspoon_available(alert_url: str) -> bool:
    parsed = urlparse(alert_url)
    host = parsed.hostname
    if not host:
        logger.warning("Hammerspoon alert URL missing host.")
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=1):
            pass
    except OSError as exc:
        logger.info("Hammerspoon host unavailable: %s", exc)
        return False

    try:
        requests.options(alert_url, timeout=1)
    except requests.RequestException as exc:
        logger.info("Hammerspoon server unavailable: %s", exc)
        return False

    return True
