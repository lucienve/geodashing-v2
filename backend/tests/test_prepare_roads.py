"""Unit tests for the road network preparation and filtering utility."""

import math
import os
import tempfile
import unittest.mock

import geopandas as gpd
import google.auth.transport.requests
import pytest
import shapely.geometry

import backend.scripts.prepare_roads


def test_filter_drivable_roads_inclusion_and_exclusion() -> None:
    """Verifies qualifying drivable roads are retained while private/restricted are excluded."""
    lines = [
        shapely.geometry.LineString([(0, 0), (1, 1)]),  # primary (keep)
        shapely.geometry.LineString([(1, 1), (2, 2)]),  # residential (keep)
        shapely.geometry.LineString([(2, 2), (3, 3)]),  # motorway (exclude)
        shapely.geometry.LineString([(3, 3), (4, 4)]),  # footway (exclude)
        shapely.geometry.LineString([(4, 4),
                                     (5, 5)]),  # residential private (exclude)
        None,  # null geometry (exclude without crash)
        shapely.geometry.LineString(
        ),  # empty geometry (exclude without crash)
    ]
    data = {
        'highway': [
            'primary',
            'residential',
            'motorway',
            'footway',
            'residential',
            'primary',
            'residential',
        ],
        'access': ['yes', 'yes', 'yes', 'yes', 'private', 'yes', 'yes'],
        'name': [
            'Main St',
            'Oak Ave',
            'I-95',
            'Walking Path',
            'Gated Rd',
            'Missing Rd',
            'Empty Rd',
        ],
    }
    raw_gdf = gpd.GeoDataFrame(data, geometry=lines, crs='EPSG:4326')

    filtered = backend.scripts.prepare_roads.filter_drivable_roads(raw_gdf)

    assert len(filtered) == 2
    assert list(filtered.columns) == ['geometry']
    assert filtered.crs is not None
    assert filtered.crs.to_epsg() == 4326


def test_filter_drivable_roads_empty() -> None:
    """Verifies that an empty GeoDataFrame is handled gracefully."""
    empty_gdf = gpd.GeoDataFrame(geometry=gpd.GeoSeries([], dtype='geometry'),
                                 crs='EPSG:4326')
    result = backend.scripts.prepare_roads.filter_drivable_roads(empty_gdf)
    assert len(result) == 0
    assert list(result.columns) == ['geometry']


def test_export_roads_geopackage() -> None:
    """Verifies that export_roads_geopackage writes a valid GeoPackage with spatial index."""
    line = shapely.geometry.LineString([(10.0, 20.0), (10.5, 20.5)])
    gdf = gpd.GeoDataFrame(geometry=[line], crs='EPSG:4326')

    with tempfile.TemporaryDirectory() as tmpdir:
        gpkg_path = os.path.join(tmpdir, 'test_roads.gpkg')
        backend.scripts.prepare_roads.export_roads_geopackage(gdf, gpkg_path)

        assert os.path.exists(gpkg_path)
        read_gdf = gpd.read_file(gpkg_path, layer='roads', engine='pyogrio')
        assert len(read_gdf) == 1
        assert read_gdf.crs is not None
        assert read_gdf.crs.to_epsg() == 4326


