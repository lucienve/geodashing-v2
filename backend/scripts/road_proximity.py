"""Spatial road-proximity sampling and grid-cell placement primitives."""

import dataclasses
import math
import typing

import geopandas as gpd
import numpy as np
import pyogrio
import shapely
import shapely.affinity
import shapely.geometry
import shapely.geometry.base

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
