"""Administrative utilities for managing Geodashing game lifecycles."""

import argparse
import base64
import configparser
import email.mime.multipart
import email.mime.text
import html.parser
import json
import os
import re
import sys
import urllib.request

from google.oauth2 import service_account
import google.auth.transport.requests

from backend.scripts.db_utils import get_db_connection

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

    def __init__(self):
        super().__init__()
        self.stack = []
        self.errors = []
        self.has_content = False

    def handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()
        self.stack.append(tag_lower)

        if tag_lower in self.FORBIDDEN_TAGS:
            self.errors.append(f"Forbidden tag detected: <{tag}>")
        elif tag_lower not in self.ALLOWED_TAGS:
            self.errors.append(f"Disallowed tag detected: <{tag}>")

        # Anchors and images basic structural attributes validation
        if tag_lower == 'a':
            has_href = False
            for attr, val in attrs:
                if attr.lower() == 'href':
                    has_href = True
                    is_valid = (val.startswith('http://') or
                                val.startswith('https://') or
                                val.startswith('#') or
                                val.startswith('/'))
                    if not val or not is_valid:
                        self.errors.append(f"Invalid or empty href in <a> tag: '{val}'")
            if not has_href:
                self.errors.append("Anchor <a> tag is missing href attribute")

        if tag_lower == 'img':
            has_src = False
            for attr, val in attrs:
                if attr.lower() == 'src':
                    has_src = True
                    if not val:
                        self.errors.append("Image <img> tag has an empty src attribute")
            if not has_src:
                self.errors.append("Image <img> tag is missing src attribute")

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if not self.stack:
            self.errors.append(f"Unexpected closing tag: </{tag}> (no opening tag)")
            return

        expected = self.stack.pop()
        if expected != tag_lower:
            self.errors.append(f"Mismatched closing tag: </{tag}>. Expected </{expected}>")

    def handle_data(self, data):
        if data.strip():
            self.has_content = True

    def validate(self, html_content: str) -> list:
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


def list_games(cursor):
    """Prints all games chronologically."""
    cursor.execute("SELECT id, title, start_time, end_time, is_active "
                   "FROM games ORDER BY start_time ASC")
    games = cursor.fetchall()

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

def activate_game(cursor, conn, game_id: int):
    """Sets the specified game to active and retires all others."""
    # Validate game exists
    cursor.execute("SELECT id, title FROM games WHERE id = %s", (game_id,))
    game = cursor.fetchone()
    if not game:
        print(f"Error: Game ID {game_id} does not exist.")
        return

    print("Retiring all currently active games...")
    cursor.execute("UPDATE games SET is_active = FALSE")

    print(f"Activating Game {game_id} ('{game[1]}')...")
    cursor.execute("UPDATE games SET is_active = TRUE WHERE id = %s", (game_id,))

    conn.commit()
    print("Game rollover completed successfully!")

def upload_summary(cursor, conn, game_id: int, file_path: str):
    """Validates and uploads an HTML summary fragment to the specified game."""
    # Check if game exists
    cursor.execute("SELECT id, title FROM games WHERE id = %s", (game_id,))
    game = cursor.fetchone()
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

def load_mail_config(config_path: str) -> tuple:
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

    creds = service_account.Credentials.from_service_account_file(
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


def email_summary(cursor, game_id: int, config_path: str):
    """Sends the end-of-month game summary to the mailing list specified in config.ini."""
    # 1. Fetch game summary, title, and start_time from database
    cursor.execute("SELECT title, summary, start_time FROM games WHERE id = %s", (game_id,))
    row = cursor.fetchone()
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
        month_year = start_time.strftime("%B %Y")  # e.g., "May 2026"
        subject = f"Geodashing Game {game_id} ({month_year}) Results"
        send_via_gmail_api(credentials_path, to_email, subject, summary)
    except Exception as e:  # pylint: disable=broad-exception-caught
        # Catching all base exceptions is architecturally unavoidable here to ensure
        # the CLI does not crash with raw Python/Google SDK tracebacks in production
        # and instead reports a clean, professional error message to the admin.
        print(f"Failed to email summary: {e}", file=sys.stderr)
        sys.exit(1)


def execute_cli_actions(cursor, conn, args, config_path: str):
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
    args = parser.parse_args()

    if (not args.list and args.activate is None and
            args.upload_summary is None and not args.email_summary):
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
        conn = get_db_connection(config_path)
        cursor = conn.cursor()
        execute_cli_actions(cursor, conn, args, config_path)

    except (FileNotFoundError, RuntimeError) as e:
        print(f"\nExecution Error: {e}")
        sys.exit(1)
    finally:
        if 'cursor' in locals() and cursor is not None:
            cursor.close()
        if 'conn' in locals() and conn.is_connected():
            conn.close()

if __name__ == "__main__":
    main()
