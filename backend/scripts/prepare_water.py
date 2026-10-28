"""Prepares and compiles OpenStreetMap global water and coastline datasets into a GeoPackage.

This module provides the Cloud Batch pipeline to extract global water polygons
(natural=water, waterway=riverbank, landuse=reservoir/basin, and inundated wetlands)
and pre-assembled OpenStreetMap coastline polygons (land-polygons-split-4326) into a
two-layer, R-tree-indexed GeoPackage (world_osm_water.gpkg). It also encapsulates
the high-performance spatial filtering primitives (SpatialFilter, build_spatial_filter,
subdivide_geometry) used during game generation and dashpoint rerolling.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import typing
import urllib.request
import zipfile

import geopandas as gpd
import numpy as np
import pyogrio
import shapely
import shapely.geometry
import shapely.strtree

import backend.scripts.prepare_roads

DEFAULT_WATER_GPKG_PATH = 'data/world_osm_water.gpkg'
DEFAULT_GCS_BUCKET = 'geodashing-v2-map-data'
DEFAULT_GCS_OBJECT_NAME = 'world_osm_water.gpkg'
DEFAULT_GCS_FILTERED_WATER_CACHE_OBJECT = 'cache/filtered_water.osm.pbf'
DEFAULT_GCS_LAND_ZIP_CACHE_OBJECT = 'cache/land-polygons-split-4326.zip'

LAND_POLYGONS_URL = (
    'https://osmdata.openstreetmap.de/download/land-polygons-split-4326.zip')
LAND_POLYGONS_SHP_MEMBER = 'land-polygons-split-4326/land_polygons.shp'
MIN_WATER_POLYGON_AREA_DEG2 = 5e-7
WATER_SIMPLIFY_TOLERANCE_DEG = 0.00005
PREPARE_VERTEX_THRESHOLD = 250
SIX_MONTHS_SECONDS = 180 * 24 * 3600
PREEMPTION_CACHE_MAX_AGE_SECONDS = 7 * 86400

LAKE_SUPPLEMENT_FILENAMES = (
    'ne_10m_lakes_australia.zip',
    'ne_10m_lakes_europe.zip',
    'ne_10m_lakes_north_america.zip',
)

OSMIUM_WATER_FILTER_EXPRESSIONS = (
    'wr/natural=water,wetland',
    'wr/waterway=riverbank',
    'wr/landuse=reservoir,basin',
)

EXCLUDED_WATER_TYPES = (
    'ditch',
    'drain',
    'wastewater',
    'moat',
    'reflecting_pool',
)

INUNDATED_WETLAND_TYPES = (
    'tidalflat',
    'swamp',
    'marsh',
    'mangrove',
    'reedbed',
    'bog',
    'fen',
    'saltmarsh',
)


def build_water_where_clause(
    min_area_deg2: float = MIN_WATER_POLYGON_AREA_DEG2, ) -> str:
    """Constructs the OGRSQL WHERE clause for filtering OSM water multipolygons.

    Args:
        min_area_deg2: Minimum polygon area threshold in square degrees.

    Returns:
        SQL WHERE clause string for ogr2ogr.
    """
    excluded_water = ', '.join(f"'{val}'" for val in EXCLUDED_WATER_TYPES)
    inundated = ', '.join(f"'{val}'" for val in INUNDATED_WETLAND_TYPES)
    water_core = (
        "(natural = 'water' OR waterway = 'riverbank' "
        "OR landuse IN ('reservoir', 'basin') "
        f"OR (natural = 'wetland' AND (wetland IS NULL OR wetland IN ({inundated}))))"
    )
    exclusions = (
        f"(water IS NULL OR water NOT IN ({excluded_water})) "
        "AND (intermittent IS NULL OR intermittent NOT IN ('yes', '1', 'true')) "
        "AND (seasonal IS NULL OR seasonal NOT IN ('yes', '1', 'true', "
        "'spring', 'summer', 'autumn', 'winter', 'wet_season', 'dry_season')) "
        "AND (tunnel IS NULL OR tunnel IN ('no', '0', 'false')) "
        "AND (covered IS NULL OR covered IN ('no', '0', 'false')) "
        "AND (location IS NULL OR location NOT IN ('underground', 'indoor', 'roof'))"
    )
    return (
        f"{water_core} AND ({exclusions}) AND OGR_GEOM_AREA >= {min_area_deg2}"
    )


def write_water_osmconf(directory: str) -> str:
    """Generates an osmconf.ini file configured for water multipolygon extraction.

    Args:
        directory: Directory where osmconf.ini should be created.

    Returns:
        Absolute path to the created osmconf.ini file.
    """
    path = os.path.join(directory, 'osmconf_water.ini')
    content = (
        '[multipolygons]\n'
        'osm_id=yes\n'
        'osm_version=no\n'
        'osm_timestamp=no\n'
        'osm_uid=no\n'
        'osm_user=no\n'
        'osm_changeset=no\n'
        'attributes=natural,water,wetland,waterway,landuse,intermittent,seasonal,'
        'tunnel,covered,location\n'
        'other_tags=no\n')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return path


def verify_land_zip(zip_path: str, expected_size: int | None = None) -> bool:
    """Verifies existence, byte size, and internal zip integrity of land polygons.

    Args:
        zip_path: Path to the land polygons zip file.
        expected_size: Optional expected byte size.

    Returns:
        bool: True if file exists and contains the expected shapefile member.
    """
    if not os.path.exists(zip_path):
        return False
    size = os.path.getsize(zip_path)
    size_valid = size > 0 and (expected_size is None or expected_size <= 0
                               or size == expected_size)
    if not size_valid:
        return False
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            has_shp = LAND_POLYGONS_SHP_MEMBER in set(zf.namelist())
            return has_shp and zf.testzip() is None
    except (zipfile.BadZipFile, OSError):
        return False


def fetch_or_cache_land_polygons_zip(
    dest_path: str,
    bucket_name: str | None = None,
    cache_object: str = DEFAULT_GCS_LAND_ZIP_CACHE_OBJECT,
    force: bool = False,
    credentials_path: str | None = None,
) -> str:
    """Downloads and verifies land-polygons-split-4326.zip, checking GCS cache first.

    Args:
        dest_path: Local destination file path.
        bucket_name: Optional GCS bucket name for 7-day checkpoint cache.
        cache_object: GCS object name for cached zip.
        force: If True, ignores GCS cache and downloads fresh.
        credentials_path: Optional service account credentials path.

    Returns:
        Path to the verified land polygons zip file.

    Raises:
        RuntimeError: If download or verification fails.
    """
    if os.path.exists(dest_path) and verify_land_zip(dest_path):
        return dest_path

    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    if bucket_name and not force:
        cached_size = backend.scripts.prepare_roads.check_gcs_object_cache(
            bucket_name,
            credentials_path=credentials_path,
            object_name=cache_object,
        )
        if cached_size is not None:
            print(
                f"Found fresh GCS land polygons cache gs://{bucket_name}/{cache_object}."
            )
            backend.scripts.prepare_roads.download_roads_from_gcs(
                dest_path,
                bucket_name,
                credentials_path=credentials_path,
                object_name=cache_object,
            )
            if verify_land_zip(dest_path, expected_size=cached_size):
                return dest_path
            print(
                "Cached GCS land polygons failed verification; redownloading.")

    part_path = f"{dest_path}.part"
    if os.path.exists(part_path):
        os.remove(part_path)

    print(f"Downloading {LAND_POLYGONS_URL} to {part_path}...")
    if shutil.which('aria2c'):
        cmd = [
            'aria2c',
            '-x',
            '4',
            '-s',
            '4',
            '-k',
            '2M',
            '--allow-overwrite=true',
            '-d',
            os.path.dirname(os.path.abspath(part_path)),
            '-o',
            os.path.basename(part_path),
            LAND_POLYGONS_URL,
        ]
        subprocess.run(cmd, check=True)
    else:
        urllib.request.urlretrieve(LAND_POLYGONS_URL, part_path)

    if not verify_land_zip(part_path):
        raise RuntimeError(
            f"Downloaded land polygons zip failed verification: {part_path}")
    os.replace(part_path, dest_path)

    if bucket_name:
        try:
            print(
                f"Caching land polygons zip to gs://{bucket_name}/{cache_object}..."
            )
            backend.scripts.prepare_roads.upload_roads_to_gcs(
                dest_path,
                bucket_name,
                credentials_path=credentials_path,
                object_name=cache_object,
            )
        except (OSError, RuntimeError) as exc:
            print(f"Warning: Caching land zip to GCS failed ({exc}).")

    return dest_path


def fetch_cached_filtered_water_pbf(
    dest_path: str,
    bucket_name: str,
    cache_object: str = DEFAULT_GCS_FILTERED_WATER_CACHE_OBJECT,
    credentials_path: str | None = None,
) -> bool:
    """Downloads and verifies 7-day cached filtered_water.osm.pbf from GCS.

    Args:
        dest_path: Local destination path for verified PBF.
        bucket_name: GCS bucket name.
        cache_object: GCS object path.
        credentials_path: Optional service account credentials path.

    Returns:
        bool: True if cached file exists, was downloaded, and verified.
    """
    cached_size = backend.scripts.prepare_roads.check_gcs_object_cache(
        bucket_name,
        credentials_path=credentials_path,
        object_name=cache_object,
    )
    if cached_size is None:
        return False

    print(
        f"Found fresh GCS water cache gs://{bucket_name}/{cache_object} ({cached_size} bytes)."
    )
    try:
        backend.scripts.prepare_roads.download_roads_from_gcs(
            dest_path,
            bucket_name,
            credentials_path=credentials_path,
            object_name=cache_object,
        )
        backend.scripts.prepare_roads.verify_pbf_download(
            dest_path, expected_size=cached_size)
        return True
    except (OSError, RuntimeError) as exc:
        print(f"Warning: Downloading cached filtered water PBF failed: {exc}")
        if os.path.exists(dest_path):
            os.remove(dest_path)
        return False


def filter_planet_water_pbf(
    input_pbf: str,
    output_pbf: str,
    delete_input: bool = False,
    bucket_name: str | None = None,
    credentials_path: str | None = None,
) -> str:
    """Extracts water relations and ways from planet PBF via osmium tags-filter.

    Args:
        input_pbf: Path to input raw planet PBF.
        output_pbf: Path to output filtered PBF.
        delete_input: If True, deletes input_pbf immediately to free local disk.
        bucket_name: Optional GCS bucket name to cache filtered water PBF.
        credentials_path: Optional service account credentials path.

    Returns:
        Path to output_pbf.

    Raises:
        RuntimeError: If osmium execution or verification fails.
    """
    part_path = f"{output_pbf}.part"
    if os.path.exists(part_path):
        os.remove(part_path)

    cmd_osmium = (['osmium', 'tags-filter', input_pbf] +
                  list(OSMIUM_WATER_FILTER_EXPRESSIONS) +
                  ['-o', part_path, '--output-format=pbf', '--overwrite'])
    print(f"Running osmium tags-filter on {input_pbf}...")
    subprocess.run(cmd_osmium, check=True)
    backend.scripts.prepare_roads.verify_pbf_download(part_path,
                                                      expected_size=0)
    os.replace(part_path, output_pbf)

    if delete_input and os.path.exists(input_pbf):
        print(f"Deleting raw planet PBF {input_pbf} to free disk space...")
        os.remove(input_pbf)

    if bucket_name:
        try:
            print(f"Caching filtered water PBF to gs://{bucket_name}/"
                  f"{DEFAULT_GCS_FILTERED_WATER_CACHE_OBJECT}...")
            backend.scripts.prepare_roads.upload_roads_to_gcs(
                output_pbf,
                bucket_name,
                credentials_path=credentials_path,
                object_name=DEFAULT_GCS_FILTERED_WATER_CACHE_OBJECT,
            )
        except (OSError, RuntimeError) as exc:
            print(f"Warning: Caching filtered water PBF failed: {exc}")

    return output_pbf


def _run_ogr_step(cmd: list[str], work_dir: str) -> None:
    """Executes an ogr2ogr command with configured SQLite and VSI memory limits."""
    env = backend.scripts.prepare_roads.get_ogr2ogr_env(work_dir)
    subprocess.run(cmd, check=True, env=env)


def extract_osm_water_and_land(water_pbf: str,
                               land_zip: str,
                               output_gpkg: str,
                               delete_inputs: bool = False) -> str:
    """Compiles water and land layers into an R-tree indexed GeoPackage.

    Args:
        water_pbf: Path to pre-filtered water PBF file.
        land_zip: Path to verified land-polygons-split-4326.zip.
        output_gpkg: Destination .gpkg path.
        delete_inputs: If True, deletes input files as steps complete.

    Returns:
        Path to output_gpkg.

    Raises:
        RuntimeError: If ogr2ogr execution or layer verification fails.
    """
    work_dir = os.path.dirname(os.path.abspath(output_gpkg))
    part_gpkg = f"{output_gpkg}.part"
    if os.path.exists(part_gpkg):
        os.remove(part_gpkg)

    with tempfile.TemporaryDirectory(dir=work_dir) as tmp_dir:
        osmconf_path = write_water_osmconf(tmp_dir)
        where_clause = build_water_where_clause()

        # Step 3a: Extract 'water' layer from PBF multipolygons
        print(f"Extracting 'water' layer from {water_pbf} to {part_gpkg}...")
        cmd_water = [
            'ogr2ogr',
            '-f',
            'GPKG',
            '-select',
            '',
            '-nln',
            'water',
            '-where',
            where_clause,
            '--config',
            'OSM_CONFIG_FILE',
            osmconf_path,
            part_gpkg,
            water_pbf,
            'multipolygons',
            '-simplify',
            str(WATER_SIMPLIFY_TOLERANCE_DEG),
            '-makevalid',
            '-explodecollections',
            '-nlt',
            'POLYGON',
            '-lco',
            'SPATIAL_INDEX=YES',
            '-gt',
            '100000',
        ]
        _run_ogr_step(cmd_water, work_dir)

    if delete_inputs and os.path.exists(water_pbf):
        print(f"Deleting filtered water PBF {water_pbf}...")
        os.remove(water_pbf)

    # Step 3b: Append 'land' layer from land-polygons-split-4326.zip
    abs_land_zip = os.path.abspath(land_zip)
    vsi_shp = f"/vsizip/{abs_land_zip}/{LAND_POLYGONS_SHP_MEMBER}"
    print(f"Appending 'land' layer from {vsi_shp} to {part_gpkg}...")
    cmd_land = [
        'ogr2ogr',
        '-update',
        '-append',
        part_gpkg,
        vsi_shp,
        '-select',
        '',
        '-nln',
        'land',
        '-makevalid',
        '-explodecollections',
        '-nlt',
        'POLYGON',
        '-lco',
        'SPATIAL_INDEX=YES',
        '-gt',
        '100000',
    ]
    _run_ogr_step(cmd_land, work_dir)

    if delete_inputs and os.path.exists(land_zip):
        print(f"Deleting land polygons zip {land_zip}...")
        os.remove(land_zip)

    # Verify both layers exist and have features
    info_water = pyogrio.read_info(part_gpkg, layer='water')
    info_land = pyogrio.read_info(part_gpkg, layer='land')
    if (info_water.get('features', 0) <= 0
            or info_land.get('features', 0) <= 0):
        raise RuntimeError(
            f"GeoPackage layers empty: water={info_water.get('features')}, "
            f"land={info_land.get('features')}")

    os.replace(part_gpkg, output_gpkg)
    print(f"Successfully compiled {output_gpkg}.")
    return output_gpkg


def resolve_water_gpkg(
    water_gpkg_path: str | None = None,
    config_path: str = 'backend/config.ini',
    max_age_s: int = SIX_MONTHS_SECONDS,
) -> str:
    """Resolves and validates the local water GeoPackage path and freshness.

    Args:
        water_gpkg_path: Optional explicit local path to check.
        config_path: Path to backend config.ini.
        max_age_s: Maximum allowed age of the dataset file in seconds.

    Returns:
        Absolute path to the existing, non-empty, and fresh .gpkg file.
    """
    return backend.scripts.prepare_roads.resolve_dataset_gpkg(
        dataset_path=water_gpkg_path,
        config_path=config_path,
        config_option='WATER_GPKG_PATH',
        default_path=DEFAULT_WATER_GPKG_PATH,
        max_age_s=max_age_s,
    )


# =============================================================================
# Spatial Filtering & Geometry Primitives
# =============================================================================


def subdivide_geometry(
    geom: shapely.geometry.base.BaseGeometry | None,
    max_size: float = 1000000.0,
) -> list[shapely.geometry.base.BaseGeometry]:
    """Subdivides a geometry into smaller grid geometries if bounds exceed max_size."""
    if geom is None or geom.is_empty:
        return []
    minx, miny, maxx, maxy = geom.bounds
    if (maxx - minx) <= max_size and (maxy - miny) <= max_size:
        if geom.geom_type == 'Polygon':
            return [geom]
        if geom.geom_type == 'MultiPolygon':
            return [
                part for part in shapely.get_parts(geom)
                if part.geom_type in ('Polygon', 'MultiPolygon')
            ]

    x_coords = np.arange(minx, maxx + max_size, max_size)
    y_coords = np.arange(miny, maxy + max_size, max_size)
    grid_boxes: list[shapely.geometry.Polygon] = []
    for i in range(len(x_coords) - 1):
        for j in range(len(y_coords) - 1):
            grid_boxes.append(
                shapely.geometry.box(x_coords[i], y_coords[j], x_coords[i + 1],
                                     y_coords[j + 1]))

    subdivided: list[shapely.geometry.base.BaseGeometry] = []
    for box in grid_boxes:
        if not geom.intersects(box):
            continue
        inter = geom.intersection(box)
        if inter.is_empty:
            continue
        for g in shapely.get_parts(inter):
            if g.geom_type in ('Polygon', 'MultiPolygon'):
                subdivided.append(g)
    return subdivided


def resolve_lake_zip_paths(lakes_zip_path: str) -> list[str]:
    """Resolves lake shapefile paths, expanding default ne_10m_lakes.zip with supplements."""
    if os.path.basename(lakes_zip_path) == 'ne_10m_lakes.zip':
        base_dir = os.path.dirname(lakes_zip_path)
        return [lakes_zip_path] + [
            os.path.join(base_dir, name) for name in LAKE_SUPPLEMENT_FILENAMES
        ]
    return [lakes_zip_path]


def _project_and_validate_gdf(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Converts a GeoDataFrame to EPSG:6933 and repairs invalid geometries."""
    if gdf.empty:
        return gpd.GeoDataFrame(geometry=[], crs='EPSG:6933')
    proj = gdf.to_crs(epsg=6933)
    invalid_mask = ~proj.geometry.is_valid
    if invalid_mask.any():
        repaired = proj.geometry.copy()
        repaired.loc[invalid_mask] = repaired.loc[invalid_mask].make_valid()
        return gpd.GeoDataFrame(geometry=repaired, crs='EPSG:6933')
    return proj


