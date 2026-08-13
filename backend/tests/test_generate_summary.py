"""Unit tests for generate_summary.py."""
# pylint: disable=protected-access

import http.client
import unittest.mock
import typing

import google.oauth2.service_account
import google.genai
import google.genai.types

import backend.scripts.generate_summary


def test_parse_photos_json() -> None:
    """Test parsing of photos JSON string."""
    res1 = backend.scripts.generate_summary._parse_photos_json('["http://example.com/1.jpg"]')
    assert not res1
    res2 = backend.scripts.generate_summary._parse_photos_json(
        '[{"url": "http://example.com/1.jpg"}]'
    )
    assert not res2
    res3 = backend.scripts.generate_summary._parse_photos_json(
        '[{"url": "http://example.com/1.jpg", '
        '"thumb_url": "http://example.com/1_thumb.jpg"}]'
    )
    assert res3 == [{
        "url": "http://example.com/1.jpg",
        "thumb_url": "http://example.com/1_thumb.jpg"
    }]
    res4 = backend.scripts.generate_summary._parse_photos_json(
        '[{"url": "http://example.com/1.jpg", '
        '"thumb_url": "http://example.com/1_thumb.jpg", '
        '"caption": "Beautiful sunset"}]'
    )
    assert res4 == [{
        "url": "http://example.com/1.jpg",
        "thumb_url": "http://example.com/1_thumb.jpg",
        "caption": "Beautiful sunset"
    }]
    assert not backend.scripts.generate_summary._parse_photos_json('')
    assert not backend.scripts.generate_summary._parse_photos_json('invalid json')


@unittest.mock.patch("backend.scripts.generate_summary.urllib.request.urlopen", autospec=True)
def test_construct_new_data(mock_urlopen: unittest.mock.MagicMock) -> None:
    """Test constructing the final prompt string."""
    scores = [("player1", 100), ("player2", 50)]
    logs: list[backend.scripts.generate_summary.LogEntry] = [{
        'dp_id': '123',
        'username': 'testuser',
        'city': 'TestCity',
        'photos': [{
            'url': 'http://example.com/1.jpg',
            'thumb_url': 'http://example.com/1_thumb.jpg',
            'caption': 'Sunset caption'
        }],
        'notes': 'Log notes'
    }]

    mock_response = unittest.mock.MagicMock(spec=http.client.HTTPResponse)
    mock_headers = unittest.mock.MagicMock(spec=http.client.HTTPMessage)
    mock_headers.get_content_type.return_value = "image/jpeg"
    mock_response.headers = mock_headers
    mock_response.read.return_value = b"fake image"

    mock_urlopen.return_value.__enter__.return_value = mock_response

    # Mock client and File API as required
    mock_client = unittest.mock.MagicMock(spec=google.genai.Client)
    mock_uploaded_file = unittest.mock.MagicMock(spec=google.genai.types.File)
    mock_client.files.upload.return_value = mock_uploaded_file

    upload_context: backend.scripts.generate_summary.UploadContext = {
        "client": mock_client,
        "local_temp_files": [],
        "uploaded_ai_files": []
    }

    game_title = "Test Game Title"
    result = backend.scripts.generate_summary.construct_new_data(
        game_title, scores, logs, upload_context
    )

    text_result = "".join([p for p in result if isinstance(p, str)])

    assert "Test Game Title" in text_result
    assert "Winner: player1 with 100 points" in text_result
    assert "- player2: 50 points" in text_result
    assert "Log: 123.txt" in text_result
    assert "Log notes" in text_result
    assert "Full: http://example.com/1.jpg" in text_result
    assert "Caption: Sunset caption" in text_result

    # Assert local files and remote uploads were tracked
    assert len(upload_context["local_temp_files"]) == 1
    assert len(upload_context["uploaded_ai_files"]) == 1
    mock_client.files.upload.assert_called_once()

    # Test empty scores
    result_empty = backend.scripts.generate_summary.construct_new_data(
        game_title, [], logs, upload_context
    )
    text_empty = "".join([p for p in result_empty if isinstance(p, str)])
    assert "No players scored in this game." in text_empty


