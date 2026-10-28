"""Unit tests for backend/scripts/prepare_water.py."""

import os
import pathlib
import shutil
import subprocess
import typing
import urllib.request
import zipfile

import geopandas as gpd
import numpy as np
import pyogrio
import pytest
import shapely
import shapely.geometry

import backend.scripts.prepare_roads
import backend.scripts.prepare_water


def test_build_water_where_clause() -> None:
    """Verifies that the water WHERE clause includes required water bodies and exclusions."""
    clause = backend.scripts.prepare_water.build_water_where_clause()
    assert "natural = 'water'" in clause
    assert "waterway = 'riverbank'" in clause
    assert "landuse IN ('reservoir', 'basin')" in clause
    assert "natural = 'wetland'" in clause
    assert "'tidalflat'" in clause
    assert "'swamp'" in clause
    assert "'marsh'" in clause
    assert "water NOT IN ('ditch', 'drain', 'wastewater', 'moat', 'reflecting_pool')" in clause
    assert "OGR_GEOM_AREA >= 5e-07" in clause


def test_write_water_osmconf(tmp_path: pathlib.Path) -> None:
    """Verifies that write_water_osmconf generates a valid configuration file."""
    conf_path = backend.scripts.prepare_water.write_water_osmconf(
        str(tmp_path))
    assert os.path.exists(conf_path)
    with open(conf_path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert '[multipolygons]' in content
    assert 'attributes=natural,water,wetland,waterway,landuse' in content
    assert 'other_tags=no' in content


def test_verify_land_zip(tmp_path: pathlib.Path) -> None:
    """Verifies land zip file existence, byte size, and internal shapefile validation."""
    nonexistent = str(tmp_path / 'missing.zip')
    assert not backend.scripts.prepare_water.verify_land_zip(nonexistent)

    empty = tmp_path / 'empty.zip'
    empty.write_bytes(b'')
    assert not backend.scripts.prepare_water.verify_land_zip(str(empty))

    bad_zip = tmp_path / 'corrupt.zip'
    bad_zip.write_bytes(b'not a zip file')
    assert not backend.scripts.prepare_water.verify_land_zip(str(bad_zip))

    missing_member = tmp_path / 'no_member.zip'
    with zipfile.ZipFile(missing_member, 'w') as zf:
        zf.writestr('other_file.txt', 'hello')
    assert not backend.scripts.prepare_water.verify_land_zip(
        str(missing_member))

    valid_zip = tmp_path / 'valid.zip'
    with zipfile.ZipFile(valid_zip, 'w') as zf:
        zf.writestr('land-polygons-split-4326/land_polygons.shp', b'shp data')
    assert backend.scripts.prepare_water.verify_land_zip(str(valid_zip))
    assert not backend.scripts.prepare_water.verify_land_zip(
        str(valid_zip), expected_size=999999)
    assert backend.scripts.prepare_water.verify_land_zip(
        str(valid_zip), expected_size=valid_zip.stat().st_size)


def test_fetch_or_cache_land_polygons_zip_existing(
        tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies existing verified land zip is returned directly without downloading."""
    zip_path = tmp_path / 'land.zip'
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr('land-polygons-split-4326/land_polygons.shp', b'data')

    download_called = False

    def fake_download(*_args: typing.Any, **_kwargs: typing.Any) -> None:
        nonlocal download_called
        download_called = True

    monkeypatch.setattr(backend.scripts.prepare_roads,
                        'download_roads_from_gcs', fake_download)

    result = backend.scripts.prepare_water.fetch_or_cache_land_polygons_zip(
        str(zip_path), bucket_name='test-bucket')
    assert result == str(zip_path)
    assert not download_called


def test_fetch_or_cache_land_polygons_zip_gcs_hit(
        tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies downloading land polygons from GCS cache when fresh."""
    dest = tmp_path / 'land.zip'

    monkeypatch.setattr(
        backend.scripts.prepare_roads,
        'check_gcs_object_cache',
        lambda *_args, **_kwargs: 1234,
    )

    def fake_download(dest_path: str, *_args: typing.Any,
                      **_kwargs: typing.Any) -> None:
        with zipfile.ZipFile(dest_path, 'w') as zf:
            zf.writestr('land-polygons-split-4326/land_polygons.shp', b'data')

    monkeypatch.setattr(backend.scripts.prepare_roads,
                        'download_roads_from_gcs', fake_download)
    monkeypatch.setattr(backend.scripts.prepare_water, 'verify_land_zip',
                        lambda *_args, **_kwargs: True)

    result = backend.scripts.prepare_water.fetch_or_cache_land_polygons_zip(
        str(dest), bucket_name='test-bucket')
    assert result == str(dest)


def test_fetch_or_cache_land_polygons_zip_mirror_download(
        tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies mirror download and caching to GCS on cache miss."""
    dest = tmp_path / 'land.zip'

    monkeypatch.setattr(
        backend.scripts.prepare_roads,
        'check_gcs_object_cache',
        lambda *_args, **_kwargs: None,
    )

    uploaded: list[str] = []

    def fake_upload(local_path: str, *_args: typing.Any,
                    **_kwargs: typing.Any) -> None:
        uploaded.append(local_path)

    monkeypatch.setattr(backend.scripts.prepare_roads, 'upload_roads_to_gcs',
                        fake_upload)

    monkeypatch.setattr(
        shutil,
        'which',
        lambda tool: '/usr/bin/aria2c' if tool == 'aria2c' else None,
    )
    monkeypatch.setattr(
        subprocess,
        'run',
        lambda *_args, **_kwargs:
        (tmp_path / 'land.zip.part').write_bytes(b''),
    )
    monkeypatch.setattr(
        urllib.request,
        'urlretrieve',
        lambda _url, _filename: (tmp_path / 'land.zip.part').write_bytes(b''),
    )
    monkeypatch.setattr(backend.scripts.prepare_water, 'verify_land_zip',
                        lambda *_args, **_kwargs: True)

    result = backend.scripts.prepare_water.fetch_or_cache_land_polygons_zip(
        str(dest), bucket_name='test-bucket')
    assert result == str(dest)
    assert uploaded == [str(dest)]


def test_fetch_cached_filtered_water_pbf(
        tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies fetch_cached_filtered_water_pbf cache hit and miss handling."""
    dest = tmp_path / 'filtered.osm.pbf'

    # Cache miss
    monkeypatch.setattr(
        backend.scripts.prepare_roads,
        'check_gcs_object_cache',
        lambda *_args, **_kwargs: None,
    )
    assert not backend.scripts.prepare_water.fetch_cached_filtered_water_pbf(
        str(dest), 'test-bucket')

    # Cache hit
    monkeypatch.setattr(
        backend.scripts.prepare_roads,
        'check_gcs_object_cache',
        lambda *_args, **_kwargs: 500,
    )
    monkeypatch.setattr(
        backend.scripts.prepare_roads,
        'download_roads_from_gcs',
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        backend.scripts.prepare_roads,
        'verify_pbf_download',
        lambda *_args, **_kwargs: None,
    )
    assert backend.scripts.prepare_water.fetch_cached_filtered_water_pbf(
        str(dest), 'test-bucket')

    # Download error
    def fail_download(*_args: typing.Any, **_kwargs: typing.Any) -> None:
        dest.write_text('bad', encoding='utf-8')
        raise RuntimeError("Network error")

    monkeypatch.setattr(backend.scripts.prepare_roads,
                        'download_roads_from_gcs', fail_download)
    assert not backend.scripts.prepare_water.fetch_cached_filtered_water_pbf(
        str(dest), 'test-bucket')
    assert not os.path.exists(str(dest))


def test_filter_planet_water_pbf(tmp_path: pathlib.Path,
                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies osmium filter invocation, input deletion, and GCS caching."""
    input_pbf = tmp_path / 'planet.osm.pbf'
    input_pbf.write_bytes(b'planet-data')
    output_pbf = tmp_path / 'filtered.osm.pbf'

    osmium_calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: typing.Any) -> None:
        osmium_calls.append(cmd)
        (tmp_path / 'filtered.osm.pbf.part').write_bytes(b'filtered-part')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    monkeypatch.setattr(
        backend.scripts.prepare_roads,
        'verify_pbf_download',
        lambda *_args, **_kwargs: None,
    )

    uploaded: list[str] = []
    monkeypatch.setattr(
        backend.scripts.prepare_roads,
        'upload_roads_to_gcs',
        lambda p, *_a, **_k: uploaded.append(p),
    )

    res = backend.scripts.prepare_water.filter_planet_water_pbf(
        str(input_pbf),
        str(output_pbf),
        delete_input=True,
        bucket_name='test-bucket',
    )

    assert res == str(output_pbf)
    assert os.path.exists(output_pbf)
    assert not os.path.exists(input_pbf)
    assert len(osmium_calls) == 1
    assert 'wr/natural=water,wetland' in osmium_calls[0]
    assert uploaded == [str(output_pbf)]


def test_extract_osm_water_and_land(tmp_path: pathlib.Path,
                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies ogr2ogr step 3a and 3b execution and layer validation."""
    water_pbf = tmp_path / 'water.osm.pbf'
    water_pbf.write_bytes(b'water')
    land_zip = tmp_path / 'land.zip'
    land_zip.write_bytes(b'land')
    out_gpkg = tmp_path / 'out.gpkg'

    ogr_cmds: list[list[str]] = []

    def fake_run_ogr(cmd: list[str], _work_dir: str) -> None:
        ogr_cmds.append(cmd)
        (tmp_path / 'out.gpkg.part').write_bytes(b'part-gpkg')

    monkeypatch.setattr(backend.scripts.prepare_water, '_run_ogr_step',
                        fake_run_ogr)

    monkeypatch.setattr(
        pyogrio,
        'read_info',
        lambda p, layer:
        {'features': 100 if layer in ('water', 'land') else 0},
    )

    res = backend.scripts.prepare_water.extract_osm_water_and_land(
        str(water_pbf), str(land_zip), str(out_gpkg), delete_inputs=True)
    assert res == str(out_gpkg)
    assert os.path.exists(out_gpkg)
    assert not os.path.exists(water_pbf)
    assert not os.path.exists(land_zip)
    assert len(ogr_cmds) == 2
    assert '--config' in ogr_cmds[0]
    assert 'OSM_CONFIG_FILE' in ogr_cmds[0]


def test_extract_osm_water_and_land_empty_layer_raises(
        tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies that empty water or land layers raise RuntimeError."""
    water_pbf = tmp_path / 'water.osm.pbf'
    water_pbf.write_bytes(b'water')
    land_zip = tmp_path / 'land.zip'
    land_zip.write_bytes(b'land')
    out_gpkg = tmp_path / 'out.gpkg'

    monkeypatch.setattr(
        backend.scripts.prepare_water,
        '_run_ogr_step',
        lambda cmd, d: (tmp_path / 'out.gpkg.part').write_bytes(b'part'),
    )
    monkeypatch.setattr(
        pyogrio,
        'read_info',
        lambda p, layer: {'features': 0},
    )

    with pytest.raises(RuntimeError, match='GeoPackage layers empty'):
        backend.scripts.prepare_water.extract_osm_water_and_land(
            str(water_pbf), str(land_zip), str(out_gpkg))


def test_resolve_water_gpkg(tmp_path: pathlib.Path) -> None:
    """Verifies resolve_water_gpkg delegates to resolve_dataset_gpkg."""
    fake_gpkg = tmp_path / 'world_osm_water.gpkg'
    fake_gpkg.write_bytes(b'gpkg-data')

    resolved = backend.scripts.prepare_water.resolve_water_gpkg(str(fake_gpkg))
    assert resolved == os.path.abspath(str(fake_gpkg))

    cfg_file = tmp_path / 'config.ini'
    cfg_file.write_text(f'[gcs]\nWATER_GPKG_PATH = "{fake_gpkg}"\n',
                        encoding='utf-8')
    resolved_cfg = backend.scripts.prepare_water.resolve_water_gpkg(
        config_path=str(cfg_file))
    assert resolved_cfg == os.path.abspath(str(fake_gpkg))


def test_subdivide_geometry() -> None:
    """Verifies geometry subdivision and short-circuit optimization."""
    # None or empty
    assert backend.scripts.prepare_water.subdivide_geometry(None) == []
    empty_poly = shapely.geometry.Polygon()
    assert backend.scripts.prepare_water.subdivide_geometry(empty_poly) == []

    # Small polygon <= max_size (short-circuit)
    small_poly = shapely.geometry.box(0, 0, 100, 100)
    sub = backend.scripts.prepare_water.subdivide_geometry(small_poly,
                                                           max_size=500.0)
    assert len(sub) == 1
    assert sub[0].equals(small_poly)

    # Large polygon > max_size
    large_poly = shapely.geometry.box(0, 0, 1000, 1000)
    sub_large = backend.scripts.prepare_water.subdivide_geometry(
        large_poly, max_size=400.0)
    assert len(sub_large) > 1


def test_prepare_complex_geometries() -> None:
    """Verifies selective shapely.prepare only for geometries >= min_vertices."""
    # Empty
    backend.scripts.prepare_water.prepare_complex_geometries([])

    # Simple 5-vertex polygon
    simple_poly = shapely.geometry.box(0, 0, 1, 1)

    # Complex polygon with > 250 vertices
    angles = np.linspace(0, 2 * np.pi, 300)
    coords = [(np.cos(a), np.sin(a)) for a in angles]
    complex_poly = shapely.geometry.Polygon(coords)

    backend.scripts.prepare_water.prepare_complex_geometries(
        [simple_poly, complex_poly], min_vertices=250)


def test_load_and_project_geometries_gpkg(
        tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies reading land and water layers from GeoPackage."""
    fake_gpkg = tmp_path / 'test.gpkg'
    fake_gpkg.write_bytes(b'gpkg')

    poly_land = shapely.geometry.box(0, 0, 1, 1)
    poly_water = shapely.geometry.box(0.2, 0.2, 0.8, 0.8)

    def fake_read(_path: str,
                  layer: str = '',
                  **_kwargs: typing.Any) -> gpd.GeoDataFrame:
        if layer == 'land':
            return gpd.GeoDataFrame(geometry=[poly_land], crs='EPSG:4326')
        if layer == 'water':
            return gpd.GeoDataFrame(geometry=[poly_water], crs='EPSG:4326')
        return gpd.GeoDataFrame()

    monkeypatch.setattr(gpd, 'read_file', fake_read)

    land_proj, water_proj = (
        backend.scripts.prepare_water.load_and_project_geometries(
            str(fake_gpkg)))
    assert not land_proj.empty
    assert not water_proj.empty
    assert land_proj.crs is not None
    assert water_proj.crs is not None
    assert land_proj.crs.to_epsg() == 6933
    assert water_proj.crs.to_epsg() == 6933


def test_spatial_filter_eval_boundary() -> None:
    """Verifies spatial filter boundary point evaluation."""
    land = shapely.geometry.box(0, 0, 10, 10)
    lake = shapely.geometry.box(2, 2, 4, 4)

    tree_land = shapely.strtree.STRtree([land])
    tree_lake = shapely.strtree.STRtree([lake])

    sf = backend.scripts.prepare_water.SpatialFilter(tree_land, tree_lake,
                                                     [land], [lake])

    # Point in lake
    lake_buf = shapely.geometry.Point(3, 3).buffer(0.1)
    assert not sf.eval_boundary_point(lake_buf, [land], [lake])

    # Point on dry land
    dry_buf = shapely.geometry.Point(7, 7).buffer(0.1)
    assert sf.eval_boundary_point(dry_buf, [land], [lake])


def test_main_cli_early_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies main() exits 0 immediately when GCS cache is fresh."""
    monkeypatch.setattr(
        backend.scripts.prepare_roads,
        'check_gcs_object_cache',
        lambda *_args, **_kwargs: 12345,
    )

    exit_code = backend.scripts.prepare_water.main(
        ['--upload-gcs', '--gcs-bucket', 'test-bucket'])
    assert exit_code == 0


def test_main_cli_full_flow(tmp_path: pathlib.Path,
                            monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies main() end-to-end execution with stage mocks."""
    out_file = tmp_path / 'world_osm_water.gpkg'

    monkeypatch.setattr(
        backend.scripts.prepare_roads,
        'check_gcs_object_cache',
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        backend.scripts.prepare_water,
        'fetch_or_cache_land_polygons_zip',
        lambda *_a, **_k: 'land.zip',
    )
    monkeypatch.setattr(
        backend.scripts.prepare_water,
        '_resolve_water_source_pbf',
        lambda *_a, **_k: 'water.osm.pbf',
    )
    monkeypatch.setattr(
        backend.scripts.prepare_water,
        'extract_osm_water_and_land',
        lambda *_a, **_k: str(out_file),
    )
    uploaded = False

    def fake_upload(*_args: typing.Any, **_kwargs: typing.Any) -> None:
        nonlocal uploaded
        uploaded = True

    monkeypatch.setattr(backend.scripts.prepare_roads, 'upload_roads_to_gcs',
                        fake_upload)

    exit_code = backend.scripts.prepare_water.main([
        '--output',
        str(out_file),
        '--upload-gcs',
        '--gcs-bucket',
        'test-bucket',
    ])
    assert exit_code == 0
    assert uploaded
