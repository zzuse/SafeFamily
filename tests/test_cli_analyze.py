"""Tests for CLI analyze entrypoint."""

from src.safe_family.cli import analyze


def test_cli_analyze_calls_log_analysis(monkeypatch):
    called = {}

    def fake_get_time_range(**kwargs):
        called["range"] = kwargs.get("range")
        return ("start", "end")

    def fake_log_analysis(start, end):
        called["log_analysis"] = (start, end)

    monkeypatch.setattr(analyze, "get_time_range", fake_get_time_range)
    monkeypatch.setattr(analyze, "log_analysis", fake_log_analysis)

    analyze.main(["--range", "last_5min"])

    assert called["range"] == "last_5min"
    assert called["log_analysis"] == ("start", "end")
