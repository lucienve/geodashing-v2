"""Spatial road-proximity sampling and grid-cell placement primitives."""

import collections
import dataclasses
import math
import os
import sqlite3
import typing

import geopandas as gpd
import numpy as np
import pyogrio
import pyproj
import shapely
import shapely.affinity
import shapely.errors
import shapely.geometry
import shapely.geometry.base
import shapely.strtree

EARTH_RADIUS_KM: float = 6371.0088


@dataclasses.dataclass(frozen=True)
class LatitudeBand:
    """Represents a discrete latitudinal band on the globe."""
    band_idx: int
    lat_min: float
    lat_max: float
    lon_offset: float
    num_cells: int
    dlon: float


@typing.runtime_checkable
class SpatialFilterProtocol(typing.Protocol):
    """Protocol for spatial filter evaluation on geometry bounding boxes."""

    def get_candidate_matches(
        self,
        buffers: typing.Sequence[shapely.geometry.base.BaseGeometry],
    ) -> tuple[dict[int, list[shapely.geometry.base.BaseGeometry]], dict[
            int, list[shapely.geometry.base.BaseGeometry]]]:
        """Queries candidate land and lake geometries for bounding boxes."""
        ...

    def eval_boundary_point(
        self,
        buffer_geom: shapely.geometry.base.BaseGeometry,
        matching_lands: list[shapely.geometry.base.BaseGeometry],
        matching_lakes: list[shapely.geometry.base.BaseGeometry],
    ) -> bool:
        """Determines if a single buffered point intersects dry land."""
        ...

    def filter_valid_indices(
        self,
        raw_points: list[shapely.geometry.Point],
    ) -> set[int]:
        """Identifies indices of points situated on dry land."""
        ...


@typing.runtime_checkable
class NeighborGridProtocol(typing.Protocol):
    """Protocol for spatial spacing constraint checks."""

    def can_place(self, lon: float, lat: float) -> bool:
        """Checks if a point is at least min distance from all stored points."""
        ...

    def insert(self, lon: float, lat: float) -> bool:
        """Inserts a point if it meets the minimum distance constraint."""
        ...


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
        try:
            info = pyogrio.read_info(roads_input, layer='roads')
            tb = info.get('total_bounds')
            if tb is not None and len(tb) >= 4 and not np.isnan(tb).any():
                return (float(tb[0]), float(tb[1]), float(tb[2]), float(tb[3]))
        except (OSError, ValueError, RuntimeError):
            pass
        return (-180.0, -90.0, 180.0, 90.0)

    tb = getattr(roads_input, 'total_bounds', None)
    if tb is not None and len(tb) >= 4 and not np.isnan(tb).any():
        return (float(tb[0]), float(tb[1]), float(tb[2]), float(tb[3]))
    return (-180.0, -90.0, 180.0, 90.0)


