"""Utility helper functions."""

import logging

from src.safe_family.core.extensions import get_db_connection

logger = logging.getLogger(__name__)


def get_agile_config(config_key: str, default_value: str = "") -> str:
    """Retrieve an agile configuration value by key."""
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
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
        if cur:
            cur.close()
        if conn:
            conn.close()


def set_agile_config(config_key: str, config_value: str):
    """Update or insert an agile configuration value."""
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
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
        if conn:
            conn.rollback()
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def update_agile_config_by_timestamp(time_str: str):
    """Update agile_config show_disable_button_start and end based on a formula.
    Accepts time_str in "HH:MM" format, converts to float hours, then:
    show_disable_button_start = ((-3) * input + 46) / 4 + 12
    show_disable_button_end = show_disable_button_start + 0.5 hours
    """
    try:
        # Convert "HH:MM" to decimal hours (e.g. "10:30" -> 10.5)
        parts = time_str.split(":")
        if len(parts) != 2:
            raise ValueError("Invalid time format. Use HH:MM")

        hours = int(parts[0])
        minutes = int(parts[1])
        input_val = hours + (minutes / 60.0)

        start_hours = ((-3.0) * input_val + 46.0) / 4.0 + 12.0
        end_hours = start_hours + 0.5

        def format_hours(h):
            # Use modulo 24 to keep it within a day
            total_minutes = int(round(h * 60))
            hh = (total_minutes // 60) % 24
            mm = total_minutes % 60
            return f"{hh:02d}:{mm:02d}"

        set_agile_config("show_disable_button_start", format_hours(start_hours))
        set_agile_config("show_disable_button_end", format_hours(end_hours))
        return True
    except Exception as e:
        logger.error("Error updating agile config by timestamp (%s): %s", time_str, e)
        return False
