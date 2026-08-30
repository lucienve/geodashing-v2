# Geodashing V2 - Game Administration & Lifecycle Operations Guide

This document provides a comprehensive operational guide for the Geodashing V2 platform game administrator. It details the administrative command-line utilities, their configuration, internal mechanics, and a step-by-step procedure for executing monthly game rollovers on the production machine.

---

## 1. System Requirements & Environment Setup

All administrative utilities are located in the `backend/scripts/` directory and must be executed in an environment matching the core production specifications.

### Technical Target Versions
*   **Python**: `3.14` (Pinned via `.python-version`)
*   **PHP**: `8.3.6`
*   **MySQL**: `8.4.8`

### Installation & Virtual Environment Setup

`uv` (Astral) is used to manage Python runtimes and isolate dependencies:

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Navigate to the project root
# (Example working directory: /home/lucien/src/geodashing-v2)

# Synchronize all dependencies and create/update the virtual environment
uv sync
```

### Required Configuration (`backend/config.ini`)

All scripts securely connect to the database and external API services using parameters parsed from `backend/config.ini`. An administrative layout requires the following sections configured:

```ini
[database]
DB_HOST = "127.0.0.1"
DB_PORT = "3306"
DB_NAME = "geodashing"
DB_USER = "geodashing"
DB_PASS = "secure_password"

[mail]
GOOGLE_APPLICATION_CREDENTIALS = "backend/gcp-credentials.json"
MAILING_LIST_ADDRESS = "tracker@geodashing.org"

[google]
GOOGLE_MAPS_API_KEY = "AIzaSy..."

