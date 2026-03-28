import unittest
from unittest.mock import patch
from shapely.geometry import Point, box
import geopandas as gpd
from generate_game import generate_valid_dashpoints

class TestGenerateGame(unittest.TestCase):
    
    @patch('generate_game.gpd.read_file')
    @patch('generate_game.generate_spherical_points')
    def test_inland_lake_avoidance(self, mock_generate_points, mock_read_file):
        """
        Validates the geometric differencing matrix natively ensuring that Dashpoints
        never mathematically spawn inside Inland Lakes or Oceans.
        """
        # 1. Define strictly controlled Mock Boundaries (EPSG:4326 Degrees)
        # Landmass: A giant 10x10 degree synthetic island centered at the equator (0,0)
        land_polygon = box(-5, -5, 5, 5) 
        
        # Lake: A 2x2 degree synthetic lake punched exactly into the center of the island
        lake_polygon = box(-1, -1, 1, 1) 
        
        # Intercept the gpd.read_file method binding our memory synthetic polygons instead of HD shapefiles 
        def read_file_side_effect(path):
            if 'land' in path:
                return gpd.GeoDataFrame(geometry=[land_polygon], crs="EPSG:4326")
            elif 'lakes' in path:
                return gpd.GeoDataFrame(geometry=[lake_polygon], crs="EPSG:4326")
            return gpd.GeoDataFrame()
            
        mock_read_file.side_effect = read_file_side_effect
        
        # 2. Inject target coordinates dynamically representing the random generator logic
        test_points = [
            Point(0, 0),    # Target 1: Dead center of the Lake (Should be EXCLUDED)
            Point(3, 3),    # Target 2: Dry Land away from water (Should be KEPT)
            Point(10, 10)   # Target 3: Remote Ocean outside island (Should be EXCLUDED)
        ]
        
        # Bind the mock array back into the core while loop natively
        mock_generate_points.return_value = test_points
        
        # 3. Execute the Geopandas Mathematics constraint engine
        # We specify a target of exactly 1 valid point to break the while-loop instantly!
        valid_points = generate_valid_dashpoints(
            target_count=1, 
            land_zip_path="mock_land.zip", 
            lakes_zip_path="mock_lakes.zip"
        )
        
        # 4. Assert Geometric Success Array!
        self.assertEqual(len(valid_points), 1, "Exactly one Dashpoint should mathematically survive the geometric hole-punch phase!")
        
        # Target 2 (3,3) should be the sole mathematical survivor natively.
        self.assertEqual(valid_points[0].x, 3.0, "Point X did not strictly match land target bounds!")
        self.assertEqual(valid_points[0].y, 3.0, "Point Y did not strictly match land target bounds!")

if __name__ == '__main__':
    unittest.main()
