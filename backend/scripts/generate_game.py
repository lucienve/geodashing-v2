import os
import numpy as np
import geopandas as gpd
from shapely.geometry import Point
from typing import List

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

def generate_valid_dashpoints(target_count: int = 31000, land_zip_path: str = '../../data/ne_10m_land.zip') -> List[Point]:
    """Generates valid dashpoints ensuring they are on land or <= 500m offshore.
    
    Algorithm:
        1. Generates random global spherical coordinates.
        2. Projects the raw points and the core landmass polygons to a Cylindrical Equal-Area CRS (EPSG:6933) to enable precise 2D metric measurements.
        3. Buffers our simple points by a 500m radius. This is a CPU optimization trick: buffering thousands of simple dots is vastly faster than buffering the entire global coastline.
        4. Filters for points whose 500m radius geometrically intersects the land polygon.

    Args:
        target_count (int): The number of valid points to generate.
        land_zip_path (str): The relative or absolute path to the Natural Earth land zip file.

    Returns:
        List[Point]: A list of valid Shapely Point objects.
        
    Raises:
        FileNotFoundError: If the land shapefile cannot be found or read.
    """
    try:
        land_gdf = gpd.read_file(f"zip://{land_zip_path}")
    except Exception as e:
        raise FileNotFoundError(f"Failed to read shapefile from {land_zip_path}: {e}")

    # We reproject the land to EPSG:6933 (Cylindrical Equal Area) which uses METERS instead of Degrees.
    # This is crucial so we can accurately measure 500 meters everywhere on earth.
    print("Projecting land geometries to equal-area projection for accurate meter math...")
    land_proj = land_gdf.to_crs(epsg=6933)
    
    # We will combine all land polygons into a single geometric tree for fast searches
    land_geometry = land_proj.geometry.union_all()
    
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
    
    try:
        # Test run the engine
        points = generate_valid_dashpoints(target_count=31000, land_zip_path=zip_path)
        
        # Just show a preview to prove it worked
        print("\nPreview of first 5 Dashpoints:")
        for i in range(5):
            print(f" Lat: {points[i].y:.6f}, Lon: {points[i].x:.6f}")
            
        # Export 50 points to a CSV file for Google Maps/Earth verification
        import pandas as pd
        sample50 = points[:50]
        df = pd.DataFrame({'Latitude': [p.y for p in sample50], 'Longitude': [p.x for p in sample50]})
        df.to_csv('sample_map_points.csv', index=False)
        print("\nSuccessfully exported 'sample_map_points.csv'. You can import this directly into Google My Maps or Google Earth to visually verify the 500m rule!")
    except Exception as e:
        print(f"Execution Error: {e}")
