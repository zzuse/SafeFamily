"""Unit tests for SafeFamily utility functions."""

from datetime import datetime

import pytest

from src.safe_family.cli.gentags import infer_tag
from src.safe_family.todo.todo import generate_time_slots
from src.safe_family.urls.analyzer import get_time_range


def test_generate_time_slots_weekday_half_hour():
    weekday = datetime(2025, 1, 6, 12, 0)  # Monday
    slots = generate_time_slots(
        slot_type="30",
        schedule_mode="weekday",
        custom_start="",
        custom_end="",
        today=weekday,
    )
    assert slots[0] == "18:30 - 19:00"
    assert slots[-1] == "21:00 - 21:30"
    assert len(slots) == 6


def test_generate_time_slots_weekend_hour():
    weekend = datetime(2025, 1, 4, 12, 0)  # Saturday
    slots = generate_time_slots(
        slot_type="60",
        schedule_mode="weekday",
        custom_start="",
        custom_end="",
        today=weekend,
    )
    assert slots[0] == "09:00 - 10:00"
    assert slots[-1] == "15:00 - 16:00"
    assert len(slots) == 7


def test_get_time_range_last_hour_uses_midnight_start():
    now = datetime(2025, 1, 2, 15, 30)
    start_time, end_time = get_time_range(range="last_hour", now=now)
    assert start_time.strftime("%Y-%m-%d %H:%M:%S") == "2025-01-02 00:00:00"
    assert end_time.strftime("%Y-%m-%d %H:%M:%S") == "2025-01-02 14:30:00"


def test_get_time_range_invalid_raises():
    with pytest.raises(ValueError):
        get_time_range(custom=("2025-01-02T10:00:00", "2025-01-01T09:00:00"))


def test_infer_tag_matches_keywords_and_unknown():
    assert infer_tag("Finish calculus problems") == "math"
    assert infer_tag("Unrelated task name") == "unknown"
