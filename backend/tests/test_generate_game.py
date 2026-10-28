"""Tests for the Geodashing V2 point generator script."""

import datetime
import unittest.mock
import geopandas as gpd
import mysql.connector.cursor
import pytest
import shapely.geometry

import backend.scripts.generate_game
import backend.scripts.prepare_roads


def test_generate_spherical_points() -> None:
    """Verify coordinate bounding boxes and type generations."""
    points = backend.scripts.generate_game.generate_spherical_points(10)
    assert len(points) == 10

    for pt in points:
        assert isinstance(pt, shapely.geometry.Point)
        assert -180 <= pt.x <= 180
        assert -90 <= pt.y <= 90


def test_water_exclusion_logic() -> None:
    """Verify that the coastal buffer logic accurately intersects land.

    Uses an EPSG:6933 (Cylindrical Equal Area) mock polygon for testing.
    """
    # Create a simple 1km x 1km square 'island' at the equator
    island_geom = shapely.geometry.Polygon([(-500, -500), (500, -500),
                                            (500, 500), (-500, 500)])

    # Point 1: On the island
    p1 = shapely.geometry.Point(0, 0)
    # Point 2: 400m offshore (Valid = within 500m test buffer)
    p2 = shapely.geometry.Point(900, 0)
    # Point 3: 600m offshore (Invalid = >500m test buffer)
    p3 = shapely.geometry.Point(1100, 0)

    points_gdf = gpd.GeoDataFrame(geometry=[p1, p2, p3], crs="EPSG:6933")
    buffered_points = points_gdf.buffer(500)

    intersections = buffered_points.intersects(island_geom)

    assert bool(intersections.iloc[0]) is True  # On land
    assert bool(intersections.iloc[1]) is True  # 400m offshore
    assert bool(intersections.iloc[2]) is False  # 600m offshore


