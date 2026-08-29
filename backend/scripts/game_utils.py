"""Administrative utilities for managing Geodashing game lifecycles."""

import argparse
import base64
import calendar
import configparser
import datetime
import email.mime.multipart
import email.mime.text
import html.parser
import json
import os
import re
import sys
import typing
import urllib.request
import zoneinfo

import google.auth.transport.requests
import google.oauth2.service_account
import mysql.connector.connection
import mysql.connector.cursor

import backend.scripts.db_utils
import backend.scripts.generate_game

class HTMLFragmentValidator(html.parser.HTMLParser):
    """Validates HTML summary fragments ensuring safety, proper structure, and styling limits."""
    FORBIDDEN_TAGS = {
        'html', 'head', 'body', 'title', 'meta', 'link', 'style',
        'script', 'iframe', 'object', 'embed', 'applet', 'svg',
        'audio', 'video'
    }

    ALLOWED_TAGS = {
        'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'div', 'span', 'br', 'hr',
        'strong', 'b', 'em', 'i', 'u', 'code', 'pre', 'blockquote',
        'ul', 'ol', 'li', 'a', 'img'
    }

    VOID_TAGS = {'br', 'hr', 'img'}

    def __init__(self):
        super().__init__()
        self.stack = []
        self.errors = []
        self.has_content = False

    def _validate_anchor_attributes(self, attrs: list[tuple[str, str | None]]) -> None:
        """Validates that anchor tags possess non-empty, safe URL href targets."""
        has_href = False
        for attr, val in attrs:
            if attr.lower() == 'href':
                has_href = True
                is_valid = (val is not None and (
                            val.startswith('http://') or
                            val.startswith('https://') or
                            val.startswith('#') or
                            val.startswith('/')))
                if not val or not is_valid:
                    self.errors.append(f"Invalid or empty href in <a> tag: '{val}'")
        if not has_href:
            self.errors.append("Anchor <a> tag is missing href attribute")

    def _validate_image_attributes(self, attrs: list[tuple[str, str | None]]) -> None:
        """Validates that image tags possess non-empty src attributes."""
        has_src = False
        for attr, val in attrs:
            if attr.lower() == 'src':
                has_src = True
                if not val:
                    self.errors.append("Image <img> tag has an empty src attribute")
                else:
                    self.has_content = True
        if not has_src:
            self.errors.append("Image <img> tag is missing src attribute")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        if tag_lower not in self.VOID_TAGS:
            self.stack.append(tag_lower)

        if tag_lower in self.FORBIDDEN_TAGS:
            self.errors.append(f"Forbidden tag detected: <{tag}>")
        elif tag_lower not in self.ALLOWED_TAGS:
            self.errors.append(f"Disallowed tag detected: <{tag}>")

        if tag_lower == 'a':
            self._validate_anchor_attributes(attrs)
        elif tag_lower == 'img':
            self._validate_image_attributes(attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in self.VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower in self.VOID_TAGS:
            if self.stack and self.stack[-1] == tag_lower:
                self.stack.pop()
            return

        if not self.stack:
            self.errors.append(f"Unexpected closing tag: </{tag}> (no opening tag)")
            return

        expected = self.stack.pop()
        if expected != tag_lower:
            self.errors.append(f"Mismatched closing tag: </{tag}>. Expected </{expected}>")

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.has_content = True

    def validate(self, html_content: str) -> list[str]:
        """Parses the HTML and returns list of validation errors. Empty if valid."""
        self.errors = []
        self.stack = []
        self.has_content = False
        try:
            self.feed(html_content)
            self.close()
        # HTMLParser.feed() can raise unexpected parsing exceptions or AssertionErrors
        # depending on internal implementation and malformed structure, so catching
        # all exceptions is architecturally unavoidable here to guarantee the CLI never crashes.
        except Exception as e: # pylint: disable=broad-exception-caught
            self.errors.append(f"HTML parsing exception: {str(e)}")

        if self.stack:
            unclosed = ", ".join(f"<{t}>" for t in reversed(self.stack))
            self.errors.append(f"Unclosed tags detected: {unclosed}")

        if not self.errors and not self.has_content:
            self.errors.append("HTML summary contains no text content")

        return self.errors


def list_games(cursor: mysql.connector.cursor.MySQLCursor) -> None:
    """Prints all games chronologically."""
    cursor.execute("SELECT id, title, start_time, end_time, is_active "
                   "FROM games ORDER BY start_time ASC")
    games = typing.cast(
        list[tuple[int, str, datetime.datetime | None, datetime.datetime | None, bool]],
        cursor.fetchall()
    )

    if not games:
        print("No games found in the database.")
        return
    print(f"{'ID':<5} | {'Active':<8} | {'Start Time':<20} | {'End Time':<20} | {'Title'}")
    print("-" * 80)
    for g in games:
        g_id, title, start_time, end_time, is_active = g
        active_str = "YES" if is_active else "NO"
        start_str = start_time.strftime("%Y-%m-%d %H:%M:%S") if start_time else "N/A"
        end_str = end_time.strftime("%Y-%m-%d %H:%M:%S") if end_time else "N/A"
        print(f"{g_id:<5} | {active_str:<8} | {start_str:<20} | {end_str:<20} | {title}")

def activate_game(
    cursor: mysql.connector.cursor.MySQLCursor,
    conn: mysql.connector.connection.MySQLConnection,
    game_id: int
) -> None:
    """Sets the specified game to active and retires all others."""
    # Validate game exists
    cursor.execute("SELECT id, title FROM games WHERE id = %s", (game_id,))
    game = typing.cast(tuple[int, str] | None, cursor.fetchone())
    if not game:
        print(f"Error: Game ID {game_id} does not exist.")
        return

    print("Retiring all currently active games...")
    cursor.execute("UPDATE games SET is_active = FALSE")

    print(f"Activating Game {game_id} ('{game[1]}')...")
    cursor.execute("UPDATE games SET is_active = TRUE WHERE id = %s", (game_id,))

    conn.commit()
    print("Game rollover completed successfully!")

def upload_summary(
    cursor: mysql.connector.cursor.MySQLCursor,
    conn: mysql.connector.connection.MySQLConnection,
    game_id: int,
    file_path: str
) -> None:
    """Validates and uploads an HTML summary fragment to the specified game."""
    # Check if game exists
    cursor.execute("SELECT id, title FROM games WHERE id = %s", (game_id,))
    game = typing.cast(tuple[int, str] | None, cursor.fetchone())
    if not game:
        print(f"Error: Game ID {game_id} does not exist.")
        sys.exit(1)

    # Check if file exists
    if not os.path.exists(file_path):
        print(f"Error: Summary file not found at '{file_path}'.")
        sys.exit(1)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
    except OSError as e:
        print(f"Error reading file: {e}")
        sys.exit(1)

    # Validate HTML fragment formatting
    validator = HTMLFragmentValidator()
    errors = validator.validate(html_content)

    if errors:
        print("Validation failed. The following format violations were detected:")
        for err in errors:
            print(f"- {err}")
        sys.exit(1)

    print(f"Uploading summary for Game {game_id} ('{game[1]}')...")
    cursor.execute("UPDATE games SET summary = %s WHERE id = %s", (html_content, game_id))
    conn.commit()
    print("Summary uploaded and saved to the database successfully!")

def load_mail_config(config_path: str) -> tuple[str, str]:
    """Reads and validates mail configurations from config.ini."""
    if not os.path.exists(config_path):
        print(f"Error: Config not found at {config_path}")
        sys.exit(1)

    config = configparser.ConfigParser()
    config.read(config_path)

    if 'mail' not in config:
        print("Error: [mail] section is missing in config.ini.")
        sys.exit(1)

    to_email = config['mail'].get('MAILING_LIST_ADDRESS', '').strip('"\'')
    credentials_path = config['mail'].get('GOOGLE_APPLICATION_CREDENTIALS', '').strip('"\'')

    if not to_email:
        print("Error: MAILING_LIST_ADDRESS is not configured in config.ini.")
        sys.exit(1)

    if not credentials_path:
        print("Error: GOOGLE_APPLICATION_CREDENTIALS is not configured in config.ini.")
        sys.exit(1)

    if not os.path.exists(credentials_path):
        print(f"Error: Credentials file not found at '{credentials_path}'.")
        sys.exit(1)

    return to_email, credentials_path


def send_via_gmail_api(credentials_path: str, to_email: str, subject: str, html_body: str) -> None:
    """Authenticates and sends an email via Gmail REST API."""
    sender = 'tracker@geodashing.org'

    creds = google.oauth2.service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=['https://www.googleapis.com/auth/gmail.send']
    )
    delegated_creds = creds.with_subject(sender)

    # Refresh token to get access token
    auth_req = google.auth.transport.requests.Request()
    delegated_creds.refresh(auth_req)
    access_token = delegated_creds.token

    # Generate a plain-text fallback by stripping tags
    plain_text = (html_body.replace('<br>', '\n')
                  .replace('<br/>', '\n')
                  .replace('<br />', '\n')
                  .replace('</p>', '\n'))
    plain_text = re.sub('<[^<]+?>', '', plain_text)

    msg = email.mime.multipart.MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = to_email

    msg.attach(email.mime.text.MIMEText(plain_text, 'plain', 'utf-8'))
    msg.attach(email.mime.text.MIMEText(html_body, 'html', 'utf-8'))

    # Base64url encode the message
    raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')

    # Send via Gmail REST API
    api_req = urllib.request.Request(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        data=json.dumps({"raw": raw_message}).encode('utf-8'),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        method='POST'
    )
    with urllib.request.urlopen(api_req) as response:
        if 'id' in json.loads(response.read().decode('utf-8')):
            print("Email dispatched successfully!")
        else:
            print("Error: Response did not contain email ID.")
            sys.exit(1)


