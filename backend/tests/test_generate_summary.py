"""Unit tests for generate_summary.py."""

import json
import os
from unittest import mock

import pytest
from vertexai.generative_models import Content

from backend.scripts import generate_summary

def test_parse_photos_json():
    """Test parsing of photos JSON string."""
    assert generate_summary._parse_photos_json('["http://example.com/1.jpg", "http://example.com/2.jpg"]') == ["http://example.com/1.jpg", "http://example.com/2.jpg"]
    assert generate_summary._parse_photos_json('[{"url": "http://example.com/1.jpg"}, {"other": "value"}]') == ["http://example.com/1.jpg"]
    assert generate_summary._parse_photos_json('') == []
    assert generate_summary._parse_photos_json('invalid json') == []

def test_construct_new_data():
    """Test constructing the final prompt string."""
    scores = [("player1", 100), ("player2", 50)]
    logs = ["Log 1 data", "Log 2 data"]
    result = generate_summary.construct_new_data(scores, logs)
    
    assert "Winner: player1 with 100 points" in result
    assert "- player2: 50 points" in result
    assert "Log 1 data\n\nLog 2 data" in result
    
    # Test empty scores
    result_empty = generate_summary.construct_new_data([], logs)
    assert "No players scored in this game." in result_empty

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
    assert isinstance(history[0], Content)
    assert history[0].role == "user"
    assert history[1].role == "model"
    assert history[2].role == "user"
    assert history[3].role == "model"

@mock.patch("builtins.open", new_callable=mock.mock_open)
def test_write_summary_files(mock_file):
    """Test writing the prompt and html to files."""
    generate_summary.write_summary_files("/out", 123, "my prompt", "my html")
    
    # Open should be called twice
    assert mock_file.call_count == 2
    mock_file.assert_any_call("/out/game_123_input.txt", 'w', encoding='utf-8')
    mock_file.assert_any_call("/out/game_123_output.html", 'w', encoding='utf-8')
    
    # Write should be called with "my prompt" and "my html"
    handle = mock_file()
    handle.write.assert_any_call("my prompt")
    handle.write.assert_any_call("my html")

@mock.patch("backend.scripts.generate_summary.vertexai")
@mock.patch("backend.scripts.generate_summary.GenerativeModel")
def test_generate_vertex_summary(mock_generative_model, mock_vertexai):
    """Test vertex API call structure."""
    mock_model_instance = mock.MagicMock()
    mock_chat_instance = mock.MagicMock()
    mock_response = mock.MagicMock()
    mock_response.text = "generated HTML"
    
    mock_generative_model.return_value = mock_model_instance
    mock_model_instance.start_chat.return_value = mock_chat_instance
    mock_chat_instance.send_message.return_value = mock_response
    
    config = {"project_id": "p1", "region": "r1", "model_name": "m1"}
    result = generate_summary._generate_vertex_summary(config, ["sys inst"], [], "my prompt")
    
    assert result == "generated HTML"
    mock_vertexai.init.assert_called_once_with(project="p1", location="r1")
    mock_generative_model.assert_called_once_with("m1", system_instruction=["sys inst"])
    mock_model_instance.start_chat.assert_called_once_with(history=[])
    mock_chat_instance.send_message.assert_called_once_with("my prompt")