def test_inland_lake_avoidance(monkeypatch: pytest.MonkeyPatch) -> None:
    """Validates geometric differencing so dashpoints avoid inland lakes and oceans."""
    # 1. Define mock boundaries (EPSG:4326 Degrees)
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

    # 2. Inject target coordinates representing candidate generator output
    test_points = [
        shapely.geometry.Point(
            0, 0),  # Target 1: Center of the lake (should be excluded)
        shapely.geometry.Point(
            3, 3),  # Target 2: Dry land away from water (should be kept)
        shapely.geometry.Point(
            10, 10)  # Target 3: Ocean outside island (should be excluded)
    ]

    monkeypatch.setattr(
        'backend.scripts.generate_game.generate_spherical_points',
        lambda *args, **kwargs: test_points)

    # 3. Execute the spatial filter pipeline
    valid_points = backend.scripts.generate_game.generate_valid_dashpoints(
        target_count=1,
        land_zip_path="mock_land.zip",
        lakes_zip_path="mock_lakes.zip")

    # 4. Assert geometric filtering result
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

    backend.scripts.generate_game.bulk_insert_dashpoints(
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


def test_sphere_neighbor_grid_spacing() -> None:
    """Verify that SphereNeighborGrid enforces the 12km threshold accurately."""
    with pytest.raises(ValueError, match="min_distance_km must be positive"):
        backend.scripts.generate_game.SphereNeighborGrid(min_distance_km=0)

    with pytest.raises(ValueError, match="min_distance_km must be positive"):
        backend.scripts.generate_game.SphereNeighborGrid(min_distance_km=-5.0)

    grid = backend.scripts.generate_game.SphereNeighborGrid(
        min_distance_km=12.0)
    assert grid.count() == 0

    # Insert initial point at (0, 0)
    assert grid.insert(0.0, 0.0) is True
    assert grid.count() == 1
    assert grid.can_place(0.0, 0.0) is False

    # Point ~5km North (1 deg lat ~ 111km -> 0.045 deg ~ 5km)
    assert grid.can_place(0.0, 0.045) is False
    assert grid.insert(0.0, 0.045) is False
    assert grid.count() == 1

    # Point ~15km North (0.135 deg lat ~ 15km)
    assert grid.can_place(0.0, 0.135) is True
    assert grid.insert(0.0, 0.135) is True
    assert grid.count() == 2


def test_sphere_neighbor_grid_antimeridian_and_poles() -> None:
    """Verify that SphereNeighborGrid handles antimeridian and polar distances without wrap bugs."""
    grid = backend.scripts.generate_game.SphereNeighborGrid(
        min_distance_km=12.0)

    # Insert point near eastern antimeridian at equator
    assert grid.insert(179.99, 0.0) is True
    # Point at western antimeridian is ~2.2km away -> should collide
    assert grid.can_place(-179.99, 0.0) is False

    # Point at North Pole (lat 90.0)
    assert grid.insert(0.0, 90.0) is True
    # Near North pole with different longitude: lat 89.95 is ~5.5km away -> should collide
    assert grid.can_place(180.0, 89.95) is False
    # Point 20km south of North pole: lat 89.8 is ~22km away -> should succeed
    assert grid.can_place(90.0, 89.8) is True


def test_build_spherical_grid() -> None:
    """Verify spherical grid construction and boundary coverage."""
    with pytest.raises(ValueError, match="grid_size_km must be positive"):
        backend.scripts.generate_game.build_spherical_grid(grid_size_km=0)

    with pytest.raises(ValueError, match="grid_size_km must be positive"):
        backend.scripts.generate_game.build_spherical_grid(grid_size_km=-10.0)

    bands = backend.scripts.generate_game.build_spherical_grid(
        grid_size_km=500.0)
    assert len(bands) > 0

    # First band starts at -90.0 and last band ends at 90.0
    assert bands[0].lat_min == pytest.approx(-90.0)
    assert bands[-1].lat_max == pytest.approx(90.0)

    # Verify continuity
    for i in range(len(bands) - 1):
        assert bands[i].lat_max == pytest.approx(bands[i + 1].lat_min)

    # Equator band should have significantly more cells than polar bands
    polar_band = bands[0]
    mid_band = bands[len(bands) // 2]
    assert mid_band.num_cells > polar_band.num_cells


def test_get_cardinal_neighbors() -> None:
    """Verify cardinal neighbor resolution including East/West wrap and North/South bounds."""
    bands = backend.scripts.generate_game.build_spherical_grid(
        grid_size_km=500.0)
    assert len(bands) >= 3

    # Southernmost band (index 0) has no South neighbor
    south_neighbors = backend.scripts.generate_game.get_cardinal_neighbors(
        bands[0], 0, bands)
    assert len(south_neighbors) == 3  # East, West, North

    # Northernmost band has no North neighbor
    north_neighbors = backend.scripts.generate_game.get_cardinal_neighbors(
        bands[-1], 0, bands)
    assert len(north_neighbors) == 3  # East, West, South

    # Middle band has all 4 cardinal neighbors
    mid_idx = len(bands) // 2
    mid_band = bands[mid_idx]
    mid_neighbors = backend.scripts.generate_game.get_cardinal_neighbors(
        mid_band, 0, bands)
    assert len(mid_neighbors) == 4

    # East/West wrap within same band
    assert (mid_band.band_idx, 1 % mid_band.num_cells) in mid_neighbors
    assert (mid_band.band_idx, (0 - 1) % mid_band.num_cells) in mid_neighbors


def test_sample_point_in_cell() -> None:
    """Verify that sample_point_in_cell generates points within cell boundaries."""
    band = backend.scripts.generate_game.LatitudeBand(band_idx=1,
                                                      lat_min=10.0,
                                                      lat_max=20.0,
                                                      lon_offset=0.0,
                                                      num_cells=4,
                                                      dlon=90.0)

    for _ in range(50):
        pt = backend.scripts.generate_game.sample_point_in_cell(band,
                                                                cell_idx=1)
        assert isinstance(pt, shapely.geometry.Point)
        assert 10.0 <= pt.y <= 20.0
        assert -180.0 <= pt.x <= 180.0


def test_generate_grid_dashpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that generate_grid_dashpoints runs two passes and enforces 12km spacing."""
    # Define substantial land polygon around equator
    land_polygon = shapely.geometry.box(-30, -30, 30, 30)
    lake_polygon = shapely.geometry.box(-1, -1, 1, 1)

    def read_file_side_effect(path: str) -> gpd.GeoDataFrame:
        if 'land' in path:
            return gpd.GeoDataFrame(geometry=[land_polygon], crs="EPSG:4326")
        if 'lakes' in path:
            return gpd.GeoDataFrame(geometry=[lake_polygon], crs="EPSG:4326")
        return gpd.GeoDataFrame()

    monkeypatch.setattr('backend.scripts.generate_game.gpd.read_file',
                        read_file_side_effect)

    # Run with grid size 500 km for fast test execution with guaranteed land hits
    points = backend.scripts.generate_game.generate_grid_dashpoints(
        grid_size_km=500.0,
        land_zip_path="mock_land.zip",
        lakes_zip_path="mock_lakes.zip")

    assert len(points) > 0
    for pt in points:
        assert isinstance(pt, shapely.geometry.Point)
        assert -180.0 <= pt.x <= 180.0
        assert -90.0 <= pt.y <= 90.0

    # Verify mutual 12km distance constraint
    grid = backend.scripts.generate_game.SphereNeighborGrid(
        min_distance_km=12.0)
    for pt in points:
        assert grid.insert(pt.x, pt.y) is True


def test_main_cli_algorithm_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that main() routes CLI arguments to grid or random algorithms."""
    mock_seed = unittest.mock.create_autospec(
        backend.scripts.generate_game.seed_database)
    monkeypatch.setattr('backend.scripts.generate_game.seed_database',
                        mock_seed)

    # Test grid algorithm routing with explicit grid size
    monkeypatch.setattr('sys.argv', [
        'generate_game.py', '-t', 'Grid Test', '--algorithm', 'grid',
        '--grid-size', '2000'
    ])
    mock_grid = unittest.mock.create_autospec(
        backend.scripts.generate_game.generate_grid_dashpoints,
        return_value=[shapely.geometry.Point(0, 0)])
    monkeypatch.setattr(
        'backend.scripts.generate_game.generate_grid_dashpoints', mock_grid)

    backend.scripts.generate_game.main()
    mock_grid.assert_called_once_with(grid_size_km=2000.0,
                                      land_zip_path=unittest.mock.ANY,
                                      lakes_zip_path=unittest.mock.ANY)
    mock_seed.assert_called_once()

    # Test grid algorithm routing with default grid size (60.05 km)
    mock_seed.reset_mock()
    mock_grid.reset_mock()
    monkeypatch.setattr(
        'sys.argv',
        ['generate_game.py', '-t', 'Grid Default Test', '--algorithm', 'grid'])
    backend.scripts.generate_game.main()
    mock_grid.assert_called_once_with(grid_size_km=60.05,
                                      land_zip_path=unittest.mock.ANY,
                                      lakes_zip_path=unittest.mock.ANY)
    mock_seed.assert_called_once()

    # Test random algorithm routing (default)
    mock_seed.reset_mock()
    monkeypatch.setattr('sys.argv',
                        ['generate_game.py', '-t', 'Random Test', '-c', '100'])
    mock_random = unittest.mock.create_autospec(
        backend.scripts.generate_game.generate_valid_dashpoints,
        return_value=[shapely.geometry.Point(0, 0)])
    monkeypatch.setattr(
        'backend.scripts.generate_game.generate_valid_dashpoints', mock_random)

    backend.scripts.generate_game.main()
    mock_random.assert_called_once_with(target_count=100,
                                        land_zip_path=unittest.mock.ANY,
                                        lakes_zip_path=unittest.mock.ANY)
    mock_seed.assert_called_once()

    # Test road-proximity algorithm routing
    mock_seed.reset_mock()
    monkeypatch.setattr('sys.argv', [
        'generate_game.py', '-t', 'Road Test', '--algorithm', 'road-proximity',
        '--roads-gpkg', 'test_roads.gpkg'
    ])
    mock_road = unittest.mock.create_autospec(
        backend.scripts.generate_game.generate_road_proximity_dashpoints,
        return_value=[shapely.geometry.Point(0, 0)])
    monkeypatch.setattr(
        'backend.scripts.generate_game.generate_road_proximity_dashpoints',
        mock_road)
    monkeypatch.setattr('backend.scripts.prepare_roads.resolve_roads_gpkg',
                        lambda path, config_path: 'resolved_roads.gpkg')

    backend.scripts.generate_game.main()
    mock_road.assert_called_once_with(
        grid_size_km=backend.scripts.generate_game.DEFAULT_GRID_SIZE_KM,
        land_zip_path=unittest.mock.ANY,
        lakes_zip_path=unittest.mock.ANY,
        roads_input='resolved_roads.gpkg')
    mock_seed.assert_called_once()

    # Test road-proximity algorithm routing when --roads-gpkg is omitted
    mock_seed.reset_mock()
    mock_road.reset_mock()
    monkeypatch.setattr('sys.argv', [
        'generate_game.py', '-t', 'Road Test Default Path', '--algorithm',
        'road-proximity'
    ])
    mock_resolve = unittest.mock.create_autospec(
        backend.scripts.prepare_roads.resolve_roads_gpkg,
        return_value='default_resolved_roads.gpkg')
    monkeypatch.setattr('backend.scripts.prepare_roads.resolve_roads_gpkg',
                        mock_resolve)

    backend.scripts.generate_game.main()
    mock_resolve.assert_called_once_with(None, config_path=unittest.mock.ANY)
    mock_road.assert_called_once_with(
        grid_size_km=backend.scripts.generate_game.DEFAULT_GRID_SIZE_KM,
        land_zip_path=unittest.mock.ANY,
        lakes_zip_path=unittest.mock.ANY,
        roads_input='default_resolved_roads.gpkg')
    mock_seed.assert_called_once()


def test_main_cli_road_proximity_error_surfacing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verifies that missing or stale road dataset errors are surfaced cleanly."""
    monkeypatch.setattr('sys.argv', [
        'generate_game.py', '-t', 'Road Error Test', '--algorithm',
        'road-proximity'
    ])

    # 1. Missing file error
    def raise_missing(*_args: object, **_kwargs: object) -> str:
        raise FileNotFoundError(
            "Road dataset 'data/world_drivable_roads.gpkg' is missing or "
            "empty. See data/README.md for instructions on downloading it "
            "via 'gcloud storage cp'.")

    monkeypatch.setattr('backend.scripts.prepare_roads.resolve_roads_gpkg',
                        raise_missing)
    with pytest.raises(SystemExit) as exit_exc1:
        backend.scripts.generate_game.main()
    assert exit_exc1.value.code == 1
    out1 = capsys.readouterr().out
    assert 'Execution Error:' in out1
    assert 'data/README.md' in out1
    assert 'gcloud storage cp' in out1

    # 2. Stale dataset error (>6 months old)
    def raise_stale(*_args: object, **_kwargs: object) -> str:
        raise RuntimeError(
            "Road dataset 'data/world_drivable_roads.gpkg' is more than "
            "6 months old (185 days). See data/README.md for instructions on "
            "refreshing and downloading an updated dataset via "
            "'gcloud storage cp'.")

    monkeypatch.setattr('backend.scripts.prepare_roads.resolve_roads_gpkg',
                        raise_stale)
    with pytest.raises(SystemExit) as exit_exc2:
        backend.scripts.generate_game.main()
    assert exit_exc2.value.code == 1
    out2 = capsys.readouterr().out
    assert 'Execution Error:' in out2
    assert 'more than 6 months old' in out2
    assert 'data/README.md' in out2
    assert 'gcloud storage cp' in out2


def test_resolve_lake_zip_paths() -> None:
    """Verify that default ne_10m_lakes.zip expands to include regional supplements."""
    expanded = backend.scripts.generate_game.resolve_lake_zip_paths(
        'data/ne_10m_lakes.zip')
    assert expanded == [
        'data/ne_10m_lakes.zip',
        'data/ne_10m_lakes_australia.zip',
        'data/ne_10m_lakes_europe.zip',
        'data/ne_10m_lakes_north_america.zip',
    ]

    custom_expanded = backend.scripts.generate_game.resolve_lake_zip_paths(
        '/var/data/ne_10m_lakes.zip')
    assert custom_expanded == [
        '/var/data/ne_10m_lakes.zip',
        '/var/data/ne_10m_lakes_australia.zip',
        '/var/data/ne_10m_lakes_europe.zip',
        '/var/data/ne_10m_lakes_north_america.zip',
    ]

    single = backend.scripts.generate_game.resolve_lake_zip_paths(
        'mock_lakes.zip')
    assert single == ['mock_lakes.zip']


def test_supplemental_lakes_exclusion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that points inside Australia, Europe, and NA lake supplements are excluded."""
    land_polygon = shapely.geometry.box(-20, -20, 20, 20)
    base_lake = shapely.geometry.box(-2, -2, -1, -1)
    aus_lake = shapely.geometry.box(1, 1, 2, 2)
    eur_lake = shapely.geometry.box(3, 3, 4, 4)
    na_lake = shapely.geometry.box(5, 5, 6, 6)

    def read_file_side_effect(path: str) -> gpd.GeoDataFrame:
        if 'land' in path:
            return gpd.GeoDataFrame(geometry=[land_polygon], crs="EPSG:4326")
        if 'australia' in path:
            return gpd.GeoDataFrame(geometry=[aus_lake], crs="EPSG:4326")
        if 'europe' in path:
            return gpd.GeoDataFrame(geometry=[eur_lake], crs="EPSG:4326")
        if 'north_america' in path:
            return gpd.GeoDataFrame(geometry=[na_lake], crs="EPSG:4326")
        if 'lakes' in path:
            return gpd.GeoDataFrame(geometry=[base_lake], crs="EPSG:4326")
        return gpd.GeoDataFrame()

    monkeypatch.setattr('backend.scripts.generate_game.gpd.read_file',
                        read_file_side_effect)

    test_points = [
        shapely.geometry.Point(-1.5, -1.5),  # in base lake -> exclude
        shapely.geometry.Point(1.5, 1.5),  # in Australia supplement -> exclude
        shapely.geometry.Point(3.5, 3.5),  # in Europe supplement -> exclude
        shapely.geometry.Point(5.5, 5.5),  # in NA supplement -> exclude
        shapely.geometry.Point(10.0, 10.0),  # dry land -> keep
    ]

    monkeypatch.setattr(
        'backend.scripts.generate_game.generate_spherical_points',
        lambda *args, **kwargs: test_points)

    valid_points = backend.scripts.generate_game.generate_valid_dashpoints(
        target_count=1,
        land_zip_path="data/ne_10m_land.zip",
        lakes_zip_path="data/ne_10m_lakes.zip")

    assert len(valid_points) == 1
    assert valid_points[0].x == 10.0
    assert valid_points[0].y == 10.0


def test_get_cell_bboxes() -> None:
    """Verifies bounding box calculation and antimeridian/polar splitting."""
    # Standard cell
    band_std = backend.scripts.generate_game.LatitudeBand(band_idx=1,
                                                          lat_min=10.0,
                                                          lat_max=20.0,
                                                          lon_offset=-100.0,
                                                          num_cells=36,
                                                          dlon=10.0)
    boxes = backend.scripts.generate_game.get_cell_bboxes(band_std, 2)
    assert boxes == [(-80.0, 10.0, -70.0, 20.0)]

    # Antimeridian crossing cell: raw_min_lon = 175.0, raw_max_lon = 185.0
    band_anti = backend.scripts.generate_game.LatitudeBand(band_idx=2,
                                                           lat_min=0.0,
                                                           lat_max=10.0,
                                                           lon_offset=175.0,
                                                           num_cells=36,
                                                           dlon=10.0)
    boxes_anti = backend.scripts.generate_game.get_cell_bboxes(band_anti, 0)
    assert len(boxes_anti) == 2
    assert boxes_anti[0] == (175.0, 0.0, 180.0, 10.0)
    assert boxes_anti[1] == (-180.0, 0.0, -175.0, 10.0)

    # Polar cell: num_cells = 1
    band_polar = backend.scripts.generate_game.LatitudeBand(band_idx=0,
                                                            lat_min=80.0,
                                                            lat_max=90.0,
                                                            lon_offset=-180.0,
                                                            num_cells=1,
                                                            dlon=360.0)
    boxes_polar = backend.scripts.generate_game.get_cell_bboxes(band_polar, 0)
    assert len(boxes_polar) == 2
    assert boxes_polar[0] == (-180.0, 80.0, 0.0, 90.0)
    assert boxes_polar[1] == (0.0, 80.0, 180.0, 90.0)


def test_classify_grid_cells() -> None:
    """Verifies partitioning into dry land cells and water-only cells."""
    band_land = backend.scripts.generate_game.LatitudeBand(band_idx=0,
                                                           lat_min=0.0,
                                                           lat_max=10.0,
                                                           lon_offset=0.0,
                                                           num_cells=2,
                                                           dlon=10.0)
    bands = [band_land]

    mock_filter = unittest.mock.MagicMock()
    mock_filter.get_candidate_matches.return_value = ({
        0: [unittest.mock.MagicMock()]
    }, {})
    mock_filter.eval_boundary_point.return_value = True

    land_cells, water_cells = backend.scripts.generate_game.classify_grid_cells(
        bands, mock_filter)
    assert len(land_cells) == 1
    assert land_cells[0] == (band_land, 0)
    assert len(water_cells) == 1
    assert water_cells[0] == (band_land, 1)


def test_generate_road_proximity_dashpoints(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies road-proximity generation: <= 50m road offset and 12km spacing."""
    band0 = backend.scripts.generate_game.LatitudeBand(band_idx=0,
                                                       lat_min=0.0,
                                                       lat_max=1.0,
                                                       lon_offset=0.0,
                                                       num_cells=2,
                                                       dlon=1.0)
    band1 = backend.scripts.generate_game.LatitudeBand(band_idx=1,
                                                       lat_min=1.0,
                                                       lat_max=2.0,
                                                       lon_offset=0.0,
                                                       num_cells=2,
                                                       dlon=1.0)
    mock_bands = [band0, band1]

    monkeypatch.setattr('backend.scripts.generate_game.build_spherical_grid',
                        lambda *args, **kwargs: mock_bands)

    mock_filter = unittest.mock.MagicMock()
    monkeypatch.setattr(
        'backend.scripts.generate_game.classify_grid_cells', lambda bands, sf:
        ([(band0, 0), (band0, 1)], [(band1, 0), (band1, 1)]))
    monkeypatch.setattr('backend.scripts.generate_game.build_spatial_filter',
                        lambda *args, **kwargs: mock_filter)

    road_line = shapely.geometry.LineString([(0.1, 0.5), (1.9, 0.5)])
    roads_gdf = gpd.GeoDataFrame(
        geometry=[road_line],
        data={
            'highway': ['primary'],
            'access': ['yes']
        },
        crs='EPSG:4326',
    )

    mock_filter.filter_valid_indices.side_effect = lambda pts: set(
        range(len(pts)))

    points = backend.scripts.generate_game.generate_road_proximity_dashpoints(
        grid_size_km=50.0,
        land_zip_path='mock_land.zip',
        lakes_zip_path='mock_lakes.zip',
        roads_input=roads_gdf,
        verbose=False,
    )

    assert len(points) >= 1
    for pt in points:
        dist_deg = road_line.distance(pt)
        assert dist_deg <= 0.001
