"""Extensions initialization for the SafeFamily application."""

import json
import logging
from zoneinfo import ZoneInfo

import psycopg2
from flask_jwt_extended import JWTManager
from flask_mail import Mail
from flask_sqlalchemy import SQLAlchemy

from config.settings import settings
from src.safe_family.utils.constants import TIMEZONE

logger = logging.getLogger(__name__)
db = SQLAlchemy()
jwt = JWTManager()
mail = Mail()
# zoneinfo reads the OS tz database (kept current by the base image) rather than
# pytz's bundled snapshot, which lags real-world rule changes.
local_tz = ZoneInfo(TIMEZONE)


def get_db_connection():
    """Establish a new database connection using psycopg2."""
    config_dict = json.loads(settings.DB_PARAMS)
    return psycopg2.connect(**config_dict)
