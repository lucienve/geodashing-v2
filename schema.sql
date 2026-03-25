-- Geodashing Database Schema

-- 1. Users 
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Teams
CREATE TABLE teams (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Team Membership (Many-to-Many logic)
CREATE TABLE team_members (
    team_id INT,
    user_id INT,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (team_id, user_id),
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 4. Games (Represents a 1-month period)
CREATE TABLE games (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(128) NOT NULL, -- Format: "April 2026 Dash" or simply "Game 1"
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Dashpoints (The ~31,000 generated coordinates)
CREATE TABLE dashpoints (
    id VARCHAR(20) PRIMARY KEY, -- Utilizing custom formats like GD-01-XXXX if desired
    game_id INT NOT NULL,
    location POINT SRID 4326 NOT NULL,
    country_code VARCHAR(10),
    state_province VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
);

-- Spatial/Coordinate indexing for fast bounding box queries (Finding points in user's region)
CREATE SPATIAL INDEX idx_dashpoints_location ON dashpoints (location);
CREATE INDEX idx_dashpoints_game ON dashpoints (game_id);

-- 6. Visits / Reports
CREATE TABLE visits (
    id INT AUTO_INCREMENT PRIMARY KEY,
    dashpoint_id VARCHAR(20) NOT NULL,
    user_id INT NOT NULL,
    team_id INT DEFAULT NULL, -- Historical snapshot if the user was on a team when they dashed
    
    -- Submitter's recorded coordinates at the time of visit
    reported_location POINT SRID 4326 NOT NULL,
    distance_meters INT NOT NULL, -- Computed ST_Distance_Sphere result in meters (should be <= 100m)
    
    -- Core Tie-Breaking Variables
    visit_time DATETIME NOT NULL, -- The time from their GPS device/Claim
    reported_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, -- The time the form was submitted online
    
    -- Evidence and Flavor
    notes TEXT,
    photos JSON, -- Array of up to 10 photo paths
    
    -- Scoring state
    score_awarded INT DEFAULT 0, -- Caches 3, 2, or 1 based on PHP evaluation logic
    status ENUM('pending', 'approved', 'rejected') DEFAULT 'approved',
    
    FOREIGN KEY (dashpoint_id) REFERENCES dashpoints(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE SET NULL
);

-- Lookups by dashpoint are highly frequent for score recalculations
CREATE INDEX idx_visits_dashpoint ON visits (dashpoint_id);
-- Lookups by user/team frequently used for Scoreboards
CREATE INDEX idx_visits_user ON visits (user_id);
CREATE INDEX idx_visits_team ON visits (team_id);
