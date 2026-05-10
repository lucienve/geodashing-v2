-- Geodashing Database Schema
USE geodashing;

-- 1. Users 
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_verified BOOLEAN DEFAULT FALSE,
    verification_token VARCHAR(64) NULL,
    reset_token VARCHAR(64) NULL,
    reset_token_expires TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Teams
CREATE TABLE teams (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Team Membership (Many-to-Many logic)
CREATE TABLE team_members (
    team_id INT,
    user_id INT,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (team_id, user_id),
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. Games (Represents a 1-month period)
CREATE TABLE games (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL, -- Format: "The game title"
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. Dashpoints (The ~31,000 generated coordinates)
CREATE TABLE dashpoints (
    id VARCHAR(20) PRIMARY KEY, -- Format like GD001-AAAA
    game_id INT NOT NULL,
    location POINT SRID 4326 NOT NULL,
    country_code VARCHAR(10),
    state_province VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
    reported_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, -- The exact time the API received the request (FCFS Logic)
    edited_at DATETIME NULL DEFAULT NULL, -- Structural tracking identifying when a post-log Field Note modification occurred
    
    -- Evidence and Flavor
    notes TEXT,
    photos JSON, -- Array of up to 10 photo paths
    
    -- Scoring state
    score_awarded INT DEFAULT 0, -- Caches 3, 2, or 1 based on PHP evaluation logic
    is_attempt BOOLEAN DEFAULT FALSE, -- True if the user logged this as a 0-point attempt
    status ENUM('pending', 'approved', 'rejected') DEFAULT 'approved',
    
    FOREIGN KEY (dashpoint_id) REFERENCES dashpoints(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Lookups by dashpoint are highly frequent for score recalculations
CREATE INDEX idx_visits_dashpoint ON visits (dashpoint_id);
-- Lookups by user/team frequently used for Scoreboards
CREATE INDEX idx_visits_user ON visits (user_id);
CREATE INDEX idx_visits_team ON visits (team_id);

-- 7. Major Cities (For Geographic Contextualization)
CREATE TABLE major_cities (
    id INT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    admin_name VARCHAR(255),
    country_name VARCHAR(255),
    location POINT SRID 4326 NOT NULL,
    population INT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Spatial index to quickly find cities near dashpoints
CREATE SPATIAL INDEX idx_major_cities_location ON major_cities (location);
