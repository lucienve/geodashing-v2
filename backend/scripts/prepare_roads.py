"""Utility script for preparing, filtering, and caching global drivable road data."""

import argparse
import configparser
import datetime
import os
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request

import geopandas as gpd
import google.auth
import google.auth.transport.requests
import google.oauth2.service_account

DEFAULT_ROADS_GPKG_PATH: str = 'data/world_drivable_roads.gpkg'
DEFAULT_MAP_BUCKET_NAME: str = 'geodashing-v2-map-data'
RESUMABLE_CHUNK_SIZE: int = 128 * 1024 * 1024  # 128 MiB chunks
ROADS_GPKG_MAX_AGE_S: int = 180 * 24 * 3600  # 180 days (~6 months)
PLANET_PBF_CACHE_OBJECT: str = 'cache/planet-latest.osm.pbf'
FILTERED_PBF_CACHE_OBJECT: str = 'cache/filtered_roads.osm.pbf'
ROADS_GPKG_GCS_OBJECT: str = 'world_drivable_roads.gpkg'
PLANET_PBF_CACHE_MAX_AGE_S: int = 7 * 24 * 3600
PLANET_OSM_MIRRORS: tuple[str, ...] = (
    'https://ftpmirror.your.org/pub/openstreetmap/pbf/planet-latest.osm.pbf',
    'https://planet.openstreetmap.org/pbf/planet-latest.osm.pbf',
    'https://ftp.osuosl.org/pub/openstreetmap/pbf/planet-latest.osm.pbf',
)

QUALIFYING_HIGHWAY_TYPES: set[str] = {
    'primary', 'secondary', 'tertiary', 'unclassified', 'residential',
    'primary_link', 'secondary_link', 'tertiary_link'
}

EXCLUDED_ACCESS_VALUES: set[str] = {
    'private', 'no', 'customers', 'military', 'permit', 'agricultural',
    'forestry'
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
    content = (
        "[lines]\nosm_id=no\nosm_version=no\nosm_timestamp=no\nosm_uid=no\n"
        "osm_user=no\nosm_changeset=no\nattributes=highway,access\nother_tags=no\n"
    )
    with open(conf_path, 'w', encoding='utf-8') as f:
        f.write(content)


def _filter_and_cache_pbf_roads(
    input_pbf: str,
    filtered_pbf: str,
    *,
    bucket_name: str | None = None,
    credentials_path: str | None = None,
    delete_input: bool = False,
) -> None:
    """Filters OSM highway ways using osmium and caches to GCS if configured."""
    filtered_part_pbf = f'{filtered_pbf}.part'
    print(f"Running osmium tags-filter on {input_pbf}...")
    hw_filter = ','.join(sorted(QUALIFYING_HIGHWAY_TYPES))
    cmd_osmium = [
        'osmium',
        'tags-filter',
        input_pbf,
        f'w/highway={hw_filter}',
        '-o',
        filtered_part_pbf,
        '--output-format=pbf',
        '--overwrite',
    ]
    subprocess.run(cmd_osmium, check=True)
    _verify_planet_download(filtered_part_pbf, expected_size=0)
    os.replace(filtered_part_pbf, filtered_pbf)

    if delete_input and os.path.exists(input_pbf):
        os.remove(input_pbf)

    if bucket_name:
        print(f'Caching filtered PBF to gs://{bucket_name}/'
              f'{FILTERED_PBF_CACHE_OBJECT}...')
        try:
            upload_roads_to_gcs(filtered_pbf,
                                bucket_name,
                                credentials_path,
                                object_name=FILTERED_PBF_CACHE_OBJECT)
        except (OSError, RuntimeError) as exc:
            print(f'Warning: Caching filtered PBF to GCS failed ({exc}); '
                  'continuing with local GeoPackage compilation.')


def _run_ogr2ogr_roads_export(
    source_pbf: str,
    output_gpkg: str,
    work_dir: str,
    osmconf_path: str,
) -> None:
    """Executes ogr2ogr to compile lines into an R-tree indexed GeoPackage."""
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
    env['OSM_MAX_TMPFILE_SIZE'] = '45000'
    env['OSM_COMPRESS_NODES'] = 'YES'
    env['OGR_SQLITE_CACHE'] = '10240'
    env['OGR_SQLITE_PRAGMA'] = 'page_size=65536'
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
        'LINESTRING',
        '-lco',
        'SPATIAL_INDEX=YES',
        '-gt',
        '100000',
    ]
    print(f"Running ogr2ogr to generate {output_gpkg}...")
    subprocess.run(cmd_ogr, check=True, env=env)
    print("GeoPackage compilation completed successfully.")


