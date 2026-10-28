"""Unit tests for spatial road-proximity sampling and grid-cell placement primitives."""

import math
import os
import tempfile
import typing
import unittest.mock

import geopandas as gpd
import pytest
import shapely.geometry
import shapely.geometry.base

import backend.scripts.road_proximity


def test_spatial_protocols_runtime_checkable() -> None:
    """Verifies that SpatialFilterProtocol and NeighborGridProtocol are runtime checkable."""

    class DummySpatialFilter:
        """Dummy spatial filter implementation for runtime protocol checks."""

        def get_candidate_matches(
            self,
            buffers: typing.Sequence[shapely.geometry.base.BaseGeometry],
        ) -> tuple[dict[int, list[shapely.geometry.base.BaseGeometry]], dict[
                int, list[shapely.geometry.base.BaseGeometry]]]:
            """Queries candidate geometries for bounding boxes."""
            del buffers
            return {}, {}

        def eval_boundary_point(
            self,
            buffer_geom: shapely.geometry.base.BaseGeometry,
            matching_lands: list[shapely.geometry.base.BaseGeometry],
            matching_lakes: list[shapely.geometry.base.BaseGeometry],
        ) -> bool:
            """Evaluates whether point intersects dry land."""
            del buffer_geom, matching_lands, matching_lakes
            return True

        def filter_valid_indices(
            self,
            raw_points: list[shapely.geometry.Point],
        ) -> set[int]:
            """Identifies indices of points on dry land."""
            del raw_points
            return set()

    class DummyNeighborGrid:
        """Dummy neighbor grid implementation for runtime protocol checks."""

        def can_place(self, lon: float, lat: float) -> bool:
            """Checks distance constraint."""
            del lon, lat
            return True

        def insert(self, lon: float, lat: float) -> bool:
            """Inserts point into grid."""
            del lon, lat
            return True

    filter_obj = DummySpatialFilter()
    grid_obj = DummyNeighborGrid()

    assert isinstance(filter_obj,
                      backend.scripts.road_proximity.SpatialFilterProtocol)
    assert isinstance(grid_obj,
                      backend.scripts.road_proximity.NeighborGridProtocol)


def test_get_roads_total_bounds() -> None:
    """Verifies total bounds calculation on GeoDataFrame and GeoPackage."""
    line = shapely.geometry.LineString([(-75.5, 39.0), (-75.0, 39.5)])
    gdf = gpd.GeoDataFrame(geometry=[line], crs='EPSG:4326')

    tb = backend.scripts.road_proximity.get_roads_total_bounds(gdf)
    assert tb == (-75.5, 39.0, -75.0, 39.5)

    with tempfile.TemporaryDirectory() as tmpdir:
        gpkg_path = os.path.join(tmpdir, 'test_bounds.gpkg')
        gdf.to_file(gpkg_path, driver='GPKG', layer='roads', engine='pyogrio')
        tb_gpkg = backend.scripts.road_proximity.get_roads_total_bounds(
            gpkg_path)
        assert tb_gpkg[0] == pytest.approx(-75.5)
        assert tb_gpkg[1] == pytest.approx(39.0)
        assert tb_gpkg[2] == pytest.approx(-75.0)
        assert tb_gpkg[3] == pytest.approx(39.5)


def test_get_roads_total_bounds_empty_dataset() -> None:
    """Verifies get_roads_total_bounds returns fallback bounds for empty dataset."""
    empty_gdf = gpd.GeoDataFrame(geometry=gpd.GeoSeries([], dtype='geometry'),
                                 crs='EPSG:4326')
    bounds = backend.scripts.road_proximity.get_roads_total_bounds(empty_gdf)
    assert bounds == (-180.0, -90.0, 180.0, 90.0)

    bounds_missing_file = backend.scripts.road_proximity.get_roads_total_bounds(
        '/path/does/not/exist.gpkg')
    assert bounds_missing_file == (-180.0, -90.0, 180.0, 90.0)


def test_query_clipped_roads_in_bboxes() -> None:
    """Verifies that road segments are clipped to bounding box and degenerate parts stripped."""
    line = shapely.geometry.LineString([(5.0, 5.0), (15.0, 5.0)])
    gdf = gpd.GeoDataFrame(geometry=[line], crs='EPSG:4326')

    lines, weights = backend.scripts.road_proximity.query_clipped_roads_in_bboxes(
        gdf, [(0.0, 0.0, 10.0, 10.0)])

    assert len(lines) == 1
    assert len(weights) == 1
    assert lines[0].coords[0] == pytest.approx((5.0, 5.0))
    assert lines[0].coords[-1] == pytest.approx((10.0, 5.0))
    assert weights[0] > 0.0


