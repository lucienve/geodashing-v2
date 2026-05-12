"""Shared database utilities for backend scripts."""

import configparser
import os
import mysql.connector

def get_db_connection(config_path: str) -> mysql.connector.connection.MySQLConnection:
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
    config.read(config_path)

    host = config['database'].get('DB_HOST', '127.0.0.1').strip('"\'')
    port = config['database'].get('DB_PORT', '3306').strip('"\'')
    user = config['database'].get('DB_USER', 'geodashing').strip('"\'')
    password = config['database'].get('DB_PASS', '').strip('"\'')
    database = config['database'].get('DB_NAME', 'geodashing').strip('"\'')

    try:
        conn = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            port=port
        )
        return conn
    except mysql.connector.Error as e:
        raise RuntimeError(f"Database Connection Error: {e}") from e
