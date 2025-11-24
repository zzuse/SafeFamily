"""Notification utilities for sending updates via email and Discord."""

import ast
import logging

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
        content += f"- {t['time_slot']}: {t['task']}\n"

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
