"""Unit tests for generate_summary.py."""

import json
import os
from unittest import mock

import pytest
from google.genai import types

from backend.scripts import generate_summary

def test_parse_photos_json():
    """Test parsing of photos JSON string."""
    assert generate_summary._parse_photos_json('["http://example.com/1.jpg"]') == [{"url": "http://example.com/1.jpg"}]
    assert generate_summary._parse_photos_json('[{"url": "http://example.com/1.jpg"}]') == [{"url": "http://example.com/1.jpg", "thumb_url": None}]
    assert generate_summary._parse_photos_json('') == []
    assert generate_summary._parse_photos_json('invalid json') == []

@mock.patch("backend.scripts.generate_summary.urllib.request.urlopen")
def test_construct_new_data(mock_urlopen):
    """Test constructing the final prompt string."""
    scores = [("player1", 100), ("player2", 50)]
    logs = [{
        'dp_id': 123,
        'username': 'testuser',
        'city': 'TestCity',
        'photos': [{'url': 'http://example.com/1.jpg'}],
        'notes': 'Log notes'
    }]
    
    mock_response = mock.MagicMock()
    mock_response.read.return_value = b"fake image"
    mock_response.headers.get_content_type.return_value = "image/jpeg"
    
    mock_urlopen_context = mock.MagicMock()
    mock_urlopen_context.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_urlopen_context

    game_title = "Test Game Title"
    result = generate_summary.construct_new_data(game_title, scores, logs)
    
    text_result = "".join([p for p in result if isinstance(p, str)])
    
    assert "Test Game Title" in text_result
    assert "Winner: player1 with 100 points" in text_result
    assert "- player2: 50 points" in text_result
    assert "Log: 123.txt" in text_result
    assert "Log notes" in text_result
    assert "Full: http://example.com/1.jpg" in text_result
    
    # Test empty scores
    result_empty = generate_summary.construct_new_data(game_title, [], logs)
    text_empty = "".join([p for p in result_empty if isinstance(p, str)])
    assert "No players scored in this game." in text_empty

@mock.patch("backend.scripts.generate_summary.os.path.isdir")
@mock.patch("backend.scripts.generate_summary.os.listdir")
@mock.patch("backend.scripts.generate_summary.os.path.exists")
@mock.patch("builtins.open", new_callable=mock.mock_open, read_data="mock data")
def test_load_chat_history(mock_open, mock_exists, mock_listdir, mock_isdir):
    """Test loading chat history from directory."""
    mock_isdir.return_value = True
    mock_listdir.return_value = ['example_1_input.txt', 'example_2_input.txt', 'other.txt']
    mock_exists.return_value = True
    
    history = generate_summary.load_chat_history("/fake/dir")
    
    assert len(history) == 4
    assert isinstance(history[0], types.Content)
    assert history[0].role == "user"
    assert history[1].role == "model"
    assert history[2].role == "user"
    assert history[3].role == "model"

@mock.patch("builtins.open", new_callable=mock.mock_open)
def test_write_summary_files(mock_file):
    """Test writing the prompt and html to files."""
    # We pass a mixed list simulating text and image parts
    fake_part = mock.MagicMock()
    fake_part.__class__ = generate_summary.types.Part
    
    generate_summary.write_summary_files("/out", 123, ["my prompt", fake_part], "my html")
    
    # Open should be called twice
    assert mock_file.call_count == 2
    mock_file.assert_any_call("/out/game_123_input.txt", 'w', encoding='utf-8')
    mock_file.assert_any_call("/out/game_123_output.html", 'w', encoding='utf-8')
    
    # Write should be called with constructed string and html
    handle = mock_file()
    handle.write.assert_any_call("my prompt[IMAGE DATA DETACHED]\n")
    handle.write.assert_any_call("my html")

@mock.patch("backend.scripts.generate_summary.genai.Client")
@mock.patch("backend.scripts.generate_summary.types.GenerateContentConfig")
def test_generate_vertex_summary(mock_generate_content_config, mock_client_class):
    """Test vertex API call structure."""
    mock_client_instance = mock.MagicMock()
    mock_chat_instance = mock.MagicMock()
    mock_response = mock.MagicMock()
    mock_response.text = "generated HTML"
    
    mock_client_class.return_value = mock_client_instance
    mock_client_instance.chats.create.return_value = mock_chat_instance
    mock_chat_instance.send_message.return_value = mock_response
    
    mock_config_instance = mock.MagicMock()
    mock_generate_content_config.return_value = mock_config_instance
    
    config = {"project_id": "p1", "region": "r1", "model_name": "m1"}
    result = generate_summary._generate_vertex_summary(config, "sys inst", [], "my prompt")
    
    assert result == "generated HTML"
    mock_client_class.assert_called_once_with(vertexai=True, project="p1", location="r1")
    mock_generate_content_config.assert_called_once_with(system_instruction="sys inst")
    mock_client_instance.chats.create.assert_called_once_with(model="m1", config=mock_config_instance, history=[])
    mock_chat_instance.send_message.assert_called_once_with("my prompt")
