import os
import mysql.connector
import import_pes6_data
import update_player_finances

# Database connection details (hardcoded for local use)
DB_CONFIG = {
    'host': 'localhost',
    'user': 'simpleuser',
    'password': '',  # or your password here
    'database': 'pes6_league_db'
}

SQL_SCHEMA_FILE = 'database.sql'


def refresh_database():
    print('Refreshing database schema...')
    with open(SQL_SCHEMA_FILE, 'r') as f:
        sql_commands = f.read().split(';')
    conn = mysql.connector.connect(
        host=DB_CONFIG['host'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password']
    )
    cursor = conn.cursor()
    # Create DB if not exists
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']}")
    cursor.execute(f"USE {DB_CONFIG['database']}")
    for command in sql_commands:
        cmd = command.strip()
        # Skip comments and empty lines
        if not cmd or cmd.startswith('--'):
            continue
        try:
            cursor.execute(cmd)
            # If it's a SELECT, fetch all results to avoid unread result error
            if cmd.lower().startswith('select'):
                cursor.fetchall()
        except Exception as e:
            print(f"Error executing SQL: {cmd[:60]}...\n{e}")
    # Ensure CPU user exists
    try:
        cursor.execute("SELECT id FROM users WHERE id = 1")
        result = cursor.fetchone()
        if not result:
            cursor.execute("INSERT INTO users (id, username, password, email) VALUES (1, 'CPU', '', 'cpu@localhost')")
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
    cursor.close()
    conn.close()
    print('Database schema refreshed.')


def assign_teams_to_cpu():
    print('Assigning all teams to CPU in league_teams...')
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM league_teams")
    cursor.execute("SELECT club_name FROM teams")
    all_teams = cursor.fetchall()
    for (club_name,) in all_teams:
        cursor.execute("INSERT INTO league_teams (user_id, team_name) VALUES (1, %s)", (club_name,))
    conn.commit()
    cursor.close()
    conn.close()
    print('All teams assigned to CPU.')


def main():
    refresh_database()
    print('Importing PES6 player and team data...')
    # Delete player_performance and players to avoid FK constraint errors
    conn = mysql.connector.connect(**DB_CONFIG)
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
    print('Updating player finances...')
    update_player_finances.update_player_finances()
    print('All done!')

if __name__ == '__main__':
    main() 