[gemini]
GEMINI_API_KEY = "AIzaSy..."
GEMINI_MODEL = "gemini-3.7-flash"
GEMINI_THINKING_LEVEL = "medium"
GEMINI_PROJECT_ID = "your-gcp-project-id"
```

---

## 2. Deep Dive: Administrative Command Line Utilities

The system relies on six primary backend utilities to manage the lifecycle of games, validate generated resources, and distribute notifications.

### A. `generate_game.py` (Game Generator Engine)
Generates globally distributed, geographically balanced geodashing points situated on land (or up to 100 meters offshore) and initializes new games in the database.

*   **Location**: `backend/scripts/generate_game.py`
*   **Execution Command**:
    ```bash
    uv run python -m backend.scripts.generate_game -t "Game Title" [options]
    ```

#### Command Line Arguments
| Flag | Long Form | Type | Description |
| :--- | :--- | :---: | :--- |
| `-t` | `--title` | `str` | **Required.** Brief descriptive title of the game (maximum 40 characters). |
| `-c` | `--count` | `int` | Total number of dashpoints to randomly distribute globally. Defaults to `31000`. |
| `-m` | `--month` | `int` | Optional month (1–12) for the game schedule. Defaults to the current month. |
| `-y` | `--year` | `int` | Optional year for the game schedule. Defaults to the current year. |
| | `--preview` | `flag` | Generates the game in an inactive "preview" state (`is_active = FALSE`) instead of immediately activating it. |

#### Internal Mechanics
1.  **Spherical Coordinate Generation**: Generates raw global points utilizing a uniform spherical distribution (equal density per unit area).
2.  **Landmass Filtering (EPSG:6933)**: 
    *   Loads complex shapefiles for global landmasses (`data/ne_10m_land.zip`) and major lakes (`data/ne_10m_lakes.zip`).
    *   Projects both datasets to a Cylindrical Equal-Area coordinate system (`EPSG:6933`) and subdivides them using a grid-based approach (`subdivide_geometry` with a max size of 1,000,000m) to minimize vertex complexity per feature.
    *   Performs a fast **Point-in-Polygon (PIP)** vectorized check using prepared geometries to immediately accept dry land coordinates (about 30% of points), avoiding buffering for 99% of valid points.
    *   For boundary/ocean candidates, queries the `STRtree` spatial index bounding boxes and performs localized intersection tests (using 100m buffers) to identify valid near-shore points.
3.  **Profanity Filtering & ID Generation**:
    *   Generates systematic alphanumeric sequence IDs prefixed by the game context (e.g., `GD001-ABCD`).
    *   Cross-references each sequence against a local 4-letter profanity list (`data/bad_words.txt`) and dynamically skips forbidden sequences.
4.  **Database Seeding**: Inserts records in structured batches of `5000` using WKT syntax `POINT(lat lon)` to guarantee spatial indexing alignment with MySQL 8.4.8 SRID 4326.

---

### B. `game_utils.py` (Lifecycle & Summary Validator)
Maintains game activation status and provides strict schema validation for admin-submitted HTML summaries.

*   **Location**: `backend/scripts/game_utils.py`
*   **Execution Command**:
    ```bash
    uv run python -m backend.scripts.game_utils [commands]
    ```

#### Command Line Arguments
| Flag | Type | Argument | Description |
| :--- | :---: | :---: | :--- |
| `--list` | `flag` | — | Lists all database games chronologically, showing ID, active status, start/end times, and titles. |
| `--activate` | `int` | `GAME_ID` | Deactivates all currently active games and sets the target game's `is_active` to `TRUE`. |
| `--upload-summary` | `str` | `FILE_PATH` | Parses, validates, and uploads a local HTML summary file. Requires `--game_id`. |
| `--email-summary` | `flag` | — | Emails the HTML summary for the specified game_id to the mailing list. Requires `--game_id`. |
| `--game_id` | `int` | `GAME_ID` | Specifies the target game ID when uploading or emailing an HTML summary. |
| `--rollover` | `flag` | — | Executes complete automated end-of-month turnover: promotes preview to active, seeds next preview game, and emails announcement to players. |
| `--dry-run` | `flag` | — | Simulates the turnover execution without making database changes or sending emails. |
| `--year` | `int` | `YYYY` | Optional override for the target activation year (used with `--rollover`). |
| `--month` | `int` | `1-12` | Optional override for the target activation month (used with `--rollover`). |
| `--count` | `int` | `N` | Optional dashpoint count override for preview generation (defaults to `DEFAULT_DASHPOINT_COUNT` in `config.ini`). |

#### Automated Monthly Rollover (`--rollover`)
The `--rollover` command automates the end-of-month game transition at `00:00:00 America/New_York` on the 1st of each month:
1. **Current Month Activation**: Inspects games for the current month. If exactly one preview game exists, it promotes it to active (`is_active = TRUE`) and deactivates all others. If no preview game exists or multiple conflicting games exist, it fails fast with a non-zero exit code to alert administrators.
2. **Next Month Preview Generation**: Checks if a preview game exists for the upcoming month. If not, it looks up the pre-planned title from `data/game_titles.json` (or uses a fallback pattern), generates ~35,000 dashpoints, and inserts the new preview game (`is_active = FALSE`).
3. **Turnover Announcement Email**: Constructs and dispatches a multipart HTML/plain-text announcement email to the player mailing list (`MAILING_LIST_ADDRESS`) via the Gmail REST API.

#### HTML Fragment Safety & Validation rules
To prevent cross-site scripting (Stored XSS) and layout breakages in user browsers and sitemaps, the parser enforces these rules:
*   **Whitelist Compliance**: Strictly limits acceptable structural tags to: `h2`, `h3`, `h4`, `h5`, `h6`, `p`, `div`, `span`, `br`, `hr`, `strong`, `b`, `em`, `i`, `u`, `code`, `pre`, `blockquote`, `ul`, `ol`, `li`, `a`, `img`.
*   **Layout & Script Bans**: Rejects all page structural elements (`html`, `head`, `body`), styles (`style`), and interactive scripts (`script`, `iframe`, `svg`).
*   **Tag Balancing**: Employs standard stack tracking via `html.parser.HTMLParser` to ensure all elements are properly nested and closed.
*   **Hyperlink Security**: Mandates that `<a>` tags include `href` attributes starting exclusively with `http://`, `https://`, `/`, or `#`.
*   **Image Integrity**: Restricts `<img>` tags to possess valid, non-empty `src` attributes.

---

### C. `generate_summary.py` (AI Game Summary Generator)
Harnesses the Gemini Developer API via the Google GenAI SDK to synthesize a structured, HTML-formatted summary of player achievements, outstanding logs, and game statistics.

*   **Location**: `backend/scripts/generate_summary.py`
*   **Execution Command**:
    ```bash
    uv run python -m backend.scripts.generate_summary --game_id GAME_ID --output_dir DIR_PATH
    ```

#### Command Line Arguments
| Parameter | Type | Description |
| :--- | :---: | :--- |
| `--game_id` | `int` | **Required.** The database ID of the completed game to summarize. |
| `--output_dir` | `str` | **Required.** The absolute or relative path to a directory where the input dump and synthesized output will be written. |

#### Workflow & AI Integration
1.  **Data Extraction**: Queries the database to extract the final game score rankings and all approved player logs (`status = 'approved'`) containing notes and user-uploaded photos.
2.  **Spatial Context Enrichment**: Performs highly efficient `ST_Distance_Sphere` lookups against the local `major_cities` spatial table to resolve the nearest major city, state, and country for each geodashing visit.
3.  **Media Processing & AI Uploads**:
    *   Identifies user-uploaded photos from log metadata.
    *   Downloads full-resolution images into local secure temporary files.
    *   Uploads raw bytes to the Google AI Studio remote files API (`client.files.upload`) so Gemini can visually evaluate the photographs inline.
