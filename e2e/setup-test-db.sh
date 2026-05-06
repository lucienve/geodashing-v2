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

echo "Waiting for MySQL to become ready (up to 30s)..."
for i in {1..30}; do
    if mysqladmin ping -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" --silent; then
        echo "MySQL is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "ERROR: MySQL did not become ready in time."
        exit 1
    fi
    sleep 1
done

# 1. Drop existing tables (to ensure clean slate without needing DROP DATABASE permissions everywhere)
# We can just drop the tables individually or just use a helper pipeline if we have DROP DATABASE rights.
# Rather than trying to DROP/CREATE the entire database without root privileges, we just drop the tables if they exist.
# However, the user gave the test user ALL PRIVILEGES ON geodashing_test.* so they can't drop the database geodashing_test but they can DROP all tables.

TABLES=$(mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" -N -B -e "SHOW TABLES IN \`$DB_NAME\`")

if [ -n "$TABLES" ]; then
    DROP_QUERY="SET FOREIGN_KEY_CHECKS = 0;"
    for TABLE in $TABLES; do
        DROP_QUERY="$DROP_QUERY DROP TABLE IF EXISTS \`$TABLE\`;"
    done
    DROP_QUERY="$DROP_QUERY SET FOREIGN_KEY_CHECKS = 1;"
    mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "$DROP_QUERY"
fi

# 2. Pipe the schema structure
# We must dynamically strip the `USE geodashing;` directive out of schema.sql to prevent 
# overwriting the dev DB if the user executes this script directly.
echo "Loading schema.sql..."
grep -v -E -i "^USE " schema.sql | mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME"

# 3. Inject shared Mock Testing Data
echo "Injecting mock CI Test Game, User, and Dashpoint..."

# Generate a valid PHP password hash natively
PASSWORD_HASH=$(php -r "echo password_hash('testpass', PASSWORD_DEFAULT);")

mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "
    -- Game 1 (Historical)
    INSERT INTO games (id, title, start_time, end_time, is_active) 
    VALUES (1, 'Historical Game', DATE_SUB(NOW(), INTERVAL 35 DAY), DATE_SUB(NOW(), INTERVAL 5 DAY), FALSE);

    -- Game 2 (Active)
    INSERT INTO games (id, title, start_time, end_time, is_active) 
    VALUES (2, 'CI Test Game', DATE_SUB(NOW(), INTERVAL 1 DAY), DATE_ADD(NOW(), INTERVAL 30 DAY), TRUE);
    
    -- Game 3 (Preview)
    INSERT INTO games (id, title, start_time, end_time, is_active) 
    VALUES (3, 'Preview Test Game', DATE_ADD(NOW(), INTERVAL 31 DAY), DATE_ADD(NOW(), INTERVAL 60 DAY), FALSE);

    
    -- Test User
    INSERT INTO users (id, username, email, password_hash, is_verified)
    VALUES (1, 'TestUser', 'testuser@example.com', '${PASSWORD_HASH}', TRUE);
    
    -- Test Dashpoints
    -- Game 1 dashpoint (London)
    INSERT INTO dashpoints (id, game_id, location, country_code, state_province)
    VALUES ('GD000-AAAA', 1, ST_GeomFromText('POINT(51.5074 -0.1278)', 4326), 'UK', 'ENG');

    -- Game 2 dashpoint (NYC)
    INSERT INTO dashpoints (id, game_id, location, country_code, state_province)
    VALUES ('GD001-AAAA', 2, ST_GeomFromText('POINT(40.7128 -74.0060)', 4326), 'US', 'NY');

    -- Game 3 dashpoint (Paris)
    INSERT INTO dashpoints (id, game_id, location, country_code, state_province)
    VALUES ('GD002-AAAA', 3, ST_GeomFromText('POINT(48.8566 2.3522)', 4326), 'FR', 'IDF');


    -- Mock historical visit for TestUser on Game 1 dashpoint
    INSERT INTO visits (id, dashpoint_id, user_id, team_id, reported_location, distance_meters, reported_time, score_awarded, status)
    VALUES (1, 'GD000-AAAA', 1, NULL, ST_GeomFromText('POINT(51.5074 -0.1278)', 4326), 0, DATE_SUB(NOW(), INTERVAL 10 DAY), 3, 'approved');
"

echo "Test database initialized successfully!"
