import pytest
import os
import geopandas as gpd
from shapely.geometry import Point, Polygon
from backend.scripts.generate_game import generate_spherical_points

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
    
    assert intersections.iloc[0] == True   # On land
    assert intersections.iloc[1] == True   # 400m offshore
    assert intersections.iloc[2] == False  # 600m offshore