def email_summary(
    cursor: mysql.connector.cursor.MySQLCursor,
    game_id: int,
    config_path: str
) -> None:
    """Sends the end-of-month game summary to the mailing list specified in config.ini."""
    # 1. Fetch game summary, title, and start_time from database
    cursor.execute("SELECT title, summary, start_time FROM games WHERE id = %s", (game_id,))
    row = typing.cast(
        tuple[str, str | None, datetime.datetime | None] | None,
        cursor.fetchone()
    )
    if not row:
        print(f"Error: Game ID {game_id} does not exist.")
        sys.exit(1)

    title, summary, start_time = row
    if not summary:
        print(
            f"Error: Game ID {game_id} ('{title}') "
            "does not have a summary uploaded yet. "
            "Run summary generation and upload first."
        )
        sys.exit(1)

    to_email, credentials_path = load_mail_config(config_path)

    # Bypass physical API interaction during E2E/unit testing
    app_env = os.getenv('APP_ENV') or ''
    if app_env == 'testing':
        print(f"APP_ENV=testing: Suppressed physical email transmission to {to_email}")
        return

    print(f"Preparing to email summary for Game {game_id} ('{title}') to {to_email}...")

    # Authenticate and send email cleanly
    try:
        month_year = (
            start_time.strftime("%B %Y") if start_time else "Unknown Month"
        )
        subject = f"Geodashing Game {game_id} ({month_year}) Results"
        send_via_gmail_api(credentials_path, to_email, subject, summary)
    except Exception as e:  # pylint: disable=broad-exception-caught
        # Catching all base exceptions is architecturally unavoidable here to ensure
        # the CLI does not crash with raw Python/Google SDK tracebacks in production
        # and instead reports a clean, professional error message to the admin.
        print(f"Failed to email summary: {e}", file=sys.stderr)
        sys.exit(1)


