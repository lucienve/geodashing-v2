"""Module for generating globally distributed geodashing points."""

import argparse
import calendar
import dataclasses
import datetime
import itertools
import math
import os
import sys
import typing

import geopandas as gpd
import mysql.connector.cursor
import numpy as np
import shapely
import shapely.geometry
import shapely.geometry.base
import shapely.strtree

import backend.scripts.db_utils
import backend.scripts.prepare_roads

EARTH_RADIUS_KM: float = 6371.0088
DEFAULT_GRID_SIZE_KM: float = 60.05
MIN_NEIGHBOR_DISTANCE_KM: float = 12.0
MAX_CELL_ATTEMPTS: int = 50
MAX_ROAD_DISTANCE_M: float = 50.0
LAKE_SUPPLEMENT_FILENAMES: tuple[str, ...] = (
    'ne_10m_lakes_australia.zip',
    'ne_10m_lakes_europe.zip',
    'ne_10m_lakes_north_america.zip',
)


@dataclasses.dataclass(frozen=True)
class LatitudeBand:
    """Represents a discrete latitudinal band on the globe."""
    band_idx: int
    lat_min: float
    lat_max: float
    lon_offset: float
    num_cells: int
    dlon: float


class SphereNeighborGrid:
    """3D unit-sphere spatial hash grid for enforcing minimum great-circle spacing."""

    def __init__(self,
                 min_distance_km: float = MIN_NEIGHBOR_DISTANCE_KM,
                 earth_radius_km: float = EARTH_RADIUS_KM) -> None:
        """Initializes the spatial hash grid with chord distance buckets."""
        if min_distance_km <= 0:
            raise ValueError(
                f"min_distance_km must be positive, got {min_distance_km}")
        self._min_distance_km = min_distance_km
        self._earth_radius_km = earth_radius_km
        # Great circle distance d to 3D unit chord length: c = 2 * sin(d / (2 * R))
        self._chord_dist = 2.0 * math.sin(min_distance_km /
                                          (2.0 * earth_radius_km))
        self._chord_dist_sq = self._chord_dist**2
        self._cell_size = self._chord_dist
        self._grid: dict[tuple[int, int, int], list[tuple[float, float,
                                                          float]]] = {}
        self._count = 0

    def _to_unit_vector(self, lon: float,
                        lat: float) -> tuple[float, float, float]:
        """Converts (longitude, latitude) in degrees to 3D unit coordinates (x, y, z)."""
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)
        cos_lat = math.cos(lat_rad)
        x = cos_lat * math.cos(lon_rad)
        y = cos_lat * math.sin(lon_rad)
        z = math.sin(lat_rad)
        return x, y, z

    def _get_key(self, x: float, y: float, z: float) -> tuple[int, int, int]:
        """Maps 3D coordinates to a discrete bucket key."""
        return (math.floor(x / self._cell_size),
                math.floor(y / self._cell_size),
                math.floor(z / self._cell_size))

    def _is_too_close(self, x: float, y: float, z: float,
                      pts: list[tuple[float, float, float]]) -> bool:
        """Determines if (x, y, z) is within chord distance of any stored points."""
        for ox, oy, oz in pts:
            dist_sq = (x - ox)**2 + (y - oy)**2 + (z - oz)**2
            if dist_sq < self._chord_dist_sq:
                return True
        return False

    def can_place(self, lon: float, lat: float) -> bool:
        """Checks if a point is at least min_distance_km from all stored points."""
        x, y, z = self._to_unit_vector(lon, lat)
        bx, by, bz = self._get_key(x, y, z)

        for dx, dy, dz in itertools.product((-1, 0, 1), repeat=3):
            stored_pts = self._grid.get((bx + dx, by + dy, bz + dz))
            if stored_pts and self._is_too_close(x, y, z, stored_pts):
                return False
        return True

    def insert(self, lon: float, lat: float) -> bool:
        """Inserts a point if it meets the minimum distance constraint."""
        if not self.can_place(lon, lat):
            return False
        x, y, z = self._to_unit_vector(lon, lat)
        key = self._get_key(x, y, z)
        self._grid.setdefault(key, []).append((x, y, z))
        self._count += 1
        return True

    def count(self) -> int:
        """Returns the number of accepted points in the grid."""
        return self._count


