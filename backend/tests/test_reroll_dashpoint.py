"""Unit tests for the backend reroll_dashpoint spatial module."""

import math
import os

import pytest

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


def test_is_valid_land_point() -> None:
    """Verifies single coordinate evaluation against land spatial filter."""
    land_zip = "data/ne_10m_land.zip"
    lakes_zip = "data/ne_10m_lakes.zip"

    if not os.path.exists(land_zip):
        pytest.fail(f"Required land shapefile not found at {land_zip}")
    if not os.path.exists(lakes_zip):
        pytest.fail(f"Required lakes shapefile not found at {lakes_zip}")

    spatial_filter = backend.scripts.generate_game.build_spatial_filter(land_zip, lakes_zip)
    # London (51.5074, -0.1278) is dry land
    is_valid = backend.scripts.reroll_dashpoint.is_valid_land_point(
        51.5074, -0.1278, spatial_filter
    )
    assert is_valid is True


def test_find_valid_reroll_point() -> None:
    """Verifies valid reroll point selection on dry land using actual shapefiles."""
    land_zip = "data/ne_10m_land.zip"
    lakes_zip = "data/ne_10m_lakes.zip"

    if not os.path.exists(land_zip):
        pytest.fail(f"Required land shapefile not found at {land_zip}")
    if not os.path.exists(lakes_zip):
        pytest.fail(f"Required lakes shapefile not found at {lakes_zip}")

    # London origin (51.5074, -0.1278)
    origin = (51.5074, -0.1278)
    max_radius_km = 10.0

    spatial_filter = backend.scripts.generate_game.build_spatial_filter(land_zip, lakes_zip)
    new_lat, new_lon = backend.scripts.reroll_dashpoint.find_valid_reroll_point(
        origin, max_radius_km, spatial_filter
    )


    # Verify distance constraint
    dist = backend.scripts.reroll_dashpoint.haversine_distance_km(
        origin[0], origin[1], new_lat, new_lon
    )
    assert 0.1 <= dist <= max_radius_km
