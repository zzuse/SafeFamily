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