def build_spherical_grid(
        grid_size_km: float = DEFAULT_GRID_SIZE_KM,
        earth_radius_km: float = EARTH_RADIUS_KM) -> list[LatitudeBand]:
    """Divides the globe into staggered spherical trapezoids of approximately grid_size_km."""
    if grid_size_km <= 0:
        raise ValueError(f"grid_size_km must be positive, got {grid_size_km}")

    dlat = math.degrees(grid_size_km / earth_radius_km)
    lat_shift = float(np.random.uniform(0.0, dlat))

    bands: list[LatitudeBand] = []
    lat_cursor = -90.0
    band_idx = 0

    while lat_cursor < 90.0:
        if band_idx == 0 and lat_shift > 0.0:
            lat_next = min(90.0, -90.0 + lat_shift)
        else:
            lat_next = min(90.0, lat_cursor + dlat)

        if lat_next - lat_cursor > 1e-6:
            lat_center = 0.5 * (lat_cursor + lat_next)
            circumference = 2.0 * math.pi * earth_radius_km * math.cos(
                math.radians(lat_center))
            num_cells = max(1, round(circumference / grid_size_km))
            dlon = 360.0 / num_cells
            lon_offset = -180.0 + float(np.random.uniform(0.0, dlon))

            bands.append(
                LatitudeBand(band_idx=band_idx,
                             lat_min=lat_cursor,
                             lat_max=lat_next,
                             lon_offset=lon_offset,
                             num_cells=num_cells,
                             dlon=dlon))
            band_idx += 1

        lat_cursor = lat_next

    return bands


def get_cardinal_neighbors(band: LatitudeBand, cell_idx: int,
                           bands: list[LatitudeBand]) -> list[tuple[int, int]]:
    """Identifies the 4 cardinal neighbor cells (East, West, North, South) for a grid cell."""
    neighbors: list[tuple[int, int]] = []

    # East and West within the same latitude band
    neighbors.append((band.band_idx, (cell_idx + 1) % band.num_cells))
    neighbors.append((band.band_idx, (cell_idx - 1) % band.num_cells))

    # Longitude center of current cell normalized to [-180.0, 180.0)
    lon_start = band.lon_offset + cell_idx * band.dlon
    lon_center = ((lon_start + 0.5 * band.dlon + 180.0) % 360.0) - 180.0

    # North neighbor (if not the northernmost band)
    if band.band_idx + 1 < len(bands):
        north_band = bands[band.band_idx + 1]
        north_j = int(((lon_center - north_band.lon_offset) % 360.0) //
                      north_band.dlon) % north_band.num_cells
        neighbors.append((north_band.band_idx, north_j))

    # South neighbor (if not the southernmost band)
    if band.band_idx - 1 >= 0:
        south_band = bands[band.band_idx - 1]
        south_j = int(((lon_center - south_band.lon_offset) % 360.0) //
                      south_band.dlon) % south_band.num_cells
        neighbors.append((south_band.band_idx, south_j))

    return neighbors


def sample_point_in_cell(band: LatitudeBand,
                         cell_idx: int) -> shapely.geometry.Point:
    """Samples a single uniform random geographic point inside a spherical trapezoid cell."""
    sin_min = math.sin(math.radians(band.lat_min))
    sin_max = math.sin(math.radians(band.lat_max))
    u = float(np.random.uniform(sin_min, sin_max))
    lat = math.degrees(math.asin(max(-1.0, min(1.0, u))))

    v = float(np.random.uniform(0.0, 1.0))
    raw_lon = band.lon_offset + (cell_idx + v) * band.dlon
    lon = ((raw_lon + 180.0) % 360.0) - 180.0

    return shapely.geometry.Point(lon, lat)


get_cell_bboxes = backend.scripts.prepare_roads.get_cell_bboxes


