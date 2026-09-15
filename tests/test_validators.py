"""Tests for rule input validators."""

import pytest

from src.safe_family.utils import validators


@pytest.mark.parametrize("value", ["*.apple.com", "%embedly.com", "www.officeholidays.com", "time?.example"])
def test_valid_filter_rules(value):
    assert validators.is_valid_filter_rule(value)


@pytest.mark.parametrize(
    "value",
    [None, "", "; id ;", "`id`", "$(id)", "|id", "||san666.com^", "a\nb", "a.com\n", "x" * 254],
)
def test_invalid_filter_rules(value):
    assert not validators.is_valid_filter_rule(value)


@pytest.mark.parametrize("value", ["%grok.com", "%x.com/i/grok", "example.com", "a_b-c.io"])
def test_valid_block_qh(value):
    assert validators.is_valid_block_qh(value)


@pytest.mark.parametrize("value", [None, "", "%medal.tv;id", "a b.com", "x`id`.png", "a.com\n"])
def test_invalid_block_qh(value):
    assert not validators.is_valid_block_qh(value)


@pytest.mark.parametrize("value", ["game", "ai", "block_2"])
def test_valid_block_type(value):
    assert validators.is_valid_block_type(value)


@pytest.mark.parametrize("value", [None, "", " video", "../tmp/x", "..\u2215tmp\u2215x", "Game", "a.b", "x" * 33])
def test_invalid_block_type(value):
    assert not validators.is_valid_block_type(value)


def test_split_lines():
    assert validators.split_lines(["a\r\n\n b ", "", "c"]) == ["a", "b", "c"]


def test_safe_date():
    assert validators.safe_date("2025-01-02", "d") == "2025-01-02"
    assert validators.safe_date("2025-01-02&error=x", "d") == "d"
    assert validators.safe_date(None, "d") == "d"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("3", 3), (None, 1), ("abc", 1), ("0", 1), ("-2", 1), ("9" * 5000, 1)],
)
def test_positive_int(value, expected):
    assert validators.positive_int(value) == expected
