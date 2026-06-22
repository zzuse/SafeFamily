"""Tests for utility helper functions."""

from unittest.mock import MagicMock, patch

from src.safe_family.utils import helpers


def test_get_agile_config_returns_value():
    """Test that get_agile_config returns the correct value from the database."""
    mock_conn = MagicMock()
    mock_cur = mock_conn.cursor.return_value
    mock_cur.fetchone.return_value = ("18:00",)

    with patch("src.safe_family.utils.helpers.get_db_connection", return_value=mock_conn):
        result = helpers.get_agile_config("test_key", "default")

    assert result == "18:00"
    mock_cur.execute.assert_called_once_with(
        "SELECT config_value FROM agile_config WHERE config_key = %s",
        ("test_key",),
    )
    mock_conn.close.assert_called_once()


def test_get_agile_config_returns_default_when_not_found():
    """Test that get_agile_config returns the default value if key is missing."""
    mock_conn = MagicMock()
    mock_cur = mock_conn.cursor.return_value
    mock_cur.fetchone.return_value = None

    with patch("src.safe_family.utils.helpers.get_db_connection", return_value=mock_conn):
        result = helpers.get_agile_config("missing_key", "default_val")

    assert result == "default_val"
    mock_conn.close.assert_called_once()


def test_get_agile_config_handles_exception():
    """Test that get_agile_config returns default on database error."""
    with patch("src.safe_family.utils.helpers.get_db_connection", side_effect=Exception("DB Error")):
        result = helpers.get_agile_config("any_key", "fallback")

    assert result == "fallback"


def test_set_agile_config_success():
    """Test that set_agile_config executes the correct UPSERT query."""
    mock_conn = MagicMock()
    mock_cur = mock_conn.cursor.return_value

    with patch("src.safe_family.utils.helpers.get_db_connection", return_value=mock_conn):
        helpers.set_agile_config("new_key", "new_val")

    assert mock_cur.execute.called
    args, _ = mock_cur.execute.call_args
    assert "INSERT INTO agile_config" in args[0]
    assert "ON CONFLICT (config_key)" in args[0]
    assert args[1] == ("new_key", "new_val")
    mock_conn.commit.assert_called_once()
    mock_conn.close.assert_called_once()


def test_set_agile_config_handles_exception():
    """Test that set_agile_config rolls back on error."""
    mock_conn = MagicMock()
    mock_cur = mock_conn.cursor.return_value
    mock_cur.execute.side_effect = Exception("Write Error")

    with patch("src.safe_family.utils.helpers.get_db_connection", return_value=mock_conn):
        helpers.set_agile_config("key", "val")

    mock_conn.rollback.assert_called_once()
    mock_conn.close.assert_called_once()


def test_update_agile_config_by_timestamp_basic():
    """Verify formula output for a known input with no delay or eating."""
    saved = {}

    def fake_set(key: str, value: str) -> None:
        saved[key] = value

    with patch("src.safe_family.utils.helpers.set_agile_config", side_effect=fake_set):
        result = helpers.update_agile_config_by_timestamp("10:00")

    assert result is True
    # input=10.0 → start=((-3)*10+46)/4+12 = 16/4+12 = 4+12 = 16.0 → "16:00"
    assert saved["show_disable_button_start"] == "16:00"
    assert saved["show_disable_button_end"] == "16:30"


def test_update_agile_config_by_timestamp_with_delay_and_eating():
    """Verify delay and eating minutes shift start time correctly."""
    saved = {}

    def fake_set(key: str, value: str) -> None:
        saved[key] = value

    with patch("src.safe_family.utils.helpers.set_agile_config", side_effect=fake_set):
        # input=10.0, delay=60min=1h, eating=60min=1h
        # start=((-3)*10+46)/4 + 1 + 1 + 12 = 4 + 2 + 12 = 18.0 → "18:00"
        result = helpers.update_agile_config_by_timestamp("10:00", delay_minutes=60, eating_minutes=60)

    assert result is True
    assert saved["show_disable_button_start"] == "18:00"
    assert saved["show_disable_button_end"] == "18:30"


def test_update_agile_config_by_timestamp_with_fractional_minutes():
    """Verify float delay/eating values are handled correctly."""
    saved = {}

    def fake_set(key: str, value: str) -> None:
        saved[key] = value

    with patch("src.safe_family.utils.helpers.set_agile_config", side_effect=fake_set):
        # input=10.0, delay=30.0min=0.5h, eating=30.0min=0.5h
        # start=((-3)*10+46)/4 + 0.5 + 0.5 + 12 = 4 + 1 + 12 = 17.0 → "17:00"
        result = helpers.update_agile_config_by_timestamp("10:00", delay_minutes=30.0, eating_minutes=30.0)

    assert result is True
    assert saved["show_disable_button_start"] == "17:00"
    assert saved["show_disable_button_end"] == "17:30"


def test_update_agile_config_by_timestamp_with_minutes_in_input():
    """Verify fractional hour input (HH:MM) is parsed correctly."""
    saved = {}

    def fake_set(key: str, value: str) -> None:
        saved[key] = value

    with patch("src.safe_family.utils.helpers.set_agile_config", side_effect=fake_set):
        # input=10.5 → start=((-3)*10.5+46)/4+12 = 14.5/4+12 = 3.625+12 = 15.625 → "15:38" (rounded)
        result = helpers.update_agile_config_by_timestamp("10:30")

    assert result is True
    assert saved["show_disable_button_start"] == "15:38"
    assert saved["show_disable_button_end"] == "16:08"


def test_update_agile_config_by_timestamp_invalid_format():
    """Return False for a malformed time string."""
    result = helpers.update_agile_config_by_timestamp("not-a-time")
    assert result is False


def test_update_agile_config_by_timestamp_returns_false_on_set_error():
    """Return False when set_agile_config raises."""
    with patch("src.safe_family.utils.helpers.set_agile_config", side_effect=Exception("DB down")):
        result = helpers.update_agile_config_by_timestamp("10:00")
    assert result is False
