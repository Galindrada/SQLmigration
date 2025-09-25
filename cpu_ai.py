"""
CPU AI System for Intelligent Team Management

This module handles CPU team composition, budget management, and intelligent
decision-making for transfers, negotiations, and team building.
"""

import sqlite3
import random
import math
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

@dataclass
class TeamComposition:
    """Represents the ideal team composition for CPU teams"""
    goalkeepers: int = 2      # Position 0
    defenders: int = 4        # Positions 2, 3 (Sweeper, Centre-Back)
    fullbacks: int = 4        # Positions 4, 6 (Side-Back, Wing-Back)
    midfielders: int = 6      # Positions 5, 7, 9 (Defensive Mid, Center Mid, Attacking Mid)
    wingers: int = 4          # Positions 8, 10 (Side Midfielder, Winger)
    forwards: int = 4         # Positions 11, 12 (Shadow Striker, Striker)
    
    @property
    def total_minimum(self) -> int:
        return self.goalkeepers + self.defenders + self.fullbacks + self.midfielders + self.wingers + self.forwards
    
    @property
    def total_maximum(self) -> int:
        return 32  # Maximum team size

@dataclass
class TeamNeeds:
    """Represents what a team needs to improve"""
    needs_goalkeeper: bool = False
    needs_defender: bool = False
    needs_fullback: bool = False
    needs_midfielder: bool = False
    needs_winger: bool = False
    needs_forward: bool = False
    needs_improvement: bool = False
    budget_available: int = 0
    is_in_debt: bool = False

