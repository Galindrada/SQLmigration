#!/usr/bin/env python3
"""
Team Management Script
Allows direct database access to transfer teams between users and CPU teams.
"""

import sqlite3
import sys
import pandas as pd
from typing import List, Dict, Optional
import os

class TeamManager:
    def __init__(self, db_path: str = 'pes6_league_db.sqlite'):
        self.db_path = db_path
        self.conn = None
    
    def connect(self):
        """Connect to the database"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
            print(f"✅ Connected to database: {self.db_path}")
            return True
        except Exception as e:
            print(f"❌ Error connecting to database: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the database"""
        if self.conn:
            self.conn.close()
            print("✅ Disconnected from database")
    
    def get_all_users(self) -> List[Dict]:
        """Get all users from the database"""
        if not self.conn:
            return []
        
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, username, email FROM users WHERE id != 1 ORDER BY id")
        users = cursor.fetchall()
        
        return [dict(user) for user in users]
    
    def get_cpu_teams(self) -> List[Dict]:
        """Get all CPU teams (teams without user ownership)"""
        if not self.conn:
            return []
        
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT t.id, t.club_name, t.budget, t.available_cap, t.stance
            FROM teams t
            LEFT JOIN league_teams lt ON t.club_name = lt.team_name
            WHERE lt.user_id IS NULL OR lt.user_id = 1
            ORDER BY t.club_name
        """)
        teams = cursor.fetchall()
        
        return [dict(team) for team in teams]
    
    def get_user_teams(self, user_id: int) -> List[Dict]:
        """Get all teams owned by a specific user"""
        if not self.conn:
            return []
        
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT t.id, t.club_name, t.budget, t.available_cap, t.stance
            FROM teams t
            JOIN league_teams lt ON t.club_name = lt.team_name
            WHERE lt.user_id = ?
            ORDER BY t.club_name
        """, (user_id,))
        teams = cursor.fetchall()
        
        return [dict(team) for team in teams]
    
    def get_all_teams(self) -> List[Dict]:
        """Get all teams with their ownership information"""
        if not self.conn:
            return []
        
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT t.id, t.club_name, t.budget, t.available_cap, t.stance,
                   lt.user_id, u.username
            FROM teams t
            LEFT JOIN league_teams lt ON t.club_name = lt.team_name
            LEFT JOIN users u ON lt.user_id = u.id
            ORDER BY t.club_name
        """)
        teams = cursor.fetchall()
        
        return [dict(team) for team in teams]
    
    def transfer_team_to_user(self, team_id: int, user_id: int) -> bool:
        """Transfer a team to a user (from CPU to user)"""
        if not self.conn:
            return False
        
        try:
            cursor = self.conn.cursor()
            
            # Get team name
            cursor.execute("SELECT club_name FROM teams WHERE id = ?", (team_id,))
            team_result = cursor.fetchone()
            if not team_result:
                print(f"❌ Team with ID {team_id} not found")
                return False
            
            team_name = team_result['club_name']
            
            # Check if team is already owned by a user
            cursor.execute("SELECT user_id FROM league_teams WHERE team_name = ?", (team_name,))
            existing_owner = cursor.fetchone()
            
            if existing_owner and existing_owner['user_id'] != 1:
                print(f"❌ Team '{team_name}' is already owned by user ID {existing_owner['user_id']}")
                return False
            
            # Update or insert league_teams entry
            cursor.execute("""
                INSERT OR REPLACE INTO league_teams (team_name, user_id)
                VALUES (?, ?)
            """, (team_name, user_id))
            
            self.conn.commit()
            print(f"✅ Successfully transferred team '{team_name}' to user ID {user_id}")
            return True
            
        except Exception as e:
            print(f"❌ Error transferring team: {e}")
            self.conn.rollback()
            return False
    
    def transfer_team_to_cpu(self, team_id: int) -> bool:
        """Transfer a team to CPU (remove user ownership)"""
        if not self.conn:
            return False
        
        try:
            cursor = self.conn.cursor()
            
            # Get team name
            cursor.execute("SELECT club_name FROM teams WHERE id = ?", (team_id,))
            team_result = cursor.fetchone()
            if not team_result:
                print(f"❌ Team with ID {team_id} not found")
                return False
            
            team_name = team_result['club_name']
            
            # Check if team exists in league_teams
            cursor.execute("SELECT id FROM league_teams WHERE id = ?", (team_id,))
            league_team_result = cursor.fetchone()
            
            if league_team_result:
                # Update existing league_teams entry to CPU ownership
                cursor.execute("""
                    UPDATE league_teams 
                    SET user_id = 1 
                    WHERE id = ?
                """, (team_id,))
                print(f"✅ Updated existing league_teams entry for team '{team_name}' to CPU ownership")
            else:
                # Create new league_teams entry for CPU ownership
                cursor.execute("""
                    INSERT INTO league_teams (id, team_name, user_id)
                    VALUES (?, ?, 1)
                """, (team_id, team_name))
                print(f"✅ Created new league_teams entry for team '{team_name}' with CPU ownership")
            
            self.conn.commit()
            print(f"✅ Successfully transferred team '{team_name}' to CPU")
            return True
            
        except Exception as e:
            print(f"❌ Error transferring team: {e}")
            self.conn.rollback()
            return False
    
    def create_new_team_for_user(self, team_name: str, user_id: int, budget: int = 10000000) -> bool:
        """Create a new team and assign it to a user"""
        if not self.conn:
            return False
        
        try:
            cursor = self.conn.cursor()
            
            # Check if team name already exists
            cursor.execute("SELECT id FROM teams WHERE club_name = ?", (team_name,))
            if cursor.fetchone():
                print(f"❌ Team '{team_name}' already exists")
                return False
            
            # Create new team
            cursor.execute("""
                INSERT INTO teams (club_name, budget, available_cap, stance, total_salaries)
                VALUES (?, ?, ?, 'Tinkering', 0)
            """, (team_name, budget, budget))
            
            team_id = cursor.lastrowid
            
            # Assign to user
            cursor.execute("""
                INSERT INTO league_teams (team_name, user_id)
                VALUES (?, ?)
            """, (team_name, user_id))
            
            self.conn.commit()
            print(f"✅ Successfully created team '{team_name}' with ID {team_id} and assigned to user ID {user_id}")
            return True
            
        except Exception as e:
            print(f"❌ Error creating team: {e}")
            self.conn.rollback()
            return False
    
    def modify_team_budget(self, team_id: int, amount: int, operation: str) -> bool:
        """Add or subtract budget from a team"""
        if not self.conn:
            return False
        
        try:
            cursor = self.conn.cursor()
            
            # Get current team budget
            cursor.execute("SELECT club_name, budget, available_cap, total_salaries FROM teams WHERE id = ?", (team_id,))
            team_result = cursor.fetchone()
            if not team_result:
                print(f"❌ Team with ID {team_id} not found")
                return False
            
            team_name = team_result['club_name']
            current_budget = team_result['budget']
            current_available_cap = team_result['available_cap']
            total_salaries = team_result['total_salaries']
            
            # Calculate new budget
            if operation == 'add':
                new_budget = current_budget + amount
                new_available_cap = current_available_cap + amount
                operation_text = f"added €{amount:,}"
            elif operation == 'subtract':
                new_budget = current_budget - amount
                new_available_cap = current_available_cap - amount
                operation_text = f"subtracted €{amount:,}"
            else:
                print("❌ Invalid operation. Use 'add' or 'subtract'")
                return False
            
            # Check if budget would go negative
            if new_budget < 0:
                print(f"❌ Cannot subtract €{amount:,} from budget €{current_budget:,} (would result in negative budget)")
                return False
            
            # Update team budget
            cursor.execute("""
                UPDATE teams 
                SET budget = ?, available_cap = ?
                WHERE id = ?
            """, (new_budget, new_available_cap, team_id))
            
            self.conn.commit()
            print(f"✅ Successfully {operation_text} from team '{team_name}' (ID: {team_id})")
            print(f"   Budget: €{current_budget:,} → €{new_budget:,}")
            print(f"   Available Cap: €{current_available_cap:,} → €{new_available_cap:,}")
            return True
            
        except Exception as e:
            print(f"❌ Error modifying team budget: {e}")
            self.conn.rollback()
            return False
    
    def update_players_from_newcomers_csv_range(self, csv_path: str = 'NewcomerII.csv', id_start: int = 1, id_end: int = 99999) -> bool:
        """Update players from CSV file for a specific ID range, mark as draftees and blacklist them.
        
        Args:
            csv_path: Path to the CSV file
            id_start: Starting player ID (inclusive)
            id_end: Ending player ID (inclusive)
        
        Returns:
            True if successful, False otherwise
        """
        if not self.conn:
            print("❌ Not connected to database")
            return False
        
        try:
            # Read the newcomers CSV
            print(f"📖 Reading newcomer data from {csv_path}...")
            df = pd.read_csv(csv_path, encoding='latin1')
            
            # Use the same column mapping from import_pes6_data.py
            raw_to_sql_column_map = {
                'ID': 'id',
                'NAME': 'player_name',
                'SHIRT_NAME': 'shirt_name',
                'CLUB TEAM': 'club_team_raw',
                'REGISTERED POSITION': 'registered_position',
                'HEIGHT': 'height',
                'STRONG FOOT': 'strong_foot',
                'FAVOURED SIDE': 'favoured_side',
                'WEAK FOOT ACCURACY': 'weak_foot_accuracy',
                'WEAK FOOT FREQUENCY': 'weak_foot_frequency',
                'ATTACK': 'attack',
                'DEFENSE': 'defense',
                'BALANCE': 'balance',
                'STAMINA': 'stamina',
                'TOP SPEED': 'top_speed',
                'ACCELERATION': 'acceleration',
                'RESPONSE': 'response',
                'AGILITY': 'agility',
                'DRIBBLE ACCURACY': 'dribble_accuracy',
                'DRIBBLE SPEED': 'dribble_speed',
                'SHORT PASS ACCURACY': 'short_pass_accuracy',
                'SHORT PASS SPEED': 'short_pass_speed',
                'LONG PASS ACCURACY': 'long_pass_accuracy',
                'LONG PASS SPEED': 'long_pass_speed',
                'SHOT ACCURACY': 'shot_accuracy',
                'SHOT POWER': 'shot_power',
                'SHOT TECHNIQUE': 'shot_technique',
                'FREE KICK ACCURACY': 'free_kick_accuracy',
                'SWERVE': 'swerve',
                'HEADING': 'heading',
                'JUMP': 'jump',
                'TECHNIQUE': 'technique',
                'AGGRESSION': 'aggression',
                'MENTALITY': 'mentality',
                'GOAL KEEPING': 'goal_keeping',
                'TEAM WORK': 'team_work',
                'CONSISTENCY': 'consistency',
                'CONDITION / FITNESS': 'condition_fitness',
                'DRIBBLING': 'dribbling_skill',
                'TACTIAL DRIBBLE': 'tactical_dribble',
                'POSITIONING': 'positioning',
                'REACTION': 'reaction',
                'PLAYMAKING': 'playmaking',
                'PASSING': 'passing',
                'SCORING': 'scoring',
                '1-1 SCORING': 'one_one_scoring',
                'POST PLAYER': 'post_player',
                'LINES': 'lines',
                'MIDDLE SHOOTING': 'middle_shooting',
                'SIDE': 'side',
                'CENTRE': 'centre',
                'PENALTIES': 'penalties',
                '1-TOUCH PASS': 'one_touch_pass',
                'OUTSIDE': 'outside',
                'MARKING': 'marking',
                'SLIDING': 'sliding',
                'COVERING': 'covering',
                'D-LINE CONTROL': 'd_line_control',
                'PENALTY STOPPER': 'penalty_stopper',
                '1-ON-1 STOPPER': 'one_on_one_stopper',
                'LONG THROW': 'long_throw',
                'INJURY TOLERANCE': 'injury_tolerance',
                'DRIBBLE STYLE': 'dribble_style',
                'FREE KICK STYLE': 'free_kick_style',
                'PK STYLE': 'pk_style',
                'DROP KICK STYLE': 'drop_kick_style',
                'AGE': 'age',
                'WEIGHT': 'weight',
                'NATIONALITY': 'nationality',
                'SKIN COLOR': 'skin_color',
                'FACE TYPE': 'face_type',
                'PRESET FACE NUMBER': 'preset_face_number',
                'HEAD WIDTH': 'head_width',
                'NECK LENGTH': 'neck_length',
                'NECK WIDTH': 'neck_width',
                'SHOULDER HEIGHT': 'shoulder_height',
                'SHOULDER WIDTH': 'shoulder_width',
                'CHEST MEASUREMENT': 'chest_measurement',
                'WAIST CIRCUMFERENCE': 'waist_circumference',
                'ARM CIRCUMFERENCE': 'arm_circumference',
                'LEG CIRCUMFERENCE': 'leg_circumference',
                'CALF CIRCUMFERENCE': 'calf_circumference',
                'LEG LENGTH': 'leg_length',
                'WRISTBAND': 'wristband',
                'WRISTBAND COLOR': 'wristband_color',
                'INTERNATIONAL NUMBER': 'international_number',
                'CLASSIC NUMBER': 'classic_number',
                'CLUB NUMBER': 'club_number',
                'GK  0': 'gk',
                'CWP  2': 'cwp',
                'CBT  3': 'cbt',
                'SB  4': 'sb',
                'DMF  5': 'dmf',
                'WB  6': 'wb',
                'CMF  7': 'cmf',
                'SMF  8': 'smf',
                'AMF  9': 'amf',
                'WF 10': 'wf',
                'SS  11': 'ss',
                'CF  12': 'cf'
            }
            
            # Rename columns in the DataFrame using the map
            df = df.rename(columns=raw_to_sql_column_map)
            
            # Filter to only IDs in the specified range
            df = df[(df['id'] >= id_start) & (df['id'] <= id_end)]
            
            if len(df) == 0:
                print(f"❌ No players found in ID range {id_start}-{id_end} in CSV")
                return False
            
            print(f"📋 Found {len(df)} players in range {id_start}-{id_end}")
            
            cursor = self.conn.cursor()
            
            updates_made = 0
            blacklisted = 0
            
            for _, row in df.iterrows():
                player_id = row['id']
                csv_name = row['player_name']
                
                # Check if player exists in database
                cursor.execute("SELECT id, player_name FROM players WHERE id = ?", (player_id,))
                existing_player = cursor.fetchone()
                
                if not existing_player:
                    print(f"⚠️  Player ID {player_id} not found in database - skipping")
                    continue
                
                print(f"🔄 Updating Player ID {player_id}: '{existing_player[1]}' → '{csv_name}' (newcomer/draftee)")
                
                # Prepare all columns for update (excluding club_team_raw which we'll set to No Club)
                sql_columns = [
                    'player_name', 'shirt_name', 'registered_position', 'age', 'height', 'weight',
                    'nationality', 'strong_foot', 'favoured_side', 'gk', 'cwp', 'cbt', 'sb', 'dmf',
                    'wb', 'cmf', 'smf', 'amf', 'wf', 'ss', 'cf',
                    'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration', 'response', 
                    'agility', 'dribble_accuracy', 'dribble_speed', 'short_pass_accuracy', 'short_pass_speed', 
                    'long_pass_accuracy', 'long_pass_speed', 'shot_accuracy', 'shot_power', 'shot_technique', 
                    'free_kick_accuracy', 'swerve', 'heading', 'jump', 'technique', 'aggression', 'mentality', 
                    'goal_keeping', 'team_work', 'consistency', 'condition_fitness', 'dribbling_skill', 
                    'tactical_dribble', 'positioning', 'reaction', 'playmaking', 'passing', 'scoring',
                    'one_one_scoring', 'post_player', 'lines', 'middle_shooting', 'side', 'centre',
                    'penalties', 'one_touch_pass', 'outside', 'marking', 'sliding', 'covering',
                    'd_line_control', 'penalty_stopper', 'one_on_one_stopper', 'long_throw',
                    'injury_tolerance', 'dribble_style', 'free_kick_style', 'pk_style', 'drop_kick_style',
                    'skin_color', 'face_type', 'preset_face_number', 'head_width', 'neck_length',
                    'neck_width', 'shoulder_height', 'shoulder_width', 'chest_measurement',
                    'waist_circumference', 'arm_circumference', 'leg_circumference', 'calf_circumference',
                    'leg_length', 'wristband', 'wristband_color', 'international_number',
                    'classic_number', 'club_number'
                ]
                
                # Add newcomer-specific columns
                sql_columns.extend(['club_id', 'draftee', 'contract_years_remaining', 'salary', 
                                  'yearly_wage_rise', 'career_earnings'])
                
                # Prepare values for update
                values = []
                for col in sql_columns:
                    if col == 'club_id':
                        values.append(141)  # No Club
                    elif col == 'draftee':
                        values.append(1)  # Mark as draftee
                    elif col == 'contract_years_remaining':
                        values.append(3)
                    elif col == 'salary':
                        values.append(1000000)
                    elif col == 'yearly_wage_rise':
                        values.append(0.25)
                    elif col == 'career_earnings':
                        values.append(0)
                    else:
                        val = row.get(col, None)
                        values.append(None if pd.isna(val) else val)
                
                # Add player_id for WHERE clause
                values.append(player_id)
                
                # Create UPDATE query
                set_clause = ', '.join([f"{col} = ?" for col in sql_columns])
                update_query = f"UPDATE players SET {set_clause} WHERE id = ?"
                
                # Execute update
                cursor.execute(update_query, values)
                
                # Add to blacklist
                cursor.execute("SELECT 1 FROM blacklist WHERE user_id = 1 AND player_id = ?", (player_id,))
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO blacklist (user_id, player_id) VALUES (1, ?)", (player_id,))
                    blacklisted += 1
                
                updates_made += 1
            
            # Commit all changes
            self.conn.commit()
            
            print(f"\n✅ Update complete!")
            print(f"   🔄 Players updated: {updates_made}")
            print(f"   🔒 Players blacklisted: {blacklisted}")
            print(f"   🌟 All updated players marked as draftees in No Club")
            
            # Calculate overalls and bundled ratings for updated players
            if updates_made > 0:
                calc_ratings = input(f"\n📊 Calculate overall and bundled ratings for the {updates_made} updated players? (y/N): ").strip().lower()
                if calc_ratings == 'y':
                    print("\n🔄 Calculating ratings...")
                    from refresh_and_reimport import calculate_player_overall
                    from game_mechanics import calculate_bundled_skill_ratings
                    
                    # Get updated players
                    cursor.execute("""
                        SELECT * FROM players 
                        WHERE id >= ? AND id <= ?
                    """, (id_start, id_end))
                    
                    players = cursor.fetchall()
                    column_names = [description[0] for description in cursor.description]
                    
                    for player_row in players:
                        player_data = dict(zip(column_names, player_row))
                        
                        # Calculate overall
                        overall = calculate_player_overall(player_data)
                        
                        # Calculate bundled ratings
                        bundled_ratings = calculate_bundled_skill_ratings(player_data)
                        
                        # Update database
                        cursor.execute("""
                            UPDATE players 
                            SET overall = ?, attack_rating = ?, defense_rating = ?, physical_rating = ?, 
                                power_rating = ?, technique_rating = ?, goalkeeping_rating = ?
                            WHERE id = ?
                        """, (
                            overall,
                            bundled_ratings['attack_rating'],
                            bundled_ratings['defense_rating'],
                            bundled_ratings['physical_rating'],
                            bundled_ratings['power_rating'],
                            bundled_ratings['technique_rating'],
                            bundled_ratings['goalkeeping_rating'],
                            player_data['id']
                        ))
                    
                    self.conn.commit()
                    print(f"   ✅ Overall and bundled ratings calculated for {updates_made} players")
            
            return True
            
        except FileNotFoundError:
            print(f"❌ File not found: {csv_path}")
            return False
        except Exception as e:
            print(f"❌ Error updating players: {e}")
            import traceback
            traceback.print_exc()
            if self.conn:
                self.conn.rollback()
            return False
    
    def update_players_from_newcomers_csv(self, csv_path: str = 'newcomers.csv') -> bool:
        """Update players from newcomers.csv when their name differs from pe6_player_data.csv (by ID).

        - Reads newcomers.csv (new attributes)
        - Reads pe6_player_data.csv (baseline/original names)
        - For each ID present in newcomers.csv, if newcomer's NAME != original CSV NAME (case-insensitive),
          then update the connected DB row (players) for that ID using newcomer's attributes.
        """
        if not self.conn:
            print("❌ Not connected to database")
            return False
        
        try:
            # Read the newcomers CSV with the same mapping as import_pes6_data.py
            print(f"📖 Reading newcomers data from {csv_path}...")
            df = pd.read_csv(csv_path, encoding='latin1')

            # Read baseline original CSV to compare names by ID
            print("📖 Reading baseline data from pe6_player_data.csv for name comparison...")
            try:
                df_original_raw = pd.read_csv('pe6_player_data.csv', encoding='latin-1')
            except FileNotFoundError:
                print("❌ pe6_player_data.csv not found. Cannot perform comparison against original CSV.")
                return False
            
            # Use the same column mapping from import_pes6_data.py
            raw_to_sql_column_map = {
                'ID': 'id',
                'NAME': 'player_name',
                'SHIRT_NAME': 'shirt_name',
                'CLUB TEAM': 'club_team_raw',
                'REGISTERED POSITION': 'registered_position',
                'HEIGHT': 'height',
                'STRONG FOOT': 'strong_foot',
                'FAVOURED SIDE': 'favoured_side',
                'WEAK FOOT ACCURACY': 'weak_foot_accuracy',
                'WEAK FOOT FREQUENCY': 'weak_foot_frequency',
                'ATTACK': 'attack',
                'DEFENSE': 'defense',
                'BALANCE': 'balance',
                'STAMINA': 'stamina',
                'TOP SPEED': 'top_speed',
                'ACCELERATION': 'acceleration',
                'RESPONSE': 'response',
                'AGILITY': 'agility',
                'DRIBBLE ACCURACY': 'dribble_accuracy',
                'DRIBBLE SPEED': 'dribble_speed',
                'SHORT PASS ACCURACY': 'short_pass_accuracy',
                'SHORT PASS SPEED': 'short_pass_speed',
                'LONG PASS ACCURACY': 'long_pass_accuracy',
                'LONG PASS SPEED': 'long_pass_speed',
                'SHOT ACCURACY': 'shot_accuracy',
                'SHOT POWER': 'shot_power',
                'SHOT TECHNIQUE': 'shot_technique',
                'FREE KICK ACCURACY': 'free_kick_accuracy',
                'SWERVE': 'swerve',
                'HEADING': 'heading',
                'JUMP': 'jump',
                'TECHNIQUE': 'technique',
                'AGGRESSION': 'aggression',
                'MENTALITY': 'mentality',
                'GOAL KEEPING': 'goal_keeping',
                'TEAM WORK': 'team_work',
                'CONSISTENCY': 'consistency',
                'CONDITION / FITNESS': 'condition_fitness',
                'DRIBBLING': 'dribbling_skill',
                'TACTIAL DRIBBLE': 'tactical_dribble',
                'POSITIONING': 'positioning',
                'REACTION': 'reaction',
                'PLAYMAKING': 'playmaking',
                'PASSING': 'passing',
                'SCORING': 'scoring',
                '1-1 SCORING': 'one_one_scoring',
                'POST PLAYER': 'post_player',
                'LINES': 'lines',
                'MIDDLE SHOOTING': 'middle_shooting',
                'SIDE': 'side',
                'CENTRE': 'centre',
                'PENALTIES': 'penalties',
                '1-TOUCH PASS': 'one_touch_pass',
                'OUTSIDE': 'outside',
                'MARKING': 'marking',
                'SLIDING': 'sliding',
                'COVERING': 'covering',
                'D-LINE CONTROL': 'd_line_control',
                'PENALTY STOPPER': 'penalty_stopper',
                '1-ON-1 STOPPER': 'one_on_one_stopper',
                'LONG THROW': 'long_throw',
                'INJURY TOLERANCE': 'injury_tolerance',
                'DRIBBLE STYLE': 'dribble_style',
                'FREE KICK STYLE': 'free_kick_style',
                'PK STYLE': 'pk_style',
                'DROP KICK STYLE': 'drop_kick_style',
                'AGE': 'age',
                'WEIGHT': 'weight',
                'NATIONALITY': 'nationality',
                'SKIN COLOR': 'skin_color',
                'FACE TYPE': 'face_type',
                'PRESET FACE NUMBER': 'preset_face_number',
                'HEAD WIDTH': 'head_width',
                'NECK LENGTH': 'neck_length',
                'NECK WIDTH': 'neck_width',
                'SHOULDER HEIGHT': 'shoulder_height',
                'SHOULDER WIDTH': 'shoulder_width',
                'CHEST MEASUREMENT': 'chest_measurement',
                'WAIST CIRCUMFERENCE': 'waist_circumference',
                'ARM CIRCUMFERENCE': 'arm_circumference',
                'LEG CIRCUMFERENCE': 'leg_circumference',
                'CALF CIRCUMFERENCE': 'calf_circumference',
                'LEG LENGTH': 'leg_length',
                'WRISTBAND': 'wristband',
                'WRISTBAND COLOR': 'wristband_color',
                'INTERNATIONAL NUMBER': 'international_number',
                'CLASSIC NUMBER': 'classic_number',
                'CLUB NUMBER': 'club_number',
                'GK  0': 'gk',
                'CWP  2': 'cwp',
                'CBT  3': 'cbt',
                'SB  4': 'sb',
                'DMF  5': 'dmf',
                'WB  6': 'wb',
                'CMF  7': 'cmf',
                'SMF  8': 'smf',
                'AMF  9': 'amf',
                'WF 10': 'wf',
                'SS  11': 'ss',
                'CF  12': 'cf'
            }
            
            # Rename columns in the DataFrame using the map
            df = df.rename(columns=raw_to_sql_column_map)

            # Build ID -> original_name map from the baseline CSV (only need ID and NAME)
            original_name_map = {'ID': 'id', 'NAME': 'player_name'}
            missing_needed_cols = [c for c in ['ID', 'NAME'] if c not in df_original_raw.columns]
            if missing_needed_cols:
                print(f"❌ pe6_player_data.csv is missing required columns: {', '.join(missing_needed_cols)}")
                return False
            df_original_names = df_original_raw[['ID', 'NAME']].rename(columns=original_name_map)
            original_names_by_id = {}
            for _, r in df_original_names.iterrows():
                try:
                    pid = int(r['id'])
                except Exception:
                    continue
                original_names_by_id[pid] = str(r['player_name']) if pd.notna(r['player_name']) else ''
            
            cursor = self.conn.cursor()
            
            # We still need to know if the player ID exists in DB
            cursor.execute("SELECT id FROM players")
            db_ids = {row[0] for row in cursor.fetchall()}
            
            updates_made = 0
            players_checked = 0
            updated_player_ids = []  # Track which players were actually updated
            
            print("🔍 Comparing newcomers.csv names with pe6_player_data.csv names (by ID)...")
            
            for _, row in df.iterrows():
                player_id = row['id']
                csv_name = row['player_name']
                players_checked += 1
                
                # Compare against original CSV name and update DB if different
                if player_id in db_ids:
                    original_name = original_names_by_id.get(player_id, None)
                    if original_name is None:
                        # If original is missing, skip update; we only act when there's a confirmed difference
                        print(f"⚠️  Skipping ID {player_id}: not found in pe6_player_data.csv")
                        continue
                    
                    if str(csv_name).strip().lower() != str(original_name).strip().lower():
                        print(f"🔄 Player ID {player_id}: '{original_name}' → '{csv_name}' (updating DB with newcomers attributes)")
                        
                        # Prepare club_id mapping (same logic as import_pes6_data.py)
                        club_team_raw = row.get('club_team_raw', '')
                        if pd.isna(club_team_raw) or club_team_raw == '':
                            cursor.execute("SELECT id FROM teams WHERE club_name = 'No Club'")
                            club_result = cursor.fetchone()
                            club_id = club_result[0] if club_result else None
                        else:
                            cursor.execute("SELECT id FROM teams WHERE club_name = ?", (club_team_raw,))
                            club_result = cursor.fetchone()
                            if club_result:
                                club_id = club_result[0]
                            else:
                                # Create the team if it doesn't exist
                                cursor.execute("INSERT INTO teams (club_name) VALUES (?)", (club_team_raw,))
                                club_id = cursor.lastrowid
                                print(f"   ✅ Created new team: {club_team_raw}")
                        
                        # Prepare all columns for update (same as import_pes6_data.py)
                        sql_columns = [
                            'player_name', 'shirt_name', 'club_id', 'registered_position', 'age', 'height', 'weight',
                            'nationality', 'strong_foot', 'favoured_side', 'gk', 'cwp', 'cbt', 'sb', 'dmf',
                            'wb', 'cmf', 'smf', 'amf', 'wf', 'ss', 'cf',
                            'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration', 'response', 
                            'agility', 'dribble_accuracy', 'dribble_speed', 'short_pass_accuracy', 'short_pass_speed', 
                            'long_pass_accuracy', 'long_pass_speed', 'shot_accuracy', 'shot_power', 'shot_technique', 
                            'free_kick_accuracy', 'swerve', 'heading', 'jump', 'technique', 'aggression', 'mentality', 
                            'goal_keeping', 'team_work', 'consistency', 'condition_fitness', 'dribbling_skill', 
                            'tactical_dribble', 'positioning', 'reaction', 'playmaking', 'passing', 'scoring',
                            'one_one_scoring', 'post_player', 'lines', 'middle_shooting', 'side', 'centre',
                            'penalties', 'one_touch_pass', 'outside', 'marking', 'sliding', 'covering',
                            'd_line_control', 'penalty_stopper', 'one_on_one_stopper', 'long_throw',
                            'injury_tolerance', 'dribble_style', 'free_kick_style', 'pk_style', 'drop_kick_style',
                            'skin_color', 'face_type', 'preset_face_number', 'head_width', 'neck_length',
                            'neck_width', 'shoulder_height', 'shoulder_width', 'chest_measurement',
                            'waist_circumference', 'arm_circumference', 'leg_circumference', 'calf_circumference',
                            'leg_length', 'wristband', 'wristband_color', 'international_number',
                            'classic_number', 'club_number'
                        ]
                        
                        # Prepare values for update
                        values = []
                        for col in sql_columns:
                            if col == 'club_id':
                                values.append(club_id)
                            else:
                                val = row.get(col, None)
                                values.append(None if pd.isna(val) else val)
                        
                        # Add player_id for WHERE clause
                        values.append(player_id)
                        
                        # Create UPDATE query
                        set_clause = ', '.join([f"{col} = ?" for col in sql_columns])
                        update_query = f"UPDATE players SET {set_clause} WHERE id = ?"
                        
                        # Execute update
                        cursor.execute(update_query, values)
                        updates_made += 1
                        updated_player_ids.append(player_id)  # Track this player as updated
                        
                else:
                    print(f"⚠️  Player ID {player_id} not found in database ('{csv_name}')")
            
            # Commit all changes
            self.conn.commit()
            
            print(f"\n✅ Update complete!")
            print(f"   📊 Players checked: {players_checked}")
            print(f"   🔄 Players updated: {updates_made}")
            
            # Ask if user wants to calculate overalls and export to CSV for updated players only
            if updates_made > 0:
                calc_overalls = input(f"\n🎯 Calculate overall ratings for the {updates_made} updated players and export sorted list to CSV? (y/N): ").strip().lower()
                if calc_overalls == 'y':
                    print("\n" + "="*60)
                    self.calculate_and_export_player_overalls_for_specific_players(updated_player_ids)
            
            return True
            
        except FileNotFoundError:
            print(f"❌ File not found: {csv_path}")
            return False
        except Exception as e:
            print(f"❌ Error updating players: {e}")
            if self.conn:
                self.conn.rollback()
            return False
    
    def calculate_and_export_player_overalls(self, output_csv: str = 'player_overalls_sorted.csv') -> bool:
        """Calculate overall ratings for all players and export sorted list to CSV"""
        if not self.conn:
            print("❌ Not connected to database")
            return False
        
        try:
            print("⭐ Calculating overall ratings for all players...")
            
            # Import the calculation function
            try:
                from refresh_and_reimport import calculate_player_overall
            except ImportError:
                print("❌ Could not import calculate_player_overall from refresh_and_reimport.py")
                return False
            
            cursor = self.conn.cursor()
            
            # Get all players with their data
            cursor.execute("SELECT * FROM players")
            players = cursor.fetchall()
            
            if not players:
                print("❌ No players found in database")
                return False
            
            print(f"📊 Processing {len(players)} players...")
            
            # Calculate overalls and prepare data for sorting
            players_with_overalls = []
            updated_count = 0
            
            for player in players:
                player_data = dict(player)
                
                # Calculate overall rating
                overall = calculate_player_overall(player_data)
                
                # Update the overall in the database
                cursor.execute("UPDATE players SET overall = ? WHERE id = ?", (overall, player['id']))
                
                # Prepare data for CSV export
                export_data = {
                    'id': player_data.get('id'),
                    'player_name': player_data.get('player_name'),
                    'overall': overall,
                    'registered_position': player_data.get('registered_position'),
                    'age': player_data.get('age'),
                    'nationality': player_data.get('nationality'),
                    'height': player_data.get('height'),
                    'weight': player_data.get('weight'),
                    'club_id': player_data.get('club_id'),
                    'attack': player_data.get('attack'),
                    'defense': player_data.get('defense'),
                    'balance': player_data.get('balance'),
                    'stamina': player_data.get('stamina'),
                    'top_speed': player_data.get('top_speed'),
                    'acceleration': player_data.get('acceleration'),
                    'technique': player_data.get('technique'),
                    'mentality': player_data.get('mentality'),
                    'team_work': player_data.get('team_work'),
                    'consistency': player_data.get('consistency')
                }
                
                players_with_overalls.append(export_data)
                updated_count += 1
                
                if updated_count % 100 == 0:
                    print(f"   Processed {updated_count}/{len(players)} players...")
            # Commit overall updates to database
            self.conn.commit()
            print(f"✅ Updated overall ratings for {updated_count} players in database")
            
            # Sort players by overall rating (best to worst)
            players_with_overalls.sort(key=lambda p: p['overall'], reverse=True)
            
            # Convert to DataFrame for easier CSV export
            df = pd.DataFrame(players_with_overalls)
            
            # Add position names for better readability
            position_names = {
                0: 'Goal-Keeper', 1: 'Centre-Back', 2: 'Centre-Back', 3: 'Centre-Back',
                4: 'Side-Back', 5: 'Defensive Midfielder', 6: 'Wing-Back',
                7: 'Central Midfielder', 8: 'Side Midfielder', 9: 'Attacking Midfielder',
                10: 'Wing Forward', 11: 'Second Striker', 12: 'Centre Forward'
            }
            df['position_name'] = df['registered_position'].map(position_names).fillna('Unknown')
            
            # Reorder columns for better readability
            column_order = [
                'overall', 'id', 'player_name', 'position_name', 'registered_position',
                'age', 'nationality', 'height', 'weight', 'club_id',
                'attack', 'defense', 'balance', 'stamina', 'top_speed',
                'acceleration', 'technique', 'mentality', 'team_work', 'consistency'
            ]
            df = df[column_order]
            
            # Export to CSV
            df.to_csv(output_csv, index=False)
            
            print(f"📄 Exported sorted player list to: {output_csv}")
            print(f"📊 Total players: {len(players_with_overalls)}")
            
            # Show top 10 players
            print(f"\n🏆 TOP 10 PLAYERS:")
            print("-" * 80)
            print(f"{'Overall':<8} {'Name':<25} {'Position':<20} {'Age':<4} {'Nationality':<15}")
            print("-" * 80)
            
            for i, player in enumerate(players_with_overalls[:10]):
                pos_name = position_names.get(player['registered_position'], 'Unknown')
                print(f"{player['overall']:<8} {player['player_name']:<25} {pos_name:<20} {player['age']:<4} {player['nationality'] or 'N/A':<15}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error calculating overalls: {e}")
            if self.conn:
                self.conn.rollback()
            return False
    
    def calculate_and_export_player_overalls_for_specific_players(self, player_ids: List[int], output_csv: str = 'newcomers_overalls_sorted.csv') -> bool:
        """Calculate overall ratings for specific players and export sorted list to CSV"""
        if not self.conn:
            print("❌ Not connected to database")
            return False
        
        if not player_ids:
            print("❌ No player IDs provided")
            return False
        
        try:
            print(f"⭐ Calculating overall ratings for {len(player_ids)} updated players...")
            
            # Import the calculation function
            try:
                from refresh_and_reimport import calculate_player_overall
            except ImportError:
                print("❌ Could not import calculate_player_overall from refresh_and_reimport.py")
                return False
            
            cursor = self.conn.cursor()
            
            # Get specific players with their data
            placeholders = ','.join(['?' for _ in player_ids])
            cursor.execute(f"SELECT * FROM players WHERE id IN ({placeholders})", player_ids)
            players = cursor.fetchall()
            
            if not players:
                print("❌ No players found for the provided IDs")
                return False
            
            print(f"📊 Processing {len(players)} updated players...")
            
            # Calculate overalls and prepare data for sorting
            players_with_overalls = []
            updated_count = 0
            
            for player in players:
                player_data = dict(player)
                
                # Calculate overall rating
                overall = calculate_player_overall(player_data)
                
                # Update the overall in the database
                cursor.execute("UPDATE players SET overall = ? WHERE id = ?", (overall, player['id']))
                
                # Prepare data for CSV export
                export_data = {
                    'id': player_data.get('id'),
                    'player_name': player_data.get('player_name'),
                    'overall': overall,
                    'registered_position': player_data.get('registered_position'),
                    'age': player_data.get('age'),
                    'nationality': player_data.get('nationality'),
                    'height': player_data.get('height'),
                    'weight': player_data.get('weight'),
                    'club_id': player_data.get('club_id'),
                    'attack': player_data.get('attack'),
                    'defense': player_data.get('defense'),
                    'balance': player_data.get('balance'),
                    'stamina': player_data.get('stamina'),
                    'top_speed': player_data.get('top_speed'),
                    'acceleration': player_data.get('acceleration'),
                    'technique': player_data.get('technique'),
                    'mentality': player_data.get('mentality'),
                    'team_work': player_data.get('team_work'),
                    'consistency': player_data.get('consistency')
                }
                
                players_with_overalls.append(export_data)
                updated_count += 1
                
                print(f"   ✅ {player_data.get('player_name')}: Overall = {overall}")
            
            # Commit overall updates to database
            self.conn.commit()
            print(f"✅ Updated overall ratings for {updated_count} players in database")
            
            # Sort players by overall rating (best to worst)
            players_with_overalls.sort(key=lambda p: p['overall'], reverse=True)
            
            # Convert to DataFrame for easier CSV export
            df = pd.DataFrame(players_with_overalls)
            
            # Add position names for better readability
            position_names = {
                0: 'Goal-Keeper', 1: 'Centre-Back', 2: 'Centre-Back', 3: 'Centre-Back',
                4: 'Side-Back', 5: 'Defensive Midfielder', 6: 'Wing-Back',
                7: 'Central Midfielder', 8: 'Side Midfielder', 9: 'Attacking Midfielder',
                10: 'Wing Forward', 11: 'Second Striker', 12: 'Centre Forward'
            }
            df['position_name'] = df['registered_position'].map(position_names).fillna('Unknown')
            
            # Reorder columns for better readability
            column_order = [
                'overall', 'id', 'player_name', 'position_name', 'registered_position',
                'age', 'nationality', 'height', 'weight', 'club_id',
                'attack', 'defense', 'balance', 'stamina', 'top_speed',
                'acceleration', 'technique', 'mentality', 'team_work', 'consistency'
            ]
            df = df[column_order]
            
            # Export to CSV
            df.to_csv(output_csv, index=False)
            
            print(f"📄 Exported sorted newcomers list to: {output_csv}")
            print(f"📊 Total updated players: {len(players_with_overalls)}")
            
            # Show all updated players (since it's a smaller list)
            print(f"\n🏆 UPDATED PLAYERS (SORTED BY OVERALL):")
            print("-" * 80)
            print(f"{'Overall':<8} {'Name':<25} {'Position':<20} {'Age':<4} {'Nationality':<15}")
            print("-" * 80)
            
            for player in players_with_overalls:
                pos_name = position_names.get(player['registered_position'], 'Unknown')
                print(f"{player['overall']:<8} {player['player_name']:<25} {pos_name:<20} {player['age']:<4} {player['nationality'] or 'N/A':<15}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error calculating overalls for specific players: {e}")
            if self.conn:
                self.conn.rollback()
            return False
    
    def fix_team_id_mismatches(self) -> bool:
        """Fix team ID mismatches between league_teams and teams tables"""
        if not self.conn:
            return False
        
        try:
            cursor = self.conn.cursor()
            
            print("🔍 Checking for team ID mismatches...")
            
            # Find teams in league_teams that don't exist in teams table
            cursor.execute("""
                SELECT lt.id, lt.team_name, lt.user_id
                FROM league_teams lt
                LEFT JOIN teams t ON lt.id = t.id
                WHERE t.id IS NULL
            """)
            
            mismatched_teams = cursor.fetchall()
            
            if not mismatched_teams:
                print("✅ No team ID mismatches found")
                return True
            
            print(f"⚠️  Found {len(mismatched_teams)} team ID mismatches:")
            
            for team in mismatched_teams:
                print(f"   - League Team ID {team['id']}: '{team['team_name']}' (User {team['user_id']})")
                
                # Try to find the correct team ID in teams table
                cursor.execute("""
                    SELECT id FROM teams 
                    WHERE club_name = ?
                """, (team['team_name'],))
                
                correct_team = cursor.fetchone()
                
                if correct_team:
                    correct_id = correct_team['id']
                    print(f"     → Found correct team ID: {correct_id}")
                    
                    # Update the league_teams entry
                    cursor.execute("""
                        UPDATE league_teams 
                        SET id = ? 
                        WHERE id = ? AND team_name = ?
                    """, (correct_id, team['id'], team['team_name']))
                    
                    print(f"     ✅ Updated league_teams entry from ID {team['id']} to {correct_id}")
                else:
                    print(f"     ❌ No matching team found in teams table for '{team['team_name']}'")
            
            self.conn.commit()
            print(f"✅ Fixed {len(mismatched_teams)} team ID mismatches")
            return True
            
        except Exception as e:
            print(f"❌ Error fixing team ID mismatches: {e}")
            self.conn.rollback()
            return False
    
    def replace_player_from_csv(self, player_id: int, csv_file_path: str) -> bool:
        """Replace a player from the active database with data from CSV entry"""
        if not self.conn:
            print("❌ Not connected to database")
            return False
        
        try:
            # Check if CSV file exists
            if not os.path.exists(csv_file_path):
                print(f"❌ CSV file not found: {csv_file_path}")
                return False
            
            # Read CSV file
            try:
                df = pd.read_csv(csv_file_path, encoding='latin-1')
            except UnicodeDecodeError:
                try:
                    df = pd.read_csv(csv_file_path, encoding='utf-8')
                except UnicodeDecodeError:
                    df = pd.read_csv(csv_file_path, encoding='iso-8859-1')
            
            # Check if player ID exists in CSV
            csv_player = df[df['ID'] == player_id]
            if csv_player.empty:
                print(f"❌ Player ID {player_id} not found in CSV file")
                return False
            
            # Get player data from CSV
            csv_data = csv_player.iloc[0]
            
            # Check if player exists in database
            cursor = self.conn.cursor()
            cursor.execute("SELECT player_name, club_id FROM players WHERE id = ?", (player_id,))
            db_player = cursor.fetchone()
            
            if not db_player:
                print(f"❌ Player ID {player_id} not found in database")
                return False
            
            old_name, old_club_id = db_player
            print(f"🔄 Replacing player: {old_name} (ID: {player_id})")
            print(f"   Old club ID: {old_club_id}")
            
            # Get all column names from players table
            cursor.execute("PRAGMA table_info(players)")
            columns_info = cursor.fetchall()
            column_names = [col[1] for col in columns_info]
            
            # Map CSV columns to database columns
            csv_to_db_mapping = {
                'ID': 'id',
                'NAME': 'player_name',
                'SHIRT_NAME': 'shirt_name',
                'GK  0': 'gk',
                'CWP  2': 'cwp',
                'CBT  3': 'cbt',
                'SB  4': 'sb',
                'DMF  5': 'dmf',
                'WB  6': 'wb',
                'CMF  7': 'cmf',
                'SMF  8': 'smf',
                'AMF  9': 'amf',
                'WF 10': 'wf',
                'SS  11': 'ss',
                'CF  12': 'cf',
                'REGISTERED POSITION': 'registered_position',
                'HEIGHT': 'height',
                'STRONG FOOT': 'strong_foot',
                'FAVOURED SIDE': 'favoured_side',
                'ATTACK': 'attack',
                'DEFENSE': 'defense',
                'BALANCE': 'balance',
                'STAMINA': 'stamina',
                'TOP SPEED': 'top_speed',
                'ACCELERATION': 'acceleration',
                'RESPONSE': 'response',
                'AGILITY': 'agility',
                'DRIBBLE ACCURACY': 'dribble_accuracy',
                'DRIBBLE SPEED': 'dribble_speed',
                'SHORT PASS ACCURACY': 'short_pass_accuracy',
                'SHORT PASS SPEED': 'short_pass_speed',
                'LONG PASS ACCURACY': 'long_pass_accuracy',
                'LONG PASS SPEED': 'long_pass_speed',
                'SHOT ACCURACY': 'shot_accuracy',
                'SHOT POWER': 'shot_power',
                'SHOT TECHNIQUE': 'shot_technique',
                'FREE KICK ACCURACY': 'free_kick_accuracy',
                'SWERVE': 'swerve',
                'HEADING': 'heading',
                'JUMP': 'jump',
                'TECHNIQUE': 'technique',
                'AGGRESSION': 'aggression',
                'MENTALITY': 'mentality',
                'GOAL KEEPING': 'goal_keeping',
                'TEAM WORK': 'team_work',
                'CONSISTENCY': 'consistency',
                'CONDITION / FITNESS': 'condition_fitness',
                'DRIBBLING': 'dribbling_skill',
                'TACTIAL DRIBBLE': 'tactical_dribble',
                'POSITIONING': 'positioning',
                'REACTION': 'reaction',
                'PLAYMAKING': 'playmaking',
                'PASSING': 'passing',
                'SCORING': 'scoring',
                '1-1 SCORING': 'one_one_scoring',
                'POST PLAYER': 'post_player',
                'LINES': 'lines',
                'MIDDLE SHOOTING': 'middle_shooting',
                'SIDE': 'side',
                'CENTRE': 'centre',
                'PENALTIES': 'penalties',
                '1-TOUCH PASS': 'one_touch_pass',
                'OUTSIDE': 'outside',
                'MARKING': 'marking',
                'SLIDING': 'sliding',
                'COVERING': 'covering',
                'D-LINE CONTROL': 'd_line_control',
                'PENALTY STOPPER': 'penalty_stopper',
                '1-ON-1 STOPPER': 'one_on_one_stopper',
                'LONG THROW': 'long_throw',
                'INJURY TOLERANCE': 'injury_tolerance',
                'DRIBBLE STYLE': 'dribble_style',
                'FREE KICK STYLE': 'free_kick_style',
                'PK STYLE': 'pk_style',
                'DROP KICK STYLE': 'drop_kick_style',
                'AGE': 'age',
                'WEIGHT': 'weight',
                'NATIONALITY': 'nationality',
                'SKIN COLOR': 'skin_color',
                'FACE TYPE': 'face_type',
                'PRESET FACE NUMBER': 'preset_face_number',
                'HEAD WIDTH': 'head_width',
                'NECK LENGTH': 'neck_length',
                'NECK WIDTH': 'neck_width',
                'SHOULDER HEIGHT': 'shoulder_height',
                'SHOULDER WIDTH': 'shoulder_width',
                'CHEST MEASUREMENT': 'chest_measurement',
                'WAIST CIRCUMFERENCE': 'waist_circumference',
                'ARM CIRCUMFERENCE': 'arm_circumference',
                'LEG CIRCUMFERENCE': 'leg_circumference',
                'CALF CIRCUMFERENCE': 'calf_circumference',
                'LEG LENGTH': 'leg_length',
                'WRISTBAND': 'wristband',
                'WRISTBAND COLOR': 'wristband_color',
                'INTERNATIONAL NUMBER': 'international_number',
                'CLASSIC NUMBER': 'classic_number',
                'CLUB NUMBER': 'club_number',
                'CLUB TEAM': 'club_team_raw'
            }
            
            # Build UPDATE query
            update_fields = []
            update_values = []
            
            for csv_col, db_col in csv_to_db_mapping.items():
                if csv_col in csv_data.index and db_col in column_names:
                    value = csv_data[csv_col]
                    
                    # Handle NaN values
                    if pd.isna(value):
                        value = None
                    
                    # Handle string values that should be integers
                    if db_col in ['gk', 'cwp', 'cbt', 'sb', 'dmf', 'wb', 'cmf', 'smf', 'amf', 'wf', 'ss', 'cf',
                                 'height', 'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
                                 'response', 'agility', 'dribble_accuracy', 'dribble_speed', 'short_pass_accuracy',
                                 'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed', 'shot_accuracy',
                                 'shot_power', 'shot_technique', 'free_kick_accuracy', 'swerve', 'heading', 'jump',
                                 'technique', 'aggression', 'mentality', 'goal_keeping', 'team_work', 'consistency',
                                 'condition_fitness', 'dribbling_skill', 'tactical_dribble', 'positioning', 'reaction',
                                 'playmaking', 'passing', 'scoring', 'one_one_scoring', 'post_player', 'lines',
                                 'middle_shooting', 'side', 'centre', 'penalties', 'one_touch_pass', 'outside',
                                 'marking', 'sliding', 'covering', 'd_line_control', 'penalty_stopper',
                                 'one_on_one_stopper', 'long_throw', 'head_width', 'neck_length', 'neck_width',
                                 'shoulder_height', 'shoulder_width', 'chest_measurement', 'waist_circumference',
                                 'arm_circumference', 'leg_circumference', 'calf_circumference', 'leg_length',
                                 'international_number', 'classic_number', 'club_number', 'age', 'weight',
                                 'preset_face_number']:
                        try:
                            value = int(value) if value is not None else None
                        except (ValueError, TypeError):
                            value = None
                    
                    update_fields.append(f"{db_col} = ?")
                    update_values.append(value)
            
            # Add player ID to the end for WHERE clause
            update_values.append(player_id)
            
            # Execute UPDATE query
            update_query = f"UPDATE players SET {', '.join(update_fields)} WHERE id = ?"
            cursor.execute(update_query, update_values)
            
            # Get updated player info
            cursor.execute("SELECT player_name FROM players WHERE id = ?", (player_id,))
            new_name = cursor.fetchone()[0]
            
            self.conn.commit()
            
            print(f"✅ Successfully replaced player!")
            print(f"   Old name: {old_name}")
            print(f"   New name: {new_name}")
            print(f"   Updated {len(update_fields)} fields")
            
            return True
            
        except Exception as e:
            print(f"❌ Error replacing player from CSV: {e}")
            self.conn.rollback()
            return False
    
    def replace_player_manually(self, player_id: int) -> bool:
        """Replace a player by manually entering each field"""
        if not self.conn:
            print("❌ Not connected to database")
            return False
        
        try:
            # Check if player exists in database
            cursor = self.conn.cursor()
            cursor.execute("SELECT player_name, club_id FROM players WHERE id = ?", (player_id,))
            db_player = cursor.fetchone()
            
            if not db_player:
                print(f"❌ Player ID {player_id} not found in database")
                return False
            
            old_name, old_club_id = db_player
            print(f"🔄 Replacing player: {old_name} (ID: {player_id})")
            print(f"   Current club ID: {old_club_id}")
            
            # Get all column names from players table
            cursor.execute("PRAGMA table_info(players)")
            columns_info = cursor.fetchall()
            column_names = [col[1] for col in columns_info]
            
            # Define fields to update (excluding id, club_id, and other system fields)
            updatable_fields = [
                'player_name', 'shirt_name', 'gk', 'cwp', 'cbt', 'sb', 'dmf', 'wb', 'cmf', 'smf', 'amf', 'wf', 'ss', 'cf',
                'registered_position', 'height', 'strong_foot', 'favoured_side', 'attack', 'defense', 'balance', 'stamina',
                'top_speed', 'acceleration', 'response', 'agility', 'dribble_accuracy', 'dribble_speed', 'short_pass_accuracy',
                'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed', 'shot_accuracy', 'shot_power', 'shot_technique',
                'free_kick_accuracy', 'swerve', 'heading', 'jump', 'technique', 'aggression', 'mentality', 'goal_keeping',
                'team_work', 'consistency', 'condition_fitness', 'dribbling_skill', 'tactical_dribble', 'positioning',
                'reaction', 'playmaking', 'passing', 'scoring', 'one_one_scoring', 'post_player', 'lines', 'middle_shooting',
                'side', 'centre', 'penalties', 'one_touch_pass', 'outside', 'marking', 'sliding', 'covering', 'd_line_control',
                'penalty_stopper', 'one_on_one_stopper', 'long_throw', 'injury_tolerance', 'dribble_style', 'free_kick_style',
                'pk_style', 'drop_kick_style', 'age', 'weight', 'nationality', 'skin_color', 'face_type', 'preset_face_number',
                'head_width', 'neck_length', 'neck_width', 'shoulder_height', 'shoulder_width', 'chest_measurement',
                'waist_circumference', 'arm_circumference', 'leg_circumference', 'calf_circumference', 'leg_length',
                'wristband', 'wristband_color', 'international_number', 'classic_number', 'club_number', 'salary',
                'contract_years_remaining', 'market_value', 'yearly_wage_rise', 'games_played', 'goals', 'assists',
                'championships_won', 'cups_won', 'seed_player'
            ]
            
            # Filter to only include fields that exist in the database
            updatable_fields = [field for field in updatable_fields if field in column_names]
            
            print(f"\n📝 You will be prompted to enter values for {len(updatable_fields)} fields.")
            print("Press Enter to keep current value, or enter new value to change it.")
            print("Type 'skip' to skip updating this field.")
            print("-" * 60)
            
            update_fields = []
            update_values = []
            
            for field in updatable_fields:
                # Get current value
                cursor.execute(f"SELECT {field} FROM players WHERE id = ?", (player_id,))
                current_value = cursor.fetchone()[0]
                
                # Display current value
                if current_value is None:
                    current_display = "NULL"
                else:
                    current_display = str(current_value)
                
                # Prompt for new value
                new_value = input(f"{field} (current: {current_display}): ").strip()
                
                if new_value.lower() == 'skip':
                    continue
                elif new_value == '':
                    # Keep current value
                    continue
                else:
                    # Convert value based on field type
                    try:
                        # Determine if field should be integer
                        if field in ['gk', 'cwp', 'cbt', 'sb', 'dmf', 'wb', 'cmf', 'smf', 'amf', 'wf', 'ss', 'cf',
                                   'height', 'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
                                   'response', 'agility', 'dribble_accuracy', 'dribble_speed', 'short_pass_accuracy',
                                   'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed', 'shot_accuracy',
                                   'shot_power', 'shot_technique', 'free_kick_accuracy', 'swerve', 'heading', 'jump',
                                   'technique', 'aggression', 'mentality', 'goal_keeping', 'team_work', 'consistency',
                                   'condition_fitness', 'dribbling_skill', 'tactical_dribble', 'positioning', 'reaction',
                                   'playmaking', 'passing', 'scoring', 'one_one_scoring', 'post_player', 'lines',
                                   'middle_shooting', 'side', 'centre', 'penalties', 'one_touch_pass', 'outside',
                                   'marking', 'sliding', 'covering', 'd_line_control', 'penalty_stopper',
                                   'one_on_one_stopper', 'long_throw', 'head_width', 'neck_length', 'neck_width',
                                   'shoulder_height', 'shoulder_width', 'chest_measurement', 'waist_circumference',
                                   'arm_circumference', 'leg_circumference', 'calf_circumference', 'leg_length',
                                   'international_number', 'classic_number', 'club_number', 'age', 'weight',
                                   'preset_face_number', 'salary', 'contract_years_remaining', 'market_value',
                                   'yearly_wage_rise', 'games_played', 'goals', 'assists', 'championships_won', 'cups_won',
                                   'seed_player']:
                            converted_value = int(new_value)
                        else:
                            converted_value = new_value
                        
                        update_fields.append(f"{field} = ?")
                        update_values.append(converted_value)
                        
                    except ValueError:
                        print(f"   ⚠️  Invalid value for {field}, skipping...")
                        continue
            
            if not update_fields:
                print("❌ No fields were updated")
                return False
            
            # Add player ID to the end for WHERE clause
            update_values.append(player_id)
            
            # Execute UPDATE query
            update_query = f"UPDATE players SET {', '.join(update_fields)} WHERE id = ?"
            cursor.execute(update_query, update_values)
            
            # Get updated player info
            cursor.execute("SELECT player_name FROM players WHERE id = ?", (player_id,))
            new_name = cursor.fetchone()[0]
            
            self.conn.commit()
            
            print(f"\n✅ Successfully updated player!")
            print(f"   Old name: {old_name}")
            print(f"   New name: {new_name}")
            print(f"   Updated {len(update_fields)} fields")
            
            return True
            
        except Exception as e:
            print(f"❌ Error replacing player manually: {e}")
            self.conn.rollback()
            return False

    def refresh_league_standings(self, division_id: int):
        """Manually refresh and display league standings for a division"""
        try:
            cursor = self.conn.cursor()
            
            # Get division name
            cursor.execute("SELECT name FROM divisions WHERE id = ?", (division_id,))
            division = cursor.fetchone()
            if not division:
                print(f"❌ Division ID {division_id} not found.")
                return
            
            division_name = division['name']
            print(f"\n🏆 Updated Standings for {division_name}")
            print("-" * 80)
            print(f"{'Pos':<4} {'Team':<25} {'P':<3} {'W':<3} {'D':<3} {'L':<3} {'GF':<3} {'GA':<3} {'GD':<4} {'Pts':<4}")
            print("-" * 80)
            
            # Calculate standings (similar to app.py)
            cursor.execute("SELECT team_id FROM division_teams WHERE division_id = ?", (division_id,))
            teams = cursor.fetchall()
            
            standings = []
            for team in teams:
                team_id = team['team_id']
                
                # Get team name
                cursor.execute("SELECT club_name FROM teams WHERE id = ?", (team_id,))
                team_name = cursor.fetchone()['club_name']
                
                # Calculate stats from games
                cursor.execute("""
                    SELECT 
                        COUNT(*) as games_played,
                        SUM(CASE WHEN (home_team_id = ? AND home_score > away_score) OR (away_team_id = ? AND away_score > home_score) THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN home_score = away_score THEN 1 ELSE 0 END) as draws,
                        SUM(CASE WHEN (home_team_id = ? AND home_score < away_score) OR (away_team_id = ? AND away_score < home_score) THEN 1 ELSE 0 END) as losses,
                        SUM(CASE WHEN home_team_id = ? THEN home_score ELSE away_score END) as goals_for,
                        SUM(CASE WHEN home_team_id = ? THEN away_score ELSE home_score END) as goals_against
                    FROM league_games
                    WHERE (home_team_id = ? OR away_team_id = ?) AND is_played = 1 AND division_id = ?
                """, (team_id, team_id, team_id, team_id, team_id, team_id, team_id, team_id, division_id))
                
                stats = cursor.fetchone()
                
                games_played = stats['games_played'] or 0
                wins = stats['wins'] or 0
                draws = stats['draws'] or 0
                losses = stats['losses'] or 0
                goals_for = stats['goals_for'] or 0
                goals_against = stats['goals_against'] or 0
                goal_difference = goals_for - goals_against
                points = wins * 3 + draws
                
                standings.append({
                    'team_name': team_name,
                    'games_played': games_played,
                    'wins': wins,
                    'draws': draws,
                    'losses': losses,
                    'goals_for': goals_for,
                    'goals_against': goals_against,
                    'goal_difference': goal_difference,
                    'points': points
                })
            
            # Sort standings
            standings.sort(key=lambda x: (x['points'], x['goal_difference'], x['goals_for']), reverse=True)
            
            # Print standings
            for i, team in enumerate(standings, 1):
                print(f"{i:<4} {team['team_name']:<25} {team['games_played']:<3} {team['wins']:<3} {team['draws']:<3} {team['losses']:<3} {team['goals_for']:<3} {team['goals_against']:<3} {team['goal_difference']:<4} {team['points']:<4}")
            
            print(f"\n✅ Standings refreshed for {division_name}.")
            
        except Exception as e:
            print(f"❌ Error refreshing standings: {e}")

def display_menu():
    """Display the main menu"""
    print("\n" + "="*60)
    print("🏆 TEAM MANAGEMENT SYSTEM")
    print("="*60)
    print("1. List all users")
    print("2. List all teams with ownership")
    print("3. List teams owned by a specific user")
    print("4. List CPU teams")
    print("5. Transfer team to user (CPU → User)")
    print("6. Transfer team to CPU (User → CPU)")
    print("7. Create new team for user")
    print("8. Add budget to team")
    print("9. Subtract budget from team")
    print("10. Update players from NewcomerII.csv (ID range → Draftees)")
    print("11. Calculate overalls and export to CSV")
    print("12. Fix team ID mismatches")
    print("13. Replace player from CSV by ID")
    print("14. Replace player manually (field by field)")
    print("15. Rename players with long names (16+ characters)")
    print("16. Duplicate player stats for a team")
    print("17. Delete a game from Colados League")
    print("18. Exit")
    print("="*60)

def list_users(manager: TeamManager):
    """List all users"""
    users = manager.get_all_users()
    if not users:
        print("❌ No users found")
        return
    
    print(f"\n👥 USERS ({len(users)} total):")
    print("-" * 60)
    print(f"{'ID':<4} {'Username':<20} {'Email':<30}")
    print("-" * 60)
    for user in users:
        email = user['email'] if user['email'] else 'No email'
        print(f"{user['id']:<4} {user['username']:<20} {email:<30}")

def list_all_teams(manager: TeamManager):
    """List all teams with ownership information"""
    teams = manager.get_all_teams()
    if not teams:
        print("❌ No teams found")
        return
    
    print(f"\n🏟️  ALL TEAMS ({len(teams)} total):")
    print("-" * 80)
    print(f"{'ID':<4} {'Team Name':<25} {'Owner':<15} {'Budget':<12} {'Available Cap':<12}")
    print("-" * 80)
    
    for team in teams:
        owner = team['username'] if team['username'] else 'CPU'
        budget = f"€{team['budget']:,.0f}"
        available_cap = f"€{team['available_cap']:,.0f}"
        print(f"{team['id']:<4} {team['club_name']:<25} {owner:<15} {budget:<12} {available_cap:<12}")

def list_user_teams(manager: TeamManager):
    """List teams owned by a specific user"""
    user_id = input("Enter user ID: ").strip()
    if not user_id.isdigit():
        print("❌ Invalid user ID")
        return
    
    user_id = int(user_id)
    teams = manager.get_user_teams(user_id)
    
    if not teams:
        print(f"❌ No teams found for user ID {user_id}")
        return
    
    print(f"\n🏟️  TEAMS OWNED BY USER ID {user_id} ({len(teams)} total):")
    print("-" * 60)
    print(f"{'ID':<4} {'Team Name':<25} {'Budget':<12} {'Available Cap':<12}")
    print("-" * 60)
    
    for team in teams:
        budget = f"€{team['budget']:,.0f}"
        available_cap = f"€{team['available_cap']:,.0f}"
        print(f"{team['id']:<4} {team['club_name']:<25} {budget:<12} {available_cap:<12}")

def list_cpu_teams(manager: TeamManager):
    """List CPU teams"""
    teams = manager.get_cpu_teams()
    if not teams:
        print("❌ No CPU teams found")
        return
    
    print(f"\n🤖 CPU TEAMS ({len(teams)} total):")
    print("-" * 60)
    print(f"{'ID':<4} {'Team Name':<25} {'Budget':<12} {'Available Cap':<12}")
    print("-" * 60)
    
    for team in teams:
        budget = f"€{team['budget']:,.0f}"
        available_cap = f"€{team['available_cap']:,.0f}"
        print(f"{team['id']:<4} {team['club_name']:<25} {budget:<12} {available_cap:<12}")

def transfer_to_user(manager: TeamManager):
    """Transfer a team to a user"""
    team_id = input("Enter team ID to transfer: ").strip()
    if not team_id.isdigit():
        print("❌ Invalid team ID")
        return
    
    user_id = input("Enter user ID to transfer to: ").strip()
    if not user_id.isdigit():
        print("❌ Invalid user ID")
        return
    
    team_id = int(team_id)
    user_id = int(user_id)
    
    # Confirm transfer
    confirm = input(f"Transfer team ID {team_id} to user ID {user_id}? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Transfer cancelled")
        return
    
    manager.transfer_team_to_user(team_id, user_id)

def transfer_to_cpu(manager: TeamManager):
    """Transfer a team to CPU"""
    team_id = input("Enter team ID to transfer to CPU: ").strip()
    if not team_id.isdigit():
        print("❌ Invalid team ID")
        return
    
    team_id = int(team_id)
    
    # Confirm transfer
    confirm = input(f"Transfer team ID {team_id} to CPU? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Transfer cancelled")
        return
    
    manager.transfer_team_to_cpu(team_id)

def create_new_team(manager: TeamManager):
    """Create a new team for a user"""
    team_name = input("Enter new team name: ").strip()
    if not team_name:
        print("❌ Team name cannot be empty")
        return
    
    user_id = input("Enter user ID to assign team to: ").strip()
    if not user_id.isdigit():
        print("❌ Invalid user ID")
        return
    
    budget_input = input("Enter team budget (default: 10,000,000): ").strip()
    if budget_input.isdigit():
        budget = int(budget_input)
    else:
        budget = 10000000
    
    user_id = int(user_id)
    
    # Confirm creation
    confirm = input(f"Create team '{team_name}' with budget €{budget:,} for user ID {user_id}? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Team creation cancelled")
        return
    
    manager.create_new_team_for_user(team_name, user_id, budget)

def add_budget_to_team(manager: TeamManager):
    """Add budget to a team"""
    team_id = input("Enter team ID to add budget to: ").strip()
    if not team_id.isdigit():
        print("❌ Invalid team ID")
        return
    
    amount_input = input("Enter amount to add: ").strip()
    if not amount_input.isdigit():
        print("❌ Invalid amount")
        return
    
    team_id = int(team_id)
    amount = int(amount_input)
    
    # Confirm addition
    confirm = input(f"Add €{amount:,} to team ID {team_id}? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Budget addition cancelled")
        return
    
    manager.modify_team_budget(team_id, amount, 'add')

def subtract_budget_from_team(manager: TeamManager):
    """Subtract budget from a team"""
    team_id = input("Enter team ID to subtract budget from: ").strip()
    if not team_id.isdigit():
        print("❌ Invalid team ID")
        return
    
    amount_input = input("Enter amount to subtract: ").strip()
    if not amount_input.isdigit():
        print("❌ Invalid amount")
        return
    
    team_id = int(team_id)
    amount = int(amount_input)
    
    # Confirm subtraction
    confirm = input(f"Subtract €{amount:,} from team ID {team_id}? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Budget subtraction cancelled")
        return
    
    manager.modify_team_budget(team_id, amount, 'subtract')

def update_players_from_newcomers(manager: TeamManager):
    """Update players from NewcomerII.csv with ID range, mark as draftees and blacklist"""
    csv_path = input("Enter path to newcomers CSV file (default: NewcomerII.csv): ").strip()
    if not csv_path:
        csv_path = 'NewcomerII.csv'
    
    # Get ID range
    id_start = input("Enter starting player ID: ").strip()
    id_end = input("Enter ending player ID: ").strip()
    
    try:
        id_start = int(id_start)
        id_end = int(id_end)
    except ValueError:
        print("❌ Invalid ID range. Must be integers.")
        return
    
    if id_start > id_end:
        print("❌ Start ID must be less than or equal to end ID")
        return
    
    # Confirm update
    confirm = input(f"Update player IDs {id_start}-{id_end} from '{csv_path}'? Players will be set to No Club, marked as draftees, and blacklisted. (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Update cancelled")
        return
    
    manager.update_players_from_newcomers_csv_range(csv_path, id_start, id_end)

def calculate_overalls_and_export(manager: TeamManager):
    """Calculate overall ratings for all players and export to CSV"""
    output_file = input("Enter output CSV filename (default: player_overalls_sorted.csv): ").strip()
    if not output_file:
        output_file = 'player_overalls_sorted.csv'
    
    # Confirm calculation
    confirm = input(f"Calculate overall ratings for ALL players and export to '{output_file}'? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Calculation cancelled")
        return
    
    manager.calculate_and_export_player_overalls(output_file)

def fix_team_id_mismatches(manager: TeamManager):
    """Fix team ID mismatches between league_teams and teams tables"""
    print("🔍 Checking for team ID mismatches...")
    
    # Confirm fix
    confirm = input("Fix team ID mismatches between league_teams and teams tables? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Fix cancelled")
        return
    
    manager.fix_team_id_mismatches()

def replace_player_from_csv(manager: TeamManager):
    """Replace a player from the active database with data from CSV entry"""
    print("\n🔄 REPLACE PLAYER FROM CSV")
    print("-" * 40)
    
    try:
        # Get player ID
        player_id_input = input("Enter player ID to replace: ").strip()
        if not player_id_input:
            print("❌ Player ID is required")
            return
        
        try:
            player_id = int(player_id_input)
        except ValueError:
            print("❌ Player ID must be a number")
            return
        
        # Get CSV file path
        csv_file_path = input("Enter CSV file path (or press Enter for 'pe6_player_data.csv'): ").strip()
        if not csv_file_path:
            csv_file_path = "pe6_player_data.csv"
        
        # Check if player exists in database
        cursor = manager.conn.cursor()
        cursor.execute("SELECT player_name, club_id FROM players WHERE id = ?", (player_id,))
        player_info = cursor.fetchone()
        
        if not player_info:
            print(f"❌ Player ID {player_id} not found in database")
            return
        
        player_name, club_id = player_info
        print(f"\n📊 Player found:")
        print(f"   Name: {player_name}")
        print(f"   ID: {player_id}")
        print(f"   Club ID: {club_id}")
        
        # Confirm replacement
        confirm = input(f"\n⚠️  Are you sure you want to replace {player_name} (ID: {player_id})? (y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ Operation cancelled")
            return
        
        # Perform replacement
        success = manager.replace_player_from_csv(player_id, csv_file_path)
        
        if success:
            print(f"\n🎉 Player replacement completed successfully!")
        else:
            print(f"\n❌ Player replacement failed!")
            
    except Exception as e:
        print(f"❌ Error in replace_player_from_csv: {e}")

def replace_player_manually(manager: TeamManager):
    """Replace a player by manually entering each field"""
    print("\n🔄 REPLACE PLAYER MANUALLY")
    print("-" * 40)
    
    try:
        # Get player ID
        player_id_input = input("Enter player ID to replace: ").strip()
        if not player_id_input:
            print("❌ Player ID is required")
            return
        
        try:
            player_id = int(player_id_input)
        except ValueError:
            print("❌ Player ID must be a number")
            return
        
        # Check if player exists in database
        cursor = manager.conn.cursor()
        cursor.execute("SELECT player_name, club_id FROM players WHERE id = ?", (player_id,))
        player_info = cursor.fetchone()
        
        if not player_info:
            print(f"❌ Player ID {player_id} not found in database")
            return
        
        player_name, club_id = player_info
        print(f"\n📊 Player found:")
        print(f"   Name: {player_name}")
        print(f"   ID: {player_id}")
        print(f"   Club ID: {club_id}")
        
        # Confirm replacement
        confirm = input(f"\n⚠️  Are you sure you want to manually edit {player_name} (ID: {player_id})? (y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ Operation cancelled")
            return
        
        # Perform manual replacement
        success = manager.replace_player_manually(player_id)
        
        if success:
            print(f"\n🎉 Player manual update completed successfully!")
        else:
            print(f"\n❌ Player manual update failed!")
            
    except Exception as e:
        print(f"❌ Error in replace_player_manually: {e}")

def rename_long_names(manager: TeamManager):
    """Rename players with 16+ character names one by one"""
    print("\n✏️ RENAME LONG PLAYER NAMES")
    print("-" * 40)
    
    try:
        cursor = manager.conn.cursor()
        renamed_count = 0
        skipped_count = 0
        
        while True:
            # Find the next player with 16+ character name
            cursor.execute("""
                SELECT id, player_name, club_id
                FROM players 
                WHERE LENGTH(player_name) >= 16
                ORDER BY LENGTH(player_name) DESC, player_name
                LIMIT 1
            """)
            player = cursor.fetchone()
            
            if not player:
                print(f"\n🎉 All done! No more players with 16+ character names.")
                print(f"📊 Summary: {renamed_count} renamed, {skipped_count} skipped")
                break
            
            player_id = player['id']
            current_name = player['player_name']
            
            print(f"\n📝 Player found with long name:")
            print(f"   ID: {player_id}")
            print(f"   Name: {current_name}")
            print(f"   Length: {len(current_name)} characters")
            
            while True:
                new_name = input(f"\n   Enter new name (or 'skip' to skip, 'quit' to exit): ").strip()
                
                if new_name.lower() == 'quit':
                    print(f"\n👋 Exiting... Summary: {renamed_count} renamed, {skipped_count} skipped")
                    return
                
                if new_name.lower() == 'skip':
                    print("   ⏭️  Skipped.")
                    skipped_count += 1
                    break
                
                if not new_name:
                    print("   ❌ Name cannot be empty. Please try again.")
                    continue
                
                if len(new_name) > 50:
                    print("   ❌ Name too long (max 50 characters). Please try again.")
                    continue
                
                # Confirm the change
                confirm = input(f"   Confirm change '{current_name}' → '{new_name}'? (y/n): ").strip().lower()
                
                if confirm == 'y':
                    # Update the player name
                    cursor.execute("UPDATE players SET player_name = ? WHERE id = ?", (new_name, player_id))
                    manager.conn.commit()
                    
                    print(f"   ✅ Successfully updated: '{current_name}' → '{new_name}'")
                    renamed_count += 1
                    break
                elif confirm == 'n':
                    print("   ❌ Change cancelled. Please try again.")
                    continue
                else:
                    print("   ❌ Please enter 'y' or 'n'.")
                    continue
        
    except KeyboardInterrupt:
        print(f"\n👋 Exiting... Summary: {renamed_count} renamed, {skipped_count} skipped")
    except Exception as e:
        print(f"❌ Database error: {e}")

def duplicate_player_stats(manager: TeamManager):
    """Duplicate player stats (games_played, goals, assists) for all players on a selected team"""
    print("\n📊 DUPLICATE PLAYER STATS")
    print("-" * 40)
    
    try:
        # Get team ID
        team_id_input = input("Enter team ID to duplicate stats for: ").strip()
        if not team_id_input:
            print("❌ Team ID is required")
            return
        
        try:
            team_id = int(team_id_input)
        except ValueError:
            print("❌ Team ID must be a number")
            return
        
        # Check if team exists
        cursor = manager.conn.cursor()
        cursor.execute("SELECT club_name FROM teams WHERE id = ?", (team_id,))
        team_info = cursor.fetchone()
        
        if not team_info:
            print(f"❌ Team ID {team_id} not found in database")
            return
        
        team_name = team_info['club_name']
        print(f"\n📊 Team found:")
        print(f"     Name: {team_name}")
        print(f"   ID: {team_id}")
        
        # Get all players on the team
        cursor.execute("SELECT id, player_name, games_played, goals, assists FROM players WHERE club_id = ?", (team_id,))
        players = cursor.fetchall()
        
        if not players:
            print(f"❌ No players found on team '{team_name}'")
            return
        
        print(f"\n📊 Found {len(players)} players on team '{team_name}':")
        print("-" * 80)
        print(f"{'ID':<6} {'Name':<25} {'Games':<6} {'Goals':<6} {'Assists':<8}")
        print("-" * 80)
        
        for player in players:
            print(f"{player['id']:<6} {player['player_name']:<25} {player['games_played'] or 0:<6} {player['goals'] or 0:<6} {player['assists'] or 0:<8}")
        
        # Confirm duplication
        confirm = input(f"\n⚠️  Are you sure you want to DUPLICATE stats for all {len(players)} players on '{team_name}'? (y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ Operation cancelled")
            return
        
        # Perform duplication
        updated_count = 0
        for player in players:
            player_id = player['id']
            current_games = player['games_played'] or 0
            current_goals = player['goals'] or 0
            current_assists = player['assists'] or 0
            
            new_games = current_games * 2
            new_goals = current_goals * 2
            new_assists = current_assists * 2
            
            cursor.execute("""
                UPDATE players 
                SET games_played = ?, goals = ?, assists = ? 
                WHERE id = ?
            """, (new_games, new_goals, new_assists, player_id))
            
            updated_count += 1
            print(f"   ✅ {player['player_name']}: Games {current_games}→{new_games}, Goals {current_goals}→{new_goals}, Assists {current_assists}→{new_assists}")
        
        manager.conn.commit()
        
        print(f"\n🎉 Successfully duplicated stats for {updated_count} players on team '{team_name}'!")
        
    except Exception as e:
        print(f"❌ Error duplicating player stats: {e}")
        if manager.conn:
            manager.conn.rollback()

def delete_colados_game(manager: TeamManager):
    """Delete a game from Colados League"""
    print("\n🗑️ DELETE GAME FROM COLADOS LEAGUE")
    print("-" * 40)
    
    try:
        cursor = manager.conn.cursor()
        
        # Fetch all played games
        cursor.execute("""
            SELECT lg.id, lg.home_team_name, lg.away_team_name, lg.home_score, lg.away_score, lg.round_number, d.name as division_name, lg.division_id
            FROM league_games lg
            JOIN divisions d ON lg.division_id = d.id
            WHERE lg.is_played = 1
            ORDER BY lg.id DESC
        """)
        
        games = cursor.fetchall()
        
        if not games:
            print("❌ No played games found in Colados League.")
            return
        
        print(f"\n📊 Found {len(games)} played games:")
        print("-" * 100)
        print(f"{'ID':<5} {'Division':<15} {'Home Team':<20} {'Score':<8} {'Away Team':<20} {'Round':<6}")
        print("-" * 100)
        
        for game in games:
            print(f"{game['id']:<5} {game['division_name']:<15} {game['home_team_name']:<20} {game['home_score']}-{game['away_score']:<8} {game['away_team_name']:<20} {game['round_number']:<6}")
        
        # Prompt user to select a game to delete
        while True:
            try:
                game_id_input = input("\nEnter the ID of the game to delete (or 'cancel' to exit): ").strip()
                if game_id_input.lower() == 'cancel':
                    print("❌ Operation cancelled.")
                    return
                
                game_id = int(game_id_input)
                
                # Check if the game ID exists in the list
                game_ids = [game['id'] for game in games]
                if game_id not in game_ids:
                    print("❌ Invalid game ID. Please try again.")
                    continue
                
                # Confirm deletion
                confirm = input(f"Are you sure you want to delete game ID {game_id}? (y/N): ").strip().lower()
                if confirm != 'y':
                    print("❌ Deletion cancelled.")
                    return
                
                # Reverse player scorers (goals and assists)
                # Get player stats from the game
                cursor.execute("""
                    SELECT player_id, goals, assists 
                    FROM player_game_stats 
                    WHERE game_id = ?
                """, (game_id,))
                
                player_stats = cursor.fetchall()
                for stat in player_stats:
                    cursor.execute("""
                        UPDATE players 
                        SET goals = goals - ?, assists = assists - ? 
                        WHERE id = ?
                    """, (stat['goals'], stat['assists'], stat['player_id']))
                
                # Delete player game stats
                cursor.execute("DELETE FROM player_game_stats WHERE game_id = ?", (game_id,))
                
                # Delete the game
                cursor.execute("DELETE FROM league_games WHERE id = ?", (game_id,))
                
                manager.conn.commit()
                print(f"✅ Game ID {game_id} deleted successfully, standings and scorers updated.")
                break
                
            except ValueError:
                print("❌ Please enter a valid number.")
            except Exception as e:
                print(f"❌ Error deleting game: {e}")
                manager.conn.rollback()
                break
    
    except Exception as e:
        print(f"❌ Error fetching games: {e}")

def main():
    """Main function"""
    print("🏆 Team Management System")
    print("Direct database access for team ownership management")
    
    manager = TeamManager()
    
    if not manager.connect():
        print("❌ Failed to connect to database")
        return
    
    try:
        while True:
            display_menu()
            choice = input("\nEnter your choice (1-18): ").strip()
            
            if choice == '1':
                list_users(manager)
            elif choice == '2':
                list_all_teams(manager)
            elif choice == '3':
                list_user_teams(manager)
            elif choice == '4':
                list_cpu_teams(manager)
            elif choice == '5':
                transfer_to_user(manager)
            elif choice == '6':
                transfer_to_cpu(manager)
            elif choice == '7':
                create_new_team(manager)
            elif choice == '8':
                add_budget_to_team(manager)
            elif choice == '9':
                subtract_budget_from_team(manager)
            elif choice == '10':
                update_players_from_newcomers(manager)
            elif choice == '11':
                calculate_overalls_and_export(manager)
            elif choice == '12':
                fix_team_id_mismatches(manager)
            elif choice == '13':
                replace_player_from_csv(manager)
            elif choice == '14':
                replace_player_manually(manager)
            elif choice == '15':
                rename_long_names(manager)
            elif choice == '16':
                duplicate_player_stats(manager)
            elif choice == '17':
                delete_colados_game(manager)
            elif choice == '18':
                print("👋 Goodbye!")
                break
            else:
                print("❌ Invalid choice. Please enter 1-18.")
    
    except KeyboardInterrupt:
        print("\n👋 Exiting...")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        manager.disconnect()

if __name__ == "__main__":
    main()
