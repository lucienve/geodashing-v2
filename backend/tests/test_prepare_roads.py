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


def test_resolve_roads_gpkg_existing_and_fresh(tmp_path: pathlib.Path) -> None:
    """Verifies existing fresh file is returned directly or resolved from config."""
    fake_gpkg = tmp_path / 'roads.gpkg'
    fake_gpkg.write_bytes(b'geopackage')

    # Explicit path
    resolved = backend.scripts.prepare_roads.resolve_roads_gpkg(
        roads_path=str(fake_gpkg))
    assert resolved == os.path.abspath(str(fake_gpkg))

    # Path from config with surrounding quotes
    cfg_file = tmp_path / 'config.ini'
    cfg_file.write_text(f'[gcs]\nROADS_GPKG_PATH = "{fake_gpkg}"\n',
                        encoding='utf-8')
    resolved_cfg = backend.scripts.prepare_roads.resolve_roads_gpkg(
        roads_path=None, config_path=str(cfg_file))
    assert resolved_cfg == os.path.abspath(str(fake_gpkg))


def test_resolve_roads_gpkg_missing_or_empty_raises(
        tmp_path: pathlib.Path) -> None:
    """Verifies FileNotFoundError referencing data/README.md when missing or empty."""
    # Missing file
    with pytest.raises(FileNotFoundError, match='data/README.md') as exc_info:
        backend.scripts.prepare_roads.resolve_roads_gpkg(
            roads_path=str(tmp_path / 'nonexistent.gpkg'))
    assert 'gcloud storage cp' in str(exc_info.value)

    # Empty 0-byte file
    empty_file = tmp_path / 'empty.gpkg'
    empty_file.write_bytes(b'')
    with pytest.raises(FileNotFoundError,
                       match='data/README.md') as exc_info_empty:
        backend.scripts.prepare_roads.resolve_roads_gpkg(
            roads_path=str(empty_file))
    assert 'gcloud storage cp' in str(exc_info_empty.value)


def test_resolve_roads_gpkg_stale_raises(tmp_path: pathlib.Path) -> None:
    """Verifies RuntimeError referencing data/README.md when older than 6 months."""
    stale_file = tmp_path / 'stale.gpkg'
    stale_file.write_bytes(b'geopackage-data')

    # Set mtime to 185 days ago
    stale_mtime = datetime.datetime.now(
        datetime.timezone.utc).timestamp() - (185 * 24 * 3600)
    os.utime(str(stale_file), (stale_mtime, stale_mtime))

    with pytest.raises(RuntimeError,
                       match='more than 6 months old') as exc_info:
        backend.scripts.prepare_roads.resolve_roads_gpkg(
            roads_path=str(stale_file))
    assert 'data/README.md' in str(exc_info.value)
    assert 'gcloud storage cp' in str(exc_info.value)


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


def test_main_cli_rejects_download_gcs_and_validates_input(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verifies prepare_roads CLI rejects removed --download-gcs and enforces --input."""
    # --download-gcs flag must be rejected by argparse
    monkeypatch.setattr('sys.argv', ['prepare_roads.py', '--download-gcs'])
    with pytest.raises(SystemExit) as exit_exc:
        backend.scripts.prepare_roads.main()
    assert exit_exc.value.code == 2

    # Missing --input flag must exit with code 1
    monkeypatch.setattr('sys.argv', ['prepare_roads.py'])
    with pytest.raises(SystemExit) as exit_exc1:
        backend.scripts.prepare_roads.main()
    assert exit_exc1.value.code == 1
    captured = capsys.readouterr()
    assert 'Error: --input is required' in captured.out


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
        if cmd[0] == 'ogr2ogr':
            input_existed_during_ogr = input_pbf.exists()
            env = kwargs.get('env')
            assert isinstance(env, dict)
            assert env.get('OSM_MAX_TMPFILE_SIZE') == '45000'
            assert env.get('OSM_COMPRESS_NODES') == 'YES'
            assert env.get('OGR_SQLITE_CACHE') == '10240'
            assert env.get('OGR_SQLITE_PRAGMA') == 'page_size=65536'

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
    assert task_spec.get('computeResource', {}).get('memoryMib') == '65536'
    policy = (data.get('allocationPolicy', {}).get('instances',
                                                   [{}])[0].get('policy', {}))
    assert policy.get('machineType') == 'n2d-highmem-8'
    assert policy.get('provisioningModel') == 'SPOT'
    assert (backend.scripts.prepare_roads.RESUMABLE_CHUNK_SIZE == 128 * 1024 *
            1024)
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
        elif cmd[:2] == ['osmium', 'fileinfo']:
            if cmd[-1].endswith('.part') and '--input-format=pbf' not in cmd:
                raise subprocess.CalledProcessError(1, cmd)

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
    assert any(cmd[:3] == ['osmium', 'fileinfo', '--input-format=pbf']
               for cmd in ran_cmds)
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


def test_place_shuffled_road_cells_progress_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verifies periodic progress printing with custom interval and final flush."""
    mock_band = unittest.mock.MagicMock(band_idx=0)
    cells = [(mock_band, i) for i in range(5)]
    ctx = backend.scripts.prepare_roads.RoadPlacementContext(
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
        backend.scripts.prepare_roads,
        'find_valid_road_cell_point',
        lambda *args, **kwargs: next(pt_iter),
    )

    accepted: list[shapely.geometry.Point] = []
    count = backend.scripts.prepare_roads.place_shuffled_road_cells(
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
    mock_band = unittest.mock.MagicMock(band_idx=0)
    cells = [(mock_band, 0), (mock_band, 1)]
    ctx = backend.scripts.prepare_roads.RoadPlacementContext(
        roads_input='mock.gpkg',
        spatial_filter=unittest.mock.MagicMock(),
        neighbor_grid=unittest.mock.MagicMock(),
        road_bounds=None,
        cell_candidates={},
        verbose=False,
    )
    monkeypatch.setattr(
        backend.scripts.prepare_roads,
        'find_valid_road_cell_point',
        lambda *args, **kwargs: shapely.geometry.Point(0, 0),
    )

    accepted: list[shapely.geometry.Point] = []
    count = backend.scripts.prepare_roads.place_shuffled_road_cells(
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
        backend.scripts.prepare_roads.RoadPlacementContext(
            roads_input='mock.gpkg',
            spatial_filter=unittest.mock.MagicMock(),
            neighbor_grid=unittest.mock.MagicMock(),
            road_bounds=None,
            cell_candidates={},
            progress_interval=0,
        )

    with pytest.raises(ValueError,
                       match="progress_interval must be greater than 0"):
        backend.scripts.prepare_roads.RoadPlacementContext(
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
    ctx = backend.scripts.prepare_roads.RoadPlacementContext(
        roads_input='mock.gpkg',
        spatial_filter=unittest.mock.MagicMock(),
        neighbor_grid=unittest.mock.MagicMock(),
        road_bounds=None,
        cell_candidates={},
        verbose=True,
        progress_interval=100,
    )
    accepted: list[shapely.geometry.Point] = []
    count = backend.scripts.prepare_roads.place_shuffled_road_cells(
        [],
        ctx,
        accepted,
        pass2_counts={},
    )

    assert count == 0
    assert len(accepted) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
