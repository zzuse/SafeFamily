"""Input validation for admin-managed block list and filter rules.

These values end up in SQL LIKE / fnmatch patterns, in AdGuard rule files and,
for block types, in file names (block_<type>.txt), so only a conservative
character set is accepted.
"""

import re
from datetime import date

MAX_PATTERN_LENGTH = 253  # longest valid DNS name
MAX_LINES_PER_REQUEST = 100

# fnmatch patterns over domains, e.g. "*.apple.com", "%embedly.com"
_FILTER_RULE_RE = re.compile(rf"[A-Za-z0-9.*?%_-]{{1,{MAX_PATTERN_LENGTH}}}")
# SQL LIKE patterns over domains, optionally with a path, e.g. "%x.com/i/grok"
_BLOCK_QH_RE = re.compile(rf"[A-Za-z0-9.%_/-]{{1,{MAX_PATTERN_LENGTH}}}")
# Part of a file name, so no dots, slashes or whitespace
_BLOCK_TYPE_RE = re.compile(r"[a-z0-9_]{1,32}")


def is_valid_filter_rule(value: str | None) -> bool:
    """Return True if value is a safe filter_rule pattern."""
    return bool(value) and _FILTER_RULE_RE.fullmatch(value) is not None


def is_valid_block_qh(value: str | None) -> bool:
    """Return True if value is a safe block_list pattern."""
    return bool(value) and _BLOCK_QH_RE.fullmatch(value) is not None


def is_valid_block_type(value: str | None) -> bool:
    """Return True if value is a safe block type name."""
    return bool(value) and _BLOCK_TYPE_RE.fullmatch(value) is not None


def split_lines(values: list[str]) -> list[str]:
    """Split textarea submissions into stripped, non-empty lines."""
    return [line.strip() for value in values for line in value.splitlines() if line.strip()]


def safe_date(value: str | None, default: str) -> str:
    """Return value normalized as YYYY-MM-DD, or default if it is not a date."""
    try:
        return date.fromisoformat(value or "").isoformat()
    except ValueError:
        return default


def positive_int(value: str | None, default: int = 1) -> int:
    """Parse a positive integer query parameter, falling back to default."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default
