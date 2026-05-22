"""Tests for the Geodashing V2 point generator script."""

from unittest.mock import MagicMock

import geopandas as gpd
import mysql.connector.cursor
from shapely.geometry import Point, Polygon, box

from backend.scripts.generate_game import (_bulk_insert_dashpoints,
                                           _initialize_new_game,
                                           generate_spherical_points,
                                           generate_valid_dashpoints,
                                           int_to_letters)


def test_generate_spherical_points():
    """Verify coordinate bounding boxes and type generations."""
    points = generate_spherical_points(10)
    assert len(points) == 10

    for pt in points:
        assert isinstance(pt, Point)
        assert -180 <= pt.x <= 180
        assert -90 <= pt.y <= 90


def test_water_exclusion_logic():
    """Verify that the 500m buffer logic accurately intersects land.
    Uses an EPSG:6933 (Cylindrical Equal Area) mock polygon for testing.
    """
    # Create a simple 1km x 1km square 'island' at the equator
    island_geom = Polygon([(-500, -500), (500, -500), (500, 500), (-500, 500)])

    # Point 1: On the island
    p1 = Point(0, 0)
    # Point 2: 400m offshore (Valid = within 500m)
    p2 = Point(900, 0)
    # Point 3: 600m offshore (Invalid = >500m)
    p3 = Point(1100, 0)

    points_gdf = gpd.GeoDataFrame(geometry=[p1, p2, p3], crs="EPSG:6933")
    buffered_points = points_gdf.buffer(500)

    intersections = buffered_points.intersects(island_geom)

    assert bool(intersections.iloc[0]) is True  # On land
    assert bool(intersections.iloc[1]) is True  # 400m offshore
    assert bool(intersections.iloc[2]) is False  # 600m offshore


def test_inland_lake_avoidance(monkeypatch):
    """
    Validates the geometric differencing matrix ensuring that Dashpoints
    never spawn inside Inland Lakes or Oceans.
    """
    # 1. Define strictly controlled Mock Boundaries (EPSG:4326 Degrees)
    land_polygon = box(-5, -5, 5, 5)
    lake_polygon = box(-1, -1, 1, 1)

    def read_file_side_effect(path):
        if 'land' in path:
            return gpd.GeoDataFrame(geometry=[land_polygon], crs="EPSG:4326")
        if 'lakes' in path:
            return gpd.GeoDataFrame(geometry=[lake_polygon], crs="EPSG:4326")
        return gpd.GeoDataFrame()

    monkeypatch.setattr('backend.scripts.generate_game.gpd.read_file',
                        read_file_side_effect)

    # 2. Inject target coordinates dynamically representing the random generator logic
    test_points = [
        Point(0, 0),  # Target 1: Dead center of the Lake (Should be EXCLUDED)
        Point(3, 3),  # Target 2: Dry Land away from water (Should be KEPT)
        Point(10,
              10)  # Target 3: Remote Ocean outside island (Should be EXCLUDED)
    ]

    monkeypatch.setattr(
        'backend.scripts.generate_game.generate_spherical_points',
        lambda *args, **kwargs: test_points)

    # 3. Execute the Geopandas Mathematics constraint engine
    valid_points = generate_valid_dashpoints(target_count=1,
                                             land_zip_path="mock_land.zip",
                                             lakes_zip_path="mock_lakes.zip")

    # 4. Assert geometric success array.
    assert len(valid_points) == 1, "Exactly one Dashpoint should exist."
    assert valid_points[0].x == 3.0, "Point X did not match land bounds"
    assert valid_points[0].y == 3.0, "Point Y did not match land bounds"


def test_int_to_letters():
    """Verify numeric to alphabetic sequence generation."""
    assert int_to_letters(0) == "AAAA"
    assert int_to_letters(1) == "AAAB"
    assert int_to_letters(25) == "AAAZ"
    assert int_to_letters(26) == "AABA"
    assert int_to_letters(27) == "AABB"


def test_initialize_new_game():
    """Verify that starting a new game successfully updates the DB state."""
    mock_cursor = MagicMock(spec=mysql.connector.cursor.MySQLCursor)
    mock_cursor.lastrowid = 42

    game_id = _initialize_new_game(mock_cursor, "Global Dash")

    assert game_id == 42
    # Verify the initial retirement of old games ran
    mock_cursor.execute.assert_any_call("UPDATE games SET is_active = FALSE")

    # Verify the parameter-bound database insert
    assert mock_cursor.execute.call_count == 2
    args = mock_cursor.execute.call_args_list[1][0]
    query = args[0]
    payload = args[1]

    assert "INSERT INTO games" in query
    assert payload[0] == "Global Dash"


def test_bulk_insert_dashpoints(monkeypatch):
    """Verify that multiple generated points are chunked and executed properly."""
    # Mock away blocklist reading logic
    monkeypatch.setattr('backend.scripts.generate_game.load_blocklist',
                        lambda path: set())

    mock_cursor = MagicMock(spec=mysql.connector.cursor.MySQLCursor)
    points = [Point(10, 20), Point(-30, 40)]

    _bulk_insert_dashpoints(mock_cursor,
                            points,
                            game_id=7,
                            bad_words_path="mock/path")

    assert mock_cursor.executemany.call_count == 1
    args = mock_cursor.executemany.call_args[0]

    query = args[0]
    batch_data = args[1]

    assert "INSERT INTO dashpoints" in query
    assert len(batch_data) == 2

    # Validate correct param formatting including POINT(lat lon) strictness
    assert batch_data[0][0] == "GD007-AAAA"
    assert batch_data[0][1] == 7
    assert batch_data[0][2] == "POINT(20.0 10.0)"

    assert batch_data[1][0] == "GD007-AAAB"
    assert batch_data[1][1] == 7
    assert batch_data[1][2] == "POINT(40.0 -30.0)"
