# Spatial Filtering Memory Optimization & GeoPackage Architecture

## 1. Executive Summary

During game generation and dashpoint candidate validation using OpenStreetMap
water and coastline data (`data/world_osm_water.gpkg`, 5.25 GB on disk), global
in-memory projection and indexing crashed with exit status 137 (Linux Out-Of-
Memory Killer) after exceeding 14.3 GB RSS.

This document details the root-cause analysis, the mathematical and empirical
findings that disproved simpler optimization hypotheses, the design and
verification of the on-demand R-tree spatial filter (`GpkgSpatialFilter`), and a
reusable diagnostic playbook for future agent sessions performing spatial
pipeline modifications.

## 2. Dataset Anatomy & Internal Byte Distribution

SQLite and GeoPackage inspection of `data/world_osm_water.gpkg` reveals the
following internal storage distribution across its 2.54 million features:

| Layer                    | Feature Count |      WKB Geometry Data | Max Single Polygon |     Vertex Count |
| :----------------------- | ------------: | ---------------------: | -----------------: | ---------------: |
| `land`                   |       873,875 |             1,318.1 MB |            2.63 MB |      ~82 million |
| `water`                  |     1,670,128 |             3,563.2 MB |            5.84 MB |     ~223 million |
| **Total WKB**            | **2,544,003** | **4,881.3 MB (93.0%)** |                  — | **~305 million** |
| **Attributes & Indexes** |             — |    **368.3 MB (7.0%)** |                  — |                — |

### Why Stripping String Attributes Alone Fails

The 12 OpenStreetMap string tags (`natural`, `water`, `wetland`, `waterway`,
`landuse`, etc.) and SQLite R-tree index tables combined account for only 7.0%
(368.3 MB) of the file. Raw 64-bit polygon vertex coordinate data accounts for
93.0% (4.88 GB). Deserializing 305 million vertices into C++ `GEOSGeometry`
instances, projecting them to `EPSG:6933`, and preparing monotone chains in RAM
fundamentally exceeds 14.3 GB even when passing `columns=[]`.

## 3. Analysis of Failure Modes & Disproved Hypotheses

### 3.1 Global Grid Feature Selectivity

An initial hypothesis assumed that evaluating whole-globe grids (such as a 500
km dry-run grid) would only touch a small subset of water bodies. Empirical
simulation of `build_spherical_grid()` directly against the R-tree index tables
disproved this:

- **500.0 km grid (2,041 cells, 1,109 candidate land boxes):** Touches 873,875 /
  873,875 (100.0%) of `land` envelopes and 1,670,128 / 1,670,128 (100.0%) of
  `water` envelopes.
- **60.05 km production grid (141,439 cells, 48,153 candidate land boxes):**
  Touches 873,875 / 873,875 (100.0%) of `land` envelopes and 1,670,125 /
  1,670,128 (99.9998%) of `water` envelopes.

Because any spherical grid partitions the entire surface of the Earth, the union
of candidate land cells covers the entire global landmass. Pre-fetching all
matched water IDs across candidate cells loads the entire 4.88 GB GeoPackage
into memory (~10.5 GB RSS), regardless of cell size.

### 3.2 Tiling Asymmetry & Bounding-Box Sum Heuristic Failure

A second hypothesis proposed comparing the largest land polygon area against the
sum of water bounding-box areas in each cell
(`max_land_area > sum_water_bbox_area`). Inspection of the R-tree tables
revealed a critical structural asymmetry:

- `land` features originate from `land-polygons-split-4326` and are pre-tiled
  into $1^\circ \times 1^\circ$ squares (max extent $1.11^\circ \times
  1.00^\circ$, max area $\le 1.0\text{ deg}^2$).
- `water` features are unsplit multipolygons with bounding boxes extending up to
  $9.97^\circ \times 10.41^\circ$.

In dense lake regions (e.g., Canadian Shield, Finland), a single 500 km cell
contains up to 156,839 water envelopes, and a 60.05 km cell contains up to 9,358
water envelopes. The sum of overlapping diagonal water bounding boxes severely
over-approximates actual water surface area. Consequently:

- 41.0% (454 / 1,108) of 500 km candidate boxes fail the heuristic, touching
  94.6% (1,579,560) of all water polygons.
- 7.7% (3,723 / 48,145) of 60.05 km candidate boxes fail the heuristic, touching
  41.0% (684,179) of all water polygons.