def process_osm_pbf_to_gpkg(
    input_pbf: str,
    output_gpkg: str,
    delete_input: bool = False,
    bucket_name: str | None = None,
    credentials_path: str | None = None,
) -> None:
    """Compiles an OSM PBF extract into a filtered, R-tree indexed GeoPackage.

    Args:
        input_pbf: Path to the raw or pre-filtered .osm.pbf file.
        output_gpkg: Destination .gpkg path.
        delete_input: If True, removes input_pbf after processing.
        bucket_name: Optional GCS bucket name to cache filtered_roads.osm.pbf.
        credentials_path: Optional service account credentials path.

    Raises:
        FileNotFoundError: If input_pbf does not exist.
        RuntimeError: If osmium or ogr2ogr subprocess execution fails.
    """
    if not os.path.exists(input_pbf):
        raise FileNotFoundError(f"Input OSM PBF not found: {input_pbf}")

    work_dir = os.path.dirname(os.path.abspath(output_gpkg))
    os.makedirs(work_dir, exist_ok=True)

    filtered_pbf = os.path.join(work_dir, 'filtered_roads.osm.pbf')
    filtered_part_pbf = f'{filtered_pbf}.part'
    osmconf_path = os.path.join(work_dir, 'osmconf.ini')
    is_prefiltered = os.path.abspath(input_pbf) == os.path.abspath(
        filtered_pbf)
    source_pbf = input_pbf

    try:
        if not is_prefiltered and shutil.which('osmium'):
            _filter_and_cache_pbf_roads(input_pbf,
                                        filtered_pbf,
                                        bucket_name=bucket_name,
                                        credentials_path=credentials_path,
                                        delete_input=delete_input)
            source_pbf = filtered_pbf

        _run_ogr2ogr_roads_export(source_pbf, output_gpkg, work_dir,
                                  osmconf_path)

    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Road processing command failed: {exc}") from exc
    finally:
        if os.path.exists(osmconf_path):
            os.remove(osmconf_path)
        if os.path.exists(filtered_part_pbf):
            os.remove(filtered_part_pbf)
        if (not is_prefiltered
                or delete_input) and os.path.exists(filtered_pbf):
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
            for chunk in resp.iter_content(chunk_size=RESUMABLE_CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
        os.replace(temp_path, local_path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

    file_size_mb = os.path.getsize(local_path) / (1024 * 1024)
    print(f'Downloaded {file_size_mb:.1f} MB successfully.')


def _check_gcs_planet_cache(
    bucket_name: str,
    credentials_path: str | None = None,
    object_name: str = PLANET_PBF_CACHE_OBJECT,
) -> int | None:
    """Returns cached GCS object byte size if it exists and is <= 7 days old."""
    session, _ = get_gcs_session(credentials_path)
    encoded = urllib.parse.quote(object_name, safe='')
    url = f'https://storage.googleapis.com/storage/v1/b/{bucket_name}/o/{encoded}'
    resp = session.get(url, timeout=60)
    if resp.status_code != 200:
        return None
    data = resp.json()
    size = int(data.get('size', 0))
    ts_str = data.get('updated') or data.get('timeCreated')
    if size <= 0 or not ts_str:
        return None
    updated_dt = datetime.datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
    age_s = (datetime.datetime.now(datetime.timezone.utc) -
             updated_dt).total_seconds()
    if age_s > PLANET_PBF_CACHE_MAX_AGE_S:
        print(f'GCS cache gs://{bucket_name}/{object_name} expired '
              f'({age_s / 86400:.1f} days old).')
        return None
    return size


def _get_expected_planet_size() -> int:
    """Queries remote HTTP HEAD Content-Length across configured OSM mirrors."""
    for url in PLANET_OSM_MIRRORS:
        req = urllib.request.Request(url, method='HEAD')
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                length = int(resp.headers.get('Content-Length', 0))
                if length > 0:
                    return length
        except (OSError, ValueError):
            continue
    return 0


def _verify_planet_download(part_path: str, expected_size: int = 0) -> None:
    """Verifies downloaded PBF completeness, absence of .aria2 file, and header."""
    if not os.path.exists(part_path):
        raise RuntimeError(f'Downloaded file missing: {part_path}')
    if os.path.exists(f'{part_path}.aria2'):
        raise RuntimeError('Incomplete aria2 download (.aria2 file present)')
    actual_size = os.path.getsize(part_path)
    if actual_size <= 0 or (expected_size > 0
                            and actual_size != expected_size):
        raise RuntimeError(
            f'Size mismatch: got {actual_size} bytes, expected {expected_size}'
        )
    if shutil.which('osmium'):
        subprocess.run(['osmium', 'fileinfo', '--input-format=pbf', part_path],
                       check=True)


def fetch_cached_filtered_pbf(
    dest_path: str,
    bucket_name: str,
    credentials_path: str | None = None,
) -> bool:
    """Downloads and verifies 7-day cached filtered_roads.osm.pbf from GCS.

    Args:
        dest_path: Destination local path for the verified filtered PBF.
        bucket_name: GCS bucket name.
        credentials_path: Optional service account credentials path.

    Returns:
        bool: True if cached file exists, was downloaded, and passed verification;
            False otherwise.
    """
    cached_size = _check_gcs_planet_cache(
        bucket_name, credentials_path, object_name=FILTERED_PBF_CACHE_OBJECT)
    if cached_size is None:
        return False

    print(f'Found fresh GCS filtered cache gs://{bucket_name}/'
          f'{FILTERED_PBF_CACHE_OBJECT} ({cached_size} bytes).')
    try:
        download_roads_from_gcs(dest_path,
                                bucket_name,
                                credentials_path,
                                object_name=FILTERED_PBF_CACHE_OBJECT)
        _verify_planet_download(dest_path, expected_size=cached_size)
        return True
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(
            f'Warning: GCS filtered cache download or validation failed ({exc}); '
            'falling back to raw OSM download and filtering.')
        if os.path.exists(dest_path):
            os.remove(dest_path)
        return False


def _download_planet_from_mirrors(dest_path: str) -> None:
    """Downloads planet-latest.osm.pbf via aria2c multi-source mirrors and verifies."""
    work_dir = os.path.dirname(os.path.abspath(dest_path))
    os.makedirs(work_dir, exist_ok=True)
    part_name = f'{os.path.basename(dest_path)}.part'
    part_path = os.path.join(work_dir, part_name)
    for stale in (part_path, f'{part_path}.aria2'):
        if os.path.exists(stale):
            os.remove(stale)
    expected_size = _get_expected_planet_size()
    if shutil.which('aria2c'):
        cmd = [
            'aria2c', '--max-connection-per-server=8', '--split=16',
            '--min-split-size=64M', '--file-allocation=falloc',
            '--continue=true', '--max-tries=10', '--retry-wait=5',
            '--summary-interval=30', '--allow-overwrite=true',
            '--auto-file-renaming=false', '--dir', work_dir, '--out',
            part_name, *PLANET_OSM_MIRRORS
        ]
    else:
        cmd = [
            'curl', '-L', '--fail', '--retry', '5', '--retry-delay', '5',
            PLANET_OSM_MIRRORS[0], '-o', part_path
        ]
    try:
        subprocess.run(cmd, check=True)
        _verify_planet_download(part_path, expected_size)
        os.replace(part_path, dest_path)
    except (subprocess.CalledProcessError, OSError, RuntimeError) as exc:
        for stale in (part_path, f'{part_path}.aria2'):
            if os.path.exists(stale):
                os.remove(stale)
        raise RuntimeError(f'Planet OSM download failed: {exc}') from exc


def fetch_or_cache_planet_pbf(
    dest_path: str,
    bucket_name: str,
    credentials_path: str | None = None,
    force: bool = False,
) -> str:
    """Fetches planet-latest.osm.pbf from 7-day GCS cache or OSM mirrors.

    Args:
        dest_path: Destination local path for the PBF file.
        bucket_name: GCS bucket name.
        credentials_path: Optional service account credentials path.
        force: If True, bypasses GCS cache and forces fresh download.

    Returns:
        str: Path to the validated PBF file.
    """
    if not force:
        cached_size = _check_gcs_planet_cache(bucket_name, credentials_path)
        if cached_size is not None:
            print(f'Found fresh GCS cache gs://{bucket_name}/'
                  f'{PLANET_PBF_CACHE_OBJECT} ({cached_size} bytes).')
            try:
                download_roads_from_gcs(dest_path,
                                        bucket_name,
                                        credentials_path,
                                        object_name=PLANET_PBF_CACHE_OBJECT)
                _verify_planet_download(dest_path, expected_size=cached_size)
                return dest_path
            except (OSError, RuntimeError,
                    subprocess.CalledProcessError) as exc:
                print(
                    f'Warning: GCS cache download or validation failed ({exc}); '
                    'falling back to OSM mirrors.')
                if os.path.exists(dest_path):
                    os.remove(dest_path)
    print('Downloading planet-latest.osm.pbf from OpenStreetMap mirrors...')
    _download_planet_from_mirrors(dest_path)
    print(f'Caching verified PBF to gs://{bucket_name}/'
          f'{PLANET_PBF_CACHE_OBJECT}...')
    upload_roads_to_gcs(dest_path,
                        bucket_name,
                        credentials_path,
                        object_name=PLANET_PBF_CACHE_OBJECT)
    return dest_path


def resolve_roads_gpkg(
    roads_path: str | None = None,
    config_path: str = 'backend/config.ini',
    max_age_s: int = ROADS_GPKG_MAX_AGE_S,
) -> str:
    """Resolves and validates the local road GeoPackage path and freshness.

    Args:
        roads_path: Optional explicit local path to check. If None, resolves
            from config_path or falls back to DEFAULT_ROADS_GPKG_PATH.
        config_path: Path to backend config.ini.
        max_age_s: Maximum allowed age of the dataset file in seconds.

    Returns:
        Absolute path to the existing, non-empty, and fresh .gpkg file.

    Raises:
        FileNotFoundError: If the road dataset is missing or empty.
        RuntimeError: If the road dataset is older than max_age_s.
    """
    if roads_path is not None:
        target_path = roads_path
    else:
        target_cfg = config_path
        if not os.path.exists(target_cfg):
            alt_cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   '../config.ini')
            if os.path.exists(alt_cfg):
                target_cfg = alt_cfg
        configured_path: str | None = None
        if os.path.exists(target_cfg):
            cfg = configparser.ConfigParser()
            cfg.read(target_cfg)
            if cfg.has_option('gcs', 'ROADS_GPKG_PATH'):
                raw_path = cfg.get('gcs', 'ROADS_GPKG_PATH')
                configured_path = raw_path.strip('"\'')
        target_path = configured_path or DEFAULT_ROADS_GPKG_PATH

    if not os.path.exists(target_path) or os.path.getsize(target_path) <= 0:
        raise FileNotFoundError(
            f"Road dataset '{target_path}' is missing or empty. "
            "See data/README.md for instructions on downloading it via "
            "'gcloud storage cp'.")

    mtime = os.path.getmtime(target_path)
    now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
    age_s = now_ts - mtime
    if age_s > max_age_s:
        age_days = int(age_s // 86400)
        raise RuntimeError(
            f"Road dataset '{target_path}' is more than 6 months old "
            f"({age_days} days). See data/README.md for instructions on "
            "refreshing and downloading an updated dataset via 'gcloud storage cp'."
        )

    return os.path.abspath(target_path)


def _compile_roads_dataset(
    input_path: str,
    output_path: str,
    delete_input: bool = False,
    bucket_name: str | None = None,
    credentials_path: str | None = None,
) -> None:
    """Processes input PBF or vector road dataset into target GeoPackage."""
    if input_path.lower().endswith('.osm.pbf') or input_path.lower().endswith(
            '.pbf'):
        process_osm_pbf_to_gpkg(input_path,
                                output_path,
                                delete_input=delete_input,
                                bucket_name=bucket_name,
                                credentials_path=credentials_path)
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
    parser.add_argument('-i', '--input', type=str, help='Input roads path')
    parser.add_argument('-o',
                        '--output',
                        type=str,
                        default=DEFAULT_ROADS_GPKG_PATH)
    parser.add_argument('--delete-input', action='store_true')
    parser.add_argument('--upload-gcs', action='store_true')
    parser.add_argument('--download-planet-osm', action='store_true')
    parser.add_argument(
        '--force',
        action='store_true',
        help='Bypass GCS freshness and cache checks to recompile')
    parser.add_argument('-c',
                        '--config',
                        type=str,
                        default='backend/config.ini')
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
        if not args.input:
            print('Error: --input is required when preparing road data.')
            sys.exit(1)

        # Stage 0: Early-exit check if output in GCS is already fresh
        if args.upload_gcs and not args.force:
            cached_output_size = _check_gcs_planet_cache(
                bucket_name, cred_clean, object_name=ROADS_GPKG_GCS_OBJECT)
            if cached_output_size is not None:
                print(
                    f'Destination gs://{bucket_name}/{ROADS_GPKG_GCS_OBJECT} '
                    f'is already fresh ({cached_output_size} bytes). Exiting early.'
                )
                return

        # Stage 1 & 2: Filtered PBF cache check or raw planet download + filtering
        skipped_osmium = False
        work_dir = os.path.dirname(os.path.abspath(args.output))
        filtered_cache_local = os.path.join(work_dir, 'filtered_roads.osm.pbf')

        if args.download_planet_osm:
            if not args.force and fetch_cached_filtered_pbf(
                    filtered_cache_local, bucket_name, cred_clean):
                print(
                    'Using cached filtered PBF; skipping raw planet OSM download.'
                )
                skipped_osmium = True
            else:
                fetch_or_cache_planet_pbf(args.input,
                                          bucket_name,
                                          cred_clean,
                                          force=args.force)

        effective_input = filtered_cache_local if skipped_osmium else args.input
        _compile_roads_dataset(
            effective_input,
            args.output,
            delete_input=True if skipped_osmium else args.delete_input,
            bucket_name=bucket_name,
            credentials_path=cred_clean)

        if args.upload_gcs:
            upload_roads_to_gcs(args.output, bucket_name, cred_clean)

    except (OSError, RuntimeError, ValueError, configparser.Error) as exc:
        print(f'Execution Error: {exc}')
        sys.exit(1)


if __name__ == '__main__':
    main()
