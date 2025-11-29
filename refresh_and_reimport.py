import os
import sqlite3
import import_pes6_data
import update_player_finances
from datetime import datetime
from config import Config
import pandas as pd

SQL_SCHEMA_FILE = 'database.sql'
DB_PATH = getattr(Config, 'SQLITE_DB_PATH', 'pes6_league_db.sqlite')

def calculate_player_overall(player_data):
    """Calculate position-weighted overall rating using position-specific number of most relevant skills"""
    from game_mechanics import get_cached_position_averages, get_position_skill_weights_from_averages
    
    # Use registered_position (number) instead of game_position (string)
    position = str(player_data.get('registered_position', ''))
    
    try:
        # Get cached position averages for skill weights
        pos_avg_df = get_cached_position_averages('pes6_league_db.sqlite')
        
        # Get position-specific skill weights based on position averages
        position_weights = get_position_skill_weights_from_averages(pos_avg_df, position)
        
        # Filter to only include skills with positive weights and sort by weight (descending)
        relevant_skills = [(skill, weight) for skill, weight in position_weights.items() if weight > 0]
        relevant_skills.sort(key=lambda x: x[1], reverse=True)
        
        # Determine number of skills based on position
        # Goalkeepers (0) and Defenders (2,3,4,6): 6 most relevant skills
        # Midfielders (5,7,8,9) and Forwards (10,11,12): 8 most relevant skills
        if position in ['0', '2', '3', '4', '6']:  # Goalkeepers and Defenders
            num_skills = 6
        elif position in ['5', '7', '8', '9', '10', '11', '12']:  # Midfielders and Forwards
            num_skills = 8
        else:
            num_skills = 7  # Default for unknown positions
        
        # Take only the top N most relevant skills
        top_skills = relevant_skills[:num_skills]
        
        if not top_skills:
            return 50  # Default if no relevant skills
        
        # Calculate weighted average of the top skills
        overall = 0
        total_weight = 0
        
        for skill, weight in top_skills:
            skill_value = player_data.get(skill, 50)  # Default to 50 if skill not found
            overall += skill_value * weight
            total_weight += weight
        
        # Calculate weighted average
        if total_weight > 0:
            overall = overall / total_weight
        else:
            overall = 50
        
        return round(overall)
        
    except Exception as e:
        print(f"  ⚠️  Error calculating overall for position {position}: {e}")
        # Fallback to simple average
        skills = ['attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration', 
                 'response', 'agility', 'dribble_accuracy', 'short_pass_accuracy', 
                 'shot_accuracy', 'technique', 'mentality', 'team_work']
        skill_values = [player_data.get(skill, 50) for skill in skills]
        return round(sum(skill_values) / len(skill_values))

