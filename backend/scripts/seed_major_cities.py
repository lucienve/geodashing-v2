"""Seed major cities into the database."""

import os
import sys

import mysql.connector

import backend.scripts.db_utils


def load_admin1_codes(filepath: str) -> dict[str, str]:
    """Loads admin1 codes mapping to ascii names."""
    mapping: dict[str, str] = {}
    if not os.path.exists(filepath):
        print(f"Warning: {filepath} not found.")
        return mapping

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip('\n').split('\t')
            if len(parts) >= 2:
                code = parts[0]
                name = parts[2] if len(parts) > 2 and parts[2] else parts[1]
                mapping[code] = name
    return mapping


def load_country_info(filepath: str) -> dict[str, str]:
    """Loads country ISO to Country Name mapping."""
    mapping: dict[str, str] = {}
    if not os.path.exists(filepath):
        print(f"Warning: {filepath} not found.")
        return mapping

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('#'):
                continue
            parts = line.strip('\n').split('\t')
            if len(parts) > 4:
                iso = parts[0]
                country_name = parts[4]
                mapping[iso] = country_name
    return mapping


def _parse_city_row(
    line: str, admin1_mapping: dict[str, str],
    country_mapping: dict[str,
                          str]) -> tuple[int, str, str, str, str, int] | None:
    """Parses a single tab-delimited GeoNames city line into a DB insert tuple."""
    parts = line.strip('\n').split('\t')
    if len(parts) < 15:
        return None

    geonameid = int(parts[0])
    name = parts[2] if parts[2] else parts[1]
    lat = parts[4]
    lon = parts[5]
    country_code = parts[8]
    admin1_code = parts[10]
    population = int(parts[14]) if parts[14].isdigit() else 0

    # WKT String for SRID 4326 is Point(Lat Lon) in MySQL 8
    wkt_string = f"POINT({lat} {lon})"
    country_name = country_mapping.get(country_code, country_code)
    full_admin_code = f"{country_code}.{admin1_code}"
    admin_name = admin1_mapping.get(full_admin_code, admin1_code)

    return (geonameid, name, admin_name, country_name, wkt_string, population)


_BATCH_SIZE = 5000
_INSERT_CITY_SQL = """
    INSERT INTO major_cities (id, name, admin_name, country_name, location, population)
    VALUES (%s, %s, %s, %s, ST_GeomFromText(%s, 4326), %s)
"""


def seed_database() -> None:
    """Main execution point to load city data into the database."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(current_dir, '../../data')
    config_path = os.path.join(current_dir, '../config.ini')

    cities_file = os.path.join(data_dir, 'cities15000.txt')

    if not os.path.exists(cities_file):
        raise FileNotFoundError(f"Cannot find {cities_file}")

    try:
        print("Loading mapping files...")
        admin1_mapping = load_admin1_codes(
            os.path.join(data_dir, 'admin1CodesASCII.txt'))
        country_mapping = load_country_info(
            os.path.join(data_dir, 'countryInfo.txt'))

        print("Connecting to database...")
        with backend.scripts.db_utils.db_session(config_path) as (conn,
                                                                  cursor):
            cursor.execute("TRUNCATE TABLE major_cities")

            print("Processing cities...")
            batch_data: list[tuple[int, str, str, str, str, int]] = []
            total_processed = 0

            with open(cities_file, 'r', encoding='utf-8') as f:
                for line in f:
                    row = _parse_city_row(line, admin1_mapping,
                                          country_mapping)
                    if row is None:
                        continue
                    batch_data.append(row)

                    if len(batch_data) >= _BATCH_SIZE:
                        cursor.executemany(_INSERT_CITY_SQL, batch_data)
                        conn.commit()
                        total_processed += len(batch_data)
                        print(f"Inserted {total_processed} cities...")
                        batch_data = []

            if batch_data:
                cursor.executemany(_INSERT_CITY_SQL, batch_data)
                conn.commit()
                total_processed += len(batch_data)

            print(f"Successfully seeded {total_processed} cities.")
    except (OSError, RuntimeError, ValueError, mysql.connector.Error) as err:
        print(f"Error seeding major cities: {err}", file=sys.stderr)
        raise


if __name__ == "__main__":
    seed_database()