def clip_geometry_lines(
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
            clip_geometry_lines(geom, bbox, cos_lat, all_lines, all_weights)

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


def _bbox_intersects(b1: tuple[float, float, float, float],
                     b2: tuple[float, float, float, float]) -> bool:
    """Checks if two (minx, miny, maxx, maxy) bounding boxes intersect."""
    return not (b1[2] < b2[0] or b1[0] > b2[2] or b1[3] < b2[1]
                or b1[1] > b2[3])


def sample_cell_road_candidates(
    roads_input: str | gpd.GeoDataFrame,
    bboxes: list[tuple[float, float, float, float]],
    num_candidates: int,
    max_dist_m: float = 50.0,
    road_bounds: tuple[float, float, float, float] | None = None,
) -> list[shapely.geometry.Point]:
    """Queries roads in a cell once and pre-samples offset candidate Points.

    Args:
        roads_input: Path to road GeoPackage or in-memory GeoDataFrame.
        bboxes: Cell bounding boxes.
        num_candidates: Number of candidate Points to sample.
        max_dist_m: Maximum offset distance in meters.
        road_bounds: Optional total bounds of the roads dataset for fast skipping.

    Returns:
        list[Point]: Sampled candidate Points in EPSG:4326.
    """
    if num_candidates <= 0:
        return []

    if road_bounds is not None and not any(
            _bbox_intersects(b, road_bounds) for b in bboxes):
        return []

    lines, weights = query_clipped_roads_in_bboxes(roads_input, bboxes)
    if not lines:
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


def get_cell_bboxes(band: LatitudeBand,
                    cell_idx: int) -> list[tuple[float, float, float, float]]:
    """Computes bounding boxes in EPSG:4326 for a cell, splitting at antimeridian and poles."""
    lat_min, lat_max = band.lat_min, band.lat_max
    if band.num_cells <= 1:
        return [(-180.0, lat_min, 0.0, lat_max),
                (0.0, lat_min, 180.0, lat_max)]

    raw_min_lon = band.lon_offset + cell_idx * band.dlon
    raw_max_lon = raw_min_lon + band.dlon
    if raw_max_lon > 180.0:
        return [
            (raw_min_lon, lat_min, 180.0, lat_max),
            (-180.0, lat_min, raw_max_lon - 360.0, lat_max),
        ]
    return [(raw_min_lon, lat_min, raw_max_lon, lat_max)]


def _build_cell_bounding_boxes(
    bands: list[LatitudeBand],
) -> tuple[list[tuple[LatitudeBand, int]], list[shapely.geometry.Polygon],
           list[int]]:
    """Builds geographic bounding boxes and mapping indices for all grid cells."""
    flat_cells: list[tuple[LatitudeBand, int]] = []
    boxes: list[shapely.geometry.Polygon] = []
    box_to_cell: list[int] = []
    for band in bands:
        for cell_idx in range(band.num_cells):
            c_idx = len(flat_cells)
            flat_cells.append((band, cell_idx))
            for bbox in get_cell_bboxes(band, cell_idx):
                boxes.append(shapely.geometry.box(*bbox))
                box_to_cell.append(c_idx)
    return flat_cells, boxes, box_to_cell


def classify_grid_cells(
    bands: list[LatitudeBand], spatial_filter: SpatialFilterProtocol
) -> tuple[list[tuple[LatitudeBand, int]], list[tuple[LatitudeBand, int]]]:
    """Partitions grid cells into dry land cells (> 0% land) and water-only cells (0% land)."""
    if isinstance(spatial_filter, GpkgSpatialFilter):
        return spatial_filter.classify_grid_cells(bands)

    flat_cells, boxes, box_to_cell = _build_cell_bounding_boxes(bands)
    proj_boxes = list(gpd.GeoSeries(boxes, crs='EPSG:4326').to_crs(epsg=6933))
    land_map, lake_map = spatial_filter.get_candidate_matches(proj_boxes)

    land_cell_indices: set[int] = set()
    for b_idx, lands in land_map.items():
        geom = proj_boxes[b_idx]
        if spatial_filter.eval_boundary_point(geom, lands,
                                              lake_map.get(b_idx, [])):
            land_cell_indices.add(box_to_cell[b_idx])

    land_cells = [
        c for i, c in enumerate(flat_cells) if i in land_cell_indices
    ]
    water_cells = [
        c for i, c in enumerate(flat_cells) if i not in land_cell_indices
    ]
    return land_cells, water_cells


def _safe_union(
    geoms: list[shapely.geometry.base.BaseGeometry],
) -> shapely.geometry.base.BaseGeometry:
    """Safely unions geometries, falling back to make_valid on topology conflicts."""
    if not geoms:
        return shapely.geometry.Polygon()
    if len(geoms) == 1:
        return geoms[0]
    try:
        return shapely.union_all(geoms)
    except shapely.errors.GEOSException:
        repaired = [
            shapely.make_valid(g) if not g.is_valid else g for g in geoms
        ]
        try:
            return shapely.union_all(repaired)
        except shapely.errors.GEOSException:
            res = repaired[0]
            for g in repaired[1:]:
                try:
                    res = res.union(g)
                except (shapely.errors.GEOSException, ValueError):
                    continue
            return res


def _safe_difference(
    geom_a: shapely.geometry.base.BaseGeometry,
    geom_b: shapely.geometry.base.BaseGeometry,
) -> shapely.geometry.base.BaseGeometry:
    """Safely computes geom_a.difference(geom_b), falling back to make_valid."""
    if geom_a.is_empty:
        return geom_a
    if geom_b.is_empty:
        return geom_a
    try:
        return geom_a.difference(geom_b)
    except shapely.errors.GEOSException:
        a_rep = shapely.make_valid(geom_a) if not geom_a.is_valid else geom_a
        b_rep = shapely.make_valid(geom_b) if not geom_b.is_valid else geom_b
        try:
            return a_rep.difference(b_rep)
        except shapely.errors.GEOSException:
            return a_rep


def _load_rtree_index(
    conn: sqlite3.Connection,
    table_name: str,
) -> tuple[np.ndarray, shapely.strtree.STRtree]:
    """Loads an R-tree table into an in-memory STRtree with chunked fetching.

    Args:
        conn: Read-only SQLite connection.
        table_name: Name of the R-tree table (e.g. 'rtree_land_geom').

    Returns:
        tuple[np.ndarray, shapely.strtree.STRtree]: Tuple of (fids, strtree).
    """
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    if count == 0:
        return np.empty(0, dtype=np.int64), shapely.strtree.STRtree([])

    fids = np.empty(count, dtype=np.int64)
    boxes = np.empty((count, 4), dtype=np.float64)

    cursor.execute(f"SELECT id, minx, miny, maxx, maxy FROM {table_name}")
    offset = 0
    chunk_size = 100000
    while True:
        rows = cursor.fetchmany(chunk_size)
        if not rows:
            break
        chunk_arr = np.asarray(rows, dtype=np.float64)
        n = len(rows)
        fids[offset:offset + n] = chunk_arr[:, 0].astype(np.int64)
        boxes[offset:offset + n] = chunk_arr[:, 1:5]
        offset += n

    box_geoms = shapely.box(boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3])
    del boxes
    tree = shapely.strtree.STRtree(box_geoms)
    return fids, tree


