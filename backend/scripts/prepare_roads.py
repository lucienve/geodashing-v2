"""Utility script for preparing, filtering, and caching global drivable road data."""

import argparse
import configparser
import math
import os
import shutil
import subprocess
import sys
import urllib.parse

import geopandas as gpd
import google.auth
import google.auth.transport.requests
import google.oauth2.service_account
import numpy as np
import pyogrio
import shapely
import shapely.affinity
import shapely.geometry
import shapely.geometry.base

EARTH_RADIUS_KM: float = 6371.0088
DEFAULT_ROADS_GPKG_PATH: str = 'data/world_drivable_roads.gpkg'
DEFAULT_MAP_BUCKET_NAME: str = 'geodashing-v2-map-data'
RESUMABLE_CHUNK_SIZE: int = 32 * 1024 * 1024  # 32 MiB chunks

QUALIFYING_HIGHWAY_TYPES: set[str] = {
    'primary',
    'secondary',
    'tertiary',
    'unclassified',
    'residential',
    'primary_link',
    'secondary_link',
    'tertiary_link',
}

EXCLUDED_ACCESS_VALUES: set[str] = {
    'private',
    'no',
    'customers',
    'military',
    'permit',
    'agricultural',
    'forestry',
}


def filter_drivable_roads(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Filters a GeoDataFrame of road segments down to qualifying public drivable roads.

    Args:
        gdf: Raw input road geometries and attributes.

    Returns:
        Cleaned GeoDataFrame with only qualifying drivable roads,
        stripped of non-essential attributes, projected in EPSG:4326.
    """
    if gdf.empty:
        return gpd.GeoDataFrame(
            geometry=gpd.GeoSeries([], dtype='geometry'),
            crs=gdf.crs or 'EPSG:4326',
        )

    filtered = gdf.copy()
    col_map = {col: str(col).lower() for col in filtered.columns}
    filtered = filtered.rename(columns=col_map)

    if 'highway' in filtered.columns:
        filtered = filtered[[
            str(h).lower() in QUALIFYING_HIGHWAY_TYPES
            for h in filtered['highway']
        ]]

    if 'access' in filtered.columns:
        filtered = filtered[[
            str(a).lower() not in EXCLUDED_ACCESS_VALUES
            for a in filtered['access']
        ]]

    valid_geom_types = ('LineString', 'MultiLineString')
    filtered = filtered[[
        geom is not None and not geom.is_empty
        and geom.geom_type in valid_geom_types for geom in filtered.geometry
    ]]

    filtered = filtered.explode(column='geometry', ignore_index=True)
    filtered = filtered[[
        geom is not None and not geom.is_empty and geom.is_valid
        for geom in filtered.geometry
    ]]

    result = gpd.GeoDataFrame(geometry=filtered.geometry,
                              crs=filtered.crs or 'EPSG:4326')
    if result.crs is None or result.crs.to_epsg() != 4326:
        result = result.to_crs(epsg=4326)

    return result


def export_roads_geopackage(gdf: gpd.GeoDataFrame, output_path: str) -> None:
    """Exports road geometries to a GeoPackage file with an R-tree spatial index.

    Args:
        gdf: Filtered road geometries.
        output_path: Destination path for the .gpkg file.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    if os.path.exists(output_path):
        os.remove(output_path)

    gdf.to_file(output_path, driver='GPKG', layer='roads', engine='pyogrio')


def _write_osmconf_ini(conf_path: str) -> None:
    """Writes a minimal osmconf.ini extracting only highway and access columns."""
    content = ("[lines]\n"
               "osm_id=no\n"
               "osm_version=no\n"
               "osm_timestamp=no\n"
               "osm_uid=no\n"
               "osm_user=no\n"
               "osm_changeset=no\n"
               "attributes=highway,access\n"
               "other_tags=no\n")
    with open(conf_path, 'w', encoding='utf-8') as f:
        f.write(content)


def process_osm_pbf_to_gpkg(
    input_pbf: str,
    output_gpkg: str,
    delete_input: bool = False,
) -> None:
    """Compiles an OSM PBF extract into a filtered, R-tree indexed GeoPackage.

    Args:
        input_pbf: Path to the raw .osm.pbf file.
        output_gpkg: Destination .gpkg path.
        delete_input: If True, removes input_pbf after processing.

    Raises:
        FileNotFoundError: If input_pbf does not exist.
        RuntimeError: If osmium or ogr2ogr subprocess execution fails.
    """
    if not os.path.exists(input_pbf):
        raise FileNotFoundError(f"Input OSM PBF not found: {input_pbf}")

    work_dir = os.path.dirname(os.path.abspath(output_gpkg))
    os.makedirs(work_dir, exist_ok=True)

    filtered_pbf = os.path.join(work_dir, 'filtered_roads.osm.pbf')
    osmconf_path = os.path.join(work_dir, 'osmconf.ini')
    source_pbf = input_pbf

    try:
        if shutil.which('osmium'):
            print(f"Running osmium tags-filter on {input_pbf}...")
            hw_filter = ','.join(sorted(QUALIFYING_HIGHWAY_TYPES))
            cmd_osmium = [
                'osmium',
                'tags-filter',
                input_pbf,
                f'w/highway={hw_filter}',
                '-o',
                filtered_pbf,
                '--overwrite',
            ]
            subprocess.run(cmd_osmium, check=True)
            source_pbf = filtered_pbf

        _write_osmconf_ini(osmconf_path)

        access_cond = ' AND '.join(f"(access IS NULL OR access != '{val}')"
                                   for val in sorted(EXCLUDED_ACCESS_VALUES))
        hw_cond = 'highway IN (' + ','.join(
            f"'{val}'" for val in sorted(QUALIFYING_HIGHWAY_TYPES)) + ')'
        where_clause = f'{hw_cond} AND ({access_cond})'

        if os.path.exists(output_gpkg):
            os.remove(output_gpkg)

        env = os.environ.copy()
        env['CPL_TMPDIR'] = work_dir
        env['SQLITE_TMPDIR'] = work_dir
        env['OGR_SQLITE_CACHE'] = '4096'
        env['OGR_SQLITE_SYNCHRONOUS'] = 'OFF'

        cmd_ogr = [
            'ogr2ogr',
            '-f',
            'GPKG',
            output_gpkg,
            source_pbf,
            'lines',
            '--config',
            'OSM_CONFIG_FILE',
            osmconf_path,
            '-where',
            where_clause,
            '-select',
            '',
            '-nln',
            'roads',
            '-explodecollections',
            '-nlt',
            'PROMOTE_TO_MULTI',
            '-lco',
            'SPATIAL_INDEX=YES',
            '-gt',
            '100000',
        ]
        print(f"Running ogr2ogr to generate {output_gpkg}...")
        subprocess.run(cmd_ogr, check=True, env=env)
        print("GeoPackage compilation completed successfully.")

    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Road processing command failed: {exc}") from exc
    finally:
        if os.path.exists(osmconf_path):
            os.remove(osmconf_path)
        if os.path.exists(filtered_pbf):
            os.remove(filtered_pbf)
        if delete_input and os.path.exists(input_pbf):
            os.remove(input_pbf)


def get_gcs_session(
    credentials_path: str | None = None,
) -> tuple[google.auth.transport.requests.AuthorizedSession, str]:
    """Initializes an authenticated Google Cloud Storage HTTP session.

    Falls back to Application Default Credentials when credentials_path is missing.

    Args:
        credentials_path: Optional path to service account JSON file.

    Returns:
        tuple[AuthorizedSession, str]: Authenticated requests session and project ID.
    """
    scopes = ['https://www.googleapis.com/auth/devstorage.read_write']
    if credentials_path and os.path.exists(credentials_path):
        creds = google.oauth2.service_account.Credentials.from_service_account_file(
            credentials_path, scopes=scopes)
        project_id = creds.project_id or 'geodashing-v2'
    else:
        creds, project_id = google.auth.default(scopes=scopes)
        if not project_id:
            project_id = 'geodashing-v2'

    session = google.auth.transport.requests.AuthorizedSession(creds)
    return session, project_id


def _stream_chunks_to_gcs(
    session: google.auth.transport.requests.AuthorizedSession,
    upload_url: str,
    local_path: str,
    total_size: int,
) -> None:
    """Streams file chunks to GCS resumable upload endpoint."""
    with open(local_path, 'rb') as f:
        bytes_sent = 0
        while bytes_sent < total_size:
            chunk = f.read(RESUMABLE_CHUNK_SIZE)
            chunk_len = len(chunk)
            start = bytes_sent
            end = bytes_sent + chunk_len - 1
            headers = {
                'Content-Range': f'bytes {start}-{end}/{total_size}',
                'Content-Type': 'application/geopackage+sqlite3',
            }
            resp = session.put(upload_url,
                               data=chunk,
                               headers=headers,
                               timeout=300)
            if end + 1 == total_size:
                if resp.status_code not in (200, 201):
                    raise RuntimeError(
                        f'Final chunk failed ({resp.status_code}): {resp.text}'
                    )
            else:
                if resp.status_code != 308:
                    raise RuntimeError(
                        f'Chunk upload failed ({resp.status_code}): {resp.text}'
                    )
            bytes_sent += chunk_len


def upload_roads_to_gcs(
    local_path: str,
    bucket_name: str,
    credentials_path: str | None = None,
    object_name: str = 'world_drivable_roads.gpkg',
) -> None:
    """Uploads the road GeoPackage to Google Cloud Storage via resumable streaming.

    Args:
        local_path: Path to local .gpkg file.
        bucket_name: Name of the GCS bucket.
        credentials_path: Path to service account JSON credentials or None for ADC.
        object_name: Destination GCS object name.

    Raises:
        FileNotFoundError: If the local file does not exist.
        RuntimeError: If GCS initiation or upload fails.
    """
    if not os.path.exists(local_path):
        raise FileNotFoundError(f"Local file does not exist: {local_path}")

    session, _ = get_gcs_session(credentials_path)
    encoded_name = urllib.parse.quote(object_name, safe='')
    init_url = (f'https://storage.googleapis.com/upload/storage/v1/b/'
                f'{bucket_name}/o?uploadType=resumable&name={encoded_name}')

    total_size = os.path.getsize(local_path)
    init_resp = session.post(
        init_url,
        headers={
            'Content-Type': 'application/geopackage+sqlite3',
            'X-Upload-Content-Length': str(total_size),
        },
        timeout=120,
    )
    if init_resp.status_code not in (200, 201):
        raise RuntimeError(
            f'GCS upload initiation failed ({init_resp.status_code}): {init_resp.text}'
        )

    upload_url = init_resp.headers.get('Location')
    if not upload_url:
        raise RuntimeError('Missing Location header in GCS upload initiation')

    print(f'Uploading {local_path} ({total_size / (1024 * 1024):.1f} MB) to '
          f'gs://{bucket_name}/{object_name}...')
    _stream_chunks_to_gcs(session, upload_url, local_path, total_size)
    print('GCS upload succeeded.')


def download_roads_from_gcs(
    local_path: str,
    bucket_name: str,
    credentials_path: str | None = None,
    object_name: str = 'world_drivable_roads.gpkg',
) -> None:
    """Downloads the road GeoPackage from Google Cloud Storage to local disk.

    Args:
        local_path: Destination path on local disk.
        bucket_name: Name of the GCS bucket.
        credentials_path: Optional service account credentials path.
        object_name: GCS object name.

    Raises:
        RuntimeError: If GCS download fails.
    """
    session, _ = get_gcs_session(credentials_path)
    encoded_name = urllib.parse.quote(object_name, safe='')
    download_url = (f'https://storage.googleapis.com/storage/v1/b/'
                    f'{bucket_name}/o/{encoded_name}?alt=media')

    print(f'Downloading gs://{bucket_name}/{object_name} to {local_path}...')
    resp = session.get(download_url, stream=True, timeout=300)
    if resp.status_code != 200:
        raise RuntimeError(
            f'GCS download failed ({resp.status_code}): {resp.text}')

    os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
    temp_path = f'{local_path}.tmp'
    try:
        with open(temp_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
        os.replace(temp_path, local_path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

    file_size_mb = os.path.getsize(local_path) / (1024 * 1024)
    print(f'Downloaded {file_size_mb:.1f} MB successfully.')


def resolve_roads_gpkg(
    roads_path: str = DEFAULT_ROADS_GPKG_PATH,
    config_path: str = 'backend/config.ini',
    allow_download: bool = True,
) -> str | None:
    """Ensures the road GeoPackage is available on disk, downloading from GCS if needed.

    Args:
        roads_path: Local path to check or populate.
        config_path: Path to backend config.ini.
        allow_download: If True, downloads from GCS if missing locally.

    Returns:
        Absolute path to the existing .gpkg file, or None if unavailable.
    """
    if os.path.exists(roads_path) and os.path.getsize(roads_path) > 0:
        return os.path.abspath(roads_path)

    target_cfg = config_path
    if not os.path.exists(target_cfg):
        alt_cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               '../config.ini')
        if os.path.exists(alt_cfg):
            target_cfg = alt_cfg
        else:
            return None

    try:
        cfg = configparser.ConfigParser()
        cfg.read(target_cfg)
        configured_path = cfg.get('gcs',
                                  'ROADS_GPKG_PATH',
                                  fallback=roads_path)
        if os.path.exists(configured_path) and os.path.getsize(
                configured_path) > 0:
            return os.path.abspath(configured_path)

        if not allow_download:
            return None

        bucket_name = cfg.get('gcs',
                              'GCS_MAP_DATA_BUCKET_NAME',
                              fallback=DEFAULT_MAP_BUCKET_NAME)
        cred_path = cfg.get('mail',
                            'GOOGLE_APPLICATION_CREDENTIALS',
                            fallback=None)
        cred_clean = cred_path.strip('"\'') if cred_path else None

        download_roads_from_gcs(configured_path, bucket_name, cred_clean)
        if os.path.exists(configured_path):
            return os.path.abspath(configured_path)
    except (OSError, RuntimeError, ValueError, configparser.Error) as exc:
        print(f'Warning: Could not auto-resolve road dataset from GCS: {exc}')

    return None


def get_roads_total_bounds(
    roads_input: str | gpd.GeoDataFrame,
) -> tuple[float, float, float, float]:
    """Retrieves the overall (min_lon, min_lat, max_lon, max_lat) bounds of the roads dataset.

    Args:
        roads_input: Path to road GeoPackage or in-memory GeoDataFrame.

    Returns:
        Bounding box tuple in EPSG:4326.
    """
    if isinstance(roads_input, str):
        info = pyogrio.read_info(roads_input, layer='roads')
        tb = info['total_bounds']
        return (float(tb[0]), float(tb[1]), float(tb[2]), float(tb[3]))

    tb = roads_input.total_bounds
    return (float(tb[0]), float(tb[1]), float(tb[2]), float(tb[3]))


def _clip_geometry_lines(
    geom: shapely.geometry.base.BaseGeometry | None,
    bbox: tuple[float, float, float, float],
    cos_lat: float,
    all_lines: list[shapely.geometry.LineString],
    all_weights: list[float],
) -> None:
    """Clips a geometry to bbox and appends scaled LineStrings with positive lengths."""
    if geom is None or geom.is_empty:
        return
    min_lon, min_lat, max_lon, max_lat = bbox
    clipped = shapely.clip_by_rect(geom, min_lon, min_lat, max_lon, max_lat)
    for part in shapely.get_parts(clipped):
        if (part.geom_type == 'LineString' and not part.is_empty
                and part.length > 1e-9):
            scaled_line = shapely.affinity.scale(part,
                                                 xfact=cos_lat,
                                                 yfact=1.0,
                                                 origin=(0, 0))
            weight = float(scaled_line.length)
            if weight > 1e-9:
                all_lines.append(part)
                all_weights.append(weight)


def query_clipped_roads_in_bboxes(
    roads_input: str | gpd.GeoDataFrame,
    bboxes: list[tuple[float, float, float, float]],
) -> tuple[list[shapely.geometry.LineString], list[float]]:
    """Queries and clips road segments across one or more bounding boxes for a cell.

    Args:
        roads_input: Path to road GeoPackage or in-memory GeoDataFrame.
        bboxes: List of (min_lon, min_lat, max_lon, max_lat) bounding boxes.

    Returns:
        tuple[list[LineString], list[float]]: Clipped LineString segments and their
        latitude-cosine-scaled metric weights.
    """
    all_lines: list[shapely.geometry.LineString] = []
    all_weights: list[float] = []

    for bbox in bboxes:
        min_lon, min_lat, max_lon, max_lat = bbox
        if isinstance(roads_input, str):
            try:
                gdf = gpd.read_file(roads_input, bbox=bbox, engine='pyogrio')
            except (OSError, ValueError, RuntimeError):
                continue
        else:
            gdf = roads_input.cx[min_lon:max_lon, min_lat:max_lat]

        if gdf.empty:
            continue

        lat_center = (min_lat + max_lat) / 2.0
        cos_lat = max(math.cos(math.radians(lat_center)), 0.01)

        for geom in gdf.geometry:
            _clip_geometry_lines(geom, bbox, cos_lat, all_lines, all_weights)

    return all_lines, all_weights


def sample_length_weighted_line_point(
    lines: list[shapely.geometry.LineString],
    weights: list[float],
) -> shapely.geometry.Point | None:
    """Samples a random Point along a random LineString weighted by segment length.

    Args:
        lines: Available LineString segments.
        weights: Corresponding length weights.

    Returns:
        Sampled Point geometry, or None if lines is empty.
    """
    if not lines:
        return None

    total_weight = sum(weights)
    if total_weight <= 0.0:
        idx = int(np.random.randint(0, len(lines)))
    else:
        probs = np.array(weights, dtype=float) / total_weight
        probs = probs / np.sum(probs)
        idx = int(np.random.choice(len(lines), p=probs))

    chosen_line = lines[idx]
    frac = float(np.random.uniform(0.0, 1.0))
    return chosen_line.interpolate(frac, normalized=True)


def generate_polar_road_offset(
    origin: tuple[float, float],
    max_dist_m: float = 50.0,
) -> tuple[float, float]:
    """Generates a random coordinate offset by 0 to max_dist_m meters from origin.

    Args:
        origin: (latitude, longitude) of road origin coordinate.
        max_dist_m: Maximum offset in meters (default: 50.0).

    Returns:
        tuple[float, float]: Offset (latitude, longitude) in degrees.
    """
    origin_lat_rad = math.radians(origin[0])
    origin_lon_rad = math.radians(origin[1])

    u = float(np.random.uniform(0.0, 1.0))
    angular_dist = (math.sqrt(u) * (max_dist_m / 1000.0)) / EARTH_RADIUS_KM
    bearing = float(np.random.uniform(0.0, 2.0 * math.pi))

    cand_lat_rad = math.asin(
        max(
            -1.0,
            min(
                1.0,
                math.sin(origin_lat_rad) * math.cos(angular_dist) +
                math.cos(origin_lat_rad) * math.sin(angular_dist) *
                math.cos(bearing),
            ),
        ))
    cand_lon_rad = origin_lon_rad + math.atan2(
        math.sin(bearing) * math.sin(angular_dist) * math.cos(origin_lat_rad),
        math.cos(angular_dist) -
        math.sin(origin_lat_rad) * math.sin(cand_lat_rad),
    )

    cand_lat_deg = math.degrees(cand_lat_rad)
    cand_lon_deg = ((math.degrees(cand_lon_rad) + 540.0) % 360.0) - 180.0
    return cand_lat_deg, cand_lon_deg


def sample_cell_road_candidates(
    roads_input: str | gpd.GeoDataFrame,
    bboxes: list[tuple[float, float, float, float]],
    num_candidates: int,
    max_dist_m: float = 50.0,
) -> list[shapely.geometry.Point]:
    """Queries roads in a cell once and pre-samples offset candidate Points.

    Args:
        roads_input: Path to road GeoPackage or in-memory GeoDataFrame.
        bboxes: Cell bounding boxes.
        num_candidates: Number of candidate Points to sample.
        max_dist_m: Maximum offset distance in meters.

    Returns:
        list[Point]: Sampled candidate Points in EPSG:4326.
    """
    lines, weights = query_clipped_roads_in_bboxes(roads_input, bboxes)
    if not lines or num_candidates <= 0:
        return []

    candidates: list[shapely.geometry.Point] = []
    for _ in range(num_candidates):
        pt_on_line = sample_length_weighted_line_point(lines, weights)
        if pt_on_line is None:
            continue
        c_lat, c_lon = generate_polar_road_offset((pt_on_line.y, pt_on_line.x),
                                                  max_dist_m=max_dist_m)
        candidates.append(shapely.geometry.Point(c_lon, c_lat))

    return candidates


def _compile_roads_dataset(input_path: str, output_path: str) -> None:
    """Processes input PBF or vector road dataset into target GeoPackage."""
    if input_path.lower().endswith('.osm.pbf') or input_path.lower().endswith(
            '.pbf'):
        process_osm_pbf_to_gpkg(input_path, output_path)
        return

    print(f'Reading raw road data from {input_path}...')
    raw_gdf = gpd.read_file(input_path)
    print(f'Loaded {len(raw_gdf)} features. Filtering drivable roads...')
    filtered_gdf = filter_drivable_roads(raw_gdf)
    print(
        f'Filtered down to {len(filtered_gdf)} segments. Exporting to {output_path}...'
    )
    export_roads_geopackage(filtered_gdf, output_path)
    print('Export completed successfully.')


def main() -> None:
    """CLI entry point for road data preparation and GCS synchronization."""
    parser = argparse.ArgumentParser(
        description='Filter and synchronize global drivable road network data')
    parser.add_argument(
        '--input',
        '-i',
        type=str,
        help=
        'Path to raw input roads dataset (.osm.pbf, .gpkg, .shp, .geojson)',
    )
    parser.add_argument(
        '--output',
        '-o',
        type=str,
        default=DEFAULT_ROADS_GPKG_PATH,
        help=
        f'Path to destination .gpkg file (default: {DEFAULT_ROADS_GPKG_PATH})',
    )
    parser.add_argument(
        '--upload-gcs',
        action='store_true',
        help='Upload the output file to Google Cloud Storage',
    )
    parser.add_argument(
        '--download-gcs',
        action='store_true',
        help=
        'Download the road dataset from Google Cloud Storage to local disk',
    )
    parser.add_argument(
        '--config',
        '-c',
        type=str,
        default='backend/config.ini',
        help='Path to backend config.ini (default: backend/config.ini)',
    )
    args = parser.parse_args()

    cfg = configparser.ConfigParser()
    if os.path.exists(args.config):
        cfg.read(args.config)
    bucket_name = cfg.get('gcs',
                          'GCS_MAP_DATA_BUCKET_NAME',
                          fallback=DEFAULT_MAP_BUCKET_NAME)
    cred_path = cfg.get('mail',
                        'GOOGLE_APPLICATION_CREDENTIALS',
                        fallback=None)
    cred_clean = cred_path.strip('"\'') if cred_path else None

    try:
        if args.download_gcs:
            download_roads_from_gcs(args.output, bucket_name, cred_clean)
            return

        if not args.input:
            print('Error: --input is required when preparing road data.')
            sys.exit(1)

        _compile_roads_dataset(args.input, args.output)

        if args.upload_gcs:
            upload_roads_to_gcs(args.output, bucket_name, cred_clean)

    except (OSError, RuntimeError, ValueError, configparser.Error) as exc:
        print(f'Execution Error: {exc}')
        sys.exit(1)


if __name__ == '__main__':
    main()
