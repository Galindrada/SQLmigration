#!/usr/bin/env python3
"""
CPU League Simulation System
Handles league management, match simulation, and statistics tracking for CPU teams.
"""

import sqlite3
import random
import math
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

class LeagueStatus(Enum):
    NOT_STARTED = "not_started"
    ROUND_ROBIN = "round_robin"
    PLAYOFFS = "playoffs"
    COMPLETED = "completed"

@dataclass
class Team:
    id: int
    name: str
    division: int
    wins: int = 0
    losses: int = 0
    draws: int = 0
    goals_for: int = 0
    goals_against: int = 0
    points: int = 0
    players: List[Dict] = None
    
    def __post_init__(self):
        if self.players is None:
            self.players = []
    
    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against
    
    @property
    def games_played(self) -> int:
        return self.wins + self.losses + self.draws

@dataclass
class Match:
    home_team: Team
    away_team: Team
    home_score: int = 0
    away_score: int = 0
    played: bool = False
    match_id: Optional[int] = None
    home_scorers: List[Dict] = None
    away_scorers: List[Dict] = None
    round_number: int = 0
    
    def __post_init__(self):
        if self.home_scorers is None:
            self.home_scorers = []
        if self.away_scorers is None:
            self.away_scorers = []

@dataclass
class PlayoffSeries:
    team1: Team
    team2: Team
    team1_wins: int = 0
    team2_wins: int = 0
    games_played: int = 0
    max_games: int = 7
    stage: str = "semi_final"  # semi_final, final
    completed: bool = False
    winner: Team = None
    games: List[Match] = None
    
    def __post_init__(self):
        if self.games is None:
            self.games = []
    
    @property
    def is_complete(self) -> bool:
        return self.completed or self.games_played >= self.max_games or \
               self.team1_wins >= 4 or self.team2_wins >= 4

