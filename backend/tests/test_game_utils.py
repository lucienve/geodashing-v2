"""Unit tests for game_utils.py administrative and validation scripts."""
# pylint: disable=protected-access

import unittest
from unittest import mock
import os
import sys

from backend.scripts.game_utils import HTMLFragmentValidator, upload_summary

class TestHTMLFragmentValidator(unittest.TestCase):
    """Test case verifying HTML fragment whitelisting, stack-nesting, and format checks."""

    def setUp(self):
        self.validator = HTMLFragmentValidator()

    def test_valid_html_fragment(self):
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

    def test_forbidden_layout_tags_fail(self):
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

    def test_forbidden_script_tags_fail(self):
        """Security checks: scripts, iframes, and embeds must be blocked."""
        bad_html_1 = "<p>Nice day</p><script>alert('hack');</script>"
        bad_html_2 = "<div><iframe src='https://malicious.site'></iframe></div>"
        
        errors1 = self.validator.validate(bad_html_1)
        self.assertTrue(any("Forbidden tag" in err and "script" in err for err in errors1))

        errors2 = self.validator.validate(bad_html_2)
        self.assertTrue(any("Forbidden tag" in err and "iframe" in err for err in errors2))

    def test_disallowed_tag_fail(self):
        """Ensuring unsupported elements like <marquee>, <table>, or <form> are blocked."""
        bad_html = "<marquee>Awesome Game!</marquee>"
        errors = self.validator.validate(bad_html)
        self.assertTrue(any("Disallowed tag detected: <marquee>" in err for err in errors))

    def test_mismatched_and_unclosed_tags(self):
        """Tags that are left unclosed or nested incorrectly should fail parsing."""
        mismatched = "<p>Hello <strong>world</p></strong>"
        unclosed = "<div><p>This is an open paragraph"
        
        errors1 = self.validator.validate(mismatched)
        self.assertTrue(any("Mismatched closing tag" in err for err in errors1))

        errors2 = self.validator.validate(unclosed)
        self.assertTrue(any("Unclosed tags detected" in err for err in errors2))

    def test_empty_content_fails(self):
        """Uploading completely empty, white-spaced, or tag-only content is blocked."""
        errors1 = self.validator.validate("")
        self.assertTrue(any("no text content" in err for err in errors1))

        errors2 = self.validator.validate("   \n   \t  ")
        self.assertTrue(any("no text content" in err for err in errors2))

    def test_missing_and_invalid_attributes(self):
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

    @mock.patch("backend.scripts.game_utils.os.path.exists", autospec=True)
    @mock.patch("builtins.open", new_callable=mock.mock_open, read_data="<p>Awesome summary content</p>")
    def test_successful_summary_upload(self, mock_file_open, mock_path_exists):
        """A valid HTML fragment and existing game ID should commit successfully to the database."""
        mock_path_exists.return_value = True
        
        mock_cursor = mock.MagicMock()
        mock_cursor.fetchone.return_value = (12, "Game Title")
        mock_conn = mock.MagicMock()

        # Execute upload
        upload_summary(mock_cursor, mock_conn, 12, "dummy_summary.html")

        # Verify DB queries
        mock_cursor.execute.assert_any_call("SELECT id, title FROM games WHERE id = %s", (12,))
        mock_cursor.execute.assert_any_call("UPDATE games SET summary = %s WHERE id = %s", ("<p>Awesome summary content</p>", 12))
        
        # Verify transaction committed
        mock_conn.commit.assert_called_once()
        mock_file_open.assert_called_once_with("dummy_summary.html", 'r', encoding='utf-8')

    @mock.patch("backend.scripts.game_utils.os.path.exists", autospec=True)
    def test_non_existent_game_id_aborts(self, mock_path_exists):
        """Uploading to a non-existent game ID must raise a SystemExit immediately without checking files."""
        mock_path_exists.return_value = True
        mock_cursor = mock.MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn = mock.MagicMock()

        with self.assertRaises(SystemExit):
            upload_summary(mock_cursor, mock_conn, 999, "dummy.html")

        mock_conn.commit.assert_not_called()

    @mock.patch("backend.scripts.game_utils.os.path.exists", autospec=True)
    @mock.patch("builtins.open", new_callable=mock.mock_open, read_data="<html><body>No HTML fragments!</body></html>")
    def test_invalid_summary_fails_upload(self, mock_file_open, mock_path_exists):
        """Invalid summaries containing document wrapper tags must trigger SystemExit without DB changes."""
        mock_path_exists.return_value = True
        mock_cursor = mock.MagicMock()
        mock_cursor.fetchone.return_value = (12, "Test Game")
        mock_conn = mock.MagicMock()

        with self.assertRaises(SystemExit):
            upload_summary(mock_cursor, mock_conn, 12, "bad.html")

        mock_conn.commit.assert_not_called()