def load_game_config(config_path: str) -> dict[str, typing.Any]:
    """Reads game configuration parameters from config.ini."""
    default_config: dict[str, typing.Any] = {
        'default_dashpoint_count': 35000,
        'timezone': 'America/New_York',
        'send_turnover_announcement': True
    }
    if not os.path.exists(config_path):
        return default_config

    config = configparser.ConfigParser()
    config.read(config_path)

    if 'game' in config:
        game_sec = config['game']
        default_config['default_dashpoint_count'] = game_sec.getint(
            'DEFAULT_DASHPOINT_COUNT', fallback=35000
        )
        default_config['timezone'] = game_sec.get(
            'TIMEZONE', fallback='America/New_York'
        ).strip('"\'')
        default_config['send_turnover_announcement'] = game_sec.getboolean(
            'SEND_TURNOVER_ANNOUNCEMENT', fallback=True
        )

    return default_config


def get_game_title(year: int, month: int, titles_path: str) -> str:
    """Resolves the game title from a JSON titles file, or constructs a standard fallback title."""
    month_key = f"{year:04d}-{month:02d}"
    if os.path.exists(titles_path):
        try:
            with open(titles_path, 'r', encoding='utf-8') as f:
                titles_dict = json.load(f)
                if isinstance(titles_dict, dict) and month_key in titles_dict:
                    custom_title = str(titles_dict[month_key]).strip()
                    if custom_title:
                        return custom_title
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: Failed to parse titles file at '{titles_path}': {e}. Using fallback.")

    month_name = calendar.month_name[month]
    return f"{month_name} {year} Dashing Classic"