def _find_valid_cell_point(
        band: LatitudeBand, cell_idx: int, initial_pt: shapely.geometry.Point,
        spatial_filter: 'SpatialFilter',
        neighbor_grid: SphereNeighborGrid) -> shapely.geometry.Point | None:
    """Finds a non-colliding dry-land point in the cell, retrying up to MAX_CELL_ATTEMPTS."""
    if neighbor_grid.insert(initial_pt.x, initial_pt.y):
        return initial_pt

    for _ in range(MAX_CELL_ATTEMPTS):
        cand = sample_point_in_cell(band, cell_idx)
        if neighbor_grid.can_place(cand.x, cand.y):
            if spatial_filter.filter_valid_indices([cand]):
                neighbor_grid.insert(cand.x, cand.y)
                return cand
    return None


def load_blocklist(bad_words_path: str) -> set[str]:
    """Loads a set of blocked 4-letter strings from a file."""
    if not os.path.exists(bad_words_path):
        raise FileNotFoundError(
            f"Profanity blocklist not found at {bad_words_path}")
    try:
        with open(bad_words_path, 'r', encoding='utf-8') as f:
            return set(line.strip().upper() for line in f
                       if len(line.strip()) == 4)
    except OSError as e:
        raise RuntimeError(
            f"Failed to read profanity blocklist at {bad_words_path}: {e}"
        ) from e


def int_to_letters(index: int) -> str:
    """Converts an integer to a 4-letter alphabetic sequence string."""
    result: list[str] = []
    for _ in range(4):
        result.append(chr(65 + (index % 26)))
        index //= 26
    return "".join(reversed(result))


def generate_valid_sequence_id(start_index: int,
                               blocklist: set[str]) -> tuple[str, int]:
    """Finds the next valid alphabetic sequence ID not present in the blocklist."""
    current = start_index
    while True:
        seq = int_to_letters(current)
        if seq not in blocklist:
            return seq, current + 1
        current += 1


def initialize_new_game(cursor: mysql.connector.cursor.MySQLCursor,
                        game_title: str,
                        year: int | None = None,
                        month: int | None = None,
                        is_preview: bool = False) -> int:
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
        (year, month))
    existing = cursor.fetchone()
    if existing:
        raise ValueError(
            f"A game for {year}-{month:02d} already exists (Game {existing[0]}: '{existing[1]}'). "
            "Duplicate creation blocked.")

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
    if cursor.lastrowid is None:
        raise RuntimeError("Failed to retrieve lastrowid for new game insert.")
    return cursor.lastrowid


