"""Unit tests for the shared db_utils module."""

import configparser
import unittest.mock
import pytest
import mysql.connector
import mysql.connector.cursor
import backend.scripts.db_utils

def test_get_db_connection_file_not_found() -> None:
    """Verify that FileNotFoundError is raised if config is missing."""
    with unittest.mock.patch('os.path.exists', return_value=False, autospec=True):
        with pytest.raises(FileNotFoundError, match="Database config not found"):
            backend.scripts.db_utils.get_db_connection("fake/path.ini")

def test_get_db_connection_success() -> None:
    """Verify that a successful connection returns the connection object."""
    mock_conn = unittest.mock.MagicMock(spec=mysql.connector.connection.MySQLConnection)

    with unittest.mock.patch('os.path.exists', return_value=True, autospec=True), \
         unittest.mock.patch('configparser.ConfigParser.read', autospec=True), \
         unittest.mock.patch(
             'configparser.ConfigParser.__getitem__', autospec=True
         ) as mock_getitem, \
         unittest.mock.patch(
             'mysql.connector.connect', return_value=mock_conn, autospec=True
         ) as mock_connect:

        # Setup mock config returning defaults
        mock_db_section = unittest.mock.MagicMock(spec=configparser.SectionProxy)
        mock_db_section.get.side_effect = lambda key, default=None: default
        mock_getitem.return_value = mock_db_section

        conn = backend.scripts.db_utils.get_db_connection("fake/path.ini")

        assert conn == mock_conn
        mock_connect.assert_called_once_with(
            host='127.0.0.1',
            user='geodashing',
            password='',
            database='geodashing',
            port='3306'
        )

def test_get_db_connection_mysql_error() -> None:
    """Verify that mysql.connector.Error is caught and raised as RuntimeError."""
    with unittest.mock.patch('os.path.exists', return_value=True, autospec=True), \
         unittest.mock.patch('configparser.ConfigParser.read', autospec=True), \
         unittest.mock.patch(
             'configparser.ConfigParser.__getitem__', autospec=True
         ) as mock_getitem, \
         unittest.mock.patch('mysql.connector.connect', autospec=True) as mock_connect:

        # Setup mock config returning defaults
        mock_db_section = unittest.mock.MagicMock(spec=configparser.SectionProxy)
        mock_db_section.get.side_effect = lambda key, default=None: default
        mock_getitem.return_value = mock_db_section

        mock_connect.side_effect = mysql.connector.Error("Mock DB Error")

        with pytest.raises(RuntimeError, match="Database Connection Error: Mock DB Error"):
            backend.scripts.db_utils.get_db_connection("fake/path.ini")


def test_db_session_success() -> None:
    """Verify db_session yields connection/cursor and closes them on success."""
    mock_conn = unittest.mock.MagicMock(spec=mysql.connector.connection.MySQLConnection)
    mock_cursor = unittest.mock.MagicMock(spec=mysql.connector.cursor.MySQLCursor)
    mock_conn.cursor.return_value = mock_cursor

    with unittest.mock.patch(
        'backend.scripts.db_utils.get_db_connection',
        return_value=mock_conn,
        autospec=True
    ) as mock_get_conn:
        with backend.scripts.db_utils.db_session("fake/path.ini") as (conn, cursor):
            assert conn == mock_conn
            assert cursor == mock_cursor
            mock_cursor.close.assert_not_called()
            mock_conn.close.assert_not_called()

        mock_get_conn.assert_called_once_with("fake/path.ini")
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()


def test_db_session_exception() -> None:
    """Verify db_session rolls back and propagates exceptions on failure."""
    mock_conn = unittest.mock.MagicMock(spec=mysql.connector.connection.MySQLConnection)
    mock_cursor = unittest.mock.MagicMock(spec=mysql.connector.cursor.MySQLCursor)
    mock_conn.cursor.return_value = mock_cursor

    with unittest.mock.patch(
        'backend.scripts.db_utils.get_db_connection',
        return_value=mock_conn,
        autospec=True
    ):
        with pytest.raises(ValueError, match="Mock Error"):
            with backend.scripts.db_utils.db_session("fake/path.ini"):
                raise ValueError("Mock Error")

        mock_conn.rollback.assert_called_once()
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()
