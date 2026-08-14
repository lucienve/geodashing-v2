"""Unit tests for game_utils.py administrative and validation scripts."""
# pylint: disable=protected-access

import argparse
import datetime
import http.client
import json
import unittest
import unittest.mock
import google.oauth2.service_account
import mysql.connector
import mysql.connector.cursor
import shapely.geometry

import backend.scripts.game_utils

class TestHTMLFragmentValidator(unittest.TestCase):
    """Test case verifying HTML fragment whitelisting, stack-nesting, and format checks."""

    def setUp(self) -> None:
        self.validator = backend.scripts.game_utils.HTMLFragmentValidator()

    def test_valid_html_fragment(self) -> None:
        """Standard valid HTML formatting fragments should pass completely."""
        valid_html = (
            "<h2>April Hunt Results!</h2>"
            "<p>The game came to an exciting finish. "
            "<strong>Player1</strong> took the victory near <span>Seattle</span>.</p>"
            "<ul>"
            "<li>First hunt: <a href='#dashpoint?id=GD001-AAAA'>GD001-AAAA</a></li>"
            "<li>Second hunt: <a href='https://www.geodashing.org/'>Main Site</a></li>"
            "</ul>"
            "<p>Check this awesome view:<br/>"
            "<img src='https://storage.googleapis.com/geodashing/1.jpg' alt='Hunt view'/>"
            "</p>"
        )
        errors = self.validator.validate(valid_html)
        self.assertEqual(len(errors), 0, f"Expected no errors, got: {errors}")

    def test_forbidden_layout_tags_fail(self) -> None:
        """Enforcing that document layouts (<html>, <body>, etc.) fail fragment validation."""
        full_doc = (
            "<!DOCTYPE html>"
            "<html>"
            "<head><title>My Title</title></head>"
            "<body><p>Hello world</p></body>"
            "</html>"
        )
        errors = self.validator.validate(full_doc)
        self.assertTrue(any("Forbidden tag detected" in err for err in errors))

    def test_forbidden_script_tags_fail(self) -> None:
        """Security checks: scripts, iframes, and embeds must be blocked."""
        bad_html_1 = "<p>Nice day</p><script>alert('hack');</script>"
        bad_html_2 = "<div><iframe src='https://malicious.site'></iframe></div>"

        errors1 = self.validator.validate(bad_html_1)
        self.assertTrue(any("Forbidden tag" in err and "script" in err for err in errors1))

        errors2 = self.validator.validate(bad_html_2)
        self.assertTrue(any("Forbidden tag" in err and "iframe" in err for err in errors2))

    def test_disallowed_tag_fail(self) -> None:
        """Ensuring unsupported elements like <marquee>, <table>, or <form> are blocked."""
        bad_html = "<marquee>Awesome Game!</marquee>"
        errors = self.validator.validate(bad_html)
        self.assertTrue(any("Disallowed tag detected: <marquee>" in err for err in errors))

    def test_mismatched_and_unclosed_tags(self) -> None:
        """Tags that are left unclosed or nested incorrectly should fail parsing."""
        mismatched = "<p>Hello <strong>world</p></strong>"
        unclosed = "<div><p>This is an open paragraph"

        errors1 = self.validator.validate(mismatched)
        self.assertTrue(any("Mismatched closing tag" in err for err in errors1))

        errors2 = self.validator.validate(unclosed)
        self.assertTrue(any("Unclosed tags detected" in err for err in errors2))

    def test_empty_content_fails(self) -> None:
        """Uploading completely empty, white-spaced, or tag-only content is blocked."""
        errors1 = self.validator.validate("")
        self.assertTrue(any("no text content" in err for err in errors1))

        errors2 = self.validator.validate("   \n   \t  ")
        self.assertTrue(any("no text content" in err for err in errors2))

    def test_missing_and_invalid_attributes(self) -> None:
        """Hyperlinks and images must have properly populated src and href tags."""
        no_href = "<a>Text</a>"
        empty_href = "<a href=''>Text</a>"
        invalid_href = "<a href='javascript:alert(1)'>Text</a>"

        errors1 = self.validator.validate(no_href)
        self.assertTrue(any("Anchor <a> tag is missing href attribute" in err for err in errors1))

        errors2 = self.validator.validate(empty_href)
        self.assertTrue(any("Invalid or empty href" in err for err in errors2))

        errors3 = self.validator.validate(invalid_href)
        self.assertTrue(any("Invalid or empty href" in err for err in errors3))

        no_src = "<img>"
        errors4 = self.validator.validate(no_src)
        self.assertTrue(any("Image <img> tag is missing src attribute" in err for err in errors4))