def _parse_gpkg_wkb(
    blob: bytes | None, ) -> shapely.geometry.base.BaseGeometry | None:
    """Parses a GeoPackage binary geometry blob into a Shapely geometry."""
    if not blob or len(blob) < 8 or blob[:2] != b'GP':
        return None
    flags = blob[3]
    is_empty = (flags >> 4) & 0x01
    if is_empty:
        return None
    env_indicator = (flags >> 1) & 0x07
    env_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
    env_size = env_sizes.get(env_indicator)
    if env_size is None or len(blob) < 8 + env_size:
        return None
    wkb_bytes = blob[8 + env_size:]
    try:
        return shapely.from_wkb(wkb_bytes)
    except (shapely.errors.GEOSException, ValueError, IndexError):
        return None


def _build_batch_pt_boxes(
    batch_points: list[shapely.geometry.Point],
) -> list[shapely.geometry.Polygon]:
    """Builds polar-scaled and antimeridian-wrapped search boxes for points."""
    pt_boxes: list[shapely.geometry.Polygon] = []
    for pt in batch_points:
        lat, lon = pt.y, pt.x
        cos_lat = max(math.cos(math.radians(abs(lat))), 0.01)
        delta = 0.002 / cos_lat
        minx, maxx = lon - delta, lon + delta
        miny, maxy = max(-90.0, lat - delta), min(90.0, lat + delta)
        if (minx < -180.0 or maxx > 180.0 or (lat + delta) >= 90.0
                or (lat - delta) <= -90.0):
            minx, maxx = -180.0, 180.0
        pt_boxes.append(shapely.box(minx, miny, maxx, maxy))
    return pt_boxes


@dataclasses.dataclass(frozen=True)
class _RtreeIndex:
    """Stores R-tree feature IDs and corresponding STRtree spatial index."""
    fids: np.ndarray
    tree: shapely.strtree.STRtree


