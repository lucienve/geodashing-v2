"""Script to generate a game summary using Gemini via Google AI Studio."""

import argparse
import configparser
import json
import os
import sys
import tempfile
import urllib.request
import urllib.error

import mysql.connector
import google.auth
import google.auth.exceptions
from google import genai
from google.genai import types

from backend.scripts.db_utils import get_db_connection


def configure_environment(config_path: str) -> dict:
    """Configures environment variables and Gemini AI parameters."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config not found at {config_path}")

    config = configparser.ConfigParser()
    config.read(config_path)

    if 'mail' in config and 'GOOGLE_APPLICATION_CREDENTIALS' in config['mail']:
        creds_path = config['mail']['GOOGLE_APPLICATION_CREDENTIALS'].strip('"\'')
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = creds_path

    model_name = "gemini-3.5-pro"
    project_id = None

    # Support loading API key, model, and project ID from config.ini
    if 'gemini' in config:
        model_name = config['gemini'].get('GEMINI_MODEL', model_name).strip('"\'')
        api_key = config['gemini'].get('GEMINI_API_KEY')
        if api_key:
            os.environ['GEMINI_API_KEY'] = api_key.strip('"\'')
        project_id = config['gemini'].get('GEMINI_PROJECT_ID')
        if project_id:
            project_id = project_id.strip('"\'')

    return {"model_name": model_name, "project_id": project_id}


def get_gemini_client(ai_config: dict) -> genai.Client:
    """Builds a GenAI client using project billing credentials."""
    project_id = ai_config.get('project_id')
    try:
        creds, default_project = google.auth.default()
        target_project = project_id or default_project
        if target_project and hasattr(creds, 'with_quota_project'):
            creds = creds.with_quota_project(target_project)
    except google.auth.exceptions.DefaultCredentialsError:
        creds = None
        target_project = project_id

    return genai.Client(
        vertexai=False,
        project=target_project,
        credentials=creds
    )


def download_file_to_temp(url: str) -> str:
    """Downloads a file via HTTP to a local temporary file."""
    try:
        req = urllib.request.Request(
            url, headers={'User-Agent': 'Mozilla/5.0'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            image_bytes = response.read()

        ext = url.split('.')[-1].lower().split('?')[0] if '.' in url else 'jpg'
        if ext not in ['jpg', 'jpeg', 'png', 'webp', 'heic', 'heif']:
            ext = 'jpg'

        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as temp_file:
            temp_file.write(image_bytes)
            return temp_file.name
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        print(f"Failed to download image {url}: {err}", file=sys.stderr)
        return None


def get_nearest_city(cursor, lat: float, lon: float) -> str:
    """Finds the nearest major city to the given coordinates."""
    query = """
        SELECT name, admin_name, country_name
        FROM major_cities
        ORDER BY ST_Distance_Sphere(location, ST_GeomFromText(%s, 4326)) ASC
        LIMIT 1
    """
    wkt = f"POINT({lat} {lon})"
    cursor.execute(query, (wkt,))
    row = cursor.fetchone()
    if row:
        name, admin_name, country_name = row
        parts = [p for p in [name, admin_name, country_name] if p]
        return ", ".join(parts)
    return "Unknown Location"


def _extract_scores(cursor, game_id: int) -> list:
    """Extracts scores strictly constrained to the game."""
    score_query = """
        SELECT u.username, SUM(v.score_awarded) as total_points
        FROM visits v
        JOIN users u ON v.user_id = u.id
        JOIN dashpoints d ON v.dashpoint_id = d.id
        WHERE d.game_id = %s
        GROUP BY u.username
        ORDER BY total_points DESC, u.username ASC
    """
    cursor.execute(score_query, (game_id,))
    return cursor.fetchall()


def _parse_photos_json(photos_json: str) -> list:
    """Parses the photos JSON string into a list of photo dictionaries."""
    photos = []
    if photos_json:
        try:
            photos_data = json.loads(photos_json)
            for item in photos_data:
                if isinstance(item, dict) and 'url' in item and 'thumb_url' in item:
                    photos.append({
                        'thumb_url': item['thumb_url'],
                        'url': item['url']
                    })
        except json.JSONDecodeError:
            pass
    return photos


def _extract_logs(cursor, game_id: int) -> list:
    """Extracts all approved logs for the game."""
    logs_query = """
        SELECT v.dashpoint_id, u.username, ST_Latitude(d.location) as dp_lat,
               ST_Longitude(d.location) as dp_lon, v.notes, v.photos
        FROM visits v
        JOIN users u ON v.user_id = u.id
        JOIN dashpoints d ON v.dashpoint_id = d.id
        WHERE d.game_id = %s AND v.status = 'approved'
        ORDER BY v.reported_time ASC
    """
    cursor.execute(logs_query, (game_id,))
    raw_logs = cursor.fetchall()

    formatted_logs = []
    for dp_id, username, dp_lat, dp_lon, notes, photos_json in raw_logs:
        city = get_nearest_city(cursor, dp_lat, dp_lon)
        photos = _parse_photos_json(photos_json)
        formatted_logs.append({
            'dp_id': dp_id,
            'username': username,
            'city': city,
            'photos': photos,
            'notes': notes
        })

    return formatted_logs


def extract_logs_and_scores(cursor, game_id: int) -> tuple:
    """Extracts the game title, scores, and all approved logs."""
    cursor.execute("SELECT title FROM games WHERE id = %s", (game_id,))
    row = cursor.fetchone()
    game_title = row[0] if row else f"Game {game_id}"

    scores = _extract_scores(cursor, game_id)
    formatted_logs = _extract_logs(cursor, game_id)
    return game_title, scores, formatted_logs


def load_system_instructions(instructions_path: str) -> str:
    """Loads system instructions from a text file."""
    with open(instructions_path, 'r', encoding='utf-8') as f:
        return f.read().strip()


def load_chat_history(examples_dir: str) -> list:
    """Loads few-shot examples into AI Studio Chat History."""
    history = []
    if not os.path.isdir(examples_dir):
        return history

    example_prefixes = []
    for filename in os.listdir(examples_dir):
        if filename.endswith('_input.txt'):
            example_prefixes.append(filename.replace('_input.txt', ''))

    example_prefixes.sort()

    for prefix in example_prefixes:
        in_path = os.path.join(examples_dir, f'{prefix}_input.txt')
        out_path = os.path.join(examples_dir, f'{prefix}_output.html')
        if os.path.exists(in_path) and os.path.exists(out_path):
            with open(in_path, 'r', encoding='utf-8') as f:
                in_text = f.read().strip()
            with open(out_path, 'r', encoding='utf-8') as f:
                out_text = f.read().strip()
            history.append(types.Content(role="user", parts=[types.Part.from_text(text=in_text)]))
            history.append(types.Content(role="model", parts=[types.Part.from_text(text=out_text)]))
    return history


def _append_photo_parts(parts: list, photos: list, upload_context: dict) -> None:
    """Appends photo text and uploaded AI files to the prompt parts list."""
    if not photos:
        parts.append("Photos: None\n\n")
        return

    client = upload_context["client"]
    parts.append("Photos:\n")
    for photo in photos:
        full_url = photo['url']
        thumb_url = photo['thumb_url']
        parts.append(f"Thumb: {thumb_url} | Full: {full_url}\nImage Content:\n")

        local_path = download_file_to_temp(full_url)
        if local_path:
            upload_context["local_temp_files"].append(local_path)
            try:
                uploaded_file = client.files.upload(file=local_path)
                upload_context["uploaded_ai_files"].append(uploaded_file)
                parts.append(uploaded_file)
                parts.append("\n")
            except Exception as err:  # pylint: disable=broad-exception-caught
                print(f"Failed to upload image {full_url} to AI Studio: {err}", file=sys.stderr)
                parts.append("(Image could not be processed)\n")
        else:
            parts.append("(Image could not be downloaded)\n")
    parts.append("\n")


def _format_log_entry(log: dict, upload_context: dict) -> list:
    """Formats a single player log entry list of prompt parts."""
    dp_id = log['dp_id']
    username = log['username']
    city = log['city']
    notes = log['notes'] or ''

    entry_parts = []
    log_header = (
        "---------------------\n"
        f"Log: {dp_id}.txt\n"
        "---------------------\n"
        f"Player: {username}\n\n"
        f"{dp_id} is near {city}.\n\n"
    )
    entry_parts.append(log_header)
    _append_photo_parts(entry_parts, log['photos'], upload_context)
    entry_parts.append(f"{notes}\n\n")
    return entry_parts


def construct_new_data(game_title: str, scores: list, formatted_logs: list,
                       upload_context: dict) -> list:
    """Constructs the final input prompt parts with game title, scores, and logs."""
    if not scores:
        score_text = "No players scored in this game."
    else:
        winner = scores[0]
        score_text = f"Winner: {winner[0]} with {winner[1]} points.\n\nOther Players:\n"
        for user, points in scores[1:]:
            score_text += f"- {user}: {points} points\n"

    parts = []
    initial_text = (
        "[NEW INPUT DATA SET]\n\n"
        f"--- GAME TITLE ---\n{game_title}\n\n"
        f"--- SCORE RANKINGS ---\n{score_text}\n\n"
        "--- PLAYER LOGS ---\n"
    )
    parts.append(initial_text)

    for log in formatted_logs:
        parts.extend(_format_log_entry(log, upload_context))

    return parts


def _generate_summary(client: genai.Client, model_name: str, instructions_path: str,
                      examples_dir: str, prompt: list) -> str:
    """Generates the summary using the initialized client and prompt."""
    sys_inst = load_system_instructions(instructions_path)
    history = load_chat_history(examples_dir)
    config = types.GenerateContentConfig(
        system_instruction=sys_inst,
    )
    chat = client.chats.create(model=model_name, config=config, history=history)
    response = chat.send_message(prompt)
    return response.text


def write_summary_files(output_dir: str, game_id: int, prompt: list, summary_html: str) -> None:
    """Writes the generated summary and input prompt to files."""
    in_path = os.path.join(output_dir, f"game_{game_id}_input.txt")
    out_path = os.path.join(output_dir, f"game_{game_id}_output.html")

    with open(in_path, 'w', encoding='utf-8') as f:
        text_prompt = ""
        for p in prompt:
            if isinstance(p, str):
                text_prompt += p
            else:
                text_prompt += "[IMAGE DATA DETACHED]\n"
        f.write(text_prompt)

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(summary_html)

    print("Summary generated successfully.")
    print(f"Input file: {in_path}")
    print(f"Output file: {out_path}")


def _get_game_data(config_path: str, game_id: int) -> tuple:
    """Extracts game title, scores, and formatted logs from the database."""
    conn = get_db_connection(config_path)
    cursor = conn.cursor()
    try:
        return extract_logs_and_scores(cursor, game_id)
    finally:
        cursor.close()
        conn.close()


def run_summary_generation(args: argparse.Namespace, config_path: str,
                           instructions_path: str, examples_dir: str) -> None:
    """Orchestrates the data extraction, AI upload, and generation process."""
    ai_config = configure_environment(config_path)
    game_title, scores, formatted_logs = _get_game_data(config_path, args.game_id)

    client = get_gemini_client(ai_config)

    upload_context = {
        "client": client,
        "local_temp_files": [],
        "uploaded_ai_files": []
    }

    try:
        prompt = construct_new_data(game_title, scores, formatted_logs, upload_context)
        summary_html = _generate_summary(
            client, ai_config['model_name'], instructions_path, examples_dir, prompt
        )
        write_summary_files(args.output_dir, args.game_id, prompt, summary_html)

    finally:
        # A. Clean up local temporary files
        for local_file in upload_context["local_temp_files"]:
            try:
                if os.path.exists(local_file):
                    os.unlink(local_file)
            except OSError as e:
                print(f"Failed to delete local temp file {local_file}: {e}", file=sys.stderr)

        # B. Clean up uploaded remote AI Studio files
        for uploaded_file in upload_context["uploaded_ai_files"]:
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception as e:  # pylint: disable=broad-exception-caught
                print(
                    f"Failed to delete remote AI Studio file {uploaded_file.name}: {e}",
                    file=sys.stderr
                )


def main() -> None:
    """Main execution point for the summary script."""
    parser = argparse.ArgumentParser(description="Geodashing Game Summary Generator")
    parser.add_argument('--game_id', type=int, required=True,
                        help="ID of the game to summarize.")
    parser.add_argument('--output_dir', type=str, required=True,
                        help="Directory to save the input and output files.")
    args = parser.parse_args()

    if not os.path.isdir(args.output_dir):
        print(f"Error: Output directory not found: {args.output_dir}", file=sys.stderr)
        sys.exit(1)

    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, '../config.ini')
    instructions_path = os.path.join(current_dir, '../../data/summary_system_instructions.txt')
    examples_dir = os.path.join(current_dir, '../../data/summary_examples/')

    try:
        run_summary_generation(args, config_path, instructions_path, examples_dir)
    except (FileNotFoundError, ValueError, mysql.connector.Error) as specific_err:
        print(f"Configuration or Database Error: {specific_err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