def bulk_insert_dashpoints(cursor: mysql.connector.cursor.MySQLCursor,
                           points: list[shapely.geometry.Point], game_id: int,
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
        batch_data: list[tuple[str, int, str]] = []
        for point in points[i:i + batch_size]:
            seq_str, current_seq_index = generate_valid_sequence_id(
                current_seq_index, blocklist)
            dashpoint_id = f"GD{game_id:03d}-{seq_str}"
            # MySQL 8 SRID 4326 strictly enforces (Latitude Longitude) coordinate ordering
            wkt_string = f"POINT({point.y} {point.x})"
            batch_data.append((dashpoint_id, game_id, wkt_string))

        cursor.executemany(insert_dp_sql, batch_data)


def seed_database(points: list[shapely.geometry.Point], config_path: str,
                  game_title: str, bad_words_path: str,
                  **kwargs: typing.Any) -> None:
    """Seeds the newly generated Dashpoints into tracking tables along with a new active Game state.

    Args:
        points (list[shapely.geometry.Point]): Validated Point geometries to insert.
        config_path (str): The path to the PHP backend config.ini.
        game_title (str): Brief descriptive title of the game.
        bad_words_path (str): Path to the profanity filter blocklist.
        **kwargs: Optional overrides including 'year' (int), 'month' (int),
                  and 'is_preview' (bool) for generating inactive games.

    Raises:
        RuntimeError: If database initialization or seeding fails.
    """
    print("\nConnecting to the database to seed points...")
    try:
        with backend.scripts.db_utils.db_session(config_path) as (conn,
                                                                  cursor):
            year = kwargs.get('year')
            month = kwargs.get('month')
            is_preview = kwargs.get('is_preview')

            year_val = int(year) if year is not None else None
            month_val = int(month) if month is not None else None
            is_preview_val = bool(
                is_preview) if is_preview is not None else False

            game_id = initialize_new_game(cursor, game_title, year_val,
                                          month_val, is_preview_val)

            print(
                f"Bulk inserting {len(points)} Dashpoints for Game ID format GD{game_id:03d}..."
            )
            bulk_insert_dashpoints(cursor, points, game_id, bad_words_path)

            conn.commit()
            print("Database seeding completed successfully!")

    except Exception as e:
        raise RuntimeError(f"Failed to seed database: {e}") from e


def generate_spherical_points(num_points: int) -> list[shapely.geometry.Point]:
    """Generates random global coordinates with equal geographic density.

    Args:
        num_points (int): The number of raw points to generate.

    Returns:
        list[shapely.geometry.Point]: A list of Shapely Point objects in WGS84 coordinates.
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
    grid_boxes: list[shapely.geometry.Polygon] = []
    for i in range(len(x_coords) - 1):
        for j in range(len(y_coords) - 1):
            grid_boxes.append(
                shapely.geometry.box(x_coords[i], y_coords[j], x_coords[i + 1],
                                     y_coords[j + 1]))

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


def resolve_lake_zip_paths(lakes_zip_path: str) -> list[str]:
    """Resolves lake shapefile paths, expanding default ne_10m_lakes.zip with supplements."""
    if os.path.basename(lakes_zip_path) == 'ne_10m_lakes.zip':
        base_dir = os.path.dirname(lakes_zip_path)
        return [lakes_zip_path] + [
            os.path.join(base_dir, name) for name in LAKE_SUPPLEMENT_FILENAMES
        ]
    return [lakes_zip_path]


def _load_and_project_geometries(
        land_zip_path: str,
        lakes_zip_path: str,
        verbose: bool = True) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Loads and projects the land and lake shapefiles to EPSG:6933."""
    lake_paths = resolve_lake_zip_paths(lakes_zip_path)
    try:
        land_gdf = gpd.read_file(f"zip://{land_zip_path}")
        lake_gdfs = [gpd.read_file(f"zip://{path}") for path in lake_paths]
    except Exception as e:
        raise FileNotFoundError(f"Failed to read shapefiles: {e}") from e

    if verbose:
        print("Projecting land and lakes geometries to EPSG:6933...")
    land_proj = gpd.GeoDataFrame(
        geometry=land_gdf.to_crs(epsg=6933).geometry.make_valid(),
        crs="EPSG:6933")
    lake_geoms: list[shapely.geometry.base.BaseGeometry] = []
    for gdf in lake_gdfs:
        valid_series = gdf.to_crs(epsg=6933).geometry.make_valid()
        lake_geoms.extend(valid_series.tolist())
    lakes_proj = gpd.GeoDataFrame(geometry=lake_geoms, crs="EPSG:6933")
    return land_proj, lakes_proj


class SpatialFilter:
    """Helper class to encapsulate spatial indexing and boundary filtering logic."""

    def __init__(self, tree_land: shapely.strtree.STRtree,
                 tree_lakes: shapely.strtree.STRtree,
                 land_sub: list[shapely.geometry.base.BaseGeometry],
                 lakes_sub: list[shapely.geometry.base.BaseGeometry]) -> None:
        """Initializes spatial trees and subdivided geometry lists."""
        self.tree_land = tree_land
        self.tree_lakes = tree_lakes
        self.land_sub = land_sub
        self.lakes_sub = lakes_sub

    def get_candidate_matches(
        self, buffers: typing.Any
    ) -> tuple[dict[int, list[shapely.geometry.base.BaseGeometry]], dict[
            int, list[shapely.geometry.base.BaseGeometry]]]:
        """Finds matching land and lake geometries for each buffered point."""
        land_matches = self.tree_land.query(buffers)
        land_map: dict[int, list[shapely.geometry.base.BaseGeometry]] = {}
        if land_matches.size > 0:
            for buf_idx, land_idx in zip(land_matches[0], land_matches[1]):
                land_map.setdefault(buf_idx,
                                    []).append(self.land_sub[land_idx])

        lake_matches = self.tree_lakes.query(buffers)
        lake_map: dict[int, list[shapely.geometry.base.BaseGeometry]] = {}
        if lake_matches.size > 0:
            for buf_idx, lake_idx in zip(lake_matches[0], lake_matches[1]):
                lake_map.setdefault(buf_idx,
                                    []).append(self.lakes_sub[lake_idx])

        return land_map, lake_map

    def eval_boundary_point(
            self, buffer_geom: shapely.geometry.base.BaseGeometry,
            matching_lands: list[shapely.geometry.base.BaseGeometry],
            matching_lakes: list[shapely.geometry.base.BaseGeometry]) -> bool:
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

    def _filter_batch_indices(
            self, batch_points: list[shapely.geometry.Point]) -> set[int]:
        """Filters a single batch of points and returns the valid local indices."""
        proj_geoms = gpd.GeoDataFrame(
            geometry=batch_points,
            crs="EPSG:4326").to_crs(epsg=6933).geometry.tolist()

        land_contains = self.tree_land.query(proj_geoms, predicate="contains")
        on_land = set(land_contains[0])
        lake_contains = self.tree_lakes.query(proj_geoms, predicate="contains")
        in_lakes = set(lake_contains[0])

        valid = on_land - in_lakes
        remaining = [i for i in range(len(batch_points)) if i not in valid]
        if remaining:
            remaining_buffers = shapely.buffer(
                [proj_geoms[i] for i in remaining], 100)
            land_map, lake_map = self.get_candidate_matches(remaining_buffers)
            for buf_idx, lands in land_map.items():
                if self.eval_boundary_point(remaining_buffers[buf_idx], lands,
                                            lake_map.get(buf_idx, [])):
                    valid.add(remaining[buf_idx])

        return valid

    def filter_valid_indices(
            self, raw_points: list[shapely.geometry.Point]) -> set[int]:
        """Identifies indices of points situated on dry land or within 100m offshore."""
        if not raw_points:
            return set()

        batch_size = 50000
        valid_indices: set[int] = set()
        for offset in range(0, len(raw_points), batch_size):
            batch = raw_points[offset:offset + batch_size]
            batch_valid = self._filter_batch_indices(batch)
            valid_indices.update(offset + idx for idx in batch_valid)

        return valid_indices


def build_spatial_filter(land_zip_path: str,
                         lakes_zip_path: str,
                         verbose: bool = True) -> SpatialFilter:
    """Loads shapefiles, projects them, subdivides them, and builds the SpatialFilter."""
    land_proj, lakes_proj = _load_and_project_geometries(
        land_zip_path, lakes_zip_path, verbose)

    if verbose:
        print(
            "Subdividing land and lakes geometries to optimize spatial query performance..."
        )
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
    lakes_zip_path: str = '../../data/ne_10m_lakes.zip'
) -> list[shapely.geometry.Point]:
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
        list[shapely.geometry.Point]: A list of valid Shapely Point objects.

    Raises:
        FileNotFoundError: If the land or lake shapefiles cannot be found or read.
    """
    spatial_filter = build_spatial_filter(land_zip_path, lakes_zip_path)

    valid_points: list[shapely.geometry.Point] = []
    batch_size = 50000 if target_count > 10000 else 10000

    print("Generating valid dashpoints...")
    while len(valid_points) < target_count:
        raw_points = generate_spherical_points(batch_size)
        valid_indices = spatial_filter.filter_valid_indices(raw_points)
        valid_points.extend(raw_points[i] for i in sorted(valid_indices))

        if len(valid_points) % 1000 == 0 or len(valid_points) >= target_count:
            print(f"Generated {min(len(valid_points), target_count)} / "
                  f"{target_count} valid dashpoints...")

    return valid_points[:target_count]


def _collect_all_grid_cells(
        bands: list[LatitudeBand]) -> list[tuple[LatitudeBand, int]]:
    """Flattens all bands into a list of (band, cell_idx) coordinate cells."""
    return [(band, cell_idx) for band in bands
            for cell_idx in range(band.num_cells)]


def _place_shuffled_darts(
        darts: list[tuple[LatitudeBand, int, shapely.geometry.Point]],
        spatial_filter: SpatialFilter, neighbor_grid: SphereNeighborGrid,
        accepted_points: list[shapely.geometry.Point]) -> None:
    """Places darts in random order, retrying any 12km collisions."""
    rng = np.random.default_rng()
    for i in rng.permutation(len(darts)):
        b, c, pt = darts[i]
        placed = _find_valid_cell_point(b, c, pt, spatial_filter,
                                        neighbor_grid)
        if placed is not None:
            accepted_points.append(placed)


def _execute_pass1(
    bands: list[LatitudeBand], spatial_filter: SpatialFilter,
    neighbor_grid: SphereNeighborGrid,
    accepted_points: list[shapely.geometry.Point]
) -> list[tuple[LatitudeBand, int]]:
    """Executes Pass 1 base grid sampling, returning the cells whose initial dart hit water."""
    all_cells = _collect_all_grid_cells(bands)

    print(f"Generated {len(all_cells)} grid cells. Running Pass 1...")
    pass1_points = [sample_point_in_cell(b, c) for b, c in all_cells]
    valid_indices = spatial_filter.filter_valid_indices(pass1_points)

    water_cells: list[tuple[LatitudeBand, int]] = []
    land_darts: list[tuple[LatitudeBand, int, shapely.geometry.Point]] = []
    for idx, (b, c) in enumerate(all_cells):
        if idx in valid_indices:
            land_darts.append((b, c, pass1_points[idx]))
        else:
            water_cells.append((b, c))

    _place_shuffled_darts(land_darts, spatial_filter, neighbor_grid,
                          accepted_points)
    return water_cells


def _collect_cardinal_candidates(
    water_cells: list[tuple[LatitudeBand, int]], bands: list[LatitudeBand]
) -> list[tuple[LatitudeBand, int, shapely.geometry.Point]]:
    """Generates candidate darts in all cardinal neighbors of water cells."""
    candidates: list[tuple[LatitudeBand, int, shapely.geometry.Point]] = []
    for b, c in water_cells:
        for nb_band_idx, nb_cell_idx in get_cardinal_neighbors(b, c, bands):
            nb_band = bands[nb_band_idx]
            cand = sample_point_in_cell(nb_band, nb_cell_idx)
            candidates.append((nb_band, nb_cell_idx, cand))
    return candidates


def _execute_pass2(water_cells: list[tuple[LatitudeBand, int]],
                   bands: list[LatitudeBand], spatial_filter: SpatialFilter,
                   neighbor_grid: SphereNeighborGrid,
                   accepted_points: list[shapely.geometry.Point]) -> None:
    """Executes Pass 2 non-cascading cardinal water redistribution."""
    candidates = _collect_cardinal_candidates(water_cells, bands)
    pts = [item[2] for item in candidates]
    valid_indices = spatial_filter.filter_valid_indices(pts)
    valid_darts = [candidates[i] for i in sorted(valid_indices)]
    _place_shuffled_darts(valid_darts, spatial_filter, neighbor_grid,
                          accepted_points)


def generate_grid_dashpoints(
    grid_size_km: float = DEFAULT_GRID_SIZE_KM,
    land_zip_path: str = '../../data/ne_10m_land.zip',
    lakes_zip_path: str = '../../data/ne_10m_lakes.zip'
) -> list[shapely.geometry.Point]:
    """Generates globally distributed dashpoints using a staggered spherical trapezoid grid.

    Algorithm (Two-Pass Point Darts):
        1. Tiles the globe into staggered spherical trapezoid bands of height grid_size_km.
        2. Pass 1: Samples 1 random candidate point per cell.
        3. Identifies dry-land points via SpatialFilter and inserts into SphereNeighborGrid,
           retrying up to MAX_CELL_ATTEMPTS times if a 12 km collision occurs.
        4. Pass 2: For cells whose Pass 1 point landed in water, throws 1 additional bonus dart
           in each of their 4 cardinal neighbor cells (strictly 1-hop, non-cascading).
        5. Validates Pass 2 points on dry land and inserts with the 12 km check and retry loop.

    Args:
        grid_size_km (float): Desired grid cell size in kilometers (default: 60.05).
        land_zip_path (str): Path to Natural Earth land zip file.
        lakes_zip_path (str): Path to Natural Earth lakes zip file.

    Returns:
        list[shapely.geometry.Point]: A list of accepted Point geometries.
    """
    spatial_filter = build_spatial_filter(land_zip_path, lakes_zip_path)
    bands = build_spherical_grid(grid_size_km)
    neighbor_grid = SphereNeighborGrid()
    accepted_points: list[shapely.geometry.Point] = []

    water_cells = _execute_pass1(bands, spatial_filter, neighbor_grid,
                                 accepted_points)
    print(f"Pass 1 placed {len(accepted_points)} points. "
          f"Running Pass 2 with {len(water_cells)} water cells...")

    _execute_pass2(water_cells, bands, spatial_filter, neighbor_grid,
                   accepted_points)
    print(
        f"Grid generation completed: {len(accepted_points)} total dashpoints placed."
    )

    rng = np.random.default_rng()
    rng.shuffle(accepted_points)
    return accepted_points


classify_grid_cells = backend.scripts.prepare_roads.classify_grid_cells


def _collect_road_pass2_slots(
    water_cells: list[tuple[LatitudeBand, int]],
    bands: list[LatitudeBand],
    land_cells: list[tuple[LatitudeBand, int]],
) -> tuple[list[tuple[LatitudeBand, int]], dict[tuple[int, int], int]]:
    """Identifies Pass 2 cardinal bonus slots in land neighbor cells."""
    land_cell_map = {(b.band_idx, c): b for b, c in land_cells}
    pass2_counts: dict[tuple[int, int], int] = {}
    pass2_slots: list[tuple[LatitudeBand, int]] = []
    for b, c in water_cells:
        for nb_band_idx, nb_c in get_cardinal_neighbors(b, c, bands):
            if (nb_band_idx, nb_c) in land_cell_map:
                pass2_slots.append((land_cell_map[(nb_band_idx, nb_c)], nb_c))
                pass2_counts[(nb_band_idx, nb_c)] = (pass2_counts.get(
                    (nb_band_idx, nb_c), 0) + 1)
    return pass2_slots, pass2_counts


def _run_road_placement_passes(
    land_cells: list[tuple[LatitudeBand, int]],
    pass2_data: tuple[list[tuple[LatitudeBand, int]], dict[tuple[int, int],
                                                           int]],
    ctx: backend.scripts.prepare_roads.RoadPlacementContext,
    accepted_points: list[shapely.geometry.Point],
    verbose: bool = True,
) -> None:
    """Executes Pass 1 and Pass 2 road-proximity candidate placement."""
    pass2_slots, pass2_counts = pass2_data
    if verbose:
        print(f"Running Pass 1 with {len(land_cells)} land cells...")
    backend.scripts.prepare_roads.place_shuffled_road_cells(
        land_cells, ctx, accepted_points, pass2_counts)

    if verbose:
        print(
            f"Pass 1 placed {len(accepted_points)} points. "
            f"Running Pass 2 with {len(pass2_slots)} cardinal bonus slots...")
    placed_bonus = backend.scripts.prepare_roads.place_shuffled_road_cells(
        pass2_slots, ctx, accepted_points, pass2_counts)

    if verbose:
        print(
            f"Pass 2 placed {placed_bonus} bonus points. "
            f"Total road-proximity dashpoints placed: {len(accepted_points)}")


def generate_road_proximity_dashpoints(
    grid_size_km: float = DEFAULT_GRID_SIZE_KM,
    land_zip_path: str = '../../data/ne_10m_land.zip',
    lakes_zip_path: str = '../../data/ne_10m_lakes.zip',
    roads_input: str | gpd.GeoDataFrame = (
        backend.scripts.prepare_roads.DEFAULT_ROADS_GPKG_PATH),
    verbose: bool = True,
) -> list[shapely.geometry.Point]:
    """Generates globally distributed dashpoints within 50m of drivable roads.

    Algorithm:
        1. Tiles the globe into spherical trapezoid bands using build_spherical_grid.
        2. Classifies cells into dry land cells (> 0% land) and water-only cells (0% land).
        3. Pass 1: Shuffles all land cells and attempts 1 road-proximity point per cell.
        4. Pass 2: For each water-only cell, throws 1 bonus road dart in each cardinal neighbor
           cell that contains land (strictly non-cascading).
        5. Validates candidate points on dry land and enforces 12 km minimum distance spacing.

    Args:
        grid_size_km: Desired grid cell size in kilometers.
        land_zip_path: Path to Natural Earth land zip file.
        lakes_zip_path: Path to Natural Earth lakes zip file.
        roads_input: Path to road GeoPackage or in-memory GeoDataFrame.
        verbose: Whether to log progress messages.

    Returns:
        list[shapely.geometry.Point]: A list of accepted Point geometries.
    """
    spatial_filter = build_spatial_filter(land_zip_path,
                                          lakes_zip_path,
                                          verbose=verbose)
    bands = build_spherical_grid(grid_size_km)
    neighbor_grid = SphereNeighborGrid()
    accepted_points: list[shapely.geometry.Point] = []

    if verbose:
        print("Classifying spherical grid cells into land and water...")
    land_cells, water_cells = classify_grid_cells(bands, spatial_filter)
    if verbose:
        print(f"Grid classified: {len(land_cells)} land cells, "
              f"{len(water_cells)} water-only cells.")

    pass2_data = _collect_road_pass2_slots(water_cells, bands, land_cells)

    ctx = backend.scripts.prepare_roads.RoadPlacementContext(
        roads_input=roads_input,
        spatial_filter=spatial_filter,
        neighbor_grid=neighbor_grid,
        road_bounds=backend.scripts.prepare_roads.get_roads_total_bounds(
            roads_input),
        cell_candidates={},
    )

    _run_road_placement_passes(land_cells, pass2_data, ctx, accepted_points,
                               verbose)

    rng = np.random.default_rng()
    rng.shuffle(accepted_points)
    return accepted_points


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
        help=
        "Optional month (1-12) to generate the game for (defaults to current month)"
    )
    parser.add_argument(
        '-y',
        '--year',
        type=int,
        help="Optional year to generate the game for (defaults to current year)"
    )
    parser.add_argument(
        '--preview',
        action='store_true',
        help=
        "Generate the game in an inactive preview state instead of immediately activating it"
    )
    parser.add_argument(
        '--algorithm',
        type=str,
        choices=['random', 'grid', 'road-proximity'],
        default='random',
        help=
        "Distribution algorithm: 'random', 'grid', or 'road-proximity' (default: random)"
    )
    parser.add_argument(
        '--grid-size',
        type=float,
        default=DEFAULT_GRID_SIZE_KM,
        help=
        "Cell size in km for grid or road-proximity algorithm (default: 60.05)"
    )
    parser.add_argument(
        '--roads-gpkg',
        type=str,
        default=None,
        help="Optional road GeoPackage path (default: resolved from config.ini)"
    )
    args = parser.parse_args()

    current_dir = os.path.dirname(os.path.abspath(__file__))
    zip_path = os.path.join(current_dir, '../../data/ne_10m_land.zip')
    lakes_zip = os.path.join(current_dir, '../../data/ne_10m_lakes.zip')
    config_path = os.path.join(current_dir, '../config.ini')
    bad_words_path = os.path.join(current_dir, '../../data/bad_words.txt')

    try:
        if args.algorithm == 'grid':
            print(
                f"Generating dashpoints using grid algorithm (size: {args.grid_size} km)..."
            )
            points = generate_grid_dashpoints(grid_size_km=args.grid_size,
                                              land_zip_path=zip_path,
                                              lakes_zip_path=lakes_zip)
        elif args.algorithm == 'road-proximity':
            print(f"Generating dashpoints using road-proximity algorithm "
                  f"(size: {args.grid_size} km)...")
            roads_path = backend.scripts.prepare_roads.resolve_roads_gpkg(
                args.roads_gpkg, config_path=config_path)
            points = generate_road_proximity_dashpoints(
                grid_size_km=args.grid_size,
                land_zip_path=zip_path,
                lakes_zip_path=lakes_zip,
                roads_input=roads_path)
        else:
            target = args.count
            print(f"Generating {target} dashpoints using random algorithm...")
            points = generate_valid_dashpoints(target_count=target,
                                               land_zip_path=zip_path,
                                               lakes_zip_path=lakes_zip)

        # 2. Upload to MySQL
        seed_database(points,
                      config_path,
                      args.title,
                      bad_words_path,
                      year=args.year,
                      month=args.month,
                      is_preview=args.preview)

    except (FileNotFoundError, RuntimeError, ValueError) as e:
        print(f"\nExecution Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
