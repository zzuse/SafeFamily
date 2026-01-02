# config/settings.py
"""Application settings module."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    """Application settings loaded from environment variables."""

    # Admin settings
    ADMIN_IDENTITY = os.environ.get("ADMIN_IDENTITY")

    # FLASK settings
    FLASK_DEBUG = os.getenv("FLASK_DEBUG", "False") == "True"
    SQLALCHEMY_DATABASE_URI = os.environ.get("FLASK_SQLALCHEMY_DATABASE_URI")
    DB_PARAMS = os.environ.get("DB_PARAMS", None)
    SQLALCHEMY_ECHO = os.environ.get("FLASK_SQLALCHEMY_ECHO") == "True"
    APP_SECRET_KEY = os.environ.get("FLASK_APP_SECRET_KEY")
    JWT_SECRET_KEY = os.environ.get("FLASK_JWT_SECRET_KEY")
    JWT_ACCESS_TOKEN_EXPIRES = 3

    # Mail settings
    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_ACCOUNT = os.environ.get("MAIL_ACCOUNT")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_PERSON_LIST = os.environ.get("MAIL_PERSON_LIST", "")

    # AdGuard settings
    ADGUARD_HOSTPORT = os.environ.get("ADGUARD_HOSTPORT", "")
    ADGUARD_USERNAME = os.environ.get("ADGUARD_USERNAME", "")
    ADGUARD_PASSWORD = os.environ.get("ADGUARD_PASSWORD", "")
    ADGUARD_RULE_PATH = os.environ.get("ADGUARD_RULE_PATH", "")
    ROUTER_IP = os.environ.get("ROUTER_IP", "")

    # Other settings can be added here as needed
    DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
    HAMMERSPOON_ALERT_URL = os.environ.get(
        "HAMMERSPOON_ALERT_URL",
        "http://localhost:9181/alert",
    )

    # OAuth settings
    GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID")
    GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET")
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
    GOOGLE_CLIENT_PROJECT_ID = os.environ.get("GOOGLE_CLIENT_PROJECT_ID")
    GOOGLE_CALLBACK_ROUTE = os.environ.get("GOOGLE_CALLBACK_ROUTE")
    OAUTHLIB_INSECURE_TRANSPORT = os.environ.get("OAUTHLIB_INSECURE_TRANSPORT")


settings = Settings()
