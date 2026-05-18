# Geodashing V2 - Project Context

## Overview
Geodashing V2 is a reimplementation of the classic GeoDashing game originally created by Scout. 
The application allows users to participate in global geographic games where they are tasked with reaching randomly generated "dashpoints" across the world.

## Architectural Decisions
- **Core Stack**: 
  - **Frontend**: Vanilla JS (ES6+), Semantic HTML5, Vanilla CSS3. **No Heavy Frameworks** (React/Vue/etc. are strictly prohibited). Logic is decoupled into separate files (`api.js`, `app.js`, `controllers.js`, `map.js`).
  - **Backend**: Primary API layer written in **PHP 8.3.6** (`public/api`) supplemented with **Python 3.11+** for server-side scripts / game generation algorithms (`generate_game.py`), remaining backward compatible with Debian 12.
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
  - Playwright E2E tests are used for automated layout testing and verify the UI constraints across devices without hanging.
  - Lighthouse tests are integrated to enforce SEO, accessibility, and performance best practices.

## Detailed Milestones & Implementation History

### 1. Engine & Data Generation 
- Established the base database schemas (`schema.sql`), enforcing strict procedural queries over ORMs.
- Implemented Python routines using `geopandas` and `shapely` to randomize and insert dashpoints geographically, accounting for explicit exclusions like major lakes. 
- Format of dashpoint IDs successfully transitioned from numeric to alphanumeric to match classical standards.

### 2. Core API Layer & Authentication
- Built PHP endpoints for authentication, securely logging users in, mandating secure email verifications, and facilitating password resets.
- Added comprehensive reporting features including the ability for users to append logs up to 10k characters. Enabled capabilities for users to dynamically edit their own prior log entries.
- Implemented automated HTML email notifications that dispatch dashpoint log details (including inline photos and real-time scoring updates) to a configured mailing list immediately after a successful dashpoint claim.
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

### 6. Backend Modernization & Rule Compliance
- Migrated all monolithic PHP API scripts into dedicated PSR-4 namespaced Service classes.
- Enabled native Composer autoloading mapped to the `backend/` directory, establishing structured unit testing capabilities.
- Enforced strict PSR-12 formatting across the entire backend verified natively via `phpcs`.
- Integrated `declare(strict_types=1);` natively into every PHP file to strictly enforce type safety.
- Added comprehensive PHPDoc documentation across all Service layers and stripped dramatic/unprofessional tones from logging, strictly complying with new engineering standards.

### 7. E2E Testing Synchronization & Infrastructure
- Modernized and unified the Geodashing Playwright E2E test suite to ensure architectural consistency between the local development environment and the GitHub Actions CI pipeline.
- Established a hermetic testing environment by isolating E2E execution exclusively to a dedicated `geodashing_test` database, completely preventing accidental pollution of the live development schema.
- Built a unified database bootstrapping script (`e2e/setup-test-db.sh`) which is directly consumed by the CI workflow and automatically evaluated by a Playwright global setup hook (`e2e/global-setup.js`) locally.
- Implemented secure environment interception within `backend/Database.php` routing securely to test credentials dynamically via `APP_ENV=testing` without altering any configuration states. 
- Integrated `fsouza/fake-gcs-server` functionally bypassing all real-world Google Cloud Storage APIs ensuring hermetic E2E tests for photo uploads.

### 8. Geographical Contextualization
- Implemented `GeoContextService.php` to dynamically calculate and append geographic context to Dashpoint report emails (e.g., "50 miles northwest of Portland, Maine, United States").
- Integrated the Google Maps Reverse Geocoding API to resolve the immediate State/Province and Country of Dashpoints.
- Created `seed_major_cities.py` to ingest the GeoNames `cities15000.txt` dataset into a new local `major_cities` spatial table, facilitating highly efficient `ST_Distance_Sphere` lookups for the nearest major population centers.

### 9. Gmail API Migration
- Replaced the native PHP `mail()` engine with the official Gmail REST API (`google/apiclient`) to guarantee high deliverability, particularly to Gmail users, bypassing spam filters.
- Implemented `symfony/mime` for structured compilation of complex multipart email payloads, strictly enforcing automatic plain-text fallbacks alongside HTML payloads.
- Migrated all outbound system emails (Verifications, Password Resets, Dashpoint Reports) to originate uniformly from `tracker@geodashing.org` via Google Workspace Domain-Wide Delegation.

### 10. Dashpoint Preview & Game Lifecycle Management
- Implemented the capability to generate non-active "Preview" games using the `--preview` flag in `generate_game.py`, allowing the community to view upcoming dashpoints without prematurely exposing them to log submissions.
- Built a localized Python administrative utility (`game_utils.py`) to systematically view chronological game sequences and seamlessly execute monthly rollovers via transactional SQL commands.
- Configured the frontend UI to parse dynamic game states securely, identifying `[PREVIEW]` and `[COMPLETED]` chronological states using native JavaScript Date comparisons, ensuring robust client-side display logic independent of backend integer IDs.

### 11. AI Game Summaries & Reporting
- Migrated to the modern `google-genai` Python SDK to automatically synthesize monthly game summaries.
- The summary engine processes historical logs and selectively curates the best user-submitted photos (rendering them via optimized precomputed thumbnails) to build comprehensive HTML recaps.
- Implemented data serialization to save inputs and outputs from the GenAI workflows to facilitate future model fine-tuning and few-shot example generation.

### 12. UI, SEO & Performance Optimizations
- Integrated automated Lighthouse testing to rigorously enforce strict accessibility, performance, and SEO standards.
- Addressed indexability of deep-linked SPA routes (like `#dashpoint` and `#help`) by dynamically injecting self-referencing canonical links into the document header.
- Modernized mobile upload capabilities by integrating a native device library selector and restricting uploads to a hard 10-photo limit. Added a custom Material Design "My Location" control for rapid GPS syncing.
- Enhanced map UX by automatically refreshing marker layers upon successful log submission, removing the need for manual panning.
- Optimized DOM performance by minimizing repaints during historical game list generation.

### 13. Export Contextualization & Data Portability
- Constrained the data export engine to strictly respect the historical game context active in the frontend. 
- Updated dynamic export filenames and search queries to lock tightly to the parsed game ID.
- Bolstered with extensive E2E validation to ensure exported datasets consistently reflect the user's expected context.

### 14. Advanced Security & Session Integrity
- Enhanced PHP session management to gracefully bypass Ubuntu's default aggressive GC mechanisms, instead relying on strict 30-day sliding activity windows for cookie expiration.
- Addressed multiple Unicode encoding edge-cases in the native MySQL connector to safely process varied international characters in dashpoint logs.