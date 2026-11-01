# Geodashing Data Directory

This directory stores datasets, configuration assets, and few-shot examples
required for game generation, spatial validation, geographic contextualization,
and AI summary generation.

## Version Control & File Tracking Policy

Files in this directory follow an explicit tracking policy configured in the
root `.gitignore`:

- **Tracked in Version Control**:
  - `README.md`: This documentation guide.
  - `game_titles.json`: Curated list of game titles used during monthly rollover
    and manual game generation.
  - `summary_system_instructions.txt`: System instructions provided to Gemini
    models for monthly game summary generation.
  - `summary_examples/`: Few-shot training pairs (`game_*_input.txt` and
    `game_*_output.html`) used to condition the LLM summary generator.
- **Untracked (Downloaded or Compiled Externally)**:
  - `bad_words.txt`: LDNOOBW profane wordlist for dashpoint ID filtering.
  - GeoNames files: `cities15000.txt`, `admin1CodesASCII.txt`, and
    `countryInfo.txt`.
  - GeoPackages: `world_osm_water.gpkg` and `world_drivable_roads.gpkg` (and any
    SQLite WAL/SHM companion files).
  - OpenStreetMap extracts and shapefile archives: `*.osm.pbf`,
    `land-polygons-split-4326.zip`, and general `*.zip` files.
  - Temporary or download cache directories: `cache/`, `*.tmp`, `*.part*`, and
    `*.aria2`.

---

## Game Generation & Spatial Datasets

Game generation (`generate_game.py`) and dashpoint relocation
(`reroll_dashpoint.py`) rely exclusively on OpenStreetMap-derived GeoPackage
datasets and a profanity filter list. Legacy Natural Earth shapefiles
(`ne_10m_*`) have been completely retired.

### Profanity Filter List (`bad_words.txt`)

To ensure generated dashpoint IDs do not spell offensive 4-letter words,
download and sort the 4-letter subset from the LDNOOBW repository:

```bash
curl -s "https://raw.githubusercontent.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words/master/en" | grep -xE '.{4}' | tr '[:lower:]' '[:upper:]' | sort > data/bad_words.txt
```

---

## Water & Coastline Dataset (`world_osm_water.gpkg`)

To prevent dashpoints from landing in open oceans, lakes, wide riverbanks,
reservoirs, and wetlands, game generation and dashpoint rerolling require
`data/world_osm_water.gpkg`.

The GeoPackage contains two R-tree indexed spatial layers:

- `land`: Global coastline polygons pre-split on a 0.5-degree grid, compiled
  from the official OSM coastline dataset (`land-polygons-split-4326.zip`).
- `water`: Global inland water and inundated wetland polygons extracted from
  `planet-latest.osm.pbf` (`natural=water`, `waterway=riverbank`,
  `landuse=reservoir,basin`, and `natural=wetland`).

### Freshness Requirement

To maintain geographical accuracy as water bodies and coastlines change,
`generate_game.py` and `reroll_dashpoint.py` enforce a strict **6-month (180
days)** freshness gate on `data/world_osm_water.gpkg`. If the file is missing,
empty, or older than 180 days, execution halts immediately with an actionable
error message.

### Downloading the Water Dataset

Download the pre-compiled GeoPackage directly from Google Cloud Storage:

```bash
gcloud storage cp gs://geodashing-v2-map-data/world_osm_water.gpkg data/world_osm_water.gpkg
```

### Refreshing the Water Dataset via Google Cloud Batch

Administrators can trigger an automated Cloud Batch compilation job to rebuild
and publish a fresh water GeoPackage from the latest planet OSM PBF extract:

```bash
# Standard compilation with GCS caching and checkpointing
./backend/scripts/submit_water_batch_job.sh

# Force recompilation (bypassing GCS cache and freshness checks)
./backend/scripts/submit_water_batch_job.sh --force
```

Monitor job status via the Cloud Batch CLI:

```bash
gcloud batch jobs list --project=geodashing-v2 --location=us-east1 --limit=5
```

### Building Locally with `prepare_water.py`

Administrators can also compile the water dataset locally. Note that
`prepare_water.py` automatically downloads or consumes the upstream OSM
coastline archive `land-polygons-split-4326.zip` (from
`https://osmdata.openstreetmap.de/download/land-polygons-split-4326.zip`), which
is used to compile the `land` layer:

```bash
uv run python -m backend.scripts.prepare_water \
  --osm-pbf data/planet-latest.osm.pbf \
  --land-zip data/land-polygons-split-4326.zip \
  --output data/world_osm_water.gpkg
```

---

## Road Proximity Dataset (`world_drivable_roads.gpkg`)

The `--algorithm road-proximity` generator mode requires an indexed
OpenStreetMap GeoPackage file (`data/world_drivable_roads.gpkg`) containing
qualifying public drivable roads (`primary`, `secondary`, `tertiary`,
`unclassified`, `residential`, and links).

Like the water dataset, `world_drivable_roads.gpkg` must be non-empty and
refreshed within the last **6 months** (180 days).

### Downloading the Road Dataset

Download the pre-compiled global road network GeoPackage directly from Google
Cloud Storage:

```bash
gcloud storage cp gs://geodashing-v2-map-data/world_drivable_roads.gpkg data/world_drivable_roads.gpkg
```

### Refreshing the Road Dataset via Google Cloud Batch

```bash
# Standard compilation with GCS checkpointing and early-exit guards
./backend/scripts/submit_roads_batch_job.sh

# Force recompilation (bypassing GCS cache and freshness checks)
./backend/scripts/submit_roads_batch_job.sh --force
```

### Building Locally with `prepare_roads.py`

```bash
uv run python -m backend.scripts.prepare_roads \
  --input data/planet-latest.osm.pbf \
  --output data/world_drivable_roads.gpkg
```

---

## GeoNames Datasets (Geographical Contextualization)

The nearest-city contextualization feature requires local demographic data to
function offline and avoid third-party API costs when locating the nearest major
population center.

Download and seed the GeoNames files into the local database:

```bash
# 1. Download and extract major cities (population > 15,000)
curl -O http://download.geonames.org/export/dump/cities15000.zip
unzip cities15000.zip
rm cities15000.zip

# 2. Download administrative area mappings (state/province codes to names)
curl -O http://download.geonames.org/export/dump/admin1CodesASCII.txt

# 3. Download country code mappings
curl -O http://download.geonames.org/export/dump/countryInfo.txt

# 4. Populate the local database
uv run python -m backend.scripts.seed_major_cities
```

---

## Summary Generation & Evaluation Datasets

The files below support the monthly game summary generation engine
(`backend/scripts/generate_summary.py`) and automated LLM regression evaluation
(`backend/tests/test_summary_evaluation.py`).

### `game_titles.json`

A version-controlled JSON list of creative, thematic titles used during monthly
game rollover (`game_utils.py`) and CLI initialization (`generate_game.py`).

### `summary_system_instructions.txt`

The canonical prompt system instruction file instructing Gemini models on the
persona, tone, formatting conventions, and HTML tag constraints for generating
monthly wrap-up emails.

### `summary_examples/`

A directory containing paired few-shot interaction examples:

- `game_{id}_input.txt`: Structured game data including final standings, top
  dashpoints, and player visit log extracts.
- `game_{id}_output.html`: Curated, human-verified HTML output meeting all
  layout, styling, and link conventions.

These pairs are loaded dynamically by `load_chat_history()` in
`generate_summary.py` to condition the Gemini model via multi-turn few-shot
in-context learning. They are also used as benchmark cases in
`test_summary_evaluation.py` to evaluate tone, accuracy, and narrative quality.
