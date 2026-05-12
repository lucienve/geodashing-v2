"""Unit tests for the shared db_utils module."""

from unittest.mock import patch, MagicMock
import pytest
import mysql.connector
from backend.scripts.db_utils import get_db_connection

def test_get_db_connection_file_not_found():
    """Verify that FileNotFoundError is raised if config is missing."""
    with patch('os.path.exists', return_value=False):
        with pytest.raises(FileNotFoundError, match="Database config not found"):
            get_db_connection("fake/path.ini")

def test_get_db_connection_success():
    """Verify that a successful connection returns the connection object."""
    mock_conn = MagicMock()

    with patch('os.path.exists', return_value=True), \
         patch('configparser.ConfigParser.read'), \
         patch('configparser.ConfigParser.__getitem__') as mock_getitem, \
         patch('mysql.connector.connect', return_value=mock_conn) as mock_connect:

        # Setup mock config returning defaults
        mock_db_section = MagicMock()
        mock_db_section.get.side_effect = lambda key, default=None: default
        mock_getitem.return_value = mock_db_section

        conn = get_db_connection("fake/path.ini")

        assert conn == mock_conn
        mock_connect.assert_called_once_with(
            host='127.0.0.1',
            user='geodashing',
            password='',
            database='geodashing',
            port='3306'
        )

def test_get_db_connection_mysql_error():
    """Verify that mysql.connector.Error is caught and raised as RuntimeError."""
    with patch('os.path.exists', return_value=True), \
         patch('configparser.ConfigParser.read'), \
         patch('configparser.ConfigParser.__getitem__') as mock_getitem, \
         patch('mysql.connector.connect') as mock_connect:

        # Setup mock config returning defaults
        mock_db_section = MagicMock()
        mock_db_section.get.side_effect = lambda key, default=None: default
        mock_getitem.return_value = mock_db_section

        mock_connect.side_effect = mysql.connector.Error("Mock DB Error")

        with pytest.raises(RuntimeError, match="Database Connection Error: Mock DB Error"):
            get_db_connection("fake/path.ini")