class TestUploadSummaryCLI(unittest.TestCase):
    """Test cases validating command line summary uploads and database commits."""

    @unittest.mock.patch("backend.scripts.game_utils.os.path.exists", autospec=True)
    @unittest.mock.patch("builtins.open", new_callable=unittest.mock.mock_open,
                         read_data="<p>Awesome summary content</p>")
    def test_successful_summary_upload(
        self,
        mock_file_open: unittest.mock.MagicMock,
        mock_path_exists: unittest.mock.MagicMock
    ) -> None:
        """A valid HTML fragment and existing game ID should commit successfully."""
        mock_path_exists.return_value = True

        mock_cursor = unittest.mock.MagicMock(spec=mysql.connector.cursor.MySQLCursor)
        mock_cursor.fetchone.return_value = (12, "Game Title")
        mock_conn = unittest.mock.MagicMock(spec=mysql.connector.connection.MySQLConnection)

        # Execute upload
        backend.scripts.game_utils.upload_summary(mock_cursor, mock_conn, 12, "dummy_summary.html")

        # Verify DB queries
        mock_cursor.execute.assert_any_call("SELECT id, title FROM games WHERE id = %s", (12,))
        mock_cursor.execute.assert_any_call(
            "UPDATE games SET summary = %s WHERE id = %s",
            ("<p>Awesome summary content</p>", 12)
        )

        # Verify transaction committed
        mock_conn.commit.assert_called_once()
        mock_file_open.assert_called_once_with("dummy_summary.html", 'r', encoding='utf-8')

    @unittest.mock.patch("backend.scripts.game_utils.os.path.exists", autospec=True)
    def test_non_existent_game_id_aborts(self, mock_path_exists: unittest.mock.MagicMock) -> None:
        """Uploading to a non-existent game ID must raise a SystemExit
        immediately without checking files."""
        mock_path_exists.return_value = True
        mock_cursor = unittest.mock.MagicMock(spec=mysql.connector.cursor.MySQLCursor)
        mock_cursor.fetchone.return_value = None
        mock_conn = unittest.mock.MagicMock(spec=mysql.connector.connection.MySQLConnection)

        with self.assertRaises(SystemExit):
            backend.scripts.game_utils.upload_summary(mock_cursor, mock_conn, 999, "dummy.html")

        mock_conn.commit.assert_not_called()

    @unittest.mock.patch("backend.scripts.game_utils.os.path.exists", autospec=True)
    @unittest.mock.patch("builtins.open", new_callable=unittest.mock.mock_open,
                         read_data="<html><body>No HTML fragments!</body></html>")
    def test_invalid_summary_fails_upload(
        self,
        mock_file_open: unittest.mock.MagicMock,
        mock_path_exists: unittest.mock.MagicMock
    ) -> None:
        """Invalid summaries containing document wrapper tags must trigger
        SystemExit without DB changes."""
        mock_path_exists.return_value = True
        mock_cursor = unittest.mock.MagicMock(spec=mysql.connector.cursor.MySQLCursor)
        mock_cursor.fetchone.return_value = (12, "Test Game")
        mock_conn = unittest.mock.MagicMock(spec=mysql.connector.connection.MySQLConnection)

        with self.assertRaises(SystemExit):
            backend.scripts.game_utils.upload_summary(mock_cursor, mock_conn, 12, "bad.html")

        mock_file_open.assert_called_once_with("bad.html", 'r', encoding='utf-8')
        mock_conn.commit.assert_not_called()


