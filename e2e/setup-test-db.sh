#!/bin/bash
set -e

# Default to local testing config, allow CI to override via env vars
DB_HOST=${DB_HOST:-127.0.0.1}
DB_PORT=${DB_PORT:-3306}
DB_NAME=${DB_NAME:-geodashing_test}
DB_USER=${DB_USER:-geodashing_test}
DB_PASS=${DB_PASS:-geodashing_test_secure_pass}

echo "Initializing Geodashing E2E test database..."

# Critical safety guard
if [ "$DB_NAME" = "geodashing" ]; then
    echo "ERROR: Refusing to drop or overwrite the live development 'geodashing' database."
    echo "Please use 'geodashing_test' or another designated testing DB."
    exit 1
fi

echo "Connecting to MySQL at $DB_HOST:$DB_PORT with user $DB_USER..."
echo "Target Database: $DB_NAME"

# 1. Drop existing tables (to ensure clean slate without needing DROP DATABASE permissions everywhere)
# We can just drop the tables individually or just use a helper pipeline if we have DROP DATABASE rights.
# Rather than trying to DROP/CREATE the entire database without root privileges, we just drop the tables if they exist.
# However, the user gave the test user ALL PRIVILEGES ON geodashing_test.* so they can't drop the database geodashing_test but they can DROP all tables.

mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "
    SET FOREIGN_KEY_CHECKS = 0;
    DROP TABLE IF EXISTS visits, dashpoints, games, team_members, teams, users;
    SET FOREIGN_KEY_CHECKS = 1;
"

# 2. Pipe the schema structure
# We must dynamically strip the `USE geodashing;` directive out of schema.sql to prevent 
# overwriting the dev DB if the user executes this script directly.
echo "Loading schema.sql..."
grep -v -E -i "^USE " schema.sql | mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME"

# 3. Inject shared Mock Testing Data
echo "Injecting mock CI Test Game..."
mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "
    INSERT INTO games (id, title, start_time, end_time, is_active) 
    VALUES (1, 'CI Test Game', DATE_SUB(NOW(), INTERVAL 1 DAY), DATE_ADD(NOW(), INTERVAL 30 DAY), TRUE);
"

echo "Test database initialized successfully!"
