"""Script to generate a game summary using Gemini via Google AI Studio."""

import argparse
import configparser
import json
import os
import sys
import tempfile
import typing
import urllib.request
import urllib.error

import mysql.connector
import mysql.connector.cursor
import google.auth
import google.auth.exceptions
import google.genai
import google.genai.types

import backend.scripts.db_utils


class LogEntry(typing.TypedDict):
    """Represents a structured player dashpoint log entry."""
    dp_id: str
    username: str
    city: str
    photos: list[dict[str, str]]
    notes: str | None


class TextContentDict(typing.TypedDict):
    """Represents a text content block in an Interaction step."""
    type: typing.Literal["text"]
    text: str


class ImageContentDict(typing.TypedDict):
    """Represents an image content block with a URI reference in an Interaction step."""
    type: typing.Literal["image"]
    uri: str
    mime_type: str


ContentItem = TextContentDict | ImageContentDict


class UserInputStepDict(typing.TypedDict):
    """Represents a user input step in the interaction timeline."""
    type: typing.Literal["user_input"]
    content: list[ContentItem]


class ModelOutputStepDict(typing.TypedDict):
    """Represents a model output step in the interaction timeline."""
    type: typing.Literal["model_output"]
    content: list[TextContentDict]


InteractionStep = UserInputStepDict | ModelOutputStepDict


class GenerationConfigDict(typing.TypedDict, total=False):
    """Configuration options for model generation in Interactions API."""
    thinking_level: str
    max_output_tokens: int
    seed: int
    stop_sequences: list[str]


class UploadContext(typing.TypedDict):
    """Context container for local and uploaded GenAI files."""
    client: google.genai.Client
    local_temp_files: list[str]
    uploaded_ai_files: list[google.genai.types.File]