class CPUAI:
    """Main CPU AI class for intelligent team management"""
    
    def __init__(self, db_path: str = 'pes6_league_db.sqlite'):
        self.db_path = db_path
        self.ideal_composition = TeamComposition()
        
    def connect(self) -> bool:
        """Connect to the database"""
        try:
            self.conn = sqlite3.connect(self.db_path, timeout=30.0)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode=WAL")
            return True
        except Exception as e:
            print(f"Error connecting to database: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the database"""
        if hasattr(self, 'conn'):
            self.conn.close()
    
    def analyze_team_composition(self, team_id: int) -> Dict:
        """Analyze a team's current composition and needs"""
        if not self.connect():
            return {}
        
        try:
            cur = self.conn.cursor()
            
            # Get team info
            cur.execute("SELECT club_name, budget FROM teams WHERE id = ?", (team_id,))
            team_info = cur.fetchone()
            if not team_info:
                return {}
            
            # Get player count by position
            cur.execute("""
                SELECT registered_position, COUNT(*) as count
                FROM players 
                WHERE club_id = ?
                GROUP BY registered_position
            """, (team_id,))
            
            position_counts = {row['registered_position']: row['count'] for row in cur.fetchall()}
            
            # Analyze composition
            current_gk = position_counts.get(0, 0)
            current_def = position_counts.get(2, 0) + position_counts.get(3, 0)
            current_fb = position_counts.get(4, 0) + position_counts.get(6, 0)
            current_mid = position_counts.get(5, 0) + position_counts.get(7, 0) + position_counts.get(9, 0)
            current_wing = position_counts.get(8, 0) + position_counts.get(10, 0)
            current_fwd = position_counts.get(11, 0) + position_counts.get(12, 0)
            
            total_players = sum(position_counts.values())
            
            # Determine needs
            needs = TeamNeeds()
            needs.needs_goalkeeper = current_gk < self.ideal_composition.goalkeepers
            needs.needs_defender = current_def < self.ideal_composition.defenders
            needs.needs_fullback = current_fb < self.ideal_composition.fullbacks
            needs.needs_midfielder = current_mid < self.ideal_composition.midfielders
            needs.needs_winger = current_wing < self.ideal_composition.wingers
            needs.needs_forward = current_fwd < self.ideal_composition.forwards
            needs.needs_improvement = total_players < self.ideal_composition.total_minimum
            needs.budget_available = team_info['budget']
            needs.is_in_debt = team_info['budget'] < 0
            
            return {
                'team_id': team_id,
                'team_name': team_info['club_name'],
                'total_players': total_players,
                'position_counts': position_counts,
                'needs': needs,
                'composition': {
                    'goalkeepers': current_gk,
                    'defenders': current_def,
                    'fullbacks': current_fb,
                    'midfielders': current_mid,
                    'wingers': current_wing,
                    'forwards': current_fwd
                }
            }
            
        except Exception as e:
            print(f"Error analyzing team composition: {e}")
            return {}
        finally:
            self.disconnect()
    
    def get_team_position_needs(self, team_id: int) -> List[int]:
        """Get list of positions that a team needs to fill"""
        analysis = self.analyze_team_composition(team_id)
        if not analysis:
            return []
        
        needs = analysis['needs']
        needed_positions = []
        
        if needs.needs_goalkeeper:
            needed_positions.append(0)
        if needs.needs_defender:
            needed_positions.extend([2, 3])  # Sweeper, Centre-Back
        if needs.needs_fullback:
            needed_positions.extend([4, 6])  # Side-Back, Wing-Back
        if needs.needs_midfielder:
            needed_positions.extend([5, 7, 9])  # Defensive Mid, Center Mid, Attacking Mid
        if needs.needs_winger:
            needed_positions.extend([8, 10])  # Side Midfielder, Winger
        if needs.needs_forward:
            needed_positions.extend([11, 12])  # Shadow Striker, Striker
            
        return needed_positions
    
    def calculate_fair_salary(self, player_data: Dict) -> int:
        """Calculate what a player's salary should be based on their skills using game mechanics"""
        try:
            from game_mechanics import calculate_player_financials
            
            # Use the existing game mechanics function to calculate fair salary
            financials = calculate_player_financials(player_data, self.db_path)
            return financials['salary']
            
        except Exception as e:
            print(f"Error calculating fair salary using game mechanics: {e}")
            # Fallback to simplified calculation
            try:
                market_value = player_data.get('market_value', 1000000)
                overall = player_data.get('overall', 50)
                
                # Base salary calculation: market_value * 0.1 * (overall/100)
                base_salary = int(market_value * 0.1 * (overall / 100))
                
                # Ensure minimum and maximum salary bounds
                min_salary = 500000   # €500k minimum
                max_salary = 15000000 # €15M maximum
                
                return max(min_salary, min(base_salary, max_salary))
                
            except Exception as e2:
                print(f"Error in fallback salary calculation: {e2}")
                return player_data.get('salary', 1000000)  # Final fallback
    
    def is_toxic_contract(self, player_data: Dict) -> Tuple[bool, int]:
        """Check if a player's contract is toxic (overpaid)"""
        current_salary = player_data.get('salary', 0)
        fair_salary = self.calculate_fair_salary(player_data)
        
        # If current salary is more than 150% of fair salary, it's toxic
        toxic_threshold = fair_salary * 1.5
        is_toxic = current_salary > toxic_threshold
        
        overpayment = current_salary - fair_salary if is_toxic else 0
        
        return is_toxic, overpayment
    
    def get_interested_cpu_teams_for_player(self, player_data: Dict) -> List[Dict]:
        """Get CPU teams that would be interested in buying a specific player"""
        if not self.connect():
            return []
        
        try:
            cur = self.conn.cursor()
            
            player_position = player_data.get('registered_position', 0)
            player_overall = player_data.get('overall', 50)
            player_market_value = player_data.get('market_value', 1000000)
            
            # Get all CPU teams (excluding free agency and user teams)
            cur.execute("""
                SELECT t.id, t.club_name, t.budget
                FROM teams t
                WHERE t.id != 141 
                AND t.id IN (
                    SELECT DISTINCT lt.id FROM league_teams lt WHERE lt.user_id = 1
                )
            """)
            
            cpu_teams = cur.fetchall()
            interested_teams = []
            
            for team in cpu_teams:
                team_id = team['id']
                team_budget = team['budget']
                
                # Analyze team needs
                analysis = self.analyze_team_composition(team_id)
                if not analysis:
                    continue
                
                needs = analysis['needs']
                needed_positions = self.get_team_position_needs(team_id)
                
                # Check if team needs this position or player represents improvement
                position_match = player_position in needed_positions
                
                # Check if player would improve the team
                cur.execute("""
                    SELECT AVG(overall) as avg_overall
                    FROM players 
                    WHERE club_id = ? AND registered_position = ?
                """, (team_id, player_position))
                
                avg_overall_result = cur.fetchone()
                avg_overall = avg_overall_result['avg_overall'] if avg_overall_result['avg_overall'] else 50
                
                improvement = player_overall > avg_overall
                
                # Check if team can afford the player
                can_afford = team_budget >= player_market_value * 0.25  # At least 25% of market value
                
                # Check for toxic contract
                is_toxic, overpayment = self.is_toxic_contract(player_data)
                
                if (position_match or improvement) and (can_afford or is_toxic):
                    # Calculate offer range
                    if is_toxic:
                        # For toxic contracts, offer negative value
                        contract_years = player_data.get('contract_years_remaining', 1)
                        toxic_penalty = overpayment * contract_years
                        min_offer = max(-toxic_penalty, player_market_value * 0.1)
                        max_offer = player_market_value * 0.5
                    else:
                        # Normal offer range
                        min_offer = player_market_value * 0.25
                        max_offer = player_market_value * 0.75
                    
                    interested_teams.append({
                        'team_id': team_id,
                        'team_name': team['club_name'],
                        'budget': team_budget,
                        'position_match': position_match,
                        'improvement': improvement,
                        'is_toxic': is_toxic,
                        'overpayment': overpayment,
                        'min_offer': int(min_offer),
                        'max_offer': int(max_offer),
                        'reason': 'position_needed' if position_match else 'improvement'
                    })
            
            return interested_teams
            
        except Exception as e:
            print(f"Error getting interested CPU teams: {e}")
            return []
        finally:
            self.disconnect()
    
    def list_cpu_player_for_loan(self, team_id: int) -> Optional[Dict]:
        """List a CPU player for loan in the market bazaar"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            cur = conn.cursor()
            
            # Check if this team already has active loan listings
            cur.execute("""
                SELECT COUNT(*) as active_loans
                FROM market_bazaar_listings 
                WHERE team_id = ? AND status = 'active' AND listing_type = 'cpu_loan'
            """, (team_id,))
            active_loans = cur.fetchone()['active_loans']
            
            # Limit to 1 active loan listing per team
            if active_loans >= 1:
                return None
            
            # Get team analysis
            team_analysis = self.analyze_team_composition(team_id)
            if not team_analysis:
                return None
            
            # Find a player to loan (prefer younger players or surplus players)
            cur.execute("""
                SELECT p.*, t.club_name
                FROM players p
                JOIN teams t ON p.club_id = t.id
                WHERE p.club_id = ? 
                AND p.id NOT IN (
                    SELECT player_id FROM market_bazaar_listings WHERE status = 'active'
                )
                AND p.id NOT IN (
                    SELECT player_id FROM blacklist WHERE user_id = 1
                )
                AND p.age <= 25  -- Prefer younger players for loans
                ORDER BY p.age ASC, p.market_value DESC
                LIMIT 1
            """, (team_id,))
            
            player = cur.fetchone()
            if not player:
                return None
            
            # Loans are free (0€)
            loan_fee = 0
            
            # Create loan listing
            expires_at = datetime.now() + timedelta(days=7)
            cur.execute("""
                INSERT INTO market_bazaar_listings (player_id, team_id, asking_price, expires_at, status, listing_type)
                VALUES (?, ?, ?, ?, 'active', 'cpu_loan')
            """, (player['id'], team_id, loan_fee, expires_at.isoformat()))
            
            conn.commit()
            conn.close()
            
            return {
                'action': 'list_player_for_loan',
                'team': player['club_name'],
                'details': {
                    'player_name': player['player_name'],
                    'loan_fee': loan_fee,
                    'player_id': player['id']
                }
            }
            
        except Exception as e:
            print(f"Error listing CPU player for loan: {e}")
            return None

    def list_cpu_player_for_sale(self, team_id: int) -> Optional[Dict]:
        """List a CPU player for sale in the market bazaar"""
        try:
            # Use a fresh connection for each operation
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            cur = conn.cursor()
            
            # Check if this team already has active listings to prevent duplicates
            cur.execute("""
                SELECT COUNT(*) as active_listings
                FROM market_bazaar_listings 
                WHERE team_id = ? AND status = 'active' AND listing_type = 'cpu_sale'
            """, (team_id,))
            active_listings = cur.fetchone()['active_listings']
            
            # Limit to 2 active listings per team to prevent spam
            if active_listings >= 2:
                return None
            
            # Get team analysis
            analysis = self.analyze_team_composition(team_id)
            if not analysis:
                return None
            
            needs = analysis['needs']
            budget = analysis['needs'].budget_available
            
            # Find players to sell (overpaid, surplus, or if team needs money)
            # Exclude players already listed and blacklisted
            cur.execute("""
                SELECT p.*, p.market_value, p.salary
                FROM players p
                WHERE p.club_id = ?
                AND p.id NOT IN (
                    SELECT player_id FROM market_bazaar_listings 
                    WHERE status = 'active' AND listing_type = 'cpu_sale'
                )
                AND p.id NOT IN (
                    SELECT player_id FROM blacklist WHERE user_id = 1
                )
                ORDER BY p.salary DESC, p.overall ASC
                LIMIT 10
            """, (team_id,))
            
            team_players = cur.fetchall()
            
            if not team_players:
                return None
            
            # Select a player to sell (prefer overpaid or surplus players)
            selected_player = team_players[0]  # Highest salary, lowest overall
            
            # Calculate asking price
            market_value = selected_player['market_value']
            salary = selected_player['salary']
            
            # Check if contract is toxic (salary > 150% of fair value)
            fair_salary = self.calculate_fair_salary(dict(selected_player))
            is_toxic = salary > fair_salary * 1.5
            
            if is_toxic or budget < 0:
                # Sell below market value for toxic contracts or debt
                asking_price = int(market_value * random.uniform(0.6, 0.8))
            else:
                # Normal asking price
                asking_price = int(market_value * random.uniform(0.8, 1.2))
            
            # Create market listing
            from datetime import datetime, timedelta
            expires_at = datetime.now() + timedelta(days=random.randint(7, 14))  # 1-2 weeks
            
            cur.execute("""
                INSERT INTO market_bazaar_listings (player_id, team_id, asking_price, expires_at, status, listing_type)
                VALUES (?, ?, ?, ?, 'active', 'cpu_sale')
            """, (selected_player['id'], team_id, asking_price, expires_at.isoformat()))
            
            conn.commit()
            conn.close()
            
            return {
                'action': 'list_player_for_sale',
                'team': analysis['team_name'],
                'details': {
                    'player_name': selected_player['player_name'],
                    'asking_price': asking_price,
                    'player_id': selected_player['id']
                }
            }
            
        except Exception as e:
            print(f"Error listing CPU player for sale: {e}")
            try:
                conn.close()
            except:
                pass
            return None
    
    def make_cpu_loan_offer(self, team_id: int) -> Optional[Dict]:
        """CPU team loans a player from user loan listings"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            cur = conn.cursor()
            
            # Find user loan listings
            cur.execute("""
                SELECT mbl.*, p.player_name, p.market_value, t.club_name as seller_team_name
                FROM market_bazaar_listings mbl
                JOIN players p ON mbl.player_id = p.id
                JOIN teams t ON mbl.team_id = t.id
                WHERE mbl.status = 'active' 
                AND mbl.listing_type = 'user_loan'
                AND mbl.team_id IN (
                    SELECT DISTINCT lt.id FROM league_teams lt WHERE lt.user_id != 1
                )
                AND p.id NOT IN (
                    SELECT player_id FROM blacklist WHERE user_id = 1
                )
                ORDER BY p.market_value DESC
                LIMIT 5
            """)
            
            loan_listings = cur.fetchall()
            if not loan_listings:
                return None
            
            # Select a random loan listing
            selected_listing = random.choice(loan_listings)
            
            # Transfer player (loan)
            cur.execute("UPDATE players SET club_id = ?, loaned_by = ? WHERE id = ?", 
                       (team_id, selected_listing['seller_team_name'], selected_listing['player_id']))
            
            # Mark listing as completed
            cur.execute("UPDATE market_bazaar_listings SET status = 'completed' WHERE id = ?", (selected_listing['id'],))
            
            # Add player to blacklist
            cur.execute("INSERT OR IGNORE INTO blacklist (user_id, player_id) VALUES (1, ?)", (selected_listing['player_id'],))
            
            conn.commit()
            conn.close()
            
            return {
                'action': 'loan_player',
                'team': f"CPU Team {team_id}",
                'details': {
                    'player_name': selected_listing['player_name'],
                    'loaned_from': selected_listing['seller_team_name'],
                    'player_id': selected_listing['player_id']
                }
            }
            
        except Exception as e:
            print(f"Error making CPU loan offer: {e}")
            return None

    def buy_listed_player(self, team_id: int) -> Optional[Dict]:
        """CPU team directly buys a listed player if they need them and can afford it"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            cur = conn.cursor()
            
            # Get team analysis to understand needs
            analysis = self.analyze_team_composition(team_id)
            if not analysis:
                return None
            
            needs = analysis['needs']
            
            # Find listed players that would improve the team
            cur.execute("""
                SELECT mbl.*, p.player_name, p.registered_position, p.overall, p.market_value,
                       p.salary, p.contract_years_remaining, p.age,
                       t.club_name as seller_team_name
                FROM market_bazaar_listings mbl
                JOIN players p ON mbl.player_id = p.id
                JOIN teams t ON mbl.team_id = t.id
                WHERE mbl.status = 'active' 
                AND mbl.listing_type IN ('cpu_sale', 'user_sale')
                AND mbl.team_id != ?  -- Not from own team
                AND p.id NOT IN (
                    SELECT player_id FROM blacklist WHERE user_id = 1
                )
                AND mbl.asking_price <= (
                    SELECT budget FROM teams WHERE id = ?
                ) * 0.3  -- Don't spend more than 30% of budget on one player
                ORDER BY p.overall DESC, mbl.asking_price ASC
                LIMIT 10
            """, (team_id, team_id))
            
            available_players = cur.fetchall()
            if not available_players:
                return None
            
            # Select a player that would improve the team
            selected_player = None
            for player in available_players:
                position = str(player['registered_position'])
                player_overall = player['overall'] or 0
                
                # Get the current best player in this position on the team
                cur.execute("""
                    SELECT MAX(overall) as best_overall
                    FROM players
                    WHERE club_id = ? AND registered_position = ?
                """, (team_id, position))
                
                current_best_result = cur.fetchone()
                current_best_overall = current_best_result['best_overall'] if current_best_result and current_best_result['best_overall'] else 0
                
                # Buy if this player would be an improvement OR if it's a CPU-to-CPU transaction with reasonable price
                is_improvement = player_overall > current_best_overall
                is_cpu_to_cpu = player['listing_type'] == 'cpu_sale'
                player_market_value = player['market_value'] or 1000000
                is_reasonable_price = player['asking_price'] <= player_market_value * 1.2  # Within 120% of market value
                
                if is_improvement or (is_cpu_to_cpu and is_reasonable_price):
                    # Apply the same sophisticated contract evaluation as CPU offers
                    asking_price = player['asking_price']
                    market_value = player['market_value'] or 1000000
                    current_salary = player['salary'] or 0
                    contract_years = player['contract_years_remaining'] or 1
                    
                    # Calculate fair salary using game mechanics
                    fair_salary = self.calculate_fair_salary(dict(player))
                    salary_difference = current_salary - fair_salary
                    total_overpayment = salary_difference * contract_years
                    
                    # Base acceptable range (80-90% of market value)
                    base_min = market_value * 0.8
                    base_max = market_value * 0.9
                    
                    # Adjust for contract situation (less strict for CPU-to-CPU transactions)
                    if salary_difference > 0:
                        # Overpaid player - reduce acceptable price by overpayment amount
                        # Use lower penalty for CPU-to-CPU transactions to encourage more trading
                        contract_penalty = min(total_overpayment * 0.2, market_value * 0.4)  # Reduced penalty
                        adjusted_min = base_min - contract_penalty
                        adjusted_max = base_max - contract_penalty
                        
                        # For extremely toxic contracts, require compensation (negative asking price)
                        if total_overpayment > market_value * 2:  # If overpayment > 2x market value
                            # Only accept if asking price is negative (user pays CPU to take player)
                            compensation_required = min(total_overpayment * 0.2, market_value * 0.3)
                            adjusted_min = -compensation_required  # Negative = user pays CPU
                            adjusted_max = market_value * 0.1  # Small positive offer as alternative
                    else:
                        # Underpaid player - can pay premium for good contracts
                        contract_bonus = abs(total_overpayment) * 0.3
                        adjusted_min = base_min + contract_bonus
                        adjusted_max = min(base_max + contract_bonus, market_value * 1.2)  # Cap at 120% of market value
                    
                    # Check if asking price is within acceptable range OR is a great deal OR is CPU-to-CPU with reasonable price
                    is_great_deal = asking_price < market_value * 0.5  # Less than 50% of market value
                    is_acceptable_price = adjusted_min <= asking_price <= adjusted_max
                    is_cpu_to_cpu_reasonable = is_cpu_to_cpu and asking_price <= market_value * 1.2
                    
                    if is_acceptable_price or is_great_deal or is_cpu_to_cpu_reasonable:
                        selected_player = player
                        break
            
            # If no improvement found, don't buy anyone
            if not selected_player:
                return None
            
            # Buy the player directly
            asking_price = selected_player['asking_price']
            
            # Transfer player
            cur.execute("UPDATE players SET club_id = ? WHERE id = ?", 
                       (team_id, selected_player['player_id']))
            
            # Get buyer team name first
            cur.execute("SELECT club_name FROM teams WHERE id = ?", (team_id,))
            buyer_team = cur.fetchone()
            
            # Update budgets - handle user teams vs CPU teams differently
            seller_team_id = selected_player['team_id']
            
            # Check if seller is a user team (unified budget system)
            cur.execute("SELECT user_id FROM league_teams WHERE id = ?", (seller_team_id,))
            seller_team_info = cur.fetchone()
            
            if seller_team_info and seller_team_info['user_id'] != 1:  # User team
                # Use unified budget system for user teams - add movement directly to database
                # First get current budget and update it
                cur.execute("SELECT budget FROM user_budgets WHERE user_id = ?", (seller_team_info['user_id'],))
                current_budget_result = cur.fetchone()
                current_budget = current_budget_result['budget'] if current_budget_result else 450000000
                new_budget = current_budget + asking_price
                
                # Update user budget
                cur.execute("""
                    INSERT OR REPLACE INTO user_budgets (user_id, budget, updated_at) 
                    VALUES (?, ?, ?)
                """, (seller_team_info['user_id'], new_budget, datetime.now().isoformat()))
                
                # Add movement record
                cur.execute("""
                    INSERT INTO user_movements (user_id, type, description, amount, balance_after)
                    VALUES (?, ?, ?, ?, ?)
                """, (seller_team_info['user_id'], 'CPU Sale',
                      f"Sold {selected_player['player_name']} to {buyer_team['club_name']}",
                      asking_price, new_budget))
                
                # Send inbox message directly to database
                cur.execute("SELECT username, email FROM users WHERE id = ?", (seller_team_info['user_id'],))
                user_info = cur.fetchone()
                if user_info:
                    subject = f"Player Sale: {selected_player['player_name']}"
                    message = f"Your player {selected_player['player_name']} has been sold to {buyer_team['club_name']} for €{asking_price:,}."
                    cur.execute("""
                        INSERT INTO messages (sender_id, receiver_id, subject, content, created_at)
                        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (1, seller_team_info['user_id'], subject, message))
            else:
                # CPU team - update teams table budget
                cur.execute("UPDATE teams SET budget = budget + ? WHERE id = ?", 
                           (asking_price, seller_team_id))
            
            # Buyer (CPU team) pays from teams table budget
            cur.execute("UPDATE teams SET budget = budget - ? WHERE id = ?", 
                       (asking_price, team_id))
            
            # Mark listing as completed
            cur.execute("UPDATE market_bazaar_listings SET status = 'completed' WHERE id = ?", 
                       (selected_player['id'],))
            
            # Add player to blacklist
            cur.execute("INSERT OR IGNORE INTO blacklist (user_id, player_id) VALUES (1, ?)", 
                       (selected_player['player_id'],))
            
            conn.commit()
            conn.close()
            
            return {
                'action': 'buy_player',
                'team': buyer_team['club_name'] if buyer_team else f"Team {team_id}",
                'details': {
                    'player_name': selected_player['player_name'],
                    'price_paid': asking_price,
                    'seller_team': selected_player['seller_team_name'],
                    'player_id': selected_player['player_id']
                }
            }
            
        except Exception as e:
            print(f"Error buying listed player: {e}")
            return None

    def make_cpu_offer_for_user_player(self, team_id: int) -> Optional[Dict]:
        """CPU team makes offer for USER player (not listed) - creates actual database entry"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            cur = conn.cursor()
            
            # Get team analysis to understand needs
            analysis = self.analyze_team_composition(team_id)
            if not analysis:
                return None
            
            # Get team's current players by position to find improvement targets
            cur.execute("""
                SELECT registered_position, MAX(overall) as best_overall, AVG(overall) as avg_overall
                FROM players 
                WHERE club_id = ?
                GROUP BY registered_position
            """, (team_id,))
            
            position_analysis = {row['registered_position']: {
                'best': row['best_overall'], 
                'average': row['avg_overall']
            } for row in cur.fetchall()}
            
            # Find user players that would IMPROVE the team (not listed, not blacklisted)
            cur.execute("""
                SELECT p.*, t.club_name as current_team_name
                FROM players p
                JOIN teams t ON p.club_id = t.id
                JOIN league_teams lt ON t.id = lt.id
                WHERE lt.user_id != 1  -- User teams only
                AND p.id NOT IN (
                    SELECT player_id FROM market_bazaar_listings WHERE status = 'active'
                )
                AND p.id NOT IN (
                    SELECT player_id FROM blacklist WHERE user_id = 1
                )
                AND p.overall > 75  -- Only interested in good players
                ORDER BY p.overall DESC, p.market_value ASC
            """, ())
            
            user_players = cur.fetchall()
            if not user_players:
                return None
            
            # Filter players that would actually improve the team
            improvement_candidates = []
            for player in user_players:
                position = player['registered_position']
                player_overall = player['overall']
                
                if position in position_analysis:
                    best_in_position = position_analysis[position]['best']
                    avg_in_position = position_analysis[position]['average']
                    
                    # Player must be better than current best OR significantly better than average
                    if player_overall > best_in_position or player_overall > (avg_in_position + 5):
                        improvement_candidates.append(player)
                else:
                    # If team has no player in this position, any good player is an improvement
                    improvement_candidates.append(player)
            
            if not improvement_candidates:
                return None
            
            # Select a random improvement candidate
            selected_player = random.choice(improvement_candidates)
            
            # Calculate intelligent offer based on contract situation
            market_value = selected_player['market_value']
            current_salary = selected_player['salary']
            contract_years = selected_player['contract_years_remaining']
            
            # Calculate fair salary using game mechanics
            fair_salary = self.calculate_fair_salary(dict(selected_player))
            
            # Calculate contract toxicity
            salary_difference = current_salary - fair_salary
            total_overpayment = salary_difference * contract_years
            
            # Base offer range (80-90% of market value)
            base_min = market_value * 0.8
            base_max = market_value * 0.9
            
            # Adjust for contract situation
            if salary_difference > 0:
                # Overpaid player - reduce offer by overpayment amount
                contract_penalty = min(total_overpayment * 0.5, market_value * 0.8)  # Cap at 80% of market value
                adjusted_min = base_min - contract_penalty  # Can go below market value
                adjusted_max = base_max - contract_penalty
                
                # For extremely toxic contracts, allow compensation offers (negative values)
                if total_overpayment > market_value * 2:  # If overpayment > 2x market value
                    # Offer compensation to take the player off user's hands
                    compensation = min(total_overpayment * 0.2, market_value * 0.3)  # Max 30% market value compensation
                    adjusted_min = -compensation  # Negative value = compensation
                    adjusted_max = market_value * 0.1  # Small positive offer as alternative
            else:
                # Underpaid player - increase offer
                contract_bonus = abs(total_overpayment) * 0.3  # Reward good contract
                adjusted_min = base_min + contract_bonus
                adjusted_max = min(base_max + contract_bonus, market_value * 1.2)  # Cap at 120% of market value
            
            # Final offer calculation
            # Handle negative values for toxic contracts (compensation offers)
            if adjusted_min < 0:
                # For toxic contracts, we want negative offers (user pays CPU)
                # Use the negative range properly
                offered_price = random.randint(int(adjusted_min), int(adjusted_max))
            else:
                # Normal case: ensure min <= max for random.randint
                min_price = int(min(adjusted_min, adjusted_max))
                max_price = int(max(adjusted_min, adjusted_max))
                offered_price = random.randint(min_price, max_price)
            
            # Create a temporary listing for this player so we can create an offer
            from datetime import datetime, timedelta
            expires_at = datetime.now() + timedelta(days=7)
            
            # Create temporary listing
            cur.execute("""
                INSERT INTO market_bazaar_listings (player_id, team_id, asking_price, expires_at, status, listing_type)
                VALUES (?, ?, ?, ?, 'active', 'cpu_user_offer')
            """, (selected_player['id'], selected_player['club_id'], market_value, expires_at.isoformat()))
            
            listing_id = cur.lastrowid
            
            # Create the actual offer
            cur.execute("""
                INSERT INTO market_bazaar_offers (listing_id, buyer_team_id, offered_price, expires_at, status)
                VALUES (?, ?, ?, ?, 'active')
            """, (listing_id, team_id, offered_price, expires_at.isoformat()))
            
            # Get team name
            cur.execute("SELECT club_name FROM teams WHERE id = ?", (team_id,))
            buyer_team = cur.fetchone()
            
            conn.commit()
            conn.close()
            
            return {
                'action': 'make_user_offer',
                'team': buyer_team['club_name'] if buyer_team else f"Team {team_id}",
                'details': {
                    'player_name': selected_player['player_name'],
                    'offered_price': offered_price,
                    'market_value': market_value,
                    'current_team': selected_player['current_team_name'],
                    'player_id': selected_player['id'],
                    'contract_analysis': {
                        'current_salary': current_salary,
                        'fair_salary': fair_salary,
                        'salary_difference': salary_difference,
                        'contract_years': contract_years,
                        'total_overpayment': total_overpayment,
                        'improvement_reason': f"Player overall {selected_player['overall']} vs team best {position_analysis.get(selected_player['registered_position'], {}).get('best', 'N/A')}"
                    }
                }
            }
            
        except Exception as e:
            print(f"Error making CPU offer for user player: {e}")
            return None

    def make_cpu_market_bazaar_offer(self, team_id: int) -> Optional[Dict]:
        """Make a CPU team bid on a player in the market bazaar"""
        try:
            # Use a fresh connection for each operation
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            cur = conn.cursor()
            
            # Get team analysis
            analysis = self.analyze_team_composition(team_id)
            if not analysis:
                return None
            
            needs = analysis['needs']
            budget = analysis['needs'].budget_available
            
            # Get needed positions
            needed_positions = self.get_team_position_needs(team_id)
            
            if not needed_positions or budget < 1000000:  # Minimum budget for offers
                return None
            
            # Find suitable players in market bazaar (both CPU and user listed) - exclude blacklisted players
            cur.execute("""
                SELECT mbl.*, p.player_name, p.market_value, p.registered_position, p.overall, mbl.listing_type
                FROM market_bazaar_listings mbl
                JOIN players p ON mbl.player_id = p.id
                WHERE mbl.status = 'active'
                AND p.registered_position IN ({})
                AND mbl.asking_price <= ?
                AND mbl.team_id != ?
                AND p.id NOT IN (
                    SELECT player_id FROM blacklist WHERE user_id = 1
                )
                ORDER BY p.overall DESC
                LIMIT 15
            """.format(','.join(map(str, needed_positions))), (budget * 0.8, team_id))
            
            available_players = cur.fetchall()
            
            if not available_players:
                return None
            
            # Prefer user-listed players (better deals) but also consider CPU players
            user_listed = [p for p in available_players if p['listing_type'] == 'user_sale']
            cpu_listed = [p for p in available_players if p['listing_type'] == 'cpu_sale']
            
            # 70% chance to prefer user-listed players, 30% for CPU players
            if user_listed and random.random() < 0.7:
                selected_listing = random.choice(user_listed)
            elif cpu_listed:
                selected_listing = random.choice(cpu_listed)
            else:
                selected_listing = random.choice(available_players)
            
            # Calculate offer (85-100% of asking price, with higher chance of full price)
            asking_price = selected_listing['asking_price']
            
            # 40% chance of offering full asking price (100%)
            # 60% chance of offering 85-99% of asking price
            if random.random() < 0.4:
                offered_price = asking_price  # Full asking price
            else:
                offer_range = (asking_price * 0.85, asking_price * 0.99)
                min_offer = int(min(offer_range[0], offer_range[1]))
                max_offer = int(max(offer_range[0], offer_range[1]))
                offered_price = random.randint(min_offer, max_offer)
            
            # If CPU offers 95% or more of asking price, complete the transfer immediately
            if offered_price >= (asking_price * 0.95):
                # Get team names for the return message
                cur.execute("SELECT club_name FROM teams WHERE id = ?", (team_id,))
                buyer_team = cur.fetchone()
                cur.execute("SELECT club_name FROM teams WHERE id = ?", (selected_listing['team_id'],))
                seller_team = cur.fetchone()
                
                # Complete the transfer immediately
                cur.execute("UPDATE players SET club_id = ? WHERE id = ?", 
                           (team_id, selected_listing['player_id']))
                
                # Update budgets
                cur.execute("UPDATE teams SET budget = budget + ? WHERE id = ?", 
                           (offered_price, selected_listing['team_id']))
                cur.execute("UPDATE teams SET budget = budget - ? WHERE id = ?", 
                           (offered_price, team_id))
                
                # Mark listing as completed
                cur.execute("UPDATE market_bazaar_listings SET status = 'completed' WHERE id = ?", 
                           (selected_listing['id'],))
                
                # Add player to blacklist
                cur.execute("INSERT OR IGNORE INTO blacklist (user_id, player_id) VALUES (1, ?)", 
                           (selected_listing['player_id'],))
                
                conn.commit()
                conn.close()
                
                return {
                    'action': 'buy_player',
                    'team': buyer_team['club_name'] if buyer_team else f"Team {team_id}",
                    'details': {
                        'player_name': selected_listing['player_name'],
                        'price_paid': offered_price,
                        'seller_team': seller_team['club_name'] if seller_team else 'Unknown',
                        'player_id': selected_listing['player_id']
                    }
                }
            
            # Otherwise, just make an offer
            
            # Create offer
            from datetime import datetime, timedelta
            expires_at = datetime.now() + timedelta(days=random.randint(3, 7))  # 3-7 days
            
            cur.execute("""
                INSERT INTO market_bazaar_offers (listing_id, buyer_team_id, offered_price, expires_at, status)
                VALUES (?, ?, ?, ?, 'active')
            """, (selected_listing['id'], team_id, offered_price, expires_at.isoformat()))
            
            conn.commit()
            conn.close()
            
            return {
                'action': 'make_market_offer',
                'team': analysis['team_name'],
                'details': {
                    'player_name': selected_listing['player_name'],
                    'offered_price': offered_price,
                    'asking_price': asking_price,
                    'player_id': selected_listing['player_id']
                }
            }
            
        except Exception as e:
            print(f"Error making CPU market bazaar offer: {e}")
            try:
                conn.close()
            except:
                pass
            return None
    
    def process_user_offers(self) -> List[Dict]:
        """Process offers from users to CPU teams using sophisticated evaluation"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            cur = conn.cursor()
            
            # For now, we'll create a simple table to track user offers to CPU teams
            # This is a temporary solution - in production you'd want a proper table
            cur.execute("""
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
            
            # Get pending user offers to CPU teams
            cur.execute("""
                SELECT uco.*, p.player_name, p.registered_position, p.overall, p.market_value,
                       p.salary, p.contract_years_remaining, p.age, p.club_id as cpu_team_id,
                       t.club_name as cpu_team_name
                FROM user_cpu_offers uco
                JOIN players p ON uco.player_id = p.id
                JOIN teams t ON uco.seller_team_id = t.id
                WHERE uco.status = 'pending'
            """)
            
            pending_offers = cur.fetchall()
            processed_offers = []
            
            # Group offers by player_id to handle multiple offers for same player
            offers_by_player = {}
            for offer in pending_offers:
                player_id = offer['player_id']
                if player_id not in offers_by_player:
                    offers_by_player[player_id] = []
                offers_by_player[player_id].append(offer)
            
            # Process each player's offers
            for player_id, player_offers in offers_by_player.items():
                # First, check if the player is still available (not sold/transferred)
                cur.execute("""
                    SELECT p.id, p.club_id, p.player_name, t.club_name
                    FROM players p
                    JOIN teams t ON p.club_id = t.id
                    WHERE p.id = ?
                """, (player_id,))
                
                player_check = cur.fetchone()
                if not player_check:
                    # Player doesn't exist anymore - discard all offers
                    print(f"⚠️  Player {player_id} no longer exists, discarding {len(player_offers)} offers")
                    for offer in player_offers:
                        cur.execute("UPDATE user_cpu_offers SET status = 'cancelled' WHERE id = ?", (offer['id'],))
                        # Send cancellation message
                        cur.execute("""
                            INSERT INTO messages (sender_id, receiver_id, subject, content, created_at)
                            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """, (1, offer['buyer_team_id'], f"Transfer Cancelled: Player No Longer Available", 
                              f"Your offer for player ID {player_id} has been cancelled as the player is no longer available."))
                    continue
                
                # Check if player is still on the same CPU team (not transferred elsewhere)
                original_cpu_team_id = player_offers[0]['cpu_team_id']
                if player_check['club_id'] != original_cpu_team_id:
                    # Player has been transferred to a different team - discard all offers
                    print(f"⚠️  Player {player_check['player_name']} (ID: {player_id}) transferred from team {original_cpu_team_id} to {player_check['club_id']}, discarding {len(player_offers)} offers")
                    for offer in player_offers:
                        cur.execute("UPDATE user_cpu_offers SET status = 'cancelled' WHERE id = ?", (offer['id'],))
                        # Send cancellation message
                        cur.execute("""
                            INSERT INTO messages (sender_id, receiver_id, subject, content, created_at)
                            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """, (1, offer['buyer_team_id'], f"Transfer Cancelled: {player_check['player_name']}", 
                              f"Your offer for {player_check['player_name']} has been cancelled as the player has been transferred to {player_check['club_name']}."))
                    continue
                
                # Player is still available on the original CPU team - proceed with processing
                # Sort offers by price (highest first) and select the best one
                player_offers.sort(key=lambda x: x['offered_price'], reverse=True)
                best_offer = player_offers[0]
                rejected_offers = player_offers[1:]  # All other offers for this player
                
                cpu_team_id = best_offer['cpu_team_id']
                offered_price = best_offer['offered_price']
                
                # Get current player data (not stale data from when offer was made)
                cur.execute("""
                    SELECT p.player_name, p.registered_position, p.overall, p.market_value,
                           p.salary, p.contract_years_remaining, p.age, p.club_id
                    FROM players p
                    WHERE p.id = ?
                """, (player_id,))
                
                current_player_data = cur.fetchone()
                if not current_player_data:
                    # This shouldn't happen since we already checked above, but just in case
                    continue
                
                player_overall = current_player_data['overall']
                position = str(current_player_data['registered_position'])
                market_value = current_player_data['market_value'] or 1000000
                current_salary = current_player_data['salary'] or 0
                contract_years = current_player_data['contract_years_remaining'] or 1
                
                # Get current best player in this position on the CPU team
                cur.execute("""
                    SELECT MAX(overall) as best_overall, COUNT(*) as position_count
                    FROM players
                    WHERE club_id = ? AND registered_position = ?
                """, (cpu_team_id, position))
                
                current_best_result = cur.fetchone()
                current_best_overall = current_best_result['best_overall'] if current_best_result and current_best_result['best_overall'] else 0
                position_count = current_best_result['position_count'] if current_best_result else 0
                
                # Apply sophisticated contract evaluation using current player data
                # Calculate fair salary using current player data
                fair_salary = self.calculate_fair_salary(dict(current_player_data))
                salary_difference = current_salary - fair_salary
                total_overpayment = salary_difference * contract_years
                
                # Base minimum acceptable price (market value)
                base_min = market_value
                
                # Initialize adjusted_min with base value
                adjusted_min = base_min
                
                # Adjust for player age (development potential)
                player_age = current_player_data['age']
                age_bonus = 0
                
                if player_age < 25:
                    # Young players have development potential
                    if player_age <= 20:
                        age_bonus = market_value * 0.3  # 30% bonus for very young players
                    elif player_age <= 22:
                        age_bonus = market_value * 0.2  # 20% bonus for young players
                    else:
                        age_bonus = market_value * 0.1  # 10% bonus for developing players
                elif player_age > 30:
                    # Older players have declining value
                    if player_age > 35:
                        age_penalty = market_value * 0.2  # 20% penalty for very old players
                    else:
                        age_penalty = market_value * 0.1  # 10% penalty for older players
                    adjusted_min -= age_penalty
                else:
                    # Prime age players (25-30) - no adjustment
                    pass
                
                # Apply age bonus to minimum price
                adjusted_min += age_bonus
                
                # Adjust for contract situation
                if salary_difference > 0:
                    # Overpaid player - reduce minimum price (easier to sell)
                    contract_penalty = min(total_overpayment * 0.1, market_value * 0.2)
                    adjusted_min -= contract_penalty
                    
                    # For extremely toxic contracts, require compensation
                    if total_overpayment > market_value * 3:  # Only for very toxic contracts
                        compensation_required = min(total_overpayment * 0.1, market_value * 0.2)
                        adjusted_min = -compensation_required
                else:
                    # Underpaid player - increase minimum price (harder to sell)
                    contract_bonus = abs(total_overpayment) * 0.2
                    adjusted_min += contract_bonus
                
                # CRITICAL: Adjust price based on how good the CPU's current player is (more realistic)
                if current_best_overall > 0:
                    # If CPU has a good player in this position, demand premium
                    if current_best_overall > player_overall + 5:
                        # CPU's player is significantly better - demand premium
                        premium_multiplier = 1.2 + (current_best_overall - player_overall - 5) * 0.05
                        adjusted_min *= premium_multiplier
                    elif current_best_overall >= player_overall:
                        # CPU's player is as good or slightly better - small premium
                        premium_multiplier = 1.1 + (current_best_overall - player_overall) * 0.02
                        adjusted_min *= premium_multiplier
                    elif current_best_overall >= player_overall - 3:
                        # CPU's player is close in quality - no premium
                        pass  # No adjustment
                    else:
                        # CPU's player is significantly worse - small discount
                        discount_multiplier = 0.95 + (player_overall - current_best_overall - 3) * 0.01
                        adjusted_min *= discount_multiplier
                
                # Check if the best offer is acceptable (CPU accepts if offer is above minimum)
                if offered_price >= adjusted_min:
                    # Accept the best offer
                    cur.execute("UPDATE user_cpu_offers SET status = 'accepted' WHERE id = ?", (best_offer['id'],))
                    
                    # Transfer player
                    cur.execute("UPDATE players SET club_id = ? WHERE id = ?", (best_offer['buyer_team_id'], player_id))
                    
                    # Update budgets using unified budget system
                    # Get the actual user_id from the league_team_id
                    cur.execute("SELECT user_id FROM league_teams WHERE id = ?", (best_offer['buyer_team_id'],))
                    user_result = cur.fetchone()
                    if not user_result:
                        print(f"⚠️  Could not find user_id for league_team_id {best_offer['buyer_team_id']}")
                        continue
                    actual_user_id = user_result['user_id']
                    
                    # Get current budget from unified system
                    cur.execute("""
                        SELECT COALESCE(SUM(amount), 0) as current_budget
                        FROM user_movements 
                        WHERE user_id = ?
                    """, (actual_user_id,))
                    budget_result = cur.fetchone()
                    current_budget = budget_result['current_budget'] if budget_result else 0
                    new_balance = current_budget - offered_price
                    
                    # Add movement record to unified budget system
                    cur.execute("""
                        INSERT INTO user_movements (user_id, type, description, amount, balance_after)
                        VALUES (?, ?, ?, ?, ?)
                    """, (actual_user_id, 'CPU Purchase', 
                          f"Bought {current_player_data['player_name']} from {best_offer['cpu_team_name']}", 
                          -offered_price, new_balance))
                    
                    # CPU team receives money
                    cur.execute("UPDATE teams SET budget = budget + ? WHERE id = ?", (offered_price, cpu_team_id))
                    
                    # Blacklist player universally (affects everyone)
                    cur.execute("INSERT OR IGNORE INTO blacklist (user_id, player_id) VALUES (1, ?)", 
                               (player_id,))
                    
                    # Send inbox message to user who won
                    cur.execute("""
                        INSERT INTO messages (sender_id, receiver_id, subject, content, created_at)
                        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (1, actual_user_id, f"Transfer Accepted: {current_player_data['player_name']}", 
                          f"Your offer of €{offered_price:,} for {current_player_data['player_name']} has been accepted by {best_offer['cpu_team_name']}!"))
                    
                    # Create blog post about the transfer
                    blog_title = f"Transfer News: {current_player_data['player_name']} Joins New Club"
                    blog_content = f"{current_player_data['player_name']} has completed a transfer from {best_offer['cpu_team_name']} for €{offered_price:,}. The deal was finalized after successful negotiations."
                    
                    cur.execute("""
                        INSERT INTO blog_posts (title, content, author_id, created_at)
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    """, (blog_title, blog_content, 1))  # Author ID 1 for system posts
                    
                    processed_offers.append({
                        'action': 'offer_accepted',
                        'player_name': best_offer['player_name'],
                        'cpu_team_name': best_offer['cpu_team_name'],
                        'offered_price': offered_price,
                        'buyer_team_id': best_offer['buyer_team_id']
                    })
                    
                    # Reject all other offers for this player
                    for rejected_offer in rejected_offers:
                        cur.execute("UPDATE user_cpu_offers SET status = 'rejected' WHERE id = ?", (rejected_offer['id'],))
                        
                        # Send rejection message
                        cur.execute("""
                            INSERT INTO messages (sender_id, receiver_id, subject, content, created_at)
                            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """, (1, rejected_offer['buyer_team_id'], f"Transfer Rejected: {current_player_data['player_name']}", 
                              f"Your offer of €{rejected_offer['offered_price']:,} for {current_player_data['player_name']} has been rejected by {rejected_offer['cpu_team_name']}. A higher offer was accepted."))
                        
                        processed_offers.append({
                            'action': 'offer_rejected',
                            'player_name': rejected_offer['player_name'],
                            'cpu_team_name': rejected_offer['cpu_team_name'],
                            'offered_price': rejected_offer['offered_price'],
                            'buyer_team_id': rejected_offer['buyer_team_id'],
                            'reason': 'higher_offer_accepted'
                        })
                else:
                    # Reject ALL offers for this player (including the best one)
                    all_offers = [best_offer] + rejected_offers
                    
                    for offer in all_offers:
                        cur.execute("UPDATE user_cpu_offers SET status = 'rejected' WHERE id = ?", (offer['id'],))
                        
                        # Send rejection message
                        cur.execute("""
                            INSERT INTO messages (sender_id, receiver_id, subject, content, created_at)
                            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """, (1, offer['buyer_team_id'], f"Transfer Rejected: {current_player_data['player_name']}", 
                              f"Your offer of €{offer['offered_price']:,} for {current_player_data['player_name']} has been rejected by {offer['cpu_team_name']}. The offer was not sufficient for their valuation."))
                        
                        processed_offers.append({
                            'action': 'offer_rejected',
                            'player_name': offer['player_name'],
                            'cpu_team_name': offer['cpu_team_name'],
                            'offered_price': offer['offered_price'],
                            'buyer_team_id': offer['buyer_team_id'],
                            'reason': 'insufficient_offer'
                        })
            
            conn.commit()
            conn.close()
            return processed_offers
            
        except Exception as e:
            print(f"Error processing user offers: {e}")
            return []
    
    def process_cpu_ai_actions(self) -> Dict:
        """Process all CPU AI actions (market bazaar only)"""
        try:
            # Use a fresh connection
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            cur = conn.cursor()
            
            # Get all CPU teams
            cur.execute("""
                SELECT t.id, t.club_name
                FROM teams t
                WHERE t.id != 141 
                AND t.id IN (
                    SELECT DISTINCT lt.id FROM league_teams lt WHERE lt.user_id = 1
                )
            """)
            
            cpu_teams = cur.fetchall()
            actions_taken = []
            
            # First, process user offers to CPU teams
            user_offers_processed = self.process_user_offers()
            for offer_result in user_offers_processed:
                actions_taken.append({
                    'team': 'CPU Teams',
                    'action': offer_result['action'],
                    'details': {
                        'player_name': offer_result['player_name'],
                        'cpu_team_name': offer_result['cpu_team_name'],
                        'offered_price': offer_result['offered_price']
                    }
                })
            
            # Process each CPU team
            for team in cpu_teams:
                team_id = team['id']
                team_name = team['club_name']
                
                # Random chance for CPU actions (25% chance per team)
                if random.random() < 0.25:
                    # CPU actions: prioritize buying/loaning existing listings, then make offers
                    action_choice = random.random()
                    if action_choice < 0.5:  # 50% chance to buy existing listings
                        buy_result = self.buy_listed_player(team_id)
                        if buy_result:
                            actions_taken.append({
                                'team': team_name,
                                'action': 'buy_player',
                                'details': buy_result['details']
                            })
                    elif action_choice < 0.8:  # 30% chance to loan existing loan listings
                        loan_result = self.make_cpu_loan_offer(team_id)
                        if loan_result:
                            actions_taken.append({
                                'team': team_name,
                                'action': 'loan_player',
                                'details': loan_result['details']
                            })
                    else:  # 20% chance to make offer for USER players
                        offer_result = self.make_cpu_offer_for_user_player(team_id)
                        if offer_result:
                            actions_taken.append({
                                'team': team_name,
                                'action': 'make_user_offer',
                                'details': offer_result['details']
                            })
                    # Note: Listing actions removed from main loop - will be done separately
            
            # Second phase: Create new listings (after all buying is done)
            print("Phase 2: Creating new listings...")
            for team in cpu_teams:
                team_id = team['id']
                team_name = team['club_name']
                
                # Lower chance for listing (8% per team) to avoid market flooding
                if random.random() < 0.08:
                    action_choice = random.random()
                    if action_choice < 0.9:  # 90% chance to list for sale
                        list_result = self.list_cpu_player_for_sale(team_id)
                        if list_result:
                            actions_taken.append({
                                'team': team_name,
                                'action': 'list_player_for_sale',
                                'details': list_result['details']
                            })
                    else:  # 10% chance to list for loan (much lower)
                        list_result = self.list_cpu_player_for_loan(team_id)
                        if list_result:
                            actions_taken.append({
                                'team': team_name,
                                'action': 'list_player_for_loan',
                                'details': list_result['details']
                            })
            
            conn.close()
            
            return {
                'success': True,
                'actions_taken': actions_taken,
                'total_teams_processed': len(cpu_teams),
                'actions_count': len(actions_taken)
            }
            
        except Exception as e:
            print(f"Error processing CPU AI actions: {e}")
            return {'success': False, 'error': str(e)}

# Global instance for easy access
cpu_ai = CPUAI()