def get_games_for_month(
    cursor: mysql.connector.cursor.MySQLCursor,
    year: int,
    month: int
) -> list[tuple[int, str, bool, datetime.datetime | None, datetime.datetime | None]]:
    """Retrieves all games starting within the specified calendar year and month."""
    cursor.execute(
        "SELECT id, title, is_active, start_time, end_time FROM games "
        "WHERE YEAR(start_time) = %s AND MONTH(start_time) = %s "
        "ORDER BY id ASC",
        (year, month)
    )
    return typing.cast(
        list[tuple[int, str, bool, datetime.datetime | None, datetime.datetime | None]],
        cursor.fetchall()
    )


def build_turnover_announcement_email(
    active_game: tuple[int, str],
    active_date: datetime.datetime,
    preview_game: tuple[int, str],
    preview_date: datetime.datetime
) -> tuple[str, str]:
    """Constructs the subject and HTML body for the monthly player turnover announcement email."""
    active_id, active_title = active_game
    preview_id, preview_title = preview_game

    active_month_year = active_date.strftime("%B %Y")
    preview_month_year = preview_date.strftime("%B %Y")

    subject = f"Geodashing Game {active_id} {active_title} ({active_month_year}) has begun!"

    html_body = (
        f"<h2>Game {active_id}: {active_title} is Now Live!</h2>\n"
        f"<p>\n"
        f"Welcome to the start of the <strong>{active_month_year}</strong> Geodashing hunt!\n"
        f"Game {active_id} (<em>{active_title}</em>) is now active and ready for claims and logs.\n"
        f"</p>\n"
        f"<p>\n"
        f"Head out to the coordinates and record your finds on the map:\n"
        f"<a href=\"https://www.geodashing.org/\">https://www.geodashing.org/</a>\n"
        f"</p>\n"
        f"<hr/>\n"
        f"<h3>Previous Month Concluded</h3>\n"
        f"<p>\n"
        f"The previous month's game has now concluded and scoring is locked.\n"
        f"Full results, scoreboards, and the official game summary will be published and sent out "
        f"soon in a separate communication once the writeup is composed.\n"
        f"</p>\n"
        f"<hr/>\n"
        f"<h3>Preview Game Open: {preview_month_year}</h3>\n"
        f"<p>\n"
        f"Looking ahead, Game {preview_id} (<em>{preview_title}</em>) for "
        f"<strong>{preview_month_year}</strong>\n"
        f"is now seeded in preview mode on the map for route planning and strategy.\n"
        f"</p>"
    )
    return subject, html_body.strip()


def send_turnover_announcement(
    config_path: str,
    subject: str,
    html_body: str,
    dry_run: bool = False
) -> None:
    """Dispatches the monthly turnover announcement email to the player mailing list."""
    to_email, credentials_path = load_mail_config(config_path)

    if dry_run:
        print(f"[DRY RUN] Would send turnover announcement to {to_email} with subject: '{subject}'")
        return

    app_env = os.getenv('APP_ENV') or ''
    if app_env == 'testing':
        print(f"APP_ENV=testing: Suppressed physical email transmission to {to_email}")
        return

    print(f"Dispatching turnover announcement email to {to_email}...")
    send_via_gmail_api(credentials_path, to_email, subject, html_body)


def _activate_current_month_game(
    cursor: mysql.connector.cursor.MySQLCursor,
    conn: mysql.connector.connection.MySQLConnection,
    target_date: tuple[int, int],
    dry_run: bool
) -> tuple[int, str]:
    """Inspects and activates the preview game for the current month."""
    cur_year, cur_month = target_date
    current_games = get_games_for_month(cursor, cur_year, cur_month)
    if not current_games:
        raise RuntimeError(
            f"Turnover Aborted: No preview game exists for {cur_year}-{cur_month:02d}. "
            "Fail-fast triggered."
        )

    if len(current_games) > 1:
        conflicting_ids = ", ".join(str(g[0]) for g in current_games)
        raise RuntimeError(
            f"Turnover Aborted: Multiple conflicting games found for {cur_year}-{cur_month:02d} "
            f"(Game IDs: {conflicting_ids}). Fail-fast triggered. Clean up duplicates."
        )

    active_id, active_title, is_already_active, _, _ = current_games[0]

    if is_already_active:
        print(f"Current month game (Game {active_id}: '{active_title}') is already ACTIVE.")
    else:
        print(f"Activating current month game (Game {active_id}: '{active_title}')...")
        if not dry_run:
            cursor.execute("UPDATE games SET is_active = FALSE")
            cursor.execute("UPDATE games SET is_active = TRUE WHERE id = %s", (active_id,))
            conn.commit()
            print(f"Game {active_id} is now ACTIVE.")
        else:
            print(f"[DRY RUN] Would update games SET is_active = TRUE for ID {active_id}")

    return active_id, active_title


