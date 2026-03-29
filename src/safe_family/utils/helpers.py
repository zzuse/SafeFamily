"""Utility helper functions."""

import logging
from src.safe_family.core.extensions import get_db_connection

logger = logging.getLogger(__name__)

def get_agile_config(config_key: str, default_value: str = "") -> str:
    """Retrieve an agile configuration value by key."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT config_value FROM agile_config WHERE config_key = %s",
            (config_key,),
        )
        row = cur.fetchone()
        if row:
            return row[0]
        return default_value
    except Exception as e:
        logger.error("Error fetching agile config %s: %s", config_key, e)
        return default_value
    finally:
        cur.close()
        conn.close()

def set_agile_config(config_key: str, config_value: str):
    """Update or insert an agile configuration value."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO agile_config (config_key, config_value)
            VALUES (%s, %s)
            ON CONFLICT (config_key)
            DO UPDATE SET config_value = EXCLUDED.config_value, updated_at = CURRENT_TIMESTAMP
            """,
            (config_key, config_value),
        )
        conn.commit()
    except Exception as e:
        logger.error("Error setting agile config %s: %s", config_key, e)
        conn.rollback()
    finally:
        cur.close()
        conn.close()