class TestEmailSummaryCLI(unittest.TestCase):
    """Test cases validating the email_summary configurations and API."""

    def setUp(self) -> None:
        self.mock_cursor = unittest.mock.MagicMock(spec=mysql.connector.cursor.MySQLCursor)
        self.mock_conn = unittest.mock.MagicMock(spec=mysql.connector.connection.MySQLConnection)

    @unittest.mock.patch("backend.scripts.game_utils.os.path.exists", autospec=True)
    def test_missing_game_id_aborts(self, mock_path_exists: unittest.mock.MagicMock) -> None:
        """If the game_id does not exist, the script should terminate with SystemExit."""
        mock_path_exists.return_value = True
        self.mock_cursor.fetchone.return_value = None

        with self.assertRaises(SystemExit):
            backend.scripts.game_utils.email_summary(self.mock_cursor, 999, "dummy_config.ini")

    @unittest.mock.patch("backend.scripts.game_utils.os.path.exists", autospec=True)
    def test_missing_summary_aborts(self, mock_path_exists: unittest.mock.MagicMock) -> None:
        """If the game exists but has no summary, the script should terminate with SystemExit."""
        mock_path_exists.return_value = True
        self.mock_cursor.fetchone.return_value = (
            "Game 12", None, datetime.datetime(2026, 5, 1, 0, 0)
        )

        with self.assertRaises(SystemExit):
            backend.scripts.game_utils.email_summary(self.mock_cursor, 12, "dummy_config.ini")

    @unittest.mock.patch("backend.scripts.game_utils.os.path.exists", autospec=True)
    def test_testing_env_bypass(self, mock_path_exists: unittest.mock.MagicMock) -> None:
        """If APP_ENV is 'testing', physical email sending must be bypassed and exit cleanly."""
        mock_path_exists.return_value = True
        self.mock_cursor.fetchone.return_value = (
            "Game 12", "<p>Summary html</p>", datetime.datetime(2026, 5, 1, 0, 0)
        )

        config_data = (
            "[mail]\n"
            "MAILING_LIST_ADDRESS=tracker@geodashing.org\n"
            "GOOGLE_APPLICATION_CREDENTIALS=creds.json"
        )
        with unittest.mock.patch("builtins.open", unittest.mock.mock_open(read_data=config_data)), \
             unittest.mock.patch.dict("os.environ", {"APP_ENV": "testing"}):
            # Should complete cleanly without raising SystemExit or calling APIs
            backend.scripts.game_utils.email_summary(self.mock_cursor, 12, "dummy_config.ini")

    @unittest.mock.patch("backend.scripts.game_utils.os.path.exists", autospec=True)
    def test_successful_email_dispatch(self, mock_path_exists: unittest.mock.MagicMock) -> None:
        """A valid game, summary, and configs should dispatch successfully via Gmail REST API."""
        mock_path_exists.return_value = True
        self.mock_cursor.fetchone.return_value = (
            "Game 12", "<p>Summary html</p>", datetime.datetime(2026, 5, 1, 0, 0)
        )

        # Mock Credentials
        mock_creds = unittest.mock.MagicMock(spec=google.oauth2.service_account.Credentials)
        mock_creds.token = "fake_access_token"
        mock_creds.with_subject.return_value = mock_creds

        # Mock API Response
        mock_response = unittest.mock.MagicMock(spec=http.client.HTTPResponse)
        mock_response.read.return_value = b'{"id": "msg123"}'
        mock_response.__enter__.return_value = mock_response

        config_data = (
            "[mail]\n"
            "MAILING_LIST_ADDRESS=tracker@geodashing.org\n"
            "GOOGLE_APPLICATION_CREDENTIALS=creds.json"
        )

        with unittest.mock.patch("builtins.open", unittest.mock.mock_open(read_data=config_data)), \
             unittest.mock.patch("google.oauth2.service_account.Credentials"
                        ".from_service_account_file", autospec=True) as mock_creds_file, \
             unittest.mock.patch("google.auth.transport.requests.Request", autospec=True), \
             unittest.mock.patch("urllib.request.urlopen", autospec=True) as mock_urlopen, \
             unittest.mock.patch.dict("os.environ", {"APP_ENV": ""}):

            mock_creds_file.return_value = mock_creds
            mock_urlopen.return_value = mock_response

            # Execute
            backend.scripts.game_utils.email_summary(self.mock_cursor, 12, "dummy_config.ini")

            # Verify Google service account called with domain-wide delegation impersonation
            mock_creds_file.assert_called_once_with(
                "creds.json",
                scopes=['https://www.googleapis.com/auth/gmail.send']
            )
            mock_creds.with_subject.assert_called_once_with("tracker@geodashing.org")
            mock_creds.refresh.assert_called_once()

            # Verify HTTP post request was sent to Gmail REST API
            args, _ = mock_urlopen.call_args
            req = args[0]
            self.assertEqual(
                req.get_full_url(),
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
            )
            self.assertEqual(req.get_header("Authorization"), "Bearer fake_access_token")
            self.assertEqual(req.get_header("Content-type"), "application/json")
            self.assertEqual(req.get_method(), "POST")


