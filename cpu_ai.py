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
            
            # Analyze composition (registered_position returns strings, not integers)
            current_gk = position_counts.get('0', 0)
            current_def = position_counts.get('2', 0) + position_counts.get('3', 0)
            current_fb = position_counts.get('4', 0) + position_counts.get('6', 0)
            current_mid = position_counts.get('5', 0) + position_counts.get('7', 0) + position_counts.get('9', 0)
            current_wing = position_counts.get('8', 0) + position_counts.get('10', 0)
            current_fwd = position_counts.get('11', 0) + position_counts.get('12', 0)
            
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
        toxic_threshold = fair_salary * 1.2
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
                can_afford = team_budget >= player_market_value * 0.75  # At least 25% of market value
                
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
            
            # Compute position counts to find surplus positions (>4 players), protect GK minimum of 2
            cur.execute("""
                SELECT registered_position, COUNT(*) AS cnt
                FROM players
                WHERE club_id = ?
                GROUP BY registered_position
            """, (team_id,))
            counts = {row['registered_position']: row['cnt'] for row in cur.fetchall()}

            surplus_positions = [pos for pos, cnt in counts.items() if cnt and int(cnt) > 4]
            # GK protection: do not consider GK if <= 2
            if counts.get('0', 0) <= 2 and '0' in surplus_positions:
                surplus_positions.remove('0')

            if not surplus_positions:
                return None

            # Exclude already listed or blacklisted players
            # Choose weaker and younger players from surplus positions (not the best in position)
            position_list_sql = ','.join([f"'{p}'" for p in surplus_positions])

            # Find candidate players ranked by (overall ASC, age ASC) within surplus positions, excluding top overall per position
            cur.execute(f"""
                WITH best_per_pos AS (
                    SELECT registered_position, MAX(overall) AS best_ovr
                    FROM players
                    WHERE club_id = ?
                    GROUP BY registered_position
                )
                SELECT p.*, t.club_name
                FROM players p
                JOIN teams t ON p.club_id = t.id
                LEFT JOIN best_per_pos bpp
                    ON bpp.registered_position = p.registered_position
                WHERE p.club_id = ? 
                AND p.registered_position IN ({position_list_sql})
                AND (bpp.best_ovr IS NULL OR p.overall < bpp.best_ovr)
                AND p.id NOT IN (SELECT player_id FROM market_bazaar_listings WHERE status = 'active')
                AND p.id NOT IN (SELECT player_id FROM blacklist WHERE user_id = 1)
                ORDER BY p.overall ASC, p.age ASC
                LIMIT 1
            """, (team_id, team_id))
            
            player = cur.fetchone()
            if not player:
                return None
            
            # Decide salary support percentage between 0-100%
            # Be more generous for very young or overpaid players
            try:
                fair_salary = self.calculate_fair_salary(dict(player))
            except Exception:
                fair_salary = player['salary'] or 0

            player_salary = player['salary'] or 0
            support_pct = 0.0
            if player_salary > 0:
                if player['age'] <= 21:
                    support_pct = 0.75
                elif fair_salary and player_salary > fair_salary * 1.3:
                    support_pct = 1.0
                elif fair_salary and player_salary > fair_salary * 1.1:
                    support_pct = 0.6
                else:
                    support_pct = 0.3

            # Clamp between 0 and 1
            if support_pct < 0:
                support_pct = 0.0
            if support_pct > 1:
                support_pct = 1.0

            salary_support_percentage = int(support_pct * 100)
            subsidy_amount = int(player_salary * support_pct)

            # asking_price: negative means subsidy (for display logic); 0 if no support
            asking_price = -subsidy_amount if subsidy_amount > 0 else 0
            
            # Create loan listing with salary support percentage
            expires_at = datetime.now() + timedelta(days=7)
            cur.execute(
                """
                INSERT INTO market_bazaar_listings (player_id, team_id, asking_price, expires_at, status, listing_type, salary_support_percentage)
                VALUES (?, ?, ?, ?, 'active', 'cpu_loan', ?)
                """,
                (player['id'], team_id, asking_price, expires_at.isoformat(), float(salary_support_percentage))
            )
            
            conn.commit()
            conn.close()
            
            return {
                'action': 'list_player_for_loan',
                'team': player['club_name'],
                'details': {
                    'player_name': player['player_name'],
                    'asking_price': asking_price,
                    'salary_support_percentage': salary_support_percentage,
                    'subsidy_amount': subsidy_amount,
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
            
            # Get the best player per position to protect them from being sold
            cur.execute("""
                SELECT registered_position, MAX(overall) as best_overall, 
                       GROUP_CONCAT(id) as player_ids
                FROM players
                WHERE club_id = ?
                GROUP BY registered_position
            """, (team_id,))
            
            position_bests = cur.fetchall()
            protected_player_ids = []
            
            # Extract the actual best player ID for each position
            for pos_data in position_bests:
                position = pos_data['registered_position']
                best_overall = pos_data['best_overall']
                
                # Get the specific player(s) with the best overall in this position
                cur.execute("""
                    SELECT id FROM players 
                    WHERE club_id = ? AND registered_position = ? AND overall = ?
                    LIMIT 1
                """, (team_id, position, best_overall))
                
                best_player = cur.fetchone()
                if best_player:
                    protected_player_ids.append(best_player['id'])

            # Log protected players for debugging
            if protected_player_ids:
                cur.execute("""
                    SELECT player_name, registered_position, overall 
                    FROM players 
                    WHERE id IN ({})
                """.format(','.join(map(str, protected_player_ids))))
                protected_players = cur.fetchall()
                print(f"Team {team_id} protecting best players: {[f'{p['player_name']} (Pos {p['registered_position']}, {p['overall']} OVR)' for p in protected_players]}")

            # Get current position counts to ensure we only list from positions with surplus
            cur.execute("""
                SELECT registered_position, COUNT(*) as count
                FROM players
                WHERE club_id = ?
                GROUP BY registered_position
            """, (team_id,))
            
            position_counts = {row['registered_position']: row['count'] for row in cur.fetchall()}
            
            # Calculate position groups and check for surplus
            gk_count = position_counts.get('0', 0)
            def_count = position_counts.get('2', 0) + position_counts.get('3', 0)
            fb_count = position_counts.get('4', 0) + position_counts.get('6', 0)
            mid_count = position_counts.get('5', 0) + position_counts.get('7', 0) + position_counts.get('9', 0)
            wing_count = position_counts.get('8', 0) + position_counts.get('10', 0)
            fwd_count = position_counts.get('11', 0) + position_counts.get('12', 0)
            
            # Determine which positions have surplus (above ideal)
            # Never list goalkeepers if we have 2 or fewer (always keep at least 2)
            # Never list from positions that are already below ideal
            positions_with_surplus = set()
            
            if gk_count > self.ideal_composition.goalkeepers:  # Only if more than 2
                positions_with_surplus.add('0')
            if def_count > self.ideal_composition.defenders:  # Only if more than 4
                positions_with_surplus.update(['2', '3'])
            if fb_count > self.ideal_composition.fullbacks:  # Only if more than 4
                positions_with_surplus.update(['4', '6'])
            if mid_count > self.ideal_composition.midfielders:  # Only if more than 6
                positions_with_surplus.update(['5', '7', '9'])
            if wing_count > self.ideal_composition.wingers:  # Only if more than 4
                positions_with_surplus.update(['8', '10'])
            if fwd_count > self.ideal_composition.forwards:  # Only if more than 4
                positions_with_surplus.update(['11', '12'])
            
            # Special case: if team is in debt or has toxic contracts, allow listing
            # but still protect goalkeepers (always keep at least 1)
            # Check for toxic contracts by sampling a few players
            has_toxic_contract = False
            if budget >= 0:  # Only check if not in debt
                cur.execute("SELECT * FROM players WHERE club_id = ? LIMIT 20", (team_id,))
                sample_players = cur.fetchall()
                for p in sample_players:
                    try:
                        fair_salary = self.calculate_fair_salary(dict(p))
                        if p['salary'] and fair_salary and p['salary'] > fair_salary * 1.5:
                            has_toxic_contract = True
                            break
                    except:
                        continue
            
            allow_listing_anyway = budget < 0 or has_toxic_contract
            
            # If no surplus positions AND not in debt, don't list anyone
            if not positions_with_surplus and not allow_listing_anyway:
                return None
            
            # Find players to sell (overpaid, surplus, or if team needs money)
            # Exclude players already listed, blacklisted, AND best players per position
            # Only list from positions with surplus (unless in debt/toxic contract)
            protected_ids_str = ','.join(map(str, protected_player_ids)) if protected_player_ids else '0'
            
            # Build position filter SQL
            position_filter_sql = ""
            if positions_with_surplus:
                # Format: AND p.registered_position IN ('0', '2', '3', ...)
                positions_str = "','".join(positions_with_surplus)
                position_filter_sql = f"AND p.registered_position IN ('{positions_str}')"
            elif allow_listing_anyway:
                # In debt or toxic contracts: allow listing but still protect goalkeepers
                if gk_count <= 1:
                    position_filter_sql = "AND p.registered_position != '0'"  # Never list last goalkeeper
                # Otherwise, no filter (allow all positions)
            
            # Build the full query
            query = f"""
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
                AND p.id NOT IN ({protected_ids_str})  -- Protect best players per position
                {position_filter_sql}  -- Only list from positions with surplus
                ORDER BY p.salary DESC, p.overall ASC
                LIMIT 10
            """
            
            cur.execute(query, (team_id,))
            
            team_players = cur.fetchall()
            
            if not team_players:
                return None
            
            # Additional safety check: verify the selected player's position count
            selected_player = team_players[0]
            selected_position = selected_player['registered_position']
            
            # Extra protection for goalkeepers
            if selected_position == '0':
                current_gk = position_counts.get('0', 0)
                if current_gk <= 2 and not allow_listing_anyway:
                    # Don't list if we only have 2 or fewer GKs (unless forced by debt)
                    return None
                elif current_gk == 1:
                    # Never list the last goalkeeper
                    return None
            
            # Check other positions: don't list if it would drop us below ideal
            if selected_position in ['2', '3']:  # Defenders
                if def_count <= self.ideal_composition.defenders and not allow_listing_anyway:
                    return None
            elif selected_position in ['4', '6']:  # Fullbacks
                if fb_count <= self.ideal_composition.fullbacks and not allow_listing_anyway:
                    return None
            elif selected_position in ['5', '7', '9']:  # Midfielders
                if mid_count <= self.ideal_composition.midfielders and not allow_listing_anyway:
                    return None
            elif selected_position in ['8', '10']:  # Wingers
                if wing_count <= self.ideal_composition.wingers and not allow_listing_anyway:
                    return None
            elif selected_position in ['11', '12']:  # Forwards
                if fwd_count <= self.ideal_composition.forwards and not allow_listing_anyway:
                    return None
            
            # Calculate asking price
            market_value = selected_player['market_value']
            salary = selected_player['salary']
            
            # Check if contract is toxic (salary > 150% of fair value)
            fair_salary = self.calculate_fair_salary(dict(selected_player))
            is_toxic = salary > fair_salary * 1.5
            
            if is_toxic or budget < 0:
                # Sell below market value for toxic contracts or debt
                asking_price = int(market_value * random.uniform(0.8, 0.95))
            else:
                # Normal asking price
                asking_price = int(market_value * random.uniform(0.95, 1.35))
            
            # Create market listing
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
        """CPU team intelligently loans a player from user loan listings based on team needs"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            cur = conn.cursor()
            
            # Get team analysis to understand needs
            analysis = self.analyze_team_composition(team_id)
            if not analysis:
                return None
            
            # Check squad size - don't make offers if at maximum capacity (32 players)
            total_players = analysis['total_players']
            if total_players >= 32:
                print(f"Team {team_id} has {total_players} players (max capacity) - skipping loan offers")
                return None

            needs = analysis['needs']
            needed_positions = self.get_team_position_needs(team_id)

            # Get team's current players by position for improvement analysis
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

            # Also compute current position counts for stricter need evaluation
            cur.execute("""
                SELECT registered_position, COUNT(*) as cnt
                FROM players
                WHERE club_id = ?
                GROUP BY registered_position
            """, (team_id,))
            position_counts = {row['registered_position']: row['cnt'] for row in cur.fetchall()}

            # Find user loan listings with detailed player info
            # IMPORTANT: Select salary_support_percentage from listing to properly calculate subsidies
            cur.execute("""
                SELECT mbl.*, p.player_name, p.market_value, p.registered_position, p.overall, p.age, p.salary,
                       t.club_name as seller_team_name,
                       mbl.salary_support_percentage
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
                AND p.overall >= 70  -- Only consider decent players for loans
                ORDER BY mbl.salary_support_percentage DESC, mbl.asking_price ASC, p.overall DESC  -- Prioritize highest salary support first
                LIMIT 30
            """)
            
            loan_listings = cur.fetchall()
            if not loan_listings:
                print(f"  ⚠️  Team {team_id}: No loan listings found in database")
                return None
            
            print(f"  📋 Team {team_id}: Found {len(loan_listings)} loan listings to evaluate")

            # Intelligently filter and score loan candidates
            loan_candidates = []
            for listing in loan_listings:
                player_position = listing['registered_position']
                player_overall = listing['overall']
                player_age = listing['age']
                asking_price = listing['asking_price']
                player_salary = (listing['salary'] or 0)
                salary_support_percentage = (listing['salary_support_percentage'] or 0.0)
                
                # Calculate salary subsidy - use salary_support_percentage directly if available, otherwise calculate from asking_price
                if salary_support_percentage > 0:
                    # Use percentage directly (more accurate)
                    salary_subsidy = int(player_salary * (salary_support_percentage / 100))
                    subsidy_ratio = salary_support_percentage / 100.0
                else:
                    # Fallback to asking_price calculation (for backward compatibility)
                    salary_subsidy = abs(asking_price) if asking_price < 0 else 0
                    subsidy_ratio = salary_subsidy / player_salary if player_salary > 0 else 0
                
                # Calculate interest score
                interest_score = 0
                
                # CRITICAL: Massive bonus for subsidized loans (salary support)
                # CPU is VERY willing to take heavily supported loans
                if salary_subsidy > 0:
                    
                    # Enhanced scaling: 100% support = 500 points (increased from 400)
                    # This makes heavily subsidized loans extremely attractive
                    base_subsidy_score = int(subsidy_ratio * 500)  # Up to 500 points for 100% support
                    interest_score += base_subsidy_score
                    
                    # Exponential bonuses for higher support percentages
                    if subsidy_ratio >= 1.0:  # 100% support (completely free loan)
                        interest_score += 200  # MASSIVE bonus for 100% free loans
                    elif subsidy_ratio >= 0.90:  # 90%+ support (almost free loan)
                        interest_score += 150  # Massive bonus for near-free loans
                    elif subsidy_ratio >= 0.75:  # 75%+ support
                        interest_score += 100  # Large bonus
                    elif subsidy_ratio >= 0.50:  # 50%+ support
                        interest_score += 60  # Good bonus
                    
                    # Additional bonus for larger absolute subsidy amounts
                    if salary_subsidy >= 5000000:  # €5M+ subsidy
                        interest_score += 80  # Increased from 50
                    elif salary_subsidy >= 2000000:  # €2M+ subsidy
                        interest_score += 50  # Increased from 30
                    elif salary_subsidy >= 1000000:  # €1M+ subsidy
                        interest_score += 35  # Increased from 20
                
                # Bonus for free loans (0€, no support)
                elif asking_price == 0:
                    interest_score += 30
                
                # Position need bonus (highest priority)
                # Heavy bonus if the team needs this position; extra if there are zero players in position
                current_count = position_counts.get(player_position, 0)
                if player_position in needed_positions:
                    interest_score += 120  # strong base need bonus
                    if current_count == 0:
                        interest_score += 150  # critical: fill missing position immediately
                    elif current_count == 1:
                        interest_score += 60
                else:
                    # If not a need, add small penalty unless subsidy is extremely high (>= 90%)
                    if subsidy_ratio < 0.9:
                        interest_score -= 20
                
                # Improvement bonus
                if player_position in position_analysis:
                    best_in_position = position_analysis[player_position]['best']
                    avg_in_position = position_analysis[player_position]['average']
                    
                    if player_overall > best_in_position:
                        interest_score += 30  # Better than current best
                    elif player_overall > (avg_in_position + 3):
                        interest_score += 20  # Significantly better than average
                    elif player_overall > avg_in_position:
                        interest_score += 10  # Better than average
                else:
                    # No player in this position - any decent player is valuable
                    interest_score += 40
                
                # Age bonus (prefer younger players for loans - development opportunity)
                if player_age <= 23:
                    interest_score += 15  # Young talent
                elif player_age <= 26:
                    interest_score += 10  # Prime age
                
                # Salary affordability: heavily prefer players with salary support
                if salary_subsidy > 0:
                    # With subsidy, calculate net cost (salary - subsidy)
                    net_salary_cost = player_salary - salary_subsidy
                    # Prefer if net cost is affordable (scaled by team budget)
                    # With subsidies, CPU should be much more lenient on affordability
                    team_budget = analysis['needs'].budget_available
                    if team_budget > 0:
                        affordability_ratio = net_salary_cost / team_budget
                        if affordability_ratio < 0.1:  # Less than 10% of budget
                            interest_score += 40  # Increased from 25 - heavily subsidized = very affordable
                        elif affordability_ratio < 0.2:  # Less than 20% of budget
                            interest_score += 30  # Increased from 15
                        elif affordability_ratio < 0.4:  # Less than 40% of budget (new tier)
                            interest_score += 15  # Still acceptable with subsidy
                    # Additional bonus: if subsidy covers most/all of salary, treat as almost free
                    subsidy_coverage = salary_subsidy / player_salary if player_salary > 0 else 0
                    if subsidy_coverage >= 0.8:  # 80%+ of salary covered
                        interest_score += 50  # Massive bonus - almost no cost to CPU
                elif player_salary > 0:
                    # Without subsidy, check if full salary is affordable
                    team_budget = analysis['needs'].budget_available
                    if team_budget > 0:
                        affordability_ratio = player_salary / team_budget
                        if affordability_ratio > 0.3:  # More than 30% of budget - penalize
                            interest_score -= 30
                elif player_age <= 29:
                    interest_score += 5   # Still good
                # No bonus for older players

                # Squad size pressure: if near capacity, be extremely selective unless 90%+ supported or critical need
                if total_players >= 31:
                    if player_position not in needed_positions and subsidy_ratio < 0.9:
                        # Skip this candidate altogether when at capacity and it's not critical or highly subsidized
                        continue
                    else:
                        # Minor bonus when we accept something at capacity due to strong rationale
                        interest_score += 20
                
                # Overall rating bonus
                if player_overall >= 85:
                    interest_score += 20  # Excellent player
                elif player_overall >= 80:
                    interest_score += 15  # Very good player
                elif player_overall >= 75:
                    interest_score += 10  # Good player
                elif player_overall >= 70:
                    interest_score += 5   # Decent player
                
                # Lower threshold for heavily subsidized loans - 100% support should ALWAYS pass
                # With 100% support, interest_score will be 500+200+bonuses = 700+ minimum
                # Lower threshold significantly for heavily subsidized loans
                if subsidy_ratio >= 1.0:  # 100% support
                    min_threshold = 0  # Always accept 100% subsidized loans regardless of other factors
                elif subsidy_ratio >= 0.80:  # 80%+ support
                    min_threshold = 10  # Very low threshold
                else:
                    min_threshold = 25  # Standard threshold
                
                if interest_score >= min_threshold:
                    loan_candidates.append({
                        'listing': listing,
                        'score': interest_score,
                        'reason': 'position_needed' if player_position in needed_positions else 'improvement',
                        'subsidy_ratio': subsidy_ratio  # Include for debugging
                    })

            if not loan_candidates:
                print(f"  ⚠️  Team {team_id}: No loan candidates passed filters (evaluated {len(loan_listings)} listings)")
                return None
            
            print(f"  ✅ Team {team_id}: {len(loan_candidates)} loan candidates passed filters")

            # Sort by: 100% support first, then positional need presence, then subsidy ratio, then score
            loan_candidates.sort(
                key=lambda x: (
                    1 if x.get('subsidy_ratio', 0) >= 1.0 else 0,
                    1 if x['reason'] == 'position_needed' else 0,
                    x.get('subsidy_ratio', 0),
                    x['score']
                ),
                reverse=True
            )
            
            # Prefer heavily subsidized loans - if any have 100% support, ALWAYS pick from those first
            fully_subsidized = [c for c in loan_candidates if c.get('subsidy_ratio', 0) >= 1.0]
            if fully_subsidized:
                # 100% subsidized loans - pick best one (highest score)
                fully_subsidized.sort(key=lambda x: x['score'], reverse=True)
                top_candidates = fully_subsidized[:1]  # Always take the best 100% loan
            else:
                # Prefer heavily subsidized loans - if any have 80%+ support, prefer those
                heavily_subsidized = [c for c in loan_candidates if c.get('subsidy_ratio', 0) >= 0.80]
                if heavily_subsidized:
                    # Pick from heavily subsidized loans (top 3 by score)
                    heavily_subsidized.sort(key=lambda x: x['score'], reverse=True)
                    top_candidates = heavily_subsidized[:3] if len(heavily_subsidized) >= 3 else heavily_subsidized
                else:
                    # No heavily subsidized, pick from all (top 3 by score)
                    loan_candidates.sort(key=lambda x: x['score'], reverse=True)
                    top_candidates = loan_candidates[:3]
            
            if not top_candidates:
                print(f"  ❌ Team {team_id}: ERROR - top_candidates is empty!")
                return None
            
            selected_candidate = top_candidates[0] if len(top_candidates) == 1 else random.choice(top_candidates)
            selected_listing = selected_candidate['listing']
            
            subsidy_ratio = selected_candidate.get('subsidy_ratio', 0) if 'subsidy_ratio' in selected_candidate else 0
            subsidy_info = f"{subsidy_ratio*100:.0f}% support" if subsidy_ratio > 0 else "no support"
            print(f"  ✅ Team {team_id} selected loan: {selected_listing['player_name']} (Pos {selected_listing['registered_position']}, {selected_listing['overall']} OVR, {subsidy_info}) - Score: {selected_candidate['score']} ({selected_candidate['reason']})")
            
            # Transfer player (loan)
            cur.execute("UPDATE players SET club_id = ?, loaned_by = ? WHERE id = ?", 
                       (team_id, selected_listing['seller_team_name'], selected_listing['player_id']))
            
            # Handle salary subsidy if asking_price is negative (represents subsidy)
            asking_price = selected_listing['asking_price']
            if asking_price < 0:
                subsidy_amount = abs(asking_price)
                
                # Lender pays the subsidy - find lender's user_id if it's a user team
                lender_team_id = selected_listing['team_id']
                cur.execute("""
                    SELECT lt.user_id 
                    FROM league_teams lt 
                    WHERE lt.id = ?
                """, (lender_team_id,))
                lender_info = cur.fetchone()
                
                if lender_info and lender_info['user_id'] and lender_info['user_id'] != 1:  # User team
                    # Deduct from lender's unified budget similar to free-agency signing bonus handling
                    user_id = lender_info['user_id']
                    # Prefer cached budget if present
                    cur.execute("SELECT budget FROM user_budgets WHERE user_id = ?", (user_id,))
                    budget_row = cur.fetchone()
                    if budget_row and budget_row['budget'] is not None:
                        current_budget = budget_row['budget']
                    else:
                        # Fallback to movements-only sum if cache missing
                        cur.execute("""
                            SELECT COALESCE(SUM(amount), 0) as total
                            FROM user_movements
                            WHERE user_id = ?
                        """, (user_id,))
                        result = cur.fetchone()
                        current_budget = result['total'] if result else 0
                    new_budget = current_budget - subsidy_amount

                    # Update cached budget for consistency with finances
                    cur.execute("""
                        INSERT OR REPLACE INTO user_budgets (user_id, budget, updated_at)
                        VALUES (?, ?, ?)
                    """, (user_id, new_budget, datetime.now().isoformat()))

                    # Resolve CPU team name for clearer description
                    cur.execute("SELECT club_name FROM teams WHERE id = ?", (team_id,))
                    cpu_team_row = cur.fetchone()
                    cpu_team_name = cpu_team_row['club_name'] if cpu_team_row else f"CPU Team {team_id}"

                    # Add movement record
                    cur.execute("""
                        INSERT INTO user_movements (user_id, type, description, amount, balance_after, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        user_id,
                        'Loan Salary Support',
                        f"Salary support for {selected_listing['player_name']} on loan to {cpu_team_name}",
                        -subsidy_amount,
                        new_budget,
                        datetime.now().isoformat()
                    ))
                else:
                    # CPU team lender - deduct from teams table budget
                    cur.execute("UPDATE teams SET budget = budget - ? WHERE id = ?",
                               (subsidy_amount, lender_team_id))
                
                # CPU team (loanee) receives the subsidy - add to teams table budget
                cur.execute("UPDATE teams SET budget = budget + ? WHERE id = ?",
                           (subsidy_amount, team_id))
                
                subsidy_note = f" (€{subsidy_amount:,}/year salary support)"
            else:
                subsidy_note = ""

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
                    'player_id': selected_listing['player_id'],
                    'subsidy': subsidy_note if 'subsidy_note' in locals() else ""
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
            
            # Check squad size - don't buy players if at maximum capacity (32 players)
            total_players = analysis['total_players']
            if total_players >= 32:
                print(f"Team {team_id} has {total_players} players (max capacity) - skipping purchases")
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
                LIMIT 40
            """, (team_id, team_id))
            
            available_players = cur.fetchall()
            if not available_players:
                return None
            
            # Get team needs to prioritize critical positions
            needed_positions = self.get_team_position_needs(team_id)
            
            # Score players by priority (needed positions first, then improvements)
            scored_players = []
            for player in available_players:
                position = str(player['registered_position'])
                player_overall = player['overall'] or 0
                
                # Priority score: higher = more important
                priority_score = 0
                
                # CRITICAL: Fill missing positions (especially goalkeepers)
                if position == '0' and analysis['needs'].needs_goalkeeper:
                    priority_score = 1000  # Highest priority
                elif position in needed_positions:
                    priority_score = 500  # High priority for needed positions
                
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
                
                # More lenient criteria for CPU-to-CPU to encourage trading
                is_minor_improvement = is_cpu_to_cpu and player_overall > (current_best_overall - 2)  # Allow -2 overall for CPU trades
                is_position_fill = current_best_overall == 0  # Fill empty positions (any listing type)
                is_cpu_reasonable_deal = is_cpu_to_cpu and player['asking_price'] <= player_market_value * 1.5  # 150% for CPU-to-CPU
                
                # Add improvement bonuses
                if is_improvement:
                    priority_score += 100
                if is_position_fill:
                    priority_score += 200  # Filling empty position is very important
                if is_minor_improvement:
                    priority_score += 50
                
                scored_players.append({
                    'player': player,
                    'priority': priority_score,
                    'position': position,
                    'is_improvement': is_improvement,
                    'is_cpu_to_cpu': is_cpu_to_cpu,
                    'is_reasonable_price': is_reasonable_price,
                    'is_minor_improvement': is_minor_improvement,
                    'is_position_fill': is_position_fill,
                    'is_cpu_reasonable_deal': is_cpu_reasonable_deal,
                    'current_best_overall': current_best_overall,
                    'player_market_value': player_market_value
                })
            
            # Sort by priority (highest first), then by overall rating
            scored_players.sort(key=lambda x: (-x['priority'], -(x['player']['overall'] or 0)))
            
            # Select a player that would improve the team (prioritizing needed positions)
            selected_player = None
            for scored in scored_players:
                player = scored['player']
                position = scored['position']
                is_improvement = scored['is_improvement']
                is_cpu_to_cpu = scored['is_cpu_to_cpu']
                is_reasonable_price = scored['is_reasonable_price']
                is_minor_improvement = scored['is_minor_improvement']
                is_position_fill = scored['is_position_fill']
                is_cpu_reasonable_deal = scored['is_cpu_reasonable_deal']
                player_market_value = scored['player_market_value']

                if is_improvement or (is_cpu_to_cpu and is_reasonable_price) or is_minor_improvement or is_position_fill or is_cpu_reasonable_deal:
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
                        contract_penalty = min(total_overpayment * 0.4, market_value * 0.4)  # Reduced penalty
                        adjusted_min = base_min - contract_penalty
                        adjusted_max = base_max - contract_penalty
                        
                        # For extremely toxic contracts, require compensation (negative asking price)
                        if total_overpayment > market_value * 2:  # If overpayment > 2x market value
                            # Only accept if asking price is negative (user pays CPU to take player)
                            compensation_required = min(total_overpayment * 0.6, market_value * 0.3)
                            adjusted_min = -compensation_required  # Negative = user pays CPU
                            adjusted_max = market_value * 0.1  # Small positive offer as alternative
                    else:
                        # Underpaid player - can pay premium for good contracts
                        contract_bonus = abs(total_overpayment) * 0.3
                        adjusted_min = base_min + contract_bonus
                        adjusted_max = min(base_max + contract_bonus, market_value * 1.2)  # Cap at 120% of market value
                    
                    # Check if asking price is within acceptable range OR is a great deal OR is CPU-to-CPU with lenient criteria
                    is_great_deal = asking_price < market_value * 0.5  # Less than 50% of market value
                    is_acceptable_price = adjusted_min <= asking_price <= adjusted_max
                    is_cpu_to_cpu_reasonable = is_cpu_to_cpu and asking_price <= market_value * 1.5  # More lenient for CPU-to-CPU
                    
                    # Additional CPU-to-CPU criteria for more active trading
                    is_cpu_position_need = is_cpu_to_cpu and str(player['registered_position']) in [str(p) for p in self.get_team_position_needs(team_id)]
                    is_cpu_squad_building = is_cpu_to_cpu and asking_price <= market_value * 1.3 and player_overall >= 70  # Squad building trades

                    if is_acceptable_price or is_great_deal or is_cpu_to_cpu_reasonable or is_cpu_position_need or is_cpu_squad_building:
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
            
            # Check squad size - don't make offers if at maximum capacity (32 players)
            total_players = analysis['total_players']
            if total_players >= 32:
                print(f"Team {team_id} has {total_players} players (max capacity) - skipping user offers")
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

    def make_cpu_free_agency_offer(self, team_id: int) -> Optional[Dict]:
        """CPU team makes intelligent offers on free agents based on team needs"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            cur = conn.cursor()

            # Get team analysis to understand needs
            analysis = self.analyze_team_composition(team_id)
            if not analysis:
                return None

            # Check squad size - don't make offers if at maximum capacity (32 players)
            total_players = analysis['total_players']
            if total_players >= 32:
                print(f"Team {team_id} has {total_players} players (max capacity) - skipping free agency")
                return None

            needs = analysis['needs']
            budget = analysis['needs'].budget_available
            needed_positions = self.get_team_position_needs(team_id)

            # Minimum budget check for free agency (need money for signing bonus)
            # Allow teams with at least 1M or teams with negative budget but not too negative (above -50M)
            if budget < 1000000 and budget < -50000000:  # At least 1M or not worse than -50M
                return None

            if not needed_positions:
                return None

            # Get team's current players by position for improvement analysis
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

            # Find available free agents (club_id = 141) in needed positions
            # Exclude players with active OR expired offers (fao.status = 'active' includes expired ones, so we need to check expires_at)
            from datetime import datetime
            current_time = datetime.now().isoformat()
            positions_str = ','.join([f"'{pos}'" for pos in needed_positions])
            cur.execute(f"""
                SELECT p.*, 
                       CASE WHEN fao.player_id IS NOT NULL THEN 1 ELSE 0 END as has_active_offer
                FROM players p
                LEFT JOIN free_agent_offers fao ON p.id = fao.player_id 
                    AND fao.status = 'active'
                    AND fao.expires_at > ?  -- Only consider non-expired offers
                WHERE p.club_id = 141
                AND p.registered_position IN ({positions_str})
                AND p.overall >= 70  -- Only consider decent free agents
                AND fao.player_id IS NULL  -- No active non-expired offers
                ORDER BY p.overall DESC, p.salary ASC
                LIMIT 20
            """, (current_time,))

            free_agents = cur.fetchall()
            if not free_agents:
                return None

            # Intelligently evaluate free agents
            agent_candidates = []
            for agent in free_agents:
                player_position = agent['registered_position']
                player_overall = agent['overall']
                player_age = agent['age']
                current_salary = agent['salary']
                
                # Calculate interest score
                interest_score = 0
                
                # Position need bonus (highest priority)
                if player_position in needed_positions:
                    interest_score += 60
                
                # Improvement bonus
                if player_position in position_analysis:
                    best_in_position = position_analysis[player_position]['best']
                    avg_in_position = position_analysis[player_position]['average']
                    
                    if player_overall > best_in_position:
                        interest_score += 40  # Better than current best
                    elif player_overall > (avg_in_position + 5):
                        interest_score += 30  # Significantly better than average
                    elif player_overall > avg_in_position:
                        interest_score += 20  # Better than average
                else:
                    # No player in this position - any decent player is valuable
                    interest_score += 50
                
                # Age bonus (free agency good for experienced players)
                if player_age <= 25:
                    interest_score += 20  # Young talent
                elif player_age <= 28:
                    interest_score += 15  # Prime age
                elif player_age <= 31:
                    interest_score += 10  # Still good
                elif player_age <= 34:
                    interest_score += 5   # Experienced
                # No bonus for very old players
                
                # Overall rating bonus
                if player_overall >= 85:
                    interest_score += 25  # Excellent player
                elif player_overall >= 80:
                    interest_score += 20  # Very good player
                elif player_overall >= 75:
                    interest_score += 15  # Good player
                elif player_overall >= 70:
                    interest_score += 10  # Decent player
                
                # Salary consideration (lower salary = more attractive)
                if current_salary < 2000000:  # Less than 2M
                    interest_score += 15
                elif current_salary < 5000000:  # Less than 5M
                    interest_score += 10
                elif current_salary < 10000000:  # Less than 10M
                    interest_score += 5
                # Penalty for very expensive players
                elif current_salary > 20000000:
                    interest_score -= 10
                
                # Only consider players with meaningful interest
                if interest_score >= 40:  # Minimum threshold
                    agent_candidates.append({
                        'agent': agent,
                        'score': interest_score,
                        'reason': 'position_needed' if player_position in needed_positions else 'improvement'
                    })

            if not agent_candidates:
                return None

            # Sort by interest score and select the best candidate
            agent_candidates.sort(key=lambda x: x['score'], reverse=True)
            
            # Add some randomness - pick from top 3 candidates
            top_candidates = agent_candidates[:3]
            selected_candidate = random.choice(top_candidates)
            selected_agent = selected_candidate['agent']
            
            # Calculate competitive offer
            base_salary = selected_agent['salary']
            player_age = selected_agent['age']
            
            # First bid must match player's salary demand exactly (100%)
            offered_salary = int(base_salary)  # Exact match, no variation
            
            # Contract years based on age
            if player_age <= 25:
                contract_years = random.choice([3, 4, 5])  # Longer for young players
            elif player_age <= 30:
                contract_years = random.choice([2, 3, 4])  # Medium for prime
            else:
                contract_years = random.choice([1, 2, 3])  # Shorter for older
            
            # Create the free agency offer
            from datetime import datetime, timedelta
            expires_at = datetime.now() + timedelta(minutes=5)  # 5 minutes like user offers
            
            # Create the offer
            cur.execute("""
                INSERT INTO free_agent_offers (player_id, user_id, offered_salary, offered_contract_years, expires_at, team_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (selected_agent['id'], 1, offered_salary, contract_years, expires_at.isoformat(), team_id))  # user_id = 1 for CPU
            
            # Do not update players.salary on CPU offer creation; keep as free-agency basis
            
            # Get team name
            cur.execute("SELECT club_name FROM teams WHERE id = ?", (team_id,))
            team_result = cur.fetchone()
            team_name = team_result['club_name'] if team_result else f"Team {team_id}"
            
            conn.commit()
            conn.close()
            
            print(f"Team {team_id} ({team_name}) made free agency offer: {selected_agent['player_name']} (Pos {selected_agent['registered_position']}, {selected_agent['overall']} OVR) - €{offered_salary:,}/year for {contract_years} years - Score: {selected_candidate['score']} ({selected_candidate['reason']})")
            
            return {
                'action': 'free_agency_offer',
                'team': team_name,
                'details': {
                    'player_name': selected_agent['player_name'],
                    'offered_salary': offered_salary,
                    'contract_years': contract_years,
                    'player_id': selected_agent['id'],
                    'cpu_team_id': team_id
                }
            }

        except Exception as e:
            print(f"Error making CPU free agency offer: {e}")
            return None

    def raise_cpu_free_agency_offer(self, team_id: int) -> Optional[Dict]:
        """CPU team raises an existing free agency offer to compete with other bidders"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            cur = conn.cursor()

            # Get team analysis to check budget
            analysis = self.analyze_team_composition(team_id)
            if not analysis:
                return None

            budget = analysis['needs'].budget_available
            
            # Find active offers from users; filter expiration in Python to avoid format mismatches
            from datetime import datetime
            cur.execute("""
                SELECT fao.*, p.*
                FROM free_agent_offers fao
                JOIN players p ON fao.player_id = p.id
                WHERE fao.status = 'active'
                AND p.overall >= 75
                ORDER BY p.overall DESC, fao.offered_salary ASC
                LIMIT 50
            """)
            
            competing_offers = cur.fetchall()
            if not competing_offers:
                return None

            # Check team needs, but do not bail out entirely if empty; we may still raise for elite players
            needed_positions = self.get_team_position_needs(team_id)

            # Find offers for players in positions we need
            target_offers = []
            now = datetime.now()
            for offer in competing_offers:
                # Skip expired in Python
                try:
                    if offer['expires_at'] and datetime.fromisoformat(str(offer['expires_at']).replace('Z', '+00:00')) <= now:
                        continue
                except Exception:
                    # If parsing fails, keep it (safer to consider than to drop incorrectly)
                    pass
                # Skip raising our own existing CPU offer from the same team
                if offer.get('user_id') == 1 and offer.get('team_id') and int(offer['team_id']) == int(team_id):
                    continue

                if offer['registered_position'] in needed_positions:
                    # Exact raise amount: €250,000 as specified
                    raise_amount = 250000
                    new_salary = offer['offered_salary'] + raise_amount
                    
                    # Check if we can afford it (including signing bonus estimate)
                    estimated_signing_bonus = int(new_salary * 0.4)  # Estimate 40% signing bonus
                    total_cost = estimated_signing_bonus
                    
                    if budget >= total_cost and new_salary <= offer['salary'] * 1.5:  # Don't go crazy with offers
                        target_offers.append({
                            'offer': offer,
                            'new_salary': new_salary,
                            'raise_amount': raise_amount
                        })

            if not target_offers:
                return None

            # Pick the best target offer (highest overall player we can afford)
            target_offers.sort(key=lambda x: x['offer']['overall'], reverse=True)
            selected_target = target_offers[0]
            
            offer_to_raise = selected_target['offer']
            new_salary = selected_target['new_salary']
            
            # Raise the offer by resetting timer to 5 minutes (same as user raises)
            from datetime import datetime, timedelta
            new_expires_at = datetime.now() + timedelta(minutes=5)
            
            # Update the offer
            cur.execute("""
                UPDATE free_agent_offers
                SET user_id = ?, offered_salary = ?, expires_at = ?
                WHERE id = ?
            """, (1, new_salary, new_expires_at.isoformat(), offer_to_raise['id']))  # user_id = 1 for CPU
            
            # Do not update players.salary on CPU raises; keep as free-agency basis
            
            # Get team name
            cur.execute("SELECT club_name FROM teams WHERE id = ?", (team_id,))
            team_result = cur.fetchone()
            team_name = team_result['club_name'] if team_result else f"Team {team_id}"
            
            conn.commit()
            conn.close()
            
            print(f"Team {team_id} ({team_name}) raised free agency offer: {offer_to_raise['player_name']} (Pos {offer_to_raise['registered_position']}, {offer_to_raise['overall']} OVR) - €{new_salary:,}/year (+€{selected_target['raise_amount']:,})")
            
            return {
                'action': 'raise_free_agency_offer',
                'team': team_name,
                'details': {
                    'player_name': offer_to_raise['player_name'],
                    'old_salary': offer_to_raise['offered_salary'],
                    'new_salary': new_salary,
                    'raise_amount': selected_target['raise_amount'],
                    'player_id': offer_to_raise['player_id'],
                    'cpu_team_id': team_id
                }
            }

        except Exception as e:
            print(f"Error raising CPU free agency offer: {e}")
            return None

    def raise_cpu_free_agency_offer_aggressive(self, team_id: int) -> Optional[Dict]:
        """Aggressively scan ALL user offers and raise the best ones for team needs"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            cur = conn.cursor()

            # Get team analysis to check budget and needs
            analysis = self.analyze_team_composition(team_id)
            if not analysis:
                return None

            budget = analysis['needs'].budget_available
            needed_positions = self.get_team_position_needs(team_id)
            
            # Check squad size - don't make offers if at maximum capacity
            total_players = analysis['total_players']
            if total_players >= 32:
                return None
            
            # Find ALL active user offers (more comprehensive scan)
            from datetime import datetime
            cur.execute("""
                SELECT fao.*, p.*
                FROM free_agent_offers fao
                JOIN players p ON fao.player_id = p.id
                WHERE fao.status = 'active'
                AND p.overall >= 70
                ORDER BY p.overall DESC, fao.offered_salary ASC
                LIMIT 100
            """)
            
            all_user_offers = cur.fetchall()
            if not all_user_offers:
                return None

            # Evaluate ALL offers with more aggressive criteria
            target_offers = []
            
            now = datetime.now()
            for offer in all_user_offers:
                # Skip expired in Python to avoid format issues
                try:
                    if offer['expires_at'] and datetime.fromisoformat(str(offer['expires_at']).replace('Z', '+00:00')) <= now:
                        continue
                except Exception:
                    pass
                # Skip raising our own CPU offer from the same team
                try:
                    if offer.get('user_id') == 1 and offer.get('team_id') and int(offer['team_id']) == int(team_id):
                        continue
                except Exception:
                    pass

                player_position = offer['registered_position']
                player_overall = offer['overall']
                player_age = offer['age']
                current_offer = offer['offered_salary']
                
                # Calculate market value
                estimated_value = self.calculate_free_agent_market_value(dict(offer))
                
                # Calculate fair salary to check if offer is reasonable
                fair_salary = self.calculate_fair_salary(dict(offer))
                
                # Check if the OFFERED salary is toxic (not the player's current salary)
                toxic_threshold = fair_salary * 1.2
                is_toxic = current_offer > toxic_threshold
                overpayment = current_offer - fair_salary if is_toxic else 0
                
                # More aggressive interest scoring
                interest_score = 0
                
                # Position need bonus (HIGHER priority)
                if player_position in needed_positions:
                    interest_score += 120  # Increased from 100
                else:
                    # Still interested in quality players for squad depth
                    if player_overall >= 80:
                        interest_score += 40  # Increased from 20
                    else:
                        interest_score += 15
                
                # Quality bonus (MORE generous)
                if player_overall >= 85:
                    interest_score += 60  # Increased from 50
                elif player_overall >= 80:
                    interest_score += 45  # Increased from 35
                elif player_overall >= 75:
                    interest_score += 30  # Increased from 20
                elif player_overall >= 70:
                    interest_score += 15  # New tier
                
                # Salary reasonableness check (CRITICAL for smart decisions)
                salary_ratio = current_offer / fair_salary if fair_salary > 0 else 0
                if is_toxic:
                    # Heavily penalize toxic contracts
                    if salary_ratio > 3.0:  # More than 3x fair salary
                        interest_score -= 100  # Massive penalty
                    elif salary_ratio > 2.0:  # More than 2x fair salary
                        interest_score -= 60   # Heavy penalty
                    elif salary_ratio > 1.5:  # More than 1.5x fair salary
                        interest_score -= 30   # Moderate penalty
                else:
                    # Reward reasonable salaries
                    if salary_ratio <= 0.8:  # Below fair salary
                        interest_score += 40   # Great deal
                    elif salary_ratio <= 1.0:  # At fair salary
                        interest_score += 20   # Good deal
                    elif salary_ratio <= 1.2:  # Slightly above fair
                        interest_score += 10   # Acceptable
                
                # Value opportunity bonus (based on market value)
                value_ratio = current_offer / (estimated_value * 0.1) if estimated_value > 0 else 0
                if value_ratio < 0.6:  # Great deal
                    interest_score += 30  # Reduced since we have salary check now
                elif value_ratio < 0.8:
                    interest_score += 20  # Reduced
                elif value_ratio < 1.0:
                    interest_score += 10  # Reduced
                elif value_ratio < 1.5:  # Still reasonable
                    interest_score += 5   # Reduced
                
                # Age bonus (more generous)
                if player_age <= 23:
                    interest_score += 20  # Increased from 15
                elif player_age <= 26:
                    interest_score += 15  # Increased from 10
                elif player_age <= 29:
                    interest_score += 10  # New tier
                
                # Exact raise amount: €250,000 as specified (not percentage-based)
                raise_amount = 250000
                new_salary = current_offer + raise_amount
                
                # More generous affordability (AGGRESSIVE criteria)
                estimated_signing_bonus = int(new_salary * 0.4)
                
                # Much more generous salary limits
                if interest_score >= 120:  # Position needed + quality
                    max_affordable_salary = max(estimated_value * 0.35, current_offer * 2.0)  # Very aggressive
                elif interest_score >= 100:  # High interest
                    max_affordable_salary = max(estimated_value * 0.30, current_offer * 1.8)
                elif interest_score >= 80:  # Medium-high interest
                    max_affordable_salary = max(estimated_value * 0.25, current_offer * 1.6)
                else:  # Lower interest
                    max_affordable_salary = max(estimated_value * 0.20, current_offer * 1.4)
                
                # Debug logging for salary analysis
                if player_overall >= 75:  # Only log for decent players
                    print(f"  📊 Salary Analysis: {offer['player_name']} (Pos {player_position}, {player_overall} OVR)")
                    print(f"     Current offer: €{current_offer:,}, Fair salary: €{fair_salary:,} (ratio: {salary_ratio:.2f})")
                    print(f"     Toxic: {is_toxic}, Interest score: {interest_score}")
                
                # Lower minimum threshold for aggressive scanning - be more lenient
                # Also allow negative budgets if the offer is good enough
                budget_ok = budget >= estimated_signing_bonus or (budget < 0 and budget >= -estimated_signing_bonus * 2)
                
                if (budget_ok and 
                    new_salary <= max_affordable_salary and 
                    interest_score >= 25):  # Even lower threshold (was 30)
                    
                    target_offers.append({
                        'offer': offer,
                        'new_salary': new_salary,
                        'raise_amount': raise_amount,
                        'interest_score': interest_score,
                        'estimated_value': estimated_value,
                        'value_ratio': value_ratio
                    })

            if not target_offers:
                # Debug: Log why no offers were suitable
                print(f"  ⚠️  Team {team_id}: No suitable offers to raise")
                print(f"     - Scanned {len(all_user_offers)} user offers")
                print(f"     - Budget: €{budget:,}, Needed positions: {needed_positions}")
                return None  # No suitable offers to raise

            # Sort by interest score and pick the BEST opportunity
            target_offers.sort(key=lambda x: x['interest_score'], reverse=True)
            
            # Take the absolute best offer (no randomness for aggressive mode)
            selected_target = target_offers[0]
            
            offer_to_raise = selected_target['offer']
            new_salary = selected_target['new_salary']
            
            # Raise the offer by resetting timer to 5 minutes
            from datetime import datetime, timedelta
            new_expires_at = datetime.now() + timedelta(minutes=5)
            
            # Update the offer
            cur.execute("""
                UPDATE free_agent_offers
                SET user_id = ?, offered_salary = ?, expires_at = ?
                WHERE id = ?
            """, (1, new_salary, new_expires_at.isoformat(), offer_to_raise['id']))
            
            # Do not update players.salary on CPU aggressive raises; keep as free-agency basis
            
            # Get team name
            cur.execute("SELECT club_name FROM teams WHERE id = ?", (team_id,))
            team_result = cur.fetchone()
            team_name = team_result['club_name'] if team_result else f"Team {team_id}"
            
            conn.commit()
            conn.close()
            
            print(f"🎯 AGGRESSIVE: {team_name} outbid for {offer_to_raise['player_name']} (Pos {offer_to_raise['registered_position']}, {offer_to_raise['overall']} OVR)")
            print(f"  💰 €{offer_to_raise['offered_salary']:,} → €{new_salary:,} (+€{selected_target['raise_amount']:,})")
            print(f"  📊 Interest: {selected_target['interest_score']}, Est. Value: €{selected_target['estimated_value']:,}")
            
            return {
                'action': 'raise_free_agency_offer',
                'team': team_name,
                'details': {
                    'player_name': offer_to_raise['player_name'],
                    'old_salary': offer_to_raise['offered_salary'],
                    'new_salary': new_salary,
                    'raise_amount': selected_target['raise_amount'],
                    'player_id': offer_to_raise['player_id'],
                    'cpu_team_id': team_id,
                    'interest_score': selected_target['interest_score'],
                    'estimated_value': selected_target['estimated_value']
                }
            }

        except Exception as e:
            print(f"Error in aggressive CPU free agency raise: {e}")
            return None

    def calculate_free_agent_market_value(self, player_data):
        """Calculate market value for free agents using the game's sophisticated system"""
        try:
            from game_mechanics import calculate_player_market_value_only
            
            # Create a copy to avoid modifying original
            temp_player_data = dict(player_data)
            
            # Temporarily set club_id to get true market value
            original_club_id = temp_player_data.get('club_id')
            temp_player_data['club_id'] = 1
            
            # Calculate market value
            market_value = calculate_player_market_value_only(temp_player_data)
            
            # Restore original club_id
            temp_player_data['club_id'] = original_club_id
            
            return market_value
            
        except Exception as e:
            # Fallback calculation
            overall = player_data.get('overall', 50)
            age = player_data.get('age', 25)
            
            if overall >= 85:
                base_value = 30000000
            elif overall >= 80:
                base_value = 20000000
            elif overall >= 75:
                base_value = 12000000
            else:
                base_value = 6000000
            
            # Age adjustment
            if age <= 25:
                age_multiplier = 1.2
            elif age <= 30:
                age_multiplier = 1.0
            else:
                age_multiplier = 0.8
            
            return int(base_value * age_multiplier)

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
            
            # Check squad size - don't make offers if at maximum capacity (32 players)
            total_players = analysis['total_players']
            if total_players >= 32:
                print(f"Team {team_id} has {total_players} players (max capacity) - skipping market offers")
                return None

            needs = analysis['needs']
            budget = analysis['needs'].budget_available
            
            # Get needed positions
            needed_positions = self.get_team_position_needs(team_id)
            
            if not needed_positions or budget < 1000000:  # Minimum budget for offers
                return None
            
            # Find suitable players in market bazaar (only CPU listings, exclude user listings to avoid errors)
            # Exclude blacklisted players
            cur.execute("""
                SELECT mbl.*, p.player_name, p.market_value, p.registered_position, p.overall, mbl.listing_type,
                       p.salary, p.contract_years_remaining, p.age, t.club_name as seller_team_name
                FROM market_bazaar_listings mbl
                JOIN players p ON mbl.player_id = p.id
                JOIN teams t ON mbl.team_id = t.id
                WHERE mbl.status = 'active'
                AND mbl.listing_type IN ('cpu_sale', 'cpu_loan')  -- Only CPU listings (exclude user_sale to avoid errors)
                AND p.registered_position IN ({})
                AND mbl.asking_price <= ?
                AND mbl.team_id != ?
                AND p.id NOT IN (
                    SELECT player_id FROM blacklist WHERE user_id = 1
                )
                ORDER BY p.overall DESC, mbl.asking_price ASC
                LIMIT 50
            """.format(','.join(map(str, needed_positions))), (budget * 1.2, team_id))
            
            available_players = cur.fetchall()
            
            if not available_players:
                return None
            
            # Smart evaluation of all available players using sophisticated contract analysis
            evaluated_players = []
            
            for player in available_players:
                asking_price = player['asking_price']
                market_value = player['market_value'] or 1000000
                current_salary = player['salary'] or 0
                contract_years = player['contract_years_remaining'] or 1
                player_overall = player['overall'] or 0
                player_age = player['age'] or 25
                position = str(player['registered_position'])
                is_user_listed = player['listing_type'] == 'user_sale'
                
                # Get current best player in this position on the CPU team
                cur.execute("""
                    SELECT MAX(overall) as best_overall, COUNT(*) as position_count
                    FROM players
                    WHERE club_id = ? AND registered_position = ?
                """, (team_id, position))
                
                current_best_result = cur.fetchone()
                current_best_overall = current_best_result['best_overall'] if current_best_result and current_best_result['best_overall'] else 0
                position_count = current_best_result['position_count'] if current_best_result else 0
                
                # Calculate fair salary using game mechanics
                fair_salary = self.calculate_fair_salary(dict(player))
                salary_difference = current_salary - fair_salary
                total_overpayment = salary_difference * contract_years
                
                # Base maximum acceptable price (market value)
                base_max = market_value
                
                # Initialize adjusted_max with base value
                adjusted_max = base_max
                
                # Adjust for player age (development potential)
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
                    adjusted_max -= age_penalty
                else:
                    # Prime age players (25-30) - no adjustment
                    pass
                
                # Apply age bonus to maximum price
                adjusted_max += age_bonus
                
                # Adjust for contract situation
                if salary_difference > 0:
                    # Overpaid player - reduce maximum price (less willing to pay)
                    contract_penalty = min(total_overpayment * 0.1, market_value * 0.2)
                    adjusted_max -= contract_penalty
                    
                    # For extremely toxic contracts, require compensation
                    if total_overpayment > market_value * 3:  # Only for very toxic contracts
                        compensation_required = min(total_overpayment * 0.1, market_value * 0.2)
                        adjusted_max = -compensation_required
                else:
                    # Underpaid player - increase maximum price (more willing to pay)
                    contract_bonus = abs(total_overpayment) * 0.2
                    adjusted_max += contract_bonus
                
                # CRITICAL: Adjust price based on how good the CPU's current player is (CORRECTED LOGIC)
                if current_best_overall > 0:
                    # If CPU has a worse player in this position, willing to pay premium
                    if current_best_overall < player_overall - 5:
                        # CPU's player is significantly worse - willing to pay premium
                        premium_multiplier = 1.2 + (player_overall - current_best_overall - 5) * 0.05
                        adjusted_max *= premium_multiplier
                    elif current_best_overall <= player_overall:
                        # CPU's player is as good or worse - small premium
                        premium_multiplier = 1.1 + (player_overall - current_best_overall) * 0.02
                        adjusted_max *= premium_multiplier
                    elif current_best_overall <= player_overall + 3:
                        # CPU's player is close in quality - no premium
                        pass  # No adjustment
                    else:
                        # CPU's player is significantly better - small discount
                        discount_multiplier = 0.95 + (current_best_overall - player_overall - 3) * 0.01
                        adjusted_max *= discount_multiplier
                
                # Calculate deal quality score
                deal_score = 0
                
                # Price evaluation (inverted from selling logic)
                if asking_price < market_value * 0.5:
                    deal_score += 100  # Excellent deal (less than 50% of market value)
                elif asking_price < market_value * 0.7:
                    deal_score += 80   # Great deal (less than 70% of market value)
                elif asking_price < market_value * 0.9:
                    deal_score += 60   # Good deal (less than 90% of market value)
                elif asking_price <= market_value * 1.1:
                    deal_score += 40   # Fair deal (within 110% of market value)
                elif asking_price <= market_value * 1.3:
                    deal_score += 20   # Acceptable deal (within 130% of market value)
                else:
                    deal_score += 0    # Poor deal
                
                # Contract evaluation
                if salary_difference < 0:
                    deal_score += 30   # Bonus for underpaid players
                elif salary_difference > market_value * 0.1:
                    deal_score -= 50   # Penalty for overpaid players
                
                # User listing bonus (users often offer better deals)
                if is_user_listed:
                    deal_score += 25
                
                # Loan listing bonus (loans are lower risk)
                if player['listing_type'] == 'cpu_loan':
                    deal_score += 15
                
                # Overall rating bonus
                if player_overall >= 85:
                    deal_score += 20
                elif player_overall >= 80:
                    deal_score += 15
                elif player_overall >= 75:
                    deal_score += 10
                
                # Age bonus (younger players are more valuable)
                if player_age <= 23:
                    deal_score += 15
                elif player_age <= 26:
                    deal_score += 10
                elif player_age <= 29:
                    deal_score += 5
                elif player_age >= 32:
                    deal_score -= 10
                
                # Check if deal is acceptable (CPU willing to buy at this price)
                is_great_deal = asking_price < market_value * 0.5
                is_acceptable_price = asking_price <= adjusted_max
                is_reasonable_deal = asking_price <= market_value * 1.3
                
                if is_acceptable_price or is_great_deal or is_reasonable_deal:
                    evaluated_players.append({
                        'player': player,
                        'deal_score': deal_score,
                        'asking_price': asking_price,
                        'market_value': market_value,
                        'is_great_deal': is_great_deal,
                        'is_user_listed': is_user_listed,
                        'adjusted_max': adjusted_max
                    })
            
            if not evaluated_players:
                return None
            
            # Sort by deal score (best deals first)
            evaluated_players.sort(key=lambda x: x['deal_score'], reverse=True)
            
            # Select from top deals with weighted probability
            # 60% chance to pick from top 3 deals, 30% from top 5, 10% from top 10
            selection_choice = random.random()
            if selection_choice < 0.6 and len(evaluated_players) >= 3:
                selected_evaluation = random.choice(evaluated_players[:3])
            elif selection_choice < 0.9 and len(evaluated_players) >= 5:
                selected_evaluation = random.choice(evaluated_players[:5])
            else:
                selected_evaluation = random.choice(evaluated_players[:min(10, len(evaluated_players))])
            
            selected_listing = selected_evaluation['player']
            
            # Smart offer calculation based on deal quality
            asking_price = selected_listing['asking_price']
            market_value = selected_evaluation['market_value']
            is_great_deal = selected_evaluation['is_great_deal']
            is_user_listed = selected_evaluation['is_user_listed']
            adjusted_max = selected_evaluation['adjusted_max']
            
            # Calculate offer based on deal quality
            if is_great_deal:
                # For great deals (less than 50% of market value), offer full asking price
                offered_price = asking_price
            elif asking_price < market_value * 0.7:
                # For good deals (less than 70% of market value), 90% chance of full price
                if random.random() < 0.9:
                    offered_price = asking_price
                else:
                    offered_price = int(asking_price * 0.95)
            elif asking_price < market_value * 0.9:
                # For fair deals, 70% chance of full price
                if random.random() < 0.7:
                    offered_price = asking_price
                else:
                    offered_price = int(asking_price * 0.92)
            elif is_user_listed:
                # For user-listed players, be more generous (users often offer better deals)
                if random.random() < 0.6:
                    offered_price = asking_price
                else:
                    offered_price = int(asking_price * 0.88)
            else:
                # For other deals, standard offer range
                if random.random() < 0.4:
                    offered_price = asking_price
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
                
                # Update budgets - handle user teams vs CPU teams differently
                seller_team_id = selected_listing['team_id']
                
                # Check if seller is a user team (unified budget system)
                cur.execute("SELECT user_id FROM league_teams WHERE id = ?", (seller_team_id,))
                seller_team_info = cur.fetchone()
                
                if seller_team_info and seller_team_info['user_id'] != 1:  # User team
                    # Use unified budget system for user teams
                    # First get current budget and update it
                    cur.execute("SELECT budget FROM user_budgets WHERE user_id = ?", (seller_team_info['user_id'],))
                    current_budget_result = cur.fetchone()
                    current_budget = current_budget_result['budget'] if current_budget_result else 450000000
                    new_budget = current_budget + offered_price
                    
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
                          f"Sold {selected_listing['player_name']} to {buyer_team['club_name']}",
                          offered_price, new_budget))
                    
                    # Send inbox message directly to database
                    cur.execute("SELECT username, email FROM users WHERE id = ?", (seller_team_info['user_id'],))
                    user_info = cur.fetchone()
                    if user_info:
                        subject = f"Player Sale: {selected_listing['player_name']}"
                        message = f"Your player {selected_listing['player_name']} has been sold to {buyer_team['club_name']} for €{offered_price:,}."
                        cur.execute("""
                            INSERT INTO messages (sender_id, receiver_id, subject, content, created_at)
                            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """, (1, seller_team_info['user_id'], subject, message))
                else:
                    # CPU team - update teams table budget
                    cur.execute("UPDATE teams SET budget = budget + ? WHERE id = ?", 
                               (offered_price, seller_team_id))
            
                # Buyer (CPU team) pays from teams table budget
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
                
                # Get current best player in this position on the CPU team (including the player being sold)
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
                    # If the player being sold is the best in their position, demand premium
                    if current_best_overall == player_overall:
                        # Player being sold IS the best player - demand premium
                        premium_multiplier = 1.3  # 30% premium for best player
                        adjusted_min *= premium_multiplier
                    elif current_best_overall > player_overall + 5:
                        # CPU has significantly better player - demand premium
                        premium_multiplier = 1.2 + (current_best_overall - player_overall - 5) * 0.05
                        adjusted_min *= premium_multiplier
                    elif current_best_overall > player_overall:
                        # CPU has better player - small premium
                        premium_multiplier = 1.1 + (current_best_overall - player_overall) * 0.02
                        adjusted_min *= premium_multiplier
                    elif current_best_overall >= player_overall - 3:
                        # CPU player is close in quality - no premium
                        pass  # No adjustment
                    else:
                        # CPU player is significantly worse - small discount
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
                    
                    # Get current unified budget: prefer cached snapshot, fallback to base+movements
                    cur.execute("SELECT budget FROM user_budgets WHERE user_id = ?", (actual_user_id,))
                    ub = cur.fetchone()
                    if ub and ub['budget'] is not None:
                        current_budget = ub['budget']
                    else:
                        cur.execute("SELECT COALESCE(SUM(amount), 0) as total_movements FROM user_movements WHERE user_id = ?", (actual_user_id,))
                        movements_result = cur.fetchone()
                        total_movements = movements_result['total_movements'] if movements_result else 0
                        current_budget = 450000000 + total_movements
                    new_budget = current_budget - offered_price

                    # Update user budget
                    cur.execute("""
                        INSERT OR REPLACE INTO user_budgets (user_id, budget, updated_at)
                        VALUES (?, ?, ?)
                    """, (actual_user_id, new_budget, datetime.now().isoformat()))
                    
                    # Add movement record
                    cur.execute("""
                        INSERT INTO user_movements (user_id, type, description, amount, balance_after)
                        VALUES (?, ?, ?, ?, ?)
                    """, (actual_user_id, 'CPU Purchase', 
                          f"Bought {current_player_data['player_name']} from {best_offer['cpu_team_name']}", 
                          -offered_price, new_budget))
                    
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
                
                # Random chance for CPU actions (40% chance per team - increased to be more active)
                if random.random() < 0.4:
                    # CPU actions: prioritize buying/loaning existing listings, then make offers
                    action_choice = random.random()
                    if action_choice < 0.4:  # 40% chance to buy existing listings
                        buy_result = self.buy_listed_player(team_id)
                        if buy_result:
                            actions_taken.append({
                                'team': team_name,
                                'action': 'buy_player',
                                'details': buy_result['details']
                            })
                    elif action_choice < 0.6:  # 20% chance to loan existing loan listings
                        loan_result = self.make_cpu_loan_offer(team_id)
                        if loan_result:
                            actions_taken.append({
                                'team': team_name,
                                'action': 'loan_player',
                                'details': loan_result['details']
                            })
                    elif action_choice < 0.85:  # 25% chance for free agency activity (combined)
                        # TWO-PHASE FREE AGENCY APPROACH
                        # Phase 1: Try to raise existing offers (prioritized)
                        raise_offer_result = self.raise_cpu_free_agency_offer_aggressive(team_id)
                        if raise_offer_result and 'details' in raise_offer_result:
                            # Successfully raised an offer
                            actions_taken.append({
                                'team': team_name,
                                'action': 'raise_free_agency_offer',
                                'details': raise_offer_result['details']
                            })
                        
                        # PHASE 2: Also make new offers (both raises and new offers can happen)
                        # This allows teams to raise existing offers AND make new offers for different players
                        analysis = self.analyze_team_composition(team_id)
                        if analysis and analysis['total_players'] < 32:
                            free_agency_result = self.make_cpu_free_agency_offer(team_id)
                            if free_agency_result:
                                actions_taken.append({
                                    'team': team_name,
                                    'action': 'free_agency_offer',
                                    'details': free_agency_result['details']
                                })
                    elif action_choice < 0.9:  # 5% chance to make market bazaar offers
                        market_offer_result = self.make_cpu_market_bazaar_offer(team_id)
                        if market_offer_result:
                            actions_taken.append({
                                'team': team_name,
                                'action': market_offer_result['action'],
                                'details': market_offer_result['details']
                            })
                    else:  # 10% chance to make offer for USER players
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
                
                # Lower chance for listing (15% per team) to avoid market flooding
                if random.random() < 0.20:
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

            # Calculate action type statistics
            action_counts = {}
            for action in actions_taken:
                action_type = action.get('action', 'unknown')
                action_counts[action_type] = action_counts.get(action_type, 0) + 1
            
            total_actions = len(actions_taken)
            action_percentages = {}
            if total_actions > 0:
                for action_type, count in action_counts.items():
                    action_percentages[action_type] = round((count / total_actions) * 100, 1)
            
            # Print action distribution
            print("\n" + "="*60)
            print("CPU AI ACTION DISTRIBUTION:")
            print("="*60)
            print(f"Total teams processed: {len(cpu_teams)}")
            print(f"Total actions taken: {total_actions}")
            print(f"\nAction breakdown:")
            print(f"  - 40% base chance per team to take any action")
            print(f"  - Of actions taken:")
            print(f"    • Buy existing listings: ~40% of actions")
            print(f"    • Loan existing listings: ~20% of actions")
            print(f"    • Free agency (raise/new): ~25% of actions")
            print(f"    • Market bazaar offers: ~5% of actions")
            print(f"    • User player offers (unlisted): ~10% of actions")
            print(f"  - Phase 2: 20% chance per team to create listings")
            print(f"    • List for sale: ~90% of listings")
            print(f"    • List for loan: ~10% of listings")
            if action_percentages:
                print(f"\nActual action distribution this run:")
                for action_type, percentage in sorted(action_percentages.items(), key=lambda x: x[1], reverse=True):
                    print(f"  • {action_type}: {percentage}% ({action_counts[action_type]} actions)")
            print("="*60 + "\n")
            
            return {
                'success': True,
                'actions_taken': actions_taken,
                'total_teams_processed': len(cpu_teams),
                'actions_count': len(actions_taken),
                'action_percentages': action_percentages,
                'action_counts': action_counts
            }
            
        except Exception as e:
            print(f"Error processing CPU AI actions: {e}")
            return {'success': False, 'error': str(e)}

# Global instance for easy access
cpu_ai = CPUAI()
