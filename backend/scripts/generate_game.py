"""Module for generating globally distributed geodashing points."""

import argparse
import calendar
import os
import sys
import datetime
import typing

import geopandas as gpd
import mysql.connector.cursor
import numpy as np
import shapely
import shapely.geometry
import shapely.geometry.base
import shapely.strtree

import backend.scripts.db_utils


def load_blocklist(bad_words_path: str) -> set[str]:
    """Loads a set of blocked 4-letter strings from a file."""
    if not os.path.exists(bad_words_path):
        raise FileNotFoundError(f"Profanity blocklist not found at {bad_words_path}")
    with open(bad_words_path, 'r', encoding='utf-8') as f:
        return set(line.strip().upper() for line in f if len(line.strip()) == 4)


def int_to_letters(index: int) -> str:
    """Converts an integer to a 4-letter alphabetic sequence string."""
    result = []
    for _ in range(4):
        result.append(chr(65 + (index % 26)))
        index //= 26
    return "".join(reversed(result))


def generate_valid_sequence_id(start_index: int, blocklist: set[str]) -> tuple[str, int]:
    """Finds the next valid alphabetic sequence ID not present in the blocklist."""
    current = start_index
    while True:
        seq = int_to_letters(current)
        if seq not in blocklist:
            return seq, current + 1
        current += 1



def initialize_new_game(
    cursor: mysql.connector.cursor.MySQLCursor,
    game_title: str,
    year: int | None = None,
    month: int | None = None,
    is_preview: bool = False
) -> int:
    """Retires old games and creates a new game record."""
    now = datetime.datetime.now()
    if year is None:
        year = now.year
    if month is None:
        month = now.month

    _, last_day = calendar.monthrange(year, month)
    start_time = datetime.datetime(year, month, 1, 0, 0, 0)
    end_time = datetime.datetime(year, month, last_day, 23, 59, 59)

    cursor.execute(
        "SELECT id, title FROM games WHERE YEAR(start_time) = %s AND MONTH(start_time) = %s",
        (year, month)
    )
    existing = cursor.fetchone()
    if existing:
        raise ValueError(
            f"A game for {year}-{month:02d} already exists (Game {existing[0]}: '{existing[1]}'). "
            "Duplicate creation blocked."
        )

    if not is_preview:
        print("Marking previous games as inactive...")
        cursor.execute("UPDATE games SET is_active = FALSE")
        print(f"Initializing new active game with title '{game_title}'...")
        insert_game_sql = """
            INSERT INTO games (title, start_time, end_time, is_active)
            VALUES (%s, %s, %s, True)
        """
    else:
        print(f"Initializing new preview game with title '{game_title}'...")
        insert_game_sql = """
            INSERT INTO games (title, start_time, end_time, is_active)
            VALUES (%s, %s, %s, False)
        """

    cursor.execute(insert_game_sql, (game_title, start_time, end_time))
    assert cursor.lastrowid is not None
    return cursor.lastrowid


# Alias for backward compatibility
_initialize_new_game = initialize_new_game


def bulk_insert_dashpoints(
    cursor: mysql.connector.cursor.MySQLCursor,
    points: list[shapely.geometry.Point],
    game_id: int,
    bad_words_path: str
) -> None:
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


# Alias for backward compatibility
_bulk_insert_dashpoints = bulk_insert_dashpoints


