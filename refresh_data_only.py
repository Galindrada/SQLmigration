import os
import sqlite3
import import_pes6_data
import update_player_finances
from config import Config

SQL_SCHEMA_FILE = 'database.sql'
DB_PATH = getattr(Config, 'SQLITE_DB_PATH', 'pes6_league_db.sqlite')

def refresh_data_only():
    """Refresh only the data tables without deleting the entire database."""
    print('Refreshing data tables only...')
    
    if not os.path.exists(DB_PATH):
        print(f"Database file {DB_PATH} does not exist. Please run refresh_and_reimport.py first.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON;')
    cursor = conn.cursor()
    
    try:
        # Clear data tables but keep users and other metadata
        print('Clearing player and team data...')
        cursor.execute("DELETE FROM player_performance")
        cursor.execute("DELETE FROM players")
        cursor.execute("DELETE FROM teams")
        cursor.execute("DELETE FROM league_teams")
        cursor.execute("DELETE FROM team_players")
        cursor.execute("DELETE FROM blacklist")
        conn.commit()
        print('Data tables cleared.')
        
    except Exception as e:
        print(f"Error clearing data tables: {e}")
        conn.rollback()
        cursor.close()
        conn.close()
        return
    
    cursor.close()
    conn.close()
    
    print('Importing PES6 player and team data...')
    import_pes6_data.import_data()
    
    print('Assigning teams to CPU...')
    assign_teams_to_cpu()
    
    print('Populating team players for CPU...')
    populate_team_players_for_cpu()
    
    print('Updating player finances...')
    update_player_finances.update_player_finances()
    
    print('Data refresh complete!')

def assign_teams_to_cpu():
    """Assign all teams to CPU in league_teams."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON;')
    cursor = conn.cursor()
    cursor.execute("SELECT club_name FROM teams")
    all_teams = cursor.fetchall()
    for (club_name,) in all_teams:
        cursor.execute("INSERT INTO league_teams (user_id, team_name) VALUES (?, ?)", (1, club_name))
    conn.commit()
    cursor.close()
    conn.close()
    print('All teams assigned to CPU.')

def populate_team_players_for_cpu():
    """Populate team_players for all CPU teams."""
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
    print("=== Data-Only Refresh Script ===")
    print("This script will:")
    print("1. Clear all player and team data")
    print("2. Import fresh PES6 player and team data")
    print("3. Update player finances")
    print("4. Clear blacklist")
    print("5. Preserve all users and messages")
    
    confirm = input("\nThis will delete all player data but keep users. Continue? (y/n): ").lower().strip()
    if confirm in ['y', 'yes']:
        refresh_data_only()
        print('All done!')
    else:
        print('Operation cancelled.')

if __name__ == '__main__':
    main() 