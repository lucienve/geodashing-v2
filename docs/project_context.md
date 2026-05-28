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
- Upgraded the summary generation engine from GCP Vertex AI to the Google AI Studio (Gemini Developer API) platform to simplify developer setups and facilitate seamless local testing.
- Upgraded the default AI summary model to the next-generation series (**`gemini-3.5-flash`** or **`gemini-3.1-pro-preview`**), fully parameterized alongside `GEMINI_API_KEY` under the new `[gemini]` section of `config.ini` (with a complete template supplied in `config.ini.example`).
- Streamlined image input processing by bypassing Vertex-specific GCS `gs://` URIs and instead downloading photos via standard HTTPS URLs to feed raw image bytes inline via `types.Part.from_bytes()`, ensuring absolute environment portability.
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

### 15. KML Data Portability & GIS Compatibility
- Integrated standard KML (Keyhole Markup Language) 2.2 export support inside `ExportService.php` to enable visual mapping layers on modern applications like Google Earth, Google My Maps, QGIS, and physical GPS handheld devices.
- Crafted clean standard KML `<Placemark>` nodes mapping geographic coordinates using standard `longitude,latitude,altitude` ordering clamped directly to the terrain surface.
- Formatted placemark descriptions using standard HTML within `<![CDATA[ ... ]]>` blocks to ensure out-of-the-box clickability in Google Earth Pro, Google My Maps, and Google Earth Web's Local KML data layers, accounting for a known Google Earth Web Projects platform limitation where imported HTML is loaded as plain text in their rich text editor until toggled manually.
- Decoupled KML download endpoints inside the single page application controller, supporting dynamic game active contexts.

### 16. UI Navigation & Dynamic Player Profile Redesign
- Evaluated and streamlined the frontend single page application menu structure, removing the redundant `MAP` link in favor of making the `GEODASHING.v2` brand logo a direct navigation anchor targeting `#home`.
- Replaced the cluttered, flat desktop buttons (`PROFILE` and `LOGOUT [username]`) with a dynamic, glassmorphic dropdown trigger (`👤 [username] ▾`) that reveals integrated "View Profile" and "Logout" actions in a clean overlay.
- Grouped player management actions cleanly within a distinct, stylized panel inside the mobile navigation drawer to preserve responsive layouts across all mobile screen sizes.
- Decoupled all styles into `public/css/index.css` to prevent inline style usage, keeping frontend JS logic focused purely on DOM structure.
- Verified that all 81 Playwright E2E tests, 52 PHPUnit tests, and 14 Python pytest suites pass successfully under verified, local OS dependencies.

### 17. Game Summaries & Administrative CLI Validator
- Extended the core MySQL database schema (`schema.sql` and E2E databases) with a `summary` column of type `MEDIUMTEXT` inside the `games` table.
- Added comprehensive HTML fragment validation inside `game_utils.py` using Python's built-in `html.parser.HTMLParser`. The CLI tool strictly whitelists structural/semantic tags (`<h2>`–`<h6>`, `<p>`, `<strong>`, `<a>`, `<img>`, etc.), validates balanced tags via stack tracking, and actively blocks layout wrappers (`<html>`, `<body>`) and script elements (`<script>`) to prevent Stored XSS or style bleeding.
- Integrated a new namespaced PHP service class `SummaryService.php` and public JSON controller (`public/api/summary.php`) to retrieve game summaries securely on-demand.
- Registered dynamic summary URLs (`/?summary=ID`) inside `SitemapService.php` to guarantee dynamic search engine crawlability and sitemap parity.
- Implemented deep-link routing fallbacks in `public/js/app.js` to client-side convert query parameters to hash routes and automatically highlight context games.
- Built a glassmorphic floating modal popup overlay and responsive trigger button inside the `#leaderboard` view of `public/js/controllers.js` and `public/templates/leaderboard.html` cleanly styled within `public/css/index.css`.
- Developed extensive unit test coverage in `backend/tests/test_game_utils.py` and `backend/tests/SummaryServiceTest.php` achieving 100% test success and a perfect 10.00/10 pylint quality rating.
- Aligned `data/summary_system_instructions.txt` system instructions to generate clean HTML fragments matching the whitelist expected by `game_utils.py` and conform to single-page SEO accessibility standards (nesting subheadings starting at `<h2>`/`<h3>` tags). Mandated absolute URLs (using 'https://www.geodashing.org/' prefix) for all player profile and dashpoint hyperlinks to ensure email view compatibility.