def test_query_clipped_roads_in_bboxes_gpkg_and_empty() -> None:
    """Verifies querying clipped roads from GeoPackage and handling empty results."""
    line = shapely.geometry.LineString([(5.0, 5.0), (10.0, 5.0)])
    gdf = gpd.GeoDataFrame(geometry=[line], crs='EPSG:4326')

    with tempfile.TemporaryDirectory() as tmpdir:
        gpkg_path = os.path.join(tmpdir, 'roads.gpkg')
        gdf.to_file(gpkg_path, driver='GPKG', layer='roads', engine='pyogrio')

        lines, weights = backend.scripts.road_proximity.query_clipped_roads_in_bboxes(
            gpkg_path, [(0.0, 0.0, 20.0, 20.0)])
        assert len(lines) == 1
        assert len(weights) == 1

        # Query outside the data range
        empty_lines, empty_weights = (
            backend.scripts.road_proximity.query_clipped_roads_in_bboxes(
                gpkg_path, [(50.0, 50.0, 60.0, 60.0)]))
        assert len(empty_lines) == 0
        assert len(empty_weights) == 0

        # Query non-existent gpkg
        missing_lines, missing_weights = (
            backend.scripts.road_proximity.query_clipped_roads_in_bboxes(
                os.path.join(tmpdir, 'missing.gpkg'), [(0.0, 0.0, 1.0, 1.0)]))
        assert len(missing_lines) == 0
        assert len(missing_weights) == 0


def test_clip_geometry_lines_empty_or_none() -> None:
    """Verifies clip_geometry_lines gracefully handles None and empty geometries."""
    all_lines: list[shapely.geometry.LineString] = []
    all_weights: list[float] = []
    backend.scripts.road_proximity.clip_geometry_lines(None,
                                                       (0.0, 0.0, 1.0, 1.0),
                                                       1.0, all_lines,
                                                       all_weights)
    assert len(all_lines) == 0

    empty_geom = shapely.geometry.LineString()
    backend.scripts.road_proximity.clip_geometry_lines(empty_geom,
                                                       (0.0, 0.0, 1.0, 1.0),
                                                       1.0, all_lines,
                                                       all_weights)
    assert len(all_lines) == 0


def test_sample_length_weighted_line_point() -> None:
    """Verifies sampling along line geometries."""
    assert (backend.scripts.road_proximity.sample_length_weighted_line_point(
        [], []) is None)

    line = shapely.geometry.LineString([(0.0, 0.0), (10.0, 0.0)])
    pt = backend.scripts.road_proximity.sample_length_weighted_line_point(
        [line], [10.0])
    assert pt is not None
    assert isinstance(pt, shapely.geometry.Point)
    assert 0.0 <= pt.x <= 10.0
    assert pt.y == pytest.approx(0.0)

    # Zero total weight branch
    pt_zero = backend.scripts.road_proximity.sample_length_weighted_line_point(
        [line], [0.0])
    assert pt_zero is not None


def test_generate_polar_road_offset() -> None:
    """Verifies road polar offset distance constraint (<= 50m)."""
    origin = (45.0, -75.0)
    for _ in range(50):
        lat, lon = backend.scripts.road_proximity.generate_polar_road_offset(
            origin, max_dist_m=50.0)
        assert -90.0 <= lat <= 90.0
        assert -180.0 <= lon <= 180.0

        phi1, phi2 = math.radians(45.0), math.radians(lat)
        dphi = math.radians(lat - 45.0)
        dlambda = math.radians(lon - (-75.0))
        a = (math.sin(dphi / 2.0)**2 +
             math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0)**2)
        dist_km = (2.0 * backend.scripts.road_proximity.EARTH_RADIUS_KM *
                   math.atan2(math.sqrt(a), math.sqrt(1.0 - a)))
        assert dist_km <= 0.0501


def test_sample_cell_road_candidates() -> None:
    """Verifies pre-sampling candidate points for a cell."""
    line = shapely.geometry.LineString([(1.0, 1.0), (2.0, 2.0)])
    gdf = gpd.GeoDataFrame(geometry=[line], crs='EPSG:4326')

    candidates = backend.scripts.road_proximity.sample_cell_road_candidates(
        gdf, [(0.0, 0.0, 5.0, 5.0)], num_candidates=5, max_dist_m=50.0)
    assert len(candidates) == 5
    for cand in candidates:
        assert isinstance(cand, shapely.geometry.Point)
        assert 0.0 <= cand.x <= 5.0
        assert 0.0 <= cand.y <= 5.0

    # Non-intersecting road_bounds branch
    empty_cand = backend.scripts.road_proximity.sample_cell_road_candidates(
        gdf, [(0.0, 0.0, 5.0, 5.0)],
        num_candidates=5,
        road_bounds=(20.0, 20.0, 30.0, 30.0))
    assert len(empty_cand) == 0

    # Zero candidates requested
    assert len(
        backend.scripts.road_proximity.sample_cell_road_candidates(
            gdf, [(0.0, 0.0, 5.0, 5.0)], num_candidates=0)) == 0


