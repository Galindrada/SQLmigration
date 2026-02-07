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
import random
import time

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
    
    def list_and_delete_secondary_teams(self) -> bool:
        """List all secondary teams and optionally delete them"""
        if not self.conn:
            return False
        
        try:
            cursor = self.conn.cursor()
            
            # Get all secondary teams (csv_visible = 0)
            cursor.execute("""
                SELECT t.id, t.club_name, t.budget, t.csv_visible,
                       COUNT(p.id) as player_count
                FROM teams t
                LEFT JOIN players p ON t.id = p.club_id
                WHERE t.csv_visible = 0
                GROUP BY t.id, t.club_name, t.budget, t.csv_visible
                ORDER BY t.club_name
            """)
            
            secondary_teams = cursor.fetchall()
            
            if not secondary_teams:
                print("✅ No secondary teams found in database")
                return True
            
            print(f"\n🏪 Found {len(secondary_teams)} secondary market teams:")
            print("-" * 80)
            print(f"{'ID':<6} {'Team Name':<30} {'Budget':<15} {'Players':<10}")
            print("-" * 80)
            
            for team in secondary_teams:
                print(f"{team['id']:<6} {team['club_name']:<30} €{team['budget']:,}".ljust(52) + f"{team['player_count']:<10}")
            
            # Ask if user wants to delete them
            confirm = input(f"\n🗑️  Delete all {len(secondary_teams)} secondary teams? (y/N): ").strip().lower()
            if confirm != 'y':
                print("❌ Operation cancelled")
                return False
            
            # Ask what to do with players
            print("\n📋 What should happen to players on these teams?")
            print("1. Move to No Club (ID 141)")
            print("2. Delete players entirely")
            player_action = input("Choose option (1/2): ").strip()
            
            deleted_teams = 0
            moved_players = 0
            deleted_players = 0
            
            for team in secondary_teams:
                team_id = team['id']
                team_name = team['club_name']
                player_count = team['player_count']
                
                if player_count > 0:
                    if player_action == '1':
                        # Move players to No Club
                        cursor.execute("UPDATE players SET club_id = 141 WHERE club_id = ?", (team_id,))
                        moved_players += player_count
                        print(f"   ✅ Moved {player_count} players from {team_name} to No Club")
                    elif player_action == '2':
                        # Delete players
                        cursor.execute("DELETE FROM players WHERE club_id = ?", (team_id,))
                        deleted_players += player_count
                        print(f"   ✅ Deleted {player_count} players from {team_name}")
                
                # Delete from league_teams first (foreign key)
                cursor.execute("DELETE FROM league_teams WHERE team_name = ?", (team_name,))
                
                # Delete the team
                cursor.execute("DELETE FROM teams WHERE id = ?", (team_id,))
                deleted_teams += 1
            
            self.conn.commit()
            
            print(f"\n✅ Successfully deleted {deleted_teams} secondary teams")
            if moved_players > 0:
                print(f"   📦 {moved_players} players moved to No Club")
            if deleted_players > 0:
                print(f"   🗑️  {deleted_players} players deleted")
            
            return True
            
        except Exception as e:
            print(f"❌ Error managing secondary teams: {e}")
            if self.conn:
                self.conn.rollback()
            return False
    
    def create_secondary_market_team(self, team_name: str, budget: int = 400000000) -> bool:
        """Create a secondary team for market depth (invisible in CSV exports)"""
        if not self.conn:
            return False
        
        try:
            cursor = self.conn.cursor()
            
            # Check if team name already exists
            cursor.execute("SELECT id FROM teams WHERE club_name = ?", (team_name,))
            if cursor.fetchone():
                print(f"❌ Team '{team_name}' already exists")
                return False
            
            # Create new secondary team with csv_visible=0
            cursor.execute("""
                INSERT INTO teams (club_name, budget, available_cap, stance, total_salaries, csv_visible)
                VALUES (?, ?, ?, 'Tinkering', 0, 0)
            """, (team_name, budget, budget))
            
            team_id = cursor.lastrowid
            
            # Assign to CPU (user_id = 1)
            cursor.execute("""
                INSERT INTO league_teams (team_name, user_id)
                VALUES (?, 1)
            """, (team_name,))
            
            self.conn.commit()
            print(f"✅ Successfully created secondary market team '{team_name}' with ID {team_id}")
            print(f"   Budget: €{budget:,}")
            print(f"   CSV Visible: NO (players will appear as 'No Club' in CSV exports)")
            print(f"   Owner: CPU")
            return True
            
        except Exception as e:
            print(f"❌ Error creating secondary team: {e}")
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
                    
                    # Check if the correct_id already exists in league_teams
                    cursor.execute("""
                        SELECT id, team_name, user_id FROM league_teams WHERE id = ?
                    """, (correct_id,))
                    existing_league_team = cursor.fetchone()
                    
                    if existing_league_team:
                        # The target ID already exists in league_teams
                        # Check if it's the same team (same name) or different
                        if existing_league_team['team_name'] == team['team_name']:
                            # Same team, just delete the duplicate entry
                            print(f"     ℹ️  Duplicate entry found - deleting old entry (ID {team['id']})")
                            cursor.execute("""
                                DELETE FROM league_teams WHERE id = ? AND team_name = ?
                            """, (team['id'], team['team_name']))
                            print(f"     ✅ Deleted duplicate league_teams entry (ID {team['id']})")
                        else:
                            # Different team with conflicting ID - check if the existing team also has a mismatch
                            print(f"     ⚠️  Target ID {correct_id} already exists for '{existing_league_team['team_name']}'")
                            
                            # Check if the existing team's ID matches its teams table entry
                            cursor.execute("""
                                SELECT id FROM teams WHERE club_name = ?
                            """, (existing_league_team['team_name'],))
                            existing_team_correct = cursor.fetchone()
                            
                            if existing_team_correct and existing_team_correct['id'] == correct_id:
                                # The existing team is correctly using this ID
                                # We need to find the correct ID for the current team, or use the old ID
                                # Check if the old ID (team['id']) is available in teams table
                                cursor.execute("""
                                    SELECT club_name FROM teams WHERE id = ?
                                """, (team['id'],))
                                old_id_team = cursor.fetchone()
                                
                                if not old_id_team:
                                    # Old ID doesn't exist in teams table - this team should be deleted
                                    print(f"     ❌ Team '{team['team_name']}' has no matching entry in teams table")
                                    print(f"     ℹ️  Deleting orphaned league_teams entry")
                                    cursor.execute("""
                                        DELETE FROM league_teams WHERE id = ? AND team_name = ?
                                    """, (team['id'], team['team_name']))
                                    print(f"     ✅ Deleted orphaned entry")
                                else:
                                    # Old ID exists but for a different team - complex conflict
                                    print(f"     ⚠️  Complex conflict: ID {team['id']} belongs to '{old_id_team['club_name']}' in teams table")
                                    print(f"     ⚠️  Cannot automatically resolve - manual intervention needed")
                            else:
                                # The existing team also has a mismatch - we can swap or reassign
                                if existing_team_correct:
                                    existing_correct_id = existing_team_correct['id']
                                    print(f"     ℹ️  Existing team '{existing_league_team['team_name']}' should use ID {existing_correct_id}")
                                    
                                    # Check if existing_correct_id is available
                                    cursor.execute("""
                                        SELECT id FROM league_teams WHERE id = ?
                                    """, (existing_correct_id,))
                                    existing_correct_id_taken = cursor.fetchone()
                                    
                                    if not existing_correct_id_taken:
                                        # We can swap: move existing team to its correct ID, then current team to correct_id
                                        print(f"     🔄 Swapping IDs: Moving '{existing_league_team['team_name']}' to ID {existing_correct_id}")
                                        
                                        # Update foreign keys for existing team first
                                        old_id = team['id']
                                        tables_to_update = [
                                            ('team_players', 'team_id'),
                                            ('user_cpu_offers', 'cpu_team_id'),
                                            ('user_cpu_offers', 'buyer_team_id'),
                                        ]
                                        
                                        for table_name, column_name in tables_to_update:
                                            try:
                                                cursor.execute(f"""
                                                    UPDATE {table_name} 
                                                    SET {column_name} = ? 
                                                    WHERE {column_name} = ?
                                                """, (existing_correct_id, correct_id))
                                            except:
                                                pass
                                        
                                        # Move existing team to its correct ID
                                        cursor.execute("""
                                            UPDATE league_teams 
                                            SET id = ? 
                                            WHERE id = ? AND team_name = ?
                                        """, (existing_correct_id, correct_id, existing_league_team['team_name']))
                                        
                                        # Now update foreign keys for current team
                                        for table_name, column_name in tables_to_update:
                                            try:
                                                cursor.execute(f"""
                                                    UPDATE {table_name} 
                                                    SET {column_name} = ? 
                                                    WHERE {column_name} = ?
                                                """, (correct_id, old_id))
                                            except:
                                                pass
                                        
                                        # Move current team to correct_id
                                        cursor.execute("""
                                            UPDATE league_teams 
                                            SET id = ? 
                                            WHERE id = ? AND team_name = ?
                                        """, (correct_id, old_id, team['team_name']))
                                        
                                        print(f"     ✅ Swapped IDs: '{team['team_name']}' now uses ID {correct_id}")
                                    else:
                                        print(f"     ⚠️  Cannot swap - ID {existing_correct_id} also taken. Manual intervention needed.")
                                else:
                                    print(f"     ⚠️  Existing team '{existing_league_team['team_name']}' not found in teams table")
                                    print(f"     ⚠️  Cannot automatically resolve - manual intervention needed")
                    else:
                        # Target ID doesn't exist in league_teams, safe to update
                        # But we need to update all foreign key references first
                        old_id = team['id']
                        
                        # Update all foreign key references in other tables
                        # Check what tables reference league_teams.id
                        tables_to_update = [
                            ('team_players', 'team_id'),
                            ('user_cpu_offers', 'cpu_team_id'),
                            ('user_cpu_offers', 'buyer_team_id'),
                        ]
                        
                        updated_refs = 0
                        for table_name, column_name in tables_to_update:
                            try:
                                cursor.execute(f"""
                                    UPDATE {table_name} 
                                    SET {column_name} = ? 
                                    WHERE {column_name} = ?
                                """, (correct_id, old_id))
                                updated_refs += cursor.rowcount
                            except Exception as e:
                                # Table or column might not exist, skip
                                pass
                        
                        if updated_refs > 0:
                            print(f"     ℹ️  Updated {updated_refs} foreign key references")
                        
                        # Now update the league_teams entry
                        cursor.execute("""
                            UPDATE league_teams 
                            SET id = ? 
                            WHERE id = ? AND team_name = ?
                        """, (correct_id, old_id, team['team_name']))
                        
                        print(f"     ✅ Updated league_teams entry from ID {old_id} to {correct_id}")
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
                'contract_years_remaining', 'market_value', 'yearly_wage_rise', 'games_played', 'goals', 'assists', 'MVP',
                'championships_won', 'cups_won', 'seed_player', 'draftee'
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
                                   'yearly_wage_rise', 'games_played', 'goals', 'assists', 'MVP', 'championships_won', 'cups_won',
                                   'seed_player', 'draftee']:
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

    def fix_invalid_face_skin_combinations(self) -> bool:
        """Fix invalid preset_face_number values based on skin_color using data from original.sqlite"""
        if not self.conn:
            print("❌ Not connected to database")
            return False
        
        try:
            import random
            
            # Valid face numbers for each skin color (from original.sqlite IDs 1-4783)
            VALID_FACES_BY_SKIN = {
                1: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 34, 36, 37, 38, 40, 41, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 102, 104, 105, 106, 107, 108, 109, 110, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 123, 124, 125, 126, 129, 130, 131, 133, 134, 135, 136, 138, 139, 140, 141, 142, 143, 147, 148, 149, 150, 151, 152, 153, 154, 155, 156, 158, 159, 160, 161, 162, 163, 164, 167, 168, 169, 170, 171, 172, 174, 175, 176, 177, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187, 188, 190, 191, 193, 194, 196, 197, 198, 199, 200, 201, 203, 206, 207, 208, 212, 215, 219, 221, 222, 224, 225, 226, 228, 230, 235, 236, 239, 242, 246, 247, 249, 250, 251, 252, 255, 260, 263, 266, 268, 269, 274, 275, 278, 283, 288, 295, 296, 298, 301, 304, 305, 306, 308, 311, 313, 314, 315, 316, 317, 318, 319, 320, 321, 322, 323, 324, 325, 327, 328, 329, 330, 331, 332, 333, 334, 338, 340, 341, 342, 343, 345, 346, 350, 354, 356, 361],
                2: [1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 17, 18, 19, 21, 22, 23, 24, 25, 26, 27, 29, 30, 33, 34, 36, 39, 42, 43, 45, 48, 50, 51, 59, 69, 81, 82, 83, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 103, 104, 105, 107, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 126, 130, 148, 149, 152, 164, 168, 169, 171, 172],
                3: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 35, 36, 38, 39, 40, 41, 44, 45, 46, 48, 49, 50, 53, 54, 55, 58, 61, 63, 64, 66, 67, 68],
                4: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 17, 18, 19, 20, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 36, 37, 42, 43, 44, 47]
            }
            
            cursor = self.conn.cursor()
            
            print("🔍 Checking for invalid face/skin combinations...")
            
            # Get all players with their skin_color and preset_face_number
            cursor.execute("""
                SELECT id, player_name, skin_color, preset_face_number 
                FROM players 
                WHERE skin_color IS NOT NULL AND preset_face_number IS NOT NULL
            """)
            
            players = cursor.fetchall()
            
            if not players:
                print("❌ No players found with skin_color and preset_face_number")
                return False
            
            print(f"📊 Checking {len(players)} players...")
            
            invalid_players = []
            
            for player in players:
                player_id = player['id']
                player_name = player['player_name']
                skin_color = player['skin_color']
                face_number = player['preset_face_number']
                
                # Check if skin_color is valid
                if skin_color not in VALID_FACES_BY_SKIN:
                    print(f"   ⚠️  Player ID {player_id} ({player_name}): Invalid skin_color {skin_color}")
                    continue
                
                # Check if face_number is valid for this skin_color
                valid_faces = VALID_FACES_BY_SKIN[skin_color]
                if face_number not in valid_faces:
                    invalid_players.append({
                        'id': player_id,
                        'name': player_name,
                        'skin_color': skin_color,
                        'old_face': face_number,
                        'valid_faces': valid_faces
                    })
            
            if not invalid_players:
                print("✅ All players have valid face/skin combinations!")
                return True
            
            print(f"\n⚠️  Found {len(invalid_players)} players with invalid combinations:")
            print("-" * 80)
            print(f"{'ID':<6} {'Name':<25} {'Skin':<5} {'Old Face':<10} {'Status':<20}")
            print("-" * 80)
            
            for player in invalid_players[:10]:  # Show first 10
                print(f"{player['id']:<6} {player['name']:<25} {player['skin_color']:<5} {player['old_face']:<10} {'Invalid':<20}")
            
            if len(invalid_players) > 10:
                print(f"   ... and {len(invalid_players) - 10} more")
            
            # Ask for confirmation
            confirm = input(f"\n🔧 Fix all {len(invalid_players)} invalid combinations? (y/N): ").strip().lower()
            if confirm != 'y':
                print("❌ Operation cancelled")
                return False
            
            # Fix invalid combinations
            fixed_count = 0
            
            for player in invalid_players:
                player_id = player['id']
                player_name = player['name']
                old_face = player['old_face']
                valid_faces = player['valid_faces']
                
                # Select a random valid face number
                new_face = random.choice(valid_faces)
                
                # Update the player
                cursor.execute("""
                    UPDATE players 
                    SET preset_face_number = ? 
                    WHERE id = ?
                """, (new_face, player_id))
                
                fixed_count += 1
                
                if fixed_count <= 20:  # Show first 20 fixes
                    print(f"   ✅ {player_name} (ID: {player_id}): Face {old_face} → {new_face}")
            
            if fixed_count > 20:
                print(f"   ... and {fixed_count - 20} more fixes")
            
            # Commit changes
            self.conn.commit()
            
            print(f"\n✅ Successfully fixed {fixed_count} invalid face/skin combinations!")
            print(f"📊 Summary:")
            print(f"   - Players checked: {len(players)}")
            print(f"   - Invalid combinations found: {len(invalid_players)}")
            print(f"   - Fixed: {fixed_count}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error fixing face/skin combinations: {e}")
            if self.conn:
                self.conn.rollback()
            return False
    
    def retire_player_with_random_regen(self, player_id: int) -> bool:
        """Retire a player and generate a regen with random nationality to replace them"""
        if not self.conn:
            print("❌ Not connected to database")
            return False
        
        try:
            cursor = self.conn.cursor()
            
            # Get player details
            cursor.execute("""
                SELECT p.*, t.club_name
                FROM players p
                JOIN teams t ON p.club_id = t.id
                WHERE p.id = ?
            """, (player_id,))
            
            player = cursor.fetchone()
            if not player:
                print(f"❌ Player ID {player_id} not found in database")
                return False
            
            player_name = player['player_name']
            team_name = player['club_name']
            team_id = player['club_id']
            
            print(f"\n👴 Retiring Player:")
            print(f"   Name: {player_name}")
            print(f"   ID: {player_id}")
            print(f"   Team: {team_name}")
            print(f"   Age: {player['age'] if player['age'] is not None else 'N/A'}")
            print(f"   Position: {player['registered_position'] if player['registered_position'] is not None else 'N/A'}")
            
            # Generate regen using the same system as end-of-season (random nationality)
            from game_mechanics import generate_proper_regen
            
            # Convert player data to dictionary format for regen generation
            retired_player_data = dict(player)
            
            # Create regen data WITHOUT nationality override (random nationality)
            print(f"\n🔄 Generating regen with random nationality...")
            regen_data = generate_proper_regen(retired_player_data, override_nationality=None)
            
            # Modify regen using CSV instead of original.sqlite (to avoid PythonAnywhere concurrent DB issues)
            regen_data = self.modify_regen_with_base_player_from_csv(regen_data)
            
            print(f"   ✅ Regen generated: {regen_data['player_name']} ({regen_data['nationality']})")
            
            # Update the player with regen data (reuse the same ID)
            cursor.execute("""
                UPDATE players SET
                    player_name = ?, shirt_name = ?, age = ?, nationality = ?, skin_color = ?,
                    strong_foot = ?, favoured_side = ?, registered_position = ?,
                    height = ?, weight = ?,
                    salary = ?, contract_years_remaining = ?, yearly_wage_rise = ?,
                    development_key = ?, trait_key = ?, games_played = ?, goals = ?, assists = ?, MVP = ?,
                    attack = ?, defense = ?, balance = ?, stamina = ?, top_speed = ?,
                    acceleration = ?, response = ?, agility = ?, dribble_accuracy = ?,
                    dribble_speed = ?, short_pass_accuracy = ?, short_pass_speed = ?,
                    long_pass_accuracy = ?, long_pass_speed = ?, shot_accuracy = ?,
                    shot_power = ?, shot_technique = ?, free_kick_accuracy = ?, swerve = ?,
                    heading = ?, jump = ?, technique = ?, aggression = ?, mentality = ?,
                    goal_keeping = ?, team_work = ?, consistency = ?, condition_fitness = ?,
                    gk = ?, cwp = ?, cbt = ?, sb = ?, dmf = ?, wb = ?, cmf = ?, smf = ?,
                    amf = ?, wf = ?, ss = ?, cf = ?, dribbling_skill = ?, tactical_dribble = ?,
                    positioning = ?, reaction = ?, playmaking = ?, passing = ?, scoring = ?,
                    one_one_scoring = ?, post_player = ?, lines = ?, middle_shooting = ?,
                    side = ?, centre = ?, penalties = ?, one_touch_pass = ?, outside = ?,
                    marking = ?, sliding = ?, covering = ?, d_line_control = ?,
                    penalty_stopper = ?, one_on_one_stopper = ?, long_throw = ?,
                    face_type = ?, preset_face_number = ?, head_width = ?, neck_length = ?,
                    neck_width = ?, shoulder_height = ?, shoulder_width = ?, chest_measurement = ?,
                    waist_circumference = ?, arm_circumference = ?, leg_circumference = ?,
                    calf_circumference = ?, leg_length = ?, wristband = ?, wristband_color = ?,
                    international_number = ?, classic_number = ?, club_number = ?,
                    dribble_style = ?, free_kick_style = ?, pk_style = ?, drop_kick_style = ?, seed_player = ?
                WHERE id = ?
            """, (
                regen_data['player_name'], regen_data['shirt_name'], regen_data['age'], regen_data['nationality'], regen_data['skin_color'],
                regen_data['strong_foot'], regen_data['favoured_side'], regen_data['registered_position'],
                regen_data['height'], regen_data['weight'],
                regen_data['salary'], regen_data['contract_years_remaining'], regen_data['yearly_wage_rise'],
                regen_data['development_key'], regen_data['trait_key'], regen_data['games_played'], regen_data['goals'], regen_data['assists'], regen_data.get('MVP', 0),
                regen_data['attack'], regen_data['defense'], regen_data['balance'], regen_data['stamina'], regen_data['top_speed'],
                regen_data['acceleration'], regen_data['response'], regen_data['agility'], regen_data['dribble_accuracy'],
                regen_data['dribble_speed'], regen_data['short_pass_accuracy'], regen_data['short_pass_speed'],
                regen_data['long_pass_accuracy'], regen_data['long_pass_speed'], regen_data['shot_accuracy'],
                regen_data['shot_power'], regen_data['shot_technique'], regen_data['free_kick_accuracy'], regen_data['swerve'],
                regen_data['heading'], regen_data['jump'], regen_data['technique'], regen_data['aggression'], regen_data['mentality'],
                regen_data['goal_keeping'], regen_data['team_work'], regen_data['consistency'], regen_data['condition_fitness'],
                regen_data['gk'], regen_data['cwp'], regen_data['cbt'], regen_data['sb'], regen_data['dmf'], regen_data['wb'], regen_data['cmf'], regen_data['smf'],
                regen_data['amf'], regen_data['wf'], regen_data['ss'], regen_data['cf'], regen_data['dribbling_skill'], regen_data['tactical_dribble'],
                regen_data['positioning'], regen_data['reaction'], regen_data['playmaking'], regen_data['passing'], regen_data['scoring'],
                regen_data['one_one_scoring'], regen_data['post_player'], regen_data['lines'], regen_data['middle_shooting'],
                regen_data['side'], regen_data['centre'], regen_data['penalties'], regen_data['one_touch_pass'], regen_data['outside'],
                regen_data['marking'], regen_data['sliding'], regen_data['covering'], regen_data['d_line_control'],
                regen_data['penalty_stopper'], regen_data['one_on_one_stopper'], regen_data['long_throw'],
                regen_data['face_type'], regen_data['preset_face_number'], regen_data['head_width'], regen_data['neck_length'],
                regen_data['neck_width'], regen_data['shoulder_height'], regen_data['shoulder_width'], regen_data['chest_measurement'],
                regen_data['waist_circumference'], regen_data['arm_circumference'], regen_data['leg_circumference'],
                regen_data['calf_circumference'], regen_data['leg_length'], regen_data['wristband'], regen_data['wristband_color'],
                regen_data['international_number'], regen_data['classic_number'], regen_data['club_number'],
                regen_data['dribble_style'], regen_data['free_kick_style'], regen_data['pk_style'], regen_data['drop_kick_style'],
                regen_data.get('seed_player'),
                player_id
            ))
            
            # Calculate overall rating and bundled skills for the new regen
            from refresh_and_reimport import calculate_player_overall
            from game_mechanics import calculate_bundled_skill_ratings
            
            # Get the updated player data to calculate overall
            cursor.execute("SELECT * FROM players WHERE id = ?", (player_id,))
            updated_player = cursor.fetchone()
            updated_player_dict = dict(updated_player)
            
            # Calculate overall rating
            overall = calculate_player_overall(updated_player_dict)
            
            # Calculate bundled skill ratings
            bundled_ratings = calculate_bundled_skill_ratings(updated_player_dict)
            
            # Update player with overall and bundled ratings
            cursor.execute("""
                UPDATE players SET
                    overall = ?,
                    attack_rating = ?,
                    defense_rating = ?,
                    physical_rating = ?,
                    power_rating = ?,
                    technique_rating = ?,
                    goalkeeping_rating = ?
                WHERE id = ?
            """, (
                overall,
                bundled_ratings['attack_rating'],
                bundled_ratings['defense_rating'],
                bundled_ratings['physical_rating'],
                bundled_ratings['power_rating'],
                bundled_ratings['technique_rating'],
                bundled_ratings['goalkeeping_rating'],
                player_id
            ))
            
            # Reset international statistics for the new regen (they should start with clean records)
            cursor.execute("""
                UPDATE players 
                SET international_caps_total = 0,
                    international_goals = 0,
                    international_assists = 0,
                    current_season_caps = 0,
                    current_international_goals = 0,
                    current_international_assists = 0
                WHERE id = ?
            """, (player_id,))
            
            # Clear individual achievements for the new regen
            cursor.execute("DELETE FROM player_individual_achievements WHERE player_id = ?", (player_id,))
            
            # Assign a face from the regen_faces folder based on skin_color
            from game_mechanics import assign_regen_face
            import os
            skin_color = regen_data.get('skin_color', 1)
            # Get the app root path (use current working directory or script directory)
            # assign_regen_face will default to script directory if None is passed
            app_root = os.getcwd() if os.path.exists(os.path.join(os.getcwd(), 'static')) else None
            assigned_face = assign_regen_face(player_id, skin_color, app_root)
            if assigned_face:
                cursor.execute("UPDATE players SET profile_image = ? WHERE id = ?", (assigned_face, player_id))
            
            self.conn.commit()
            
            print(f"\n✅ Successfully retired {player_name} and generated regen:")
            print(f"   New Name: {regen_data['player_name']}")
            print(f"   Nationality: {regen_data['nationality']}")
            print(f"   Age: {regen_data['age']}")
            print(f"   Overall: {overall}")
            print(f"   Position: {regen_data['registered_position']}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error retiring player: {e}")
            import traceback
            traceback.print_exc()
            if self.conn:
                self.conn.rollback()
            return False
    
    def modify_regen_with_base_player_from_csv(self, regen_data: Dict) -> Dict:
        """
        Modify regen_data by using attributes from a base player in pe6_player_data.csv.
        This is a CSV-based alternative to avoid PythonAnywhere concurrent DB issues.
        
        Args:
            regen_data: The regen data dictionary to modify
        
        Returns:
            Modified regen_data dictionary
        """
        # Seed the random number generator to ensure different results on each restart
        random.seed(time.time())
        
        # Randomly select a base player ID from 1 to 4783
        base_player_id = random.randint(1, 4783)
        
        try:
            # Try to read from pe6_player_data.csv
            csv_path = 'pe6_player_data.csv'
            if not os.path.exists(csv_path):
                print(f"⚠️  Warning: {csv_path} not found. Skipping base player modification.")
                return regen_data
            
            # Read CSV file
            try:
                df = pd.read_csv(csv_path, encoding='latin1')
            except UnicodeDecodeError:
                try:
                    df = pd.read_csv(csv_path, encoding='utf-8')
                except UnicodeDecodeError:
                    df = pd.read_csv(csv_path, encoding='iso-8859-1')
            
            # Find the base player by ID
            base_player_row = df[df['ID'] == base_player_id]
            
            if base_player_row.empty:
                print(f"⚠️  Warning: Base player with ID {base_player_id} not found in CSV. Skipping modification.")
                return regen_data
            
            # Convert to dictionary (use lowercase column names to match DB)
            base_player_dict = base_player_row.iloc[0].to_dict()
            
            # Map CSV column names to database column names (same mapping as import_pes6_data.py)
            csv_to_db_mapping = {
                'ID': 'id',
                'NAME': 'player_name',
                'SHIRT_NAME': 'shirt_name',
                'REGISTERED POSITION': 'registered_position',
                'HEIGHT': 'height',
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
            
            # Create normalized base player dict with DB column names
            normalized_base_player = {}
            for csv_col, db_col in csv_to_db_mapping.items():
                if csv_col in base_player_dict:
                    value = base_player_dict[csv_col]
                    # Handle NaN values
                    if pd.isna(value):
                        normalized_base_player[db_col] = None
                    else:
                        # Convert to int if it's a numeric column
                        if db_col in ['gk', 'cwp', 'cbt', 'sb', 'dmf', 'wb', 'cmf', 'smf', 'amf', 'wf', 'ss', 'cf',
                                     'height', 'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
                                     'response', 'agility', 'dribble_accuracy', 'dribble_speed', 'short_pass_accuracy',
                                     'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed', 'shot_accuracy',
                                     'shot_power', 'shot_technique', 'free_kick_accuracy', 'swerve', 'heading', 'jump',
                                     'technique', 'aggression', 'goal_keeping', 'team_work', 'consistency',
                                     'condition_fitness', 'dribbling_skill', 'tactical_dribble', 'positioning', 'reaction',
                                     'playmaking', 'passing', 'scoring', 'one_one_scoring', 'post_player', 'lines',
                                     'middle_shooting', 'side', 'centre', 'penalties', 'one_touch_pass', 'outside',
                                     'marking', 'sliding', 'covering', 'd_line_control', 'penalty_stopper',
                                     'one_on_one_stopper', 'long_throw', 'registered_position']:
                            try:
                                normalized_base_player[db_col] = int(value)
                            except (ValueError, TypeError):
                                normalized_base_player[db_col] = 0
                        else:
                            normalized_base_player[db_col] = value
            
            # Persist the seed for downstream development orientation
            regen_data['seed_player'] = int(base_player_id)
            
            # Generate random age between 15-20
            age = random.randint(15, 20)
            regen_data['age'] = age
            
            # Calculate age-based skill modifier (same as original function)
            age_modifier = 0
            if age == 15:
                age_modifier = 4 + random.randint(-3, 3)
            elif age == 16:
                age_modifier = 2 + random.randint(-3, 3)
            elif age == 17:
                age_modifier = 1 + random.randint(-3, 3)
            elif age == 18:
                age_modifier = -2 + random.randint(-3, 3)
            elif age == 19:
                age_modifier = -4 + random.randint(-3, 3)
            elif age == 20:
                age_modifier = -6 + random.randint(-3, 3)
            
            # Get inner_strength from regen_data
            inner_strength = regen_data.get('inner_strength', 5)
            
            # Calculate inner_strength-based penalty
            if inner_strength == 9:
                inner_strength_penalty = 15 + random.randint(-3, 3)
            elif inner_strength == 1:
                inner_strength_penalty = 30
            else:
                inner_strength_penalty = 30 - ((inner_strength - 1) / 8) * 15 + random.randint(-3, 3)
            
            # Define positional attributes
            positional_attributes = {
                'gk': normalized_base_player.get('gk', 0) or 0,
                'cwp': normalized_base_player.get('cwp', 0) or 0,
                'cbt': normalized_base_player.get('cbt', 0) or 0,
                'sb': normalized_base_player.get('sb', 0) or 0,
                'dmf': normalized_base_player.get('dmf', 0) or 0,
                'wb': normalized_base_player.get('wb', 0) or 0,
                'cmf': normalized_base_player.get('cmf', 0) or 0,
                'smf': normalized_base_player.get('smf', 0) or 0,
                'amf': normalized_base_player.get('amf', 0) or 0,
                'wf': normalized_base_player.get('wf', 0) or 0,
                'ss': normalized_base_player.get('ss', 0) or 0,
                'cf': normalized_base_player.get('cf', 0) or 0
            }
            
            # Inherit registered position from base player
            base_registered_position = normalized_base_player.get('registered_position', None)
            if base_registered_position is not None:
                regen_data['registered_position'] = base_registered_position
                regen_data['game_position'] = base_registered_position
            
            # Check if player is a goalkeeper
            is_goalkeeper = False
            if base_registered_position is not None:
                if base_registered_position == 0 or base_registered_position == '0' or str(base_registered_position) == '0':
                    is_goalkeeper = True
            
            # Define special attributes
            special_attributes = {
                'dribbling_skill': normalized_base_player.get('dribbling_skill', 0) or 0,
                'tactical_dribble': normalized_base_player.get('tactical_dribble', 0) or 0,
                'positioning': normalized_base_player.get('positioning', 0) or 0,
                'reaction': normalized_base_player.get('reaction', 0) or 0,
                'playmaking': normalized_base_player.get('playmaking', 0) or 0,
                'passing': normalized_base_player.get('passing', 0) or 0,
                'scoring': normalized_base_player.get('scoring', 0) or 0,
                'one_one_scoring': normalized_base_player.get('one_one_scoring', 0) or 0,
                'post_player': normalized_base_player.get('post_player', 0) or 0,
                'lines': normalized_base_player.get('lines', 0) or 0,
                'middle_shooting': normalized_base_player.get('middle_shooting', 0) or 0,
                'side': normalized_base_player.get('side', 0) or 0,
                'centre': normalized_base_player.get('centre', 0) or 0,
                'penalties': normalized_base_player.get('penalties', 0) or 0,
                'one_touch_pass': normalized_base_player.get('one_touch_pass', 0) or 0,
                'outside': normalized_base_player.get('outside', 0) or 0,
                'marking': normalized_base_player.get('marking', 0) or 0,
                'sliding': normalized_base_player.get('sliding', 0) or 0,
                'covering': normalized_base_player.get('covering', 0) or 0,
                'd_line_control': normalized_base_player.get('d_line_control', 0) or 0,
                'penalty_stopper': normalized_base_player.get('penalty_stopper', 0) or 0,
                'one_on_one_stopper': normalized_base_player.get('one_on_one_stopper', 0) or 0,
                'long_throw': normalized_base_player.get('long_throw', 0) or 0
            }
            
            # Define skill attributes (apply penalties)
            skill_attributes = {}
            skill_fields = [
                'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
                'response', 'agility', 'dribble_accuracy', 'dribble_speed', 'short_pass_accuracy',
                'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed', 'shot_accuracy',
                'shot_power', 'shot_technique', 'free_kick_accuracy', 'swerve', 'heading',
                'jump', 'technique', 'aggression', 'goal_keeping', 'team_work', 'mentality'
            ]
            
            for skill in skill_fields:
                base_value = normalized_base_player.get(skill, 0) or 0
                if base_value is not None:
                    total_penalty = inner_strength_penalty + age_modifier
                    skill_randomness = random.randint(-6, 6)
                    skill_attributes[skill] = max(1, int(base_value - total_penalty + skill_randomness))
                else:
                    skill_attributes[skill] = 1
            
            # If player is not a goalkeeper, set goal_keeping to 50
            if not is_goalkeeper:
                skill_attributes['goal_keeping'] = 50
            
            # Keep consistency unchanged
            skill_attributes['consistency'] = int(normalized_base_player.get('consistency', 50) or 50)
            skill_attributes['condition_fitness'] = int(normalized_base_player.get('condition_fitness', 50) or 50)
            
            # Update regen_data with modified attributes
            regen_data.update(positional_attributes)
            regen_data.update(special_attributes)
            regen_data.update(skill_attributes)
            
            player_name = normalized_base_player.get('player_name', 'Unknown')
            print(f"   ✅ Modified regen using base player ID {base_player_id} ({player_name})")
            print(f"   Age: {age}, Inner Strength: {inner_strength}, Total penalty: {inner_strength_penalty + age_modifier}")
            
        except Exception as e:
            print(f"⚠️  Warning: Error modifying regen with base player from CSV: {e}")
            import traceback
            traceback.print_exc()
        
        return regen_data
    
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

def fix_loaned_by_values(manager: TeamManager):
    """Fix loaned_by field: convert numeric team IDs to proper club names"""
    try:
        print("\n" + "="*80)
        print("🔧 FIX LOANED_BY VALUES")
        print("="*80)
        print("This routine will find all players with numeric loaned_by values")
        print("(team IDs) and convert them to proper club names.\n")
        
        cursor = manager.conn.cursor()
        
        # Find players with numeric loaned_by values
        cursor.execute("""
            SELECT p.id, p.player_name, p.loaned_by
            FROM players p
            WHERE p.loaned_by IS NOT NULL 
            AND p.loaned_by != ''
            AND CAST(p.loaned_by AS TEXT) GLOB '[0-9]*'
            AND CAST(p.loaned_by AS TEXT) NOT GLOB '*[^0-9]*'
        """)
        
        players_to_fix = cursor.fetchall()
        
        if not players_to_fix:
            print("✅ No players found with numeric loaned_by values. All values are correct!")
            return
        
        print(f"Found {len(players_to_fix)} player(s) with numeric loaned_by values:\n")
        
        fixed_count = 0
        error_count = 0
        
        for player in players_to_fix:
            team_id = int(player['loaned_by'])
            cursor.execute("SELECT club_name FROM teams WHERE id = ?", (team_id,))
            team_result = cursor.fetchone()
            
            if team_result:
                club_name = team_result['club_name']
                print(f"  Fixing: {player['player_name']} (ID {player['id']})")
                print(f"    Old: loaned_by='{player['loaned_by']}' (team ID {team_id})")
                print(f"    New: loaned_by='{club_name}'")
                
                cursor.execute("UPDATE players SET loaned_by = ? WHERE id = ?", (club_name, player['id']))
                fixed_count += 1
            else:
                print(f"  ⚠️  ERROR: Could not find team with ID {team_id} for player {player['player_name']} (ID {player['id']})")
                error_count += 1
        
        if fixed_count > 0:
            manager.conn.commit()
            print(f"\n✅ Successfully fixed {fixed_count} player(s)")
        else:
            print(f"\n⚠️  No players were fixed")
        
        if error_count > 0:
            print(f"⚠️  {error_count} player(s) could not be fixed (team ID not found)")
        
        # Verify the fix
        print("\n=== VERIFICATION ===")
        cursor.execute("""
            SELECT p.id, p.player_name, p.loaned_by
            FROM players p
            WHERE p.loaned_by IS NOT NULL 
            AND p.loaned_by != ''
            AND CAST(p.loaned_by AS TEXT) GLOB '[0-9]*'
            AND CAST(p.loaned_by AS TEXT) NOT GLOB '*[^0-9]*'
        """)
        remaining = cursor.fetchall()
        
        if remaining:
            print(f"⚠️  WARNING: {len(remaining)} player(s) still have numeric loaned_by values!")
            for p in remaining:
                print(f"  - {p['player_name']} (ID {p['id']}): loaned_by='{p['loaned_by']}'")
        else:
            print("✅ All players now have proper club names in loaned_by field")
        
    except Exception as e:
        print(f"❌ Error fixing loaned_by values: {e}")
        manager.conn.rollback()

def estimate_contract_renewal(manager: TeamManager):
    """Estimate contract renewal demands for a specific player"""
    try:
        from contract_renewal import ContractRenewalManager
        
        print("\n" + "="*80)
        print("💰 CONTRACT RENEWAL ESTIMATION")
        print("="*80)
        
        # Get player ID from user
        player_id_input = input("\nEnter Player ID (or 'cancel' to go back): ").strip()
        
        if player_id_input.lower() == 'cancel':
            print("❌ Operation cancelled")
            return
        
        try:
            player_id = int(player_id_input)
        except ValueError:
            print("❌ Invalid player ID. Please enter a number.")
            return
        
        # Get player data from database
        cursor = manager.conn.cursor()
        cursor.execute("""
            SELECT p.*, t.club_name
            FROM players p
            LEFT JOIN teams t ON p.club_id = t.id
            WHERE p.id = ?
        """, (player_id,))
        
        player = cursor.fetchone()
        
        if not player:
            print(f"❌ Player with ID {player_id} not found")
            return
        
        player_data = dict(player)
        
        # Display player info
        print(f"\n{'='*80}")
        print(f"📋 PLAYER INFORMATION")
        print(f"{'='*80}")
        print(f"Name:              {player_data['player_name']}")
        print(f"Age:               {player_data['age']} years old")
        print(f"Overall:           {player_data['overall']}")
        print(f"Position:          {get_position_name(player_data['registered_position'])}")
        print(f"Current Club:      {player_data['club_name'] if player_data['club_name'] else 'Free Agent'}")
        print(f"Current Salary:    €{player_data['salary']:,}/year")
        print(f"Market Value:      €{player_data['market_value']:,}")
        print(f"Contract Remaining: {player_data['contract_years_remaining']} year(s)")
        
        # Calculate renewal terms
        print(f"\n{'='*80}")
        print(f"💼 CALCULATING CONTRACT RENEWAL DEMANDS...")
        print(f"{'='*80}")
        
        renewal_manager = ContractRenewalManager(manager.db_path)
        renewal_manager.connect()
        
        # Calculate for both CPU and User scenarios
        cpu_terms = renewal_manager.calculate_new_contract_terms(player_data, is_cpu=True)
        user_terms = renewal_manager.calculate_new_contract_terms(player_data, is_cpu=False)
        
        renewal_manager.disconnect()
        
        # Display CPU terms
        print(f"\n🤖 IF PLAYING FOR CPU TEAM:")
        print(f"{'─'*80}")
        print(f"Contract Length:    {cpu_terms['contract_years']} year(s)")
        print(f"Salary Demand:      €{cpu_terms['salary_demand']:,}/year")
        print(f"Yearly Wage Rise:   {cpu_terms['yearly_wage_rise']*100:.1f}%")
        print(f"Signing Bonus:      €{cpu_terms['signing_bonus']:,}")
        print(f"")
        print(f"Total Cost (Year 1): €{cpu_terms['salary_demand'] + cpu_terms['signing_bonus']:,}")
        
        # Calculate total contract value for CPU
        cpu_total_value = cpu_terms['signing_bonus']
        current_salary = cpu_terms['salary_demand']
        for year in range(cpu_terms['contract_years']):
            cpu_total_value += current_salary
            current_salary = int(current_salary * (1 + cpu_terms['yearly_wage_rise']))
        
        print(f"Total Contract Value: €{cpu_total_value:,} over {cpu_terms['contract_years']} year(s)")
        
        # Display User terms
        print(f"\n👤 IF PLAYING FOR USER TEAM:")
        print(f"{'─'*80}")
        print(f"Contract Length:    {user_terms['contract_years']} year(s)")
        print(f"Salary Demand:      €{user_terms['salary_demand']:,}/year")
        print(f"Yearly Wage Rise:   {user_terms['yearly_wage_rise']*100:.1f}%")
        print(f"Signing Bonus:      €{user_terms['signing_bonus']:,}")
        print(f"")
        print(f"Total Cost (Year 1): €{user_terms['salary_demand'] + user_terms['signing_bonus']:,}")
        
        # Calculate total contract value for User
        user_total_value = user_terms['signing_bonus']
        current_salary = user_terms['salary_demand']
        for year in range(user_terms['contract_years']):
            user_total_value += current_salary
            current_salary = int(current_salary * (1 + user_terms['yearly_wage_rise']))
        
        print(f"Total Contract Value: €{user_total_value:,} over {user_terms['contract_years']} year(s)")
        
        # Comparison
        salary_diff = user_terms['salary_demand'] - cpu_terms['salary_demand']
        salary_diff_pct = ((user_terms['salary_demand'] / cpu_terms['salary_demand']) - 1) * 100 if cpu_terms['salary_demand'] > 0 else 0
        
        print(f"\n{'='*80}")
        print(f"📊 COMPARISON")
        print(f"{'='*80}")
        print(f"Current Salary:     €{player_data['salary']:,}/year")
        print(f"CPU Demand:         €{cpu_terms['salary_demand']:,}/year")
        print(f"User Demand:        €{user_terms['salary_demand']:,}/year")
        print(f"Difference:         €{salary_diff:,}/year ({salary_diff_pct:+.1f}%)")
        print(f"")
        print(f"💡 User teams typically pay {salary_diff_pct:.0f}% more than CPU teams")
        
        # Year-by-year breakdown
        print(f"\n{'='*80}")
        print(f"📅 YEAR-BY-YEAR SALARY PROJECTION (User Team)")
        print(f"{'='*80}")
        current_salary = user_terms['salary_demand']
        for year in range(1, user_terms['contract_years'] + 1):
            print(f"Year {year}: €{current_salary:,}/year")
            current_salary = int(current_salary * (1 + user_terms['yearly_wage_rise']))
        
        print(f"\n{'='*80}")
        
    except ImportError:
        print("❌ Error: contract_renewal module not found")
    except Exception as e:
        print(f"❌ Error estimating contract renewal: {e}")
        import traceback
        traceback.print_exc()

def get_position_name(position_code: int) -> str:
    """Convert position code to readable name"""
    positions = {
        0: "Goalkeeper (GK)",
        2: "Centre Back (CB)",
        3: "Defensive Midfielder (DMF)",
        4: "Full Back (FB)",
        5: "Centre Midfielder (CMF)",
        6: "Side Midfielder (SMF)",
        7: "Attacking Midfielder (AMF)",
        8: "Side Midfielder (SMF)",
        9: "Wing Forward (WF)",
        10: "Centre Forward (CF)",
        11: "Second Striker (SS)",
        12: "Centre Forward (CF)"
    }
    return positions.get(position_code, f"Unknown ({position_code})")

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
    print("18. Fix invalid face/skin combinations")
    print("19. Create secondary market team (CSV-invisible)")
    print("20. List/Delete secondary teams")
    print("21. Retire player and generate regen (random nationality)")
    print("22. Add seed goalkeepers from original.sqlite")
    print("23. Estimate contract renewal demands (by Player ID)")
    print("24. Populate CPU team stances based on division position")
    print("25. Populate AMF player stats (games, goals, assists) for CPU teams")
    print("26. Analyze CPU team selling/loaning thresholds")
    print("27. Recalculate market values for CPU team players only")
    print("28. Fix loaned_by values (convert numeric IDs to club names)")
    print("29. Clear player historical statistics")
    print("30. Match international stats (copy lifetime to current season)")
    print("31. Exit")
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
        cursor.execute("SELECT id, player_name, games_played, goals, assists, MVP FROM players WHERE club_id = ?", (team_id,))
        players = cursor.fetchall()
        
        if not players:
            print(f"❌ No players found on team '{team_name}'")
            return
        
        print(f"\n📊 Found {len(players)} players on team '{team_name}':")
        print("-" * 80)
        print(f"{'ID':<6} {'Name':<25} {'Games':<6} {'Goals':<6} {'Assists':<8} {'MVP':<6}")
        print("-" * 90)
        
        for player in players:
            print(f"{player['id']:<6} {player['player_name']:<25} {player['games_played'] or 0:<6} {player['goals'] or 0:<6} {player['assists'] or 0:<8} {player['MVP'] or 0:<6}")
        
        # Confirm multiplication
        confirm = input(f"\n⚠️  Are you sure you want to multiply stats by 1.5 for all {len(players)} players on '{team_name}'? (y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ Operation cancelled")
            return
        
        # Perform multiplication (multiply by 1.5, rounded to integer)
        updated_count = 0
        for player in players:
            player_id = player['id']
            current_games = player['games_played'] or 0
            current_goals = player['goals'] or 0
            current_assists = player['assists'] or 0
            current_mvp = player['MVP'] or 0
            
            new_games = int(round(current_games * 1.5))
            new_goals = int(round(current_goals * 1.5))
            new_assists = int(round(current_assists * 1.5))
            new_mvp = int(round(current_mvp * 1.5))
            
            cursor.execute("""
                UPDATE players 
                SET games_played = ?, goals = ?, assists = ?, MVP = ? 
                WHERE id = ?
            """, (new_games, new_goals, new_assists, new_mvp, player_id))
            
            updated_count += 1
            print(f"   ✅ {player['player_name']}: Games {current_games}→{new_games}, Goals {current_goals}→{new_goals}, Assists {current_assists}→{new_assists}, MVP {current_mvp}→{new_mvp}")
        
        manager.conn.commit()
        
        print(f"\n🎉 Successfully multiplied stats by 1.5 for {updated_count} players on team '{team_name}'!")
        
    except Exception as e:
        print(f"❌ Error duplicating player stats: {e}")
        if manager.conn:
            manager.conn.rollback()

def fix_face_skin_combinations(manager: TeamManager):
    """Fix invalid face/skin combinations in the database"""
    print("\n🎭 FIX INVALID FACE/SKIN COMBINATIONS")
    print("-" * 40)
    print("This will check all players and fix any preset_face_number values")
    print("that are not valid for their skin_color based on original.sqlite data.")
    print()
    
    manager.fix_invalid_face_skin_combinations()

def create_secondary_team(manager: TeamManager):
    """Create a secondary market team (invisible in CSV exports)"""
    print("\n🏪 CREATE SECONDARY MARKET TEAM")
    print("-" * 40)
    print("Secondary teams operate like normal teams but their players appear as")
    print("'No Club' in CSV exports. This keeps the market active without affecting")
    print("the downloadable CSV format for PES6.")
    print()
    
    team_name = input("Enter team name (e.g., 'Market Team 1', 'Transfer Pool A'): ").strip()
    if not team_name:
        print("❌ Team name cannot be empty")
        return
    
    budget_input = input("Enter team budget (default: 400,000,000): ").strip()
    if budget_input.isdigit():
        budget = int(budget_input)
    else:
        budget = 400000000
    
    # Confirm creation
    print(f"\n📋 Creating secondary team:")
    print(f"   Name: {team_name}")
    print(f"   Budget: €{budget:,}")
    print(f"   CSV Visible: NO")
    print(f"   Owner: CPU")
    confirm = input(f"\nCreate this secondary team? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Team creation cancelled")
        return
    
    manager.create_secondary_market_team(team_name, budget)

def list_delete_secondary_teams(manager: TeamManager):
    """List and optionally delete secondary teams"""
    manager.list_and_delete_secondary_teams()

def retire_player_with_random_regen(manager: TeamManager):
    """Retire a player and generate a regen with random nationality"""
    print("\n👴 RETIRE PLAYER & GENERATE REGEN")
    print("-" * 40)
    print("This will retire the selected player and generate a new regen")
    print("with random nationality to replace them.")
    print()
    
    try:
        # Get player ID
        player_id_input = input("Enter player ID to retire: ").strip()
        if not player_id_input:
            print("❌ Player ID is required")
            return
        
        try:
            player_id = int(player_id_input)
        except ValueError:
            print("❌ Player ID must be a number")
            return
        
        # Check if player exists
        cursor = manager.conn.cursor()
        cursor.execute("SELECT player_name, age, registered_position, club_id FROM players WHERE id = ?", (player_id,))
        player_info = cursor.fetchone()
        
        if not player_info:
            print(f"❌ Player ID {player_id} not found in database")
            return
        
        player_name, age, position, club_id = player_info
        print(f"\n📊 Player found:")
        print(f"   Name: {player_name}")
        print(f"   ID: {player_id}")
        print(f"   Age: {age}")
        print(f"   Position: {position}")
        
        # Confirm retirement
        confirm = input(f"\n⚠️  Are you sure you want to retire {player_name} (ID: {player_id})? (y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ Operation cancelled")
            return
        
        # Perform retirement
        success = manager.retire_player_with_random_regen(player_id)
        
        if success:
            print(f"\n🎉 Player retirement completed successfully!")
        else:
            print(f"\n❌ Player retirement failed!")
            
    except Exception as e:
        print(f"❌ Error in retire_player_with_random_regen: {e}")

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

def add_seed_goalkeepers(manager: TeamManager):
    """
    Add seed_player values to goalkeepers in the current database
    from elite goalkeepers in original.sqlite.
    
    Only assigns seeds to:
    - Goalkeepers with registered_position = 0
    - That don't already have a seed_player value
    - That have a DIFFERENT name than the original.sqlite player with the same ID
      (i.e., only regens/replacements get seeds, not original players)
    
    Seeds come from original.sqlite goalkeepers with:
    - registered_position = 0
    - goal_keeping > 82
    """
    if not manager.conn:
        print("❌ Not connected to database")
        return
    
    try:
        cursor = manager.conn.cursor()
        
        # Connect to original.sqlite to check names and get elite goalkeepers
        original_db_path = 'original.sqlite'
        if not os.path.exists(original_db_path):
            print(f"❌ Error: {original_db_path} not found")
            return
        
        original_conn = sqlite3.connect(original_db_path)
        original_conn.row_factory = sqlite3.Row
        original_cursor = original_conn.cursor()
        
        # Get all players from original.sqlite for name comparison
        original_cursor.execute("""
            SELECT id, player_name
            FROM players
        """)
        original_players = {row['id']: row['player_name'] for row in original_cursor.fetchall()}
        
        # Get goalkeepers without seeds from current database
        cursor.execute("""
            SELECT id, player_name, goal_keeping, overall
            FROM players
            WHERE registered_position = 0 
            AND (seed_player IS NULL OR seed_player = 0)
            ORDER BY goal_keeping DESC
        """)
        keepers_without_seeds = cursor.fetchall()
        
        if not keepers_without_seeds:
            print("✅ All goalkeepers already have seed_player values!")
            original_conn.close()
            return
        
        print(f"\n🧤 Found {len(keepers_without_seeds)} goalkeepers without seed_player values")
        
        # Filter out goalkeepers whose names match the original database
        # Only keep those with name mismatches (regens/replacements)
        eligible_keepers = []
        excluded_keepers = []
        
        for keeper in keepers_without_seeds:
            keeper_id = keeper['id']
            keeper_name = keeper['player_name']
            
            # Check if this ID exists in original.sqlite
            if keeper_id in original_players:
                original_name = original_players[keeper_id]
                
                # If names match, exclude this keeper (it's an original player)
                if keeper_name == original_name:
                    excluded_keepers.append(keeper)
                    continue
            
            # Name mismatch or ID doesn't exist in original - eligible for seed
            eligible_keepers.append(keeper)
        
        print(f"   ✅ Eligible for seeds (name mismatch): {len(eligible_keepers)}")
        print(f"   ❌ Excluded (same name as original): {len(excluded_keepers)}")
        
        if excluded_keepers:
            print(f"\n📋 Sample excluded goalkeepers (original players):")
            for i, keeper in enumerate(excluded_keepers[:5]):
                print(f"   {i+1}. ID {keeper['id']}: {keeper['player_name']:<25} (GK: {keeper['goal_keeping']}, OVR: {keeper['overall']})")
        
        if not eligible_keepers:
            print("\n✅ No eligible goalkeepers found (all are original players)")
            original_conn.close()
            return
        
        print(f"\n   Fetching elite goalkeepers from original.sqlite...")
        
        # Get elite goalkeepers from original database
        original_cursor.execute("""
            SELECT id, player_name, goal_keeping, overall
            FROM players
            WHERE registered_position = 0 
            AND goal_keeping > 82
            ORDER BY goal_keeping DESC
        """)
        elite_keepers = original_cursor.fetchall()
        original_conn.close()
        
        if not elite_keepers:
            print("❌ No elite goalkeepers found in original.sqlite (goal_keeping > 82)")
            return
        
        print(f"   Found {len(elite_keepers)} elite goalkeepers in original.sqlite")
        print(f"\n📊 Sample elite goalkeepers:")
        for i, keeper in enumerate(elite_keepers[:5]):
            print(f"   {i+1}. {keeper['player_name']:<25} GK: {keeper['goal_keeping']}, OVR: {keeper['overall']}")
        
        print(f"\n📋 Sample eligible goalkeepers (will receive seeds):")
        for i, keeper in enumerate(eligible_keepers[:5]):
            print(f"   {i+1}. ID {keeper['id']}: {keeper['player_name']:<25} (GK: {keeper['goal_keeping']}, OVR: {keeper['overall']})")
        
        # Confirm before proceeding
        print(f"\n⚠️  This will assign seed_player values to {len(eligible_keepers)} goalkeepers")
        print(f"   (Excluding {len(excluded_keepers)} original players with matching names)")
        confirm = input("   Continue? (y/N): ").strip().lower()
        
        if confirm != 'y':
            print("❌ Operation cancelled")
            return
        
        # Assign seeds randomly from elite keepers
        updated_count = 0
        for keeper in eligible_keepers:
            # Randomly select an elite keeper as seed
            seed_keeper = random.choice(elite_keepers)
            
            cursor.execute("""
                UPDATE players
                SET seed_player = ?
                WHERE id = ?
            """, (seed_keeper['id'], keeper['id']))
            
            updated_count += 1
            
            if updated_count % 50 == 0:
                print(f"   ⏳ Processed {updated_count}/{len(eligible_keepers)} goalkeepers...")
        
        manager.conn.commit()
        
        print(f"\n✅ Successfully assigned seed_player to {updated_count} goalkeepers!")
        print(f"   Seeds were randomly selected from {len(elite_keepers)} elite goalkeepers")
        print(f"   (goal_keeping > 82 from original.sqlite)")
        print(f"   Excluded {len(excluded_keepers)} original players (same name in both databases)")
        
        # Show some examples
        cursor.execute("""
            SELECT p.id, p.player_name, p.goal_keeping, p.overall, p.seed_player
            FROM players p
            WHERE p.registered_position = 0 
            AND p.seed_player IS NOT NULL
            AND p.seed_player > 0
            ORDER BY RANDOM()
            LIMIT 5
        """)
        examples = cursor.fetchall()
        
        if examples:
            print(f"\n📋 Sample assignments:")
            for ex in examples:
                seed_info = f"Seed: {ex['seed_player']}" if ex['seed_player'] else "No seed"
                print(f"   ID {ex['id']}: {ex['player_name']:<25} (GK: {ex['goal_keeping']}, OVR: {ex['overall']}) -> {seed_info}")
        
    except Exception as e:
        print(f"❌ Error adding seed goalkeepers: {e}")
        manager.conn.rollback()

def populate_cpu_team_stances(manager: TeamManager):
    """
    Populate CPU team stances based on their position in division standings.
    
    Stance distribution:
    - Top 25%: Powerdog
    - Next 25%: Contender
    - Next 25%: Tinkering
    - Bottom 25%: Rebuilder
    
    Only assigns stances to CPU teams (user_id = 1 or NULL in league_teams).
    
    Option to randomly assign stances to all CPU teams instead of based on position.
    """
    if not manager.conn:
        print("❌ Not connected to database")
        return False
    
    try:
        cursor = manager.conn.cursor()
        
        print("\n" + "="*80)
        print("🏆 POPULATING CPU TEAM STANCES")
        print("="*80)
        print("Choose assignment method:")
        print("  1. Based on division position (Top 25% = Powerdog, etc.)")
        print("  2. Random assignment to all CPU teams")
        print()
        
        choice = input("Enter choice (1 or 2, default: 1): ").strip()
        if not choice:
            choice = '1'
        
        if choice == '2':
            # Random assignment mode
            return _randomly_assign_stances(manager, cursor)
        else:
            # Division-based assignment mode
            return _division_based_assign_stances(manager, cursor)
    
    except Exception as e:
        print(f"❌ Error populating CPU team stances: {e}")
        import traceback
        traceback.print_exc()
        if manager.conn:
            manager.conn.rollback()
        return False

def _randomly_assign_stances(manager: TeamManager, cursor) -> bool:
    """Randomly assign stances to all CPU teams"""
    print("\n🎲 RANDOM STANCE ASSIGNMENT MODE")
    print("="*80)
    print("Randomly assigning stances to all CPU teams:")
    print("  • Powerdog")
    print("  • Contender")
    print("  • Tinkering")
    print("  • Rebuilder")
    print()
    
    # Get all CPU teams
    cursor.execute("""
        SELECT t.id, t.club_name
        FROM teams t
        LEFT JOIN league_teams lt ON t.club_name = lt.team_name
        WHERE (lt.user_id = 1 OR lt.user_id IS NULL)
        AND t.id != 141  -- Exclude "No Club"
        ORDER BY t.club_name
    """)
    
    cpu_teams = cursor.fetchall()
    
    if not cpu_teams:
        print("❌ No CPU teams found")
        return False
    
    print(f"📊 Found {len(cpu_teams)} CPU team(s)")
    
    # Stance options
    stances = ['Powerdog', 'Contender', 'Tinkering', 'Rebuilder']
    
    # Counters
    stance_counts = {'Powerdog': 0, 'Contender': 0, 'Tinkering': 0, 'Rebuilder': 0}
    
    # Randomly assign stances
    updated_count = 0
    for team in cpu_teams:
        team_id = team['id']
        team_name = team['club_name']
        
        # Randomly select a stance
        stance = random.choice(stances)
        stance_counts[stance] += 1
        
        # Update team stance
        cursor.execute("""
            UPDATE teams
            SET stance = ?
            WHERE id = ?
        """, (stance, team_id))
        
        updated_count += 1
        
        if updated_count <= 10 or updated_count >= len(cpu_teams) - 9:  # Show first 10 and last 10
            print(f"   {team_name:<30} → {stance}")
    
    if updated_count > 20:
        print(f"   ... ({updated_count - 20} more teams)")
    
    # Commit changes
    manager.conn.commit()
    
    # Print summary
    print("\n" + "="*80)
    print("✅ RANDOM STANCE ASSIGNMENT COMPLETE")
    print("="*80)
    print(f"📊 Total CPU teams updated: {updated_count}")
    print()
    print("📈 Stance Distribution:")
    print("-" * 40)
    for stance in stances:
        count = stance_counts[stance]
        percentage = (count / updated_count * 100) if updated_count > 0 else 0
        print(f"  {stance:<15}: {count:>3} teams ({percentage:>5.1f}%)")
    
    return True

def _division_based_assign_stances(manager: TeamManager, cursor) -> bool:
    """Assign stances based on division position"""
    print("\n📊 DIVISION-BASED STANCE ASSIGNMENT MODE")
    print("="*80)
    print("Assigning stances based on division position:")
    print("  • Top 25%: Powerdog")
    print("  • Next 25%: Contender")
    print("  • Next 25%: Tinkering")
    print("  • Bottom 25%: Rebuilder")
    print()
    
    # Get all CPU League divisions (exclude Colados League)
    cursor.execute("""
        SELECT d.id, d.name, d.league_id, l.name as league_name
        FROM divisions d
        LEFT JOIN leagues l ON d.league_id = l.id
        WHERE l.name != 'Colados League' OR l.name IS NULL
        ORDER BY d.id
    """)
    divisions = cursor.fetchall()
    
    if not divisions:
        print("❌ No CPU League divisions found in database")
        return False
    
    print(f"📊 Found {len(divisions)} CPU League division(s)")
    
    total_updated = 0
    division_summaries = []
    
    for division in divisions:
        division_id = division['id']
        division_name = division['name']
        league_name = division['league_name'] if division['league_name'] else 'Unknown League'
        
        print(f"\n📋 Processing Division: {division_name} (ID: {division_id}) - {league_name}")
        print("-" * 80)
        
        # Get standings for this division
        # Use division_standings if available, otherwise calculate from league_games
        cursor.execute("""
            SELECT ds.team_id, ds.team_name, ds.points, ds.goal_difference, ds.goals_for
            FROM division_standings ds
            WHERE ds.division_id = ?
            ORDER BY ds.points DESC, ds.goal_difference DESC, ds.goals_for DESC
        """, (division_id,))
        
        standings = cursor.fetchall()
        
        # If no standings in division_standings, calculate from league_games
        if not standings:
            print("   ⚠️  No standings found in division_standings, calculating from league_games...")
            
            # Get all teams in this division
            cursor.execute("""
                SELECT dt.team_id, t.club_name as team_name
                FROM division_teams dt
                JOIN teams t ON dt.team_id = t.id
                WHERE dt.division_id = ? AND dt.is_active = 1
            """, (division_id,))
            
            teams = cursor.fetchall()
            
            # Calculate standings from games
            standings = []
            for team in teams:
                team_id = team['team_id']
                team_name = team['team_name']
                
                cursor.execute("""
                    SELECT 
                        COUNT(*) as games_played,
                        SUM(CASE WHEN (home_team_id = ? AND home_score > away_score) OR 
                                     (away_team_id = ? AND away_score > home_score) THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN home_score = away_score THEN 1 ELSE 0 END) as draws,
                        SUM(CASE WHEN (home_team_id = ? AND home_score < away_score) OR 
                                     (away_team_id = ? AND away_score < home_score) THEN 1 ELSE 0 END) as losses,
                        SUM(CASE WHEN home_team_id = ? THEN home_score ELSE away_score END) as goals_for,
                        SUM(CASE WHEN home_team_id = ? THEN away_score ELSE home_score END) as goals_against
                    FROM league_games
                    WHERE (home_team_id = ? OR away_team_id = ?) AND is_played = 1 AND division_id = ?
                """, (team_id, team_id, team_id, team_id, team_id, team_id, team_id, team_id, division_id))
                
                stats = cursor.fetchone()
                games_played = stats['games_played'] or 0
                wins = stats['wins'] or 0
                draws = stats['draws'] or 0
                goals_for = stats['goals_for'] or 0
                goals_against = stats['goals_against'] or 0
                goal_difference = goals_for - goals_against
                points = wins * 3 + draws
                
                standings.append({
                    'team_id': team_id,
                    'team_name': team_name,
                    'points': points,
                    'goal_difference': goal_difference,
                    'goals_for': goals_for
                })
            
            # Sort standings
            standings.sort(key=lambda x: (x['points'], x['goal_difference'], x['goals_for']), reverse=True)
        
        if not standings:
            print(f"   ⚠️  No teams found in division {division_name}")
            continue
        
        # Filter to only CPU teams
        cpu_standings = []
        for standing in standings:
            team_id = standing['team_id'] if isinstance(standing, dict) else standing[0]
            
            # Check if team is CPU (user_id = 1 or NULL)
            cursor.execute("""
                SELECT lt.user_id
                FROM league_teams lt
                JOIN teams t ON lt.team_name = t.club_name
                WHERE t.id = ?
            """, (team_id,))
            
            team_owner = cursor.fetchone()
            if team_owner and team_owner['user_id'] in (1, None):
                # It's a CPU team
                if isinstance(standing, dict):
                    cpu_standings.append(standing)
                else:
                    # Convert Row to dict
                    cpu_standings.append({
                        'team_id': standing[0],
                        'team_name': standing[1],
                        'points': standing[2],
                        'goal_difference': standing[3],
                        'goals_for': standing[4]
                    })
        
        if not cpu_standings:
            print(f"   ℹ️  No CPU teams found in division {division_name}")
            continue
        
        total_teams = len(cpu_standings)
        print(f"   📊 Found {total_teams} CPU team(s) in division")
        
        # Calculate quartile boundaries
        q1_boundary = max(1, int(total_teams * 0.25))  # Top 25%
        q2_boundary = max(1, int(total_teams * 0.50))  # Top 50%
        q3_boundary = max(1, int(total_teams * 0.75))  # Top 75%
        
        # Assign stances based on position
        powerdog_count = 0
        contender_count = 0
        tinkering_count = 0
        rebuilder_count = 0
        
        for position, standing in enumerate(cpu_standings, 1):
            team_id = standing['team_id']
            team_name = standing['team_name']
            points = standing['points']
            
            # Determine stance based on quartile
            if position <= q1_boundary:
                stance = 'Powerdog'
                powerdog_count += 1
            elif position <= q2_boundary:
                stance = 'Contender'
                contender_count += 1
            elif position <= q3_boundary:
                stance = 'Tinkering'
                tinkering_count += 1
            else:
                stance = 'Rebuilder'
                rebuilder_count += 1
            
            # Update team stance
            cursor.execute("""
                UPDATE teams
                SET stance = ?
                WHERE id = ?
            """, (stance, team_id))
            
            if position <= 5 or position >= total_teams - 4:  # Show first 5 and last 4
                print(f"   {position:>2}. {team_name:<30} {points:>3} pts → {stance}")
        
        division_summaries.append({
            'division_name': division_name,
            'total_teams': total_teams,
            'powerdog': powerdog_count,
            'contender': contender_count,
            'tinkering': tinkering_count,
            'rebuilder': rebuilder_count
        })
        
        total_updated += total_teams
        
        print(f"   ✅ Updated {total_teams} teams:")
        print(f"      Powerdog: {powerdog_count}, Contender: {contender_count}, Tinkering: {tinkering_count}, Rebuilder: {rebuilder_count}")
    
    # Commit all changes
    manager.conn.commit()
    
    # Print summary
    print("\n" + "="*80)
    print("✅ STANCE POPULATION COMPLETE")
    print("="*80)
    print(f"📊 Total CPU teams updated: {total_updated}")
    print(f"📋 Divisions processed: {len(division_summaries)}")
    print()
    print("📈 Summary by Division:")
    print("-" * 80)
    print(f"{'Division':<30} {'Total':<6} {'Powerdog':<8} {'Contender':<9} {'Tinkering':<9} {'Rebuilder':<9}")
    print("-" * 80)
    
    total_powerdog = 0
    total_contender = 0
    total_tinkering = 0
    total_rebuilder = 0
    
    for summary in division_summaries:
        print(f"{summary['division_name']:<30} {summary['total_teams']:<6} "
              f"{summary['powerdog']:<8} {summary['contender']:<9} "
              f"{summary['tinkering']:<9} {summary['rebuilder']:<9}")
        total_powerdog += summary['powerdog']
        total_contender += summary['contender']
        total_tinkering += summary['tinkering']
        total_rebuilder += summary['rebuilder']
    
    print("-" * 80)
    print(f"{'TOTAL':<30} {total_updated:<6} "
          f"{total_powerdog:<8} {total_contender:<9} "
          f"{total_tinkering:<9} {total_rebuilder:<9}")
    
    return True

def populate_amf_player_stats(manager: TeamManager):
    """
    Populate games_played, goals, and assists for AMF players (registered_position = '9')
    on CPU teams only.
    
    Stats distribution:
    - Games: 1-11 (better overall = more games)
    - Goals: 0-5 (better overall = more goals)
    - Assists: 0-5 (better overall = more assists)
    
    Only affects CPU teams (user_id = 1 or NULL in league_teams).
    """
    if not manager.conn:
        print("❌ Not connected to database")
        return False
    
    try:
        cursor = manager.conn.cursor()
        
        print("\n" + "="*80)
        print("⚽ POPULATE AMF PLAYER STATS FOR CPU TEAMS")
        print("="*80)
        print("This will update games_played, goals, and assists for AMF players")
        print("(registered_position = '9') on CPU teams only.")
        print()
        print("Stats ranges:")
        print("  • Games: 1-11 (better overall = more games)")
        print("  • Goals: 0-5 (better overall = more goals)")
        print("  • Assists: 0-5 (better overall = more assists)")
        print()
        
        # Get all AMF players from CPU teams
        cursor.execute("""
            SELECT p.id, p.player_name, p.overall, p.games_played, p.goals, p.assists, t.club_name
            FROM players p
            JOIN teams t ON p.club_id = t.id
            LEFT JOIN league_teams lt ON t.club_name = lt.team_name
            WHERE p.registered_position = '9'
            AND (lt.user_id = 1 OR lt.user_id IS NULL)
            AND t.id != 141  -- Exclude "No Club"
            ORDER BY p.overall DESC
        """)
        
        amf_players = cursor.fetchall()
        
        if not amf_players:
            print("❌ No AMF players found on CPU teams")
            return False
        
        print(f"📊 Found {len(amf_players)} AMF player(s) on CPU teams")
        print()
        print("Sample players (top 10 by overall):")
        print("-" * 80)
        print(f"{'Name':<25} {'Overall':<8} {'Current Games':<12} {'Current Goals':<12} {'Current Assists':<12}")
        print("-" * 80)
        
        for i, player in enumerate(amf_players[:10]):
            games = player['games_played'] or 0
            goals = player['goals'] or 0
            assists = player['assists'] or 0
            print(f"{player['player_name']:<25} {player['overall'] or 0:<8} {games:<12} {goals:<12} {assists:<12}")
        
        if len(amf_players) > 10:
            print(f"   ... and {len(amf_players) - 10} more players")
        
        # Confirm update
        print()
        confirm = input(f"⚠️  Update stats for all {len(amf_players)} AMF players? (y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ Operation cancelled")
            return False
        
        # Calculate stats based on overall
        # Sort by overall (already sorted, but ensure it)
        sorted_players = sorted(amf_players, key=lambda p: p['overall'] or 0, reverse=True)
        
        updated_count = 0
        
        for i, player in enumerate(sorted_players):
            player_id = player['id']
            player_name = player['player_name']
            overall = player['overall'] or 0
            
            # Calculate position in sorted list (0.0 to 1.0)
            position_ratio = i / len(sorted_players) if len(sorted_players) > 1 else 0.5
            
            # Better players (lower position_ratio) get more games/goals/assists
            # Games: 1-11 (best players get 11, worst get 1)
            games = max(1, int(11 - (position_ratio * 10)))
            
            # Goals: 0-5 (best players get 5, worst get 0)
            # Use a more aggressive curve for goals (better players score more)
            goals_chance = 1.0 - (position_ratio ** 1.5)  # More aggressive curve
            goals = max(0, min(5, int(goals_chance * 5.5)))  # 0-5 range
            
            # Assists: 0-5 (best players get 5, worst get 0)
            # Similar curve for assists
            assists_chance = 1.0 - (position_ratio ** 1.5)
            assists = max(0, min(5, int(assists_chance * 5.5)))  # 0-5 range
            
            # Add some randomness (±1) to make it more realistic
            import random
            games = max(1, min(11, games + random.randint(-1, 1)))
            goals = max(0, min(4, goals + random.randint(-1, 1)))
            assists = max(0, min(3, assists + random.randint(-1, 1)))
            
            # Update player stats
            cursor.execute("""
                UPDATE players
                SET games_played = ?, goals = ?, assists = ?
                WHERE id = ?
            """, (games, goals, assists, player_id))
            
            updated_count += 1
            
            # Show first 10 and last 10 updates
            if updated_count <= 10 or updated_count >= len(sorted_players) - 9:
                old_games = player['games_played'] or 0
                old_goals = player['goals'] or 0
                old_assists = player['assists'] or 0
                print(f"   ✅ {player_name:<25} (OVR: {overall:>3}): Games {old_games:>2}→{games:>2}, Goals {old_goals:>2}→{goals:>2}, Assists {old_assists:>2}→{assists:>2}")
        
        if updated_count > 20:
            print(f"   ... ({updated_count - 20} more players updated)")
        
        # Commit changes
        manager.conn.commit()
        
        # Print summary
        print("\n" + "="*80)
        print("✅ AMF PLAYER STATS POPULATION COMPLETE")
        print("="*80)
        print(f"📊 Total AMF players updated: {updated_count}")
        
        # Show stats distribution
        cursor.execute("""
            SELECT 
                AVG(games_played) as avg_games,
                AVG(goals) as avg_goals,
                AVG(assists) as avg_assists,
                MAX(games_played) as max_games,
                MAX(goals) as max_goals,
                MAX(assists) as max_assists,
                MIN(games_played) as min_games,
                MIN(goals) as min_goals,
                MIN(assists) as min_assists
            FROM players p
            JOIN teams t ON p.club_id = t.id
            LEFT JOIN league_teams lt ON t.club_name = lt.team_name
            WHERE p.registered_position = '9'
            AND (lt.user_id = 1 OR lt.user_id IS NULL)
            AND t.id != 141
        """)
        
        stats_summary = cursor.fetchone()
        
        if stats_summary:
            print()
            print("📈 Stats Summary:")
            print("-" * 80)
            print(f"  Games:   Avg {stats_summary['avg_games']:.1f}, Range {stats_summary['min_games']}-{stats_summary['max_games']}")
            print(f"  Goals:   Avg {stats_summary['avg_goals']:.1f}, Range {stats_summary['min_goals']}-{stats_summary['max_goals']}")
            print(f"  Assists: Avg {stats_summary['avg_assists']:.1f}, Range {stats_summary['min_assists']}-{stats_summary['max_assists']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error populating AMF player stats: {e}")
        import traceback
        traceback.print_exc()
        if manager.conn:
            manager.conn.rollback()
        return False

def recalculate_cpu_team_market_values(manager: TeamManager):
    """
    Recalculate market values for players on CPU teams only.
    
    This routine:
    - Only affects players on CPU teams (user_id = 1 or NULL in league_teams)
    - Excludes players on user teams
    - Excludes No Club players (club_id = 141)
    - Uses the same calculation logic as the main recalculate function
    - Salaries remain unchanged
    """
    if not manager.conn:
        print("❌ Not connected to database")
        return False
    
    try:
        # Import game mechanics functions
        try:
            from game_mechanics import calculate_player_market_value_only
        except ImportError:
            print("❌ Could not import calculate_player_market_value_only from game_mechanics.py")
            return False
        
        cursor = manager.conn.cursor()
        
        print("\n" + "="*80)
        print("💰 RECALCULATE CPU TEAM MARKET VALUES")
        print("="*80)
        print("This will recalculate market values for players on CPU teams only.")
        print("Players on user teams and No Club will NOT be affected.")
        print()
        
        # Get all players on CPU teams (excluding No Club)
        cursor.execute("""
            SELECT p.*, t.club_name
            FROM players p
            JOIN teams t ON p.club_id = t.id
            LEFT JOIN league_teams lt ON t.club_name = lt.team_name
            WHERE p.club_id != 141  -- Exclude No Club
            AND (lt.user_id = 1 OR lt.user_id IS NULL)  -- Only CPU teams
            ORDER BY p.overall DESC
        """)
        
        cpu_players = cursor.fetchall()
        
        if not cpu_players:
            print("❌ No players found on CPU teams (excluding No Club)")
            return False
        
        # Get column names
        columns = [description[0] for description in cursor.description]
        
        print(f"📊 Found {len(cpu_players)} player(s) on CPU teams")
        print()
        print("Sample players (top 10 by overall):")
        print("-" * 80)
        print(f"{'Name':<25} {'Team':<25} {'Current MV':<15} {'Overall':<8}")
        print("-" * 80)
        
        for i, player_row in enumerate(cpu_players[:10]):
            player_data = dict(zip(columns, player_row))
            current_mv = player_data.get('market_value', 0) or 0
            overall = player_data.get('overall', 0) or 0
            print(f"{player_data['player_name']:<25} {player_data['club_name']:<25} €{current_mv:>12,} {overall:<8}")
        
        if len(cpu_players) > 10:
            print(f"   ... and {len(cpu_players) - 10} more players")
        
        # Confirm update
        print()
        confirm = input(f"⚠️  Recalculate market values for all {len(cpu_players)} CPU team players? (y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ Operation cancelled")
            return False
        
        # Process each player
        updated_count = 0
        errors = 0
        position_top_players = {}  # Track top 5 players per position
        
        print()
        print("🔄 Recalculating market values...")
        
        for player_row in cpu_players:
            try:
                # Convert to dictionary
                player_data = dict(zip(columns, player_row))
                player_id = player_data['id']
                player_name = player_data['player_name']
                old_market_value = player_data.get('market_value', 0) or 0
                
                # Calculate new market value
                new_market_value = calculate_player_market_value_only(player_data)
                
                # Update only market value in database
                cursor.execute("""
                    UPDATE players 
                    SET market_value = ?
                    WHERE id = ?
                """, (new_market_value, player_id))
                
                # Track for top players by position
                position = player_data.get('registered_position', 'Unknown')
                position_str = str(position) if position is not None else 'Unknown'
                if position_str not in position_top_players:
                    position_top_players[position_str] = []
                
                position_top_players[position_str].append({
                    'name': player_name,
                    'market_value': new_market_value,
                    'club_name': player_data.get('club_name', 'Unknown')
                })
                
                updated_count += 1
                
                # Show first 10 and last 10 updates
                if updated_count <= 10 or updated_count >= len(cpu_players) - 9:
                    print(f"   ✅ {player_name:<25} (Team: {player_data['club_name']:<20}): €{old_market_value:>12,} → €{new_market_value:>12,}")
                
            except Exception as e:
                print(f"   ❌ Error updating player {player_data.get('id', 'unknown')} ({player_data.get('player_name', 'Unknown')}): {e}")
                errors += 1
                continue
        
        if updated_count > 20:
            print(f"   ... ({updated_count - 20} more players updated)")
        
        # Sort top players by position and get top 5
        top_players_by_position = {}
        for position, players_list in position_top_players.items():
            sorted_players = sorted(players_list, key=lambda x: x['market_value'], reverse=True)
            top_players_by_position[position] = sorted_players[:5]
        
        # Commit changes
        manager.conn.commit()
        
        # Print summary
        print("\n" + "="*80)
        print("✅ CPU TEAM MARKET VALUE RECALCULATION COMPLETE")
        print("="*80)
        print(f"📊 Total CPU team players updated: {updated_count}")
        print(f"❌ Errors: {errors}")
        print()
        
        # Show top players by position
        if top_players_by_position:
            print("🏆 Top 5 Most Valuable CPU Team Players by Position:")
            print("-" * 80)
            
            position_names = {
                '0': 'Goalkeeper', '2': 'Sweeper', '3': 'Centre-Back', '4': 'Side-Back',
                '5': 'Defensive Midfielder', '6': 'Wing-Back', '7': 'Central Midfielder',
                '8': 'Side Midfielder', '9': 'Attacking Midfielder', '10': 'Winger',
                '11': 'Shadow Striker', '12': 'Striker'
            }
            
            for position, players_list in sorted(top_players_by_position.items()):
                if players_list:
                    pos_name = position_names.get(position, f'Position {position}')
                    print(f"\n{pos_name}:")
                    for i, player in enumerate(players_list, 1):
                        print(f"  {i}. {player['name']:<25} ({player['club_name']:<20}): €{player['market_value']:>12,}")
        
        print()
        print("📈 Summary:")
        print("  • Market values recalculated based on current skills and age")
        print("  • Salaries remain unchanged")
        print("  • Only CPU team players were affected")
        print("  • User team players and No Club players were NOT affected")
        print()
        
        return True
        
    except Exception as e:
        print(f"❌ Error recalculating CPU team market values: {e}")
        import traceback
        traceback.print_exc()
        if manager.conn:
            manager.conn.rollback()
        return False

def analyze_cpu_team_selling_thresholds(manager: TeamManager):
    """
    Analyze CPU team selling and loaning thresholds.
    
    For each player on a selected CPU team, calculates:
    - Listing price on market bazaar
    - Threshold to sell in negotiate_with_cpu
    - Threshold to loan in negotiate_with_cpu
    """
    if not manager.conn:
        print("❌ Not connected to database")
        return False
    
    try:
        # Import CPUAI
        from cpu_ai import CPUAI
        import random
        
        cursor = manager.conn.cursor()
        
        print("\n" + "="*80)
        print("📊 CPU TEAM SELLING/LOANING THRESHOLDS ANALYZER")
        print("="*80)
        print("This tool analyzes what prices/thresholds the CPU would use for:")
        print("  • Market Bazaar listing price")
        print("  • Negotiate with CPU - Sell threshold")
        print("  • Negotiate with CPU - Loan threshold")
        print()
        
        # Get all CPU teams
        cursor.execute("""
            SELECT t.id, t.club_name, t.budget, t.stance
            FROM teams t
            LEFT JOIN league_teams lt ON t.club_name = lt.team_name
            WHERE (lt.user_id = 1 OR lt.user_id IS NULL)
            AND t.id != 141
            ORDER BY t.club_name
        """)
        
        cpu_teams = cursor.fetchall()
        
        if not cpu_teams:
            print("❌ No CPU teams found")
            return False
        
        # Display teams
        print("Available CPU Teams:")
        print("-" * 80)
        print(f"{'#':<4} {'Team Name':<30} {'Budget':<15} {'Stance':<15}")
        print("-" * 80)
        
        for i, team in enumerate(cpu_teams, 1):
            budget = team['budget'] or 0
            stance = team['stance'] or 'N/A'
            print(f"{i:<4} {team['club_name']:<30} €{budget:>12,} {stance:<15}")
        
        print()
        team_choice = input("Enter team number to analyze (or 'q' to quit): ").strip()
        
        if team_choice.lower() == 'q':
            print("❌ Operation cancelled")
            return False
        
        try:
            team_index = int(team_choice) - 1
            if team_index < 0 or team_index >= len(cpu_teams):
                print("❌ Invalid team number")
                return False
        except ValueError:
            print("❌ Invalid input")
            return False
        
        selected_team = cpu_teams[team_index]
        team_id = selected_team['id']
        team_name = selected_team['club_name']
        team_stance = selected_team['stance'] or 'N/A'
        
        print(f"\n📊 Analyzing: {team_name} (Stance: {team_stance})")
        print("="*80)
        
        # Initialize CPUAI
        cpu_ai = CPUAI(manager.db_path)
        
        # Get team analysis
        analysis = cpu_ai.analyze_team_composition(team_id)
        if not analysis:
            print(f"❌ Could not analyze team {team_name}")
            return False
        
        budget = analysis['needs'].budget_available
        
        # Verify stance retrieval
        retrieved_stance = cpu_ai.get_team_stance(team_id)
        if retrieved_stance != team_stance and team_stance != 'N/A':
            print(f"⚠️  Warning: Stance mismatch. DB has '{team_stance}', CPUAI retrieved '{retrieved_stance}'")
        
        # Get all players from this team
        cursor.execute("""
            SELECT p.id, p.player_name, p.registered_position, p.overall, 
                   p.market_value, p.salary, p.contract_years_remaining, p.age
            FROM players p
            WHERE p.club_id = ?
            ORDER BY p.overall DESC, p.player_name
        """, (team_id,))
        
        players = cursor.fetchall()
        
        if not players:
            print(f"❌ No players found for {team_name}")
            return False
        
        print(f"Found {len(players)} player(s)")
        print()
        print("Calculating thresholds for each player...")
        print()
        
        # Get team stance
        stance = cpu_ai.get_team_stance(team_id)
        
        # Determine protection rules based on stance
        players_per_position_to_protect = 2 if stance == 'Powerdog' else 1
        
        # Get protected players per position
        protected_players_by_position = {}
        cursor.execute("""
            SELECT registered_position, MAX(overall) as best_overall
            FROM players
            WHERE club_id = ?
            GROUP BY registered_position
        """, (team_id,))
        
        position_bests = cursor.fetchall()
        for pos_data in position_bests:
            position = pos_data['registered_position']
            best_overall = pos_data['best_overall']
            
            # Get top N players in this position
            cursor.execute("""
                SELECT id, overall FROM players 
                WHERE club_id = ? AND registered_position = ? 
                ORDER BY overall DESC
                LIMIT ?
            """, (team_id, position, players_per_position_to_protect))
            
            protected_players_by_position[position] = [row['id'] for row in cursor.fetchall()]
        
        # Get position counts for surplus check
        cursor.execute("""
            SELECT registered_position, COUNT(*) as count
            FROM players
            WHERE club_id = ?
            GROUP BY registered_position
        """, (team_id,))
        
        position_counts = {row['registered_position']: row['count'] for row in cursor.fetchall()}
        
        # Calculate position groups
        gk_count = position_counts.get('0', 0)
        def_count = position_counts.get('2', 0) + position_counts.get('3', 0)
        fb_count = position_counts.get('4', 0) + position_counts.get('6', 0)
        mid_count = position_counts.get('5', 0) + position_counts.get('7', 0) + position_counts.get('9', 0)
        wing_count = position_counts.get('8', 0) + position_counts.get('10', 0)
        fwd_count = position_counts.get('11', 0) + position_counts.get('12', 0)
        
        # Determine positions with surplus
        positions_with_surplus = set()
        if gk_count > cpu_ai.ideal_composition.goalkeepers:
            positions_with_surplus.add('0')
        if def_count > cpu_ai.ideal_composition.defenders:
            positions_with_surplus.update(['2', '3'])
        if fb_count > cpu_ai.ideal_composition.fullbacks:
            positions_with_surplus.update(['4', '6'])
        if mid_count > cpu_ai.ideal_composition.midfielders:
            positions_with_surplus.update(['5', '7', '9'])
        if wing_count > cpu_ai.ideal_composition.wingers:
            positions_with_surplus.update(['8', '10'])
        if fwd_count > cpu_ai.ideal_composition.forwards:
            positions_with_surplus.update(['11', '12'])
        
        # Calculate thresholds for each player
        results = []
        
        for player in players:
            player_id = player['id']
            player_name = player['player_name']
            position = str(player['registered_position'])
            overall = player['overall'] or 0
            market_value = player['market_value'] or 1000000
            salary = player['salary'] or 0
            contract_years = player['contract_years_remaining'] or 1
            age = player['age'] or 25
            
            # Convert player to dict for CPUAI methods
            player_dict = dict(player)
            
            # Calculate fair salary and check if toxic (needed for listable check)
            fair_salary = cpu_ai.calculate_fair_salary(player_dict)
            is_toxic = salary > fair_salary * 1.5
            
            # Check if player would be listable (considering protection)
            is_protected = player_id in protected_players_by_position.get(position, [])
            rebuilder_override = (stance == 'Rebuilder' and age > 27)
            is_listable = False
            listable_reason = ""
            
            # Check if position has surplus
            position_has_surplus = position in positions_with_surplus
            
            # Check if player would be listable
            if is_protected and not rebuilder_override:
                # Protected and not Rebuilder >27 override
                is_listable = False
                listable_reason = "PROTECTED"
            elif position == '0' and gk_count <= 2 and budget >= 0:
                # Goalkeeper protection (always keep at least 2)
                is_listable = False
                listable_reason = "GK PROTECTED"
            elif not position_has_surplus and budget >= 0 and not rebuilder_override:
                # No surplus in position and not in debt/Rebuilder override
                is_listable = False
                listable_reason = "NO SURPLUS"
            else:
                # Would be listable
                is_listable = True
                if rebuilder_override:
                    listable_reason = "REBUILDER >27"
                elif budget < 0:
                    listable_reason = "DEBT"
                elif is_toxic:
                    listable_reason = "TOXIC CONTRACT"
                else:
                    listable_reason = "SURPLUS"
            
            # 1. Calculate listing price (from list_cpu_player_for_sale logic)
            # Note: Listing price uses random, so we'll show the range
            
            if stance == 'Rebuilder' and age > 27:
                # Rebuilder: Players >27 years old sell for 70-90% of market value
                listing_price_min = int(market_value * 0.70)
                listing_price_max = int(market_value * 0.90)
                listing_price = int(market_value * random.uniform(0.70, 0.90))
                listing_price_display = f"€{listing_price:,} (range: €{listing_price_min:,}-€{listing_price_max:,})"
            elif stance in ['Contender', 'Tinkering']:
                # Contender/Tinkering: Normal price + 30% bump
                if is_toxic or budget < 0:
                    base_min = int(market_value * 0.8)
                    base_max = int(market_value * 0.95)
                    listing_price_min = int(base_min * 1.30)
                    listing_price_max = int(base_max * 1.30)
                    listing_price = int(market_value * random.uniform(0.8, 0.95) * 1.30)
                else:
                    base_min = int(market_value * 0.95)
                    base_max = int(market_value * 1.35)
                    listing_price_min = int(base_min * 1.30)
                    listing_price_max = int(base_max * 1.30)
                    listing_price = int(market_value * random.uniform(0.95, 1.35) * 1.30)
                listing_price_display = f"€{listing_price:,} (range: €{listing_price_min:,}-€{listing_price_max:,})"
            elif is_toxic or budget < 0:
                # Sell below market value for toxic contracts or debt
                listing_price_min = int(market_value * 0.8)
                listing_price_max = int(market_value * 0.95)
                listing_price = int(market_value * random.uniform(0.8, 0.95))
                listing_price_display = f"€{listing_price:,} (range: €{listing_price_min:,}-€{listing_price_max:,})"
            else:
                # Normal asking price
                listing_price_min = int(market_value * 0.95)
                listing_price_max = int(market_value * 1.35)
                listing_price = int(market_value * random.uniform(0.95, 1.35))
                listing_price_display = f"€{listing_price:,} (range: €{listing_price_min:,}-€{listing_price_max:,})"
            
            # Mark if not listable
            if not is_listable:
                listing_price_display = f"NOT LISTABLE ({listable_reason})"
            
            # 2. Calculate sell threshold (from process_user_offers logic)
            base_min = market_value
            adjusted_min = base_min
            
            # Age adjustment
            age_bonus = 0
            if age < 25:
                if age <= 20:
                    age_bonus = market_value * 0.3
                elif age <= 22:
                    age_bonus = market_value * 0.2
                else:
                    age_bonus = market_value * 0.1
            elif age > 30:
                if age > 35:
                    age_penalty = market_value * 0.2
                else:
                    age_penalty = market_value * 0.1
                adjusted_min -= age_penalty
            
            adjusted_min += age_bonus
            
            # Contract adjustment
            salary_difference = salary - fair_salary
            total_overpayment = salary_difference * contract_years
            
            if salary_difference > 0:
                # Overpaid player - reduce minimum
                contract_penalty = min(total_overpayment * 0.1, market_value * 0.2)
                adjusted_min -= contract_penalty
                
                if total_overpayment > market_value * 3:
                    compensation_required = min(total_overpayment * 0.1, market_value * 0.2)
                    adjusted_min = -compensation_required
            else:
                # Underpaid player - increase minimum
                contract_bonus = abs(total_overpayment) * 0.2
                adjusted_min += contract_bonus
            
            # Player quality relative to team's best in position
            cursor.execute("""
                SELECT MAX(overall) as best_overall
                FROM players
                WHERE club_id = ? AND registered_position = ?
            """, (team_id, position))
            
            best_result = cursor.fetchone()
            current_best_overall = best_result['best_overall'] if best_result and best_result['best_overall'] else 0
            
            if current_best_overall > 0:
                if current_best_overall == overall:
                    # Player IS the best - demand premium
                    adjusted_min *= 1.3
                elif current_best_overall > overall + 5:
                    # CPU has significantly better player
                    premium_multiplier = 1.2 + (current_best_overall - overall - 5) * 0.05
                    adjusted_min *= premium_multiplier
                elif current_best_overall > overall:
                    # CPU has better player
                    premium_multiplier = 1.1 + (current_best_overall - overall) * 0.02
                    adjusted_min *= premium_multiplier
                elif current_best_overall >= overall - 3:
                    # Close in quality - no adjustment
                    pass
                else:
                    # CPU player is worse - discount
                    discount_multiplier = 0.95 + (overall - current_best_overall - 3) * 0.01
                    adjusted_min *= discount_multiplier
            
            sell_threshold = int(adjusted_min)
            
            # Powerdog: Boost sell threshold by 30% for protected players
            if stance == 'Powerdog' and is_protected:
                sell_threshold = int(sell_threshold * 1.30)
            
            # 3. Calculate loan threshold (from process_loan_proposals logic - STANCE-BASED VERSION)
            # Get team stance
            stance = cpu_ai.get_team_stance(team_id)
            
            # Convert position to int for comparison (same as CPU AI)
            position_int = int(position) if position.isdigit() else -1
            
            # Get position stats
            cursor.execute("""
                SELECT MAX(overall) as best_overall, AVG(overall) as avg_overall, COUNT(*) as position_count
                FROM players
                WHERE club_id = ? AND registered_position = ?
            """, (team_id, position))
            
            position_stats = cursor.fetchone()
            best_in_position = position_stats['best_overall'] if position_stats and position_stats['best_overall'] else 0
            avg_in_position = position_stats['avg_overall'] if position_stats and position_stats['avg_overall'] else 0
            position_count = position_stats['position_count'] if position_stats else 0
            
            # Determine player importance (same logic as actual CPU AI)
            is_key_player = False
            is_useful_player = False
            
            if overall >= 85:
                is_key_player = True
            elif overall >= 80:
                is_key_player = True
            elif best_in_position > 0 and overall >= best_in_position - 2:
                is_key_player = True
            elif avg_in_position > 0 and overall >= avg_in_position + 5:
                is_useful_player = True
            elif overall >= 75:
                is_useful_player = True
            
            # Check if player is surplus (not key/useful)
            is_surplus_player = not is_key_player and not is_useful_player
            
            # STANCE-BASED LOAN ACCEPTANCE CRITERIA
            if stance in ['Powerdog', 'Contender']:
                # Powerdog/Contender: Key/useful players essentially unavailable
                if is_key_player or is_useful_player:
                    # Key/useful players: 100% wage + 100% of market value as fee (essentially impossible)
                    required_wage_coverage = 1.0  # 100%
                    required_loan_fee = market_value  # 100% of market value
                    loan_threshold_note = f"100% wage + €{required_loan_fee:,} (100% MV) - Essentially unavailable"
                else:
                    # Surplus players: Easy to loan (0-10% wage + €500k fee, both required)
                    required_wage_coverage = 0.0  # Minimum 0%, but can be up to 10%
                    required_loan_fee = 500000  # €500k fee (required)
                    loan_threshold_note = f"0-10% wage + €{required_loan_fee:,}"
            
            elif stance in ['Tinkering', 'Rebuilder']:
                # Tinkering/Rebuilder: More willing to loan
                if age > 27:
                    # Players over 27: 50% wage + 10% of market value as fee
                    required_wage_coverage = 0.50  # 50%
                    required_loan_fee = int(market_value * 0.10)  # 10% of market value
                    loan_threshold_note = f"{required_wage_coverage*100:.0f}% wage + €{required_loan_fee:,} (10% MV)"
                elif is_surplus_player:
                    # Surplus players: 50% wage, no fee
                    required_wage_coverage = 0.50  # 50%
                    required_loan_fee = 0  # No fee
                    loan_threshold_note = f"{required_wage_coverage*100:.0f}% wage (no fee)"
                else:
                    # Key/useful players under 27: 50-90% wage + 15-35% of market value as fee
                    wage_min = 0.50
                    wage_max = 0.90
                    fee_min = int(market_value * 0.15)
                    fee_max = int(market_value * 0.35)
                    loan_threshold_note = f"{wage_min*100:.0f}-{wage_max*100:.0f}% wage + €{fee_min:,}-€{fee_max:,} (15-35% MV)"
            else:
                # Default stance (shouldn't happen, but fallback)
                if is_key_player:
                    required_wage_coverage = 0.90
                    required_loan_fee = 2000000
                    loan_threshold_note = f"{required_wage_coverage*100:.0f}% wage + €{required_loan_fee:,}"
                elif is_useful_player:
                    required_wage_coverage = 0.70
                    required_loan_fee = 500000
                    loan_threshold_note = f"{required_wage_coverage*100:.0f}% wage + €{required_loan_fee:,}"
                else:
                    required_wage_coverage = 0.50
                    required_loan_fee = 1000000
                    loan_threshold_note = f"{required_wage_coverage*100:.0f}% wage OR €{required_loan_fee:,} fee"
            
            results.append({
                'player_id': player_id,
                'player_name': player_name,
                'position': position,
                'overall': overall,
                'age': age,
                'market_value': market_value,
                'listing_price': listing_price if is_listable else 0,
                'listing_price_display': listing_price_display,
                'is_listable': is_listable,
                'listable_reason': listable_reason,
                'sell_threshold': sell_threshold,
                'loan_threshold': loan_threshold_note
            })
        
        # Display results
        print("\n" + "="*140)
        print(f"📊 THRESHOLDS FOR {team_name.upper()} (Stance: {stance})")
        print("="*140)
        print(f"{'Player Name':<25} {'Pos':<4} {'OVR':<4} {'Age':<4} {'MV':<12} {'Listing Price':<40} {'Sell Threshold':<15} {'Loan Threshold':<35}")
        print("-"*140)
        
        for result in results:
            print(f"{result['player_name']:<25} {result['position']:<4} {result['overall']:<4} {result['age']:<4} "
                  f"€{result['market_value']:>10,} {result['listing_price_display']:<40} "
                  f"€{result['sell_threshold']:>13,} {result['loan_threshold']:<35}")
        
        print("-"*140)
        print(f"Total players analyzed: {len(results)}")
        print()
        
        # Summary statistics
        avg_listing = sum(r['listing_price'] for r in results) / len(results) if results else 0
        avg_sell = sum(r['sell_threshold'] for r in results) / len(results) if results else 0
        
        print("Summary:")
        print(f"  Average Listing Price: €{avg_listing:,.0f}")
        print(f"  Average Sell Threshold: €{avg_sell:,.0f}")
        print()
        
        return True
        
    except Exception as e:
        print(f"❌ Error analyzing CPU team thresholds: {e}")
        import traceback
        traceback.print_exc()
        return False

def clear_player_history(manager: TeamManager, player_id: int) -> bool:
    """
    Clear all historical statistics for a player.
    
    This function clears:
    - Season history (player_season_history table)
    - Games, Goals, Assists, MVP (players table)
    - All International data (lifetime and current season)
    - Career earnings
    - Championships and cups won
    
    Args:
        manager: TeamManager instance
        player_id: ID of the player to clear history for
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not manager.conn:
        print("❌ Not connected to database")
        return False
    
    cursor = manager.conn.cursor()
    
    try:
        # First, verify the player exists
        cursor.execute("SELECT id, player_name FROM players WHERE id = ?", (player_id,))
        player = cursor.fetchone()
        
        if not player:
            print(f"❌ Player with ID {player_id} not found")
            return False
        
        player_name = player[1] if isinstance(player, tuple) else player['player_name']
        print(f"\n⚠️  WARNING: This will clear all historical statistics for player {player_id} ({player_name})")
        print("This includes:")
        print("  - Season history (player_season_history table)")
        print("  - Games, Goals, Assists, MVP")
        print("  - All International data (lifetime and current season)")
        print("  - Career earnings")
        print("  - Championships and cups won")
        
        confirmation = input("\nAre you sure you want to proceed? (yes/no): ").strip().lower()
        
        if confirmation != 'yes':
            print("❌ Operation cancelled")
            return False
        
        # Clear season history
        cursor.execute("DELETE FROM player_season_history WHERE player_id = ?", (player_id,))
        season_history_deleted = cursor.rowcount
        print(f"  ✅ Deleted {season_history_deleted} season history records")
        
        # Clear all player stats, international data, career earnings, and achievements
        cursor.execute("""
            UPDATE players 
            SET games_played = 0,
                goals = 0,
                assists = 0,
                MVP = 0,
                international_caps_total = 0,
                international_goals = 0,
                international_assists = 0,
                current_season_caps = 0,
                current_international_goals = 0,
                current_international_assists = 0,
                career_earnings = 0,
                championships_won = 0,
                cups_won = 0
            WHERE id = ?
        """, (player_id,))
        
        manager.conn.commit()
        
        print(f"  ✅ Cleared all statistics for player {player_id} ({player_name})")
        print(f"\n✅ Player history cleared successfully!")
        print(f"   - Season history records deleted: {season_history_deleted}")
        print(f"   - Games/Goals/Assists/MVP reset to 0")
        print(f"   - All International stats reset to 0")
        print(f"   - Career earnings reset to 0")
        print(f"   - Championships and cups won reset to 0")
        
        return True
        
    except Exception as e:
        manager.conn.rollback()
        print(f"❌ Error clearing player history: {e}")
        import traceback
        traceback.print_exc()
        return False

def clear_player_history_option(manager: TeamManager):
    """
    Wrapper function to prompt for player ID and clear their history.
    """
    try:
        player_id_input = input("\nEnter the player ID to clear history for (or 'cancel' to exit): ").strip()
        
        if player_id_input.lower() == 'cancel':
            print("❌ Operation cancelled")
            return
        
        try:
            player_id = int(player_id_input)
        except ValueError:
            print("❌ Invalid player ID. Please enter a number.")
            return
        
        clear_player_history(manager, player_id)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def match_international_stats(manager: TeamManager) -> bool:
    """
    Copy lifetime international statistics to current season variables for ALL players.
    
    This function copies for each player:
    - international_caps_total → current_season_caps
    - international_goals → current_international_goals
    - international_assists → current_international_assists
    
    Args:
        manager: TeamManager instance
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not manager.conn:
        print("❌ Not connected to database")
        return False
    
    cursor = manager.conn.cursor()
    
    try:
        # Get count of all players
        cursor.execute("SELECT COUNT(*) as total FROM players")
        total_players = cursor.fetchone()['total']
        
        print(f"\n📊 MATCH INTERNATIONAL STATS FOR ALL PLAYERS")
        print("="*80)
        print(f"This will copy lifetime international stats to current season stats")
        print(f"for ALL {total_players} players in the database.")
        print(f"\nFor each player, this will copy:")
        print(f"  - international_caps_total → current_season_caps")
        print(f"  - international_goals → current_international_goals")
        print(f"  - international_assists → current_international_assists")
        
        confirmation = input(f"\n⚠️  Are you sure you want to proceed? (yes/no): ").strip().lower()
        
        if confirmation != 'yes':
            print("❌ Operation cancelled")
            return False
        
        # Get all players with their stats
        cursor.execute("""
            SELECT id, player_name, 
                   international_caps_total, international_goals, international_assists,
                   current_season_caps, current_international_goals, current_international_assists
            FROM players
            ORDER BY id
        """)
        
        players = cursor.fetchall()
        
        if not players:
            print("❌ No players found in database")
            return False
        
        updated_count = 0
        skipped_count = 0
        sample_updates = []
        
        print(f"\n🔄 Processing {len(players)} players...")
        
        for player in players:
            player_id = player['id']
            player_name = player['player_name']
            lifetime_caps = player['international_caps_total'] or 0
            lifetime_goals = player['international_goals'] or 0
            lifetime_assists = player['international_assists'] or 0
            current_caps = player['current_season_caps'] or 0
            current_goals = player['current_international_goals'] or 0
            current_assists = player['current_international_assists'] or 0
            
            # Check if update is needed
            if (current_caps == lifetime_caps and 
                current_goals == lifetime_goals and 
                current_assists == lifetime_assists):
                skipped_count += 1
                continue
            
            # Update current season stats with lifetime stats
            cursor.execute("""
                UPDATE players 
                SET current_season_caps = ?,
                    current_international_goals = ?,
                    current_international_assists = ?
                WHERE id = ?
            """, (lifetime_caps, lifetime_goals, lifetime_assists, player_id))
            
            updated_count += 1
            
            # Store sample updates for display (first 10 and some with changes)
            if updated_count <= 10 or (updated_count <= 50 and (current_caps != lifetime_caps or current_goals != lifetime_goals or current_assists != lifetime_assists)):
                sample_updates.append({
                    'name': player_name,
                    'id': player_id,
                    'old_caps': current_caps,
                    'new_caps': lifetime_caps,
                    'old_goals': current_goals,
                    'new_goals': lifetime_goals,
                    'old_assists': current_assists,
                    'new_assists': lifetime_assists
                })
            
            # Progress indicator
            if updated_count % 500 == 0:
                print(f"   ⏳ Processed {updated_count} updates...")
        
        manager.conn.commit()
        
        # Print summary
        print(f"\n✅ International stats matched successfully!")
        print("="*80)
        print(f"📊 Summary:")
        print(f"   - Total players processed: {len(players)}")
        print(f"   - Players updated: {updated_count}")
        print(f"   - Players already matched (skipped): {skipped_count}")
        
        if sample_updates:
            print(f"\n📋 Sample updates (first {min(10, len(sample_updates))}):")
            print("-" * 100)
            print(f"{'Player Name':<25} {'ID':<6} {'Caps':<12} {'Goals':<12} {'Assists':<12}")
            print("-" * 100)
            
            for update in sample_updates[:10]:
                caps_change = f"{update['old_caps']}→{update['new_caps']}" if update['old_caps'] != update['new_caps'] else str(update['new_caps'])
                goals_change = f"{update['old_goals']}→{update['new_goals']}" if update['old_goals'] != update['new_goals'] else str(update['new_goals'])
                assists_change = f"{update['old_assists']}→{update['new_assists']}" if update['old_assists'] != update['new_assists'] else str(update['new_assists'])
                
                print(f"{update['name']:<25} {update['id']:<6} {caps_change:<12} {goals_change:<12} {assists_change:<12}")
            
            if len(sample_updates) > 10:
                print(f"   ... and {len(sample_updates) - 10} more sample updates")
        
        return True
        
    except Exception as e:
        manager.conn.rollback()
        print(f"❌ Error matching international stats: {e}")
        import traceback
        traceback.print_exc()
        return False

def match_international_stats_option(manager: TeamManager):
    """
    Wrapper function to match international stats for all players.
    """
    try:
        match_international_stats(manager)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def main():
    print("🏆 Team Management System")
    print("Direct database access for team ownership management")
    
    manager = TeamManager()
    
    if not manager.connect():
        print("❌ Failed to connect to database")
        return
    
    try:
        while True:
            display_menu()
            choice = input("\nEnter your choice (1-31): ").strip()
            
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
                fix_face_skin_combinations(manager)
            elif choice == '19':
                create_secondary_team(manager)
            elif choice == '20':
                list_delete_secondary_teams(manager)
            elif choice == '21':
                retire_player_with_random_regen(manager)
            elif choice == '22':
                add_seed_goalkeepers(manager)
            elif choice == '23':
                estimate_contract_renewal(manager)
            elif choice == '24':
                populate_cpu_team_stances(manager)
            elif choice == '25':
                populate_amf_player_stats(manager)
            elif choice == '26':
                analyze_cpu_team_selling_thresholds(manager)
            elif choice == '27':
                recalculate_cpu_team_market_values(manager)
            elif choice == '28':
                fix_loaned_by_values(manager)
            elif choice == '29':
                clear_player_history_option(manager)
            elif choice == '30':
                match_international_stats_option(manager)
            elif choice == '31':
                print("👋 Goodbye!")
                break
            else:
                print("❌ Invalid choice. Please enter 1-31.")
    
    except KeyboardInterrupt:
        print("\n👋 Exiting...")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        manager.disconnect()

if __name__ == "__main__":
    main()