4.  **Prompt Synthesis & Generation**:
    *   Loads system-level instructions (`data/summary_system_instructions.txt`) detailing the expected HTML output structure (subheadings restricted to `<h2>`/`<h3>` for accessibility, absolute hyperlinks, and thumbnail-to-image layouts).
    *   Injects few-shot historical templates from `data/summary_examples/` as chat history.
    *   Dispatches the structured dataset and uploaded image components to `gemini-3.7-flash` with configurable thinking level reasoning (`GEMINI_THINKING_LEVEL`).
5.  **Output Export**: Saves a plain-text prompt dump to `game_<id>_input.txt` and the final sanitized HTML fragment to `game_<id>_output.html`.
6.  **Hermetic Resource Clean-up**: Automatically purges all local temporary downloaded files and issues API requests to permanently delete uploaded files from remote Gemini servers before exiting.

---

### D. `seed_major_cities.py` (Spatial Table Populator)
Populates the system's spatial `major_cities` database table to enable near-instantaneous spatial distance calculations for reporting.

*   **Location**: `backend/scripts/seed_major_cities.py`
*   **Execution Command**:
    ```bash
    uv run python -m backend.scripts.seed_major_cities
    ```

#### Core Details
*   Ingests the GeoNames standard datasets located in the `data/` directory:
    *   `cities15000.txt`: Geonames coordinate data for populated places with populations exceeding 15,000.
    *   `admin1CodesASCII.txt`: Administrative divisions mapping region codes to ASCII names.
    *   `countryInfo.txt`: Country mapping codes.
*   Wipes the existing table using a transactional `TRUNCATE TABLE major_cities` command.
*   Processes data in batches of `5000` and inserts records with geometries aligned to WGS84 coordinates (Latitude, Longitude ordering) for high-performance `ST_Distance_Sphere` spatial querying.

---

### E. `reroll_dashpoint.py` (Dashpoint Rerolling Utility)
Relocates a single preview game dashpoint on dry land within a specified maximum radius.

*   **Location**: `backend/scripts/reroll_dashpoint.py`
*   **Execution Command**:
    ```bash
    uv run python -m backend.scripts.reroll_dashpoint --lat LAT --lon LON [options]
    ```

#### Command Line Arguments
| Flag | Long Form | Type | Description |
| :--- | :--- | :---: | :--- |
| | `--lat` | `float` | **Required.** The latitude coordinate of the original location. |
| | `--lon` | `float` | **Required.** The longitude coordinate of the original location. |
| | `--max-radius-km` | `float` | The maximum distance (in kilometers) to relocate the point. Defaults to `10.0`. |
| | `--land-zip` | `str` | Path to the Natural Earth land zip shapefile. Defaults to `data/ne_10m_land.zip`. |
| | `--lakes-zip` | `str` | Path to the Natural Earth lakes zip shapefile. Defaults to `data/ne_10m_lakes.zip`. |
| | `--verbose` | `flag` | Enables verbose console logs and progress status messages during execution. Defaults to `False` (silent). |

---

### F. `catchup_emails.php` (Manual Email Notification Dispatcher)
A PHP helper tool to manually dispatch structured HTML report emails to the game mailing list for claims logged before the automated reporting framework was initialized.

*   **Location**: `backend/scripts/catchup_emails.php`
*   **Execution Command**:
    ```bash
    php backend/scripts/catchup_emails.php
    ```

#### Usage Details
Before executing the script, manually edit the SQL filter statement (line 26) inside `backend/scripts/catchup_emails.php` to isolate the target subset of visits:
```php
// Example: Filter to isolate specific visit IDs logged during migration
$stmt = $db->query("
    SELECT v.*, u.username, d.game_id 
    FROM visits v 
    JOIN users u ON v.user_id = u.id
    JOIN dashpoints d ON v.dashpoint_id = d.id
    WHERE v.id IN (101, 102, 103)
");
```

---

## 3. End-of-Month Game Rollover & Lifecycle Operations

For detailed, step-by-step instructions on executing monthly game rollovers, generating AI summaries, and shifting active game sequences on the production server, please refer to the standalone [Game Rollover & Summary Generation Guide](game_rollover.md).

---

## 4. Production Monitoring & Error Reporting (Google Cloud)

To automatically track application exceptions, database failures, and runtime errors, the production instance uses **Google Cloud Error Reporting** integrated with the **Google Cloud Ops Agent**. This setup provides centralized logging and real-time error grouping without modifying application source code.

### Step 1: Assign IAM Roles to GCE Service Account

The production GCE instance (`vm2019-vpc`) runs under the following Google Compute Engine service account:
*   **Service Account Email**: `174669942892-compute@developer.gserviceaccount.com`

For the Ops Agent to successfully upload metrics, write logs, and report error stack traces, this service account must be granted the following IAM roles in the Google Cloud Console:

