"""Administrative utilities for managing Geodashing game lifecycles."""

import argparse
import os
import sys

from backend.scripts.db_utils import get_db_connection

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

def main() -> None:
    """Main entrypoint for the game administration script."""
    parser = argparse.ArgumentParser(description="Geodashing Game Administration Utility")
    parser.add_argument('--list', action='store_true', help="List all games chronologically")
    parser.add_argument('--activate', type=int, metavar='GAME_ID',
                        help="Activate a specific game ID and retire all others")
    args = parser.parse_args()

    if not args.list and args.activate is None:
        parser.print_help()
        sys.exit(1)

    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, '../config.ini')

    try:
        conn = get_db_connection(config_path)
        cursor = conn.cursor()

        if args.list:
            list_games(cursor)

        if args.activate is not None:
            if args.list:
                print("\n" + "="*80 + "\n")
            activate_game(cursor, conn, args.activate)

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
