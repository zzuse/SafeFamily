"""Analyzer URL routes for Safe Family application."""

import fnmatch
from datetime import datetime, timedelta

import pandas as pd
from flask import Blueprint, jsonify, render_template, request

from src.safe_family.core.auth import admin_required
from src.safe_family.core.extensions import get_db_connection, local_tz

VALID_TIME_RANGES = ["yesterday", "last_hour", "last_5min", "custom"]
analyze_bp = Blueprint("analyze", __name__)


@analyze_bp.route("/analyze_route", methods=["GET", "POST"])
def analyze_routes():
    """Render the analyze routes page."""
    return render_template("rules/analyze_route.html")


@analyze_bp.route("/analyze", methods=["POST"])
@admin_required
def analyze_logs():
    """Analyze logs and return the results."""
    data = request.json
    time_range = data.get("time_range")
    custom_start = data.get("custom_start")
    custom_end = data.get("custom_end")

    print(data)

    # Validate time range
    if time_range not in VALID_TIME_RANGES:
        return jsonify({"error": "Invalid time range"}), 400

    if time_range == "custom":
        print(custom_start, custom_end)
        start, end = get_time_range(custom=(custom_start, custom_end))
    else:
        start, end = get_time_range(range=time_range)

    log_analysis(start, end)

    """Deprecated logic using subprocess
        command = ["python3", "log_analysis.py", "--custom", str(start_time), str(end_time)]
        subprocess.run(command, capture_output=True, text=True, check=True)
    """

    return jsonify({"message": "Analysis finished"})


def get_time_range(
    range: str | None = None,
    custom: tuple[str, str] | None = None,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Return (start_time, end_time) based on predefined ranges or custom input.

    Args:
        range: One of "yesterday", "last_hour", "last_5min"
        custom: Tuple of two strings (start_str, end_str) in format "%Y-%m-%d %H:%M:%S"
        now: Override current time (useful for testing). Defaults to datetime.now()

    Returns:
        Tuple[start_time, end_time] as datetime objects

    Raises:
        ValueError: If invalid combination or malformed custom times

    """
    if now is None:
        now = datetime.now(local_tz)

    if range and custom:
        raise ValueError("Cannot specify both --range and --custom")

    if range == "yesterday":
        start_time = (now - timedelta(days=1)).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        end_time = start_time + timedelta(days=1)

    elif range == "last_hour":
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = now - timedelta(hours=1)

    elif range == "last_5min":
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = now - timedelta(minutes=5)

    elif custom:
        if len(custom) != 2:
            raise ValueError("Custom range must provide exactly two timestamps")
        try:
            start_time = datetime.strptime(custom[0], "%Y-%m-%dT%H:%M:%S")
            end_time = datetime.strptime(custom[1], "%Y-%m-%dT%H:%M:%S")
        except ValueError as e:
            raise ValueError(f"Invalid datetime format. Use 'YYYY-MM-DDTHH:MM:SS': {e}")

    else:
        raise ValueError("Must specify either --range or --custom")

    if start_time >= end_time:
        raise ValueError("start_time must be earlier than end_time")

    return start_time, end_time


def log_analysis(start_time: datetime, end_time: datetime):
    """Analyze logs between start_time and end_time."""
    print(f"Processing logs from {start_time} to {end_time}")
    # Connect to database
    conn = get_db_connection()
    cur = conn.cursor()

    # Step 0: Clean Up first
    cur.execute("delete from logs_daily where date::DATE = %s", (start_time.date(),))
    conn.commit()
    print(f"Deleting rows for date: {start_time.date()}")

    cur.execute("delete from suspicious where date::DATE = %s", (start_time.date(),))
    conn.commit()
    print(f"Deleting rows for date: {start_time.date()}")

    print(
        f"Fetching rows for datetime: {start_time.date()} {start_time.time()} - {end_time.date()} {end_time.time()}",
    )

    # Step 1: Fetch yesterday's logs
    query = "SELECT qh FROM logs WHERE timestamp >= %s AND timestamp < %s "
    df = pd.read_sql(query, conn, params=(start_time, end_time))

    # Step 2: Count occurrences of each qh
    qh_counts = df["qh"].value_counts().reset_index()
    qh_counts.columns = ["qh", "count"]

    # Step 3: Insert aggregated data into logs_daily
    for _, row in qh_counts.iterrows():
        cur.execute(
            "INSERT INTO logs_daily (date, qh, count) VALUES (%s, %s, %s) ON CONFLICT (date, qh) DO UPDATE SET count = logs_daily.count + EXCLUDED.count",
            (start_time.date(), row["qh"], row["count"]),
        )

    # Step 4: Fetch all filter rules from the database
    cur.execute("SELECT qh FROM filter_rule")
    filter_patterns = [row[0] for row in cur.fetchall()]

    # Function to check if a qh matches any pattern in filter_rule
    def is_matched(qh_value) -> bool:
        return any(fnmatch.fnmatch(qh_value, pattern) for pattern in filter_patterns)

    # Step 5: After filter, identify suspicious entries
    suspicious_qh = qh_counts[~qh_counts["qh"].apply(is_matched)]

    # Step 6: Insert suspicious entries into suspicious table
    for _, row in suspicious_qh.iterrows():
        cur.execute(
            "INSERT INTO suspicious (date, qh, count) VALUES (%s, %s, %s) ON CONFLICT (date, qh) DO NOTHING",
            (start_time.date(), row["qh"], row["count"]),
        )

    conn.commit()
    cur.close()
    conn.close()
    print("Log analysis completed.")