def test_get_cell_bboxes() -> None:
    """Verifies bounding box generation including polar and antimeridian wrapping."""
    polar_band = backend.scripts.road_proximity.LatitudeBand(band_idx=0,
                                                             lat_min=80.0,
                                                             lat_max=90.0,
                                                             lon_offset=0.0,
                                                             num_cells=1,
                                                             dlon=360.0)
    polar_boxes = backend.scripts.road_proximity.get_cell_bboxes(polar_band, 0)
    assert len(polar_boxes) == 2
    assert polar_boxes[0] == (-180.0, 80.0, 0.0, 90.0)
    assert polar_boxes[1] == (0.0, 80.0, 180.0, 90.0)

    wrap_band = backend.scripts.road_proximity.LatitudeBand(band_idx=1,
                                                            lat_min=0.0,
                                                            lat_max=10.0,
                                                            lon_offset=170.0,
                                                            num_cells=4,
                                                            dlon=90.0)
    wrap_boxes = backend.scripts.road_proximity.get_cell_bboxes(wrap_band, 0)
    assert len(wrap_boxes) == 2
    assert wrap_boxes[0] == (170.0, 0.0, 180.0, 10.0)
    assert wrap_boxes[1] == (-180.0, 0.0, -100.0, 10.0)

    normal_band = backend.scripts.road_proximity.LatitudeBand(
        band_idx=2,
        lat_min=0.0,
        lat_max=10.0,
        lon_offset=-100.0,
        num_cells=4,
        dlon=90.0)
    normal_boxes = backend.scripts.road_proximity.get_cell_bboxes(
        normal_band, 0)
    assert len(normal_boxes) == 1
    assert normal_boxes[0] == (-100.0, 0.0, -10.0, 10.0)


def test_classify_grid_cells() -> None:
    """Verifies grid cell classification into land and water."""
    band = backend.scripts.road_proximity.LatitudeBand(band_idx=0,
                                                       lat_min=0.0,
                                                       lat_max=1.0,
                                                       lon_offset=0.0,
                                                       num_cells=2,
                                                       dlon=180.0)

    class MockSpatialFilter:
        """Mock spatial filter for cell classification tests."""

        def get_candidate_matches(
            self,
            buffers: typing.Sequence[shapely.geometry.base.BaseGeometry],
        ) -> tuple[dict[int, list[shapely.geometry.base.BaseGeometry]], dict[
                int, list[shapely.geometry.base.BaseGeometry]]]:
            """Returns mock candidate matches for the first box."""
            del buffers
            return {0: [shapely.geometry.box(0, 0, 1, 1)]}, {}

        def eval_boundary_point(
            self,
            buffer_geom: shapely.geometry.base.BaseGeometry,
            matching_lands: list[shapely.geometry.base.BaseGeometry],
            matching_lakes: list[shapely.geometry.base.BaseGeometry],
        ) -> bool:
            """Evaluates whether point intersects dry land."""
            del buffer_geom, matching_lands, matching_lakes
            return True

        def filter_valid_indices(
            self,
            raw_points: list[shapely.geometry.Point],
        ) -> set[int]:
            """Identifies indices of points on dry land."""
            del raw_points
            return set()

    land_cells, water_cells = backend.scripts.road_proximity.classify_grid_cells(
        [band], MockSpatialFilter())
    assert len(land_cells) == 1
    assert len(water_cells) == 1
    assert land_cells[0] == (band, 0)
    assert water_cells[0] == (band, 1)


def test_find_valid_road_cell_point() -> None:
    """Verifies candidate point sampling and neighbor grid placement checks."""
    band = backend.scripts.road_proximity.LatitudeBand(band_idx=0,
                                                       lat_min=0.0,
                                                       lat_max=1.0,
                                                       lon_offset=0.0,
                                                       num_cells=1,
                                                       dlon=360.0)
    grid = unittest.mock.MagicMock()
    grid.can_place.return_value = True
    grid.insert.return_value = True

    s_filter = unittest.mock.MagicMock()
    s_filter.filter_valid_indices.return_value = {0}

    line = shapely.geometry.LineString([(0.5, 0.5), (0.6, 0.6)])
    gdf = gpd.GeoDataFrame(geometry=[line], crs='EPSG:4326')

    ctx = backend.scripts.road_proximity.RoadPlacementContext(
        roads_input=gdf,
        spatial_filter=s_filter,
        neighbor_grid=grid,
        road_bounds=None,
        cell_candidates={},
    )

    pt = backend.scripts.road_proximity.find_valid_road_cell_point(
        band, 0, ctx, total_attempts=1)
    assert pt is not None
    assert isinstance(pt, shapely.geometry.Point)