1.  **Logs Writer** (`roles/logging.logWriter`): Permits the agent to stream files to Google Cloud Logging.
2.  **Error Reporting Writer** (`roles/clouderrorreporting.writer`): Permits the agent to write exception events to Error Reporting.
3.  **Monitoring Metric Writer** (`roles/monitoring.metricWriter`): (Recommended) Permits writing VM-level performance metrics (CPU, Memory, Disk) to Cloud Monitoring.

#### How to Assign Roles:
1.  Navigate to **IAM & Admin > IAM** in the Google Cloud Console.
2.  Locate `174669942892-compute@developer.gserviceaccount.com` in the list of principals.
3.  Click the edit pencil icon on its row.
4.  Click **Add Another Role** and assign the three roles listed above.
5.  Click **Save**.

### Step 2: Install the Ops Agent on the VM
Log in to the GCE instance via SSH and run the official GCP installation script to install the Ops Agent:
```bash
# Download and run the Ops Agent installation script
curl -sSO https://dl.google.com/cloudagents/add-google-cloud-ops-agent-repo.sh
sudo bash add-google-cloud-ops-agent-repo.sh --also-install

# Verify that the service is running
sudo systemctl status google-cloud-ops-agent
```

### Step 3: Configure the Ops Agent Logging Pipeline
The Ops Agent monitors the Geodashing Apache logs as well as the monthly turnover cron logs.

1.  Open the configuration file using a text editor (e.g. `nano`):
    ```bash
    sudo nano /etc/google-cloud-ops-agent/config.yaml
    ```
2.  Configure the receivers and pipeline:
    ```yaml
    logging:
      receivers:
        geodashing_error:
          type: apache_error
          include_paths:
            - /var/log/apache2/geodashing_error.log
        geodashing_access:
          type: apache_access
          include_paths:
            - /var/log/apache2/geodashing_access.log
        geodashing_turnover:
          type: files
          include_paths:
            - /var/log/geodashing/turnover.log
      service:
        pipelines:
          geodashing_pipeline:
            receivers:
              - geodashing_error
              - geodashing_access
              - geodashing_turnover
    ```
    *(Note: The built-in `apache_error` and `apache_access` receiver types automatically parse timestamps, severities, and messages. The `geodashing_turnover` file receiver monitors cron job execution logs).*
3.  Ensure the log directory exists with appropriate permissions:
    ```bash
    sudo mkdir -p /var/log/geodashing
    sudo chown -R lucien:www-data /var/log/geodashing
    sudo chmod 775 /var/log/geodashing
    ```
4.  Save the file and restart the agent to apply changes:
    ```bash
    sudo systemctl restart google-cloud-ops-agent
    ```

### Step 4: Setting Up the Monthly Turnover Cron Job
On the production VM (`vm2019-vpc`), the turnover cron job is configured via `/etc/cron.d/geodashing-turnover` to trigger the automated rollover at midnight America/New_York on the 1st of every month using `uv run`.

1.  Edit or create the system cron file `/etc/cron.d/geodashing-turnover`:
    ```bash
    sudo nano /etc/cron.d/geodashing-turnover
    ```
2.  Add or update the scheduled turnover entry:
    ```cron
    # Geodashing Monthly Turnover: Runs at 00:00:00 America/New_York on the 1st of every month
    CRON_TZ=America/New_York
    PATH=/home/lucienve/.cargo/bin:/usr/local/bin:/usr/bin:/bin
    0 0 1 * * lucienve cd /home/lucienve/src/geodashing-v2 && uv run python -m backend.scripts.game_utils --rollover >> /var/log/geodashing/turnover.log 2>&1
    ```
3.  Ensure the file has standard permissions:
    ```bash
    sudo chmod 644 /etc/cron.d/geodashing-turnover
    ```

### Step 5: Setting Up Google Cloud Alerting for Turnover Failures
Whenever the monthly turnover fails (e.g. missing preview game, database disconnection, or email dispatch failure), the script outputs an error trace to `stderr` and exits with a non-zero exit code (`1`).

To configure an automated Google Cloud email alert:
1.  Navigate to **Google Cloud Console > Monitoring > Alerting**.
2.  Click **Create Policy**.
3.  Click **Select a metric** and switch to query mode, or choose **Logs-based Metric** with the filter:
    ```text
    resource.type="gce_instance"
    log_name=~"projects/.*/logs/geodashing_turnover"
    textPayload=~"(ERROR|Traceback|Turnover Aborted|RuntimeError)"
    ```
4.  Set the trigger condition to `Condition is met if any time series violates threshold (Count > 0 in 5 minutes)`.
5.  Under **Notification Channels**, select or create an email channel (e.g. administrator email `lucienve@gmail.com`).
6.  Set the policy name to `Geodashing Monthly Turnover Failure Alert` and save.
7.  *(Optional)* In **Error Reporting**, ensure notification emails are enabled for new exception groups detected from the Ops Agent log streams.

