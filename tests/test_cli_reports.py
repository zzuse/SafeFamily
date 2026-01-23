"""Tests for weekly metrics and diff CLIs."""

import json
from pathlib import Path

import pandas as pd
import pytest

from src.safe_family.cli import weekly_diff, weekly_metrics


def test_parse_iso_week_invalid():
    with pytest.raises(ValueError):
        weekly_metrics._parse_iso_week("2025-13")


def test_parse_time_slot_minutes_cross_midnight():
    minutes = weekly_metrics._parse_time_slot_minutes("23:00 - 01:00")
    assert minutes == 120.0


def test_status_weight_maps_values():
    series = pd.Series(["done", "half done", "skipped", None])
    weights = weekly_metrics._status_weight(series)
    assert weights.tolist() == [1.0, 0.5, 0.0, 0.0]


def test_compute_metrics_returns_summary():
    df = pd.DataFrame(
        [
            {
                "time_slot": "09:00 - 10:00",
                "completion_status": "done",
                "tags": "math",
            },
            {
                "time_slot": "10:00 - 10:30",
                "completion_status": "half done",
                "tags": "science",
            },
        ],
    )
    start = pd.Timestamp("2025-01-01").date()
    end = pd.Timestamp("2025-01-07").date()
    metrics = weekly_metrics._compute_metrics(df, start, end)

    assert metrics.completion_rate is not None
    assert "math" in metrics.by_category


def test_fetch_week_df_returns_dataframe(monkeypatch):
    class FakeCursor:
        def __init__(self):
            self.queries = []

        def execute(self, sql, params=None):
            self.queries.append((sql, params))

        def fetchall(self):
            return [
                ("2025-01-01", "09:00 - 10:00", "done", "math", "alice"),
            ]

        def close(self):
            return None

    class FakeConn:
        def __init__(self):
            self.cursor_obj = FakeCursor()

        def cursor(self):
            return self.cursor_obj

        def close(self):
            return None

    monkeypatch.setattr(weekly_metrics, "get_db_connection", lambda: FakeConn())
    df = weekly_metrics._fetch_week_df(
        pd.Timestamp("2025-01-01").date(),
        pd.Timestamp("2025-01-07").date(),
        "alice",
    )
    assert not df.empty


def test_weekly_metrics_main_rejects_conflicting_outputs(monkeypatch):
    monkeypatch.setattr(weekly_metrics, "_fetch_week_df", lambda *a, **k: pd.DataFrame())
    with pytest.raises(ValueError):
        weekly_metrics.main(
            [
                "--username",
                "alice",
                "--output-dir",
                "out",
                "--output-file",
                "out/file.json",
            ],
        )


def test_weekly_metrics_main_writes_output_dir(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(weekly_metrics, "_fetch_week_df", lambda *a, **k: pd.DataFrame())

    code = weekly_metrics.main(
        [
            "--username",
            "alice",
            "--output-dir",
            str(tmp_path),
        ],
    )
    captured = capsys.readouterr()

    assert code == 0
    output_path = Path(captured.out.strip())
    assert output_path.exists()


def test_weekly_metrics_main_writes_output_file(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(weekly_metrics, "_fetch_week_df", lambda *a, **k: pd.DataFrame())
    output_file = tmp_path / "week.json"

    code = weekly_metrics.main(
        [
            "--username",
            "alice",
            "--output-file",
            str(output_file),
        ],
    )
    captured = capsys.readouterr()

    assert code == 0
    assert Path(captured.out.strip()).exists()

def test_weekly_diff_main_missing_files(tmp_path, capsys):
    missing_a = tmp_path / "missing-a.json"
    missing_b = tmp_path / "missing-b.json"
    code = weekly_diff.main(["--files", str(missing_a), str(missing_b)])
    captured = capsys.readouterr()
    assert code == 1
    assert "Missing file" in captured.err


def test_weekly_diff_formats_output():
    current = weekly_diff.WeekMetrics(
        week="2025-W01",
        completion_rate=0.5,
        avg_tasks_per_day=2.0,
        avg_planned_minutes=30.0,
        by_category={"math": 0.5},
        by_category_minutes={"math": {"planned_minutes": 60.0, "effective_minutes": 30.0}},
    )
    previous = weekly_diff.WeekMetrics(
        week="2024-W52",
        completion_rate=0.4,
        avg_tasks_per_day=1.0,
        avg_planned_minutes=20.0,
        by_category={},
        by_category_minutes={},
    )
    output = weekly_diff._format_output(current, previous)
    assert "Completion rate" in output
    assert "math" in output


def test_weekly_diff_main_success(tmp_path, capsys):
    file_a = tmp_path / "a.json"
    file_b = tmp_path / "b.json"
    file_a.write_text(json.dumps({"week": "2024-W52"}), encoding="utf-8")
    file_b.write_text(json.dumps({"week": "2025-W01"}), encoding="utf-8")

    code = weekly_diff.main(["--files", str(file_a), str(file_b)])
    captured = capsys.readouterr()

    assert code == 0
    assert "WEEK:" in captured.out
