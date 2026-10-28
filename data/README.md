# Geodashing Data Directory

This directory stores necessary datasets for running Geodashing features, such
as geographical contextualization algorithms.

## Generating GeoNames Datasets

The geographical contextualization feature requires local demographic data to
function offline and avoid third-party API costs when finding the nearest major
population center.

You can download the latest required GeoNames files directly into this directory
by running the following commands:

```bash
# 1. Download and extract the major cities dataset (cities with population > 15,000)
curl -O http://download.geonames.org/export/dump/cities15000.zip
unzip cities15000.zip
rm cities15000.zip

# 2. Download the administrative area mappings (e.g., State/Province codes to full names)
curl -O http://download.geonames.org/export/dump/admin1CodesASCII.txt

# 3. Download the country code mappings
curl -O http://download.geonames.org/export/dump/countryInfo.txt
```

After downloading these files, you can populate the local database by running
the seed script from the root directory:

```bash
uv run python -m backend.scripts.seed_major_cities
```

## Game Generation Datasets

The core geographic generation logic requires natural earth shapefiles and a bad
words list. You can download them using the following commands:

```bash
# Natural Earth datasets for geographical boundaries
wget https://naciscdn.org/naturalearth/10m/physical/ne_10m_land.zip
wget https://naciscdn.org/naturalearth/10m/physical/ne_10m_lakes.zip
wget https://naciscdn.org/naturalearth/10m/physical/ne_10m_lakes_australia.zip
wget https://naciscdn.org/naturalearth/10m/physical/ne_10m_lakes_europe.zip
wget https://naciscdn.org/naturalearth/10m/physical/ne_10m_lakes_north_america.zip

# List of dirty/bad words for filtering generated dashpoint IDs
curl -s "https://raw.githubusercontent.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words/master/en" | grep -xE '.{4}' | tr '[:lower:]' '[:upper:]' | sort > bad_words.txt
```

## Road Proximity Datasets

The `--algorithm road-proximity` generator mode requires an indexed
OpenStreetMap GeoPackage file (`data/world_drivable_roads.gpkg`) containing
qualifying public drivable roads (`primary`, `secondary`, `tertiary`,
`unclassified`, `residential`, and links).

To ensure dashpoint accessibility and account for road network evolution,
`generate_game.py` validates that `data/world_drivable_roads.gpkg` exists, is
non-empty, and has a file modification time within the last **6 months** (180
days). If the file is missing or older than 6 months, execution halts with an
instruction to download or refresh it.

### Downloading the Road Dataset

Download the pre-compiled global road network GeoPackage directly from Google
Cloud Storage using `gcloud storage cp`:

```bash
gcloud storage cp gs://geodashing-v2-map-data/world_drivable_roads.gpkg data/world_drivable_roads.gpkg
```

### Refreshing the Road Dataset

If the dataset in Cloud Storage is approaching or past 6 months old,
administrators can trigger an automated Cloud Batch compilation job to rebuild
and upload a fresh GeoPackage from the latest planet OSM PBF extract.

The pipeline executes as a containerized job on Container-Optimized OS
(`batch-cos`) in Google Cloud Batch with Image Streaming enabled from Artifact
Registry (`us-east1-docker.pkg.dev/geodashing-v2/batch/prepare-roads:latest`),
leveraging an attached 375 GiB Local NVMe SSD for fast intermediate indexing and
automated retries on Spot VM preemption:

```bash
./backend/scripts/submit_roads_batch_job.sh
```

Monitor job status via the Cloud Batch CLI or Google Cloud Console:

```bash
gcloud batch jobs list --project=geodashing-v2 --location=us-east1 --limit=5
```

Once the batch job reaches `SUCCEEDED`, re-run `gcloud storage cp` to download
the new dataset locally.

### Building Locally from OSM PBF

Alternatively, administrators can compile a custom or local OSM extract using
`prepare_roads.py`:

```bash
# Compile from an existing local OSM PBF extract
uv run python -m backend.scripts.prepare_roads \
  --input data/planet-latest.osm.pbf \
  --output data/world_drivable_roads.gpkg
```
