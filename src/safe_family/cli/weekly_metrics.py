# CLI wrapper with __main__
# python3 -m safe_family.cli.weekly_metrics --week 2026-W01 --username Rice_Tangle --output-dir metrics
"""Weekly metrics extraction for todo_list (LLM-ready data file)."""

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src.safe_family.core.extensions import get_db_connection

logger = logging.getLogger(__name__)


STATUS_WEIGHTS = {
    "skipped": 0.0,
    "partially done": 0.25,
    "half done": 0.5,
    "mostly done": 0.75,
    "done": 1.0,
}


@dataclass(frozen=True)
class WeekMetrics:
    completion_rate: float | None
    avg_tasks_per_day: float | None
    avg_planned_minutes: float | None
    by_category: dict[str, float]
    by_category_minutes: dict[str, dict[str, float]]


def _parse_iso_week(week_str: str) -> tuple[date, date]:
    """Return start/end dates (Mon-Sun) for an ISO week like 2025-W10."""
    match = re.fullmatch(r"(\d{4})-W(\d{2})", week_str.strip())
    if not match:
        raise ValueError("week must be in YYYY-Www format (e.g., 2025-W10)")
    year, week = int(match.group(1)), int(match.group(2))
    start = date.fromisocalendar(year, week, 1)
    end = date.fromisocalendar(year, week, 7)
    logger.debug(f"Parsed week {week_str} as {start} to {end}")
    return start, end


def _parse_time_slot_minutes(time_slot: str | None) -> float | None:
    if not time_slot:
        return None
    match = re.search(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})", time_slot)
    if not match:
        return None
    sh, sm, eh, em = (int(match.group(i)) for i in range(1, 5))
    start_minutes = sh * 60 + sm
    end_minutes = eh * 60 + em
    if end_minutes < start_minutes:
        end_minutes += 24 * 60
    return float(end_minutes - start_minutes)


def _status_weight(series: pd.Series) -> pd.Series:
    if series is None:
        return pd.Series(0.0, index=pd.RangeIndex(0))
    s = series.fillna("").astype(str).str.strip().str.lower()
    return s.map(STATUS_WEIGHTS).fillna(0.0)


def _compute_metrics(df: pd.DataFrame, start: date, end: date) -> WeekMetrics:
    days = (end - start).days + 1
    if df.empty:
        return WeekMetrics(None, None, None, {}, {})

    df = df.copy()
    df["slot_minutes"] = df["time_slot"].apply(_parse_time_slot_minutes)
    df["slot_weight"] = _status_weight(df.get("completion_status"))
    df["effective_minutes"] = df["slot_minutes"] * df["slot_weight"]

    total_minutes = float(df["slot_minutes"].sum(skipna=True))
    effective_minutes = float(df["effective_minutes"].sum(skipna=True))
    completion_rate = None
    if total_minutes > 0:
        completion_rate = effective_minutes / total_minutes
    avg_tasks_per_day = float(len(df) / days) if days > 0 else None
    planned_minutes = df["slot_minutes"]
    avg_planned = (
        float(np.nanmean(planned_minutes)) if planned_minutes.notna().any() else None
    )

    tags = df.get("tags", pd.Series("", index=df.index)).fillna("")
    tags = tags.astype(str).str.strip().str.lower()
    df["tags_norm"] = tags
    by_category = {}
    by_category_minutes = {}
    for tag, group in df.groupby("tags_norm"):
        if not tag or tag == "unknown":
            continue
        total = float(group["slot_minutes"].sum(skipna=True))
        effective = float(group["effective_minutes"].sum(skipna=True))
        if total > 0:
            by_category[tag] = effective / total
        by_category_minutes[tag] = {
            "planned_minutes": total,
            "effective_minutes": effective,
        }
    return WeekMetrics(
        completion_rate,
        avg_tasks_per_day,
        avg_planned,
        by_category,
        by_category_minutes,
    )


def _fetch_week_df(start: date, end: date, username: str) -> pd.DataFrame:
    conn = get_db_connection()
    cur = conn.cursor()
    query = """
        SELECT date, time_slot, completion_status, tags, username
        FROM todo_list
        WHERE date BETWEEN %s AND %s
          AND username = %s
    """
    cur.execute(query, (start, end, username))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    if not rows:
        return pd.DataFrame(
            columns=["date", "time_slot", "completion_status", "tags", "username"],
        )
    return pd.DataFrame(
        rows,
        columns=["date", "time_slot", "completion_status", "tags", "username"],
    )


def main(args: list[str] | None = None) -> int:
    """Extract weekly metrics and render LLM-ready summary."""
    parser = argparse.ArgumentParser(
        description="Generate weekly todo_list metrics",
    )
    parser.add_argument(
        "--week",
        help="ISO week in format YYYY-Www (e.g., 2025-W10)",
    )
    parser.add_argument(
        "--username",
        required=True,
        help="Username filter (required)",
    )
    parser.add_argument(
        "--output-dir",
        help="Write weekly summary to a file under this directory",
    )
    parser.add_argument(
        "--output-file",
        help="Write weekly summary to this file path",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parsed_args = parser.parse_args(args)

    if parsed_args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if parsed_args.week:
        start, end = _parse_iso_week(parsed_args.week)
        week_label = parsed_args.week
    else:
        today = datetime.now().date()
        iso = today.isocalendar()
        week_label = f"{iso.year}-W{iso.week:02d}"
        start, end = _parse_iso_week(week_label)

    current_df = _fetch_week_df(start, end, parsed_args.username)
    current_metrics = _compute_metrics(current_df, start, end)
    output = json.dumps(
        {
            "week": week_label,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "completion_rate": current_metrics.completion_rate,
            "avg_tasks_per_day": current_metrics.avg_tasks_per_day,
            "avg_planned_minutes": current_metrics.avg_planned_minutes,
            "by_category": current_metrics.by_category,
            "by_category_minutes": current_metrics.by_category_minutes,
        },
        indent=2,
        sort_keys=True,
    )

    if parsed_args.output_dir and parsed_args.output_file:
        raise ValueError("Use only one of --output-dir or --output-file")

    if parsed_args.output_file:
        output_path = Path(parsed_args.output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
        print(str(output_path))
        return 0

    if parsed_args.output_dir:
        out_dir = Path(parsed_args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"{week_label}.txt"
        output_path.write_text(output, encoding="utf-8")
        print(str(output_path))
        return 0

    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
