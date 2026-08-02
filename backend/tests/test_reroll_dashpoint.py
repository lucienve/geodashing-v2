"""Unit tests for the backend reroll_dashpoint spatial module."""

import math

import geopandas as gpd
import pytest
import shapely.geometry

import backend.scripts.generate_game
import backend.scripts.reroll_dashpoint


def test_haversine_distance_km() -> None:
    """Verifies Great Circle distance calculations using known landmarks."""
    # Distance between London (51.5074, -0.1278) and Paris (48.8566, 2.3522) is approx 343 km
    dist = backend.scripts.reroll_dashpoint.haversine_distance_km(
        51.5074, -0.1278, 48.8566, 2.3522
    )
    assert 330.0 < dist < 360.0

    # Same point distance should be 0.0
    zero_dist = backend.scripts.reroll_dashpoint.haversine_distance_km(
        40.7128, -74.0060, 40.7128, -74.0060
    )
    assert math.isclose(zero_dist, 0.0, abs_tol=1e-5)



def test_is_valid_land_point(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies single coordinate evaluation against land spatial filter."""
    land_polygon = shapely.geometry.box(-2.0, 50.0, 2.0, 53.0)
    lake_polygon = shapely.geometry.box(0.5, 51.0, 1.0, 52.0)

    def read_file_side_effect(path: str) -> gpd.GeoDataFrame:
        if "land" in path:
            return gpd.GeoDataFrame(geometry=[land_polygon], crs="EPSG:4326")
        if "lakes" in path:
            return gpd.GeoDataFrame(geometry=[lake_polygon], crs="EPSG:4326")
        return gpd.GeoDataFrame()

    monkeypatch.setattr(
        "backend.scripts.generate_game.gpd.read_file", read_file_side_effect
    )

    spatial_filter = backend.scripts.generate_game.build_spatial_filter(
        "mock_land.zip", "mock_lakes.zip", verbose=False
    )
    # London (51.5074, -0.1278) is dry land
    is_valid = backend.scripts.reroll_dashpoint.is_valid_land_point(
        51.5074, -0.1278, spatial_filter
    )
    assert is_valid is True


def test_find_valid_reroll_point(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies valid reroll point selection on dry land using mock shapefiles."""
    land_polygon = shapely.geometry.box(-2.0, 50.0, 2.0, 53.0)
    lake_polygon = shapely.geometry.box(0.5, 51.0, 1.0, 52.0)

    def read_file_side_effect(path: str) -> gpd.GeoDataFrame:
        if "land" in path:
            return gpd.GeoDataFrame(geometry=[land_polygon], crs="EPSG:4326")
        if "lakes" in path:
            return gpd.GeoDataFrame(geometry=[lake_polygon], crs="EPSG:4326")
        return gpd.GeoDataFrame()

    monkeypatch.setattr(
        "backend.scripts.generate_game.gpd.read_file", read_file_side_effect
    )

    # London origin (51.5074, -0.1278)
    origin = (51.5074, -0.1278)
    max_radius_km = 10.0

    spatial_filter = backend.scripts.generate_game.build_spatial_filter(
        "mock_land.zip", "mock_lakes.zip", verbose=False
    )
    new_lat, new_lon = backend.scripts.reroll_dashpoint.find_valid_reroll_point(
        origin, max_radius_km, spatial_filter
    )
    # Verify distance constraint
    dist = backend.scripts.reroll_dashpoint.haversine_distance_km(
        origin[0], origin[1], new_lat, new_lon
    )
    assert 0.1 <= dist <= max_radius_km
