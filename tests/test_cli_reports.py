"""Tests for weekly metrics CLI."""

from pathlib import Path

import pandas as pd
import pytest

from src.safe_family.cli import weekly_metrics


def test_parse_iso_week_invalid():
    with pytest.raises(ValueError, match="YYYY-Www format"):
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

    monkeypatch.setattr(weekly_metrics, "get_db_connection", FakeConn)
    df = weekly_metrics._fetch_week_df(
        pd.Timestamp("2025-01-01").date(),
        pd.Timestamp("2025-01-07").date(),
        "alice",
    )
    assert not df.empty


def test_weekly_metrics_main_rejects_conflicting_outputs(monkeypatch):
    monkeypatch.setattr(weekly_metrics, "_fetch_week_df", lambda *a, **k: pd.DataFrame())
    with pytest.raises(ValueError, match="only one of"):
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
