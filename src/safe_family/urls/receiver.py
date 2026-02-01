"""Receiver URL routes for log server."""

import hashlib
import logging
import re
from datetime import UTC, datetime, timedelta

import requests
from flask import Blueprint, jsonify

from config.settings import settings
from src.safe_family.core.extensions import get_db_connection

ADGUARD_QUERY_API = f"http://{settings.ADGUARD_HOSTPORT}/control/querylog"
ADGUARD_AUTH = (f"{settings.ADGUARD_USERNAME}", f"{settings.ADGUARD_PASSWORD}")
PULL_LIMIT = 100
OVERLAP_SECONDS = 2
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

    Pull logs from AdGuard and store new entries in the database.

    """
    try:
        inserted = run_adguard_pull()
        return jsonify({"inserted": inserted}), 200

    except Exception as e:
        logger.exception("AdGuard pull failed")
        return jsonify({"error": str(e)}), 500


def make_dedupe_hash(row: dict) -> str:
    """Generate a stable deduplication hash.

    Stored in `ip` column (semantic repurpose).
    """
    raw = f"{row.get('time')}|{row.get('name')}"
    return hashlib.sha1(raw.encode()).hexdigest()


def parse_ts(ts: str) -> datetime:
    """Timestamp parser from AdGuard format to datetime."""
    # 1. Handle "Z" for older Python
    ts = ts.replace("Z", "+00:00")
    # 2. Truncate nanoseconds to microseconds if necessary
    # (Find the dot and the +/- offset, keep only 2 digits after dot)
    if "." in ts:
        prefix, remainder = ts.split(".", 1)
        # Find where the timezone starts (+ or -)

        tz_match = re.search(r"[+-]", remainder)
        if tz_match:
            tz_start = tz_match.start()
            # Keep only 2 digits of fractional seconds
            ts = f"{prefix}.{remainder[:2]}{remainder[tz_start:]}"

    return datetime.fromisoformat(ts)


def run_adguard_pull() -> int:
    """Core logic to pull logs from AdGuard and store them."""
    conn = get_db_connection()
    cur = conn.cursor()

    # 1. 找最后一条时间
    cur.execute("SELECT MAX(timestamp) FROM logs")
    # Use 1970-01-01 as a safe default instead of datetime.min to avoid OverflowError on subtraction
    safe_default = datetime(1970, 1, 1, tzinfo=UTC)
    last_ts = cur.fetchone()[0] or safe_default
    since = last_ts - timedelta(seconds=OVERLAP_SECONDS)

    # 2. 拉 AdGuard
    resp = requests.get(
        ADGUARD_QUERY_API,
        params={"limit": PULL_LIMIT},
        auth=ADGUARD_AUTH,
        timeout=5,
    )
    resp.raise_for_status()

    # ───────────────────────────────────────────────
    # Extract the fields you want
    # ───────────────────────────────────────────────

    rows = []

    for entry in resp.json().get("data", []):
        question = entry.get("question", {})
        row = {
            "name": question.get("name"),
            "time": entry.get("time"),
            "client": entry.get("client"),
            "reason": entry.get("reason"),
        }
        rows.append(row)

    inserted = 0

    # API returns reversed
    for row in reversed(rows):
        ts = parse_ts(row["time"])
        if ts < since:
            continue

        qh = row.get("name")
        dedupe_hash = make_dedupe_hash(row)

        is_filtered = row.get("reason") == "FilteredBlackList"

        cur.execute(
            """
            INSERT INTO logs (timestamp, ip, qh, is_filtered)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (ip) DO NOTHING
            """,
            (ts, dedupe_hash, qh, is_filtered),
        )

        if cur.rowcount:
            inserted += 1

    conn.commit()
    cur.close()
    conn.close()

    logger.info("AdGuard pull finished, inserted=%d", inserted)
    return inserted
