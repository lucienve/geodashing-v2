"""Unit tests for the road network preparation and filtering utility."""

import datetime
import json
import os
import pathlib
import shutil
import subprocess
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
        if cmd[0] == 'osmium' and cmd[1] == 'tags-filter':
            out_idx = cmd.index('-o') + 1
            pathlib.Path(cmd[out_idx]).write_bytes(b'filtered-pbf')
        elif cmd[0] == 'ogr2ogr':
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


def test_batch_prepare_roads_json_syntax_and_schema() -> None:
    """Validates Cloud Batch JSON schema, container runnable, Local SSD, and retry policy."""
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    config_path = repo_root / 'backend' / 'scripts' / 'batch_prepare_roads.json'
    assert config_path.exists()

    with open(config_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    task_groups = data.get('taskGroups', [])
    assert len(task_groups) == 1
    task_spec = task_groups[0].get('taskSpec', {})
    compute_res = task_spec.get('computeResource', {})
    assert compute_res.get('memoryMib') == '65536'
    assert compute_res.get('cpuMilli') == '8000'
    assert 'bootDiskMib' not in compute_res

    policy = (data.get('allocationPolicy', {}).get('instances',
                                                   [{}])[0].get('policy', {}))
    assert policy.get('machineType') == 'n2d-highmem-8'
    assert policy.get('provisioningModel') == 'SPOT'
    assert 'bootDisk' not in policy

    disks = policy.get('disks', [])
    assert len(disks) == 1
    assert disks[0].get('deviceName') == 'scratch-ssd'
    new_disk = disks[0].get('newDisk', {})
    assert new_disk.get('type') == 'local-ssd'
    assert new_disk.get('sizeGb') == '375'

    volumes = task_spec.get('volumes', [])
    assert len(volumes) == 1
    assert volumes[0].get('deviceName') == 'scratch-ssd'
    assert volumes[0].get('mountPath') == '/mnt/disks/scratch'
    assert 'rw' in volumes[0].get('mountOptions', [])

    assert task_spec.get('maxRetryCount') == 3
    lifecycle_policies = task_spec.get('lifecyclePolicies', [])
    assert len(lifecycle_policies) == 1
    assert lifecycle_policies[0].get('action') == 'RETRY_TASK'
    assert lifecycle_policies[0].get('actionCondition',
                                     {}).get('exitCodes') == [50001]

    runnables = task_spec.get('runnables', [])
    assert len(runnables) == 1
    container = runnables[0].get('container', {})
    assert container
    assert container.get(
        'imageUri'
    ) == 'us-east1-docker.pkg.dev/geodashing-v2/batch/prepare-roads:latest'
    assert container.get('enableImageStreaming') is True
    assert '/mnt/disks/scratch:/mnt/disks/scratch:rw' in container.get(
        'volumes', [])
    assert '--download-planet-osm' in container.get('commands', [])
    assert '--upload-gcs' in container.get('commands', [])
    assert 'options' not in container
    assert 'environment' not in container


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


def test_dockerfile_prepare_roads_structure_and_isolation() -> None:
    """Verifies Dockerfile instructions, hermetic dependencies, and context isolation."""
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    dockerfile_path = repo_root / 'backend' / 'scripts' / 'Dockerfile.prepare_roads'
    dockerignore_path = (repo_root / 'backend' / 'scripts' /
                         'Dockerfile.prepare_roads.dockerignore')

    assert dockerfile_path.exists()
    assert dockerignore_path.exists()

    df_content = dockerfile_path.read_text(encoding='utf-8')
    assert 'FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim' in df_content
    assert 'osmium-tool' in df_content
    assert 'gdal-bin' in df_content
    assert 'aria2' in df_content
    assert 'ENV PYTHONUNBUFFERED=1' in df_content
    assert 'uv sync --frozen --no-dev --no-install-project' in df_content
    assert 'ENV UV_NO_SYNC=1' in df_content
    assert df_content.index('uv sync') < df_content.index('ENV UV_NO_SYNC=1')
    assert 'ENTRYPOINT' in df_content
    assert 'backend.scripts.prepare_roads' in df_content

    di_content = dockerignore_path.read_text(encoding='utf-8')
    assert di_content.startswith('#') or di_content.startswith('*')
    assert '*' in di_content
    assert '!/.python-version' in di_content
    assert '!/pyproject.toml' in di_content
    assert '!/uv.lock' in di_content
    assert '!/backend/scripts/prepare_roads.py' in di_content


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


def test_main_cli_early_exit_when_gcs_output_fresh(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verifies that main exits early when world_drivable_roads.gpkg is fresh in GCS."""
    monkeypatch.setattr('sys.argv', [
        'prepare_roads.py',
        '--input',
        'dummy.pbf',
        '--upload-gcs',
    ])

    def fake_cache_check(bucket_name: str,
                         credentials_path: str | None = None,
                         object_name: str = '') -> int | None:
        del bucket_name, credentials_path
        if object_name == backend.scripts.prepare_roads.ROADS_GPKG_GCS_OBJECT:
            return 50000000
        return None

    monkeypatch.setattr(backend.scripts.prepare_roads,
                        '_check_gcs_planet_cache', fake_cache_check)

    compile_called = False

    def fake_compile(input_path: str, output_path: str,
                     **kwargs: object) -> None:
        del input_path, output_path, kwargs
        nonlocal compile_called
        compile_called = True

    monkeypatch.setattr(backend.scripts.prepare_roads,
                        '_compile_roads_dataset', fake_compile)

    backend.scripts.prepare_roads.main()

    captured = capsys.readouterr()
    assert 'is already fresh (50000000 bytes). Exiting early.' in captured.out
    assert not compile_called


def test_main_cli_force_bypasses_early_exit_and_caches(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verifies that --force bypasses early-exit and cached filtered PBF."""
    monkeypatch.setattr('sys.argv', [
        'prepare_roads.py',
        '--input',
        'dummy.pbf',
        '--upload-gcs',
        '--download-planet-osm',
        '--force',
    ])
    monkeypatch.setattr(
        backend.scripts.prepare_roads,
        '_check_gcs_planet_cache',
        lambda *args, **kwargs: 50000000,
    )

    planet_fetched = False
    compiled = False
    uploaded = False

    def fake_fetch_planet(dest: str,
                          bucket: str,
                          credentials_path: str | None = None,
                          force: bool = False) -> str:
        del bucket, credentials_path
        nonlocal planet_fetched
        assert force is True
        planet_fetched = True
        return dest

    def fake_compile(input_path: str, output_path: str,
                     **kwargs: object) -> None:
        del input_path, output_path, kwargs
        nonlocal compiled
        compiled = True

    def fake_upload(local_path: str,
                    bucket_name: str,
                    credentials_path: str | None = None,
                    object_name: str = '') -> None:
        del local_path, bucket_name, credentials_path, object_name
        nonlocal uploaded
        uploaded = True

    monkeypatch.setattr(backend.scripts.prepare_roads,
                        'fetch_or_cache_planet_pbf', fake_fetch_planet)
    monkeypatch.setattr(backend.scripts.prepare_roads,
                        '_compile_roads_dataset', fake_compile)
    monkeypatch.setattr(backend.scripts.prepare_roads, 'upload_roads_to_gcs',
                        fake_upload)

    backend.scripts.prepare_roads.main()

    captured = capsys.readouterr()
    assert 'Exiting early' not in captured.out
    assert planet_fetched
    assert compiled
    assert uploaded


def test_main_cli_uses_cached_filtered_pbf(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verifies that fresh cached filtered PBF is used, skipping raw planet download."""
    monkeypatch.setattr('sys.argv', [
        'prepare_roads.py',
        '--input',
        'dummy.pbf',
        '--download-planet-osm',
    ])
    monkeypatch.setattr(
        backend.scripts.prepare_roads,
        '_check_gcs_planet_cache',
        lambda *args, **kwargs: None,
    )

    cached_filtered_called = False

    def fake_fetch_filtered(dest: str,
                            bucket: str,
                            credentials_path: str | None = None) -> bool:
        del dest, bucket, credentials_path
        nonlocal cached_filtered_called
        cached_filtered_called = True
        return True

    planet_fetched = False

    def fake_fetch_planet(dest: str,
                          bucket: str,
                          credentials_path: str | None = None,
                          force: bool = False) -> str:
        del dest, bucket, credentials_path, force
        nonlocal planet_fetched
        planet_fetched = True
        return 'dummy.pbf'

    compiled_input = ''
    delete_input_flag = False

    def fake_compile(input_path: str, output_path: str,
                     **kwargs: object) -> None:
        del output_path
        nonlocal compiled_input, delete_input_flag
        compiled_input = input_path
        delete_input_flag = bool(kwargs.get('delete_input'))

    monkeypatch.setattr(backend.scripts.prepare_roads,
                        'fetch_cached_filtered_pbf', fake_fetch_filtered)
    monkeypatch.setattr(backend.scripts.prepare_roads,
                        'fetch_or_cache_planet_pbf', fake_fetch_planet)
    monkeypatch.setattr(backend.scripts.prepare_roads,
                        '_compile_roads_dataset', fake_compile)

    backend.scripts.prepare_roads.main()

    captured = capsys.readouterr()
    assert 'Using cached filtered PBF; skipping raw planet OSM download.' in captured.out
    assert cached_filtered_called
    assert not planet_fetched
    assert compiled_input.endswith('filtered_roads.osm.pbf')
    assert delete_input_flag is True


def test_fetch_cached_filtered_pbf_success_and_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies fetch_cached_filtered_pbf handles cache hits and corrupted downloads."""
    dest_file = tmp_path / 'filtered.osm.pbf'

    # 1. Cache miss (None returned by _check_gcs_planet_cache)
    monkeypatch.setattr(
        backend.scripts.prepare_roads,
        '_check_gcs_planet_cache',
        lambda *args, **kwargs: None,
    )
    assert not backend.scripts.prepare_roads.fetch_cached_filtered_pbf(
        str(dest_file), 'bucket')

    # 2. Cache hit with successful verification
    monkeypatch.setattr(
        backend.scripts.prepare_roads,
        '_check_gcs_planet_cache',
        lambda *args, **kwargs: 1234,
    )

    def fake_download_ok(local_path: str,
                         bucket_name: str,
                         credentials_path: str | None = None,
                         object_name: str = '') -> None:
        del bucket_name, credentials_path, object_name
        pathlib.Path(local_path).write_bytes(b'x' * 1234)

    monkeypatch.setattr(backend.scripts.prepare_roads,
                        'download_roads_from_gcs', fake_download_ok)
    monkeypatch.setattr('shutil.which', lambda name: None)

    assert backend.scripts.prepare_roads.fetch_cached_filtered_pbf(
        str(dest_file), 'bucket')
    assert dest_file.exists()

    # 3. Cache hit with verification failure (e.g. size mismatch)
    def fake_download_bad(local_path: str,
                          bucket_name: str,
                          credentials_path: str | None = None,
                          object_name: str = '') -> None:
        del bucket_name, credentials_path, object_name
        pathlib.Path(local_path).write_bytes(b'x' * 999)

    monkeypatch.setattr(backend.scripts.prepare_roads,
                        'download_roads_from_gcs', fake_download_bad)
    assert not backend.scripts.prepare_roads.fetch_cached_filtered_pbf(
        str(dest_file), 'bucket')
    assert not dest_file.exists()


def test_process_osm_pbf_to_gpkg_uploads_filtered_checkpoint(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies process_osm_pbf_to_gpkg uploads filtered checkpoint to GCS when bucket is given."""
    input_pbf = tmp_path / 'input.osm.pbf'
    input_pbf.write_bytes(b'input-pbf')
    output_gpkg = tmp_path / 'out.gpkg'

    uploaded_objects: list[str] = []

    def fake_upload(local_path: str,
                    bucket_name: str,
                    credentials_path: str | None = None,
                    object_name: str = '') -> None:
        del local_path, bucket_name, credentials_path
        uploaded_objects.append(object_name)

    def fake_run(cmd: list[str], **kwargs: object) -> None:
        del kwargs
        if cmd[0] == 'osmium' and cmd[1] == 'tags-filter':
            out_idx = cmd.index('-o') + 1
            pathlib.Path(cmd[out_idx]).write_bytes(b'filtered-pbf')

    monkeypatch.setattr('shutil.which', lambda name: '/usr/bin/osmium')
    monkeypatch.setattr('subprocess.run', fake_run)
    monkeypatch.setattr(backend.scripts.prepare_roads, 'upload_roads_to_gcs',
                        fake_upload)

    backend.scripts.prepare_roads.process_osm_pbf_to_gpkg(
        str(input_pbf),
        str(output_gpkg),
        delete_input=False,
        bucket_name='test-bucket',
    )

    assert uploaded_objects == [
        backend.scripts.prepare_roads.FILTERED_PBF_CACHE_OBJECT
    ]


def test_submit_roads_batch_job_force_flag_injection(
    tmp_path: pathlib.Path, ) -> None:
    """Verifies submit_roads_batch_job.sh handles --force and unknown arguments correctly."""
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    script_path = repo_root / 'backend' / 'scripts' / 'submit_roads_batch_job.sh'

    # 1. Invalid argument returns exit code 1
    invalid_proc = subprocess.run(
        ['bash', str(script_path), '--invalid-flag'],
        check=False,
        capture_output=True,
    )
    assert invalid_proc.returncode == 1
    assert b'Usage:' in invalid_proc.stderr

    # 2. Verify JSON config injection with --force
    sample_config = {
        'taskGroups': [{
            'taskSpec': {
                'runnables': [{
                    'container': {
                        'commands': [
                            '--download-planet-osm',
                            '--input',
                            'in.pbf',
                            '--output',
                            'out.gpkg',
                        ]
                    }
                }]
            }
        }]
    }
    src_json = tmp_path / 'batch_prepare_roads.json'
    dest_json = tmp_path / 'modified_batch_prepare_roads.json'
    src_json.write_text(json.dumps(sample_config), encoding='utf-8')

    py_cmd = (
        'import json, sys\n'
        'with open(sys.argv[1], "r", encoding="utf-8") as f:\n'
        '    data = json.load(f)\n'
        'commands = data["taskGroups"][0]["taskSpec"]["runnables"][0]["container"]["commands"]\n'
        'if "--force" not in commands:\n'
        '    commands.append("--force")\n'
        'with open(sys.argv[2], "w", encoding="utf-8") as f:\n'
        '    json.dump(data, f, indent=2)\n')
    inject_proc = subprocess.run(
        ['python3', '-c', py_cmd,
         str(src_json), str(dest_json)],
        check=True,
    )
    assert inject_proc.returncode == 0
    assert dest_json.exists()

    with open(dest_json, 'r', encoding='utf-8') as f:
        mod_data = json.load(f)
    mod_cmds = mod_data['taskGroups'][0]['taskSpec']['runnables'][0][
        'container']['commands']
    assert '--force' in mod_cmds
    assert mod_cmds[-1] == '--force'


def test_process_osm_pbf_to_gpkg_prefiltered_input_skips_osmium(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies that pre-filtered input PBF bypasses osmium and preserves file
    when delete_input=False.
    """
    work_dir = tmp_path / 'work'
    work_dir.mkdir()
    filtered_pbf = work_dir / 'filtered_roads.osm.pbf'
    filtered_pbf.write_bytes(b'fake_prefiltered_pbf')
    output_gpkg = work_dir / 'output.gpkg'

    osmium_called = False

    def fake_filter(*args: object, **kwargs: object) -> None:
        del args, kwargs
        nonlocal osmium_called
        osmium_called = True

    ogr_called = False

    def fake_ogr(*args: object, **kwargs: object) -> None:
        del args, kwargs
        nonlocal ogr_called
        ogr_called = True

    monkeypatch.setattr(backend.scripts.prepare_roads,
                        '_filter_and_cache_pbf_roads', fake_filter)
    monkeypatch.setattr(backend.scripts.prepare_roads,
                        '_run_ogr2ogr_roads_export', fake_ogr)

    backend.scripts.prepare_roads.process_osm_pbf_to_gpkg(str(filtered_pbf),
                                                          str(output_gpkg),
                                                          delete_input=False)

    assert not osmium_called
    assert ogr_called
    assert filtered_pbf.exists()