### 3.3 GEOS `union_all` Superlinear Complexity and Topology Exceptions

Attempting to evaluate contested cells by unioning all matched water polygons
(`shapely.union_all(clipped_waters)`) causes two severe issues:

1. Superlinear $O(N \log N)$ execution time when unioning thousands of complex
   polygons, causing multi-minute CPU stalls on single cells.
2. `shapely.errors.GEOSException: TopologyException: side location conflict`
   where adjacent OpenStreetMap water features share nearly identical boundary
   segments with subtle floating-point precision differences.

### 3.4 SQLite `numpy.int64` Parameter Binding

Python's `sqlite3` driver does not bind `numpy.int64` values (from NumPy array
indexing) as SQL integers in `WHERE fid IN (?)`. Instead, it binds them as
unrecognized types, returning empty results (`[]`). All feature IDs passed to
SQLite queries must be explicitly cast to Python `int(fid)`.

## 4. Architecture & Mathematical Guarantees

### 4.1 Individual Point Filtering (`filter_valid_indices`)

Candidate points across all generation algorithms (`random`, `grid`,
`road-proximity`) and `reroll_dashpoint.py` are evaluated with zero loss in
resolution or accuracy:

1. **Search Box Scaling:** For point $P = (\text{lon}, \text{lat})$, a local
   bounding box is constructed with half-width $\Delta = 0.002 /
   \max(\cos(\text{lat}), 0.01)^\circ \ge 222.6\text{ meters}$, which exceeds
   twice the 100-meter buffer radius. Antimeridian crossings and polar caps
   expand the longitude bounds to $(-180^\circ, 180^\circ)$.
2. **Envelope Pre-Filtering:** Points in open ocean hit 0 `land_tree` envelopes
   and are rejected in $< 0.05\text{ seconds}$ without reading SQLite.
3. **On-Demand Clipped WKB Evaluation:** For candidate points, only the polygons
   intersecting the local search box are fetched by primary key (`fid`), clipped
   via `shapely.clip_by_rect()`, subtracted via `_safe_difference()`, projected
   to `EPSG:6933`, and tested against $P$'s 100m buffer.

Because Boolean intersection with a 100m buffer depends solely on geometry
within 100m of $P$, local clipping produces identical mathematical results to
global geometry evaluation while using $< 1.55\text{ GB}$ peak RAM.

### 4.2 Iterative Witness-Point Grid Classification (`classify_grid_cells`)

A grid cell $B$ contains dry land if and only if there exists a witness point:

$$\exists p \in (B \cap \text{Land}) \setminus \text{Water}$$

Instead of unioning all water polygons in $B$:

1. Sort matched `land` envelopes by area descending (checking mainland tiles
   before small coastal islets).
2. Fetch `l_geom` via a 256-entry LRU cache and clip to $B$: `cl_land`.
3. Loop while `not cl_land.is_empty and cl_land.area > 1e-12`:
   - Compute `rep_pt = cl_land.representative_point()`.
   - Query `water_tree.query(rep_pt, predicate='intersects')` (a point query
     matching only 0 to 2 water envelopes covering that point).
   - If no water polygon covers `rep_pt`, $B$ is proven to contain dry land
     (`land_cell`). Terminate immediately with zero water unions.
   - If a water polygon covers `rep_pt`, subtract only that single clipped water
     polygon from `cl_land` via `_safe_difference()` and repeat.
4. If all land pieces are subtracted to empty, $B$ is a `water_cell`.

**Mathematical Guarantees:**

- **Zero False Positives:** A cell is marked as land only when an explicit point
  $p \in B$ is verified to lie inside land and outside all water.
- **Zero False Negatives:** A land polygon is discarded only when covering water
  polygons reduce its dry area below $10^{-12}\text{ deg}^2$ ($\approx
  0.01\text{ m}^2$).
- **Guaranteed Finite Termination:** Tracking `tried_w_fids` ensures no water
  polygon is subtracted twice, bounding loop iterations by $|W_{\text{cell}}|$.

### 4.3 Performance & Telemetry Summary

