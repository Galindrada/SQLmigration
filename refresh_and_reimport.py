import os
import sqlite3
import import_pes6_data
import update_player_finances
from config import Config

SQL_SCHEMA_FILE = 'database.sql'
DB_PATH = getattr(Config, 'SQLITE_DB_PATH', 'pes6_league_db.sqlite')

# Always start with a clean database file
if os.path.exists(DB_PATH):
    print(f"Deleting old database file: {DB_PATH}")
    os.remove(DB_PATH)

def refresh_database():
    print('Refreshing database schema...')
    print('Reading schema from:', os.path.abspath(SQL_SCHEMA_FILE))
    with open(SQL_SCHEMA_FILE, 'r') as f:
        sql_script = f.read()
    print('Schema script length:', len(sql_script))
    print('--- First 40 lines of schema script ---')
    for i, line in enumerate(sql_script.splitlines()):
        if i > 40: break
        print(line)
    print('--- End of preview ---')
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON;')
    cursor = conn.cursor()
    try:
        cursor.executescript(sql_script)
        print('Schema script executed.')
        conn.commit()
        print('Schema committed.')
    except Exception as e:
        print(f"Error executing schema script:\n{e}")
        cursor.close()
        conn.close()
        return  # Stop further execution if schema fails
    # Ensure CPU user exists
    try:
        cursor.execute("SELECT id FROM users WHERE id = 1")
        result = cursor.fetchone()
        if not result:
            cursor.execute("INSERT INTO users (id, username, password, email) VALUES (?, ?, ?, ?)", (1, 'CPU', '', 'cpu@localhost'))
            conn.commit()
            print('CPU user created.')
        else:
            print('CPU user already exists.')
    except Exception as e:
        print(f"Error ensuring CPU user: {e}")
    # Erase all users except CPU user (id=1)
    try:
        cursor.execute("DELETE FROM users WHERE id != 1")
        conn.commit()
        print('All users (except CPU) erased.')
    except Exception as e:
        print(f"Error erasing users: {e}")
    # After schema creation, ensure offers table has new columns for richer deals
    try:
        # Add offered_players
        cursor.execute("ALTER TABLE offers ADD COLUMN offered_players TEXT")
    except Exception as e:
        if 'duplicate column name' not in str(e):
            print(f"Error adding offered_players column: {e}")
    try:
        cursor.execute("ALTER TABLE offers ADD COLUMN offered_money INTEGER DEFAULT 0")
    except Exception as e:
        if 'duplicate column name' not in str(e):
            print(f"Error adding offered_money column: {e}")
    try:
        cursor.execute("ALTER TABLE offers ADD COLUMN requested_players TEXT")
    except Exception as e:
        if 'duplicate column name' not in str(e):
            print(f"Error adding requested_players column: {e}")
    try:
        cursor.execute("ALTER TABLE offers ADD COLUMN requested_money INTEGER DEFAULT 0")
    except Exception as e:
        if 'duplicate column name' not in str(e):
            print(f"Error adding requested_money column: {e}")
    conn.commit()
    cursor.close()
    conn.close()
    print('Database schema refreshed.')

def assign_teams_to_cpu():
    print('Assigning all teams to CPU in league_teams...')
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON;')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM league_teams")
    cursor.execute("SELECT club_name FROM teams")
    all_teams = cursor.fetchall()
    for (club_name,) in all_teams:
        cursor.execute("INSERT INTO league_teams (user_id, team_name) VALUES (?, ?)", (1, club_name))
    conn.commit()
    cursor.close()
    conn.close()
    print('All teams assigned to CPU.')

def clear_blacklist():
    print('Clearing blacklist...')
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON;')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM blacklist")
    conn.commit()
    cursor.close()
    conn.close()
    print('Blacklist cleared.')

def populate_team_players_for_cpu():
    print('Populating team_players for all CPU teams...')
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON;')
    cursor = conn.cursor()
    # For each league_team (CPU only), add all players whose club_id matches the team
    cursor.execute("SELECT id, team_name FROM league_teams WHERE user_id = 1")
    cpu_teams = cursor.fetchall()
    for team_id, team_name in cpu_teams:
        cursor.execute("SELECT id FROM teams WHERE club_name = ?", (team_name,))
        club = cursor.fetchone()
        if club:
            club_id = club[0]
            cursor.execute("SELECT id FROM players WHERE club_id = ?", (club_id,))
            player_ids = cursor.fetchall()
            for (player_id,) in player_ids:
                cursor.execute("INSERT OR IGNORE INTO team_players (team_id, player_id) VALUES (?, ?)", (team_id, player_id))
    conn.commit()
    cursor.close()
    conn.close()
    print('team_players table populated for all CPU teams.')

def main():
    refresh_database()
    print('Importing PES6 player and team data...')
    # Delete player_performance and players to avoid FK constraint errors
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON;')
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM player_performance")
        cursor.execute("DELETE FROM players")
        conn.commit()
        print('player_performance and players tables cleared.')
    except Exception as e:
        print(f"Error clearing player tables: {e}")
    cursor.close()
    conn.close()
    import_pes6_data.import_data()
    assign_teams_to_cpu()
    populate_team_players_for_cpu()
    print('Updating player finances...')
    update_player_finances.update_player_finances()
    clear_blacklist()
    print('All done!')

if __name__ == '__main__':
    main() 