def test_construct_new_data_tied_scores() -> None:
    """Test construct_new_data with tied scores to ensure correct winners format."""
    scores = [("player1", 100), ("player2", 100), ("player3", 50)]
    logs: list[backend.scripts.generate_summary.LogEntry] = [{
        'dp_id': '123',
        'username': 'testuser',
        'city': 'TestCity',
        'photos': [],
        'notes': 'Log notes'
    }]
    mock_client = unittest.mock.MagicMock(spec=google.genai.Client)
    upload_context: backend.scripts.generate_summary.UploadContext = {
        "client": mock_client,
        "local_temp_files": [],
        "uploaded_ai_files": []
    }
    result = backend.scripts.generate_summary.construct_new_data(
        "Test Game Title", scores, logs, upload_context
    )
    text_result = "".join([p for p in result if isinstance(p, str)])
    assert "Winners (tied): player1, player2 with 100 points" in text_result
    assert "- player3: 50 points" in text_result
    assert "- player2: 100 points" not in text_result


@unittest.mock.patch("backend.scripts.generate_summary.os.path.isdir", autospec=True)
@unittest.mock.patch("backend.scripts.generate_summary.os.listdir", autospec=True)
@unittest.mock.patch("backend.scripts.generate_summary.os.path.exists", autospec=True)
@unittest.mock.patch("builtins.open", new_callable=unittest.mock.mock_open, read_data="mock data")
def test_load_chat_history(
    _mock_open: unittest.mock.MagicMock,
    mock_exists: unittest.mock.MagicMock,
    mock_listdir: unittest.mock.MagicMock,
    mock_isdir: unittest.mock.MagicMock
) -> None:
    """Test loading chat history from directory."""
    mock_isdir.return_value = True
    mock_listdir.return_value = ['example_1_input.txt', 'example_2_input.txt', 'other.txt']
    mock_exists.return_value = True

    history = typing.cast(
        list[google.genai.types.Content],
        backend.scripts.generate_summary.load_chat_history("/fake/dir")
    )

    assert len(history) == 4
    assert isinstance(history[0], google.genai.types.Content)
    assert history[0].role == "user"
    assert history[1].role == "model"
    assert history[2].role == "user"
    assert history[3].role == "model"


@unittest.mock.patch("builtins.open", new_callable=unittest.mock.mock_open)
def test_write_summary_files(mock_file: unittest.mock.MagicMock) -> None:
    """Test writing the prompt and html to files."""
    fake_part = unittest.mock.MagicMock(spec=google.genai.types.Part)

    backend.scripts.generate_summary.write_summary_files(
        "/out", 123, ["my prompt", fake_part], "my html"
    )

    # Open should be called twice
    assert mock_file.call_count == 2
    mock_file.assert_any_call("/out/game_123_input.txt", 'w', encoding='utf-8')
    mock_file.assert_any_call("/out/game_123_output.html", 'w', encoding='utf-8')

    # Write should be called with constructed string and html
    handle = mock_file()
    handle.write.assert_any_call("my prompt[IMAGE DATA DETACHED]\n")
    handle.write.assert_any_call("my html")


@unittest.mock.patch("backend.scripts.generate_summary.google.genai.Client", autospec=True)
@unittest.mock.patch("google.auth.default", autospec=True)
def test_get_gemini_client(
    mock_auth_default: unittest.mock.MagicMock,
    mock_client_class: unittest.mock.MagicMock
) -> None:
    """Verify get_gemini_client builds client with project-level billing credentials."""
    mock_creds = unittest.mock.MagicMock(spec=google.oauth2.service_account.Credentials)
    mock_auth_default.return_value = (mock_creds, "default-project")

    ai_config: dict[str, str | None] = {"project_id": "test-project-123"}
    client = backend.scripts.generate_summary.get_gemini_client(ai_config)

    assert client == mock_client_class.return_value
    mock_creds.with_quota_project.assert_called_once_with("test-project-123")
    mock_client_class.assert_called_once_with(
        vertexai=False,
        project="test-project-123",
        credentials=mock_creds.with_quota_project.return_value
    )


@unittest.mock.patch("backend.scripts.generate_summary.load_system_instructions", autospec=True)
@unittest.mock.patch("backend.scripts.generate_summary.load_chat_history", autospec=True)
@unittest.mock.patch(
    "backend.scripts.generate_summary.google.genai.types.GenerateContentConfig",
    autospec=True
)
def test_generate_summary(
    mock_generate_content_config: unittest.mock.MagicMock,
    mock_load_chat: unittest.mock.MagicMock,
    mock_load_sys: unittest.mock.MagicMock
) -> None:
    """Test AI Studio API call structure via Client without thinking_level."""
    mock_client = unittest.mock.MagicMock(spec=google.genai.Client)
    mock_chat_instance = mock_client.chats.create.return_value
    mock_response = mock_chat_instance.send_message.return_value
    mock_response.text = "generated HTML"

    mock_config_instance = mock_generate_content_config.return_value
    mock_load_sys.return_value = "sys inst"
    mock_load_chat.return_value = []

    ai_config: dict[str, str | None] = {"model_name": "m1"}
    result = backend.scripts.generate_summary._generate_summary(
        mock_client, ai_config, "sys.txt", "/fake/dir", ["my prompt"]
    )

    assert result == "generated HTML"
    mock_load_sys.assert_called_once_with("sys.txt")
    mock_load_chat.assert_called_once_with("/fake/dir")
    mock_generate_content_config.assert_called_once_with(
        system_instruction="sys inst",
        thinking_config=None
    )
    mock_client.chats.create.assert_called_once_with(
        model="m1", config=mock_config_instance, history=[]
    )
    mock_chat_instance.send_message.assert_called_once_with(["my prompt"])


