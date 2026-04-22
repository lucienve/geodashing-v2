"""Module for generating globally distributed geodashing points."""

import argparse
import calendar
import configparser
import os
from datetime import datetime
from typing import List

import geopandas as gpd
import mysql.connector
import numpy as np
from shapely.geometry import Point


def load_blocklist(bad_words_path: str) -> set:
    """Loads a set of blocked 4-letter strings from a file."""
    if not os.path.exists(bad_words_path):
        return set()
    with open(bad_words_path, 'r', encoding='utf-8') as f:
        return set(line.strip().upper() for line in f if len(line.strip()) == 4)


def int_to_letters(index: int) -> str:
    """Converts an integer to a 4-letter alphabetic sequence string."""
    result = []
    for _ in range(4):
        result.append(chr(65 + (index % 26)))
        index //= 26
    return "".join(reversed(result))


def generate_valid_sequence_id(start_index: int, blocklist: set) -> tuple:
    """Finds the next valid alphabetic sequence ID not present in the blocklist."""
    current = start_index
    while True:
        seq = int_to_letters(current)
        if seq not in blocklist:
            return seq, current + 1
        current += 1


def get_db_connection(
        config_path: str) -> mysql.connector.connection.MySQLConnection:
    """Establishes a connection to the MySQL database securely via config.ini.

    Args:
        config_path (str): The absolute or relative path to the backend/config.ini.

    Returns:
        mysql.connector.connection.MySQLConnection: The active database connection object.
        
    Raises:
        FileNotFoundError: If the config file cannot be found.
        mysql.connector.Error: If the database connection fails.
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Database config not found at {config_path}")

    config = configparser.ConfigParser()
    config.read(config_path)

    # Strip quotes if they were included in the INI formatting
    host = config['database'].get('DB_HOST', '127.0.0.1').strip('"\'')
    port = config['database'].get('DB_PORT', '3306').strip('"\'')
    user = config['database'].get('DB_USER', 'geodashing').strip('"\'')
    password = config['database'].get('DB_PASS', '').strip('"\'')
    database = config['database'].get('DB_NAME', 'geodashing').strip('"\'')

    try:
        conn = mysql.connector.connect(host=host,
                                       user=user,
                                       password=password,
                                       database=database,
                                       port=port)
        return conn
    except mysql.connector.Error as e:
        raise RuntimeError(f"Database Connection Error: {e}") from e


def _initialize_new_game(cursor, game_title: str) -> int:
    """Retires old games and creates a new game record."""
    now = datetime.now()
    start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    _, last_day = calendar.monthrange(now.year, now.month)
    end_time = now.replace(day=last_day,
                           hour=23,
                           minute=59,
                           second=59,
                           microsecond=0)

    print("Marking previous games as inactive...")
    cursor.execute("UPDATE games SET is_active = FALSE")

    print(f"Initializing new game with title '{game_title}'...")
    insert_game_sql = """
        INSERT INTO games (title, start_time, end_time, is_active)
        VALUES (%s, %s, %s, True)
    """
    cursor.execute(insert_game_sql, (game_title, start_time, end_time))
    return cursor.lastrowid


def _bulk_insert_dashpoints(cursor, points: List[Point], game_id: int,
                            bad_words_path: str) -> None:
    """Inserts dashpoints systematically in chunks."""
    blocklist = load_blocklist(bad_words_path)
    current_seq_index = 0

    insert_dp_sql = """
        INSERT INTO dashpoints (id, game_id, location, country_code, state_province)
        VALUES (%s, %s, ST_GeomFromText(%s, 4326), NULL, NULL)
    """

    batch_size = 5000
    for i in range(0, len(points), batch_size):
        batch_data = []
        for point in points[i:i + batch_size]:
            seq_str, current_seq_index = generate_valid_sequence_id(
                current_seq_index, blocklist)
            dashpoint_id = f"GD{game_id:03d}-{seq_str}"
            # MySQL 8 SRID 4326 strictly enforces (Latitude Longitude) coordinate ordering
            wkt_string = f"POINT({point.y} {point.x})"
            batch_data.append((dashpoint_id, game_id, wkt_string))

        cursor.executemany(insert_dp_sql, batch_data)


def seed_database(points: List[Point], config_path: str, game_title: str,
                  bad_words_path: str) -> None:
    """Seeds the newly generated Dashpoints into tracking tables along with a new active Game state.

    Args:
        points (List[Point]): Mathematically verified Point geometries to insert.
        config_path (str): The path to the PHP backend config.ini.
        game_title (str): Brief descriptive title of the game.
        bad_words_path (str): Path to the profanity filter blocklist.
        
    Raises:
        Exception: General sql error handling wrapper for safe failure.
    """
    print("\nConnecting to the database to seed points...")
    try:
        conn = get_db_connection(config_path)
        cursor = conn.cursor()

        game_id = _initialize_new_game(cursor, game_title)

        print(
            f"Bulk inserting {len(points)} Dashpoints for Game ID format GD{game_id:03d}..."
        )
        _bulk_insert_dashpoints(cursor, points, game_id, bad_words_path)

        conn.commit()
        print("Database seeding completed successfully!")

    except Exception as e:
        if 'conn' in locals() and conn.is_connected():
            conn.rollback()
        raise RuntimeError(f"Failed to seed database: {e}") from e

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals() and conn.is_connected():
            conn.close()


def generate_spherical_points(num_points: int) -> List[Point]:
    """Generates random global coordinates with equal geographic density.

    Args:
        num_points (int): The number of raw points to generate.

    Returns:
        List[Point]: A list of Shapely Point objects in WGS84 coordinates.
    """
    lons = np.random.uniform(-180, 180, num_points)
    # asin expects value between -1 and 1
    # random distribution for latitude
    v = np.random.uniform(-1, 1, num_points)
    lats = np.degrees(np.arcsin(v))

    return [Point(lon, lat) for lon, lat in zip(lons, lats)]


def _calculate_land_geometry(land_zip_path: str, lakes_zip_path: str):
    """Loads and computes the hole-punched landmass geometry in EPSG:6933."""
    try:
        land_gdf = gpd.read_file(f"zip://{land_zip_path}")
        lakes_gdf = gpd.read_file(f"zip://{lakes_zip_path}")
    except Exception as e:
        raise FileNotFoundError(f"Failed to read shapefiles: {e}") from e

    print("Projecting land and lakes geometries to EPSG:6933...")
    land_proj = land_gdf.to_crs(epsg=6933)
    lakes_proj = lakes_gdf.to_crs(epsg=6933)

    print(
        "Computing boolean physical difference (Punching holes in landmass)...")
    land_base = land_proj.geometry.union_all()
    lakes_base = lakes_proj.geometry.union_all()

    return land_base.difference(lakes_base)


def generate_valid_dashpoints(
        target_count: int = 2000,
        land_zip_path: str = '../../data/ne_10m_land.zip',
        lakes_zip_path: str = '../../data/ne_10m_lakes.zip') -> List[Point]:
    """Generates valid dashpoints ensuring they are on land or <= 500m offshore.
    
    Algorithm:
        1. Generates random global spherical coordinates.
        2. Projects the raw points, the core landmass polygons, and the lake boundaries
           to a Cylindrical Equal-Area CRS (EPSG:6933) to enable precise 2D metric measurements.
        3. Mathematically punches the lake boundaries out of the landmass generating a
           hole-punched base geometry.
        4. Buffers our simple points by a 500m radius. This is a CPU optimization trick:
           buffering thousands of simple dots is vastly faster than buffering the entire
           global coastline.
        5. Filters for points whose 500m radius geometrically intersects the hole-punched
           land polygon.

    Args:
        target_count (int): The number of valid points to generate.
        land_zip_path (str): The relative or absolute path to the Natural Earth land zip file.
        lakes_zip_path (str): The path to the Natural Earth lakes zip file.

    Returns:
        List[Point]: A list of valid Shapely Point objects.
        
    Raises:
        FileNotFoundError: If the land or lake shapefiles cannot be found or read.
    """
    land_geometry = _calculate_land_geometry(land_zip_path, lakes_zip_path)

    valid_points: List[Point] = []
    batch_size = 10000

    while len(valid_points) < target_count:
        raw_points = generate_spherical_points(batch_size)
        points_gdf = gpd.GeoDataFrame(geometry=raw_points, crs="EPSG:4326")

        points_proj = points_gdf.to_crs(epsg=6933)
        buffered_points = points_proj.buffer(500)

        intersects_land = buffered_points.intersects(land_geometry)
        passed_points_gdf = points_gdf[intersects_land]

        for geom in passed_points_gdf.geometry:
            valid_points.append(geom)

            if len(valid_points) % 1000 == 0:
                print(
                    f"Generated {len(valid_points)} / {target_count} valid dashpoints..."
                )

            if len(valid_points) >= target_count:
                break

    return valid_points[:target_count]


def main() -> None:
    """Main execution point for generating games."""
    parser = argparse.ArgumentParser(
        description="Geodashing V2 Point Generator Engine")
    parser.add_argument(
        '-c',
        '--count',
        type=int,
        default=31000,
        help=
        "The total number of dashpoints to randomly distribute on Earth (default: 31000)"
    )
    parser.add_argument(
        '-t',
        '--title',
        type=str,
        required=True,
        help="Brief descriptive title of the game (max 40 chars)")
    args = parser.parse_args()

    current_dir = os.path.dirname(os.path.abspath(__file__))
    zip_path = os.path.join(current_dir, '../../data/ne_10m_land.zip')
    lakes_zip = os.path.join(current_dir, '../../data/ne_10m_lakes.zip')
    config_path = os.path.join(current_dir, '../config.ini')
    bad_words_path = os.path.join(current_dir, '../../data/bad_words.txt')

    try:
        # 1. Generate Points dynamically bound to the user's explicit CLI count
        target = args.count
        print(f"Generating {target} dashpoints...")
        points = generate_valid_dashpoints(target_count=target,
                                           land_zip_path=zip_path,
                                           lakes_zip_path=lakes_zip)

        # 2. Upload to MySQL
        seed_database(points, config_path, args.title, bad_words_path)

    except (FileNotFoundError, RuntimeError) as e:
        print(f"\nExecution Error: {e}")


if __name__ == "__main__":
    main()
