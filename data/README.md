# Geodashing Data Directory

This directory stores necessary datasets for running Geodashing features, such as geographical contextualization algorithms.

## Generating GeoNames Datasets

The geographical contextualization feature requires local demographic data to function offline and avoid third-party API costs when finding the nearest major population center.

You can download the latest required GeoNames files directly into this directory by running the following commands:

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

After downloading these files, you can populate the local database by running the seed script from the root directory:

```bash
python3 backend/scripts/seed_major_cities.py
```

## Game Generation Datasets

The core geographic generation logic requires natural earth shapefiles and a bad words list. You can download them using the following commands:

```bash
# Natural Earth datasets for geographical boundaries
wget https://naciscdn.org/naturalearth/10m/physical/ne_10m_land.zip
wget https://naciscdn.org/naturalearth/10m/physical/ne_10m_lakes.zip

# List of dirty/bad words for filtering generated dashpoint IDs
curl -s "https://raw.githubusercontent.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words/master/en" | grep -xE '.{4}' | tr '[:lower:]' '[:upper:]' | sort > bad_words.txt
```