class GpkgSpatialFilter:
    """Spatial filter querying a GeoPackage using R-tree indexes and on-demand WKB."""

    _MAX_CACHE_SIZE: int = 256

    def __init__(self, gpkg_path: str, verbose: bool = True) -> None:
        """Initializes the filter and loads R-tree envelopes into memory."""
        self.gpkg_path = gpkg_path
        self._conn = sqlite3.connect(
            f"file:{os.path.abspath(gpkg_path)}?mode=ro",
            uri=True,
            check_same_thread=False,
        )
        self._transformer = pyproj.Transformer.from_crs('EPSG:4326',
                                                        'EPSG:6933',
                                                        always_xy=True)
        self._inv_transformer = pyproj.Transformer.from_crs('EPSG:6933',
                                                            'EPSG:4326',
                                                            always_xy=True)
        self._geom_cache: collections.OrderedDict[
            tuple[str, int], shapely.geometry.base.BaseGeometry
            | None] = collections.OrderedDict()

        if verbose:
            print(f"Loading R-tree spatial indexes from {gpkg_path}...")
        self._land_index = _RtreeIndex(
            *_load_rtree_index(self._conn, 'rtree_land_geom'))
        self._water_index = _RtreeIndex(
            *_load_rtree_index(self._conn, 'rtree_water_geom'))
        if verbose:
            print(f"Loaded {len(self.land_fids)} land and "
                  f"{len(self.water_fids)} water envelopes.")

    @property
    def land_fids(self) -> np.ndarray:
        """Returns array of feature IDs for the land layer."""
        return self._land_index.fids

    @property
    def land_tree(self) -> shapely.strtree.STRtree:
        """Returns STRtree spatial index for the land layer."""
        return self._land_index.tree

    @property
    def water_fids(self) -> np.ndarray:
        """Returns array of feature IDs for the water layer."""
        return self._water_index.fids

    @property
    def water_tree(self) -> shapely.strtree.STRtree:
        """Returns STRtree spatial index for the water layer."""
        return self._water_index.tree

    def close(self) -> None:
        """Cleans up in-memory caches and closes the SQLite connection."""
        self._geom_cache.clear()
        self._conn.close()

    def _to_6933(self, coords: np.ndarray) -> np.ndarray:
        """Transforms coordinate array from EPSG:4326 to EPSG:6933."""
        x, y = self._transformer.transform(coords[:, 0], coords[:, 1])
        return np.column_stack((x, y))

    def _to_wgs84(self, coords: np.ndarray) -> np.ndarray:
        """Transforms coordinate array from EPSG:6933 to EPSG:4326."""
        x, y = self._inv_transformer.transform(coords[:, 0], coords[:, 1])
        return np.column_stack((x, y))

    def _fetch_single_geom(
            self, layer: str,
            fid: int) -> shapely.geometry.base.BaseGeometry | None:
        """Fetches and caches a single geometry by layer and feature ID."""
        key = (layer, int(fid))
        if key in self._geom_cache:
            self._geom_cache.move_to_end(key)
            return self._geom_cache[key]

        cursor = self._conn.cursor()
        cursor.execute(f"SELECT geom FROM {layer} WHERE fid = ?", (int(fid), ))
        row = cursor.fetchone()
        geom = _parse_gpkg_wkb(row[0]) if row else None

        if len(self._geom_cache) >= self._MAX_CACHE_SIZE:
            self._geom_cache.popitem(last=False)
        self._geom_cache[key] = geom
        return geom

    def _clip_patch(
        self,
        layer: str,
        fids: list[int],
        box_bounds: tuple[float, float, float, float],
    ) -> shapely.geometry.base.BaseGeometry | None:
        """Fetches, clips, and unions geometries for a single layer within box_bounds."""
        if not fids:
            return None
        geoms = [self._fetch_single_geom(layer, f) for f in fids]
        clipped = [
            shapely.clip_by_rect(g, *box_bounds) for g in geoms
            if g is not None and not g.is_empty
        ]
        clipped = [g for g in clipped if not g.is_empty]
        return _safe_union(clipped) if clipped else None

    def _eval_candidate_point(
        self,
        pt: shapely.geometry.Point,
        box_geom: shapely.geometry.Polygon,
        l_fids: list[int],
        w_fids: list[int],
    ) -> bool:
        """Evaluates whether a point's 100m EPSG:6933 buffer touches dry land."""
        land_patch = self._clip_patch('land', l_fids, box_geom.bounds)
        if land_patch is None or land_patch.is_empty:
            return False

        water_patch = self._clip_patch('water', w_fids, box_geom.bounds)
        if water_patch is not None and not water_patch.is_empty:
            land_patch = _safe_difference(land_patch, water_patch)

        if land_patch.is_empty:
            return False

        px, py = self._transformer.transform(pt.x, pt.y)
        pt_buf = shapely.geometry.Point(px, py).buffer(100.0)
        proj_patch = shapely.transform(land_patch, self._to_6933)
        return bool(pt_buf.intersects(proj_patch))

    def _filter_batch_indices(
        self,
        batch_points: list[shapely.geometry.Point],
    ) -> set[int]:
        """Filters a single batch of points using R-tree envelopes and on-demand WKB."""
        pt_boxes = _build_batch_pt_boxes(batch_points)
        land_hits = self.land_tree.query(pt_boxes, predicate='intersects')
        if land_hits.size == 0:
            return set()

        land_map: dict[int, list[int]] = {}
        for p, g in zip(land_hits[0], land_hits[1]):
            land_map.setdefault(p, []).append(int(self.land_fids[g]))

        cand_indices = sorted(land_map.keys())
        cand_boxes = [pt_boxes[i] for i in cand_indices]
        water_hits = self.water_tree.query(cand_boxes, predicate='intersects')
        water_map: dict[int, list[int]] = {}
        if water_hits.size > 0:
            for c, g in zip(water_hits[0], water_hits[1]):
                water_map.setdefault(cand_indices[c],
                                     []).append(int(self.water_fids[g]))

        valid_batch: set[int] = set()
        for p in cand_indices:
            if self._eval_candidate_point(
                    batch_points[p],
                    pt_boxes[p],
                    land_map[p],
                    water_map.get(p, []),
            ):
                valid_batch.add(int(p))

        return valid_batch

    def filter_valid_indices(
        self,
        raw_points: list[shapely.geometry.Point],
    ) -> set[int]:
        """Identifies indices of points situated on dry land or within 100m offshore."""
        if not raw_points:
            return set()
        matched: set[int] = set()
        step = 50000
        for start in range(0, len(raw_points), step):
            subset = raw_points[start:start + step]
            matched.update(start + i
                           for i in self._filter_batch_indices(subset))
        return matched

    def _eval_witness_loop(
        self,
        cl_land: shapely.geometry.base.BaseGeometry,
    ) -> bool:
        """Iteratively tests representative points against covering water geometries."""
        tried_w_fids: set[int] = set()
        curr_land = cl_land
        while not curr_land.is_empty and curr_land.area > 1e-12:
            rep_pt = curr_land.representative_point()
            w_hits = self.water_tree.query(rep_pt, predicate='intersects')
            covering_w: shapely.geometry.base.BaseGeometry | None = None
            for wg_idx in w_hits:
                w_fid = int(self.water_fids[wg_idx])
                if w_fid in tried_w_fids:
                    continue
                w_geom = self._fetch_single_geom('water', w_fid)
                if (w_geom is not None and not w_geom.is_empty
                        and w_geom.intersects(rep_pt)):
                    tried_w_fids.add(w_fid)
                    covering_w = w_geom
                    break
            if covering_w is None:
                return True
            cl_w = shapely.clip_by_rect(covering_w, *curr_land.bounds)
            curr_land = _safe_difference(curr_land, cl_w)
        return False

    def _box_has_dry_land(
        self,
        box_geom: shapely.geometry.Polygon,
        l_idxs: list[int],
    ) -> bool:
        """Determines if a cell bounding box contains dry land via iterative witness points."""
        minx, miny, maxx, maxy = box_geom.bounds
        sorted_l_idxs = sorted(
            l_idxs,
            key=lambda g: self.land_tree.geometries[g].area,
            reverse=True,
        )
        for g_idx in sorted_l_idxs:
            l_fid = int(self.land_fids[g_idx])
            l_geom = self._fetch_single_geom('land', l_fid)
            if l_geom is None or l_geom.is_empty:
                continue
            cl_land = shapely.clip_by_rect(l_geom, minx, miny, maxx, maxy)
            if cl_land.is_empty:
                continue
            if self._eval_witness_loop(cl_land):
                return True
        return False

    def classify_grid_cells(
        self,
        bands: list[LatitudeBand],
    ) -> tuple[list[tuple[LatitudeBand, int]], list[tuple[LatitudeBand, int]]]:
        """Partitions grid cells into dry land cells and water-only cells."""
        flat_cells, boxes, box_to_cell = _build_cell_bounding_boxes(bands)
        if not flat_cells:
            return [], []

        land_hits = self.land_tree.query(boxes, predicate='intersects')
        if land_hits.size == 0:
            return [], flat_cells

        box_to_l_idxs: dict[int, list[int]] = {}
        for b, g in zip(land_hits[0], land_hits[1]):
            box_to_l_idxs.setdefault(b, []).append(g)

        land_cell_indices: set[int] = set()
        for b in sorted(box_to_l_idxs.keys()):
            c_idx = box_to_cell[b]
            if c_idx in land_cell_indices:
                continue
            if self._box_has_dry_land(boxes[b], box_to_l_idxs[b]):
                land_cell_indices.add(c_idx)

        land_cells = [
            c for i, c in enumerate(flat_cells) if i in land_cell_indices
        ]
        water_cells = [
            c for i, c in enumerate(flat_cells) if i not in land_cell_indices
        ]
        return land_cells, water_cells

    def get_candidate_matches(
        self,
        buffers: typing.Sequence[shapely.geometry.base.BaseGeometry],
    ) -> tuple[dict[int, list[shapely.geometry.base.BaseGeometry]], dict[
            int, list[shapely.geometry.base.BaseGeometry]]]:
        """Queries candidate land and lake geometries for bounding boxes."""
        if not buffers:
            return {}, {}
        sample_geom = buffers[0]
        bounds = sample_geom.bounds
        is_projected = abs(bounds[0]) > 180.0 or abs(bounds[1]) > 90.0

        if is_projected:
            search_boxes = [
                shapely.transform(g, self._to_wgs84) for g in buffers
            ]
        else:
            search_boxes = list(buffers)

        land_matches = self.land_tree.query(search_boxes,
                                            predicate='intersects')
        land_map: dict[int, list[shapely.geometry.base.BaseGeometry]] = {}
        if land_matches.size > 0:
            for b_idx, g_idx in zip(land_matches[0], land_matches[1]):
                l_geom = self._fetch_single_geom('land',
                                                 int(self.land_fids[g_idx]))
                if l_geom is not None and not l_geom.is_empty:
                    if is_projected:
                        l_geom = shapely.transform(l_geom, self._to_6933)
                    land_map.setdefault(b_idx, []).append(l_geom)

        water_matches = self.water_tree.query(search_boxes,
                                              predicate='intersects')
        lake_map: dict[int, list[shapely.geometry.base.BaseGeometry]] = {}
        if water_matches.size > 0:
            for b_idx, g_idx in zip(water_matches[0], water_matches[1]):
                w_geom = self._fetch_single_geom('water',
                                                 int(self.water_fids[g_idx]))
                if w_geom is not None and not w_geom.is_empty:
                    if is_projected:
                        w_geom = shapely.transform(w_geom, self._to_6933)
                    lake_map.setdefault(b_idx, []).append(w_geom)

        return land_map, lake_map

    def eval_boundary_point(
        self,
        buffer_geom: shapely.geometry.base.BaseGeometry,
        matching_lands: list[shapely.geometry.base.BaseGeometry],
        matching_lakes: list[shapely.geometry.base.BaseGeometry],
    ) -> bool:
        """Determines if a single buffered point intersects dry land."""
        clipped_lands = [
            g.intersection(buffer_geom) for g in matching_lands
            if not g.is_empty
        ]
        clipped_lands = [g for g in clipped_lands if not g.is_empty]
        if not clipped_lands:
            return False
        land_geom = _safe_union(clipped_lands)

        if matching_lakes:
            clipped_lakes = [
                g.intersection(buffer_geom) for g in matching_lakes
            ]
            valid_lakes = [g for g in clipped_lakes if not g.is_empty]
            if valid_lakes:
                return not _safe_difference(land_geom,
                                            _safe_union(valid_lakes)).is_empty
        return True


