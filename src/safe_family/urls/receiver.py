"""Receiver URL routes for log server."""

import logging

from flask import Blueprint, jsonify, request

from src.safe_family.core.extensions import get_db_connection
from src.safe_family.utils.exceptions import DatabaseConnectionError

logger = logging.getLogger(__name__)
receiver_bp = Blueprint("receiver", __name__)


@receiver_bp.route("/logs", methods=["POST"])
def receive_log():
    """Receive a log entry and store it in the database.

    This endpoint expects a JSON payload with the following structure:
    {
        "T": "timestamp",
        "IP": "IP address",
        "QH": "query hash",
        "Result": {
            "IsFiltered": true/false
        }
    }
    It stores the log entry in the 'logs' table of the database.
    The 'timestamp' is expected to be in a format compatible with PostgreSQL.
    The 'IP' is the IP address of the client, and 'QH' is the query hash.
    The 'Result' field contains a dictionary with an 'IsFiltered' boolean value.

    Args:
        request: The Flask request object containing the JSON payload with log data.

    Returns:
        A JSON response indicating success or failure of the log storage operation.

    Raises:
        ValueError: If the log data is not in the expected format or is missing required fields.
        psycopg2.Error: If there is an error while interacting with the database.

    """
    log_data = request.get_json()
    if not log_data:
        return jsonify({"error": "Invalid JSON"}), 400

    ip = log_data.get("IP")
    qh = log_data.get("QH")
    is_filtered = (
        log_data.get("Result", {}).get("IsFiltered") if log_data.get("Result") else None
    )
    logger.debug("Received log: %s", {qh})

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO logs (timestamp, ip, qh, is_filtered)
            VALUES (%s, %s, %s, %s)
            """,
            (log_data.get("T"), ip, qh, is_filtered),
        )
        conn.commit()
        cur.close()
        conn.close()
        logger.info("Log stored: %s", {qh})
        return jsonify({"message": "Log received"}), 200
    except DatabaseConnectionError as e:
        logger.exception("Database error")
        return jsonify({"error": str(e)}), 500