def seed_database(points: list[shapely.geometry.Point], config_path: str, game_title: str,
                  bad_words_path: str, **kwargs: typing.Any) -> None:
    """Seeds the newly generated Dashpoints into tracking tables along with a new active Game state.

    Args:
        points (List[Point]): Mathematically verified Point geometries to insert.
        config_path (str): The path to the PHP backend config.ini.
        game_title (str): Brief descriptive title of the game.
        bad_words_path (str): Path to the profanity filter blocklist.
        **kwargs: Optional overrides including 'year' (int), 'month' (int),
                  and 'is_preview' (bool) for generating inactive games.
        
    Raises:
        Exception: General sql error handling wrapper for safe failure.
    """
    print("\nConnecting to the database to seed points...")
    try:
        with backend.scripts.db_utils.db_session(config_path) as (conn, cursor):
            year = kwargs.get('year')
            month = kwargs.get('month')
            is_preview = kwargs.get('is_preview')

            year_val = int(year) if year is not None else None
            month_val = int(month) if month is not None else None
            is_preview_val = bool(is_preview) if is_preview is not None else False

            game_id = _initialize_new_game(
                cursor, game_title, year_val, month_val, is_preview_val
            )

            print(
                f"Bulk inserting {len(points)} Dashpoints for Game ID format GD{game_id:03d}..."
            )
            _bulk_insert_dashpoints(cursor, points, game_id, bad_words_path)

            conn.commit()
            print("Database seeding completed successfully!")

    except Exception as e:
        raise RuntimeError(f"Failed to seed database: {e}") from e


def generate_spherical_points(num_points: int) -> list[shapely.geometry.Point]:
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

    return [shapely.geometry.Point(lon, lat) for lon, lat in zip(lons, lats)]


def subdivide_geometry(
    geom: shapely.geometry.base.BaseGeometry,
    max_size: float = 1000000.0
) -> list[shapely.geometry.base.BaseGeometry]:
    """Subdivides a geometry into a grid of smaller geometries of a maximum metric size."""
    if geom is None or geom.is_empty:
        return []
    minx, miny, maxx, maxy = geom.bounds
    x_coords = np.arange(minx, maxx + max_size, max_size)
    y_coords = np.arange(miny, maxy + max_size, max_size)

    # Flatten the grid creation to minimize nested block depth
    grid_boxes = []
    for i in range(len(x_coords) - 1):
        for j in range(len(y_coords) - 1):
            grid_boxes.append(
                shapely.geometry.box(x_coords[i], y_coords[j], x_coords[i + 1], y_coords[j + 1])
            )

    subdivided: list[shapely.geometry.base.BaseGeometry] = []
    for box in grid_boxes:
        if not geom.intersects(box):
            continue
        inter = geom.intersection(box)
        if inter.is_empty:
            continue
        # Unpack multi-geometries and geometry collections using get_parts
        for g in shapely.get_parts(inter):
            if g.geom_type in ('Polygon', 'MultiPolygon'):
                subdivided.append(g)
    return subdivided