def _generate_next_preview_game(
    cursor: mysql.connector.cursor.MySQLCursor,
    conn: mysql.connector.connection.MySQLConnection,
    target_date: tuple[int, int],
    dashpoint_count: int,
    dry_run: bool
) -> tuple[int, str]:
    """Checks and seeds the preview game for the upcoming month."""
    next_year, next_month = target_date
    next_games = get_games_for_month(cursor, next_year, next_month)
    if next_games:
        preview_id, preview_title, _, _, _ = next_games[0]
        print(f"Next month preview game exists (Game {preview_id}: '{preview_title}'). "
              "Skipping generation.")
        return preview_id, preview_title

    current_dir = os.path.dirname(os.path.abspath(__file__))
    preview_title = get_game_title(
        next_year, next_month, os.path.join(current_dir, '../../data/game_titles.json')
    )
    print(f"Generating next month preview game: '{preview_title}' "
          f"({next_year}-{next_month:02d}) with {dashpoint_count} points...")

    if not dry_run:
        points = backend.scripts.generate_game.generate_valid_dashpoints(
            target_count=dashpoint_count,
            land_zip_path=os.path.join(current_dir, '../../data/ne_10m_land.zip'),
            lakes_zip_path=os.path.join(current_dir, '../../data/ne_10m_lakes.zip')
        )
        preview_id = backend.scripts.generate_game.initialize_new_game(
            cursor, preview_title, next_year, next_month, is_preview=True
        )
        backend.scripts.generate_game.bulk_insert_dashpoints(
            cursor, points, preview_id, os.path.join(current_dir, '../../data/bad_words.txt')
        )
        conn.commit()
        print(f"Preview Game {preview_id} ('{preview_title}') seeded successfully "
              f"with {len(points)} points.")
    else:
        preview_id = 9999
        print(f"[DRY RUN] Would generate {dashpoint_count} dashpoints and insert preview game "
              f"'{preview_title}'.")

    return preview_id, preview_title


def _dispatch_announcement_email(
    config_path: str,
    active_info: tuple[int, str, datetime.datetime],
    preview_info: tuple[int, str, datetime.datetime],
    dry_run: bool
) -> None:
    """Helper to format and dispatch the player turnover announcement email."""
    subject, html_body = build_turnover_announcement_email(
        active_game=(active_info[0], active_info[1]),
        active_date=active_info[2],
        preview_game=(preview_info[0], preview_info[1]),
        preview_date=preview_info[2]
    )
    try:
        send_turnover_announcement(config_path, subject, html_body, dry_run=dry_run)
    except Exception as e:
        print(f"ERROR: Failed to dispatch turnover announcement email: {e}", file=sys.stderr)
        raise


def _compute_rollover_dates(
    tz_name: str,
    overrides: dict[str, int | None] | None
) -> tuple[datetime.datetime, datetime.datetime]:
    """Computes the start dates for the current active month and next preview month."""
    tz: datetime.tzinfo
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:  # pylint: disable=broad-exception-caught
        tz = datetime.timezone.utc

    now = datetime.datetime.now(tz)
    cur_year = (overrides.get('year') if overrides else None) or now.year
    cur_month = (overrides.get('month') if overrides else None) or now.month
    next_year, next_month = (cur_year + 1, 1) if cur_month == 12 else (cur_year, cur_month + 1)

    return (
        datetime.datetime(cur_year, cur_month, 1, tzinfo=tz),
        datetime.datetime(next_year, next_month, 1, tzinfo=tz)
    )