@dataclasses.dataclass(frozen=True)
class RoadPlacementContext:
    """Encapsulates shared spatial context and state for road candidate placement."""
    roads_input: str | gpd.GeoDataFrame
    spatial_filter: SpatialFilterProtocol
    neighbor_grid: NeighborGridProtocol
    road_bounds: tuple[float, float, float, float] | None
    cell_candidates: dict[tuple[int, int], list[shapely.geometry.Point]]
    verbose: bool = True
    progress_interval: int = 1000

    def __post_init__(self) -> None:
        if self.progress_interval <= 0:
            raise ValueError(
                f"progress_interval must be greater than 0, got {self.progress_interval}"
            )


def find_valid_road_cell_point(
    band: LatitudeBand,
    cell_idx: int,
    ctx: RoadPlacementContext,
    total_attempts: int = 1,
) -> shapely.geometry.Point | None:
    """Finds a non-colliding road-proximity point on dry land in the cell."""
    key = (band.band_idx, cell_idx)
    if key not in ctx.cell_candidates:
        bboxes = get_cell_bboxes(band, cell_idx)
        ctx.cell_candidates[key] = sample_cell_road_candidates(
            ctx.roads_input,
            bboxes,
            num_candidates=total_attempts * 50,
            max_dist_m=50.0,
            road_bounds=ctx.road_bounds,
        )

    candidates = ctx.cell_candidates[key]
    while candidates:
        cand = candidates.pop()
        if ctx.neighbor_grid.can_place(cand.x, cand.y):
            if ctx.spatial_filter.filter_valid_indices([cand]):
                ctx.neighbor_grid.insert(cand.x, cand.y)
                return cand
    return None


