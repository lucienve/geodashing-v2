"""Tests for the Geodashing V2 point generator script."""

import geopandas as gpd
from shapely.geometry import Point, Polygon, box

from backend.scripts.generate_game import (generate_spherical_points,
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
    Validates the geometric differencing matrix natively ensuring that Dashpoints
    never mathematically spawn inside Inland Lakes or Oceans.
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