def execute_rollover(
    cursor: mysql.connector.cursor.MySQLCursor,
    conn: mysql.connector.connection.MySQLConnection,
    config_path: str,
    dry_run: bool = False,
    overrides: dict[str, int | None] | None = None
) -> None:
    """Orchestrates the complete end-of-month turnover: activates current preview game,
    generates next preview game, and announces to players."""
    game_config = load_game_config(config_path)
    count_override = overrides.get('count') if overrides else None
    dashpoint_count = count_override or game_config.get('default_dashpoint_count', 35000)

    tz_str = game_config.get('timezone', 'America/New_York')
    cur_date, next_date = _compute_rollover_dates(tz_str, overrides)

    print("=" * 80)
    print("GEODASHING MONTHLY TURNOVER ORCHESTRATOR")
    print(f"Timezone: {tz_str} | "
          f"Target: {cur_date.year}-{cur_date.month:02d} | "
          f"Next Preview: {next_date.year}-{next_date.month:02d}")
    if dry_run:
        print("MODE: DRY RUN (No database changes or emails will be dispatched)")
    print("=" * 80)

    # 1. Activate Current Month Game
    active_game = _activate_current_month_game(
        cursor, conn, (cur_date.year, cur_date.month), dry_run
    )

    # 2. Inspect & Generate Next Month Preview Game
    preview_game = _generate_next_preview_game(
        cursor, conn, (next_date.year, next_date.month), dashpoint_count, dry_run
    )

    # 3. Dispatch Player Announcement Email
    if game_config.get('send_turnover_announcement', True):
        _dispatch_announcement_email(
            config_path,
            (active_game[0], active_game[1], cur_date),
            (preview_game[0], preview_game[1], next_date),
            dry_run
        )

    print("=" * 80)
    print("MONTHLY TURNOVER COMPLETED SUCCESSFULLY.")
    print("=" * 80)


def execute_cli_actions(
    cursor: mysql.connector.cursor.MySQLCursor,
    conn: mysql.connector.connection.MySQLConnection,
    args: argparse.Namespace,
    config_path: str
) -> None:
    """Executes the specific actions chosen via command line arguments."""
    need_separator = False

    if args.list:
        list_games(cursor)
        need_separator = True

    if args.activate is not None:
        if need_separator:
            print("\n" + "=" * 80 + "\n")
        activate_game(cursor, conn, args.activate)
        need_separator = True

    if args.upload_summary is not None:
        if need_separator:
            print("\n" + "=" * 80 + "\n")
        upload_summary(cursor, conn, args.game_id, args.upload_summary)
        need_separator = True

    if args.email_summary:
        if need_separator:
            print("\n" + "=" * 80 + "\n")
        email_summary(cursor, args.game_id, config_path)
        need_separator = True

    if args.rollover:
        if need_separator:
            print("\n" + "=" * 80 + "\n")
        execute_rollover(
            cursor, conn, config_path,
            dry_run=args.dry_run,
            overrides={"year": args.year, "month": args.month, "count": args.count}
        )


def main() -> None:
    """Main entrypoint for the game administration script."""
    parser = argparse.ArgumentParser(description="Geodashing Game Administration Utility")
    parser.add_argument('--list', action='store_true', help="List all games chronologically")
    parser.add_argument('--activate', type=int, metavar='GAME_ID',
                        help="Activate a specific game ID and retire all others")
    parser.add_argument('--upload-summary', type=str, metavar='FILE_PATH',
                        help="Upload an HTML summary fragment for the specified game_id")
    parser.add_argument('--email-summary', action='store_true',
                        help="Email the HTML summary for the specified game_id")
    parser.add_argument('--game_id', type=int, metavar='GAME_ID',
                        help="The game ID for the summary upload or email")
    parser.add_argument('--rollover', action='store_true',
                        help="Execute the automated end-of-month game rollover")
    parser.add_argument('--dry-run', action='store_true',
                        help="Simulate the rollover without writing changes or sending emails")
    parser.add_argument('--year', type=int,
                        help="Optional override year for rollover (defaults to current year)")
    parser.add_argument('--month', type=int,
                        help="Optional override month for rollover (defaults to current month)")
    parser.add_argument('--count', type=int,
                        help="Optional override dashpoint count for preview game generation")
    args = parser.parse_args()

    if (not args.list and args.activate is None and
            args.upload_summary is None and not args.email_summary and not args.rollover):
        parser.print_help()
        sys.exit(1)

    if args.upload_summary is not None and args.game_id is None:
        print("Error: --game_id is required when using --upload-summary.")
        sys.exit(1)

    if args.email_summary and args.game_id is None:
        print("Error: --game_id is required when using --email-summary.")
        sys.exit(1)

    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, '../config.ini')

    try:
        with backend.scripts.db_utils.db_session(config_path) as (conn, cursor):
            execute_cli_actions(cursor, conn, args, config_path)
    except (FileNotFoundError, RuntimeError, ValueError) as e:
        print(f"\nExecution Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
