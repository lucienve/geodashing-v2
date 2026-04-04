# Geodashing V2 - Project Context

## Overview
Geodashing V2 is a reimplementation of the classic GeoDashing game originally created by Scout. 
The application allows users to participate in global geographic games where they are tasked with reaching randomly generated "dashpoints" across the world.

## Architectural Decisions
- **Core Stack**: 
  - **Frontend**: Vanilla JS (ES6+), Semantic HTML5, Vanilla CSS3. **No Heavy Frameworks** (React/Vue/etc. are strictly prohibited). Logic is decoupled into separate files (`api.js`, `app.js`, `controllers.js`, `map.js`).
  - **Backend**: Primary API layer written in **PHP 8.3.6** (`backend/api`) supplemented with **Python 3.12** for server-side scripts / game generation algorithms (`generate_game.py`).
  - **Database**: **MySQL 8.4.8** using native drivers (PDO for PHP, `mysql-connector-python` for Python). **No ORM is used**. All queries are securely handled via explicit parameterized statements.
  - **Media Storage**: Google Cloud Storage buckets handle user-uploaded photos natively via PHP APIs.
- **Security Posture**: 
  - Centralized session handling (`session.php`) enforces `SameSite=Strict` rules and oversees a global CSRF token architecture. 
  - Strict input validation against Stored XSS via `escapeHTML` for dynamic DOM additions, and robust email verification workflows to prevent header injection.
  - Account integrity ensures login requirements for point-logging and log modification.
- **UI/UX Directives**: 
  - Implementation requires rich aesthetics prioritizing strong responsiveness and mobile-first logic. Includes native mobile photo uploads, responsive layouts, GPS syncing, Google Maps `AdvancedMarkerElement`, and marker clustering.
- **Testing Constraints**:
  - PHPUnit test files must exclusively live in `backend/tests/` and mirror the structure of the classes they test, rather than in the project root.

## Detailed Milestones & Implementation History

### 1. Engine & Data Generation 
- Established the base database schemas (`schema.sql`), enforcing strict procedural queries over ORMs.
- Implemented Python routines using `geopandas` and `shapely` to randomize and insert dashpoints geographically, accounting for explicit exclusions like major lakes. 
- Format of dashpoint IDs successfully transitioned from numeric to alphanumeric to match classical standards.

### 2. Core API Layer & Authentication
- Built PHP endpoints for authentication, securely logging users in, mandating secure email verifications, and facilitating password resets.
- Added comprehensive reporting features including the ability for users to append logs up to 10k characters. Enabled capabilities for users to dynamically edit their own prior log entries.
- Developed RESTful search and export endpoints for dashpoints.

### 3. Media Capabilities
- Integrated `google/cloud-storage` strictly on the PHP layer. Developed bucket management to securely funnel user photo uploads from live capture or mobile galleries.
- Baked in EXIF functionality to automatically parse location coordinates from uploaded photos, utilizing local and server capabilities to validate report distances dynamically.

### 4. Interactive Mapping & Frontend
- Built out the core web UI using Vanilla JS leveraging standard Google Maps APIs. Upgraded legacy map features dynamically to Modern `AdvancedMarkerElement` standards.
- Implemented core exploratory features: marker clustering at high zoom levels, geographic centering controls, dynamic color styling for visited dashpoints, and interactive layer toggling.
- Iterated heavily for mobile user experiences, trimming redundancies like extra form buttons, and perfecting GPS coordinate syncing.

### 5. Historical Data & User Profiles
- Implemented immutability controls ensuring logs and scoring for completed games are strictly locked on the backend utilizing native SQL JOIN checks.
- Constructed a global UI paradigm mapping past games to global states allowing the user to context-switch effortlessly between historical snapshots over the entire frontend (Map, Leaderboard).
- Constructed dynamic `#profile` single page architecture, aggregating total lifetime points, dashpoints accessed, and a complete ledger of previous historical games.

## Current Plan / Roadmap (Aggregated)
1. **User Profiles**: Build a 'Trophy Cabinet' for milestones.
2. **Team Play Ecosystem**: 
   - Construct services for Team Creation/Joining. 
   - Restructure UI (`LeaderboardService.php`) and templates to dynamically support toggling between `SOLO` and `TEAM` rankings.
   - Refactor score attribution logs to account for both individual players and their overarching teams.
3. **Geographic Records**: Track extreme geographical records (farthest N/S/E/W traveled) per country or state.