def recalculate_all_overalls():
    """Recalculate overall ratings for all players"""
    print("\n⭐ Recalculating overall ratings for all players...")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # Get all players
        cursor.execute("SELECT * FROM players")
        players = cursor.fetchall()
        
        updated_count = 0
        for player in players:
            player_data = dict(player)
            overall = calculate_player_overall(player_data)
            
            # Update player's overall rating
            cursor.execute("UPDATE players SET overall = ? WHERE id = ?", (overall, player['id']))
            updated_count += 1
        
        conn.commit()
        print(f"  ✅ Updated overall ratings for {updated_count} players")
        
    except Exception as e:
        print(f"  ❌ Error recalculating overalls: {e}")
        conn.rollback()
    finally:
        conn.close()

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
        
        # Add seed_player column to players table (stores base player id for regens)
        print("\n🌱 Adding seed_player column to players table...")
        try:
            cursor.execute("ALTER TABLE players ADD COLUMN seed_player INTEGER NULL")
            print("  ✅ Added seed_player column")
        except Exception as e:
            if 'duplicate column name' not in str(e):
                print(f"  ❌ Error adding seed_player column: {e}")
            else:
                print("  ℹ️  seed_player column already exists")

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
        
        # Add overall column to players table
        print("\n⭐ Adding overall column to players table...")
        try:
            cursor.execute("ALTER TABLE players ADD COLUMN overall INTEGER DEFAULT 0")
            print("  ✅ Added overall column")
        except Exception as e:
            if 'duplicate column name' not in str(e):
                print(f"  ❌ Error adding overall column: {e}")
            else:
                print("  ℹ️  overall column already exists")
        
        # Add draftee column to players table (marks manually created players)
        print("\n🌟 Adding draftee column to players table...")
        try:
            cursor.execute("ALTER TABLE players ADD COLUMN draftee INTEGER DEFAULT 0")
            print("  ✅ Added draftee column")
        except Exception as e:
            if 'duplicate column name' not in str(e):
                print(f"  ❌ Error adding draftee column: {e}")
            else:
                print("  ℹ️  draftee column already exists")
        
        # Add profile_image column to players table
        print("\n🖼️  Adding profile_image column to players table...")
        try:
            cursor.execute("ALTER TABLE players ADD COLUMN profile_image TEXT DEFAULT NULL")
            print("  ✅ Added profile_image column")
        except Exception as e:
            if 'duplicate column name' not in str(e):
                print(f"  ❌ Error adding profile_image column: {e}")
            else:
                print("  ℹ️  profile_image column already exists")
        
        # Add performance tracking columns to players table
        print("\n📊 Adding performance tracking columns to players table...")
        performance_columns = [
            ('players', 'games_played', 'INTEGER DEFAULT 0'),
            ('players', 'goals', 'INTEGER DEFAULT 0'),
            ('players', 'assists', 'INTEGER DEFAULT 0'),
            ('players', 'MVP', 'INTEGER DEFAULT 0')
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
        
        # Add international statistics columns to players table
        print("\n🌍 Adding international statistics columns to players table...")
        international_columns = [
            ('players', 'international_caps_total', 'INTEGER DEFAULT 0'),
            ('players', 'international_goals', 'INTEGER DEFAULT 0'),
            ('players', 'international_assists', 'INTEGER DEFAULT 0'),
            ('players', 'current_season_caps', 'INTEGER DEFAULT 0')
        ]
        
        for table, column, definition in international_columns:
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
        
        # Add draft picks columns to offers table
        print("\n🎯 Adding draft picks columns to offers table...")
        try:
            cursor.execute("ALTER TABLE offers ADD COLUMN offered_draft_picks TEXT")
            print("  ✅ Added offered_draft_picks column to offers table")
        except Exception as e:
            if 'duplicate column name' not in str(e):
                print(f"  ❌ Error adding offered_draft_picks column: {e}")
            else:
                print("  ℹ️  offered_draft_picks column already exists")
        
        try:
            cursor.execute("ALTER TABLE offers ADD COLUMN requested_draft_picks TEXT")
            print("  ✅ Added requested_draft_picks column to offers table")
        except Exception as e:
            if 'duplicate column name' not in str(e):
                print(f"  ❌ Error adding requested_draft_picks column: {e}")
            else:
                print("  ℹ️  requested_draft_picks column already exists")
        
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
        
        # Add career statistics columns to players table
        print("\n🏆 Adding career statistics columns to players table...")
        career_columns = [
            ('players', 'career_earnings', 'INTEGER DEFAULT 0'),
            ('players', 'championships_won', 'INTEGER DEFAULT 0'),
            ('players', 'cups_won', 'INTEGER DEFAULT 0')
        ]
        
        for table, column, definition in career_columns:
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                print(f"  ✅ Added {column} column")
            except Exception as e:
                if 'duplicate column name' not in str(e):
                    print(f"  ❌ Error adding {column} column: {e}")
                else:
                    print(f"  ℹ️  {column} column already exists")
        
        # Add stance column to teams table
        print("\n🎯 Adding stance column to teams table...")
        try:
            cursor.execute("ALTER TABLE teams ADD COLUMN stance TEXT DEFAULT 'Tinkering'")
            print("  ✅ Added stance column to teams table")
        except Exception as e:
            if 'duplicate column name' not in str(e):
                print(f"  ❌ Error adding stance column: {e}")
            else:
                print("  ℹ️  stance column already exists")
        
        # Add csv_visible column to teams table (for secondary/market teams)
        print("\n📋 Adding csv_visible column to teams table...")
        try:
            cursor.execute("ALTER TABLE teams ADD COLUMN csv_visible INTEGER DEFAULT 1")
            print("  ✅ Added csv_visible column (1=visible in CSV, 0=hidden secondary team)")
        except Exception as e:
            if 'duplicate column name' not in str(e):
                print(f"  ❌ Error adding csv_visible column: {e}")
            else:
                print("  ℹ️  csv_visible column already exists")
        
        # Create CPU leagues tables
        print("\n🏟️ Creating CPU leagues tables...")
        
        # CPU League Seasons table
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cpu_league_seasons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    season_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'not_started',
                    current_round INTEGER DEFAULT 0,
                    max_rounds INTEGER DEFAULT 0,
                    division_count INTEGER DEFAULT 4,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP NULL
                )
            """)
            print("  ✅ Created cpu_league_seasons table")
        except Exception as e:
            print(f"  ❌ Error creating cpu_league_seasons table: {e}")
        
        # CPU League Divisions table
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cpu_league_divisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    season_id INTEGER NOT NULL,
                    division_number INTEGER NOT NULL,
                    team_id INTEGER NOT NULL,
                    team_name TEXT NOT NULL,
                    games_played INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    losses INTEGER DEFAULT 0,
                    goals_for INTEGER DEFAULT 0,
                    goals_against INTEGER DEFAULT 0,
                    points INTEGER DEFAULT 0,
                    FOREIGN KEY (season_id) REFERENCES cpu_league_seasons(id),
                    FOREIGN KEY (team_id) REFERENCES teams(id),
                    UNIQUE(season_id, division_number, team_id)
                )
            """)
            print("  ✅ Created cpu_league_divisions table")
        except Exception as e:
            print(f"  ❌ Error creating cpu_league_divisions table: {e}")
        
        # CPU League Matches table
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cpu_league_matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    season_id INTEGER NOT NULL,
                    division_number INTEGER NOT NULL,
                    round_number INTEGER NOT NULL,
                    home_team_id INTEGER NOT NULL,
                    away_team_id INTEGER NOT NULL,
                    home_score INTEGER DEFAULT 0,
                    away_score INTEGER DEFAULT 0,
                    played BOOLEAN DEFAULT FALSE,
                    played_at TIMESTAMP NULL,
                    FOREIGN KEY (season_id) REFERENCES cpu_league_seasons(id),
                    FOREIGN KEY (home_team_id) REFERENCES teams(id),
                    FOREIGN KEY (away_team_id) REFERENCES teams(id)
                )
            """)
            print("  ✅ Created cpu_league_matches table")
        except Exception as e:
            print(f"  ❌ Error creating cpu_league_matches table: {e}")
        
        # CPU League Scorers table
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cpu_league_scorers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id INTEGER NOT NULL,
                    player_id INTEGER NOT NULL,
                    team_id INTEGER NOT NULL,
                    minute INTEGER NOT NULL,
                    is_goal BOOLEAN DEFAULT TRUE,
                    is_assist BOOLEAN DEFAULT FALSE,
                    FOREIGN KEY (match_id) REFERENCES cpu_league_matches(id),
                    FOREIGN KEY (player_id) REFERENCES players(id),
                    FOREIGN KEY (team_id) REFERENCES teams(id)
                )
            """)
            print("  ✅ Created cpu_league_scorers table")
        except Exception as e:
            print(f"  ❌ Error creating cpu_league_scorers table: {e}")
        
        # League Seasons tracking table
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS league_seasons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    season_name TEXT NOT NULL UNIQUE,
                    is_current BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print("  ✅ League seasons table created successfully")
        except Exception as e:
            print(f"  ❌ Error creating league_seasons table: {e}")
        
        # Player Historical Data table
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS player_season_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_id INTEGER NOT NULL,
                    season TEXT NOT NULL,
                    club_id INTEGER,
                    club_name TEXT,
                    games_played INTEGER DEFAULT 0,
                    goals INTEGER DEFAULT 0,
                    assists INTEGER DEFAULT 0,
                    MVP INTEGER DEFAULT 0,
                    salary INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (player_id) REFERENCES players(id),
                    FOREIGN KEY (club_id) REFERENCES teams(id),
                    UNIQUE(player_id, season)
                )
            """)
            print("  ✅ Created player_season_history table")
        except Exception as e:
            print(f"  ❌ Error creating player_season_history table: {e}")
        
        # Add MVP column to existing player_season_history table if it doesn't exist
        print("\n📊 Adding MVP column to player_season_history table...")
        try:
            cursor.execute("ALTER TABLE player_season_history ADD COLUMN MVP INTEGER DEFAULT 0")
            print("  ✅ Added MVP column to player_season_history table")
        except Exception as e:
            if 'duplicate column name' not in str(e):
                print(f"  ❌ Error adding MVP column to player_season_history: {e}")
            else:
                print("  ℹ️  MVP column already exists in player_season_history table")
        
        # Create player_individual_achievements table
        print("\n🏆 Creating player_individual_achievements table...")
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS player_individual_achievements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_id INTEGER NOT NULL,
                    season TEXT NOT NULL,
                    achievement TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
                    UNIQUE(player_id, season, achievement)
                )
            """)
            print("  ✅ Created player_individual_achievements table")
        except Exception as e:
            print(f"  ❌ Error creating player_individual_achievements table: {e}")
        
        # Create blog_posts table for contract renewal announcements
        print("\n📝 Creating blog_posts table...")
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS blog_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    author_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (author_id) REFERENCES users (id)
                )
            """)
            print("  ✅ Created blog_posts table")
        except Exception as e:
            print(f"  ❌ Error creating blog_posts table: {e}")
        
        # Create retired_players table for Hall of Fame
        print("\n🏆 Creating retired_players table (Hall of Fame)...")
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS retired_players (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_id INTEGER NOT NULL,
                    player_name TEXT NOT NULL,
                    team_name TEXT,
                    age_at_retirement INTEGER,
                    nationality TEXT,
                    registered_position TEXT,
                    retirement_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    retirement_season TEXT,
                    career_earnings INTEGER DEFAULT 0,
                    total_games_played INTEGER DEFAULT 0,
                    total_goals INTEGER DEFAULT 0,
                    total_assists INTEGER DEFAULT 0,
                    final_salary INTEGER DEFAULT 0,
                    final_market_value INTEGER DEFAULT 0,
                    retirement_reason TEXT,
                    seasons_played INTEGER DEFAULT 0,
                    championships_won INTEGER DEFAULT 0,
                    cups_won INTEGER DEFAULT 0,
                    FOREIGN KEY (player_id) REFERENCES players(id)
                )
            """)
            print("  ✅ Created retired_players table")
        except Exception as e:
            print(f"  ❌ Error creating retired_players table: {e}")
        
        # Add retirement_season column to existing retired_players table if it doesn't exist
        try:
            cursor.execute("ALTER TABLE retired_players ADD COLUMN retirement_season TEXT")
            print("  ✅ Added retirement_season column to retired_players table")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("  ℹ️  retirement_season column already exists in retired_players table")
            else:
                print(f"  ❌ Error adding retirement_season column: {e}")
        
        # Create Colados League tables
        print("\n🏆 Creating Colados League tables...")
        try:
            # Leagues table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS leagues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
                )
            """)
            print("  ✅ Created leagues table")
            
            # Divisions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS divisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    league_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    competition_type TEXT NOT NULL DEFAULT 'round_robin',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY (league_id) REFERENCES leagues(id)
                )
            """)
            print("  ✅ Created divisions table")
            
            # Add competition_type column if it doesn't exist (for existing databases)
            try:
                cursor.execute("ALTER TABLE divisions ADD COLUMN competition_type TEXT NOT NULL DEFAULT 'round_robin'")
                print("  ✅ Added competition_type column to divisions table")
            except Exception as e:
                # Column already exists, ignore
                pass
            
            # Division teams table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS division_teams (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    division_id INTEGER NOT NULL,
                    team_id INTEGER NOT NULL,
                    team_name TEXT NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY (division_id) REFERENCES divisions(id),
                    FOREIGN KEY (team_id) REFERENCES teams(id),
                    UNIQUE(division_id, team_id)
                )
            """)
            print("  ✅ Created division_teams table")
            
            # CPU knockout teams table to track teams still in knockout divisions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cpu_knockout_teams (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    division_id INTEGER NOT NULL,
                    team_id INTEGER NOT NULL,
                    round_number INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (division_id) REFERENCES divisions(id) ON DELETE CASCADE,
                    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                    UNIQUE(division_id, team_id, round_number)
                )
            """)
            print("  ✅ Created cpu_knockout_teams table")
            
            # League games table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS league_games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    division_id INTEGER NOT NULL,
                    round_number INTEGER NOT NULL,
                    home_team_id INTEGER NOT NULL,
                    away_team_id INTEGER NOT NULL,
                    home_team_name TEXT NOT NULL,
                    away_team_name TEXT NOT NULL,
                    home_score INTEGER DEFAULT 0,
                    away_score INTEGER DEFAULT 0,
                    game_date TIMESTAMP,
                    is_played BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (division_id) REFERENCES divisions(id),
                    FOREIGN KEY (home_team_id) REFERENCES teams(id),
                    FOREIGN KEY (away_team_id) REFERENCES teams(id)
                )
            """)
            print("  ✅ Created league_games table")
            
            # Player game stats table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS player_game_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id INTEGER NOT NULL,
                    player_id INTEGER NOT NULL,
                    team_id INTEGER NOT NULL,
                    player_name TEXT NOT NULL,
                    goals INTEGER DEFAULT 0,
                    assists INTEGER DEFAULT 0,
                    minutes_played INTEGER DEFAULT 90,
                    is_starter BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (game_id) REFERENCES league_games(id),
                    FOREIGN KEY (player_id) REFERENCES players(id),
                    FOREIGN KEY (team_id) REFERENCES teams(id)
                )
            """)
            print("  ✅ Created player_game_stats table")
            
            # Division standings table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS division_standings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    division_id INTEGER NOT NULL,
                    team_id INTEGER NOT NULL,
                    team_name TEXT NOT NULL,
                    games_played INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    draws INTEGER DEFAULT 0,
                    losses INTEGER DEFAULT 0,
                    goals_for INTEGER DEFAULT 0,
                    goals_against INTEGER DEFAULT 0,
                    goal_difference INTEGER DEFAULT 0,
                    points INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (division_id) REFERENCES divisions(id),
                    FOREIGN KEY (team_id) REFERENCES teams(id),
                    UNIQUE(division_id, team_id)
                )
            """)
            print("  ✅ Created division_standings table")
            
            # Add mvp_player_id column to league_games table if it doesn't exist
            print("\n🏆 Adding mvp_player_id column to league_games table...")
            try:
                cursor.execute("ALTER TABLE league_games ADD COLUMN mvp_player_id INTEGER")
                print("  ✅ Added mvp_player_id column to league_games table")
            except Exception as e:
                if 'duplicate column name' not in str(e):
                    print(f"  ❌ Error adding mvp_player_id column: {e}")
                else:
                    print("  ℹ️  mvp_player_id column already exists in league_games table")
            
            # Insert default league and divisions
            cursor.execute("INSERT OR IGNORE INTO leagues (id, name, description) VALUES (1, 'Colados League', 'The premier user league competition')")
            cursor.execute("INSERT OR IGNORE INTO divisions (id, league_id, name, description) VALUES (1, 1, 'Division 1', 'Top division of Colados League'), (2, 1, 'Division 2', 'Second division of Colados League')")
            print("  ✅ Inserted default league and divisions")
            
        except Exception as e:
            print(f"  ❌ Error creating Colados League tables: {e}")
        
        # Create market_bazaar_listings table for player transfer listings
        print("\n🏪 Creating market_bazaar_listings table...")
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS market_bazaar_listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_id INTEGER NOT NULL,
                    team_id INTEGER NOT NULL,
                    asking_price INTEGER NOT NULL,
                    expires_at TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    listing_type TEXT DEFAULT 'user_sale',
                    salary_support_percentage REAL DEFAULT 0.0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (player_id) REFERENCES players (id),
                    FOREIGN KEY (team_id) REFERENCES teams (id)
                )
            """)
            print("  ✅ Created market_bazaar_listings table")
            
            # Add salary_support_percentage column if it doesn't exist (for existing databases)
            # Check if column exists before trying to add it
            cursor.execute("PRAGMA table_info(market_bazaar_listings)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'salary_support_percentage' not in columns:
                try:
                    cursor.execute("ALTER TABLE market_bazaar_listings ADD COLUMN salary_support_percentage REAL DEFAULT 0.0")
                    print("  ✅ Added salary_support_percentage column to market_bazaar_listings")
                except sqlite3.OperationalError as e:
                    print(f"  ⚠️  Could not add salary_support_percentage column: {e}")
            else:
                print("  ✅ Column salary_support_percentage already exists")
        except Exception as e:
            print(f"  ❌ Error creating market_bazaar_listings table: {e}")
        
        # Create market_bazaar_offers table for transfer offers
        print("\n💰 Creating market_bazaar_offers table...")
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS market_bazaar_offers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    listing_id INTEGER NOT NULL,
                    buyer_team_id INTEGER NOT NULL,
                    offered_price INTEGER NOT NULL,
                    expires_at TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (listing_id) REFERENCES market_bazaar_listings (id),
                    FOREIGN KEY (buyer_team_id) REFERENCES teams (id)
                )
            """)
            print("  ✅ Created market_bazaar_offers table")
        except Exception as e:
            print(f"  ❌ Error creating market_bazaar_offers table: {e}")
        
        # Create user_cpu_offers table for user-to-CPU negotiations
        # Ensure team_id exists on free_agent_offers so CPU teams can outbid each other
        print("\n🔄 Ensuring team_id on free_agent_offers...")
        try:
            cursor.execute("PRAGMA table_info(free_agent_offers)")
            fo_cols = [row[1] for row in cursor.fetchall()]
            if 'team_id' not in fo_cols:
                cursor.execute("ALTER TABLE free_agent_offers ADD COLUMN team_id INTEGER NULL")
                print("  ✅ Added team_id to free_agent_offers")
            else:
                print("  ℹ️  team_id already present on free_agent_offers")
        except Exception as e:
            print(f"  ❌ Error ensuring team_id on free_agent_offers: {e}")

        print("\n🤝 Creating user_cpu_offers table...")
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_cpu_offers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    buyer_team_id INTEGER NOT NULL,
                    seller_team_id INTEGER NOT NULL,
                    player_id INTEGER NOT NULL,
                    offered_price INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (buyer_team_id) REFERENCES league_teams (id),
                    FOREIGN KEY (seller_team_id) REFERENCES teams (id),
                    FOREIGN KEY (player_id) REFERENCES players (id)
                )
            """)
            print("  ✅ Created user_cpu_offers table")
        except Exception as e:
            print(f"  ❌ Error creating user_cpu_offers table: {e}")
        
        # Create team_historical_data table for team achievements
        print("\n🏆 Creating team_historical_data table...")
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS team_historical_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    team_id INTEGER NOT NULL,
                    season TEXT NOT NULL,
                    competition TEXT NOT NULL,
                    place TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (team_id) REFERENCES teams (id),
                    UNIQUE(team_id, season, competition)
                )
            """)
            print("  ✅ Created team_historical_data table")
        except Exception as e:
            print(f"  ❌ Error creating team_historical_data table: {e}")
        
        # Create draft_picks table for user draft picks
        print("\n🎯 Creating draft_picks table...")
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS draft_picks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    season TEXT NOT NULL,
                    pick_number INTEGER NOT NULL CHECK (pick_number IN (1, 2, 3)),
                    original_user_id INTEGER NOT NULL,
                    is_expired INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (original_user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(original_user_id, season, pick_number)
                )
            """)
            print("  ✅ Created draft_picks table")
        except Exception as e:
            print(f"  ❌ Error creating draft_picks table: {e}")
        
        # Create team_preferred_lineup table for CPU league preferred 11
        print("\n⚽ Creating team_preferred_lineup table...")
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS team_preferred_lineup (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    team_id INTEGER NOT NULL,
                    slot_number INTEGER NOT NULL CHECK (slot_number BETWEEN 1 AND 11),
                    player_id INTEGER NOT NULL,
                    position_group TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
                    UNIQUE(team_id, slot_number)
                )
            """)
            print("  ✅ Created team_preferred_lineup table")
        except Exception as e:
            print(f"  ❌ Error creating team_preferred_lineup table: {e}")
        
        # Create international_teams table for international squads
        print("\n🌍 Creating international_teams table...")
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS international_teams (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nationality TEXT NOT NULL UNIQUE,
                    team_name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print("  ✅ Created international_teams table")
        except Exception as e:
            print(f"  ❌ Error creating international_teams table: {e}")
        
        # Create international_team_players table to link players to international teams
        print("\n👥 Creating international_team_players table...")
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS international_team_players (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    international_team_id INTEGER NOT NULL,
                    player_id INTEGER NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (international_team_id) REFERENCES international_teams(id) ON DELETE CASCADE,
                    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
                    UNIQUE(international_team_id, player_id)
                )
            """)
            print("  ✅ Created international_team_players table")
        except Exception as e:
            print(f"  ❌ Error creating international_team_players table: {e}")
        
        # Create international_competitions table
        print("\n🏆 Creating international_competitions table...")
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS international_competitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    competition_type TEXT NOT NULL DEFAULT 'friendly',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
                )
            """)
            print("  ✅ Created international_competitions table")
        except Exception as e:
            print(f"  ❌ Error creating international_competitions table: {e}")
        
        # Create international_games table
        print("\n⚽ Creating international_games table...")
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS international_games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    competition_id INTEGER NOT NULL,
                    round_number INTEGER NOT NULL,
                    home_team_id INTEGER NOT NULL,
                    away_team_id INTEGER NOT NULL,
                    home_team_name TEXT NOT NULL,
                    away_team_name TEXT NOT NULL,
                    home_score INTEGER DEFAULT 0,
                    away_score INTEGER DEFAULT 0,
                    game_date TIMESTAMP,
                    is_played BOOLEAN DEFAULT 0,
                    mvp_player_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (competition_id) REFERENCES international_competitions(id),
                    FOREIGN KEY (home_team_id) REFERENCES international_teams(id),
                    FOREIGN KEY (away_team_id) REFERENCES international_teams(id),
                    FOREIGN KEY (mvp_player_id) REFERENCES players(id)
                )
            """)
            print("  ✅ Created international_games table")
        except Exception as e:
            print(f"  ❌ Error creating international_games table: {e}")
        
        # Create international_player_game_stats table
        print("\n📊 Creating international_player_game_stats table...")
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS international_player_game_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id INTEGER NOT NULL,
                    player_id INTEGER NOT NULL,
                    team_id INTEGER NOT NULL,
                    player_name TEXT NOT NULL,
                    goals INTEGER DEFAULT 0,
                    assists INTEGER DEFAULT 0,
                    minutes_played INTEGER DEFAULT 90,
                    is_starter BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (game_id) REFERENCES international_games(id),
                    FOREIGN KEY (player_id) REFERENCES players(id),
                    FOREIGN KEY (team_id) REFERENCES international_teams(id)
                )
            """)
            print("  ✅ Created international_player_game_stats table")
        except Exception as e:
            print(f"  ❌ Error creating international_player_game_stats table: {e}")
        
        # Create international_squad_callups table to store 23-player squads
        print("\n👥 Creating international_squad_callups table...")
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS international_squad_callups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    international_team_id INTEGER NOT NULL,
                    player_id INTEGER NOT NULL,
                    position_group TEXT NOT NULL,
                    is_fake_player INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (international_team_id) REFERENCES international_teams(id) ON DELETE CASCADE,
                    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
                    UNIQUE(international_team_id, player_id)
                )
            """)
            print("  ✅ Created international_squad_callups table")
        except Exception as e:
            print(f"  ❌ Error creating international_squad_callups table: {e}")
        
        # Create international_competition_teams table to link teams to competitions
        print("\n🏆 Creating international_competition_teams table...")
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS international_competition_teams (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    competition_id INTEGER NOT NULL,
                    international_team_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (competition_id) REFERENCES international_competitions(id) ON DELETE CASCADE,
                    FOREIGN KEY (international_team_id) REFERENCES international_teams(id) ON DELETE CASCADE,
                    UNIQUE(competition_id, international_team_id)
                )
            """)
            print("  ✅ Created international_competition_teams table")
        except Exception as e:
            print(f"  ❌ Error creating international_competition_teams table: {e}")
        
        # Create international_knockout_teams table to track teams still in knockout competitions
        print("\n🏆 Creating international_knockout_teams table...")
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS international_knockout_teams (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    competition_id INTEGER NOT NULL,
                    international_team_id INTEGER NOT NULL,
                    round_number INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (competition_id) REFERENCES international_competitions(id) ON DELETE CASCADE,
                    FOREIGN KEY (international_team_id) REFERENCES international_teams(id) ON DELETE CASCADE,
                    UNIQUE(competition_id, international_team_id, round_number)
                )
            """)
            print("  ✅ Created international_knockout_teams table")
        except Exception as e:
            print(f"  ❌ Error creating international_knockout_teams table: {e}")
        
        # Create temp_players table for fake/temporary players (separate from real players)
        print("\n👤 Creating temp_players table...")
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS temp_players (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_name TEXT NOT NULL,
                    age INTEGER DEFAULT 25,
                    nationality TEXT,
                    registered_position TEXT,
                    club_id INTEGER,
                    overall INTEGER DEFAULT 65,
                    height INTEGER DEFAULT 180,
                    weight INTEGER DEFAULT 75,
                    strong_foot TEXT DEFAULT 'Right',
                    favoured_side TEXT DEFAULT 'Right',
                    attack INTEGER DEFAULT 65,
                    defense INTEGER DEFAULT 65,
                    balance INTEGER DEFAULT 65,
                    stamina INTEGER DEFAULT 65,
                    top_speed INTEGER DEFAULT 65,
                    acceleration INTEGER DEFAULT 65,
                    response INTEGER DEFAULT 65,
                    agility INTEGER DEFAULT 65,
                    dribble_accuracy INTEGER DEFAULT 65,
                    dribble_speed INTEGER DEFAULT 65,
                    short_pass_accuracy INTEGER DEFAULT 65,
                    short_pass_speed INTEGER DEFAULT 65,
                    long_pass_accuracy INTEGER DEFAULT 65,
                    long_pass_speed INTEGER DEFAULT 65,
                    shot_accuracy INTEGER DEFAULT 65,
                    shot_power INTEGER DEFAULT 65,
                    shot_technique INTEGER DEFAULT 65,
                    free_kick_accuracy INTEGER DEFAULT 65,
                    swerve INTEGER DEFAULT 65,
                    heading INTEGER DEFAULT 65,
                    jump INTEGER DEFAULT 65,
                    technique INTEGER DEFAULT 65,
                    aggression INTEGER DEFAULT 65,
                    mentality INTEGER DEFAULT 65,
                    goal_keeping INTEGER DEFAULT 65,
                    team_work INTEGER DEFAULT 65,
                    consistency INTEGER DEFAULT 65,
                    condition_fitness INTEGER DEFAULT 65,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print("  ✅ Created temp_players table")
            
            # Add club_id column if table already existed without it
            try:
                cursor.execute("ALTER TABLE temp_players ADD COLUMN club_id INTEGER")
                print("  ✅ Added club_id column to temp_players table")
            except Exception as e:
                # Column already exists, ignore
                if "duplicate column name" not in str(e).lower():
                    print(f"  ℹ️  club_id column: {e}")
        except Exception as e:
            print(f"  ❌ Error creating temp_players table: {e}")
        
        # Insert default "International Friendlies" competition if it doesn't exist
        try:
            cursor.execute("INSERT OR IGNORE INTO international_competitions (id, name, competition_type, is_active) VALUES (1, 'International Friendlies', 'friendly', 1)")
            print("  ✅ Inserted default International Friendlies competition")
        except Exception as e:
            print(f"  ⚠️  Could not insert default competition: {e}")
        
        # Create app_settings table
        print("\n🔄 Creating app_settings table...")
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print("  ✅ Created app_settings table")
        except Exception as e:
            print(f"  ❌ Error creating app_settings table: {e}")
        
        # Add loaned_by column to players table
        print("\n🔄 Adding loaned_by column to players table...")
        try:
            cursor.execute("ALTER TABLE players ADD COLUMN loaned_by TEXT DEFAULT NULL")
            print("  ✅ Added loaned_by column to players table")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("  ✅ loaned_by column already exists in players table")
            else:
                print(f"  ❌ Error adding loaned_by column: {e}")
        
        # Initialize first season if none exists
        try:
            cursor.execute("SELECT COUNT(*) FROM league_seasons")
            season_count = cursor.fetchone()[0]
            if season_count == 0:
                cursor.execute("""
                    INSERT INTO league_seasons (season_name, is_current) 
                    VALUES ('00/01', 1)
                """)
                print("  ✅ Initialized first season: 00/01")
        except Exception as e:
            print(f"  ❌ Error initializing first season: {e}")
        
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
        
        # Recalculate overall ratings for all players
        recalculate_all_overalls()
        
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
        initialized_count = 0
        for team_id, club_name in cpu_teams:
            # Get current budget - don't overwrite if it exists
            cursor.execute("SELECT budget, total_salaries FROM teams WHERE id = ?", (team_id,))
            team_data = cursor.fetchone()
            current_budget = team_data[0] if team_data and team_data[0] is not None else None
            current_total_salaries = team_data[1] if team_data and team_data[1] is not None else None
            
            # Calculate total salaries for this team
            cursor.execute("SELECT COALESCE(SUM(salary), 0) as total_salaries FROM players WHERE club_id = ?", (team_id,))
            result = cursor.fetchone()
            total_salaries = result[0] if result else 0
            
            # Only update budget if it's NULL/0 (not initialized) - preserve existing budgets
            if current_budget is None or current_budget == 0:
                # Initialize budget equal to total salaries
                budget = total_salaries
                initialized_count += 1
            else:
                # Preserve existing budget - only update total_salaries and available_cap
                budget = current_budget
            
            # Calculate available cap based on current budget
            available_cap = budget - total_salaries if budget else 0
            
            # Update team financial data - preserve budget if it exists
            if current_budget is None or current_budget == 0:
                # Full update including budget initialization
                cursor.execute("""
                    UPDATE teams 
                    SET total_salaries = ?, budget = ?, available_cap = ?
                    WHERE id = ?
                """, (total_salaries, budget, available_cap, team_id))
                print(f"  ✅ {club_name}: Initialized budget €{budget:,}, salaries €{total_salaries:,}, cap €{available_cap:,}")
            else:
                # Only update total_salaries and available_cap, preserve budget
                cursor.execute("""
                    UPDATE teams 
                    SET total_salaries = ?, available_cap = ?
                    WHERE id = ?
                """, (total_salaries, available_cap, team_id))
                print(f"  ℹ️  {club_name}: Preserved budget €{current_budget:,}, updated salaries €{total_salaries:,}, cap €{available_cap:,}")
            
            updated_count += 1
        
        conn.commit()
        print(f"\n✅ Financial data updated for {updated_count} CPU teams.")
        if initialized_count > 0:
            print(f"   - {initialized_count} teams had budgets initialized (were NULL/0)")
        if updated_count - initialized_count > 0:
            print(f"   - {updated_count - initialized_count} teams had budgets preserved (existing values maintained)")
        
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
        
    except Exception as e:
        print(f"Error executing schema script: {e}")
    
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
        conn.commit()
    except Exception as e:
        print(f"Error adding columns: {e}")
    
    # Add Colados League schema
    try:
        print("🏆 Adding Colados League schema...")
        with open('colados_league_schema.sql', 'r') as f:
            colados_schema = f.read()
        cursor.executescript(colados_schema)
        conn.commit()
        print("✅ Colados League schema added successfully.")
    except Exception as e:
        print(f"❌ Error adding Colados League schema: {e}")
    
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
    print('🗑️  Clearing blacklist (preserving loaned players and draftees)...')
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON;')
    cursor = conn.cursor()
    
    # Clear blacklist except for loaned players and draftees
    cursor.execute("""
        DELETE FROM blacklist
        WHERE player_id NOT IN (
            SELECT id FROM players
            WHERE (loaned_by IS NOT NULL AND loaned_by != '') OR draftee = 1
        )
    """)
    
    cleared_count = cursor.rowcount
    conn.commit()
    cursor.close()
    conn.close()
    print(f'✅ Blacklist cleared ({cleared_count} entries removed, loaned/draftee players preserved).')

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
        
        # Calculate bundled skill ratings (updated formulas)
        attack_rating = (player_data['attack'] + player_data['shot_technique'] + 
                        player_data['shot_accuracy'] + player_data['aggression']) // 4
        
        defense_rating = (player_data['defense'] + player_data['heading'] + 
                         player_data['jump'] + player_data['balance']) // 4
        
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
        # Do not overwrite existing budgets
        cursor.execute("SELECT user_id FROM user_budgets WHERE user_id = ?", (user_id,))
        if cursor.fetchone():
            continue

        # Insert snapshot matching /finances display: 450M base + SUM(user_movements)
        cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM user_movements WHERE user_id = ?", (user_id,))
        total_movements = cursor.fetchone()[0] or 0
        current_budget_snapshot = 450000000 + total_movements

        cursor.execute(
            """
            INSERT INTO user_budgets (user_id, budget, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, current_budget_snapshot, datetime.now().isoformat(), datetime.now().isoformat())
        )
        print(f"  - Initialized budget for {username} (snapshot €{current_budget_snapshot:,})")
    
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