### 18. Site-Wide Accessibility & Visual Contrast Verification
- Established an automated, site-wide E2E accessibility and visual contrast verification framework using Playwright to protect against visual regressions and contrast deficiencies.
- Modified the MySQL E2E test database seeding (`e2e/setup-test-db.sh`) to populate Game 1 (Historical) with a rich HTML summary containing hyperlinks to test the "📖 READ GAME SUMMARY" modal overlay.
- Added global high-contrast styling in `public/css/index.css` for standard anchors (`a`) and visited anchors (`a:visited`) using `var(--accent-amber)` to protect against browser-default low-contrast purples/blues on dark glassmorphic overlays.
- Created `e2e/accessibility.spec.js` providing extensive E2E accessibility checking across all 9 SPA views and overlays (under both authenticated and unauthenticated states). The suite programmatically validates heading hierarchies, descriptive text or `aria-label`/`aria-labelledby` on all buttons, alternative text (`alt` attribute) on all images, and explicit/implicit/sibling/ancestor label associations on all input elements. It also queries the browser's CSSOM stylesheets to guarantee both `.summary-rich-content a:visited` and global `a:visited` CSS rules resolve to the amber contrast accent.
- Verified that all 27 new Playwright E2E accessibility tests, all existing 55 PHPUnit backend tests, all 24 Python unit tests, and the ESLint / Pylint suites pass flawlessly with 0 issues and a perfect 10.00/10 code quality rating!

### 19. Mobile UI Overlay Close Behavior & Backdrop Dimming
- Implemented tap-outside closing behavior for mobile overlays (mobile navigation drawer and route-based `.template-view` bottom sheets), bringing Geodashing V2 into compliance with modern mobile UX standards.
- Designed full-screen fixed glassmorphic dimming scrim backdrops (`#mobile-nav-backdrop` and `.overlay-active` inside `#app-content`) featuring a subtle `backdrop-filter: blur(4px)` and smooth transition effects to isolate the focused overlay while visually obscuring the Google Map underneath.
- Strictly scoped the responsive dimming and tap-outside close triggers to mobile screen sizes (`max-width: 768px`) using precise CSS media queries and client-side viewport check logic, preserving the interactive desktop sidebar/map viewport split layout.
- Added comprehensive E2E interaction coverage inside `e2e/interaction.spec.js` programmatically validating mobile close actions using offset click triggers to avoid narrow layout element overlap.

### 20. Comprehensive Administrative Documentation
- Created the game administrator's CLI utilities guide in `docs/admin_guide.md` and the standalone `docs/game_rollover.md` operations guide.
- Documented system setup, prerequisites, configurations (`backend/config.ini`), and details of key administrative scripts (`generate_game.py`, `game_utils.py`, `generate_summary.py`, `seed_major_cities.py`, `catchup_emails.php`) in the administrative utilities guide.
- Formulated the exact chronological step-by-step rollover procedure (compiling the completed month's AI summary, promoting the current month's preview game to active, and seeding the next month's preview game) as a separate operational playbook (`docs/game_rollover.md`) for safe production environments.

### 21. End-of-Month Summary Emailing
- Added `--email-summary` functionality to the `game_utils.py` administrative utility script to dispatch the completed month's HTML summary directly to the player mailing list.
- Implemented secure Google Service Account authentication with Domain-Wide Delegation impersonation of `tracker@geodashing.org` via the official Gmail REST API, matching the security mechanism of the backend PHP visitation emails.
- Extracted and formatted both a rich HTML message and a clean, tag-stripped plain-text fallback, setting the custom subject line to `Geodashing Game <game_id> (<Month> <Year>) Results` using the game's chronological database metadata.
- Implemented an `APP_ENV=testing` environment variable bypass to suppress physical API transmission during automated test executions.
- Modularized the Python implementation to prevent linter variable complexity, achieving a perfect 10.00/10 Pylint rating on both scripts (`game_utils.py`) and test suites (`test_game_utils.py`).
- Integrated the new email execution step into the system operations documentation (`docs/admin_guide.md` and `docs/game_rollover.md`) and updated the Rollover Process Map diagram.