class TestRolloverCLI(unittest.TestCase):
    """Test cases validating the automated monthly rollover functions and CLI workflow."""

    def setUp(self) -> None:
        self.mock_cursor = unittest.mock.MagicMock(spec=mysql.connector.cursor.MySQLCursor)
        self.mock_conn = unittest.mock.MagicMock(spec=mysql.connector.connection.MySQLConnection)

    def test_load_game_config_defaults(self) -> None:
        """Loading config from non-existent path should return default configurations."""
        with unittest.mock.patch("backend.scripts.game_utils.os.path.exists", return_value=False):
            config = backend.scripts.game_utils.load_game_config("nonexistent.ini")
            self.assertEqual(config['default_dashpoint_count'], 35000)
            self.assertEqual(config['timezone'], "America/New_York")
            self.assertTrue(config['send_turnover_announcement'])

    def test_load_game_config_parsed(self) -> None:
        """Loading config with explicit [game] section should parse values properly."""
        config_text = (
            "[game]\n"
            "DEFAULT_DASHPOINT_COUNT = 40000\n"
            "TIMEZONE = America/Chicago\n"
            "SEND_TURNOVER_ANNOUNCEMENT = false\n"
        )
        with unittest.mock.patch("backend.scripts.game_utils.os.path.exists", return_value=True), \
             unittest.mock.patch("builtins.open", unittest.mock.mock_open(read_data=config_text)):
            config = backend.scripts.game_utils.load_game_config("dummy.ini")
            self.assertEqual(config['default_dashpoint_count'], 40000)
            self.assertEqual(config['timezone'], "America/Chicago")
            self.assertFalse(config['send_turnover_announcement'])

    def test_get_game_title_from_json(self) -> None:
        """A valid match in game_titles.json should return the custom title."""
        titles_data = json.dumps({"2026-08": "Briars, Bogs, and Other Minor Inconveniences"})
        with unittest.mock.patch("backend.scripts.game_utils.os.path.exists", return_value=True), \
             unittest.mock.patch("builtins.open", unittest.mock.mock_open(read_data=titles_data)):
            title = backend.scripts.game_utils.get_game_title(2026, 8, "data/game_titles.json")
            self.assertEqual(title, "Briars, Bogs, and Other Minor Inconveniences")

    def test_get_game_title_fallback(self) -> None:
        """Missing title in json or missing file should fall back to standard template."""
        with unittest.mock.patch("backend.scripts.game_utils.os.path.exists", return_value=False):
            title = backend.scripts.game_utils.get_game_title(2026, 9, "data/game_titles.json")
            self.assertEqual(title, "September 2026 Dashing Classic")

    def test_get_games_for_month(self) -> None:
        """Querying games for month should return typed tuple list."""
        self.mock_cursor.fetchall.return_value = [
            (14, "June 2026", False, datetime.datetime(2026, 6, 1, 0, 0),
             datetime.datetime(2026, 6, 30, 23, 59))
        ]
        games = backend.scripts.game_utils.get_games_for_month(self.mock_cursor, 2026, 6)
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0][0], 14)
        self.mock_cursor.execute.assert_called_once_with(
            "SELECT id, title, is_active, start_time, end_time FROM games "
            "WHERE YEAR(start_time) = %s AND MONTH(start_time) = %s "
            "ORDER BY id ASC",
            (2026, 6)
        )

    def test_build_turnover_announcement_email(self) -> None:
        """Verifies subject and HTML body structure for player announcements."""
        active_date = datetime.datetime(2026, 8, 1)
        preview_date = datetime.datetime(2026, 9, 1)
        subject, body = backend.scripts.game_utils.build_turnover_announcement_email(
            active_game=(15, "August 2026 Sprint"),
            active_date=active_date,
            preview_game=(16, "September 2026 Classic"),
            preview_date=preview_date
        )
        self.assertEqual(subject, "Geodashing Game 15 August 2026 Sprint (August 2026) has begun!")
        self.assertIn("Game 15: August 2026 Sprint is Now Live!", body)
        self.assertIn("Previous Month Concluded", body)
        self.assertIn("Game 16 (<em>September 2026 Classic</em>) for "
                      "<strong>September 2026</strong>", body)

    def test_activate_current_month_missing_fails_fast(self) -> None:
        """If no game exists for current month, _activate_current_month_game raises RuntimeError."""
        self.mock_cursor.fetchall.return_value = []
        with self.assertRaises(RuntimeError) as ctx:
            backend.scripts.game_utils._activate_current_month_game(
                self.mock_cursor, self.mock_conn, (2026, 8), dry_run=False
            )
        self.assertIn("No preview game exists for 2026-08", str(ctx.exception))

    def test_activate_current_month_multiple_fails_fast(self) -> None:
        """If multiple conflicting games exist for current month, raise RuntimeError."""
        self.mock_cursor.fetchall.return_value = [
            (14, "Game A", False, None, None),
            (15, "Game B", False, None, None)
        ]
        with self.assertRaises(RuntimeError) as ctx:
            backend.scripts.game_utils._activate_current_month_game(
                self.mock_cursor, self.mock_conn, (2026, 8), dry_run=False
            )
        self.assertIn("Multiple conflicting games found", str(ctx.exception))

    def test_activate_current_month_success(self) -> None:
        """Activating an existing preview game updates DB state and commits."""
        self.mock_cursor.fetchall.return_value = [
            (14, "August 2026", False, None, None)
        ]
        active_id, active_title = backend.scripts.game_utils._activate_current_month_game(
            self.mock_cursor, self.mock_conn, (2026, 8), dry_run=False
        )
        self.assertEqual(active_id, 14)
        self.assertEqual(active_title, "August 2026")
        self.mock_cursor.execute.assert_any_call("UPDATE games SET is_active = FALSE")
        self.mock_cursor.execute.assert_any_call(
            "UPDATE games SET is_active = TRUE WHERE id = %s", (14,)
        )
        self.mock_conn.commit.assert_called_once()

    def test_generate_next_preview_game_already_exists(self) -> None:
        """If next preview game is already in DB, skip point generation."""
        self.mock_cursor.fetchall.return_value = [
            (16, "September 2026", False, None, None)
        ]
        preview_id, preview_title = backend.scripts.game_utils._generate_next_preview_game(
            self.mock_cursor, self.mock_conn, (2026, 9), 35000, dry_run=False
        )
        self.assertEqual(preview_id, 16)
        self.assertEqual(preview_title, "September 2026")

    @unittest.mock.patch("backend.scripts.generate_game.generate_valid_dashpoints")
    @unittest.mock.patch("backend.scripts.generate_game.initialize_new_game")
    @unittest.mock.patch("backend.scripts.generate_game.bulk_insert_dashpoints")
    def test_generate_next_preview_game_generates(
        self,
        mock_bulk_insert: unittest.mock.MagicMock,
        mock_init_game: unittest.mock.MagicMock,
        mock_gen_points: unittest.mock.MagicMock
    ) -> None:
        """If next preview is missing, generate points and seed DB."""
        self.mock_cursor.fetchall.return_value = []
        mock_gen_points.return_value = [shapely.geometry.Point(0, 0)]
        mock_init_game.return_value = 17

        preview_id, preview_title = backend.scripts.game_utils._generate_next_preview_game(
            self.mock_cursor, self.mock_conn, (2026, 9), 35000, dry_run=False
        )
        self.assertEqual(preview_id, 17)
        self.assertEqual(preview_title, "Random Destinations of Unwarranted Grandeur")
        mock_gen_points.assert_called_once()
        mock_init_game.assert_called_once()
        mock_bulk_insert.assert_called_once()
        self.mock_conn.commit.assert_called_once()

    @unittest.mock.patch("backend.scripts.game_utils.load_game_config")
    @unittest.mock.patch("backend.scripts.game_utils._activate_current_month_game")
    @unittest.mock.patch("backend.scripts.game_utils._generate_next_preview_game")
    @unittest.mock.patch("backend.scripts.game_utils._dispatch_announcement_email")
    def test_execute_rollover_full_flow(
        self,
        mock_dispatch: unittest.mock.MagicMock,
        mock_gen_preview: unittest.mock.MagicMock,
        mock_activate: unittest.mock.MagicMock,
        mock_load_cfg: unittest.mock.MagicMock
    ) -> None:
        """Full rollover execution orchestrates activation, generation, and announcement."""
        mock_load_cfg.return_value = {
            'default_dashpoint_count': 35000,
            'timezone': 'America/New_York',
            'send_turnover_announcement': True
        }
        mock_activate.return_value = (14, "August 2026")
        mock_gen_preview.return_value = (15, "September 2026")

        backend.scripts.game_utils.execute_rollover(
            self.mock_cursor, self.mock_conn, "dummy.ini",
            dry_run=False,
            overrides={"year": 2026, "month": 8, "count": 35000}
        )

        mock_activate.assert_called_once_with(self.mock_cursor, self.mock_conn, (2026, 8), False)
        mock_gen_preview.assert_called_once_with(
            self.mock_cursor, self.mock_conn, (2026, 9), 35000, False
        )
        mock_dispatch.assert_called_once()

    @unittest.mock.patch("backend.scripts.game_utils.load_game_config")
    @unittest.mock.patch("backend.scripts.game_utils._activate_current_month_game")
    @unittest.mock.patch("backend.scripts.game_utils._generate_next_preview_game")
    @unittest.mock.patch("backend.scripts.game_utils._dispatch_announcement_email")
    def test_execute_rollover_email_failure_raises(
        self,
        mock_dispatch: unittest.mock.MagicMock,
        mock_gen_preview: unittest.mock.MagicMock,
        mock_activate: unittest.mock.MagicMock,
        mock_load_cfg: unittest.mock.MagicMock
    ) -> None:
        """If email dispatch fails, execute_rollover must re-raise the exception."""
        mock_load_cfg.return_value = {
            'default_dashpoint_count': 35000,
            'timezone': 'America/New_York',
            'send_turnover_announcement': True
        }
        mock_activate.return_value = (14, "August 2026")
        mock_gen_preview.return_value = (15, "September 2026")
        mock_dispatch.side_effect = RuntimeError("SMTP connection timeout")

        with self.assertRaises(RuntimeError) as ctx:
            backend.scripts.game_utils.execute_rollover(
                self.mock_cursor, self.mock_conn, "dummy.ini",
                dry_run=False,
                overrides={"year": 2026, "month": 8, "count": 35000}
            )
        self.assertIn("SMTP connection timeout", str(ctx.exception))

    @unittest.mock.patch("backend.scripts.game_utils.execute_rollover")
    def test_execute_cli_actions_rollover(
        self,
        mock_exec_rollover: unittest.mock.MagicMock
    ) -> None:
        """CLI action dispatcher invokes execute_rollover when --rollover is set."""
        args = argparse.Namespace(
            list=False,
            activate=None,
            upload_summary=None,
            email_summary=False,
            game_id=None,
            rollover=True,
            dry_run=True,
            year=2026,
            month=8,
            count=35000
        )
        backend.scripts.game_utils.execute_cli_actions(
            self.mock_cursor, self.mock_conn, args, "dummy.ini"
        )
        mock_exec_rollover.assert_called_once_with(
            self.mock_cursor, self.mock_conn, "dummy.ini",
            dry_run=True,
            overrides={"year": 2026, "month": 8, "count": 35000}
        )