def _load_and_project_geometries(
    land_zip_path: str,
    lakes_zip_path: str,
    verbose: bool = True
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Loads and projects the land and lake shapefiles to EPSG:6933."""
    try:
        land_gdf = gpd.read_file(f"zip://{land_zip_path}")
        lakes_gdf = gpd.read_file(f"zip://{lakes_zip_path}")
    except Exception as e:
        raise FileNotFoundError(f"Failed to read shapefiles: {e}") from e

    if verbose:
        print("Projecting land and lakes geometries to EPSG:6933...")
    return land_gdf.to_crs(epsg=6933), lakes_gdf.to_crs(epsg=6933)


class SpatialFilter:
    """Helper class to encapsulate spatial indexing and boundary filtering logic."""

    def __init__(
        self,
        tree_land: shapely.strtree.STRtree,
        tree_lakes: shapely.strtree.STRtree,
        land_sub: list[shapely.geometry.base.BaseGeometry],
        lakes_sub: list[shapely.geometry.base.BaseGeometry]
    ) -> None:
        self.tree_land = tree_land
        self.tree_lakes = tree_lakes
        self.land_sub = land_sub
        self.lakes_sub = lakes_sub

    def get_candidate_matches(
        self,
        buffers: typing.Any
    ) -> tuple[dict[int, list[shapely.geometry.base.BaseGeometry]],
               dict[int, list[shapely.geometry.base.BaseGeometry]]]:
        """Finds matching land and lake geometries for each buffered point."""
        land_matches = self.tree_land.query(buffers)
        land_map: dict[int, list[shapely.geometry.base.BaseGeometry]] = {}
        if land_matches.size > 0:
            for buf_idx, land_idx in zip(land_matches[0], land_matches[1]):
                land_map.setdefault(buf_idx, []).append(self.land_sub[land_idx])

        lake_matches = self.tree_lakes.query(buffers)
        lake_map: dict[int, list[shapely.geometry.base.BaseGeometry]] = {}
        if lake_matches.size > 0:
            for buf_idx, lake_idx in zip(lake_matches[0], lake_matches[1]):
                lake_map.setdefault(buf_idx, []).append(self.lakes_sub[lake_idx])

        return land_map, lake_map

    def eval_boundary_point(
        self,
        buffer_geom: shapely.geometry.base.BaseGeometry,
        matching_lands: list[shapely.geometry.base.BaseGeometry],
        matching_lakes: list[shapely.geometry.base.BaseGeometry]
    ) -> bool:
        """Determines if a single buffered point intersects dry land (land minus lakes)."""
        if len(matching_lands) == 1:
            land_geom = matching_lands[0]
        else:
            land_geom = shapely.union_all(matching_lands)

        if matching_lakes:
            if len(matching_lakes) == 1:
                lake_geom = matching_lakes[0]
            else:
                lake_geom = shapely.union_all(matching_lakes)
            land_minus_lakes = land_geom.difference(lake_geom)
        else:
            land_minus_lakes = land_geom

        return buffer_geom.intersects(land_minus_lakes)

    def filter_boundary_candidates(
        self,
        raw_points: list[shapely.geometry.Point],
        proj_geoms: list[shapely.geometry.base.BaseGeometry],
        remaining_indices: list[int]
    ) -> list[shapely.geometry.Point]:
        """Filters the remaining points using 100m buffers and local geometry intersections."""
        remaining_pts = [proj_geoms[i] for i in remaining_indices]
        remaining_buffers = shapely.buffer(remaining_pts, 100)

        land_map, lake_map = self.get_candidate_matches(remaining_buffers)
        if not land_map:
            return []

        valid: list[shapely.geometry.Point] = []
        for buf_idx, matching_lands in land_map.items():
            buffer_geom = remaining_buffers[buf_idx]
            matching_lakes = lake_map.get(buf_idx, [])

            if self.eval_boundary_point(buffer_geom, matching_lands, matching_lakes):
                orig_idx = remaining_indices[buf_idx]
                valid.append(raw_points[orig_idx])

        return valid


def build_spatial_filter(
    land_zip_path: str,
    lakes_zip_path: str,
    verbose: bool = True
) -> SpatialFilter:
    """Loads shapefiles, projects them, subdivides them, and builds the SpatialFilter."""
    land_proj, lakes_proj = _load_and_project_geometries(land_zip_path, lakes_zip_path, verbose)

    if verbose:
        print("Subdividing land and lakes geometries to optimize spatial query performance...")
    land_sub: list[shapely.geometry.base.BaseGeometry] = []
    for geom in land_proj.geometry:
        if geom is not None and not geom.is_empty:
            land_sub.extend(subdivide_geometry(geom, max_size=1000000.0))

    lakes_sub: list[shapely.geometry.base.BaseGeometry] = []
    for geom in lakes_proj.geometry:
        if geom is not None and not geom.is_empty:
            lakes_sub.extend(subdivide_geometry(geom, max_size=1000000.0))

    if verbose:
        print("Building spatial indexes...")
    tree_land = shapely.strtree.STRtree(land_sub)
    tree_lakes = shapely.strtree.STRtree(lakes_sub)

    if verbose:
        print("Preparing geometries...")
    shapely.prepare(land_sub)
    shapely.prepare(lakes_sub)

    return SpatialFilter(tree_land, tree_lakes, land_sub, lakes_sub)


def generate_valid_dashpoints(
        target_count: int = 2000,
        land_zip_path: str = '../../data/ne_10m_land.zip',
        lakes_zip_path: str = '../../data/ne_10m_lakes.zip') -> list[shapely.geometry.Point]:
    """Generates valid dashpoints ensuring they are on land or <= 100m offshore.

    Algorithm:
        1. Generates random global spherical coordinates.
        2. Projects the raw points, the landmass polygons, and the lake boundaries
           to a Cylindrical Equal-Area CRS (EPSG:6933) for precise distance analysis.
        3. Subdivides complex land/lake polygons to limit vertex counts (< 100).
        4. Performs a fast Point-in-Polygon (PIP) check to accept points directly
           on dry land and not inside a lake.
        5. For the remaining points (e.g. ocean points, lake points), buffers by 100m
           and performs localized spatial query intersection checks via STRtree.

    Args:
        target_count (int): The number of valid points to generate.
        land_zip_path (str): The relative or absolute path to the Natural Earth land zip file.
        lakes_zip_path (str): The path to the Natural Earth lakes zip file.

    Returns:
        List[Point]: A list of valid Shapely Point objects.

    Raises:
        FileNotFoundError: If the land or lake shapefiles cannot be found or read.
    """
    spatial_filter = build_spatial_filter(land_zip_path, lakes_zip_path)


    valid_points: list[shapely.geometry.Point] = []
    batch_size = 50000 if target_count > 10000 else 10000

    print("Generating valid dashpoints...")
    while len(valid_points) < target_count:
        raw_points = generate_spherical_points(batch_size)
        proj_geoms = gpd.GeoDataFrame(
            geometry=raw_points, crs="EPSG:4326"
        ).to_crs(epsg=6933).geometry.tolist()

        # Step 1: Fast Point-in-Polygon (PIP) check
        land_contains = spatial_filter.tree_land.query(proj_geoms, predicate="contains")
        on_land_indices = set(land_contains[0])

        lake_contains = spatial_filter.tree_lakes.query(proj_geoms, predicate="contains")
        in_lake_indices = set(lake_contains[0])

        # Dry land points are directly on land and not in a lake
        immediate_valid = on_land_indices - in_lake_indices
        valid_points.extend(raw_points[i] for i in immediate_valid)

        # Step 2: Buffer remaining points and do local checks
        remaining_indices = [i for i in range(len(raw_points)) if i not in immediate_valid]
        if remaining_indices:
            valid_points.extend(
                spatial_filter.filter_boundary_candidates(
                    raw_points, proj_geoms, remaining_indices
                )
            )

        # Print progress
        if len(valid_points) % 1000 == 0 or len(valid_points) >= target_count:
            print(
                f"Generated {min(len(valid_points), target_count)} / "
                f"{target_count} valid dashpoints..."
            )

    return valid_points[:target_count]


def main() -> None:
    """Main execution point for generating games."""
    parser = argparse.ArgumentParser(
        description="Geodashing V2 Point Generator Engine")
    parser.add_argument(
        '-c',
        '--count',
        type=int,
        default=35000,
        help=
        "The total number of dashpoints to randomly distribute on Earth (default: 35000)"
    )
    parser.add_argument(
        '-t',
        '--title',
        type=str,
        required=True,
        help="Brief descriptive title of the game (max 40 chars)")
    parser.add_argument(
        '-m',
        '--month',
        type=int,
        help="Optional month (1-12) to generate the game for (defaults to current month)")
    parser.add_argument(
        '-y',
        '--year',
        type=int,
        help="Optional year to generate the game for (defaults to current year)")
    parser.add_argument(
        '--preview',
        action='store_true',
        help="Generate the game in an inactive preview state instead of immediately activating it")
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
        seed_database(
            points, config_path, args.title, bad_words_path,
            year=args.year, month=args.month, is_preview=args.preview
        )

    except (FileNotFoundError, RuntimeError, ValueError) as e:
        print(f"\nExecution Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
