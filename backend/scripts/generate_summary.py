"""Script to generate a game summary using Gemini via Vertex AI."""

import argparse
import configparser
import json
import os
import sys

import mysql.connector
import vertexai
from vertexai.generative_models import GenerativeModel

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

def configure_environment(config_path: str) -> tuple:
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

    return model_name, region, project_id

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
    """Parses the photos JSON string into a list of URLs."""
    photo_urls = []
    if photos_json:
        try:
            photos_data = json.loads(photos_json)
            for item in photos_data:
                if 'url' in item:
                    photo_urls.append(item['url'])
                elif isinstance(item, str):
                    photo_urls.append(item)
        except json.JSONDecodeError:
            pass
    return photo_urls

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

        photo_urls = _parse_photos_json(photos_json)
        photo_str = "Photos: " + ", ".join(photo_urls) if photo_urls else "Photos: None"

        log_text = (
            f"---------------------\n"
            f"Log: {dp_id}.txt\n"
            f"---------------------\n"
            f"Player: {username}\n\n"
            f"{dp_id} is near {city}.\n\n"
            f"{photo_str}\n\n"
            f"{notes or ''}"
        )
        formatted_logs.append(log_text)

    return formatted_logs

def extract_logs_and_scores(cursor, game_id: int) -> tuple:
    """Extracts scores strictly constrained to the game and retrieves all approved logs."""
    scores = _extract_scores(cursor, game_id)
    formatted_logs = _extract_logs(cursor, game_id)
    return scores, formatted_logs

def construct_prompt(prompt_path: str, scores: list, formatted_logs: list) -> str:
    """Constructs the final prompt string."""
    with open(prompt_path, 'r', encoding='utf-8') as f:
        base_prompt = f.read()

    if not scores:
        score_text = "No players scored in this game."
    else:
        winner = scores[0]
        score_text = f"Winner: {winner[0]} with {winner[1]} points.\n\nOther Players:\n"
        for user, points in scores[1:]:
            score_text += f"- {user}: {points} points\n"

    sys_instructions = (
        "\n\n[SYSTEM INSTRUCTIONS FOR HTML FORMATTING]\n"
        "Please format the response exclusively as valid HTML.\n"
        "When rendering the Player Logs, any provided photo URLs MUST be "
        "formatted as embedded HTML images using <img> tags. "
        "They should be scaled to an appropriate thumbnail size "
        "(e.g., width='300'), and wrapped in an <a> anchor tag "
        "that links to the full-size photo URL so that clicking the "
        "thumbnail brings up the full-size photo.\n\n"
    )

    combined_logs = "\n\n".join(formatted_logs)

    data_set = (
        f"[NEW INPUT DATA SET]\n\n"
        f"--- SCORE RANKINGS ---\n{score_text}\n\n"
        f"--- PLAYER LOGS ---\n{combined_logs}\n"
    )

    return base_prompt + sys_instructions + data_set

def _generate_vertex_summary(project_id: str, region: str, model_name: str, prompt: str) -> None:
    """Initializes Vertex AI and generates the summary from the prompt."""
    vertexai.init(project=project_id, location=region)
    model = GenerativeModel(model_name)
    response = model.generate_content(prompt)
    print(response.text)

def main() -> None:
    """Main execution point for the summary script."""
    parser = argparse.ArgumentParser(description="Geodashing Game Summary Generator")
    parser.add_argument('--game_id', type=int, required=True,
                        help="ID of the game to summarize.")
    args = parser.parse_args()

    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, '../config.ini')
    prompt_path = os.path.join(current_dir, '../../data/summary_prompt.txt')

    try:
        model_name, region, project_id = configure_environment(config_path)

        conn = get_db_connection(config_path)
        cursor = conn.cursor()

        game_id = args.game_id
        scores, formatted_logs = extract_logs_and_scores(cursor, game_id)

        cursor.close()
        conn.close()

        prompt = construct_prompt(prompt_path, scores, formatted_logs)

        _generate_vertex_summary(project_id, region, model_name, prompt)

    except (FileNotFoundError, ValueError, mysql.connector.Error) as specific_err:
        print(f"Configuration or Database Error: {specific_err}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