class CPULeagueManager:
    def __init__(self, db_path: str = "pes6_league_db.sqlite"):
        self.db_path = db_path
        self.leagues = {}  # division_id -> league data
        self.current_round = 0
        self.max_rounds = 0
        self.league_status = LeagueStatus.NOT_STARTED
        self.top_scorers = {}  # {player_id: {'name': str, 'team': str, 'goals': int}}
        self.top_assists = {}   # {player_id: {'name': str, 'team': str, 'assists': int}}
        self.playoff_teams = []
        self.playoff_series = []  # List of PlayoffSeries objects
        self.playoff_round = 1  # Current playoff round (1=round of 16, 2=quarterfinals, 3=semifinals, 4=final)
        self.total_playoff_games = 0  # Total playoff games played throughout tournament
        self.current_season_id = None
    
    def _get_db_connection(self):
        """Get a database connection with proper settings for concurrent access."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrent access
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=10000")
        conn.execute("PRAGMA temp_store=MEMORY")
        return conn
    
    def _load_team_players(self, team_id: int) -> List[Dict]:
        """Load players for a team on demand."""
        conn = None
        try:
            conn = self._get_db_connection()
            cur = conn.cursor()
            
            cur.execute("""
                SELECT id, player_name, registered_position, game_position, attack, defense, balance, 
                       stamina, top_speed, acceleration, response, agility, 
                       dribble_accuracy, dribble_speed, short_pass_accuracy, 
                       short_pass_speed, long_pass_accuracy, long_pass_speed,
                       shot_accuracy, shot_power, shot_technique, free_kick_accuracy,
                       swerve, heading, jump, technique, aggression, mentality,
                       goal_keeping, team_work, consistency, condition_fitness,
                       games_played, goals, assists
                FROM players 
                WHERE club_id = ?
                ORDER BY RANDOM()
            """, (team_id,))
            
            rows = [dict(player) for player in cur.fetchall()]
            for row in rows:
                row.setdefault('game_position', row.get('registered_position'))
            return rows
            
        except Exception as e:
            print(f"Error loading players for team {team_id}: {e}")
            return []
        finally:
            if conn:
                conn.close()
        
    def initialize_league(self, division_count: int = 4) -> bool:
        """Initialize the CPU league with specified number of divisions."""
        conn = None
        try:
            print(f"🔄 Starting league initialization with {division_count} divisions...")
            conn = self._get_db_connection()
            cur = conn.cursor()
            
            # Create a new season in the database
            from datetime import datetime
            current_year = datetime.now().year
            season_name = f"{current_year}/{current_year + 1}"
            print(f"📅 Creating season: {season_name}")
            
            cur.execute("""
                INSERT INTO cpu_league_seasons (season_name, status, division_count)
                VALUES (?, 'not_started', ?)
            """, (season_name, division_count))
            
            self.current_season_id = cur.lastrowid
            
            # Get CPU teams (user_id = 1), excluding "No Club"
            print("🔍 Fetching CPU teams...")
            cur.execute("""
                SELECT t.id, t.club_name, COUNT(p.id) as player_count
                FROM teams t
                JOIN league_teams lt ON t.club_name = lt.team_name
                LEFT JOIN players p ON t.id = p.club_id
                WHERE lt.user_id = 1 AND t.id != 141
                GROUP BY t.id, t.club_name
                HAVING player_count >= 11
                ORDER BY RANDOM()
            """)
            
            cpu_teams = cur.fetchall()
            print(f"✅ Found {len(cpu_teams)} CPU teams with enough players")
            
            if len(cpu_teams) < division_count * 4:  # Need at least 4 teams per division
                print(f"❌ Not enough teams: {len(cpu_teams)} < {division_count * 4}")
                return False
            
            # Distribute teams evenly across divisions
            teams_per_division = len(cpu_teams) // division_count
            self.leagues = {}
            
            for div in range(1, division_count + 1):
                start_idx = (div - 1) * teams_per_division
                end_idx = start_idx + teams_per_division
                division_teams = cpu_teams[start_idx:end_idx]
                
                teams = []
                for team_data in division_teams:
                    # Create team without loading all players (load them when needed)
                    team = Team(
                        id=team_data['id'],
                        name=team_data['club_name'],
                        division=div,
                        players=[]  # Load players when needed during match simulation
                    )
                    teams.append(team)
                    
                    # Insert team into database
                    cur.execute("""
                        INSERT INTO cpu_league_divisions 
                        (season_id, division_number, team_id, team_name)
                        VALUES (?, ?, ?, ?)
                    """, (self.current_season_id, div, team_data['id'], team_data['club_name']))
                
                self.leagues[div] = {
                    'teams': teams,
                    'rounds': [],
                    'standings': teams.copy(),
                    'current_round': 0,
                    'max_rounds': len(teams) - 1 if len(teams) % 2 == 0 else len(teams)
                }
            
            # Generate round-robin matches for each division (in memory only)
            print("🏟️ Generating match schedules...")
            for div_id, league_data in self.leagues.items():
                self._generate_round_robin_matches(div_id)
            
            # Update season status
            cur.execute("""
                UPDATE cpu_league_seasons 
                SET status = 'round_robin', max_rounds = ?
                WHERE id = ?
            """, (max(league['max_rounds'] for league in self.leagues.values()), self.current_season_id))
            
            self.league_status = LeagueStatus.ROUND_ROBIN
            self.current_round = 0
            self.max_rounds = max(league['max_rounds'] for league in self.leagues.values())
            
            conn.commit()
            print("✅ League structure created successfully")
            
            # Save matches to database in separate transactions
            print("💾 Saving matches to database...")
            for div_id in self.leagues.keys():
                self._save_matches_to_database(div_id)
            
            print("✅ League initialization completed!")
            return True
            
        except Exception as e:
            print(f"Error initializing league: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()
    
    def _generate_round_robin_matches(self, division_id: int):
        """Generate round-robin matches organized by rounds for a division."""
        teams = self.leagues[division_id]['teams']
        num_teams = len(teams)
        
        # Create a proper round-robin schedule
        rounds = []
        
        if num_teams % 2 == 0:
            # Even number of teams
            num_rounds = num_teams - 1
            for round_num in range(num_rounds):
                round_matches = []
                for i in range(num_teams // 2):
                    home_idx = (round_num + i) % (num_teams - 1)
                    away_idx = (num_teams - 1 - i + round_num) % (num_teams - 1)
                    
                    # Handle the "fixed" team (last team)
                    if home_idx == away_idx:
                        home_idx = num_teams - 1
                    
                    match = Match(
                        home_team=teams[home_idx],
                        away_team=teams[away_idx],
                        round_number=round_num + 1
                    )
                    round_matches.append(match)
                rounds.append(round_matches)
        else:
            # Odd number of teams - add a "bye" team
            num_rounds = num_teams
            for round_num in range(num_rounds):
                round_matches = []
                for i in range(num_teams // 2):
                    home_idx = (round_num + i) % num_teams
                    away_idx = (num_teams - 1 - i + round_num) % num_teams
                    
                    if home_idx != away_idx:
                        match = Match(
                            home_team=teams[home_idx],
                            away_team=teams[away_idx],
                            round_number=round_num + 1
                        )
                        round_matches.append(match)
                rounds.append(round_matches)
        
        self.leagues[division_id]['rounds'] = rounds
        self.leagues[division_id]['current_round'] = 0
    
    def simulate_round(self) -> Dict:
        """Simulate one round of matches across all divisions."""
        if self.league_status == LeagueStatus.NOT_STARTED:
            return {"error": "League not initialized"}
        
        if self.league_status == LeagueStatus.COMPLETED:
            return {"error": "League already completed"}
        
        results = {
            "round": self.current_round + 1,
            "matches_played": 0,
            "total_goals": 0,
            "division_results": {}
        }
        
        if self.league_status == LeagueStatus.ROUND_ROBIN:
            # Keep scorer and assist tracking cumulative (don't clear between rounds)
            
            # Simulate round-robin matches
            for div_id, league_data in self.leagues.items():
                div_results = self._simulate_division_round(div_id)
                results["division_results"][div_id] = div_results
                results["matches_played"] += div_results["matches_played"]
                results["total_goals"] += div_results["total_goals"]
            
            self.current_round += 1
            
            # Skip real-time player stats updates - will be done at end of season
            # self._batch_update_player_stats_in_database()
            
            # Check if round-robin is complete
            if self.current_round >= self.max_rounds:
                self._advance_to_playoffs()
                results["league_status"] = "Advanced to playoffs"
            else:
                results["league_status"] = "Round-robin continues"
        
        elif self.league_status == LeagueStatus.PLAYOFFS:
            # Keep scorer and assist tracking cumulative (don't clear)
            
            # Simulate playoff matches
            playoff_results = self._simulate_playoff_round()
            results["playoff_results"] = playoff_results
            results["matches_played"] = playoff_results["matches_played"]
            results["total_goals"] = playoff_results["total_goals"]
            
            # Skip real-time player stats updates - will be done at end of season
            # self._batch_update_player_stats_in_database()
            
            if playoff_results["playoffs_complete"]:
                # Allocate player stats at end of season
                self._allocate_end_of_season_player_stats()
                
                self.league_status = LeagueStatus.COMPLETED
                results["league_status"] = "League completed"
            else:
                results["league_status"] = "Playoffs continue"
        
        return results
    
    def _simulate_division_round(self, division_id: int) -> Dict:
        """Simulate one round of matches for a specific division."""
        league_data = self.leagues[division_id]
        current_round = league_data['current_round']
        rounds = league_data['rounds']
        
        # Check if all rounds are completed
        if current_round >= len(rounds):
            return {"matches_played": 0, "total_goals": 0, "message": "All matches completed"}
        
        # Get matches for current round
        round_matches = rounds[current_round]
        
        # Simulate all matches in this round
        total_goals = 0
        round_scorers = []  # Collect all scorer data for batch processing
        round_assists = []  # Collect all assist data for batch processing
        
        for match in round_matches:
            self._simulate_match(match)
            total_goals += match.home_score + match.away_score
            match.played = True
            
            # Collect scorer data for batch processing
            for scorer in match.home_scorers:
                round_scorers.append({
                    'player_id': scorer['player_id'],
                    'player_name': scorer['player'],
                    'team_name': match.home_team.name,
                    'type': 'goal'
                })
            
            for scorer in match.away_scorers:
                round_scorers.append({
                    'player_id': scorer['player_id'],
                    'player_name': scorer['player'],
                    'team_name': match.away_team.name,
                    'type': 'goal'
                })
            
            # Collect assist data for batch processing
            if hasattr(match, 'assists'):
                for assist in match.assists:
                    round_assists.append({
                        'player_id': assist['player_id'],
                        'player_name': assist['player'],
                        'team_name': assist['team'],
                        'type': 'assist'
                    })
        
        # Update leaderboards in batch
        print(f"📊 Processing {len(round_scorers)} goals and {len(round_assists)} assists for division {division_id}")
        for scorer_data in round_scorers:
            self._update_player_stats(scorer_data['player_id'], scorer_data['player_name'], scorer_data['team_name'], 'goal')
        
        for assist_data in round_assists:
            self._update_player_stats(assist_data['player_id'], assist_data['player_name'], assist_data['team_name'], 'assist')
        
        # Move to next round
        league_data['current_round'] += 1
        
        # Update standings
        self._update_division_standings(division_id)
        
        # Update standings in database
        self._update_division_standings_in_database(division_id)
        
        return {
            "matches_played": len(round_matches),
            "total_goals": total_goals,
            "round": current_round + 1,
            "matches": [
                {
                    "home_team": m.home_team.name,
                    "away_team": m.away_team.name,
                    "home_score": m.home_score,
                    "away_score": m.away_score,
                    "scorers": {
                        "home": [{"player": s["player"], "minute": s["minute"]} for s in m.home_scorers],
                        "away": [{"player": s["player"], "minute": s["minute"]} for s in m.away_scorers]
                    },
                    "home_players_played": getattr(m, 'home_players_played', []),
                    "away_players_played": getattr(m, 'away_players_played', [])
                } for m in round_matches
            ]
        }
    
    def _simulate_match(self, match: Match, is_playoff: bool = False):
        """Simulate a single match between two teams with realistic player selection."""
        home_team = match.home_team
        away_team = match.away_team
        
        # Load players if not already loaded
        if not home_team.players:
            home_team.players = self._load_team_players(home_team.id)
        if not away_team.players:
            away_team.players = self._load_team_players(away_team.id)
        
        # Select starting 11 for each team
        home_starting_11 = self._select_starting_11(home_team.players)
        away_starting_11 = self._select_starting_11(away_team.players)
        
        # Select substitutes (up to 3 per team)
        home_subs = self._select_substitutes(home_team.players, home_starting_11)
        away_subs = self._select_substitutes(away_team.players, away_starting_11)
        
        # Track all players who played (starting 11 + substitutes)
        home_players_played = home_starting_11 + home_subs
        away_players_played = away_starting_11 + away_subs
        
        # Store players who played in the match object for later stats update
        match.home_players_played = [p['id'] for p in home_players_played]
        match.away_players_played = [p['id'] for p in away_players_played]
        
        # Skip games_played updates - will be done at end of season
        # self._update_games_played_before_match(home_players_played + away_players_played)
        
        # Calculate team strength based on starting 11 overall ratings
        home_strength = self._calculate_starting_11_strength(home_starting_11)
        away_strength = self._calculate_starting_11_strength(away_starting_11)
        
        # Calculate expected goals with amplified team strength differences
        # Use a more aggressive approach that creates proper win probabilities
        strength_ratio = home_strength / away_strength
        
        # Base expected goals (total goals per match)
        base_total_goals = 2.5  # Realistic average goals per match
        
        # Amplify the strength ratio to create extreme differences
        if strength_ratio > 1:
            # Home team is stronger
            amplified_ratio = strength_ratio ** 12  # Twelfth power for even more extreme amplification
            home_expected = (amplified_ratio / (amplified_ratio + 1)) * base_total_goals
            away_expected = (1 / (amplified_ratio + 1)) * base_total_goals
        else:
            # Away team is stronger
            amplified_ratio = (1 / strength_ratio) ** 12
            home_expected = (1 / (amplified_ratio + 1)) * base_total_goals
            away_expected = (amplified_ratio / (amplified_ratio + 1)) * base_total_goals
        
        # Ensure minimum expected goals
        home_expected = max(0.1, home_expected)
        away_expected = max(0.1, away_expected)
        
        # Generate actual goals using proper Poisson distribution
        def poisson_goals(lam):
            """Generate goals using Poisson distribution"""
            if lam <= 0:
                return 0
            count = 0
            time = 0
            while time < 1.0:
                time += random.expovariate(lam)
                if time < 1.0:
                    count += 1
            return count
        
        # Generate goals once and store them
        home_goals = poisson_goals(home_expected)
        away_goals = poisson_goals(away_expected)
        
        match.home_score = home_goals
        match.away_score = away_goals
        
        # For playoff games, eliminate draws with extra-time and penalties
        if is_playoff and match.home_score == match.away_score:
            # Extra-time: reduced expected goals
            home_et_expected = home_expected * 0.3  # 30% of normal expected goals
            away_et_expected = away_expected * 0.3
            
            # Generate extra-time goals once and store them
            home_et_goals = max(0, poisson_goals(home_et_expected))
            away_et_goals = max(0, poisson_goals(away_et_expected))
            
            match.home_score += home_et_goals
            match.away_score += away_et_goals
            
            # If still tied after extra-time, go to penalties
            if match.home_score == match.away_score:
                # Penalty shootout: simulate 5 penalties each
                home_penalties = sum(1 for _ in range(5) if random.random() < 0.75)  # 75% success rate
                away_penalties = sum(1 for _ in range(5) if random.random() < 0.75)
                
                # If still tied after 5 penalties, sudden death
                while home_penalties == away_penalties:
                    home_penalties += 1 if random.random() < 0.75 else 0
                    away_penalties += 1 if random.random() < 0.75 else 0
                
                # Penalty shootout winner gets +1 goal (for display purposes)
                if home_penalties > away_penalties:
                    match.home_score += 1
                else:
                    match.away_score += 1
        
        # Generate scorers and assists
        self._generate_scorers(match)
        self._generate_assists(match)
        
        # Save match result to database
        if hasattr(match, 'match_id') and match.match_id:
            self._save_match_result_to_database(match)
        
        # Update team statistics (only for regular season games)
        if not is_playoff:
            if match.home_score > match.away_score:
                home_team.wins += 1
                away_team.losses += 1
                home_team.points += 3
            elif match.away_score > match.home_score:
                away_team.wins += 1
                home_team.losses += 1
                away_team.points += 3
            else:
                # Draw - both teams get 1 point
                home_team.draws += 1
                away_team.draws += 1
                home_team.points += 1
                away_team.points += 1
            
            home_team.goals_for += match.home_score
            home_team.goals_against += match.away_score
            away_team.goals_for += match.away_score
            away_team.goals_against += match.home_score
    
    def _calculate_team_strength(self, team: Team) -> float:
        """Calculate comprehensive team strength based on multiple factors."""
        if not team.players:
            return 50.0  # Default strength
        
        # 1. Calculate aggregated skill ratings of entire squad
        total_skill_rating = 0
        for player in team.players:
            # Calculate player overall rating using position-specific weights
            overall = self._calculate_player_overall(player)
            total_skill_rating += overall
        
        squad_skill_rating = total_skill_rating / len(team.players)
        
        # 2. Calculate financial strength based on total salaries
        total_salaries = sum(player.get('salary', 0) for player in team.players)
        # Normalize salary to 0-100 scale (assuming max salary around 50M)
        financial_strength = min(100, (total_salaries / 50000000) * 100) if total_salaries > 0 else 50
        
        # 3. Calculate squad depth (quality of substitutes)
        # Sort players by overall rating and calculate depth
        sorted_players = sorted(team.players, key=lambda p: self._calculate_player_overall(p), reverse=True)
        
        # Starting 11 quality
        starting_11_quality = sum(self._calculate_player_overall(p) for p in sorted_players[:11]) / 11
        
        # Squad depth quality (players 12-25)
        squad_depth_quality = 0
        if len(sorted_players) > 11:
            squad_depth_quality = sum(self._calculate_player_overall(p) for p in sorted_players[11:25]) / min(14, len(sorted_players) - 11)
        else:
            squad_depth_quality = starting_11_quality * 0.8  # Penalty for small squad
        
        # 4. Combine all factors with weights
        # Skill rating: 50%, Financial strength: 20%, Squad depth: 30%
        comprehensive_strength = (
            squad_skill_rating * 0.5 +
            financial_strength * 0.2 +
            (starting_11_quality * 0.7 + squad_depth_quality * 0.3) * 0.3
        )
        
        return comprehensive_strength
    
    def _select_starting_11(self, players: List[Dict]) -> List[Dict]:
        """Select the best starting 11 players from the team roster with occasional rotation."""
        import random
        
        if not players:
            return []
        
        # Separate players by position
        goalkeepers = [p for p in players if p.get('game_position') == 'Goal-Keeper']
        defenders = [p for p in players if p.get('game_position') in ['Centre-Back', 'Side-Back', 'Wing-Back', 'Sweeper']]
        midfielders = [p for p in players if p.get('game_position') in ['Defensive Midfielder', 'Center-Midfielder', 'Side-Midfielder', 'Attacking Midfielder']]
        forwards = [p for p in players if p.get('game_position') in ['Winger', 'Shadow Striker', 'Striker']]
        
        starting_11 = []
        
        # Select 1 goalkeeper (always best one - goalkeepers rarely rotate)
        if goalkeepers:
            goalkeepers_sorted = sorted(goalkeepers, key=lambda p: self._calculate_player_overall(p), reverse=True)
            # 90% chance to pick best goalkeeper, 10% chance to pick second best
            if random.random() < 0.9 or len(goalkeepers_sorted) == 1:
                starting_11.append(goalkeepers_sorted[0])
            else:
                starting_11.append(goalkeepers_sorted[1])
        
        # Select 4 defenders with rotation
        if defenders:
            defenders_sorted = sorted(defenders, key=lambda p: self._calculate_player_overall(p), reverse=True)
            selected_defenders = []
            
            # Always pick the best 2 defenders
            selected_defenders.extend(defenders_sorted[:2])
            
            # For the remaining 2 spots, pick from top 4 defenders with some rotation
            remaining_defenders = defenders_sorted[2:6] if len(defenders_sorted) >= 6 else defenders_sorted[2:]
            if len(remaining_defenders) >= 2:
                # Randomly select 2 from the remaining defenders
                selected_defenders.extend(random.sample(remaining_defenders, min(2, len(remaining_defenders))))
            elif len(remaining_defenders) == 1:
                selected_defenders.append(remaining_defenders[0])
            
            starting_11.extend(selected_defenders[:4])
        
        # Select 4 midfielders with rotation
        if midfielders:
            midfielders_sorted = sorted(midfielders, key=lambda p: self._calculate_player_overall(p), reverse=True)
            selected_midfielders = []
            
            # Always pick the best midfielder
            selected_midfielders.append(midfielders_sorted[0])
            
            # For the remaining 3 spots, pick from top 5 midfielders with rotation
            remaining_midfielders = midfielders_sorted[1:6] if len(midfielders_sorted) >= 6 else midfielders_sorted[1:]
            if len(remaining_midfielders) >= 3:
                # Randomly select 3 from the remaining midfielders
                selected_midfielders.extend(random.sample(remaining_midfielders, 3))
            else:
                selected_midfielders.extend(remaining_midfielders)
            
            starting_11.extend(selected_midfielders[:4])
        
        # Select 2 forwards with rotation
        if forwards:
            forwards_sorted = sorted(forwards, key=lambda p: self._calculate_player_overall(p), reverse=True)
            selected_forwards = []
            
            # Always pick the best forward
            selected_forwards.append(forwards_sorted[0])
            
            # For the second spot, pick from top 3 forwards with rotation
            remaining_forwards = forwards_sorted[1:4] if len(forwards_sorted) >= 4 else forwards_sorted[1:]
            if remaining_forwards:
                selected_forwards.append(random.choice(remaining_forwards))
            
            starting_11.extend(selected_forwards[:2])
        
        # If we don't have enough players, fill with best available
        if len(starting_11) < 11:
            all_players_sorted = sorted(players, key=lambda p: self._calculate_player_overall(p), reverse=True)
            for player in all_players_sorted:
                if player not in starting_11 and len(starting_11) < 11:
                    starting_11.append(player)
        
        return starting_11[:11]  # Ensure exactly 11 players
    
    def _calculate_player_overall(self, player: Dict) -> float:
        """Get the stored overall rating for a player, or calculate it if not available."""
        # First try to get the stored overall rating
        stored_overall = player.get('overall')
        if stored_overall is not None and stored_overall > 0:
            return float(stored_overall)
        
        # Fallback to calculation if stored overall is not available
        # Use the same method as refresh_and_reimport.py
        from refresh_and_reimport import calculate_player_overall
        return calculate_player_overall(player)
        
        # Base physical and mental attributes (important for all positions)
        base_rating = (
            player.get('balance', 50) * 0.15 +
            player.get('stamina', 50) * 0.15 +
            player.get('top_speed', 50) * 0.1 +
            player.get('acceleration', 50) * 0.1 +
            player.get('response', 50) * 0.1 +
            player.get('agility', 50) * 0.1 +
            player.get('mentality', 50) * 0.1 +
            player.get('team_work', 50) * 0.1 +
            player.get('consistency', 50) * 0.1
        )
        
        # Position-specific skills
        if position == 'Goal-Keeper':
            # Goalkeepers: focus on goalkeeping, reflexes, positioning
            position_rating = (
                player.get('goal_keeping', 50) * 0.4 +
                player.get('response', 50) * 0.2 +
                player.get('jump', 50) * 0.15 +
                player.get('balance', 50) * 0.1 +
                player.get('mentality', 50) * 0.1 +
                player.get('consistency', 50) * 0.05
            )
        elif position in ['Centre-Back', 'Sweeper']:
            # Defenders: focus on defense, heading, physical
            position_rating = (
                player.get('defense', 50) * 0.3 +
                player.get('heading', 50) * 0.2 +
                player.get('jump', 50) * 0.15 +
                player.get('balance', 50) * 0.1 +
                player.get('short_pass_accuracy', 50) * 0.1 +
                player.get('response', 50) * 0.1 +
                player.get('mentality', 50) * 0.05
            )
        elif position in ['Side-Back', 'Wing-Back']:
            # Full-backs: focus on defense, speed, crossing
            position_rating = (
                player.get('defense', 50) * 0.25 +
                player.get('top_speed', 50) * 0.15 +
                player.get('acceleration', 50) * 0.15 +
                player.get('short_pass_accuracy', 50) * 0.15 +
                player.get('long_pass_accuracy', 50) * 0.1 +
                player.get('stamina', 50) * 0.1 +
                player.get('crossing', 50) * 0.1
            )
        elif position in ['Defensive Midfielder', 'Center-Midfielder']:
            # Midfielders: focus on passing, technique, work rate
            position_rating = (
                player.get('short_pass_accuracy', 50) * 0.2 +
                player.get('short_pass_speed', 50) * 0.15 +
                player.get('long_pass_accuracy', 50) * 0.15 +
                player.get('technique', 50) * 0.15 +
                player.get('stamina', 50) * 0.1 +
                player.get('defense', 50) * 0.1 +
                player.get('response', 50) * 0.1 +
                player.get('mentality', 50) * 0.05
            )
        elif position in ['Attacking Midfielder', 'Side-Midfielder']:
            # Attacking midfielders: focus on passing, technique, creativity
            position_rating = (
                player.get('short_pass_accuracy', 50) * 0.2 +
                player.get('technique', 50) * 0.2 +
                player.get('dribble_accuracy', 50) * 0.15 +
                player.get('long_pass_accuracy', 50) * 0.1 +
                player.get('shot_accuracy', 50) * 0.1 +
                player.get('response', 50) * 0.1 +
                player.get('mentality', 50) * 0.1 +
                player.get('creativity', 50) * 0.05
            )
        elif position in ['Winger']:
            # Wingers: focus on speed, dribbling, crossing
            position_rating = (
                player.get('top_speed', 50) * 0.2 +
                player.get('acceleration', 50) * 0.2 +
                player.get('dribble_accuracy', 50) * 0.2 +
                player.get('dribble_speed', 50) * 0.15 +
                player.get('crossing', 50) * 0.1 +
                player.get('short_pass_accuracy', 50) * 0.1 +
                player.get('stamina', 50) * 0.05
            )
        elif position in ['Striker', 'Shadow Striker']:
            # Strikers: focus on shooting, finishing, movement
            position_rating = (
                player.get('shot_accuracy', 50) * 0.25 +
                player.get('shot_power', 50) * 0.2 +
                player.get('shot_technique', 50) * 0.15 +
                player.get('heading', 50) * 0.15 +
                player.get('response', 50) * 0.1 +
                player.get('dribble_accuracy', 50) * 0.1 +
                player.get('mentality', 50) * 0.05
            )
        else:
            # Default: balanced approach
            position_rating = (
                player.get('attack', 50) * 0.2 +
                player.get('defense', 50) * 0.2 +
                player.get('technique', 50) * 0.2 +
                player.get('short_pass_accuracy', 50) * 0.15 +
                player.get('response', 50) * 0.15 +
                player.get('mentality', 50) * 0.1
            )
        
        # Combine base and position-specific ratings
        overall = (base_rating * 0.3) + (position_rating * 0.7)
        return overall
    
    def _calculate_starting_11_strength(self, starting_11: List[Dict]) -> float:
        """Calculate team strength based primarily on overall ratings."""
        if not starting_11:
            return 50.0
        
        # Get overall ratings for all players
        player_overalls = [self._calculate_player_overall(player) for player in starting_11]
        
        # Calculate position-weighted strength10 ma
        position_weights = {
            'Goal-Keeper': 1.2,  # Goalkeepers are crucial
            'Centre-Back': 1.1,  # Central defenders important
            'Side-Back': 1.0,    # Full-backs standard
            'Wing-Back': 1.0,    # Wing-backs standard
            'Sweeper': 1.1,      # Sweepers important
            'Defensive Midfielder': 1.1,  # Defensive midfielders important
            'Center-Midfielder': 1.2,     # Central midfielders crucial
            'Side-Midfielder': 1.0,       # Side midfielders standard
            'Attacking Midfielder': 1.3,   # Attacking midfielders very important
            'Winger': 1.1,        # Wingers important
            'Shadow Striker': 1.2, # Shadow strikers important
            'Striker': 1.4        # Strikers most important
        }
        
        # Calculate weighted average overall rating
        total_weighted_overall = 0
        total_weight = 0
        
        for i, player in enumerate(starting_11):
            position = player.get('game_position', '')
            weight = position_weights.get(position, 1.0)
            overall = player_overalls[i]
            
            total_weighted_overall += overall * weight
            total_weight += weight
        
        # Return the position-weighted average overall rating
        if total_weight > 0:
            team_strength = total_weighted_overall / total_weight
        else:
            team_strength = sum(player_overalls) / len(player_overalls)
        
        return team_strength
    
    def _select_substitutes(self, players: List[Dict], starting_11: List[Dict]) -> List[Dict]:
        """Select up to 3 substitutes from players not in starting 11."""
        if not players or len(starting_11) == 0:
            return []
        
        # Get players not in starting 11
        starting_11_ids = {p['id'] for p in starting_11}
        available_players = [p for p in players if p['id'] not in starting_11_ids]
        
        # Sort by overall rating and select up to 3 best substitutes
        available_players.sort(key=lambda p: self._calculate_player_overall(p), reverse=True)
        
        # Select up to 3 substitutes
        num_subs = min(3, len(available_players))
        return available_players[:num_subs]
    
    def _generate_scorers(self, match: Match):
        """Generate realistic scorers for a match based on player skills."""
        # Get players who actually played
        home_players_played = getattr(match, 'home_players_played', [])
        away_players_played = getattr(match, 'away_players_played', [])
        
        # Convert player IDs to player objects
        home_players_objects = [p for p in match.home_team.players if p['id'] in home_players_played]
        away_players_objects = [p for p in match.away_team.players if p['id'] in away_players_played]
        
        # Generate home team scorers
        for i in range(match.home_score):
            scorer = self._select_realistic_scorer(home_players_objects)
            minute = random.randint(1, 90)
            match.home_scorers.append({
                "player": scorer['player_name'],
                "minute": minute,
                "player_id": scorer['id']
            })
        
        # Generate away team scorers
        for i in range(match.away_score):
            scorer = self._select_realistic_scorer(away_players_objects)
            minute = random.randint(1, 90)
            match.away_scorers.append({
                "player": scorer['player_name'],
                "minute": minute,
                "player_id": scorer['id']
            })
    
    def _select_realistic_scorer(self, players: List[Dict]) -> Dict:
        """Select a realistic scorer based on player skills with much stronger position weighting."""
        if not players:
            return {}
        
        def normalize_position(pos: Optional[str]) -> str:
            return (pos or "").replace("-", "").replace("_", "").replace(" ", "").lower()
        
        attacking_positions = {
            "striker", "shadowstriker", "forward", "cf", "ss",
            "winger", "rightwingforward", "leftwingforward", "rwf", "lwf",
            "attackingmidfielder", "amf"
        }
        support_positions = {
            "centermidfielder", "centremidfielder", "cmf",
            "sidemidfielder", "widmidfielder", "rmf", "lmf", "midfielder"
        }
        defensive_positions = {
            "centreback", "centerback", "cb",
            "sideback", "fullback", "sb", "fb", "rb", "lb",
            "wingback", "wb", "sweeper", "defender", "df"
        }
        
        has_attackers = any(
            normalize_position(p.get('game_position') or p.get('registered_position')) in attacking_positions
            for p in players
        )
        
        scoring_weights = []
        for player in players:
            attack_weight = (
                player.get('shot_accuracy', 50) * 0.5 +
                player.get('shot_power', 50) * 0.3 +
                player.get('shot_technique', 50) * 0.15 +
                player.get('heading', 50) * 0.05
            )
            
            position_key = normalize_position(player.get('game_position') or player.get('registered_position'))
            position_multiplier = {
                "striker": 7.0, "shadowstriker": 7.0, "forward": 7.0, "cf": 7.0, "ss": 7.0,
                "winger": 3.5, "rightwingforward": 3.5, "leftwingforward": 3.5, "rwf": 3.5, "lwf": 4.0,
                "attackingmidfielder": 2.5, "amf": 2.5,
                "centermidfielder": 1.5, "centremidfielder": 1.5, "cmf": 1.5,
                "sidemidfielder": 1.25, "widmidfielder": 1.25, "rmf": 1.25, "lmf": 1.25,
                "defensivemidfielder": 0.75, "dmf": 0.75,
                "centreback": 0.5, "centerback": 0.5, "cb": 0.5,
                "sideback": 0.5, "fullback": 0.3, "sb": 0.5, "fb": 0.5, "rb": 0.5, "lb": 0.5,
                "wingback": 0.3, "wb": 0.3, "sweeper": 0.3, "defender": 0.3, "df": 0.3,
                "goalkeeper": 0.001, "gk": 0.001
            }.get(position_key, 1.0)
            attack_weight *= position_multiplier
            
            if has_attackers:
                if position_key in defensive_positions:
                    attack_weight *= 0.02
                elif position_key in support_positions:
                    attack_weight *= 0.2
            
            overall_rating = self._calculate_player_overall(player)
            quality_bonus = (overall_rating / 50) ** 2.5
            
            final_weight = attack_weight * quality_bonus
            scoring_weights.append(max(0.001, final_weight))
        
        total_weight = sum(scoring_weights)
        if total_weight == 0:
            return max(zip(scoring_weights, players), key=lambda item: item[0])[1]
        
        random_value = random.uniform(0, total_weight)
        current_weight = 0
        for i, weight in enumerate(scoring_weights):
            current_weight += weight
            if random_value <= current_weight:
                return players[i]
        
        return max(zip(scoring_weights, players), key=lambda item: item[0])[1]
    
    def _select_realistic_assister(self, players: List[Dict]) -> Dict:
        """Select a realistic assister based on player skills with stronger weighting."""
        if not players:
            return {}
        
        # Calculate assist probability for each player with much stronger weighting
        assist_weights = []
        for player in players:
            # Weight based on passing skills and position (much stronger weighting)
            assist_weight = (
                player.get('short_pass_accuracy', 50) * 0.4 +
                player.get('short_pass_speed', 50) * 0.25 +
                player.get('long_pass_accuracy', 50) * 0.2 +
                player.get('technique', 50) * 0.1 +
                player.get('dribble_accuracy', 50) * 0.05
            )
            
            # Position bonus for midfielders and attacking players (much stronger)
            position = player.get('game_position', '')
            if position in ['Attacking Midfielder', 'Center-Midfielder']:
                assist_weight *= 3.0  # Increased from 1.5x to 3x
            elif position in ['Winger', 'Side-Midfielder']:
                assist_weight *= 2.5  # Increased from 1.3x to 2.5x
            elif position in ['Defensive Midfielder']:
                assist_weight *= 1.5  # Increased from 1.1x to 1.5x
            elif position in ['Striker', 'Shadow Striker']:
                assist_weight *= 1.2  # Strikers can assist occasionally
            elif position in ['Centre-Back', 'Side-Back']:
                assist_weight *= 0.8  # Defenders less likely
            elif position == 'Goal-Keeper':
                assist_weight *= 0.1  # Very unlikely for goalkeepers to assist
            
            # Add overall player quality bonus (better players more likely to assist)
            overall_rating = self._calculate_player_overall(player)
            quality_bonus = (overall_rating / 50) ** 2  # Squared to amplify differences
            
            final_weight = assist_weight * quality_bonus
            assist_weights.append(max(0.1, final_weight))  # Ensure minimum weight
        
        # Select player based on weighted probability
        total_weight = sum(assist_weights)
        if total_weight == 0:
            return random.choice(players)
        
        random_value = random.uniform(0, total_weight)
        current_weight = 0
        
        for i, weight in enumerate(assist_weights):
            current_weight += weight
            if random_value <= current_weight:
                return players[i]
        
        return players[-1]  # Fallback
    
    def _generate_assists(self, match: Match):
        """Generate realistic assists for a match based on player skills."""
        # Get players who actually played
        home_players_played = getattr(match, 'home_players_played', [])
        away_players_played = getattr(match, 'away_players_played', [])
        
        # Convert player IDs to player objects
        home_players_objects = [p for p in match.home_team.players if p['id'] in home_players_played]
        away_players_objects = [p for p in match.away_team.players if p['id'] in away_players_played]
        
        # Generate assists (roughly 60% of goals have assists)
        total_goals = match.home_score + match.away_score
        num_assists = int(total_goals * 0.6)
        
        for i in range(num_assists):
            # Randomly assign assist to home or away team
            if random.choice([True, False]) and match.home_score > 0:
                assister = self._select_realistic_assister(home_players_objects)
                team_name = match.home_team.name
            elif match.away_score > 0:
                assister = self._select_realistic_assister(away_players_objects)
                team_name = match.away_team.name
            else:
                continue
            
            # Store assist data (will be processed in batch later)
            if not hasattr(match, 'assists'):
                match.assists = []
            match.assists.append({
                "player": assister['player_name'],
                "player_id": assister['id'],
                "team": team_name
            })
    
    def _update_player_stats(self, player_id: int, player_name: str, team_name: str, stat_type: str):
        """Update player statistics for leaderboards (in-memory only)."""
        if stat_type == 'goal':
            if player_id not in self.top_scorers:
                self.top_scorers[player_id] = {'name': player_name, 'team': team_name, 'goals': 0}
            self.top_scorers[player_id]['goals'] += 1
        elif stat_type == 'assist':
            if player_id not in self.top_assists:
                self.top_assists[player_id] = {'name': player_name, 'team': team_name, 'assists': 0}
            self.top_assists[player_id]['assists'] += 1
    
    def _batch_update_leaderboards(self, division_results: Dict):
        """Update leaderboards in batch after all matches in a round are played."""
        print("📊 Updating leaderboards from round results...")
        
        total_goals = 0
        total_assists = 0
        
        # Process all division results
        for div_id, div_result in division_results.items():
            if 'matches' in div_result:
                for match_data in div_result['matches']:
                    # Process goals from home team
                    if 'scorers' in match_data and 'home' in match_data['scorers']:
                        for scorer in match_data['scorers']['home']:
                            # Find the player data from the match
                            for home_scorer in match_data.get('home_scorers', []):
                                if home_scorer['player'] == scorer['player']:
                                    self._update_player_stats(
                                        home_scorer['player_id'], 
                                        scorer['player'], 
                                        match_data['home_team'], 
                                        'goal'
                                    )
                                    total_goals += 1
                                    break
                    
                    # Process goals from away team
                    if 'scorers' in match_data and 'away' in match_data['scorers']:
                        for scorer in match_data['scorers']['away']:
                            # Find the player data from the match
                            for away_scorer in match_data.get('away_scorers', []):
                                if away_scorer['player'] == scorer['player']:
                                    self._update_player_stats(
                                        away_scorer['player_id'], 
                                        scorer['player'], 
                                        match_data['away_team'], 
                                        'goal'
                                    )
                                    total_goals += 1
                                    break
                    
                    # Process assists
                    if 'assists' in match_data:
                        for assist in match_data['assists']:
                            self._update_player_stats(
                                assist['player_id'], 
                                assist['player'], 
                                assist['team'], 
                                'assist'
                            )
                            total_assists += 1
        
        print(f"✅ Updated leaderboards: {total_goals} goals, {total_assists} assists processed")
    
    def _update_division_standings(self, division_id: int):
        """Update division standings based on current results."""
        teams = self.leagues[division_id]['teams']
        # Sort by points (desc), then goal difference (desc), then goals for (desc)
        teams.sort(key=lambda t: (-t.points, -t.goal_difference, -t.goals_for))
        self.leagues[division_id]['standings'] = teams
    
    def _advance_to_playoffs(self):
        """Advance top 4 teams from each division to playoffs (16 teams total)."""
        self.playoff_teams = []
        
        for div_id, league_data in self.leagues.items():
            standings = league_data['standings']
            # Take top 4 teams from each division
            if standings:
                self.playoff_teams.extend(standings[:4])
        
        print(f"🏆 Playoff teams selected: {len(self.playoff_teams)} teams")
        for i, team in enumerate(self.playoff_teams):
            print(f"  {i+1}. {team.name} (Division {team.division})")
        
        # Create playoff bracket: 16 teams -> 8 series -> 4 series -> 2 series -> 1 final
        self.playoff_series = []
        self.playoff_round = 1  # Track which round of playoffs we're in
        
        if len(self.playoff_teams) == 16:
            # First round: 16 teams -> 8 series
            # Seed teams: 1st vs 16th, 2nd vs 15th, etc.
            for i in range(8):
                team1 = self.playoff_teams[i]
                team2 = self.playoff_teams[15-i]
                series = PlayoffSeries(team1, team2, stage="round_of_16")
                self.playoff_series.append(series)
        
        self.league_status = LeagueStatus.PLAYOFFS
        self.current_round = 0
        self.max_rounds = 7  # Maximum games in a series
    
    def _simulate_playoff_round(self) -> Dict:
        """Simulate one game in each active playoff series."""
        if not self.playoff_series:
            return {"matches_played": 0, "total_goals": 0, "playoffs_complete": True}
        
        matches_played = 0
        total_goals = 0
        playoff_scorers = []
        playoff_assists = []
        completed_series = []
        
        # Simulate one game for each active series
        for series in self.playoff_series:
            if not series.is_complete:
                # Determine home team (alternates based on game number)
                home_team = series.team1 if series.games_played % 2 == 0 else series.team2
                away_team = series.team2 if home_team == series.team1 else series.team1
                
                # Create and simulate match
                match = Match(home_team, away_team)
                self._simulate_match(match, is_playoff=True)
                
                # Add to series games
                series.games.append(match)
                series.games_played += 1
                matches_played += 1
                self.total_playoff_games += 1
                total_goals += match.home_score + match.away_score
                
                # Update series wins
                if match.home_score > match.away_score:
                    if home_team == series.team1:
                        series.team1_wins += 1
                    else:
                        series.team2_wins += 1
                elif match.away_score > match.home_score:
                    if away_team == series.team1:
                        series.team1_wins += 1
                    else:
                        series.team2_wins += 1
                
                # Check if series is complete (4 wins needed)
                if series.is_complete:
                    series.completed = True
                    series.winner = series.team1 if series.team1_wins >= 4 else series.team2
                    completed_series.append(series)
                    print(f"🏆 Series complete: {series.team1.name} vs {series.team2.name} - Winner: {series.winner.name}")
                
                # Collect scorer and assist data
                for scorer in match.home_scorers:
                    playoff_scorers.append({
                        'player_id': scorer['player_id'],
                        'player_name': scorer['player'],
                        'team_name': match.home_team.name,
                        'type': 'goal'
                    })
                
                for scorer in match.away_scorers:
                    playoff_scorers.append({
                        'player_id': scorer['player_id'],
                        'player_name': scorer['player'],
                        'team_name': match.away_team.name,
                        'type': 'goal'
                    })
                
                if hasattr(match, 'assists'):
                    for assist in match.assists:
                        playoff_assists.append({
                            'player_id': assist['player_id'],
                            'player_name': assist['player'],
                            'team_name': assist['team'],
                            'type': 'assist'
                        })
        
        # Update leaderboards in batch
        if playoff_scorers or playoff_assists:
            print(f"📊 Processing {len(playoff_scorers)} goals and {len(playoff_assists)} assists for playoffs")
            for scorer_data in playoff_scorers:
                self._update_player_stats(scorer_data['player_id'], scorer_data['player_name'], scorer_data['team_name'], 'goal')
            
            for assist_data in playoff_assists:
                self._update_player_stats(assist_data['player_id'], assist_data['player_name'], assist_data['team_name'], 'assist')
        
        # Check if we need to advance to next round
        playoffs_complete = False
        all_series_complete = all(series.is_complete for series in self.playoff_series)
        
        if all_series_complete:
            # Advance to next round
            winners = [series.winner for series in self.playoff_series]
            
            if self.playoff_round == 1:  # Round of 16 -> Quarterfinals
                self.playoff_round = 2
                self.playoff_series = []
                for i in range(0, len(winners), 2):
                    series = PlayoffSeries(winners[i], winners[i+1], stage="quarterfinal")
                    self.playoff_series.append(series)
                print(f"🏆 Advanced to Quarterfinals: {len(self.playoff_series)} series")
                
            elif self.playoff_round == 2:  # Quarterfinals -> Semifinals
                self.playoff_round = 3
                self.playoff_series = []
                for i in range(0, len(winners), 2):
                    series = PlayoffSeries(winners[i], winners[i+1], stage="semifinal")
                    self.playoff_series.append(series)
                print(f"🏆 Advanced to Semifinals: {len(self.playoff_series)} series")
                
            elif self.playoff_round == 3:  # Semifinals -> Final
                self.playoff_round = 4
                self.playoff_series = [PlayoffSeries(winners[0], winners[1], stage="final")]
                print(f"🏆 Advanced to Final: {winners[0].name} vs {winners[1].name}")
                
            elif self.playoff_round == 4:  # Final -> Championship complete
                playoffs_complete = True
                self.league_status = LeagueStatus.COMPLETED
                print(f"🏆 Championship complete! Winner: {winners[0].name}")
        
        # Check if any series are complete but others are still playing
        completed_series_count = sum(1 for series in self.playoff_series if series.is_complete)
        total_series = len(self.playoff_series)
        
        if completed_series_count > 0 and completed_series_count < total_series:
            print(f"📊 Round {self.playoff_round}: {completed_series_count}/{total_series} series complete")
        
        # Build match results for response
        match_results = []
        for series in self.playoff_series:
            if series.games:
                latest_game = series.games[-1]
                match_results.append({
                    "home_team": latest_game.home_team.name,
                    "away_team": latest_game.away_team.name,
                    "home_score": latest_game.home_score,
                    "away_score": latest_game.away_score,
                    "stage": series.stage.replace("_", " ").title(),
                    "series_score": f"{series.team1_wins}-{series.team2_wins}",
                    "series_complete": series.is_complete,
                    "playoff_round": self.playoff_round,
                    "scorers": {
                        "home": [{"player": s["player"], "minute": s["minute"]} for s in latest_game.home_scorers],
                        "away": [{"player": s["player"], "minute": s["minute"]} for s in latest_game.away_scorers]
                    },
                    "assists": [{"player": a["player"]} for a in getattr(latest_game, 'assists', [])]
                })
        
        return {
            "matches_played": matches_played,
            "total_goals": total_goals,
            "playoffs_complete": playoffs_complete,
            "winner": completed_series[0].winner.name if playoffs_complete and completed_series else None,
            "matches": match_results,
            "playoff_tree": self._get_playoff_tree(),
            "playoff_round": self.playoff_round
        }
    
    def _get_playoff_tree(self) -> Dict:
        """Generate playoff tree structure for display."""
        if not self.playoff_series:
            return {}
        
        tree = {
            "round_of_16": [],
            "quarterfinals": [],
            "semifinals": [],
            "final": None,
            "champion": None,
            "current_round": self.playoff_round
        }
        
        # Update with current series data
        for series in self.playoff_series:
            series_data = {
                "team1": series.team1.name,
                "team2": series.team2.name,
                "team1_wins": series.team1_wins,
                "team2_wins": series.team2_wins,
                "complete": series.is_complete,
                "winner": series.winner.name if series.winner else None
            }
            
            if series.stage == "round_of_16":
                tree["round_of_16"].append(series_data)
            elif series.stage == "quarterfinal":
                tree["quarterfinals"].append(series_data)
            elif series.stage == "semifinal":
                tree["semifinals"].append(series_data)
            elif series.stage == "final":
                tree["final"] = series_data
                
                if series.is_complete and series.winner:
                    tree["champion"] = series.winner.name
        
        return tree
    
    def get_standings(self) -> Dict:
        """Get current standings for all divisions."""
        standings = {}
        
        for div_id, league_data in self.leagues.items():
            teams = league_data['standings']
            standings[div_id] = [
                {
                    "team_name": team.name,
                    "games_played": team.games_played,
                    "wins": team.wins,
                    "draws": team.draws,
                    "losses": team.losses,
                    "goals_for": team.goals_for,
                    "goals_against": team.goals_against,
                    "goal_difference": team.goal_difference,
                    "points": team.points
                } for team in teams
            ]
        
        return standings
    
    def get_league_status(self) -> Dict:
        """Get current league status and progress."""
        return {
            "status": self.league_status.value,
            "current_round": self.current_round,
            "max_rounds": self.max_rounds,
            "divisions": len(self.leagues),
            "teams_per_division": [len(league['teams']) for league in self.leagues.values()],
            "playoff_teams": [team.name for team in self.playoff_teams] if self.playoff_teams else []
        }
    
    def update_player_statistics(self) -> bool:
        """Update player statistics in the database based on match results."""
        conn = None
        try:
            conn = self._get_db_connection()
            cur = conn.cursor()
            
            # Update statistics for all played matches
            for div_id, league_data in self.leagues.items():
                # Iterate through all rounds and matches
                for round_matches in league_data['rounds']:
                    for match in round_matches:
                        if match.played:
                            # Skip all player stat updates - will be done at end of season
                            pass
            
            conn.commit()
            return True
            
        except Exception as e:
            print(f"Error updating player statistics: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()
    
    def generate_revenue(self) -> Dict:
        """Generate revenue for CPU teams based on competitive balance."""
        conn = None
        try:
            conn = self._get_db_connection()
            cur = conn.cursor()
            
            revenue_data = {}
            total_revenue = 0
            
            # Calculate competitive balance metrics
            competitive_metrics = self._calculate_competitive_balance()
            
            print(f"📊 Competitive Metrics:")
            print(f"  Point differences: {competitive_metrics['point_differences']}")
            print(f"  Average point difference: {competitive_metrics['avg_point_difference']:.1f}")
            print(f"  Playoff games played: {competitive_metrics['playoff_games']}")
            print(f"  Competitive score: {competitive_metrics['competitive_score']:.2f}")
            
            # Calculate base revenue per team based on competitive balance
            base_revenue_per_team = self._calculate_base_revenue(competitive_metrics)
            
            print(f"💰 Base revenue per team: €{base_revenue_per_team:,}")
            
            # Get championship winner
            champion = None
            if self.playoff_series and self.playoff_series:
                # Find the final series winner
                for series in self.playoff_series:
                    if series.stage == "final" and series.is_complete and series.winner:
                        champion = series.winner
                        break
            
            for div_id, league_data in self.leagues.items():
                for i, team in enumerate(league_data['standings']):
                    # Base revenue for participation
                    base_revenue = base_revenue_per_team
                    
                    # Performance bonus based on position (smaller bonus for more competitive leagues)
                    position_multiplier = 1.0 - (competitive_metrics['competitive_score'] * 0.3)  # Reduce bonus for competitive leagues
                    position_bonus = (len(league_data['standings']) - i) * 100000 * position_multiplier
                    
                    # Playoff bonus if team made playoffs
                    playoff_bonus = base_revenue_per_team * 0.1 if team in self.playoff_teams else 0
                    
                    # Championship bonus
                    championship_bonus = base_revenue_per_team * 0.2 if (champion and team == champion) else 0
                    
                    # Marketing Flair bonus based on star players
                    marketing_flair_bonus = self._calculate_marketing_flair_bonus(team.id, cur)
                    
                    total_team_revenue = base_revenue + position_bonus + playoff_bonus + championship_bonus + marketing_flair_bonus
                    
                    # Update team budget
                    cur.execute("""
                        UPDATE teams 
                        SET budget = budget + ?
                        WHERE id = ?
                    """, (total_team_revenue, team.id))
                    
                    revenue_data[team.name] = {
                        "base_revenue": base_revenue,
                        "position_bonus": position_bonus,
                        "playoff_bonus": playoff_bonus,
                        "championship_bonus": championship_bonus,
                        "marketing_flair_bonus": marketing_flair_bonus,
                        "total_revenue": total_team_revenue,
                        "competitive_score": competitive_metrics['competitive_score']
                    }
                    
                    total_revenue += total_team_revenue
            
            conn.commit()
            
            return {
                "total_revenue": total_revenue,
                "team_revenues": revenue_data,
                "competitive_metrics": competitive_metrics,
                "champion": champion.name if champion else None
            }
            
        except Exception as e:
            print(f"Error generating revenue: {e}")
            if conn:
                conn.rollback()
            return {"error": str(e)}
        finally:
            if conn:
                conn.close()
    
    def _calculate_competitive_balance(self) -> Dict:
        """Calculate competitive balance metrics for revenue calculation."""
        point_differences = []
        total_playoff_games = 0
        
        # Calculate point differences for each division
        for div_id, league_data in self.leagues.items():
            standings = league_data['standings']
            if standings:
                first_place_points = standings[0].points
                last_place_points = standings[-1].points
                point_diff = first_place_points - last_place_points
                point_differences.append(point_diff)
        
        # Use total playoff games played throughout the tournament
        total_playoff_games = self.total_playoff_games
        
        avg_point_difference = sum(point_differences) / len(point_differences) if point_differences else 0
        
        # Calculate competitive score (0 = non-competitive, 1 = very competitive)
        # Point difference component (30% weight)
        if avg_point_difference >= 50:
            point_competitiveness = 0.0  # Non-competitive
        elif avg_point_difference <= 20:
            point_competitiveness = 1.0  # Very competitive
        else:
            # Linear interpolation between 20 and 50 points
            point_competitiveness = 1.0 - ((avg_point_difference - 20) / 30)
        
        # Playoff games component (70% weight)
        if total_playoff_games <= 60:
            playoff_competitiveness = 0.0  # Non-competitive (4-0 sweeps)
        elif total_playoff_games >= 105:
            playoff_competitiveness = 1.0  # Very competitive (4-3 series)
        else:
            # Linear interpolation between 60 and 105 games
            playoff_competitiveness = (total_playoff_games - 60) / 45
        
        # Weighted competitive score
        competitive_score = (point_competitiveness * 0.3) + (playoff_competitiveness * 0.7)
        
        return {
            "point_differences": point_differences,
            "avg_point_difference": avg_point_difference,
            "playoff_games": total_playoff_games,
            "point_competitiveness": point_competitiveness,
            "playoff_competitiveness": playoff_competitiveness,
            "competitive_score": competitive_score
        }
    
    def _calculate_base_revenue(self, competitive_metrics: Dict) -> int:
        """Calculate base revenue per team based on competitive balance."""
        competitive_score = competitive_metrics['competitive_score']
        
        # Revenue range: €200M (competitive) to €100M (non-competitive)
        # Competitive leagues get more revenue (harder to win, more reward)
        min_revenue = 50000000  # €100M for non-competitive leagues
        max_revenue = 100000000  # €200M for competitive leagues
        
        # Higher competitive score = higher revenue (more competitive = more money)
        base_revenue = min_revenue + (competitive_score * (max_revenue - min_revenue))
        
        return int(base_revenue)
    
    def _calculate_marketing_flair_bonus(self, team_id: int, cur) -> int:
        """Calculate Marketing Flair bonus based on star players and superstars."""
        try:
            # Get all players for this team with their market values
            cur.execute("""
                SELECT player_name, market_value
                FROM players
                WHERE club_id = ? AND market_value IS NOT NULL
                ORDER BY market_value DESC
            """, (team_id,))
            
            team_players = cur.fetchall()
            
            if not team_players:
                return 0
            
            marketing_bonus = 0
            star_players_count = 0
            superstar_bonus = 0
            
            for player in team_players:
                market_value = player['market_value']
                player_name = player['player_name']
                
                # Star player bonus (market value > €20M)
                if market_value > 20000000:
                    star_players_count += 1
                
                # Superstar bonus (market value > €100M) - 2% of value
                if market_value > 100000000:
                    player_superstar_bonus = int(market_value * 0.08)
                    superstar_bonus += player_superstar_bonus
                    print(f"  ⭐ Superstar {player_name}: €{market_value:,} → +€{player_superstar_bonus:,} marketing bonus")
            
            # Star player index bonus: €5M to €30M based on number of star players
            # Formula: €5M + (star_players_count * €2.5M), capped at €30M
            star_index_bonus = min(30000000, 5000000 + (star_players_count * 2500000))
            
            marketing_bonus = star_index_bonus + superstar_bonus
            
            # Cap total marketing flair bonus at €50M to prevent excessive bonuses
            marketing_bonus = min(50000000, marketing_bonus)
            
            if marketing_bonus > 0:
                print(f"  💫 Marketing Flair: {star_players_count} stars → €{star_index_bonus:,} + €{superstar_bonus:,} superstar = €{marketing_bonus:,}")
            
            return marketing_bonus
            
        except Exception as e:
            print(f"❌ Error calculating marketing flair bonus for team {team_id}: {e}")
            return 0
    
    def get_top_scorers(self, limit: int = 10) -> List[Dict]:
        """Get top goalscorers across all divisions."""
        scorers_list = []
        for player_id, stats in self.top_scorers.items():
            scorers_list.append({
                'player_id': player_id,
                'name': stats['name'],
                'team': stats['team'],
                'goals': stats['goals']
            })
        
        # Sort by goals (descending)
        scorers_list.sort(key=lambda x: x['goals'], reverse=True)
        return scorers_list[:limit]
    
    def get_top_assists(self, limit: int = 10) -> List[Dict]:
        """Get top assist providers across all divisions."""
        assists_list = []
        for player_id, stats in self.top_assists.items():
            assists_list.append({
                'player_id': player_id,
                'name': stats['name'],
                'team': stats['team'],
                'assists': stats['assists']
            })
        
        # Sort by assists (descending)
        assists_list.sort(key=lambda x: x['assists'], reverse=True)
        return assists_list[:limit]
    
    def get_top_scorers(self, limit: int = 10) -> List[Dict]:
        """Get top scorers from current season leaderboard."""
        scorers_list = []
        for player_id, stats in self.top_scorers.items():
            scorers_list.append({
                'player_id': player_id,
                'name': stats['name'],
                'team': stats['team'],
                'goals': stats['goals']
            })
        
        # Sort by goals (descending)
        scorers_list.sort(key=lambda x: x['goals'], reverse=True)
        return scorers_list[:limit]
    
    def get_top_assists(self, limit: int = 10) -> List[Dict]:
        """Get top assists from current season leaderboard."""
        assists_list = []
        for player_id, stats in self.top_assists.items():
            assists_list.append({
                'player_id': player_id,
                'name': stats['name'],
                'team': stats['team'],
                'assists': stats['assists']
            })
        
        # Sort by assists (descending)
        assists_list.sort(key=lambda x: x['assists'], reverse=True)
        return assists_list[:limit]
    
    def _update_games_played_before_match(self, players_played: List[Dict]):
        """Update games_played for players before the match simulation starts."""
        # Add a counter to track how many times this function is called
        if not hasattr(self, '_games_update_counter'):
            self._games_update_counter = 0
        self._games_update_counter += 1
        
        print(f"🔍 DEBUG: _update_games_played_before_match called #{self._games_update_counter} with {len(players_played)} players")
        
        conn = None
        try:
            conn = self._get_db_connection()
            cur = conn.cursor()
            
            # Update games_played for each player
            for player in players_played:
                cur.execute("""
                    UPDATE players 
                    SET games_played = games_played + 1
                    WHERE id = ?
                """, (player['id'],))
            
            conn.commit()
            
        except Exception as e:
            print(f"Error updating games_played before match: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()
    
    def _allocate_end_of_season_player_stats(self):
        """Allocate games, goals, and assists to players at end of season based on leaderboards."""
        conn = None
        try:
            conn = self._get_db_connection()
            cur = conn.cursor()
            
            print("🏆 Allocating end-of-season player statistics...")
            
            # First, allocate goals and assists based on current leaderboards
            self._allocate_goals_and_assists(cur)
            
            # Then, allocate games played based on team participation and overall ratings
            self._allocate_games_played(cur)
            
            conn.commit()
            print("✅ End-of-season player statistics allocated successfully")
            
        except Exception as e:
            print(f"❌ Error allocating end-of-season stats: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()
    
    def _allocate_goals_and_assists(self, cur):
        """Allocate goals and assists based on current leaderboards."""
        print("⚽ Allocating goals and assists...")
        
        # Allocate goals
        for player_id, stats in self.top_scorers.items():
            adjusted_goals = math.ceil(stats['goals'] / 2)
            cur.execute("""
                UPDATE players 
                SET goals = COALESCE(goals, 0) + ?
                WHERE id = ?
            """, (adjusted_goals, player_id))
            print(f"  ⚽ {stats['name']} ({stats['team']}): +{adjusted_goals} goals")
        
        # Allocate assists
        for player_id, stats in self.top_assists.items():
            assists = stats['assists']
            cur.execute("""
                UPDATE players 
                SET assists = COALESCE(assists, 0) + ?
                WHERE id = ?
            """, (assists, player_id))
            print(f"  🅰️ {stats['name']} ({stats['team']}): +{assists} assists")
        
        cur.execute("""
            UPDATE players
            SET goals = 0
            WHERE registered_position = 0
        """)
        print("  🧤 Goalkeeper goals reset to 0")
    
    def _allocate_games_played(self, cur):
        """Allocate games played based on team participation and player overall ratings."""
        print("🎮 Allocating games played...")
        
        # Get all CPU teams that participated in the league
        cur.execute("""
            SELECT DISTINCT t.id, t.club_name
            FROM teams t
            JOIN league_teams lt ON t.id = lt.id
            WHERE lt.user_id = 1
        """)
        cpu_teams = cur.fetchall()
        
        for team in cpu_teams:
            team_id = team['id']
            team_name = team['club_name']
            
            # Get team's players sorted by overall rating (best players first)
            cur.execute("""
                SELECT id, player_name, overall
                FROM players
                WHERE club_id = ? AND overall IS NOT NULL
                ORDER BY overall DESC, id ASC
            """, (team_id,))
            team_players = cur.fetchall()
            
            if not team_players:
                continue
                
            # Calculate games for this team
            base_games = 20  # Regular season games
            
            # Check if team made playoffs (simplified - could be enhanced)
            # For now, assume all teams get base_games, playoff teams get extra
            total_games = base_games
            
            # Allocate games to players
            self._distribute_team_games(cur, team_players, team_name, total_games)
    
    def _distribute_team_games(self, cur, team_players, team_name, total_games):
        """Distribute games among team players based on their overall rating."""
        if not team_players:
            return
            
        core_players = team_players[:11]
        bench_players = team_players[11:15] if len(team_players) > 11 else []
        reserves = team_players[15:] if len(team_players) > 15 else []
        
        print(f"  🏟️ {team_name}: {len(core_players)} core, {len(bench_players)} bench, {len(reserves)} reserves (total games: {total_games})")
        
        total_slots = total_games * 14  # 11 starters + 1 rotation spot per match
        total_allocated = 0
        
        for i, player in enumerate(core_players):
            games_percentage = max(0.10, 0.90 - (i * 0.05))
            games = max(1, min(total_games, int(round(total_games * games_percentage))))
            total_allocated += games
            cur.execute("""
                UPDATE players 
                SET games_played = COALESCE(games_played, 0) + ?
                WHERE id = ?
            """, (games, player['id']))
            print(f"    🎮 {player['player_name']} (Overall: {player['overall']}): +{games} games ({games_percentage:.1%})")
        
        rotation_players = bench_players + reserves
        if rotation_players:
            remaining_slots = max(0, total_slots - total_allocated)
            rotation_slots = max(len(rotation_players), min(remaining_slots, total_games * len(rotation_players)))
            max_rotation_games = max(1, int(total_games * 0.5))
            base = rotation_slots // len(rotation_players)
            remainder = rotation_slots % len(rotation_players)
            
            for idx, player in enumerate(rotation_players):
                games = base + (1 if idx < remainder else 0)
                # Add variance to make distribution more realistic (±1 game)
                games += random.randint(-5, 5)
                games = max(0, min(max_rotation_games, games))
                total_allocated += games
                cur.execute("""
                    UPDATE players 
                    SET games_played = COALESCE(games_played, 0) + ?
                    WHERE id = ?
                """, (games, player['id']))
                
                marker = "🪑" if idx < len(bench_players) else "📋"
                print(f"    {marker} {player['player_name']} (Overall: {player['overall']}): +{games} games (rotation)")
    
    def _batch_update_player_stats_in_database(self):
        """Batch update player statistics in the main players table (goals and assists only)."""
        conn = None
        try:
            conn = self._get_db_connection()
            cur = conn.cursor()
            
            # Only update goals and assists for players who scored or assisted
            players_to_update = set()
            
            # Add players who scored
            for player_id in self.top_scorers.keys():
                players_to_update.add(player_id)
            
            # Add players who assisted
            for player_id in self.top_assists.keys():
                players_to_update.add(player_id)
            
            # Update each player's goals and assists
            for player_id in players_to_update:
                goals = self.top_scorers.get(player_id, {}).get('goals', 0)
                assists = self.top_assists.get(player_id, {}).get('assists', 0)
                
                # Check if player is a goalkeeper (registered_position = 0)
                cur.execute("SELECT registered_position FROM players WHERE id = ?", (player_id,))
                position_result = cur.fetchone()
                
                if position_result and position_result[0] == 0:  # Goalkeeper
                    # Set goalkeeper goals to 0 (overwrite any previous value)
                    cur.execute("""
                        UPDATE players 
                        SET goals = 0, assists = assists + ?
                        WHERE id = ?
                    """, (assists, player_id))
                    print(f"    🧤 Goalkeeper {player_id}: Goals set to 0, +{assists} assists")
                else:
                    # Regular player - update goals and assists normally
                    cur.execute("""
                        UPDATE players 
                        SET goals = goals + ?, assists = assists + ?
                        WHERE id = ?
                    """, (goals, assists, player_id))
            
            conn.commit()
            print(f"✅ Batch updated goals/assists for {len(players_to_update)} players")
            
        except Exception as e:
            print(f"Error batch updating player stats in database: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()
    
    def _save_matches_to_database(self, division_id: int):
        """Save matches for a division to the database."""
        conn = None
        try:
            conn = self._get_db_connection()
            cur = conn.cursor()
            
            league_data = self.leagues[division_id]
            rounds = league_data['rounds']
            
            for round_num, round_matches in enumerate(rounds):
                for match in round_matches:
                    cur.execute("""
                        INSERT INTO cpu_league_matches 
                        (season_id, division_number, round_number, home_team_id, away_team_id)
                        VALUES (?, ?, ?, ?, ?)
                    """, (self.current_season_id, division_id, round_num + 1, 
                          match.home_team.id, match.away_team.id))
                    match.match_id = cur.lastrowid
            
            conn.commit()
            
        except Exception as e:
            print(f"Error saving matches to database: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()
    
    def _save_match_result_to_database(self, match: Match):
        """Save match result and scorers to the database."""
        conn = None
        try:
            conn = self._get_db_connection()
            cur = conn.cursor()
            
            # Update match result
            cur.execute("""
                UPDATE cpu_league_matches 
                SET home_score = ?, away_score = ?, played = TRUE, played_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (match.home_score, match.away_score, match.match_id))
            
            # Save scorers
            for scorer in match.home_scorers:
                cur.execute("""
                    INSERT INTO cpu_league_scorers 
                    (match_id, player_id, team_id, minute, is_goal, is_assist)
                    VALUES (?, ?, ?, ?, TRUE, FALSE)
                """, (match.match_id, scorer['player_id'], match.home_team.id, scorer['minute']))
            
            for scorer in match.away_scorers:
                cur.execute("""
                    INSERT INTO cpu_league_scorers 
                    (match_id, player_id, team_id, minute, is_goal, is_assist)
                    VALUES (?, ?, ?, ?, TRUE, FALSE)
                """, (match.match_id, scorer['player_id'], match.away_team.id, scorer['minute']))
            
            conn.commit()
            
        except Exception as e:
            print(f"Error saving match result to database: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()
    
    def _update_division_standings_in_database(self, division_id: int):
        """Update division standings in the database."""
        conn = None
        try:
            conn = self._get_db_connection()
            cur = conn.cursor()
            
            league_data = self.leagues[division_id]
            teams = league_data['standings']
            
            for team in teams:
                cur.execute("""
                    UPDATE cpu_league_divisions 
                    SET games_played = ?, wins = ?, losses = ?, 
                        goals_for = ?, goals_against = ?, points = ?
                    WHERE season_id = ? AND division_number = ? AND team_id = ?
                """, (team.games_played, team.wins, team.losses, 
                      team.goals_for, team.goals_against, team.points,
                      self.current_season_id, division_id, team.id))
            
            conn.commit()
            
        except Exception as e:
            print(f"Error updating division standings in database: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()
    
    def load_current_season(self) -> bool:
        """Load the current active season from the database."""
        conn = None
        try:
            conn = self._get_db_connection()
            cur = conn.cursor()
            
            # Get the most recent active season
            cur.execute("""
                SELECT id, season_name, status, current_round, max_rounds, division_count
                FROM cpu_league_seasons 
                WHERE status IN ('round_robin', 'playoffs')
                ORDER BY created_at DESC 
                LIMIT 1
            """)
            
            season = cur.fetchone()
            if not season:
                return False
            
            self.current_season_id = season[0]
            self.current_round = season[3]
            self.max_rounds = season[4]
            self.league_status = LeagueStatus(season[2])
            
            # Load divisions and teams
            cur.execute("""
                SELECT division_number, team_id, team_name, games_played, wins, losses,
                       goals_for, goals_against, points
                FROM cpu_league_divisions 
                WHERE season_id = ?
                ORDER BY division_number, points DESC, goal_difference DESC
            """, (self.current_season_id,))
            
            divisions_data = cur.fetchall()
            
            # Reconstruct league structure
            self.leagues = {}
            for row in divisions_data:
                div_num = row[0]
                if div_num not in self.leagues:
                    self.leagues[div_num] = {'teams': [], 'rounds': [], 'standings': [], 'current_round': 0, 'max_rounds': 0}
                
                # Create team object
                team = Team(
                    id=row[1],
                    name=row[2],
                    division=div_num,
                    players=[]  # We'll load players when needed
                )
                team.games_played = row[3]
                team.wins = row[4]
                team.losses = row[5]
                team.goals_for = row[6]
                team.goals_against = row[7]
                team.points = row[8]
                
                self.leagues[div_num]['teams'].append(team)
                self.leagues[div_num]['standings'].append(team)
            
            return True
            
        except Exception as e:
            print(f"Error loading current season: {e}")
            return False
        finally:
            if conn:
                conn.close()
    
    def reset_league(self):
        """Reset the league to initial state."""
        self.leagues = {}
        self.current_round = 0
        self.max_rounds = 0
        self.league_status = LeagueStatus.NOT_STARTED
        self.playoff_teams = []
        self.playoff_series = []
        self.playoff_round = 1
        self.total_playoff_games = 0
        self.top_scorers = {}
        self.top_assists = {}
        self.current_season_id = None

# Global league manager instance
league_manager = CPULeagueManager()

def simulate_cpu_game(home_team_id, away_team_id, cur):
    """
    SIMPLIFIED and RELIABLE CPU game simulation.
    Guarantees: 1 GK per team, no GK goals/assists, always selects MVP, includes substitutions.
    """
    import random
    
    # Helper function to convert registered_position from TEXT to int
    def get_pos_int(p):
        """Convert registered_position (TEXT) to int for comparison"""
        pos = p.get('registered_position')
        try:
            return int(pos) if pos is not None else -1
        except (ValueError, TypeError):
            return -1
    
    # Get all players for both teams
    cur.execute("""
        SELECT id, player_name, overall, registered_position
        FROM players
        WHERE club_id = ? AND overall IS NOT NULL
        ORDER BY overall DESC
    """, (home_team_id,))
    home_players_all = [dict(row) for row in cur.fetchall()]
    
    cur.execute("""
        SELECT id, player_name, overall, registered_position
        FROM players
        WHERE club_id = ? AND overall IS NOT NULL
        ORDER BY overall DESC
    """, (away_team_id,))
    away_players_all = [dict(row) for row in cur.fetchall()]
    
    def select_starting_11(players, team_id):
        """Select exactly 11 players using preferred lineup from DB, with 30% rotation per position"""
        if not players or len(players) < 11:
            return []
        
        # Get preferred lineup from database
        cur.execute("""
            SELECT slot_number, player_id, position_group
            FROM team_preferred_lineup
            WHERE team_id = ?
            ORDER BY slot_number
        """, (team_id,))
        preferred_slots = [dict(row) for row in cur.fetchall()]
        
        # If no preferred lineup exists OR all slots have invalid position_group, fall back to best overall per position
        valid_slots = [s for s in preferred_slots if s.get('position_group') and s.get('position_group') != 'FILL']
        if not preferred_slots or len(valid_slots) < 8:  # Need at least 8 valid slots
            # Group by position (using get_pos_int helper)
            gks = sorted([p for p in players if get_pos_int(p) == 0], 
                        key=lambda x: x.get('overall', 0), reverse=True)
            side_backs = sorted([p for p in players if get_pos_int(p) in [4, 6]], 
                               key=lambda x: x.get('overall', 0), reverse=True)
            centre_backs = sorted([p for p in players if get_pos_int(p) in [2, 3]], 
                                 key=lambda x: x.get('overall', 0), reverse=True)
            centre_mids = sorted([p for p in players if get_pos_int(p) in [5, 7]], 
                                key=lambda x: x.get('overall', 0), reverse=True)  # Fixed: removed 8 (SMF) from CM
            side_mids = sorted([p for p in players if get_pos_int(p) in [8, 10]], 
                              key=lambda x: x.get('overall', 0), reverse=True)
            forwards = sorted([p for p in players if get_pos_int(p) in [11, 12]], 
                             key=lambda x: x.get('overall', 0), reverse=True)
            
            lineup = []
            if gks:
                lineup.append(gks[0])
            for sb in side_backs[:2]:
                lineup.append(sb)
            for cb in centre_backs[:2]:
                lineup.append(cb)
            for cm in centre_mids[:2]:
                lineup.append(cm)
            for sm in side_mids[:2]:
                lineup.append(sm)
            for fwd in forwards[:2]:
                lineup.append(fwd)
            
            return lineup[:11]
        
        # Build player lookup dict
        players_dict = {p.get('id'): p for p in players}
        
        # Group players by position for rotation (using get_pos_int helper)
        position_groups = {
            'GK': [p for p in players if get_pos_int(p) == 0],
            'SB/WB': [p for p in players if get_pos_int(p) in [4, 6]],
            'CB/SW': [p for p in players if get_pos_int(p) in [2, 3]],
            'CM': [p for p in players if get_pos_int(p) in [5, 7]],  # Fixed: removed 8 (SMF) from CM
            'SM': [p for p in players if get_pos_int(p) in [8, 10]],
            'FWD': [p for p in players if get_pos_int(p) in [11, 12]]
        }
        
        # Sort each group by overall
        for group in position_groups.values():
            group.sort(key=lambda x: x.get('overall', 0), reverse=True)
        
        lineup = []
        used_ids = set()
        
        # Process each slot from preferred lineup
        for slot in preferred_slots:
            slot_num = slot.get('slot_number')
            preferred_player_id = slot.get('player_id')
            position_group = slot.get('position_group', '')
            
            # Get preferred player
            preferred_player = players_dict.get(preferred_player_id)
            
            # Skip if position_group is 'FILL' or invalid - determine from player's actual position
            if not position_group or position_group == 'FILL':
                if preferred_player:
                    # Determine position group from player's registered_position (using get_pos_int)
                    pos = get_pos_int(preferred_player)
                    if pos == 0:
                        position_group = 'GK'
                    elif pos in [4, 6]:
                        position_group = 'SB/WB'
                    elif pos in [2, 3]:
                        position_group = 'CB/SW'
                    elif pos in [5, 7, 8]:
                        position_group = 'CM'
                    elif pos in [8, 10]:
                        position_group = 'SM'
                    elif pos in [11, 12]:
                        position_group = 'FWD'
                    else:
                        # Unknown position - just use the player
                        if preferred_player.get('id') not in used_ids:
                            lineup.append(preferred_player)
                            used_ids.add(preferred_player.get('id'))
                        continue
                else:
                    continue
            
            # 30% chance to rotate per position group (only if position_group is valid)
            if random.random() < 0.3 and position_group in position_groups:
                # Rotate: pick another player from same position group
                available_players = [p for p in position_groups[position_group] 
                                   if p.get('id') not in used_ids and p.get('id') != preferred_player_id]
                if available_players:
                    # Pick from top 3-4 alternatives
                    chosen = random.choice(available_players[:min(4, len(available_players))])
                    lineup.append(chosen)
                    used_ids.add(chosen.get('id'))
                elif preferred_player and preferred_player.get('id') not in used_ids:
                    # Fallback to preferred if no alternatives
                    lineup.append(preferred_player)
                    used_ids.add(preferred_player.get('id'))
            else:
                # Use preferred player (70% of the time)
                if preferred_player and preferred_player.get('id') not in used_ids:
                    lineup.append(preferred_player)
                    used_ids.add(preferred_player.get('id'))
                else:
                    # Preferred player not available, pick best from position group
                    if position_group in position_groups:
                        available = [p for p in position_groups[position_group] 
                                     if p.get('id') not in used_ids]
                        if available:
                            chosen = available[0]
                            lineup.append(chosen)
                            used_ids.add(chosen.get('id'))
        
        # Ensure exactly 11 players
        if len(lineup) < 11:
            used_ids_set = set(used_ids)
            available = sorted([p for p in players if p.get('id') not in used_ids_set 
                              and get_pos_int(p) != 0], 
                             key=lambda x: x.get('overall', 0), reverse=True)
            needed = 11 - len(lineup)
            for p in available[:needed]:
                lineup.append(p)
                used_ids.add(p.get('id'))
        
        # CRITICAL: Ensure exactly 1 goalkeeper (using get_pos_int)
        gks_in_lineup = [p for p in lineup if get_pos_int(p) == 0]
        if len(gks_in_lineup) > 1:
            # Keep only first (best) GK
            first_gk = gks_in_lineup[0]
            non_gks = [p for p in lineup if get_pos_int(p) != 0]
            lineup = [first_gk] + non_gks
        elif len(gks_in_lineup) == 0:
            # No GK - add best available
            available_gks = [p for p in players if get_pos_int(p) == 0 
                           and p.get('id') not in used_ids]
            if available_gks:
                available_gks.sort(key=lambda x: x.get('overall', 0), reverse=True)
                if len(lineup) >= 11:
                    lineup = lineup[:-1]
                lineup = [available_gks[0]] + lineup
        
        return lineup[:11]
    
    # Select starting 11 for both teams using preferred lineups
    home_lineup = select_starting_11(home_players_all, home_team_id)
    away_lineup = select_starting_11(away_players_all, away_team_id)
    
    # CRITICAL: Check if lineups are empty
    if not home_lineup or len(home_lineup) == 0:
        # Fallback: create basic lineup from available players
        home_lineup = home_players_all[:11] if len(home_players_all) >= 11 else home_players_all
    
    if not away_lineup or len(away_lineup) == 0:
        # Fallback: create basic lineup from available players
        away_lineup = away_players_all[:11] if len(away_players_all) >= 11 else away_players_all
    
    # CRITICAL: Validate lineups IMMEDIATELY - ensure exactly 1 GK per team (using get_pos_int)
    def ensure_one_gk(lineup):
        """Force lineup to have exactly 1 goalkeeper"""
        gks = [p for p in lineup if get_pos_int(p) == 0]
        non_gks = [p for p in lineup if get_pos_int(p) != 0]
        if len(gks) > 1:
            # Keep only the best (first) goalkeeper
            return [gks[0]] + non_gks
        elif len(gks) == 1:
            return lineup
        else:
            # No GK - this shouldn't happen, but return as is
            return lineup
    
    home_lineup = ensure_one_gk(home_lineup)
    away_lineup = ensure_one_gk(away_lineup)
    
    # Double-check: count goalkeepers
    home_gk_count = sum(1 for p in home_lineup if get_pos_int(p) == 0)
    away_gk_count = sum(1 for p in away_lineup if get_pos_int(p) == 0)
    
    if home_gk_count != 1:
        # Emergency fix
        gks = [p for p in home_lineup if get_pos_int(p) == 0]
        non_gks = [p for p in home_lineup if get_pos_int(p) != 0]
        home_lineup = ([gks[0]] if gks else []) + non_gks
    
    if away_gk_count != 1:
        # Emergency fix
        gks = [p for p in away_lineup if get_pos_int(p) == 0]
        non_gks = [p for p in away_lineup if get_pos_int(p) != 0]
        away_lineup = ([gks[0]] if gks else []) + non_gks
    
    # Perform substitutions (2-3 per team)
    def make_substitutions(starting_11, all_players):
        """Make 2-3 substitutions, return final lineup and substitution list"""
        if len(all_players) <= 11:
            return starting_11, []
        
        num_subs = random.randint(2, 3)
        used_ids = {p.get('id') for p in starting_11}
        available_subs = [p for p in all_players if p.get('id') not in used_ids and get_pos_int(p) != 0]
        
        if len(available_subs) < num_subs:
            num_subs = len(available_subs)
        
        if num_subs == 0:
            return starting_11, []
        
        # Get non-GK players from starting 11 to substitute out
        non_gk_starters = [p for p in starting_11 if get_pos_int(p) != 0]
        if len(non_gk_starters) < num_subs:
            return starting_11, []
        
        # Select players to sub out (not goalkeeper)
        players_to_sub_out = random.sample(non_gk_starters, num_subs)
        subs_made = []
        final_lineup = starting_11.copy()
        
        for player_out in players_to_sub_out:
            if not available_subs:
                break
            # Select substitute (prefer similar position)
            player_out_pos = get_pos_int(player_out)
            similar_subs = [p for p in available_subs if get_pos_int(p) == player_out_pos]
            
            if similar_subs:
                sub_in = random.choice(similar_subs)
            else:
                sub_in = random.choice(available_subs)
            
            # Replace in lineup
            for i, p in enumerate(final_lineup):
                if p.get('id') == player_out.get('id'):
                    final_lineup[i] = sub_in
                    break
            
            subs_made.append({
                'out': player_out,
                'in': sub_in,
                'minute': random.randint(60, 85)
            })
            available_subs.remove(sub_in)
        
        return final_lineup, subs_made
    
    home_lineup_final, home_subs = make_substitutions(home_lineup, home_players_all)
    away_lineup_final, away_subs = make_substitutions(away_lineup, away_players_all)
    
    # CRITICAL: Validate final lineups after substitutions - ensure still only 1 GK
    home_lineup_final = ensure_one_gk(home_lineup_final)
    away_lineup_final = ensure_one_gk(away_lineup_final)
    
    # Final verification (using get_pos_int)
    if sum(1 for p in home_lineup_final if get_pos_int(p) == 0) != 1:
        gks = [p for p in home_lineup_final if get_pos_int(p) == 0]
        non_gks = [p for p in home_lineup_final if get_pos_int(p) != 0]
        home_lineup_final = ([gks[0]] if gks else []) + non_gks
    
    if sum(1 for p in away_lineup_final if get_pos_int(p) == 0) != 1:
        gks = [p for p in away_lineup_final if get_pos_int(p) == 0]
        non_gks = [p for p in away_lineup_final if get_pos_int(p) != 0]
        away_lineup_final = ([gks[0]] if gks else []) + non_gks
    
    # Calculate minutes played
    def calculate_minutes(lineup, subs_made):
        """Calculate minutes played for all players"""
        minutes = {}
        # All starters get 90 minutes initially
        for p in lineup:
            minutes[p.get('id')] = 90
        
        # Adjust for substitutions
        for sub in subs_made:
            player_out_id = sub['out'].get('id')
            player_in_id = sub['in'].get('id')
            sub_minute = sub['minute']
            minutes[player_out_id] = sub_minute
            minutes[player_in_id] = 90 - sub_minute
        
        return minutes
    
    home_minutes = calculate_minutes(home_lineup, home_subs)
    away_minutes = calculate_minutes(away_lineup, away_subs)
    
    # Calculate strength and scores
    home_strength = sum(p['overall'] for p in home_lineup) / len(home_lineup) if home_lineup else 50
    away_strength = sum(p['overall'] for p in away_lineup) / len(away_lineup) if away_lineup else 50
    strength_diff = (home_strength - away_strength) / 10
    home_expected = max(0.5, 1.5 + strength_diff * 1.5 + 0.3)
    away_expected = max(0.5, 1.5 - strength_diff * 1.5)
    home_score = max(0, min(6, int(random.gauss(home_expected, 0.8))))
    away_score = max(0, min(6, int(random.gauss(away_expected, 0.8))))
    
    # Player stats
    player_stats = []
    stats_dict = {}  # player_id -> stat dict
    
    def get_stat(player_id, player_name, team_id):
        if player_id not in stats_dict:
            stats_dict[player_id] = {
                'player_id': player_id,
                'player_name': player_name,
                'team_id': team_id,
                'goals': 0,
                'assists': 0,
                'played': True,
                'minutes_played': 90,
                'is_starter': 1
            }
            player_stats.append(stats_dict[player_id])
        return stats_dict[player_id]
    
    # Position probabilities
    def score_prob(pos):
        if pos == 0: return 0.0
        elif pos in [2, 3, 4, 6]: return 0.10
        elif pos in [5, 7, 8]: return 0.15
        elif pos in [10]: return 0.20
        elif pos in [11, 12]: return 0.55
        return 0.10
    
    def assist_prob(pos):
        if pos == 0: return 0.01
        elif pos in [2, 3, 4, 6]: return 0.14
        elif pos in [5, 7, 8]: return 0.35
        elif pos in [10]: return 0.25
        elif pos in [11, 12]: return 0.25
        return 0.14
    
    # Distribute goals (NEVER to goalkeepers) - use final lineup after substitutions
    # Probability per player remains constant regardless of team size
    # Not all goals need to be assigned if team is incomplete
    non_gk_home = [p for p in home_lineup_final if get_pos_int(p) != 0]
    for _ in range(home_score):
        if not non_gk_home:
            # Team incomplete - goal not assigned (this is fine)
            continue
        # Calculate weights based on position probability and overall (normalized per player)
        weights = [(p, score_prob(get_pos_int(p)) * p['overall'] / 100) for p in non_gk_home]
        total = sum(w for _, w in weights)
        if total > 0:
            # Use weighted random selection - probability per player is constant
            rand = random.random() * total
            cum = 0
            scorer = None
            for p, w in weights:
                cum += w
                if rand <= cum:
                    scorer = p
                    break
            if scorer:
                get_stat(scorer['id'], scorer['player_name'], home_team_id)['goals'] += 1
                # Assign assist (60% of goals have assists, exclude the scorer to prevent self-assists)
                if random.random() < 0.60:
                    assist_candidates = [p for p in non_gk_home if p['id'] != scorer['id']]
                    if assist_candidates:
                        assist_weights = [(p, assist_prob(get_pos_int(p)) * p['overall'] / 100) for p in assist_candidates]
                        total_assist = sum(w for _, w in assist_weights)
                        if total_assist > 0:
                            rand = random.random() * total_assist
                            cum = 0
                            for p, w in assist_weights:
                                cum += w
                                if rand <= cum:
                                    get_stat(p['id'], p['player_name'], home_team_id)['assists'] += 1
                                    break
                    # If no assist candidates or random check fails, assist is not assigned (realistic)
    
    # Distribute away goals - use final lineup after substitutions
    # Favor higher-rated players and reduce sub scoring likelihood
    non_gk_away = [p for p in away_lineup_final if get_pos_int(p) != 0]
    for _ in range(away_score):
        if not non_gk_away:
            continue
        
        # Calculate weights with minutes factor and squared overall
        weights = []
        for p in non_gk_away:
            player_id = p.get('id')
            minutes = away_minutes.get(player_id, 90)
            minutes_factor = minutes / 90.0
            overall_squared = (p['overall'] ** 2) / 10000
            weight = score_prob(get_pos_int(p)) * overall_squared * minutes_factor
            weights.append((p, weight))
        
        total = sum(w for _, w in weights)
        if total > 0:
            rand = random.random() * total
            cum = 0
            scorer = None
            for p, w in weights:
                cum += w
                if rand <= cum:
                    scorer = p
                    break
            
            if scorer:
                get_stat(scorer['id'], scorer['player_name'], away_team_id)['goals'] += 1
                # Assign assist (60% of goals have assists, exclude the scorer to prevent self-assists)
                if random.random() < 0.60:
                    assist_candidates = [p for p in non_gk_away if p['id'] != scorer['id']]
                    if assist_candidates:
                        # Same weighting for assists
                        assist_weights = []
                        for p in assist_candidates:
                            player_id = p.get('id')
                            minutes = away_minutes.get(player_id, 90)
                            minutes_factor = minutes / 90.0
                            overall_squared = (p['overall'] ** 2) / 10000
                            weight = assist_prob(get_pos_int(p)) * overall_squared * minutes_factor
                            assist_weights.append((p, weight))
                        
                        total_assist = sum(w for _, w in assist_weights)
                        if total_assist > 0:
                            rand = random.random() * total_assist
                            cum = 0
                            for p, w in assist_weights:
                                cum += w
                                if rand <= cum:
                                    get_stat(p['id'], p['player_name'], away_team_id)['assists'] += 1
                                    break
                    # If no assist candidates or random check fails, assist is not assigned (realistic)
    
    # CRITICAL: Final validation RIGHT BEFORE adding to stats - ensure exactly 1 GK per team
    def filter_to_one_gk(lineup):
        """Filter lineup to have exactly 1 goalkeeper"""
        if not lineup or len(lineup) == 0:
            return lineup
        gks = [p for p in lineup if get_pos_int(p) == 0]
        non_gks = [p for p in lineup if get_pos_int(p) != 0]
        if len(gks) > 1:
            return [gks[0]] + non_gks
        elif len(gks) == 1:
            return [gks[0]] + non_gks
        else:
            return non_gks if non_gks else lineup
    
    # CRITICAL: Filter to exactly 1 GK BEFORE any other processing
    def force_one_gk_final(lineup):
        """Force lineup to have exactly 1 goalkeeper - FINAL VERSION"""
        if not lineup:
            return lineup
        gks = [p for p in lineup if p.get('registered_position', -1) == 0]
        non_gks = [p for p in lineup if p.get('registered_position', -1) != 0]
        if len(gks) > 1:
            # Keep only the FIRST (best) goalkeeper
            return [gks[0]] + non_gks[:10]  # Ensure exactly 11 total
        elif len(gks) == 1:
            return [gks[0]] + non_gks[:10]  # Ensure exactly 11 total
        else:
            # No GK - add one if possible
            return non_gks[:11] if len(non_gks) >= 11 else non_gks
    
    home_lineup_final = force_one_gk_final(home_lineup_final)
    away_lineup_final = force_one_gk_final(away_lineup_final)
    
    # CRITICAL: Final verification - count goalkeepers (using get_pos_int)
    home_gk_final_count = sum(1 for p in home_lineup_final if get_pos_int(p) == 0)
    away_gk_final_count = sum(1 for p in away_lineup_final if get_pos_int(p) == 0)
    
    if home_gk_final_count != 1:
        # Emergency: rebuild with exactly 1 GK
        gks_h = [p for p in home_lineup_final if get_pos_int(p) == 0]
        non_gks_h = [p for p in home_lineup_final if get_pos_int(p) != 0]
        home_lineup_final = ([gks_h[0]] if gks_h else []) + non_gks_h[:10]
    
    if away_gk_final_count != 1:
        # Emergency: rebuild with exactly 1 GK
        gks_a = [p for p in away_lineup_final if get_pos_int(p) == 0]
        non_gks_a = [p for p in away_lineup_final if get_pos_int(p) != 0]
        away_lineup_final = ([gks_a[0]] if gks_a else []) + non_gks_a[:10]
    
    # CRITICAL: Ensure lineups are not empty
    if not home_lineup_final or len(home_lineup_final) == 0:
        # Emergency fallback: use first 11 players
        home_lineup_final = home_players_all[:11] if len(home_players_all) >= 11 else home_players_all
        # Ensure at least 1 GK
        gks_home = [p for p in home_lineup_final if get_pos_int(p) == 0]
        if not gks_home:
            # Add best GK if available
            all_gks_home = [p for p in home_players_all if get_pos_int(p) == 0]
            if all_gks_home:
                all_gks_home.sort(key=lambda x: x.get('overall', 0), reverse=True)
                if len(home_lineup_final) >= 11:
                    home_lineup_final = home_lineup_final[:-1]
                home_lineup_final = [all_gks_home[0]] + home_lineup_final
    
    if not away_lineup_final or len(away_lineup_final) == 0:
        # Emergency fallback: use first 11 players
        away_lineup_final = away_players_all[:11] if len(away_players_all) >= 11 else away_players_all
        # Ensure at least 1 GK
        gks_away = [p for p in away_lineup_final if get_pos_int(p) == 0]
        if not gks_away:
            # Add best GK if available
            all_gks_away = [p for p in away_players_all if get_pos_int(p) == 0]
            if all_gks_away:
                all_gks_away.sort(key=lambda x: x.get('overall', 0), reverse=True)
                if len(away_lineup_final) >= 11:
                    away_lineup_final = away_lineup_final[:-1]
                away_lineup_final = [all_gks_away[0]] + away_lineup_final
    
    # CRITICAL: Final, absolute check - remove any extra goalkeepers RIGHT BEFORE adding to stats
    def remove_extra_gks_absolute(lineup):
        """Remove ALL extra goalkeepers, keep only the first one"""
        if not lineup:
            return lineup
        gks = [p for p in lineup if get_pos_int(p) == 0]
        non_gks = [p for p in lineup if get_pos_int(p) != 0]
        if len(gks) > 1:
            # Keep ONLY the first goalkeeper, remove all others
            return [gks[0]] + non_gks
        elif len(gks) == 1:
            return [gks[0]] + non_gks
        else:
            return non_gks
    
    home_lineup_final = remove_extra_gks_absolute(home_lineup_final)
    away_lineup_final = remove_extra_gks_absolute(away_lineup_final)
    
    # Verify one more time (using get_pos_int)
    home_gk_count_final = sum(1 for p in home_lineup_final if get_pos_int(p) == 0)
    away_gk_count_final = sum(1 for p in away_lineup_final if get_pos_int(p) == 0)
    
    if home_gk_count_final > 1:
        # Last resort: rebuild completely
        gks_h = [p for p in home_lineup_final if get_pos_int(p) == 0]
        non_gks_h = [p for p in home_lineup_final if get_pos_int(p) != 0]
        home_lineup_final = [gks_h[0]] + non_gks_h[:10]
    
    if away_gk_count_final > 1:
        # Last resort: rebuild completely
        gks_a = [p for p in away_lineup_final if get_pos_int(p) == 0]
        non_gks_a = [p for p in away_lineup_final if get_pos_int(p) != 0]
        away_lineup_final = [gks_a[0]] + non_gks_a[:10]
    
    # Add all players who played (starters and substitutes)
    all_played_ids = set()
    
    # IMPORTANT: Use home_lineup (original starting 11) for starters, NOT home_lineup_final (after subs)
    # Add starters (home) - ONLY ONE GOALKEEPER ALLOWED
    home_gk_added = False
    for p in home_lineup:  # Use original lineup, not final lineup
        pid = p.get('id')
        pos = get_pos_int(p)
        # CRITICAL: Only add ONE goalkeeper per team, skip any extras
        if pos == 0:
            if not home_gk_added and pid not in all_played_ids:
                stat = get_stat(pid, p.get('player_name', 'Unknown'), home_team_id)
                stat['minutes_played'] = home_minutes.get(pid, 90)
                stat['is_starter'] = 1  # Explicitly set as starter
                all_played_ids.add(pid)
                home_gk_added = True
            # SKIP any additional goalkeepers - DO NOT ADD THEM
        elif pid not in all_played_ids:
            stat = get_stat(pid, p.get('player_name', 'Unknown'), home_team_id)
            stat['minutes_played'] = home_minutes.get(pid, 90)
            stat['is_starter'] = 1  # Explicitly set as starter
            all_played_ids.add(pid)
    
    # Add substitutes (home) - NEVER goalkeepers
    for sub in home_subs:
        pid = sub['in'].get('id')
        pos = get_pos_int(sub['in'])
        if pos != 0:  # Never add goalkeeper substitutes
            # Get or create stat - ALWAYS set as substitute, even if already exists
            stat = get_stat(pid, sub['in'].get('player_name', 'Unknown'), home_team_id)
            stat['minutes_played'] = home_minutes.get(pid, 0)
            stat['is_starter'] = 0  # CRITICAL: Always set as substitute (override any previous value)
            all_played_ids.add(pid)
    
    # IMPORTANT: Use away_lineup (original starting 11) for starters, NOT away_lineup_final (after subs)
    # Add starters (away) - ONLY ONE GOALKEEPER ALLOWED
    away_gk_added = False
    for p in away_lineup:  # Use original lineup, not final lineup
        pid = p.get('id')
        pos = get_pos_int(p)
        # CRITICAL: Only add ONE goalkeeper per team, skip any extras
        if pos == 0:
            if not away_gk_added and pid not in all_played_ids:
                stat = get_stat(pid, p.get('player_name', 'Unknown'), away_team_id)
                stat['minutes_played'] = away_minutes.get(pid, 90)
                stat['is_starter'] = 1  # Explicitly set as starter
                all_played_ids.add(pid)
                away_gk_added = True
            # SKIP any additional goalkeepers - DO NOT ADD THEM
        elif pid not in all_played_ids:
            stat = get_stat(pid, p.get('player_name', 'Unknown'), away_team_id)
            stat['minutes_played'] = away_minutes.get(pid, 90)
            stat['is_starter'] = 1  # Explicitly set as starter
            all_played_ids.add(pid)
    
    # Add substitutes (away) - NEVER goalkeepers
    for sub in away_subs:
        pid = sub['in'].get('id')
        pos = get_pos_int(sub['in'])
        if pos != 0:  # Never add goalkeeper substitutes
            # Get or create stat - ALWAYS set as substitute, even if already exists
            stat = get_stat(pid, sub['in'].get('player_name', 'Unknown'), away_team_id)
            stat['minutes_played'] = away_minutes.get(pid, 0)
            stat['is_starter'] = 0  # CRITICAL: Always set as substitute (override any previous value)
            all_played_ids.add(pid)
    
    # Select MVP - GUARANTEED to return a valid player ID
    winning_team = home_team_id if home_score > away_score else (away_team_id if away_score > home_score else None)
    contributors = [s for s in player_stats if s.get('goals', 0) > 0 or s.get('assists', 0) > 0]
    
    mvp_player_id = None
    
    if contributors:
        if winning_team:
            winning_contribs = [s for s in contributors if s.get('team_id') == winning_team]
            if winning_contribs:
                mvp_player_id = max(winning_contribs, key=lambda x: x.get('goals', 0) * 3 + x.get('assists', 0) * 2).get('player_id')
            else:
                mvp_player_id = max(contributors, key=lambda x: x.get('goals', 0) * 3 + x.get('assists', 0) * 2).get('player_id')
        else:
            mvp_player_id = max(contributors, key=lambda x: x.get('goals', 0) * 3 + x.get('assists', 0) * 2).get('player_id')
    
    # Fallback: best overall from winning team (non-GK)
    if not mvp_player_id:
        if winning_team:
            winning_lineup = home_lineup_final if winning_team == home_team_id else away_lineup_final
            non_gk = [p for p in winning_lineup if get_pos_int(p) != 0]
            if non_gk:
                mvp_player_id = max(non_gk, key=lambda x: x.get('overall', 0)).get('id')
            elif winning_lineup:
                mvp_player_id = max(winning_lineup, key=lambda x: x.get('overall', 0)).get('id')
        else:
            all_players = home_lineup_final + away_lineup_final
            non_gk = [p for p in all_players if get_pos_int(p) != 0]
            if non_gk:
                mvp_player_id = max(non_gk, key=lambda x: x.get('overall', 0)).get('id')
            elif all_players:
                mvp_player_id = max(all_players, key=lambda x: x.get('overall', 0)).get('id')
    
    # Final fallback: any player from lineups
    if not mvp_player_id:
        if home_lineup_final:
            mvp_player_id = home_lineup_final[0].get('id')
        elif away_lineup_final:
            mvp_player_id = away_lineup_final[0].get('id')
        elif player_stats:
            mvp_player_id = player_stats[0].get('player_id')
    
    # CRITICAL: Ensure MVP is always a valid player ID (not None)
    if not mvp_player_id and player_stats:
        # Last resort: use first player in stats
        mvp_player_id = player_stats[0].get('player_id')
    
    return {
        'home_score': home_score,
        'away_score': away_score,
        'player_stats': player_stats,
        'mvp_player_id': mvp_player_id
    }
