"""Script to generate a game summary using Gemini via Vertex AI."""

import argparse
import configparser
import json
import os
import sys
import urllib.request
import urllib.error

import mysql.connector
from google import genai
from google.genai import types

def get_db_connection(config_path: str) -> mysql.connector.connection.MySQLConnection:
    """Establishes a connection to the MySQL database securely via config.ini."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Database config not found at {config_path}")

    config = configparser.ConfigParser()
    config.read(config_path)

    host = config['database'].get('DB_HOST', '127.0.0.1').strip('"\'')
    port = config['database'].get('DB_PORT', '3306').strip('"\'')
    user = config['database'].get('DB_USER', 'geodashing').strip('"\'')
    password = config['database'].get('DB_PASS', '').strip('"\'')
    database = config['database'].get('DB_NAME', 'geodashing').strip('"\'')

    return mysql.connector.connect(
        host=host,
        user=user,
        password=password,
        database=database,
        port=port
    )

def configure_environment(config_path: str) -> dict:
    """Configures environment variables and Vertex AI parameters."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config not found at {config_path}")

    config = configparser.ConfigParser()
    config.read(config_path)

    if 'mail' in config and 'GOOGLE_APPLICATION_CREDENTIALS' in config['mail']:
        creds_path = config['mail']['GOOGLE_APPLICATION_CREDENTIALS'].strip('"\'')
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = creds_path

    model_name = "gemini-2.5-pro"
    region = "us-central1"
    project_id = None

    if 'vertexai' in config:
        model_name = config['vertexai'].get('VERTEX_AI_MODEL', model_name).strip('"\'')
        region = config['vertexai'].get('VERTEX_AI_REGION', region).strip('"\'')
        project_id = config['vertexai'].get('VERTEX_AI_PROJECT', project_id)
        if project_id is not None:
            project_id = project_id.strip('"\'')

    return {"model_name": model_name, "region": region, "project_id": project_id}

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
                if isinstance(item, dict):
                    photos.append({
                        'thumb_url': item.get('thumb_url'),
                        'url': item.get('url')
                    })
                elif isinstance(item, str):
                    photos.append({'url': item})
        except json.JSONDecodeError:
            pass
    return photos

def _extract_logs(cursor, game_id: int) -> list:
    """Extracts all approved logs for the game."""
    logs_query = """
        SELECT v.dashpoint_id, u.username, ST_X(d.location) as dp_lat, ST_Y(d.location) as dp_lon, v.notes, v.photos
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
    """Loads few-shot examples into Vertex AI Chat History."""
    history = []
    if not os.path.isdir(examples_dir):
        return history

    example_prefixes = []
    for filename in os.listdir(examples_dir):
        if filename.endswith('_input.txt'):
            example_prefixes.append(filename.replace('_input.txt', ''))

    # Sort to ensure consistent chat history order
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

def _append_photo_parts(parts: list, photos: list) -> None:
    """Appends photo text and image parts to the prompt parts list."""
    if not photos:
        parts.append("Photos: None\n\n")
        return

    parts.append("Photos:\n")
    for photo in photos:
        full_url = photo.get('url')
        thumb_url = photo.get('thumb_url')
        if full_url and thumb_url:
            parts.append(f"Thumb: {thumb_url} | Full: {full_url}\nImage Content:\n")
        elif thumb_url:
            parts.append(f"Thumb: {thumb_url}\nImage Content:\n")
        elif full_url:
            parts.append(f"Full: {full_url}\nImage Content:\n")
        download_url = full_url or thumb_url
        if download_url:
            if download_url.startswith("https://storage.googleapis.com/"):
                gs_uri = download_url.replace("https://storage.googleapis.com/", "gs://")
                ext = gs_uri.split('.')[-1].lower()
                mime_type = "image/jpeg"
                if ext == "png":
                    mime_type = "image/png"
                elif ext == "webp":
                    mime_type = "image/webp"
                parts.append(types.Part.from_uri(file_uri=gs_uri, mime_type=mime_type))
                parts.append("\n")
            else:
                try:
                    req = urllib.request.Request(
                        download_url, headers={'User-Agent': 'Mozilla/5.0'}
                    )
                    with urllib.request.urlopen(req, timeout=10) as response:
                        image_bytes = response.read()
                        mime_type = response.headers.get_content_type()
                        valid_mimes = ["image/jpeg", "image/png", "image/webp",
                                       "image/heic", "image/heif"]
                        if mime_type not in valid_mimes:
                            mime_type = "image/jpeg"
                        parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))
                        parts.append("\n")
                except urllib.error.URLError as err:
                    print(f"Failed to fetch image {download_url}: {err}", file=sys.stderr)
                    parts.append("(Image could not be downloaded)\n")
    parts.append("\n")

def construct_new_data(game_title: str, scores: list, formatted_logs: list) -> list:
    """Constructs the final input prompt parts with game title, scores, logs, and images."""
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
        dp_id = log['dp_id']
        username = log['username']
        city = log['city']
        notes = log['notes'] or ''

        log_header = (
            "---------------------\n"
            f"Log: {dp_id}.txt\n"
            "---------------------\n"
            f"Player: {username}\n\n"
            f"{dp_id} is near {city}.\n\n"
        )
        parts.append(log_header)

        _append_photo_parts(parts, log['photos'])

        parts.append(f"{notes}\n\n")

    return parts

def _generate_vertex_summary(ai_config: dict, sys_inst: str,
                             history: list, prompt: list) -> str:
    """Initializes Vertex AI and generates the summary from the prompt parts."""
    client = genai.Client(vertexai=True, project=ai_config['project_id'], location=ai_config['region'])
    config = types.GenerateContentConfig(
        system_instruction=sys_inst,
    )
    chat = client.chats.create(model=ai_config['model_name'], config=config, history=history)
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
            elif isinstance(p, types.Part):
                text_prompt += "[IMAGE DATA DETACHED]\n"
        f.write(text_prompt)

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(summary_html)

    print("Summary generated successfully.")
    print(f"Input file: {in_path}")
    print(f"Output file: {out_path}")

def run_summary_generation(args: argparse.Namespace, config_path: str,
                           instructions_path: str, examples_dir: str) -> None:
    """Orchestrates the data extraction and AI generation process."""
    ai_config = configure_environment(config_path)

    conn = get_db_connection(config_path)
    cursor = conn.cursor()
    game_title, scores, formatted_logs = extract_logs_and_scores(cursor, args.game_id)
    cursor.close()
    conn.close()

    sys_inst = load_system_instructions(instructions_path)
    history = load_chat_history(examples_dir)
    prompt = construct_new_data(game_title, scores, formatted_logs)

    summary_html = _generate_vertex_summary(ai_config, sys_inst, history, prompt)

    write_summary_files(args.output_dir, args.game_id, prompt, summary_html)

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