@unittest.mock.patch("backend.scripts.generate_summary.load_system_instructions", autospec=True)
@unittest.mock.patch("backend.scripts.generate_summary.load_chat_history", autospec=True)
@unittest.mock.patch(
    "backend.scripts.generate_summary.google.genai.types.ThinkingConfig",
    autospec=True
)
@unittest.mock.patch(
    "backend.scripts.generate_summary.google.genai.types.GenerateContentConfig",
    autospec=True
)
def test_generate_summary_with_thinking_level(
    mock_generate_content_config: unittest.mock.MagicMock,
    mock_thinking_config: unittest.mock.MagicMock,
    mock_load_chat: unittest.mock.MagicMock,
    mock_load_sys: unittest.mock.MagicMock
) -> None:
    """Test AI Studio API call structure via Client with thinking_level."""
    mock_client = unittest.mock.MagicMock(spec=google.genai.Client)
    mock_chat_instance = mock_client.chats.create.return_value
    mock_response = mock_chat_instance.send_message.return_value
    mock_response.text = "generated HTML with thinking"

    mock_config_instance = mock_generate_content_config.return_value
    mock_thinking_instance = mock_thinking_config.return_value
    mock_load_sys.return_value = "sys inst"
    mock_load_chat.return_value = []

    ai_config: dict[str, str | None] = {"model_name": "m1", "thinking_level": "medium"}
    result = backend.scripts.generate_summary._generate_summary(
        mock_client, ai_config, "sys.txt", "/fake/dir", ["my prompt"]
    )

    assert result == "generated HTML with thinking"
    mock_thinking_config.assert_called_once_with(
        thinking_level=google.genai.types.ThinkingLevel.MEDIUM
    )
    mock_generate_content_config.assert_called_once_with(
        system_instruction="sys inst",
        thinking_config=mock_thinking_instance
    )
    mock_client.chats.create.assert_called_once_with(
        model="m1", config=mock_config_instance, history=[]
    )
    mock_chat_instance.send_message.assert_called_once_with(["my prompt"])


@unittest.mock.patch("backend.scripts.generate_summary.os.path.exists", autospec=True)
@unittest.mock.patch("builtins.open", new_callable=unittest.mock.mock_open, read_data="""
[gemini]
GEMINI_API_KEY = "test-key"
GEMINI_MODEL = "gemini-3.7-flash"
GEMINI_THINKING_LEVEL = "medium"
GEMINI_PROJECT_ID = "test-proj"
[mail]
GOOGLE_APPLICATION_CREDENTIALS = "/path/to/creds.json"
""")
def test_configure_environment_full(
    _mock_open: unittest.mock.MagicMock,
    mock_exists: unittest.mock.MagicMock
) -> None:
    """Verify configure_environment loads all parameters including thinking level."""
    mock_exists.return_value = True
    ai_config = backend.scripts.generate_summary.configure_environment("/fake/config.ini")

    assert ai_config["model_name"] == "gemini-3.7-flash"
    assert ai_config["project_id"] == "test-proj"
    assert ai_config["thinking_level"] == "medium"


@unittest.mock.patch("backend.scripts.generate_summary.os.path.exists", autospec=True)
@unittest.mock.patch("builtins.open", new_callable=unittest.mock.mock_open, read_data="""
[gemini]
GEMINI_API_KEY = "test-key"
""")
def test_configure_environment_missing_model(
    _mock_open: unittest.mock.MagicMock,
    mock_exists: unittest.mock.MagicMock
) -> None:
    """Verify configure_environment raises ValueError when GEMINI_MODEL is absent."""
    mock_exists.return_value = True
    import pytest  # pylint: disable=import-outside-toplevel
    with pytest.raises(ValueError, match="GEMINI_MODEL must be explicitly defined"):
        backend.scripts.generate_summary.configure_environment("/fake/config.ini")