def configure_environment(config_path: str) -> dict[str, str | None]:
    """Configures environment variables and Gemini AI parameters."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config not found at {config_path}")

    config = configparser.ConfigParser()
    config.read(config_path)

    if 'mail' in config and 'GOOGLE_APPLICATION_CREDENTIALS' in config['mail']:
        creds_path = config['mail']['GOOGLE_APPLICATION_CREDENTIALS'].strip(
            '"\'')
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = creds_path

    model_name = None
    project_id = None
    thinking_level = None
    api_key = None

    # Support loading API key, model, project ID, and thinking level from config.ini
    if 'gemini' in config:
        model_name = config['gemini'].get('GEMINI_MODEL')
        if model_name:
            model_name = model_name.strip('"\'')
        api_key = config['gemini'].get('GEMINI_API_KEY')
        if api_key:
            api_key = api_key.strip('"\'')
            os.environ['GEMINI_API_KEY'] = api_key
        project_id = config['gemini'].get('GEMINI_PROJECT_ID')
        if project_id:
            project_id = project_id.strip('"\'')
        thinking_level = config['gemini'].get('GEMINI_THINKING_LEVEL')
        if thinking_level:
            thinking_level = thinking_level.strip('"\'')

    if not model_name:
        raise ValueError(
            "GEMINI_MODEL must be explicitly defined under the [gemini] section "
            "of config.ini.")

    return {
        "model_name": model_name,
        "project_id": project_id,
        "thinking_level": thinking_level,
        "api_key": api_key
    }


def get_gemini_client(ai_config: dict[str, str | None]) -> google.genai.Client:
    """Builds a GenAI client using API key or project billing credentials."""
    api_key = ai_config.get('api_key') or os.environ.get('GEMINI_API_KEY')
    if api_key:
        return google.genai.Client(vertexai=False, api_key=api_key)

    project_id = ai_config.get('project_id')
    try:
        creds, default_project = google.auth.default()
        target_project = project_id or default_project
        if target_project and hasattr(creds, 'with_quota_project'):
            creds = creds.with_quota_project(target_project)
    except google.auth.exceptions.DefaultCredentialsError:
        creds = None

    return google.genai.Client(vertexai=False, credentials=creds)


def download_file_to_temp(url: str) -> str | None:
    """Downloads a file via HTTP to a local temporary file."""
    try:
        req = urllib.request.Request(url,
                                     headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            image_bytes = response.read()

        ext = url.split('.')[-1].lower().split('?')[0] if '.' in url else 'jpg'
        if ext not in ['jpg', 'jpeg', 'png', 'webp', 'heic', 'heif']:
            ext = 'jpg'

        with tempfile.NamedTemporaryFile(suffix=f".{ext}",
                                         delete=False) as temp_file:
            temp_file.write(image_bytes)
            return temp_file.name
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        print(f"Failed to download image {url}: {err}", file=sys.stderr)
        return None


def get_nearest_city(cursor: mysql.connector.cursor.MySQLCursor, lat: float,
                     lon: float) -> str:
    """Finds the nearest major city to the given coordinates."""
    query = """
        SELECT name, admin_name, country_name
        FROM major_cities
        ORDER BY ST_Distance_Sphere(location, ST_GeomFromText(%s, 4326)) ASC
        LIMIT 1
    """
    wkt = f"POINT({lat} {lon})"
    cursor.execute(query, (wkt, ))
    row = typing.cast(tuple[str | None, str | None, str | None] | None,
                      cursor.fetchone())
    if row:
        name, admin_name, country_name = row
        parts = [p for p in [name, admin_name, country_name] if p]
        return ", ".join(parts)
    return "Unknown Location"


def _extract_scores(cursor: mysql.connector.cursor.MySQLCursor,
                    game_id: int) -> list[tuple[str, int]]:
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
    cursor.execute(score_query, (game_id, ))
    rows = cursor.fetchall()
    return [(str(r[0]),
             int(typing.cast(typing.Any, r[1])) if r[1] is not None else 0)
            for r in rows]


def _parse_photos_json(photos_json: str | None) -> list[dict[str, str]]:
    """Parses the photos JSON string into a list of photo dictionaries."""
    photos: list[dict[str, str]] = []
    if photos_json:
        try:
            photos_data = json.loads(photos_json)
            for item in photos_data:
                if isinstance(item,
                              dict) and 'url' in item and 'thumb_url' in item:
                    photo_dict = {
                        'thumb_url': item['thumb_url'],
                        'url': item['url']
                    }
                    if 'caption' in item and isinstance(item['caption'], str):
                        photo_dict['caption'] = item['caption']
                    photos.append(photo_dict)
        except json.JSONDecodeError:
            pass
    return photos


def _extract_logs(cursor: mysql.connector.cursor.MySQLCursor,
                  game_id: int) -> list[LogEntry]:
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
    cursor.execute(logs_query, (game_id, ))
    raw_logs = typing.cast(
        list[tuple[str, str, float, float, str | None, str | None]],
        cursor.fetchall())

    formatted_logs: list[LogEntry] = []
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


def extract_logs_and_scores(
        cursor: mysql.connector.cursor.MySQLCursor,
        game_id: int) -> tuple[str, list[tuple[str, int]], list[LogEntry]]:
    """Extracts the game title, scores, and all approved logs."""
    cursor.execute("SELECT title FROM games WHERE id = %s", (game_id, ))
    row = typing.cast(tuple[str] | None, cursor.fetchone())
    game_title = row[0] if row else f"Game {game_id}"

    scores = _extract_scores(cursor, game_id)
    formatted_logs = _extract_logs(cursor, game_id)
    return game_title, scores, formatted_logs


def load_system_instructions(instructions_path: str) -> str:
    """Loads system instructions from a text file."""
    with open(instructions_path, 'r', encoding='utf-8') as f:
        return f.read().strip()


def load_chat_history(examples_dir: str) -> list[InteractionStep]:
    """Loads few-shot examples into Step dictionaries for Interactions API."""
    steps: list[InteractionStep] = []
    if not os.path.isdir(examples_dir):
        return steps

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
            steps.append({
                "type": "user_input",
                "content": [{
                    "type": "text",
                    "text": in_text
                }]
            })
            steps.append({
                "type": "model_output",
                "content": [{
                    "type": "text",
                    "text": out_text
                }]
            })
    return steps


def _append_photo_parts(parts: list[ContentItem], photos: list[dict[str, str]],
                        upload_context: UploadContext) -> None:
    """Appends photo text and uploaded AI files to the prompt parts list."""
    if not photos:
        parts.append({"type": "text", "text": "Photos: None\n\n"})
        return

    client = upload_context["client"]
    parts.append({"type": "text", "text": "Photos:\n"})
    for photo in photos:
        full_url = photo['url']
        thumb_url = photo['thumb_url']
        caption = photo.get('caption')
        if caption:
            parts.append({
                "type":
                "text",
                "text": (f"Thumb: {thumb_url} | Full: {full_url}\n"
                         f"Caption: {caption}\n"
                         "Image Content:\n")
            })
        else:
            parts.append({
                "type":
                "text",
                "text": (f"Thumb: {thumb_url} | Full: {full_url}\n"
                         "Image Content:\n")
            })

        local_path = download_file_to_temp(full_url)
        if local_path:
            upload_context["local_temp_files"].append(local_path)
            try:
                uploaded_file = client.files.upload(file=local_path)
                upload_context["uploaded_ai_files"].append(uploaded_file)
                parts.append({
                    "type":
                    "image",
                    "uri":
                    uploaded_file.uri or "",
                    "mime_type":
                    uploaded_file.mime_type or "image/jpeg"
                })
                parts.append({"type": "text", "text": "\n"})
            except Exception as err:  # pylint: disable=broad-exception-caught
                print(f"Failed to upload image {full_url} to AI Studio: {err}",
                      file=sys.stderr)
                parts.append({
                    "type": "text",
                    "text": "(Image could not be processed)\n"
                })
        else:
            parts.append({
                "type": "text",
                "text": "(Image could not be downloaded)\n"
            })
    parts.append({"type": "text", "text": "\n"})


def _format_log_entry(log: LogEntry,
                      upload_context: UploadContext) -> list[ContentItem]:
    """Formats a single player log entry list of prompt parts."""
    dp_id = log['dp_id']
    username = log['username']
    city = log['city']
    notes = log['notes'] or ''

    entry_parts: list[ContentItem] = []
    log_header = ("---------------------\n"
                  f"Log: {dp_id}.txt\n"
                  "---------------------\n"
                  f"Player: {username}\n\n"
                  f"{dp_id} is near {city}.\n\n")
    entry_parts.append({"type": "text", "text": log_header})
    _append_photo_parts(entry_parts, log['photos'], upload_context)
    entry_parts.append({"type": "text", "text": f"{notes}\n\n"})
    return entry_parts


def construct_new_data(game_title: str, scores: list[tuple[str, int]],
                       formatted_logs: list[LogEntry],
                       upload_context: UploadContext) -> list[ContentItem]:
    """Constructs the final input prompt parts with game title, scores, and logs."""
    if not scores:
        score_text = "No players scored in this game."
    else:
        max_score = scores[0][1]
        winners = [s for s in scores if s[1] == max_score]
        other_players = [s for s in scores if s[1] < max_score]

        if len(winners) > 1:
            winner_names = ", ".join(w[0] for w in winners)
            score_text = f"Winners (tied): {winner_names} with {max_score} points.\n\n"
        else:
            score_text = f"Winner: {winners[0][0]} with {max_score} points.\n\n"

        if other_players:
            score_text += "Other Players:\n"
            for user, points in other_players:
                score_text += f"- {user}: {points} points\n"

    parts: list[ContentItem] = []
    initial_text = ("[NEW INPUT DATA SET]\n\n"
                    f"--- GAME TITLE ---\n{game_title}\n\n"
                    f"--- SCORE RANKINGS ---\n{score_text}\n\n"
                    "--- PLAYER LOGS ---\n")
    parts.append({"type": "text", "text": initial_text})

    for log in formatted_logs:
        parts.extend(_format_log_entry(log, upload_context))

    return parts


def _generate_summary(client: google.genai.Client,
                      ai_config: dict[str, str | None], instructions_path: str,
                      examples_dir: str, prompt: list[ContentItem]) -> str:
    """Generates the summary using the initialized client and prompt."""
    model_name = ai_config.get('model_name')
    if not model_name:
        raise ValueError("model_name must be defined in ai_config")
    sys_inst = load_system_instructions(instructions_path)
    steps: list[InteractionStep] = load_chat_history(examples_dir)
    steps.append({"type": "user_input", "content": prompt})

    generation_config: GenerationConfigDict = {}
    thinking_level = ai_config.get('thinking_level')
    if thinking_level:
        generation_config["thinking_level"] = thinking_level.lower()

    interaction = client.interactions.create(
        model=model_name,
        system_instruction=sys_inst,
        input=steps,
        generation_config=generation_config or None)
    output_text = getattr(interaction, "output_text", None)
    if output_text is not None:
        return str(output_text)
    raise TypeError("Expected interaction response with output_text attribute")


def write_summary_files(output_dir: str, game_id: int,
                        prompt: list[ContentItem], summary_html: str) -> None:
    """Writes the generated summary and input prompt to files."""
    in_path = os.path.join(output_dir, f"game_{game_id}_input.txt")
    out_path = os.path.join(output_dir, f"game_{game_id}_output.html")

    with open(in_path, 'w', encoding='utf-8') as f:
        text_prompt = ""
        for p in prompt:
            if p["type"] == "text":
                text_prompt += p["text"]
            elif p["type"] == "image":
                text_prompt += "[IMAGE DATA DETACHED]\n"
        f.write(text_prompt)

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(summary_html)

    print("Summary generated successfully.")
    print(f"Input file: {in_path}")
    print(f"Output file: {out_path}")


def _get_game_data(
        config_path: str,
        game_id: int) -> tuple[str, list[tuple[str, int]], list[LogEntry]]:
    """Extracts game title, scores, and formatted logs from the database."""
    conn = backend.scripts.db_utils.get_db_connection(config_path)
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
    game_data = _get_game_data(config_path, args.game_id)

    client = get_gemini_client(ai_config)

    upload_context: UploadContext = {
        "client": client,
        "local_temp_files": [],
        "uploaded_ai_files": []
    }

    try:
        prompt = construct_new_data(game_data[0], game_data[1], game_data[2],
                                    upload_context)
        summary_html = _generate_summary(client, ai_config, instructions_path,
                                         examples_dir, prompt)
        write_summary_files(args.output_dir, args.game_id, prompt,
                            summary_html)

    finally:
        # A. Clean up local temporary files
        for local_file in upload_context["local_temp_files"]:
            try:
                if os.path.exists(local_file):
                    os.unlink(local_file)
            except OSError as e:
                print(f"Failed to delete local temp file {local_file}: {e}",
                      file=sys.stderr)

        # B. Clean up uploaded remote AI Studio files
        for uploaded_file in upload_context["uploaded_ai_files"]:
            try:
                if uploaded_file.name:
                    client.files.delete(name=uploaded_file.name)
            except Exception as e:  # pylint: disable=broad-exception-caught
                print(
                    f"Failed to delete remote AI Studio file {uploaded_file.name}: {e}",
                    file=sys.stderr)


def main() -> None:
    """Main execution point for the summary script."""
    parser = argparse.ArgumentParser(
        description="Geodashing Game Summary Generator")
    parser.add_argument('--game_id',
                        type=int,
                        required=True,
                        help="ID of the game to summarize.")
    parser.add_argument('--output_dir',
                        type=str,
                        required=True,
                        help="Directory to save the input and output files.")
    args = parser.parse_args()

    if not os.path.isdir(args.output_dir):
        print(f"Error: Output directory not found: {args.output_dir}",
              file=sys.stderr)
        sys.exit(1)

    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, '../config.ini')
    instructions_path = os.path.join(
        current_dir, '../../data/summary_system_instructions.txt')
    examples_dir = os.path.join(current_dir, '../../data/summary_examples/')

    try:
        run_summary_generation(args, config_path, instructions_path,
                               examples_dir)
    except (FileNotFoundError, ValueError,
            mysql.connector.Error) as specific_err:
        print(f"Configuration or Database Error: {specific_err}",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
