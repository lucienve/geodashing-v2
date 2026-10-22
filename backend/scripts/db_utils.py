"""Shared database utilities for backend scripts."""

import collections.abc
import configparser
import contextlib
import os
import typing

import mysql.connector
import mysql.connector.connection
import mysql.connector.cursor


def get_db_connection(
        config_path: str) -> mysql.connector.connection.MySQLConnection:
    """Establishes a connection to the MySQL database securely via config.ini.

    Args:
        config_path (str): The absolute or relative path to the backend/config.ini.

    Returns:
        mysql.connector.connection.MySQLConnection: The active database connection object.
        
    Raises:
        FileNotFoundError: If the config file cannot be found.
        RuntimeError: If the database connection fails.
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Database config not found at {config_path}")

    config = configparser.ConfigParser()
    try:
        config.read(config_path)
        db_section = config['database']
        host = db_section.get('DB_HOST', '127.0.0.1').strip('"\'')
        port = db_section.get('DB_PORT', '3306').strip('"\'')
        user = db_section.get('DB_USER', 'geodashing').strip('"\'')
        password = db_section.get('DB_PASS', '').strip('"\'')
        database = db_section.get('DB_NAME', 'geodashing').strip('"\'')
    except (configparser.Error, KeyError, OSError) as e:
        raise RuntimeError(
            f"Database Configuration Error in {config_path}: {e}") from e

    try:
        conn = mysql.connector.connect(host=host,
                                       user=user,
                                       password=password,
                                       database=database,
                                       port=port)
        return typing.cast(mysql.connector.connection.MySQLConnection, conn)
    except mysql.connector.Error as e:
        raise RuntimeError(f"Database Connection Error: {e}") from e


@contextlib.contextmanager
def db_session(
    config_path: str
) -> collections.abc.Iterator[tuple[mysql.connector.connection.MySQLConnection,
                                    mysql.connector.cursor.MySQLCursor]]:
    """Context manager for establishing and closing a database session.

    Args:
        config_path (str): The absolute or relative path to backend/config.ini.

    Yields:
        tuple[MySQLConnection, MySQLCursor]: Active connection and cursor.
    """
    conn = get_db_connection(config_path)
    cursor = conn.cursor()
    try:
        yield conn, cursor
    except Exception as e:
        if conn.is_connected():
            conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()
