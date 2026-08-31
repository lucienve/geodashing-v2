"""Tests for the Geodashing V2 point generator script."""
# pylint: disable=protected-access
# Architecturally, unit testing private helper functions (_initialize_new_game and
# _bulk_insert_dashpoints) is required to verify the correctness of individual database
# operations without executing the entire orchestrator.

import datetime
import unittest.mock
import geopandas as gpd
import mysql.connector.cursor
import pytest
import shapely.geometry

import backend.scripts.generate_game


def test_generate_spherical_points() -> None:
    """Verify coordinate bounding boxes and type generations."""
    points = backend.scripts.generate_game.generate_spherical_points(10)
    assert len(points) == 10

    for pt in points:
        assert isinstance(pt, shapely.geometry.Point)
        assert -180 <= pt.x <= 180
        assert -90 <= pt.y <= 90


def test_water_exclusion_logic() -> None:
    """Verify that the 500m buffer logic accurately intersects land.
    Uses an EPSG:6933 (Cylindrical Equal Area) mock polygon for testing.
    """
    # Create a simple 1km x 1km square 'island' at the equator
    island_geom = shapely.geometry.Polygon([(-500, -500), (500, -500),
                                            (500, 500), (-500, 500)])

    # Point 1: On the island
    p1 = shapely.geometry.Point(0, 0)
    # Point 2: 400m offshore (Valid = within 500m)
    p2 = shapely.geometry.Point(900, 0)
    # Point 3: 600m offshore (Invalid = >500m)
    p3 = shapely.geometry.Point(1100, 0)

    points_gdf = gpd.GeoDataFrame(geometry=[p1, p2, p3], crs="EPSG:6933")
    buffered_points = points_gdf.buffer(500)

    intersections = buffered_points.intersects(island_geom)

    assert bool(intersections.iloc[0]) is True  # On land
    assert bool(intersections.iloc[1]) is True  # 400m offshore
    assert bool(intersections.iloc[2]) is False  # 600m offshore


def test_inland_lake_avoidance(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Validates the geometric differencing matrix ensuring that Dashpoints
    never spawn inside Inland Lakes or Oceans.
    """
    # 1. Define strictly controlled Mock Boundaries (EPSG:4326 Degrees)
    land_polygon = shapely.geometry.box(-5, -5, 5, 5)
    lake_polygon = shapely.geometry.box(-1, -1, 1, 1)

    def read_file_side_effect(path: str) -> gpd.GeoDataFrame:
        if 'land' in path:
            return gpd.GeoDataFrame(geometry=[land_polygon], crs="EPSG:4326")
        if 'lakes' in path:
            return gpd.GeoDataFrame(geometry=[lake_polygon], crs="EPSG:4326")
        return gpd.GeoDataFrame()

    monkeypatch.setattr('backend.scripts.generate_game.gpd.read_file',
                        read_file_side_effect)

    # 2. Inject target coordinates dynamically representing the random generator logic
    test_points = [
        shapely.geometry.Point(
            0, 0),  # Target 1: Dead center of the Lake (Should be EXCLUDED)
        shapely.geometry.Point(
            3, 3),  # Target 2: Dry Land away from water (Should be KEPT)
        shapely.geometry.Point(
            10,
            10)  # Target 3: Remote Ocean outside island (Should be EXCLUDED)
    ]

    monkeypatch.setattr(
        'backend.scripts.generate_game.generate_spherical_points',
        lambda *args, **kwargs: test_points)

    # 3. Execute the Geopandas Mathematics constraint engine
    valid_points = backend.scripts.generate_game.generate_valid_dashpoints(
        target_count=1,
        land_zip_path="mock_land.zip",
        lakes_zip_path="mock_lakes.zip")

    # 4. Assert geometric success array.
    assert len(valid_points) == 1, "Exactly one Dashpoint should exist."
    assert valid_points[0].x == 3.0, "Point X did not match land bounds"
    assert valid_points[0].y == 3.0, "Point Y did not match land bounds"


def test_int_to_letters() -> None:
    """Verify numeric to alphabetic sequence generation."""
    assert backend.scripts.generate_game.int_to_letters(0) == "AAAA"
    assert backend.scripts.generate_game.int_to_letters(1) == "AAAB"
    assert backend.scripts.generate_game.int_to_letters(25) == "AAAZ"
    assert backend.scripts.generate_game.int_to_letters(26) == "AABA"
    assert backend.scripts.generate_game.int_to_letters(27) == "AABB"


def test_initialize_new_game() -> None:
    """Verify that starting a new game successfully updates the DB state."""
    mock_cursor = unittest.mock.MagicMock(
        spec=mysql.connector.cursor.MySQLCursor)
    mock_cursor.lastrowid = 42
    mock_cursor.fetchone.return_value = None

    game_id = backend.scripts.generate_game.initialize_new_game(
        mock_cursor, "Global Dash")

    assert game_id == 42
    # Verify the initial duplicate check and retirement of old games ran
    mock_cursor.execute.assert_any_call(
        "SELECT id, title FROM games WHERE YEAR(start_time) = %s AND MONTH(start_time) = %s",
        (datetime.datetime.now().year, datetime.datetime.now().month))
    mock_cursor.execute.assert_any_call("UPDATE games SET is_active = FALSE")

    # Verify the parameter-bound database insert
    assert mock_cursor.execute.call_count == 3
    args = mock_cursor.execute.call_args_list[2][0]
    query = args[0]
    payload = args[1]

    assert "INSERT INTO games" in query
    assert payload[0] == "Global Dash"


def test_initialize_new_game_duplicate_blocked() -> None:
    """Verify that creating a duplicate game for the same month raises ValueError."""
    mock_cursor = unittest.mock.MagicMock(
        spec=mysql.connector.cursor.MySQLCursor)
    mock_cursor.fetchone.return_value = (10, "Existing Game")

    with pytest.raises(ValueError, match="already exists"):
        backend.scripts.generate_game.initialize_new_game(
            mock_cursor, "Duplicate Dash")


def test_bulk_insert_dashpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that multiple generated points are chunked and executed properly."""
    # Mock away blocklist reading logic
    monkeypatch.setattr('backend.scripts.generate_game.load_blocklist',
                        lambda path: set())

    mock_cursor = unittest.mock.MagicMock(
        spec=mysql.connector.cursor.MySQLCursor)
    points = [shapely.geometry.Point(10, 20), shapely.geometry.Point(-30, 40)]

    backend.scripts.generate_game._bulk_insert_dashpoints(
        mock_cursor, points, game_id=7, bad_words_path="mock/path")

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
