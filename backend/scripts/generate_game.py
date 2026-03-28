import os
import time
import calendar
import configparser
import numpy as np
import geopandas as gpd
from datetime import datetime
from shapely.geometry import Point
from typing import List
import mysql.connector

def get_db_connection(config_path: str) -> mysql.connector.connection.MySQLConnection:
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
        conn = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            port=port
        )
        return conn
    except mysql.connector.Error as e:
        raise Exception(f"Database Connection Error: {e}")

def seed_database(points: List[Point], config_path: str) -> None:
    """Seeds the newly generated Dashpoints into tracking tables along with a new active Game state.

    Args:
        points (List[Point]): Mathematically verified Point geometries to insert.
        config_path (str): The path to the PHP backend config.ini.
        
    Raises:
        Exception: General sql error handling wrapper for safe failure.
    """
    print("\nConnecting to the database to seed points...")
    try:
        conn = get_db_connection(config_path)
        cursor = conn.cursor()
        
        # 1. Define the game constraints
        now = datetime.now()
        game_name = now.strftime("%B %Y Dash")
        start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        _, last_day = calendar.monthrange(now.year, now.month)
        end_time = now.replace(day=last_day, hour=23, minute=59, second=59, microsecond=0)
        
        # 2. End all active games
        print("Marking previous games as inactive...")
        cursor.execute("UPDATE games SET is_active = FALSE")
        
        # 3. Insert the new active game
        print(f"Initializing new game: '{game_name}'...")
        insert_game_sql = """
            INSERT INTO games (name, start_time, end_time, is_active)
            VALUES (%s, %s, %s, True)
        """
        cursor.execute(insert_game_sql, (game_name, start_time, end_time))
        game_id = cursor.lastrowid
        
        # 4. Insert all valid dashpoints
        print(f"Bulk inserting {len(points)} Dashpoints for Game ID format GD{game_id:02d}...")
        
        # Format the parameters for chunked execution
        # Process in batches of 5000 to prevent overwhelming MySQL's statement packet limits
        insert_dp_sql = """
            INSERT INTO dashpoints (id, game_id, location, country_code, state_province)
            VALUES (%s, %s, ST_GeomFromText(%s, 4326), NULL, NULL)
        """
        
        batch_size = 5000
        for i in range(0, len(points), batch_size):
            batch_data = []
            for j, point in enumerate(points[i:i+batch_size]):
                point_index = i + j + 1
                dashpoint_id = f"GD{game_id:02d}-{point_index:05d}"
                # MySQL 8 SRID 4326 strictly enforces (Latitude Longitude) coordinate ordering
                wkt_string = f"POINT({point.y} {point.x})"
                batch_data.append((dashpoint_id, game_id, wkt_string))
            
            cursor.executemany(insert_dp_sql, batch_data)
            
        conn.commit()
        print("Database seeding completed successfully!")
        
    except Exception as e:
        if 'conn' in locals() and conn.is_connected():
            conn.rollback()
        raise Exception(f"Failed to seed database: {e}")
        
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

def generate_valid_dashpoints(target_count: int = 2000, land_zip_path: str = '../../data/ne_10m_land.zip', lakes_zip_path: str = '../../data/ne_10m_lakes.zip') -> List[Point]:
    """Generates valid dashpoints ensuring they are on land or <= 500m offshore.
    
    Algorithm:
        1. Generates random global spherical coordinates.
        2. Projects the raw points, the core landmass polygons, and the lake boundaries to a Cylindrical Equal-Area CRS (EPSG:6933) to enable precise 2D metric measurements.
        3. Mathematically punches the lake boundaries out of the landmass generating a hole-punched base geometry.
        4. Buffers our simple points by a 500m radius. This is a CPU optimization trick: buffering thousands of simple dots is vastly faster than buffering the entire global coastline.
        5. Filters for points whose 500m radius geometrically intersects the hole-punched land polygon.

    Args:
        target_count (int): The number of valid points to generate.
        land_zip_path (str): The relative or absolute path to the Natural Earth land zip file.
        lakes_zip_path (str): The path to the Natural Earth lakes zip file.

    Returns:
        List[Point]: A list of valid Shapely Point objects.
        
    Raises:
        FileNotFoundError: If the land or lake shapefiles cannot be found or read.
    """
    try:
        land_gdf = gpd.read_file(f"zip://{land_zip_path}")
        lakes_gdf = gpd.read_file(f"zip://{lakes_zip_path}")
    except Exception as e:
        raise FileNotFoundError(f"Failed to read shapefiles: {e}")

    # We reproject the geometries to EPSG:6933 (Cylindrical Equal Area) which uses METERS instead of Degrees.
    # This is crucial so we can accurately measure 500 meters everywhere on earth.
    print("Projecting land and lakes geometries to equal-area projection for accurate meter math...")
    land_proj = land_gdf.to_crs(epsg=6933)
    lakes_proj = lakes_gdf.to_crs(epsg=6933)
    
    print("Computing boolean physical difference (Punching holes in the landmass to exclude major lakes)...")
    land_base = land_proj.geometry.union_all()
    lakes_base = lakes_proj.geometry.union_all()
    
    land_geometry = land_base.difference(lakes_base)
    
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
                print(f"Generated {len(valid_points)} / {target_count} valid dashpoints...")
                
            if len(valid_points) >= target_count:
                break

    return valid_points[:target_count]


if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    zip_path = os.path.join(current_dir, '../../data/ne_10m_land.zip')
    lakes_zip = os.path.join(current_dir, '../../data/ne_10m_lakes.zip')
    config_path = os.path.join(current_dir, '../config.ini')
    
    try:
        # 1. Generate Points
        target = 2000
        points = generate_valid_dashpoints(target_count=target, land_zip_path=zip_path, lakes_zip_path=lakes_zip)
        
        # 2. Upload to MySQL
        seed_database(points, config_path)
        
    except Exception as e:
        print(f"\nExecution Error: {e}")
