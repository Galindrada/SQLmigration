#!/usr/bin/env python3
"""
Contract Renewal System
Handles contract renewals for both CPU teams and user teams.
"""

import sqlite3
import random
import math
from typing import Dict, List, Tuple, Optional
import pandas as pd
from game_mechanics import (
    calculate_player_salary_base, 
    get_cached_position_averages,
    apply_random_salary_adjustment,
    GLOBAL_BASE_SALARY
)

class ContractRenewalManager:
    def __init__(self, db_path: str = 'pes6_league_db.sqlite'):
        self.db_path = db_path
        self.conn = None
    
    def connect(self):
        """Connect to the database"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
            return True
        except Exception as e:
            print(f"❌ Error connecting to database: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the database"""
        if self.conn:
            self.conn.close()
    
    def get_cpu_players_with_expired_contracts(self) -> List[Dict]:
        """Get all CPU team players with contract_years_remaining = 0"""
        if not self.conn:
            return []
        
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT p.*, t.club_name
            FROM players p
            JOIN teams t ON p.club_id = t.id
            LEFT JOIN league_teams lt ON t.club_name = lt.team_name
            WHERE p.contract_years_remaining <= 0 
              AND (lt.user_id IS NULL OR lt.user_id = 1)
              AND p.club_id != 141
            ORDER BY t.club_name, p.player_name
        """)
        
        players = cursor.fetchall()
        return [dict(player) for player in players]
    
    def get_user_players_with_expired_contracts(self, user_id: int) -> List[Dict]:
        """Get all user team players with contract_years_remaining = 0"""
        if not self.conn:
            return []
        
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT p.*, t.club_name, t.budget
            FROM players p
            JOIN teams t ON p.club_id = t.id
            JOIN league_teams lt ON t.club_name = lt.team_name
            WHERE p.contract_years_remaining = 0 
              AND lt.user_id = ?
              AND p.club_id != 141
            ORDER BY p.player_name
        """, (user_id,))
        
        players = cursor.fetchall()
        return [dict(player) for player in players]
    
    def calculate_new_contract_terms(self, player_data: Dict, is_cpu: bool = True) -> Dict:
        """Calculate new contract terms for a player"""
        try:
            # Convert to pandas Series for salary calculation
            player_row = pd.Series(player_data)
            
            # Get position averages
            pos_avg_df = get_cached_position_averages(self.db_path)
            
            # Define skill lists
            skills = ['attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
                     'response', 'agility', 'dribble_accuracy', 'dribble_speed',
                     'short_pass_accuracy', 'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed',
                     'shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy', 'swerve',
                     'heading', 'jump', 'technique', 'aggression', 'mentality', 'goal_keeping',
                     'team_work', 'consistency', 'condition_fitness']
            
            binaries = ['dribbling_skill', 'tactical_dribble', 'positioning', 'reaction', 'playmaking',
                       'passing', 'scoring', 'one_one_scoring', 'post_player', 'lines', 'middle_shooting',
                       'side', 'centre', 'penalties', 'one_touch_pass', 'outside', 'marking', 'sliding',
                       'covering', 'd_line_control', 'penalty_stopper', 'one_on_one_stopper', 'long_throw']
            
            # Calculate base salary
            # Position-specific skill boosts are now applied inside calculate_player_salary_base:
            # - Goalkeepers (0): Defense, Balance, Response, Agility, Goal Keeping get 1.5x boost
            # - Sweepers/Centre-backs (2, 3): Defense, Balance, Heading, Jump get 1.5x boost
            # This provides more accurate compensation based on key skills rather than a blanket multiplier
            base_salary = calculate_player_salary_base(player_row, pos_avg_df, skills, binaries)
            
            # Apply random salary adjustment (±20% variation, rounded to nearest 1000)
            # Use player ID as seed for deterministic results (same player always gets same adjustment)
            # This matches the fair salary calculation used elsewhere in the system
            random.seed(player_data.get('id', 1))
            fair_salary = apply_random_salary_adjustment(base_salary)
            
            # Calculate player's overall for negotiation difficulty
            from refresh_and_reimport import calculate_player_overall
            player_overall = calculate_player_overall(player_data)
            
            # Contract years based on player age (age-appropriate contracts)
            player_age = player_data.get('age', 25)
            random.seed(player_data.get('id', 1))  # Deterministic based on player ID
            
            if player_age <= 23:
                # Young players: 2-4 years (building careers)
                contract_years = random.randint(2, 4)
            elif player_age <= 29:
                # Mid-20s players: 4-5 years (prime years)
                contract_years = random.randint(4, 5)
            else:
                # 30+ players: 1-3 years (shorter contracts for older players)
                contract_years = random.randint(1, 3)
            
            # Yearly wage rise based on player age (1-25%, younger players want higher rises)
            if player_age <= 22:
                yearly_wage_rise = random.uniform(0.15, 0.25)  # 15-25% for very young players
            elif player_age <= 25:
                yearly_wage_rise = random.uniform(0.10, 0.20)  # 10-20% for young players
            elif player_age <= 28:
                yearly_wage_rise = random.uniform(0.05, 0.15)  # 5-15% for mid-age players
            else:
                yearly_wage_rise = random.uniform(0.01, 0.10)  # 1-10% for older players
            
            # Apply contract renewal variance (-2% to +15%) on top of fair salary
            # This is in addition to the ±20% variance already in fair_salary from apply_random_salary_adjustment
            contract_renewal_variance = random.uniform(-0.02, 0.15)
            salary_demand = fair_salary * (1 + contract_renewal_variance)
            
            if is_cpu:
                # CPU gets fair terms (fair salary + contract renewal variance)
                signing_bonus_percentage = random.uniform(0.10, 0.25)
            else:
                # User players can ask for more signing bonus
                signing_bonus_percentage = random.uniform(0.10, 0.50)
            
            random.seed()  # Reset random seed
            
            # Calculate signing bonus
            signing_bonus = int(salary_demand * signing_bonus_percentage)
            
            # Make signing bonus divisible by 1000
            signing_bonus = round(signing_bonus / 1000) * 1000
            
            return {
                'contract_years': contract_years,
                'salary_demand': int(salary_demand),
                'yearly_wage_rise': yearly_wage_rise,
                'signing_bonus': signing_bonus,
                'player_overall': player_overall,
                'base_salary': base_salary,
                'fair_salary': fair_salary
            }
            
        except Exception as e:
            print(f"Error calculating contract terms: {e}")
            # Fallback to simple calculation with age-appropriate contract years
            player_age = player_data.get('age', 25)
            
            if player_age <= 23:
                fallback_contract_years = random.randint(2, 4)
            elif player_age <= 29:
                fallback_contract_years = random.randint(4, 5)
            else:
                fallback_contract_years = random.randint(1, 3)
            
            return {
                'contract_years': fallback_contract_years,
                'salary_demand': player_data.get('salary', GLOBAL_BASE_SALARY),
                'yearly_wage_rise': 0.05,
                'signing_bonus': 1000000,
                'player_overall': 50,
                'base_salary': player_data.get('salary', GLOBAL_BASE_SALARY)
            }
    
    def process_cpu_contract_renewals(self) -> Dict:
        """Process contract renewals for all CPU teams"""
        if not self.conn:
            return {'success': False, 'error': 'Database not connected'}
        
        try:
            cursor = self.conn.cursor()
            
            # Get all CPU players with expired contracts
            expired_players = self.get_cpu_players_with_expired_contracts()
            
            if not expired_players:
                return {
                    'success': True,
                    'message': 'No CPU players with expired contracts found',
                    'renewed': 0,
                    'rejected': 0,
                    'free_agents': []
                }
            
            renewed_count = 0
            rejected_count = 0
            free_agents = []
            
            print(f"🔄 Processing {len(expired_players)} CPU players with expired contracts...")
            
            for player in expired_players:
                # 90% chance CPU can renew contract
                if random.random() < 0.90:
                    # Calculate new contract terms
                    contract_terms = self.calculate_new_contract_terms(player, is_cpu=True)
                    
                    # Update player contract
                    cursor.execute("""
                        UPDATE players 
                        SET contract_years_remaining = ?,
                            salary = ?,
                            yearly_wage_rise = ?
                        WHERE id = ?
                    """, (
                        contract_terms['contract_years'],
                        contract_terms['salary_demand'],
                        contract_terms['yearly_wage_rise'],
                        player['id']
                    ))
                    
                    renewed_count += 1
                    print(f"  ✅ Renewed {player['player_name']} ({player['club_name']}) - €{contract_terms['salary_demand']:,}/year")
                    
                else:
                    # Player rejects contract, goes to free agency
                    contract_terms = self.calculate_new_contract_terms(player, is_cpu=False)
                    
                    # Move player to free agency
                    cursor.execute("""
                        UPDATE players 
                        SET club_id = 141,
                            contract_years_remaining = ?,
                            salary = ?,
                            yearly_wage_rise = ?,
                            market_value = 0
                        WHERE id = ?
                    """, (
                        contract_terms['contract_years'],
                        contract_terms['salary_demand'],
                        contract_terms['yearly_wage_rise'],
                        player['id']
                    ))
                    
                    rejected_count += 1
                    free_agents.append({
                        'player_name': player['player_name'],
                        'club_name': player['club_name'],
                        'new_salary': contract_terms['salary_demand'],
                        'contract_years': contract_terms['contract_years']
                    })
                    print(f"  ❌ {player['player_name']} ({player['club_name']}) rejected contract - now free agent")
            
            # Create blog post if there were any renewals or rejections (before commit)
            if renewed_count > 0 or rejected_count > 0:
                renewal_data = {
                    'renewed': renewed_count,
                    'rejected': rejected_count,
                    'free_agents': free_agents
                }
                self.create_contract_renewal_blog_post(renewal_data)
            
            # Commit all changes together (player updates + blog post)
            self.conn.commit()
            
            return {
                'success': True,
                'message': f'Processed {len(expired_players)} CPU contract renewals',
                'renewed': renewed_count,
                'rejected': rejected_count,
                'free_agents': free_agents
            }
            
        except Exception as e:
            self.conn.rollback()
            return {'success': False, 'error': str(e)}
    
    def create_contract_renewal_blog_post(self, renewal_data: Dict) -> bool:
        """Create a blog post about contract renewals"""
        if not self.conn:
            return False
        
        try:
            cursor = self.conn.cursor()
            
            # Create blog post content
            content = f"<h3>🔄 CPU Contract Renewal Results</h3>\n"
            content += f"<p><strong>Renewed Contracts:</strong> {renewal_data['renewed']}</p>\n"
            content += f"<p><strong>Rejected Contracts:</strong> {renewal_data['rejected']}</p>\n"
            
            if renewal_data['free_agents']:
                content += f"<h4>📋 Players Entering Free Agency:</h4>\n"
                content += f"<ul>\n"
                for agent in renewal_data['free_agents']:
                    content += f"<li><strong>{agent['player_name']}</strong> (formerly {agent['club_name']}) - "
                    content += f"€{agent['new_salary']:,}/year, {agent['contract_years']} years</li>\n"
                content += f"</ul>\n"
            
            # Insert blog post (commit happens in parent function)
            cursor.execute("""
                INSERT INTO blog_posts (title, content, author_id, created_at)
                VALUES (?, ?, ?, datetime('now'))
            """, (
                f"CPU Contract Renewal Results - {renewal_data['renewed']} Renewed, {renewal_data['rejected']} Free Agents",
                content,
                1  # System user
            ))
            
            # Don't commit here - let parent function commit everything together
            return True
            
        except Exception as e:
            print(f"Error creating blog post: {e}")
            return False
    
    def sign_player_contract(self, player_id: int, user_id: int) -> Dict:
        """Sign player contract with their demands"""
        if not self.conn:
            return {'success': False, 'error': 'Database not connected'}
        
        try:
            cursor = self.conn.cursor()
            
            # Get player data
            cursor.execute("""
                SELECT p.*, t.club_name, t.budget
                FROM players p
                JOIN teams t ON p.club_id = t.id
                JOIN league_teams lt ON t.club_name = lt.team_name
                WHERE p.id = ? AND lt.user_id = ?
            """, (player_id, user_id))
            
            player_data = cursor.fetchone()
            if not player_data:
                return {'success': False, 'error': 'Player not found or not owned by user'}
            
            player_dict = dict(player_data)
            
            # Calculate player's contract demands (consistent for this player)
            contract_terms = self.calculate_new_contract_terms(player_dict, is_cpu=False)
            
            # Player's demands
            salary_demand = contract_terms['salary_demand']
            signing_bonus = contract_terms['signing_bonus']
            contract_years = contract_terms['contract_years']
            yearly_wage_rise = contract_terms['yearly_wage_rise']
            
            # Check if user has enough budget (allow negative budgets)
            total_cost = signing_bonus + (salary_demand * contract_years)
            # Always allow signing, even if it results in negative budget
            
            # Accept the contract
            cursor.execute("""
                    UPDATE players 
                    SET contract_years_remaining = ?,
                        salary = ?,
                        yearly_wage_rise = ?
                    WHERE id = ?
                """, (contract_years, salary_demand, yearly_wage_rise, player_id))
            
            # Use unified budget system (same as add_user_movement)
            # Get current budget from user_budgets table
            cursor.execute("SELECT budget FROM user_budgets WHERE user_id = ?", (user_id,))
            budget_result = cursor.fetchone()
            
            if budget_result:
                current_budget = budget_result[0]
            else:
                # Fallback: get from teams table if user_budgets doesn't exist
                cursor.execute("""
                    SELECT t.budget FROM teams t
                    JOIN league_teams lt ON t.club_name = lt.team_name
                    WHERE lt.user_id = ?
                """, (user_id,))
                team_result = cursor.fetchone()
                current_budget = team_result[0] if team_result else 450000000
                # Initialize user_budgets if it doesn't exist
                cursor.execute("""
                    INSERT INTO user_budgets (user_id, budget, updated_at)
                    VALUES (?, ?, datetime('now'))
                """, (user_id, current_budget))
            
            # Calculate new budget after signing bonus deduction
            new_budget = current_budget - signing_bonus
            
            # Update unified budget
            cursor.execute("""
                UPDATE user_budgets 
                SET budget = ?, updated_at = datetime('now')
                WHERE user_id = ?
            """, (new_budget, user_id))
            
            # Also update teams table budget for consistency (legacy)
            cursor.execute("""
                UPDATE teams 
                SET budget = budget - ?
                WHERE id = (
                    SELECT t.id FROM teams t
                    JOIN league_teams lt ON t.club_name = lt.team_name
                    WHERE lt.user_id = ?
                )
            """, (signing_bonus, user_id))
            
            # Record signing bonus transaction in finances with correct balance_after
            cursor.execute("""
                INSERT INTO user_movements (user_id, type, description, amount, balance_after)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, 'Signing Bonus', 
                  f"Signing bonus for {player_dict['player_name']} (Contract Renewal)", 
                  -signing_bonus, new_budget))
            
            # Commit database changes first
            self.conn.commit()
            
            # Create blog post for successful contract renewal (after commit to avoid lock)
            from app import post_transfer_news
            title = f"Contract Renewal: {player_dict['player_name']}"
            content = f"{player_dict['player_name']} has successfully renewed their contract! The player signed for €{salary_demand:,} per year for {contract_years} years with a {yearly_wage_rise*100:.1f}% yearly wage rise. Signing bonus: €{signing_bonus:,} ({(signing_bonus/salary_demand*100):.1f}% of annual salary)."
            post_transfer_news(title, content, user_id)
            
            return {
                'success': True,
                'accepted': True,
                'message': f'Contract signed! {player_dict["player_name"]} signed for €{salary_demand:,}/year, {contract_years} years, {yearly_wage_rise*100:.1f}% yearly rise',
                'cost': total_cost
            }
                
        except Exception as e:
            self.conn.rollback()
            return {'success': False, 'error': str(e)}
    
    def let_player_walk_away(self, player_id: int, user_id: int) -> Dict:
        """Let player walk away to free agency"""
        if not self.conn:
            return {'success': False, 'error': 'Database not connected'}
        
        try:
            cursor = self.conn.cursor()
            
            # Get player data
            cursor.execute("""
                SELECT p.*, t.club_name
                FROM players p
                JOIN teams t ON p.club_id = t.id
                JOIN league_teams lt ON t.club_name = lt.team_name
                WHERE p.id = ? AND lt.user_id = ?
            """, (player_id, user_id))
            
            player_data = cursor.fetchone()
            if not player_data:
                return {'success': False, 'error': 'Player not found or not owned by user'}
            
            player_dict = dict(player_data)
            
            # Calculate new contract terms for free agency
            contract_terms = self.calculate_new_contract_terms(player_dict, is_cpu=False)
            
            # Move player to free agency
            cursor.execute("""
                UPDATE players 
                SET club_id = 141,
                    contract_years_remaining = ?,
                    salary = ?,
                    yearly_wage_rise = ?,
                    market_value = 0
                WHERE id = ?
            """, (
                contract_terms['contract_years'],
                contract_terms['salary_demand'],
                contract_terms['yearly_wage_rise'],
                player_id
            ))
            
            # Commit database changes first
            self.conn.commit()
            
            # Create sensationalistic blog post for player walking away (after commit to avoid lock)
            from app import post_transfer_news
            title = f"🚨 SHOCKING: {player_dict['player_name']} WALKS AWAY! 🚨"
            content = f"BREAKING NEWS: {player_dict['player_name']} has SHOCKINGLY rejected contract renewal talks and walked away from the club! The player has become a free agent and is now demanding €{contract_terms['salary_demand']:,} per year for {contract_terms['contract_years']} years with a {contract_terms['yearly_wage_rise']*100:.1f}% yearly wage rise. This unexpected departure has left fans stunned and the club scrambling to find a replacement! 💥"
            post_transfer_news(title, content, user_id)
            
            return {
                'success': True,
                'message': f"{player_dict['player_name']} has become a free agent.",
                'walked_away': True
            }
            
        except Exception as e:
            self.conn.rollback()
            return {'success': False, 'error': str(e)}
    
    def handle_negotiation_walk_away(self, player_id: int, user_id: int) -> Dict:
        """Handle when user walks away from negotiation (closes modal)"""
        if not self.conn:
            return {'success': False, 'error': 'Database not connected'}
        
        try:
            cursor = self.conn.cursor()
            
            # Get player data
            cursor.execute("""
                SELECT p.*, t.club_name
                FROM players p
                JOIN teams t ON p.club_id = t.id
                JOIN league_teams lt ON t.club_name = lt.team_name
                WHERE p.id = ? AND lt.user_id = ?
            """, (player_id, user_id))
            
            player_data = cursor.fetchone()
            if not player_data:
                return {'success': False, 'error': 'Player not found or not owned by user'}
            
            player_dict = dict(player_data)
            
            # Calculate new contract terms for free agency
            contract_terms = self.calculate_new_contract_terms(player_dict, is_cpu=False)
            
            # Move player to free agency
            cursor.execute("""
                UPDATE players 
                SET club_id = 141,
                    contract_years_remaining = ?,
                    salary = ?,
                    yearly_wage_rise = ?,
                    market_value = 0
                WHERE id = ?
            """, (
                contract_terms['contract_years'],
                contract_terms['salary_demand'],
                contract_terms['yearly_wage_rise'],
                player_id
            ))
            
            self.conn.commit()
            
            return {
                'success': True,
                'message': f"{player_dict['player_name']} has become a free agent after you walked away from negotiations.",
                'walked_away': True
            }
            
        except Exception as e:
            self.conn.rollback()
            return {'success': False, 'error': str(e)}
    
    def reject_user_contract(self, player_id: int, user_id: int) -> Dict:
        """Handle player rejecting user contract and going to free agency"""
        if not self.conn:
            return {'success': False, 'error': 'Database not connected'}
        
        try:
            cursor = self.conn.cursor()
            
            # Get player data
            cursor.execute("""
                SELECT p.*, t.club_name
                FROM players p
                JOIN teams t ON p.club_id = t.id
                JOIN league_teams lt ON t.club_name = lt.team_name
                WHERE p.id = ? AND lt.user_id = ?
            """, (player_id, user_id))
            
            player_data = cursor.fetchone()
            if not player_data:
                return {'success': False, 'error': 'Player not found or not owned by user'}
            
            player_dict = dict(player_data)
            
            # Calculate new contract terms for free agency (with 15-30% increase)
            contract_terms = self.calculate_new_contract_terms(player_dict, is_cpu=False)
            
            # Move player to free agency
            cursor.execute("""
                UPDATE players 
                SET club_id = 141,
                    contract_years_remaining = ?,
                    salary = ?,
                    yearly_wage_rise = ?,
                    market_value = 0
                WHERE id = ?
            """, (
                contract_terms['contract_years'],
                contract_terms['salary_demand'],
                contract_terms['yearly_wage_rise'],
                player_id
            ))
            
            self.conn.commit()
            
            return {
                'success': True,
                'message': f'{player_dict["player_name"]} rejected the contract and entered free agency',
                'new_contract': {
                    'salary': contract_terms['salary_demand'],
                    'years': contract_terms['contract_years'],
                    'bonus': contract_terms['signing_bonus']
                }
            }
            
        except Exception as e:
            self.conn.rollback()
            return {'success': False, 'error': str(e)}

def main():
    """Test the contract renewal system"""
    manager = ContractRenewalManager()
    
    if not manager.connect():
        print("❌ Failed to connect to database")
        return
    
    try:
        # Test CPU contract renewals
        result = manager.process_cpu_contract_renewals()
        
        if result['success']:
            print(f"\n✅ {result['message']}")
            print(f"   Renewed: {result['renewed']}")
            print(f"   Rejected: {result['rejected']}")
            
            # Create blog post
            if manager.create_contract_renewal_blog_post(result):
                print("✅ Blog post created successfully")
            else:
                print("❌ Failed to create blog post")
        else:
            print(f"❌ Error: {result['error']}")
    
    finally:
        manager.disconnect()

if __name__ == "__main__":
    main()