def load_and_project_geometries(
    land_path: str,
    lakes_path: str = '',
    verbose: bool = True,
    bbox: tuple[float, float, float, float] | None = None,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Loads and projects land and lake geometries to EPSG:6933.

    Args:
        land_path: Path to .gpkg file or legacy land shapefile zip.
        lakes_path: Optional path to legacy lakes shapefile zip.
        verbose: Whether to print progress messages.
        bbox: Optional (minx, miny, maxx, maxy) bounding box filter.

    Returns:
        tuple[GeoDataFrame, GeoDataFrame]: (land_proj, lakes_proj) in EPSG:6933.
    """
    if land_path.lower().endswith('.gpkg'):
        try:
            if bbox is not None:
                land_gdf = gpd.read_file(land_path, layer='land', bbox=bbox)
                water_gdf = gpd.read_file(land_path, layer='water', bbox=bbox)
            else:
                land_gdf = gpd.read_file(land_path, layer='land')
                water_gdf = gpd.read_file(land_path, layer='water')
        except Exception as exc:
            raise FileNotFoundError(
                f"Failed to read GeoPackage layers from {land_path}: {exc}"
            ) from exc
    else:
        lake_paths = resolve_lake_zip_paths(lakes_path)
        try:
            if bbox is not None:
                land_gdf = gpd.read_file(f"zip://{land_path}", bbox=bbox)
                lake_gdfs = [
                    gpd.read_file(f"zip://{p}", bbox=bbox) for p in lake_paths
                ]
            else:
                land_gdf = gpd.read_file(f"zip://{land_path}")
                lake_gdfs = [gpd.read_file(f"zip://{p}") for p in lake_paths]
            water_geoms: list[shapely.geometry.base.BaseGeometry] = []
            for lgdf in lake_gdfs:
                water_geoms.extend(lgdf.geometry.tolist())
            water_gdf = gpd.GeoDataFrame(geometry=water_geoms,
                                         crs=land_gdf.crs or 'EPSG:4326')
        except Exception as exc:
            raise FileNotFoundError(
                f"Failed to read shapefiles: {exc}") from exc

    if verbose:
        print("Projecting land and water geometries to EPSG:6933...")
    land_proj = _project_and_validate_gdf(land_gdf)
    water_proj = _project_and_validate_gdf(water_gdf)
    return land_proj, water_proj


def prepare_complex_geometries(
    geoms: list[shapely.geometry.base.BaseGeometry],
    min_vertices: int = PREPARE_VERTEX_THRESHOLD,
) -> None:
    """Prepares only geometries with coordinate counts meeting min_vertices threshold."""
    if not geoms:
        return
    coord_counts = shapely.get_num_coordinates(geoms)
    complex_geoms = [
        geom for geom, count in zip(geoms, coord_counts)
        if count >= min_vertices
    ]
    if complex_geoms:
        shapely.prepare(complex_geoms)


class SpatialFilter:
    """Encapsulates spatial indexing and boundary dry-land filtering logic."""

    def __init__(
        self,
        tree_land: shapely.strtree.STRtree,
        tree_lakes: shapely.strtree.STRtree,
        land_sub: list[shapely.geometry.base.BaseGeometry],
        lakes_sub: list[shapely.geometry.base.BaseGeometry],
    ) -> None:
        """Initializes spatial trees and geometry lists."""
        self.tree_land = tree_land
        self.tree_lakes = tree_lakes
        self.land_sub = land_sub
        self.lakes_sub = lakes_sub

    def get_candidate_matches(
        self, buffers: typing.Any
    ) -> tuple[
            dict[int, list[shapely.geometry.base.BaseGeometry]],
            dict[int, list[shapely.geometry.base.BaseGeometry]],
    ]:
        """Finds matching land and lake geometries for each buffered point."""
        land_matches = self.tree_land.query(buffers)
        land_map: dict[int, list[shapely.geometry.base.BaseGeometry]] = {}
        if land_matches.size > 0:
            for buf_idx, land_idx in zip(land_matches[0], land_matches[1]):
                land_map.setdefault(buf_idx,
                                    []).append(self.land_sub[land_idx])

        lake_matches = self.tree_lakes.query(buffers)
        lake_map: dict[int, list[shapely.geometry.base.BaseGeometry]] = {}
        if lake_matches.size > 0:
            for buf_idx, lake_idx in zip(lake_matches[0], lake_matches[1]):
                lake_map.setdefault(buf_idx,
                                    []).append(self.lakes_sub[lake_idx])

        return land_map, lake_map

    def eval_boundary_point(
        self,
        buffer_geom: shapely.geometry.base.BaseGeometry,
        matching_lands: list[shapely.geometry.base.BaseGeometry],
        matching_lakes: list[shapely.geometry.base.BaseGeometry],
    ) -> bool:
        """Determines if a single buffered point intersects dry land."""
        if len(matching_lands) == 1:
            land_geom = matching_lands[0]
        else:
            land_geom = shapely.union_all(matching_lands)

        if matching_lakes:
            if len(matching_lakes) == 1:
                lake_geom = matching_lakes[0]
            else:
                lake_geom = shapely.union_all(matching_lakes)
            land_minus_lakes = land_geom.difference(lake_geom)
        else:
            land_minus_lakes = land_geom

        return buffer_geom.intersects(land_minus_lakes)

    def _filter_batch_indices(
            self, batch_points: list[shapely.geometry.Point]) -> set[int]:
        """Filters a single batch of points and returns the valid local indices."""
        proj_geoms = (gpd.GeoDataFrame(
            geometry=batch_points,
            crs='EPSG:4326').to_crs(epsg=6933).geometry.tolist())

        land_contains = self.tree_land.query(proj_geoms, predicate='contains')
        on_land = set(land_contains[0])
        lake_contains = self.tree_lakes.query(proj_geoms, predicate='contains')
        in_lakes = set(lake_contains[0])

        valid = on_land - in_lakes
        remaining = [i for i in range(len(batch_points)) if i not in valid]
        if remaining:
            remaining_buffers = shapely.buffer(
                [proj_geoms[i] for i in remaining], 100)
            land_map, lake_map = self.get_candidate_matches(remaining_buffers)
            for buf_idx, lands in land_map.items():
                if self.eval_boundary_point(
                        remaining_buffers[buf_idx],
                        lands,
                        lake_map.get(buf_idx, []),
                ):
                    valid.add(remaining[buf_idx])

        return valid

    def filter_valid_indices(
            self, raw_points: list[shapely.geometry.Point]) -> set[int]:
        """Identifies indices of points situated on dry land or within 100m offshore."""
        if not raw_points:
            return set()

        batch_size = 50000
        valid_indices: set[int] = set()
        for offset in range(0, len(raw_points), batch_size):
            batch = raw_points[offset:offset + batch_size]
            batch_valid = self._filter_batch_indices(batch)
            valid_indices.update(offset + idx for idx in batch_valid)

        return valid_indices


def build_spatial_filter(
    land_path: str = DEFAULT_WATER_GPKG_PATH,
    lakes_path: str = '',
    verbose: bool = True,
    bbox: tuple[float, float, float, float] | None = None,
) -> SpatialFilter:
    """Loads datasets, subdivides them, and builds a SpatialFilter instance."""
    land_proj, lakes_proj = load_and_project_geometries(land_path,
                                                        lakes_path,
                                                        verbose=verbose,
                                                        bbox=bbox)

    if verbose:
        print("Subdividing land and water geometries...")
    land_sub: list[shapely.geometry.base.BaseGeometry] = []
    for geom in land_proj.geometry:
        if geom is not None and not geom.is_empty:
            land_sub.extend(subdivide_geometry(geom, max_size=1000000.0))

    lakes_sub: list[shapely.geometry.base.BaseGeometry] = []
    for geom in lakes_proj.geometry:
        if geom is not None and not geom.is_empty:
            lakes_sub.extend(subdivide_geometry(geom, max_size=1000000.0))

    if verbose:
        print("Building spatial indexes...")
    tree_land = shapely.strtree.STRtree(land_sub)
    tree_lakes = shapely.strtree.STRtree(lakes_sub)

    if verbose:
        print("Selectively preparing complex geometries...")
    prepare_complex_geometries(land_sub)
    prepare_complex_geometries(lakes_sub)

    return SpatialFilter(tree_land, tree_lakes, land_sub, lakes_sub)


# =============================================================================
# CLI Entrypoint
# =============================================================================


def _parse_cli_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parses command line arguments for prepare_water script."""
    parser = argparse.ArgumentParser(
        description="Prepare OpenStreetMap water and coastline GeoPackage")
    parser.add_argument(
        '--input',
        default='planet-latest.osm.pbf',
        help="Input raw planet or pre-filtered OSM PBF path",
    )
    parser.add_argument(
        '--land-zip',
        default='data/cache/land-polygons-split-4326.zip',
        help="Path to land-polygons-split-4326.zip",
    )
    parser.add_argument(
        '--output',
        default=DEFAULT_WATER_GPKG_PATH,
        help="Destination .gpkg file path",
    )
    parser.add_argument(
        '--download-planet-osm',
        action='store_true',
        help="Download raw planet OSM PBF from mirrors or GCS cache if missing",
    )
    parser.add_argument(
        '--delete-input',
        action='store_true',
        help="Delete intermediate PBF and zip files to conserve disk space",
    )
    parser.add_argument(
        '--upload-gcs',
        action='store_true',
        help="Upload the compiled GeoPackage to Google Cloud Storage",
    )
    parser.add_argument(
        '--gcs-bucket',
        default=DEFAULT_GCS_BUCKET,
        help="Destination GCS bucket name",
    )
    parser.add_argument(
        '--gcs-object',
        default=DEFAULT_GCS_OBJECT_NAME,
        help="Destination GCS object name",
    )
    parser.add_argument(
        '--credentials',
        default=None,
        help="Path to Google Cloud service account JSON credentials",
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help="Force regeneration even if fresh GCS output exists",
    )
    return parser.parse_args(argv)


def _resolve_water_source_pbf(args: argparse.Namespace,
                              scratch_dir: str) -> str:
    """Resolves or prepares the filtered water PBF file."""
    filtered_pbf = os.path.join(scratch_dir, 'filtered_water.osm.pbf')
    if os.path.exists(filtered_pbf):
        return filtered_pbf

    if args.upload_gcs and fetch_cached_filtered_water_pbf(
            filtered_pbf,
            args.gcs_bucket,
            credentials_path=args.credentials,
    ):
        return filtered_pbf

    input_pbf = args.input
    if not os.path.exists(input_pbf) and args.download_planet_osm:
        input_pbf = backend.scripts.prepare_roads.fetch_or_cache_planet_pbf(
            input_pbf,
            bucket_name=args.gcs_bucket,
            credentials_path=args.credentials,
        )

    bucket = args.gcs_bucket if args.upload_gcs else None
    return filter_planet_water_pbf(
        input_pbf,
        filtered_pbf,
        delete_input=args.delete_input,
        bucket_name=bucket,
        credentials_path=args.credentials,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI execution entry point."""
    args = _parse_cli_args(argv)
    scratch_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(scratch_dir, exist_ok=True)

    if (args.upload_gcs and not args.force
            and backend.scripts.prepare_roads.check_gcs_object_cache(
                args.gcs_bucket,
                credentials_path=args.credentials,
                object_name=args.gcs_object,
            ) is not None):
        print("Fresh GeoPackage already exists in GCS. Exiting 0.")
        return 0

    land_zip = fetch_or_cache_land_polygons_zip(
        args.land_zip,
        bucket_name=args.gcs_bucket if args.upload_gcs else None,
        force=args.force,
        credentials_path=args.credentials,
    )

    source_pbf = _resolve_water_source_pbf(args, scratch_dir)

    extract_osm_water_and_land(
        source_pbf,
        land_zip,
        args.output,
        delete_inputs=args.delete_input,
    )

    if args.upload_gcs:
        backend.scripts.prepare_roads.upload_roads_to_gcs(
            args.output,
            args.gcs_bucket,
            credentials_path=args.credentials,
            object_name=args.gcs_object,
        )

    return 0


if __name__ == '__main__':
    sys.exit(main())
