"""Unit tests for the road network preparation and filtering utility."""

import datetime
import json
import math
import os
import pathlib
import shutil
import subprocess
import tarfile
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


def test_resolve_roads_gpkg_none_handling(tmp_path: pathlib.Path) -> None:
    """Verifies resolve_roads_gpkg handles roads_path=None gracefully without TypeError."""
    cfg_file = tmp_path / 'config.ini'
    cfg_file.write_text('[gcs]\n', encoding='utf-8')
    res = backend.scripts.prepare_roads.resolve_roads_gpkg(
        None, config_path=str(cfg_file), allow_download=False)
    assert res is None


def test_get_roads_total_bounds_empty_dataset() -> None:
    """Verifies get_roads_total_bounds returns fallback bounds for empty dataset."""
    empty_gdf = gpd.GeoDataFrame(geometry=gpd.GeoSeries([], dtype='geometry'),
                                 crs='EPSG:4326')
    bounds = backend.scripts.prepare_roads.get_roads_total_bounds(empty_gdf)
    assert bounds == (-180.0, -90.0, 180.0, 90.0)


def test_process_osm_pbf_to_gpkg_deletes_input_after_osmium(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies delete_input removes input PBF before ogr2ogr executes."""
    input_pbf = tmp_path / 'planet.osm.pbf'
    input_pbf.write_bytes(b'fake-pbf')
    output_gpkg = tmp_path / 'out.gpkg'
    input_existed_during_ogr = True

    def fake_run(cmd: list[str], **kwargs: object) -> None:
        nonlocal input_existed_during_ogr
        del kwargs
        if cmd[0] == 'ogr2ogr':
            input_existed_during_ogr = input_pbf.exists()

    monkeypatch.setattr('shutil.which', lambda name: '/usr/bin/osmium')
    monkeypatch.setattr('subprocess.run', fake_run)

    backend.scripts.prepare_roads.process_osm_pbf_to_gpkg(str(input_pbf),
                                                          str(output_gpkg),
                                                          delete_input=True)
    assert not input_existed_during_ogr
    assert not input_pbf.exists()


def test_batch_prepare_roads_json_syntax_and_shellcheck() -> None:
    """Validates Cloud Batch JSON schema and verifies inline script passes POSIX sh shellcheck."""
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    config_path = repo_root / 'backend' / 'scripts' / 'batch_prepare_roads.json'
    assert config_path.exists()

    with open(config_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    task_groups = data.get('taskGroups', [])
    assert len(task_groups) == 1
    task_spec = task_groups[0].get('taskSpec', {})
    runnables = task_spec.get('runnables', [])
    assert len(runnables) == 1
    script_text = runnables[0].get('script', {}).get('text', '')
    assert script_text

    # Verify POSIX sh syntax via /bin/sh -n
    sh_proc = subprocess.run(['/bin/sh', '-n'],
                             input=script_text.encode('utf-8'),
                             check=False,
                             capture_output=True)
    assert sh_proc.returncode == 0, f"POSIX /bin/sh syntax check failed: {sh_proc.stderr.decode()}"

    # Verify via shellcheck with strict POSIX sh dialect if installed
    if shutil.which('shellcheck'):
        sc_proc = subprocess.run(['shellcheck', '--shell=sh', '-'],
                                 input=script_text.encode('utf-8'),
                                 check=False,
                                 capture_output=True)
        assert sc_proc.returncode == 0, f"shellcheck --shell=sh failed:\n{sc_proc.stdout.decode()}"


def test_submit_roads_batch_job_syntax_and_shellcheck() -> None:
    """Validates submission wrapper script syntax and shellcheck."""
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    script_path = repo_root / 'backend' / 'scripts' / 'submit_roads_batch_job.sh'
    assert script_path.exists()

    bash_proc = subprocess.run(['bash', '-n', str(script_path)],
                               check=False,
                               capture_output=True)
    assert bash_proc.returncode == 0, f"bash -n check failed: {bash_proc.stderr.decode()}"

    if shutil.which('shellcheck'):
        sc_proc = subprocess.run(
            ['shellcheck', '--shell=bash',
             str(script_path)],
            check=False,
            capture_output=True)
        assert sc_proc.returncode == 0, f"shellcheck failed:\n{sc_proc.stdout.decode()}"


def test_batch_bundle_packaging_simulation(tmp_path: pathlib.Path) -> None:
    """Simulates bundling of the hermetic code package and verifies contents unpack cleanly."""
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    bundle_path = tmp_path / 'test_bundle.tar.gz'
    files_to_pack = [
        '.python-version',
        'pyproject.toml',
        'uv.lock',
        'backend/scripts/prepare_roads.py',
    ]
    for rel_path in files_to_pack:
        assert (repo_root / rel_path).exists()

    with tarfile.open(bundle_path, 'w:gz') as tar:
        for rel_path in files_to_pack:
            tar.add(repo_root / rel_path, arcname=rel_path)

    unpack_dir = tmp_path / 'unpacked'
    unpack_dir.mkdir()
    with tarfile.open(bundle_path, 'r:gz') as tar:
        tar.extractall(unpack_dir)

    for rel_path in files_to_pack:
        unpacked_file = unpack_dir / rel_path
        assert unpacked_file.exists()
        assert unpacked_file.stat().st_size > 0


def test_fetch_or_cache_planet_pbf_cache_hit(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies fresh <=7-day GCS cache is used without downloading from OSM mirrors."""
    dest_pbf = tmp_path / 'planet-latest.osm.pbf'
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    mock_session = unittest.mock.MagicMock(
        spec=google.auth.transport.requests.AuthorizedSession)
    meta_resp = unittest.mock.MagicMock()
    meta_resp.status_code = 200
    meta_resp.json.return_value = {'size': '12', 'updated': now_iso}
    mock_session.get.return_value = meta_resp

    monkeypatch.setattr(
        backend.scripts.prepare_roads,
        'get_gcs_session',
        lambda creds: (mock_session, 'test-project'),
    )

    def fake_download_gcs(
        local_path: str,
        bucket_name: str,
        credentials_path: str | None = None,
        object_name: str = '',
    ) -> None:
        del bucket_name, credentials_path
        assert object_name == backend.scripts.prepare_roads.PLANET_PBF_CACHE_OBJECT
        pathlib.Path(local_path).write_bytes(b'cached-bytes')

    monkeypatch.setattr(backend.scripts.prepare_roads,
                        'download_roads_from_gcs', fake_download_gcs)
    mirror_called = False

    def fail_mirror(_dest: str) -> None:
        nonlocal mirror_called
        mirror_called = True

    monkeypatch.setattr(backend.scripts.prepare_roads,
                        '_download_planet_from_mirrors', fail_mirror)

    res = backend.scripts.prepare_roads.fetch_or_cache_planet_pbf(
        str(dest_pbf), 'test-bucket')
    assert res == str(dest_pbf)
    assert dest_pbf.read_bytes() == b'cached-bytes'
    assert not mirror_called


def test_fetch_or_cache_planet_pbf_expired_cache_downloads_and_caches(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies expired >7-day GCS cache triggers multi-mirror download and re-caches."""
    dest_pbf = tmp_path / 'planet-latest.osm.pbf'
    old_dt = datetime.datetime.now(
        datetime.timezone.utc) - datetime.timedelta(days=8)

    mock_session = unittest.mock.MagicMock(
        spec=google.auth.transport.requests.AuthorizedSession)
    meta_resp = unittest.mock.MagicMock()
    meta_resp.status_code = 200
    meta_resp.json.return_value = {'size': '16', 'updated': old_dt.isoformat()}
    mock_session.get.return_value = meta_resp

    monkeypatch.setattr(
        backend.scripts.prepare_roads,
        'get_gcs_session',
        lambda creds: (mock_session, 'test-project'),
    )
    monkeypatch.setattr(backend.scripts.prepare_roads,
                        '_get_expected_planet_size', lambda: 16)
    monkeypatch.setattr('shutil.which', lambda name: f'/usr/bin/{name}')

    ran_cmds: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> None:
        del kwargs
        ran_cmds.append(cmd)
        if cmd[0] == 'aria2c':
            part_file = tmp_path / 'planet-latest.osm.pbf.part'
            part_file.write_bytes(b'0123456789abcdef')

    monkeypatch.setattr('subprocess.run', fake_run)
    uploaded_objects: list[str] = []

    def fake_upload(
        local_path: str,
        bucket_name: str,
        credentials_path: str | None = None,
        object_name: str = '',
    ) -> None:
        del bucket_name, credentials_path
        assert os.path.getsize(local_path) == 16
        uploaded_objects.append(object_name)

    monkeypatch.setattr(backend.scripts.prepare_roads, 'upload_roads_to_gcs',
                        fake_upload)

    res = backend.scripts.prepare_roads.fetch_or_cache_planet_pbf(
        str(dest_pbf), 'test-bucket')
    assert res == str(dest_pbf)
    assert dest_pbf.exists()
    assert any(cmd[0] == 'aria2c' for cmd in ran_cmds)
    assert any(cmd[:2] == ['osmium', 'fileinfo'] for cmd in ran_cmds)
    assert uploaded_objects == [
        backend.scripts.prepare_roads.PLANET_PBF_CACHE_OBJECT
    ]


def test_download_planet_rejects_incomplete_and_never_caches(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies incomplete download (size mismatch or .aria2 file) fails and is not cached."""
    dest_pbf = tmp_path / 'planet-latest.osm.pbf'
    monkeypatch.setattr(backend.scripts.prepare_roads,
                        '_check_gcs_planet_cache', lambda *a, **kw: None)
    monkeypatch.setattr(backend.scripts.prepare_roads,
                        '_get_expected_planet_size', lambda: 1000)
    monkeypatch.setattr('shutil.which', lambda name: '/usr/bin/aria2c')

    def fake_run(cmd: list[str], **kwargs: object) -> None:
        del kwargs
        if cmd[0] == 'aria2c':
            part_file = tmp_path / 'planet-latest.osm.pbf.part'
            part_file.write_bytes(b'truncated')

    monkeypatch.setattr('subprocess.run', fake_run)
    upload_called = False

    def fail_upload(*_args: object, **_kwargs: object) -> None:
        nonlocal upload_called
        upload_called = True

    monkeypatch.setattr(backend.scripts.prepare_roads, 'upload_roads_to_gcs',
                        fail_upload)

    with pytest.raises(RuntimeError, match='Size mismatch'):
        backend.scripts.prepare_roads.fetch_or_cache_planet_pbf(
            str(dest_pbf), 'test-bucket')

    assert not dest_pbf.exists()
    assert not (tmp_path / 'planet-latest.osm.pbf.part').exists()
    assert not upload_called