def test_place_shuffled_road_cells_progress_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verifies periodic progress printing with custom interval and final flush."""
    mock_band = backend.scripts.road_proximity.LatitudeBand(band_idx=0,
                                                            lat_min=0.0,
                                                            lat_max=1.0,
                                                            lon_offset=0.0,
                                                            num_cells=5,
                                                            dlon=72.0)
    cells = [(mock_band, i) for i in range(5)]
    ctx = backend.scripts.road_proximity.RoadPlacementContext(
        roads_input='mock.gpkg',
        spatial_filter=unittest.mock.MagicMock(),
        neighbor_grid=unittest.mock.MagicMock(),
        road_bounds=None,
        cell_candidates={},
        verbose=True,
        progress_interval=2,
    )

    placed_points = [
        shapely.geometry.Point(0, 0),
        shapely.geometry.Point(1, 1),
        None,
        shapely.geometry.Point(3, 3),
        None,
    ]
    pt_iter = iter(placed_points)
    monkeypatch.setattr(
        backend.scripts.road_proximity,
        'find_valid_road_cell_point',
        lambda *args, **kwargs: next(pt_iter),
    )

    accepted: list[shapely.geometry.Point] = []
    count = backend.scripts.road_proximity.place_shuffled_road_cells(
        cells,
        ctx,
        accepted,
        pass2_counts={},
    )

    assert count == 3
    assert len(accepted) == 3

    captured = capsys.readouterr()
    lines = [
        line.strip() for line in captured.out.strip().splitlines() if line
    ]
    assert len(lines) == 3
    assert 'Processed 2/5 cells' in lines[0]
    assert 'Processed 4/5 cells' in lines[1]
    assert 'Processed 5/5 cells (3 points placed)...' in lines[2]


def test_place_shuffled_road_cells_verbose_false(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verifies that progress messages are completely suppressed when verbose is False."""
    mock_band = backend.scripts.road_proximity.LatitudeBand(band_idx=0,
                                                            lat_min=0.0,
                                                            lat_max=1.0,
                                                            lon_offset=0.0,
                                                            num_cells=2,
                                                            dlon=180.0)
    cells = [(mock_band, 0), (mock_band, 1)]
    ctx = backend.scripts.road_proximity.RoadPlacementContext(
        roads_input='mock.gpkg',
        spatial_filter=unittest.mock.MagicMock(),
        neighbor_grid=unittest.mock.MagicMock(),
        road_bounds=None,
        cell_candidates={},
        verbose=False,
    )
    monkeypatch.setattr(
        backend.scripts.road_proximity,
        'find_valid_road_cell_point',
        lambda *args, **kwargs: shapely.geometry.Point(0, 0),
    )

    accepted: list[shapely.geometry.Point] = []
    count = backend.scripts.road_proximity.place_shuffled_road_cells(
        cells,
        ctx,
        accepted,
        pass2_counts={},
    )

    assert count == 2
    captured = capsys.readouterr()
    assert captured.out == ""


def test_place_shuffled_road_cells_invalid_interval() -> None:
    """Verifies that non-positive progress intervals raise a ValueError."""
    with pytest.raises(ValueError,
                       match="progress_interval must be greater than 0"):
        backend.scripts.road_proximity.RoadPlacementContext(
            roads_input='mock.gpkg',
            spatial_filter=unittest.mock.MagicMock(),
            neighbor_grid=unittest.mock.MagicMock(),
            road_bounds=None,
            cell_candidates={},
            progress_interval=0,
        )

    with pytest.raises(ValueError,
                       match="progress_interval must be greater than 0"):
        backend.scripts.road_proximity.RoadPlacementContext(
            roads_input='mock.gpkg',
            spatial_filter=unittest.mock.MagicMock(),
            neighbor_grid=unittest.mock.MagicMock(),
            road_bounds=None,
            cell_candidates={},
            progress_interval=-5,
        )


def test_place_shuffled_road_cells_empty_cells(
    capsys: pytest.CaptureFixture[str], ) -> None:
    """Verifies that empty cells list returns 0 and produces no stdout output."""
    ctx = backend.scripts.road_proximity.RoadPlacementContext(
        roads_input='mock.gpkg',
        spatial_filter=unittest.mock.MagicMock(),
        neighbor_grid=unittest.mock.MagicMock(),
        road_bounds=None,
        cell_candidates={},
        verbose=True,
        progress_interval=100,
    )
    accepted: list[shapely.geometry.Point] = []
    count = backend.scripts.road_proximity.place_shuffled_road_cells(
        [],
        ctx,
        accepted,
        pass2_counts={},
    )

    assert count == 0
    assert len(accepted) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
