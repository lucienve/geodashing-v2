"""Seed major cities into the database."""

import os

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


def seed_database() -> None:
    """Main execution point to load city data into the database."""
    # pylint: disable=too-many-locals

    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(current_dir, '../../data')
    config_path = os.path.join(current_dir, '../config.ini')

    cities_file = os.path.join(data_dir, 'cities15000.txt')
    admin1_file = os.path.join(data_dir, 'admin1CodesASCII.txt')
    country_file = os.path.join(data_dir, 'countryInfo.txt')

    if not os.path.exists(cities_file):
        raise FileNotFoundError(f"Cannot find {cities_file}")

    print("Loading mapping files...")
    admin1_mapping = load_admin1_codes(admin1_file)
    country_mapping = load_country_info(country_file)

    print("Connecting to database...")
    with backend.scripts.db_utils.db_session(config_path) as (conn, cursor):
        # Optional: Clear existing data
        cursor.execute("TRUNCATE TABLE major_cities")

        insert_sql = """
            INSERT INTO major_cities (id, name, admin_name, country_name, location, population)
            VALUES (%s, %s, %s, %s, ST_GeomFromText(%s, 4326), %s)
        """

        print("Processing cities...")
        batch_data = []
        batch_size = 5000
        total_processed = 0

        with open(cities_file, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip('\n').split('\t')
                if len(parts) < 15:
                    continue

                geonameid = int(parts[0])
                name = parts[2] if parts[2] else parts[
                    1]  # ascii name or local name
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

                batch_data.append((geonameid, name, admin_name, country_name,
                                   wkt_string, population))

                if len(batch_data) >= batch_size:
                    cursor.executemany(insert_sql, batch_data)
                    conn.commit()
                    total_processed += len(batch_data)
                    print(f"Inserted {total_processed} cities...")
                    batch_data = []

        if batch_data:
            cursor.executemany(insert_sql, batch_data)
            conn.commit()
            total_processed += len(batch_data)

        print(f"Successfully seeded {total_processed} cities.")


if __name__ == "__main__":
    seed_database()
