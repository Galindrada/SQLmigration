import os
import sqlite3
import import_pes6_data
import update_player_finances
from datetime import datetime
from config import Config

SQL_SCHEMA_FILE = 'database.sql'
DB_PATH = getattr(Config, 'SQLITE_DB_PATH', 'pes6_league_db.sqlite')

def safe_refresh_database():
    """Safely refresh database schema without erasing existing data"""
    print('🔧 Safely refreshing database schema...')
    print('📖 Reading schema from:', os.path.abspath(SQL_SCHEMA_FILE))
    
    # Check if database exists
    if not os.path.exists(DB_PATH):
        print(f"❌ Database {DB_PATH} does not exist. Creating new database...")
        create_new_database()
        return
    
    print(f"✅ Database {DB_PATH} exists. Adding new features safely...")
    
    # Connect to existing database
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON;')
    cursor = conn.cursor()
    
    try:
        # Add new columns to teams table for financial data
        print("\n💰 Adding financial data columns to teams table...")
        
        try:
            cursor.execute("ALTER TABLE teams ADD COLUMN total_salaries INTEGER DEFAULT 0")
            print("  ✅ Added total_salaries column")
        except Exception as e:
            if 'duplicate column name' not in str(e):
                print(f"  ❌ Error adding total_salaries column: {e}")
            else:
                print("  ℹ️  total_salaries column already exists")
        
        try:
            cursor.execute("ALTER TABLE teams ADD COLUMN budget INTEGER DEFAULT 0")
            print("  ✅ Added budget column")
        except Exception as e:
            if 'duplicate column name' not in str(e):
                print(f"  ❌ Error adding budget column: {e}")
            else:
                print("  ℹ️  budget column already exists")
        
        try:
            cursor.execute("ALTER TABLE teams ADD COLUMN available_cap INTEGER DEFAULT 0")
            print("  ✅ Added available_cap column")
        except Exception as e:
            if 'duplicate column name' not in str(e):
                print(f"  ❌ Error adding available_cap column: {e}")
            else:
                print("  ℹ️  available_cap column already exists")
        
        # Add development_key column to players table
        print("\n📈 Adding development_key column to players table...")
        try:
            cursor.execute("ALTER TABLE players ADD COLUMN development_key INTEGER DEFAULT 0")
            print("  ✅ Added development_key column")
        except Exception as e:
            if 'duplicate column name' not in str(e):
                print(f"  ❌ Error adding development_key column: {e}")
            else:
                print("  ℹ️  development_key column already exists")
        
        # Add trait_key column to players table
        print("\n🎭 Adding trait_key column to players table...")
        try:
            cursor.execute("ALTER TABLE players ADD COLUMN trait_key INTEGER DEFAULT 0")
            print("  ✅ Added trait_key column")
        except Exception as e:
            if 'duplicate column name' not in str(e):
                print(f"  ❌ Error adding trait_key column: {e}")
            else:
                print("  ℹ️  trait_key column already exists")
        
        # Add performance tracking columns to players table
        print("\n📊 Adding performance tracking columns to players table...")
        performance_columns = [
            ('players', 'games_played', 'INTEGER DEFAULT 0'),
            ('players', 'goals', 'INTEGER DEFAULT 0'),
            ('players', 'assists', 'INTEGER DEFAULT 0')
        ]
        
        for table, column, definition in performance_columns:
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                print(f"  ✅ Added {column} column")
            except Exception as e:
                if 'duplicate column name' not in str(e):
                    print(f"  ❌ Error adding {column} column: {e}")
                else:
                    print(f"  ℹ️  {column} column already exists")
        
        # Add other missing columns that might be needed
        print("\n📋 Adding missing columns to offers table...")
        try:
            cursor.execute("ALTER TABLE offers ADD COLUMN offered_players TEXT")
            print("  ✅ Added offered_players column to offers table")
        except Exception as e:
            if 'duplicate column name' not in str(e):
                print(f"  ❌ Error adding offered_players column: {e}")
            else:
                print("  ℹ️  offered_players column already exists")
        
        try:
            cursor.execute("ALTER TABLE offers ADD COLUMN offered_money INTEGER DEFAULT 0")
            print("  ✅ Added offered_money column to offers table")
        except Exception as e:
            if 'duplicate column name' not in str(e):
                print(f"  ❌ Error adding offered_money column: {e}")
            else:
                print("  ℹ️  offered_money column already exists")
        
        try:
            cursor.execute("ALTER TABLE offers ADD COLUMN requested_players TEXT")
            print("  ✅ Added requested_players column to offers table")
        except Exception as e:
            if 'duplicate column name' not in str(e):
                print(f"  ❌ Error adding requested_players column: {e}")
            else:
                print("  ℹ️  requested_players column already exists")
        
        try:
            cursor.execute("ALTER TABLE offers ADD COLUMN requested_money INTEGER DEFAULT 0")
            print("  ✅ Added requested_money column to offers table")
        except Exception as e:
            if 'duplicate column name' not in str(e):
                print(f"  ❌ Error adding requested_money column: {e}")
            else:
                print("  ℹ️  requested_money column already exists")
        
        try:
            cursor.execute("ALTER TABLE offers ADD COLUMN sender_team_id INTEGER")
            print("  ✅ Added sender_team_id column to offers table")
        except Exception as e:
            if 'duplicate column name' not in str(e):
                print(f"  ❌ Error adding sender_team_id column: {e}")
            else:
                print("  ℹ️  sender_team_id column already exists")
        
        try:
            cursor.execute("ALTER TABLE offers ADD COLUMN receiver_team_id INTEGER")
            print("  ✅ Added receiver_team_id column to offers table")
        except Exception as e:
            if 'duplicate column name' not in str(e):
                print(f"  ❌ Error adding receiver_team_id column: {e}")
            else:
                print("  ℹ️  receiver_team_id column already exists")
        
        # Ensure CPU user exists
        print("\n🤖 Ensuring CPU user exists...")
        try:
            cursor.execute("SELECT id FROM users WHERE id = 1")
            result = cursor.fetchone()
            if not result:
                cursor.execute("INSERT INTO users (id, username, password, email) VALUES (?, ?, ?, ?)", (1, 'CPU', '', 'cpu@localhost'))
                print('  ✅ CPU user created.')
            else:
                print('  ℹ️  CPU user already exists.')
        except Exception as e:
            print(f"  ❌ Error ensuring CPU user: {e}")
        
        conn.commit()
        print("\n✅ Schema updates completed successfully.")
        
    except Exception as e:
        print(f"❌ Error updating schema: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def calculate_cpu_team_finances():
    """Calculate and populate financial data for CPU teams only"""
    print("\n💰 Calculating financial data for CPU teams only...")
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON;')
    cursor = conn.cursor()
    
    try:
        # Get only CPU teams (teams managed by user_id = 1 in league_teams)
        cursor.execute("""
            SELECT t.id, t.club_name 
            FROM teams t
            JOIN league_teams lt ON t.club_name = lt.team_name
            WHERE lt.user_id = 1
        """)
        cpu_teams = cursor.fetchall()
        
        updated_count = 0
        for team_id, club_name in cpu_teams:
            # Calculate total salaries for this team
            cursor.execute("SELECT COALESCE(SUM(salary), 0) as total_salaries FROM players WHERE club_id = ?", (team_id,))
            result = cursor.fetchone()
            total_salaries = result[0] if result else 0
            
            # Set budget equal to total salaries initially
            budget = total_salaries
            
            # Calculate available cap
            available_cap = budget - total_salaries
            
            # Update team financial data
            cursor.execute("""
                UPDATE teams 
                SET total_salaries = ?, budget = ?, available_cap = ?
                WHERE id = ?
            """, (total_salaries, budget, available_cap, team_id))
            
            updated_count += 1
            print(f"  ✅ {club_name}: €{total_salaries:,} salaries, €{budget:,} budget, €{available_cap:,} available cap")
        
        conn.commit()
        print(f"\n✅ Financial data calculated for {updated_count} CPU teams.")
        
    except Exception as e:
        print(f"❌ Error calculating CPU team finances: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def create_new_database():
    """Create a completely new database from scratch"""
    print('🆕 Creating new database from scratch...')
    with open(SQL_SCHEMA_FILE, 'r') as f:
        sql_script = f.read()
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON;')
    cursor = conn.cursor()
    
    try:
        cursor.executescript(sql_script)
        print('Schema script executed.')
        conn.commit()
        print('Schema committed.')
        
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
        
        # Add new columns for financial data
        try:
            cursor.execute("ALTER TABLE teams ADD COLUMN total_salaries INTEGER DEFAULT 0")
            cursor.execute("ALTER TABLE teams ADD COLUMN budget INTEGER DEFAULT 0")
            cursor.execute("ALTER TABLE teams ADD COLUMN available_cap INTEGER DEFAULT 0")
            cursor.execute("ALTER TABLE players ADD COLUMN development_key INTEGER DEFAULT 0")
            print("Financial columns and development_key added to tables.")
        except Exception as e:
            print(f"Error adding columns: {e}")
        
        conn.commit()
        
    except Exception as e:
        print(f"Error executing schema script:\n{e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
    
    print('New database created.')

def assign_teams_to_cpu():
    print('🤖 Assigning all teams to CPU in league_teams...')
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
    print('🗑️  Clearing blacklist...')
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON;')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM blacklist")
    conn.commit()
    cursor.close()
    conn.close()
    print('Blacklist cleared.')

def update_player_positions():
    print('⚽ Updating player game positions...')
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON;')
    cursor = conn.cursor()
    
    # Position mapping (as strings since registered_position is stored as text)
    position_mapping = {
        '0': 'Goal-Keeper',
        '2': 'Sweeper',
        '3': 'Centre-Back',
        '4': 'Side-Back',
        '5': 'Defensive Midfielder',
        '6': 'Wing-Back',
        '7': 'Center-Midfielder',
        '8': 'Side-Midfielder',
        '9': 'Attacking Midfielder',
        '10': 'Winger',
        '11': 'Shadow Striker',
        '12': 'Striker',
        '13': 'Unknown'  # Handle position 13
    }
    
    # Update game_position based on registered_position
    cursor.execute("SELECT id, registered_position FROM players")
    players = cursor.fetchall()
    
    updated_count = 0
    for player_id, registered_position in players:
        if registered_position in position_mapping:
            game_position = position_mapping[registered_position]
            cursor.execute("UPDATE players SET game_position = ? WHERE id = ?", (game_position, player_id))
            updated_count += 1
    
    conn.commit()
    cursor.close()
    conn.close()
    print(f'Player game positions updated for {updated_count} players.')

def calculate_skill_ratings():
    print('📊 Calculating bundled skill ratings...')
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON;')
    cursor = conn.cursor()
    
    # Add bundled skill columns if they don't exist
    try:
        cursor.execute("ALTER TABLE players ADD COLUMN attack_rating INTEGER DEFAULT 0")
    except Exception as e:
        if 'duplicate column name' not in str(e):
            print(f"Error adding attack_rating column: {e}")
    
    try:
        cursor.execute("ALTER TABLE players ADD COLUMN defense_rating INTEGER DEFAULT 0")
    except Exception as e:
        if 'duplicate column name' not in str(e):
            print(f"Error adding defense_rating column: {e}")
    
    try:
        cursor.execute("ALTER TABLE players ADD COLUMN physical_rating INTEGER DEFAULT 0")
    except Exception as e:
        if 'duplicate column name' not in str(e):
            print(f"Error adding physical_rating column: {e}")
    
    try:
        cursor.execute("ALTER TABLE players ADD COLUMN power_rating INTEGER DEFAULT 0")
    except Exception as e:
        if 'duplicate column name' not in str(e):
            print(f"Error adding power_rating column: {e}")
    
    try:
        cursor.execute("ALTER TABLE players ADD COLUMN technique_rating INTEGER DEFAULT 0")
    except Exception as e:
        if 'duplicate column name' not in str(e):
            print(f"Error adding technique_rating column: {e}")
    
    try:
        cursor.execute("ALTER TABLE players ADD COLUMN goalkeeping_rating INTEGER DEFAULT 0")
    except Exception as e:
        if 'duplicate column name' not in str(e):
            print(f"Error adding goalkeeping_rating column: {e}")
    
    try:
        cursor.execute("ALTER TABLE players ADD COLUMN game_position TEXT DEFAULT ''")
    except Exception as e:
        if 'duplicate column name' not in str(e):
            print(f"Error adding game_position column: {e}")
    
    # Fetch all players
    cursor.execute("SELECT * FROM players")
    players = cursor.fetchall()
    
    # Get column names
    column_names = [description[0] for description in cursor.description]
    
    for player in players:
        player_data = dict(zip(column_names, player))
        
        # Calculate bundled skill ratings
        attack_rating = player_data['attack']
        
        defense_rating = (player_data['defense'] + player_data['aggression']) // 2
        
        physical_rating = (player_data['stamina'] + player_data['top_speed'] + 
                          player_data['acceleration'] + player_data['response'] + 
                          player_data['agility'] + player_data['jump']) // 6
        
        power_rating = (player_data['shot_power'] + player_data['balance'] + 
                       player_data['mentality']) // 3
        
        technique_rating = (player_data['technique'] + player_data['swerve'] + 
                           player_data['free_kick_accuracy'] + player_data['dribble_accuracy'] + 
                           player_data['dribble_speed'] + player_data['short_pass_accuracy'] + 
                           player_data['short_pass_speed'] + player_data['long_pass_accuracy'] + 
                           player_data['long_pass_speed']) // 9
        
        goalkeeping_rating = (player_data['defense'] + player_data['goal_keeping'] + 
                             player_data['response'] + player_data['agility']) // 4
        
        # Update player with calculated ratings
        cursor.execute("""
            UPDATE players 
            SET attack_rating = ?, defense_rating = ?, physical_rating = ?, 
                power_rating = ?, technique_rating = ?, goalkeeping_rating = ?
            WHERE id = ?
        """, (attack_rating, defense_rating, physical_rating, power_rating, 
              technique_rating, goalkeeping_rating, player_data['id']))
    
    conn.commit()
    cursor.close()
    conn.close()
    print('Bundled skill ratings calculated and updated.')

def populate_team_players_for_cpu():
    print('👥 Populating team_players for all CPU teams...')
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

def initialize_budget_system():
    print('💰 Initializing budget system for all users...')
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON;')
    cursor = conn.cursor()
    
    # Get all users except CPU (user_id = 1)
    cursor.execute("SELECT id, username FROM users WHERE id != 1")
    users = cursor.fetchall()
    
    for user_id, username in users:
        # Check if user already has a budget record
        cursor.execute("SELECT user_id FROM user_budgets WHERE user_id = ?", (user_id,))
        if not cursor.fetchone():
            # Create budget record with initial €450M
            cursor.execute("""
                INSERT INTO user_budgets (user_id, budget, created_at, updated_at)
                VALUES (?, ?, ?, ?)
            """, (user_id, 450000000, datetime.now().isoformat(), datetime.now().isoformat()))
            print(f"  - Initialized budget for {username}")
    
    conn.commit()
    cursor.close()
    conn.close()
    print('Budget system initialized for all users.')

def safe_main():
    """Safe main function that only adds new features without erasing data"""
    print("=== SAFE Database Refresh Script ===")
    print("🔒 This script will SAFELY add new features without erasing existing data:")
    print("1. ✅ Add new database columns safely")
    print("2. ✅ Calculate CPU team financial data")
    print("3. ✅ Update player positions and skill ratings")
    print("4. ✅ Initialize budget system for new users")
    print("5. ✅ Ensure CPU user exists")
    print("6. ✅ Populate team_players for CPU teams")
    print("7. ✅ Assign development keys to players")
    print("\n⚠️  EXISTING USER DATA WILL BE PRESERVED!")
    
    # Safe operations that don't erase data
    safe_refresh_database()
    calculate_cpu_team_finances()
    update_player_positions()
    calculate_skill_ratings()
    populate_team_players_for_cpu()
    initialize_budget_system()
    
    # Assign development keys to players
    print("\n🎭 Assigning development keys to players...")
    try:
        from game_mechanics import assign_development_keys_to_players, verify_development_keys
        result = assign_development_keys_to_players(DB_PATH)
        if result.get('new_keys_assigned', 0) > 0:
            print(f"✅ Successfully assigned development keys to {result['new_keys_assigned']} players")
        else:
            print("ℹ️  All players already have development keys")
        
        # Verify the assignments
        print("\n🔍 Verifying development key assignments...")
        verify_result = verify_development_keys(DB_PATH)
        if 'error' not in verify_result:
            print("✅ Development key verification completed")
        
    except Exception as e:
        print(f"❌ Error assigning development keys: {e}")
    
    print("\n✅ All safe operations completed successfully!")
    print("🎉 Your existing data is safe and new features have been added!")

def destructive_main():
    """Original destructive main function - USE WITH CAUTION"""
    print("=== DESTRUCTIVE Database Refresh Script ===")
    print("⚠️  WARNING: This will DELETE ALL EXISTING DATA!")
    print("This script will:")
    print("1. ❌ Delete the existing database file")
    print("2. ❌ Create a fresh database with the schema")
    print("3. ❌ Import PES6 player and team data")
    print("4. ❌ Update player finances")
    print("5. ❌ Update player game positions")
    print("6. ❌ Calculate bundled skill ratings")
    print("7. ❌ Clear blacklist")
    print("8. ❌ Initialize budget system for all users")
    
    # Ask for confirmation
    response = input("\n⚠️  Are you sure you want to DELETE ALL DATA? (yes/no): ")
    if response.lower() != 'yes':
        print("❌ Operation cancelled. Your data is safe.")
        return
    
    # Delete database file
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"🗑️  Deleted {DB_PATH}")
    
    create_new_database()
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
    update_player_positions()
    calculate_skill_ratings()
    clear_blacklist()
    initialize_budget_system()
    print('All done!')

if __name__ == '__main__':
    # Use safe main by default
    safe_main() 