| Metric                               | Legacy In-Memory Loading  | `GpkgSpatialFilter` On-Demand    |
| :----------------------------------- | :------------------------ | :------------------------------- |
| **Peak RAM (`generate_game.py`)**    | > 14.3 GB (OOM Crash 137) | **1.55 GB**                      |
| **Peak RAM (`reroll_dashpoint.py`)** | Up to several GB          | **~140–250 MB**                  |
| **Startup Latency**                  | > 60s before crashing     | **4.8s** (streams R-trees)       |
| **60.05 km Grid Classification**     | Stalls / Crashes          | **10.8s** (141,447 cells)        |
| **500.0 km Grid Classification**     | Stalls / Crashes          | **0.79s** (2,040 cells)          |
| **50,000 Random Points Filter**      | Crashes before filtering  | **0.95s**                        |
| **LRU Cache Hit Rate (256 entries)** | N/A                       | **57.0%** (33,121 hits / 58,118) |

## 5. Reusable Diagnostic & Profiling Playbook

Future agent sessions evaluating spatial dataset updates or algorithm changes
must follow this verification sequence:

### Step 1: GeoPackage & R-Tree Structural Inspection

Execute read-only SQL queries to inspect layer record counts, byte sizes, and
R-tree bounding-box extent distributions:

```bash
uv run python -c "
import sqlite3
conn = sqlite3.connect('file:data/world_osm_water.gpkg?mode=ro', uri=True)
cur = conn.cursor()
for table in ('land', 'water'):
    cur.execute(f'SELECT COUNT(*), SUM(LENGTH(geom)) FROM {table}')
    count, bytes_total = cur.fetchone()
    cur.execute(f'SELECT MAX(maxx - minx), MAX(maxy - miny) FROM rtree_{table}_geom')
    max_dx, max_dy = cur.fetchone()
    print(f'{table}: {count:,} rows, {bytes_total / 1024**2:.1f} MB WKB, max extent ({max_dx:.2f} x {max_dy:.2f}) deg')
"
```

### Step 2: Grid Selectivity & Overlap Simulation

Before implementing full geometry algorithms, simulate R-tree envelope hits
against the spherical grid to measure selectivity and detect worst-case cells:

```bash
uv run python -c "
from backend.scripts.generate_game import build_spherical_grid
from backend.scripts.road_proximity import _build_cell_bounding_boxes
from backend.scripts.road_proximity import GpkgSpatialFilter

sf = GpkgSpatialFilter('data/world_osm_water.gpkg', verbose=False)
bands = build_spherical_grid(60.05)
flat_cells, boxes, _ = _build_cell_bounding_boxes(bands)
l_hits = sf.land_tree.query(boxes, predicate='intersects')
print(f'Candidate land boxes: {len(set(l_hits[0]))} / {len(boxes)}')
sf.close()
"
```

### Step 3: Geographical Canary Suite Verification

Run the 8-point geographical canary suite covering edge cases across open ocean,
major lakes, reservoirs, inundated wetlands, island-in-lake, and inland dry
land:

```bash
uv run python -c "
import shapely
from backend.scripts.road_proximity import GpkgSpatialFilter

cases = [
    ('Mid-Atlantic Ocean', 0.0, -30.0, False),
    ('Lake Superior', 47.70, -87.50, False),
    ('Lake Okeechobee', 26.95, -80.80, False),
    ('Everglades Wetland', 25.60, -80.85, False),
    ('Lake Mindemoya (lake on island)', 45.75, -82.20, False),
    ('Manitoulin Island (dry land)', 45.85, -82.20, True),
    ('Waconda Lake Reservoir (KS)', 39.50, -98.35, False),
    ('Central Kansas Farmland (dry land)', 38.50, -98.50, True),
]
sf = GpkgSpatialFilter('data/world_osm_water.gpkg', verbose=False)
pts = [shapely.geometry.Point(lon, lat) for _, lat, lon, _ in cases]
valid = sf.filter_valid_indices(pts)
for i, (name, lat, lon, expected) in enumerate(cases):
    actual = i in valid
    assert actual == expected, f'Canary {name} failed: expected {expected}, got {actual}'
print('All 8 geographical canary tests passed successfully.')
sf.close()
"
```

### Step 4: Memory & CPU Profiling

Measure wall-clock time and peak resident set size using `/usr/bin/time -v`:

```bash
/usr/bin/time -v uv run python -c "
from backend.scripts.generate_game import generate_valid_dashpoints
pts = generate_valid_dashpoints(target_count=50, land_zip_path='data/world_osm_water.gpkg', lakes_zip_path='')
print(f'Generated {len(pts)} dashpoints.')
"
```

Verify that `Maximum resident set size` remains strictly below 2,000,000 KB (2.0
GB) and exit status is 0.