def place_shuffled_road_cells(
    cells: list[tuple[LatitudeBand, int]],
    ctx: RoadPlacementContext,
    accepted_points: list[shapely.geometry.Point],
    pass2_counts: dict[tuple[int, int], int],
) -> int:
    """Places road points for cells in shuffled order, returning count placed.

    Args:
        cells: List of (band, cell_idx) tuples to sample.
        ctx: Road placement context with caches, spatial filter, and road data.
        accepted_points: List where accepted candidate points are appended.
        pass2_counts: Map of (band_idx, cell_idx) to bonus attempt counts.

    Returns:
        The total number of road-proximity points successfully placed.
    """
    rng = np.random.default_rng()
    placed_count = 0
    total_cells = len(cells)
    for i, idx in enumerate(rng.permutation(total_cells), start=1):
        b, c = cells[idx]
        attempts = 1 + pass2_counts.get((b.band_idx, c), 0)
        pt = find_valid_road_cell_point(b, c, ctx, attempts)
        if pt is not None:
            accepted_points.append(pt)
            placed_count += 1
        if ctx.verbose and (i % ctx.progress_interval == 0
                            or i == total_cells):
            print(
                f"  Processed {i}/{total_cells} cells ({placed_count} points placed)...",
                flush=True)
    return placed_count