def test_upload_roads_to_gcs_resumable(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies chunked resumable upload to GCS."""
    mock_session = unittest.mock.MagicMock(
        spec=google.auth.transport.requests.AuthorizedSession)

    init_resp = unittest.mock.MagicMock()
    init_resp.status_code = 200
    init_resp.headers = {
        'Location': 'https://storage.googleapis.com/upload/foo'
    }

    chunk_resp = unittest.mock.MagicMock()
    chunk_resp.status_code = 200

    mock_session.post.return_value = init_resp
    mock_session.put.return_value = chunk_resp

    monkeypatch.setattr(
        backend.scripts.prepare_roads,
        'get_gcs_session',
        lambda creds: (mock_session, 'test-project'),
    )

    with tempfile.NamedTemporaryFile(suffix='.gpkg') as tmp:
        tmp.write(b'dummy geopackage content')
        tmp.flush()

        backend.scripts.prepare_roads.upload_roads_to_gcs(
            local_path=tmp.name,
            bucket_name='test-bucket',
            credentials_path='dummy/creds.json',
        )

    mock_session.post.assert_called_once()
    mock_session.put.assert_called_once()


def test_download_roads_from_gcs_success(
    monkeypatch: pytest.MonkeyPatch, ) -> None:
    """Verifies streaming download and atomic replacement from GCS."""
    mock_session = unittest.mock.MagicMock(
        spec=google.auth.transport.requests.AuthorizedSession)
    mock_response = unittest.mock.MagicMock()
    mock_response.status_code = 200
    mock_response.iter_content.return_value = [b'chunk1', b'chunk2']
    mock_session.get.return_value = mock_response

    monkeypatch.setattr(
        backend.scripts.prepare_roads,
        'get_gcs_session',
        lambda creds: (mock_session, 'test-project'),
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        dest_path = os.path.join(tmpdir, 'downloaded.gpkg')
        backend.scripts.prepare_roads.download_roads_from_gcs(
            local_path=dest_path,
            bucket_name='test-bucket',
            credentials_path='dummy/creds.json',
        )

        assert os.path.exists(dest_path)
        with open(dest_path, 'rb') as f:
            assert f.read() == b'chunk1chunk2'


def test_resolve_roads_gpkg_existing(tmp_path: pytest.TempPathFactory) -> None:
    """Verifies that an existing non-empty file is returned immediately."""
    fake_gpkg = os.path.join(str(tmp_path), 'roads.gpkg')
    with open(fake_gpkg, 'wb') as f:
        f.write(b'geopackage')

    resolved = backend.scripts.prepare_roads.resolve_roads_gpkg(
        roads_path=fake_gpkg, allow_download=False)
    assert resolved == os.path.abspath(fake_gpkg)


def test_resolve_roads_gpkg_missing_no_download() -> None:
    """Verifies None is returned when missing locally and allow_download is False."""
    resolved = backend.scripts.prepare_roads.resolve_roads_gpkg(
        roads_path='nonexistent/roads.gpkg', allow_download=False)
    assert resolved is None


def test_get_roads_total_bounds() -> None:
    """Verifies total bounds calculation on GeoDataFrame and GeoPackage."""
    line = shapely.geometry.LineString([(-75.5, 39.0), (-75.0, 39.5)])
    gdf = gpd.GeoDataFrame(geometry=[line], crs='EPSG:4326')

    tb = backend.scripts.prepare_roads.get_roads_total_bounds(gdf)
    assert tb == (-75.5, 39.0, -75.0, 39.5)

    with tempfile.TemporaryDirectory() as tmpdir:
        gpkg_path = os.path.join(tmpdir, 'test_bounds.gpkg')
        backend.scripts.prepare_roads.export_roads_geopackage(gdf, gpkg_path)
        tb_gpkg = backend.scripts.prepare_roads.get_roads_total_bounds(
            gpkg_path)
        assert tb_gpkg[0] == pytest.approx(-75.5)
        assert tb_gpkg[1] == pytest.approx(39.0)
        assert tb_gpkg[2] == pytest.approx(-75.0)
        assert tb_gpkg[3] == pytest.approx(39.5)


def test_query_clipped_roads_in_bboxes() -> None:
    """Verifies that road segments are clipped to bounding box and degenerate parts stripped."""
    # Line crosses from inside box (0,0,10,10) to outside
    line = shapely.geometry.LineString([(5.0, 5.0), (15.0, 5.0)])
    gdf = gpd.GeoDataFrame(geometry=[line], crs='EPSG:4326')

    lines, weights = backend.scripts.prepare_roads.query_clipped_roads_in_bboxes(
        gdf, [(0.0, 0.0, 10.0, 10.0)])

    assert len(lines) == 1
    assert len(weights) == 1
    # Clipped line should be from (5,5) to (10,5) -> length 5.0
    assert lines[0].coords[0] == pytest.approx((5.0, 5.0))
    assert lines[0].coords[-1] == pytest.approx((10.0, 5.0))
    assert weights[0] > 0.0


def test_sample_length_weighted_line_point() -> None:
    """Verifies sampling along line geometries."""
    assert (backend.scripts.prepare_roads.sample_length_weighted_line_point([],
                                                                            [])
            is None)

    line = shapely.geometry.LineString([(0.0, 0.0), (10.0, 0.0)])
    pt = backend.scripts.prepare_roads.sample_length_weighted_line_point(
        [line], [10.0])
    assert pt is not None
    assert isinstance(pt, shapely.geometry.Point)
    assert 0.0 <= pt.x <= 10.0
    assert pt.y == pytest.approx(0.0)


def test_generate_polar_road_offset() -> None:
    """Verifies road polar offset distance constraint (<= 50m)."""
    origin = (45.0, -75.0)
    for _ in range(50):
        lat, lon = backend.scripts.prepare_roads.generate_polar_road_offset(
            origin, max_dist_m=50.0)
        assert -90.0 <= lat <= 90.0
        assert -180.0 <= lon <= 180.0

        phi1, phi2 = math.radians(45.0), math.radians(lat)
        dphi = math.radians(lat - 45.0)
        dlambda = math.radians(lon - (-75.0))
        a = (math.sin(dphi / 2.0)**2 +
             math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0)**2)
        dist_km = (2.0 * backend.scripts.prepare_roads.EARTH_RADIUS_KM *
                   math.atan2(math.sqrt(a), math.sqrt(1.0 - a)))
        assert dist_km <= 0.0501  # Within 50m + floating point tolerance


def test_sample_cell_road_candidates() -> None:
    """Verifies pre-sampling candidate points for a cell."""
    line = shapely.geometry.LineString([(1.0, 1.0), (2.0, 2.0)])
    gdf = gpd.GeoDataFrame(geometry=[line], crs='EPSG:4326')

    candidates = backend.scripts.prepare_roads.sample_cell_road_candidates(
        gdf, [(0.0, 0.0, 5.0, 5.0)], num_candidates=5, max_dist_m=50.0)
    assert len(candidates) == 5
    for cand in candidates:
        assert isinstance(cand, shapely.geometry.Point)
        assert 0.0 <= cand.x <= 5.0
        assert 0.0 <= cand.y <= 5.0


def test_process_osm_pbf_to_gpkg_missing_file() -> None:
    """Verifies FileNotFoundError on missing input file."""
    with pytest.raises(FileNotFoundError, match='not found'):
        backend.scripts.prepare_roads.process_osm_pbf_to_gpkg(
            'nonexistent.osm.pbf', 'out.gpkg')
