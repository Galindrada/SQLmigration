#!/usr/bin/env python3
"""
CPU League Financial System

Calculates match-day revenues for CPU league games:
1. Attendance Revenue (home team only) - based on team market value and league position
2. Sponsor Premium (both teams) - based on division tier (Division 1 > Division 2)
3. Merchandise Revenue (both teams) - based on team market value and star players
4. Prize Bonus (winner or split) - match result bonus

All financial data is stored in league_games table and added to team budgets.
"""

import sqlite3
import random
from typing import Dict, Tuple

# Base financial values (reduced to 40% for final tuning)
# Target: €100M-€320M per season Tier 1, €40M-€128M Tier 2
BASE_ATTENDANCE_MULTIPLIER = 0.0128 # 1.28% of team market value potential (40% of 3.2%)
BASE_SPONSOR_DIVISION_1 = 1600000   # €1.6M per game for Division 1 (40% of 4.0M)
BASE_SPONSOR_DIVISION_2 = 960000    # €960k per game for Division 2 (40% of 2.4M)
BASE_SPONSOR_DIVISION_3 = 480000    # €480k per game for Division 3+ (40% of 1.2M)
BASE_MERCHANDISE = 0.0168           # 1.68% of team market value (40% of 4.2%)
STAR_PLAYER_BONUS = 24000           # €24k per star player (40% of 60k)
STAR_PLAYER_THRESHOLD = 50000000    # €50M market value
WIN_BONUS = 3400000                 # €3.4M for winning (40% of 8.5M)
DRAW_BONUS = 1700000                # €1.7M for draw (40% of 4.25M)
BASE_TV_RIGHTS_MULTIPLIER = 0.028   # 2.8% of team total salary expense (40% of 7.0%)

# Randomness ranges (±percentage)
ATTENDANCE_VARIANCE = 0.15         # ±15% randomness
SPONSOR_VARIANCE = 0.10            # ±10% randomness
MERCHANDISE_VARIANCE = 0.12        # ±12% randomness
TV_RIGHTS_VARIANCE = 0.08          # ±8% randomness

# Tier multipliers
TIER_1_MULTIPLIER = 1.0            # 100% of base values
TIER_2_MULTIPLIER = 0.40           # 40% of base values (60% reduction)


def get_team_market_value(cursor, team_id: int) -> int:
    """Get total market value of a team"""
    cursor.execute("""
        SELECT COALESCE(SUM(market_value), 0) as total_mv
        FROM players
        WHERE club_id = ?
    """, (team_id,))
    result = cursor.fetchone()
    return result[0] if result else 0


def get_team_star_players(cursor, team_id: int) -> int:
    """Count star players (market value > threshold) up to 5"""
    cursor.execute("""
        SELECT COUNT(*) as star_count
        FROM (
            SELECT id
            FROM players
            WHERE club_id = ? AND market_value > ?
            ORDER BY market_value DESC
            LIMIT 5
        )
    """, (team_id, STAR_PLAYER_THRESHOLD))
    result = cursor.fetchone()
    return result[0] if result else 0


def get_team_total_salaries(cursor, team_id: int) -> int:
    """Get total salary expense for a team"""
    cursor.execute("""
        SELECT COALESCE(SUM(salary), 0) as total_salaries
        FROM players
        WHERE club_id = ?
    """, (team_id,))
    result = cursor.fetchone()
    return result[0] if result else 0


def apply_randomness(value: int, variance: float) -> int:
    """Apply random variance to a value"""
    if value == 0:
        return 0
    # Random multiplier between (1 - variance) and (1 + variance)
    multiplier = random.uniform(1.0 - variance, 1.0 + variance)
    return int(value * multiplier)


def get_division_tier_from_db(cursor, division_id: int) -> int:
    """Get division tier from database (1 or 2)"""
    cursor.execute("SELECT tier FROM divisions WHERE id = ?", (division_id,))
    result = cursor.fetchone()
    return result[0] if result and result[0] else 1  # Default to tier 1


def apply_tier_multiplier(value: int, tier: int) -> int:
    """Apply tier multiplier to financial value"""
    if tier == 2:
        return int(value * TIER_2_MULTIPLIER)
    return value  # Tier 1 gets full value


def get_team_league_position(cursor, division_id: int, team_name: str) -> int:
    """Get team's current position in the division (1-based)"""
    cursor.execute("""
        SELECT team_name, points, goal_difference, goals_for
        FROM division_standings
        WHERE division_id = ?
        ORDER BY points DESC, goal_difference DESC, goals_for DESC
    """, (division_id,))
    
    standings = cursor.fetchall()
    for position, row in enumerate(standings, 1):
        if row[0] == team_name:
            return position
    
    return len(standings)  # Default to last position if not found


def calculate_attendance_revenue(
    team_market_value: int,
    league_position: int,
    total_teams: int,
    tier: int = 1
) -> int:
    """
    Calculate attendance revenue (home team only) with randomness and tier adjustment.
    
    Formula:
    - Base: 15% of team market value
    - Position bonus: 70% weighted by league position
    - Randomness: ±15%
    - Tier adjustment: Tier 2 = 40% of Tier 1
    """
    # Base attendance from market value
    base_attendance = int(team_market_value * BASE_ATTENDANCE_MULTIPLIER)
    
    # Position factor (1.0 for 1st place, 0.3 for last place)
    if total_teams > 1:
        position_factor = 1.0 - ((league_position - 1) / (total_teams - 1)) * 0.7
    else:
        position_factor = 1.0
    
    # 70% of base is affected by position, 30% is guaranteed
    guaranteed_component = int(base_attendance * 0.30)
    position_component = int(base_attendance * 0.70 * position_factor)
    
    total_attendance = guaranteed_component + position_component
    
    # Apply tier multiplier
    total_attendance = apply_tier_multiplier(total_attendance, tier)
    
    # Apply randomness
    total_attendance = apply_randomness(total_attendance, ATTENDANCE_VARIANCE)
    
    return max(0, total_attendance)


def calculate_sponsor_premium(tier: int = 1) -> int:
    """
    Calculate sponsor premium based on tier with randomness.
    
    Base: €500k per game (Tier 1)
    Tier 2: 40% of Tier 1 (€200k)
    Randomness: ±10%
    """
    base = BASE_SPONSOR_DIVISION_1
    
    # Apply tier multiplier
    base = apply_tier_multiplier(base, tier)
    
    # Apply randomness
    return apply_randomness(base, SPONSOR_VARIANCE)


def calculate_merchandise_revenue(
    team_market_value: int,
    star_player_count: int,
    tier: int = 1
) -> int:
    """
    Calculate merchandise revenue with randomness and tier adjustment.
    
    Formula:
    - 50% based on total team market value (8% of MV)
    - 50% based on star players
    - Randomness: ±12%
    - Tier adjustment: Tier 2 = 40% of Tier 1
    """
    # Base merchandise from market value
    base_merch = int(team_market_value * BASE_MERCHANDISE)
    mv_component = int(base_merch * 0.50)
    
    # Star player component
    star_component = int(base_merch * 0.50 * (star_player_count / 5.0))
    
    total_merchandise = mv_component + star_component
    
    # Apply tier multiplier
    total_merchandise = apply_tier_multiplier(total_merchandise, tier)
    
    # Apply randomness
    total_merchandise = apply_randomness(total_merchandise, MERCHANDISE_VARIANCE)
    
    return max(0, total_merchandise)


def calculate_tv_rights_revenue(
    team_total_salaries: int,
    tier: int = 1
) -> int:
    """
    Calculate TV rights revenue based on team salary expense with diminishing returns.
    
    Formula:
    - Base: 12% of team total salary expense
    - Diminishing returns for very high salaries (cap effect)
    - Higher salaries = more TV appeal = more revenue
    - Randomness: ±8%
    - Tier adjustment: Tier 2 = 40% of Tier 1
    """
    # Apply diminishing returns for very high salaries
    # Use logarithmic scaling above €150M to prevent extreme outliers
    if team_total_salaries > 150000000:
        # Split into base (150M) and excess
        base_component = 150000000 * BASE_TV_RIGHTS_MULTIPLIER
        excess = team_total_salaries - 150000000
        # Excess has strong diminishing returns (30% efficiency)
        excess_component = excess * BASE_TV_RIGHTS_MULTIPLIER * 0.30
        base_tv_rights = int(base_component + excess_component)
    else:
        base_tv_rights = int(team_total_salaries * BASE_TV_RIGHTS_MULTIPLIER)
    
    # Apply tier multiplier
    base_tv_rights = apply_tier_multiplier(base_tv_rights, tier)
    
    # Apply randomness
    tv_rights = apply_randomness(base_tv_rights, TV_RIGHTS_VARIANCE)
    
    return max(0, tv_rights)


def calculate_prize_bonus(home_score: int, away_score: int, tier: int = 1) -> Tuple[int, int]:
    """
    Calculate prize bonus based on match result with tier adjustment.
    
    Win: €300k to winner
    Draw: €150k split (€75k each)
    Tier 2: 40% of base values
    """
    win_bonus = apply_tier_multiplier(WIN_BONUS, tier)
    draw_bonus = apply_tier_multiplier(DRAW_BONUS, tier)
    
    if home_score > away_score:
        # Home win
        return (win_bonus, 0)
    elif away_score > home_score:
        # Away win
        return (0, win_bonus)
    else:
        # Draw - split the draw bonus
        split_bonus = draw_bonus // 2
        return (split_bonus, split_bonus)


def calculate_game_finances(
    cursor,
    game_id: int,
    division_id: int,
    division_name: str,
    home_team_id: int,
    away_team_id: int,
    home_team_name: str,
    away_team_name: str,
    home_score: int,
    away_score: int
) -> Dict:
    """
    Calculate all financial components for a game including TV rights.
    
    Returns dictionary with all financial data.
    """
    
    # Get division tier from database
    tier = get_division_tier_from_db(cursor, division_id)
    
    # Get team market values
    home_mv = get_team_market_value(cursor, home_team_id)
    away_mv = get_team_market_value(cursor, away_team_id)
    
    # Get team salary expenses
    home_salaries = get_team_total_salaries(cursor, home_team_id)
    away_salaries = get_team_total_salaries(cursor, away_team_id)
    
    # Get star player counts
    home_stars = get_team_star_players(cursor, home_team_id)
    away_stars = get_team_star_players(cursor, away_team_id)
    
    # Get league positions
    cursor.execute("SELECT COUNT(*) FROM division_standings WHERE division_id = ?", (division_id,))
    total_teams = cursor.fetchone()[0]
    
    home_position = get_team_league_position(cursor, division_id, home_team_name)
    
    # Calculate each component with tier and randomness
    home_attendance = calculate_attendance_revenue(home_mv, home_position, total_teams, tier)
    
    home_sponsor = calculate_sponsor_premium(tier)
    away_sponsor = calculate_sponsor_premium(tier)
    
    home_merch = calculate_merchandise_revenue(home_mv, home_stars, tier)
    away_merch = calculate_merchandise_revenue(away_mv, away_stars, tier)
    
    home_tv_rights = calculate_tv_rights_revenue(home_salaries, tier)
    away_tv_rights = calculate_tv_rights_revenue(away_salaries, tier)
    
    home_prize, away_prize = calculate_prize_bonus(home_score, away_score, tier)
    
    # Calculate totals
    home_total = home_attendance + home_sponsor + home_merch + home_tv_rights + home_prize
    away_total = away_sponsor + away_merch + away_tv_rights + away_prize
    
    return {
        'home_attendance_revenue': home_attendance,
        'home_sponsor_premium': home_sponsor,
        'away_sponsor_premium': away_sponsor,
        'home_merchandise_revenue': home_merch,
        'away_merchandise_revenue': away_merch,
        'home_tv_rights_revenue': home_tv_rights,
        'away_tv_rights_revenue': away_tv_rights,
        'home_prize_bonus': home_prize,
        'away_prize_bonus': away_prize,
        'home_total_earnings': home_total,
        'away_total_earnings': away_total,
        # Metadata for reporting
        'home_market_value': home_mv,
        'away_market_value': away_mv,
        'home_total_salaries': home_salaries,
        'away_total_salaries': away_salaries,
        'home_star_players': home_stars,
        'away_star_players': away_stars,
        'home_league_position': home_position,
        'tier': tier,
        'total_teams': total_teams
    }


def apply_game_finances_to_database(cursor, game_id: int, finances: Dict):
    """
    Update league_games table with financial data and add to team budgets.
    """
    
    # Update league_games table
    cursor.execute("""
        UPDATE league_games
        SET home_attendance_revenue = ?,
            home_sponsor_premium = ?,
            away_sponsor_premium = ?,
            home_merchandise_revenue = ?,
            away_merchandise_revenue = ?,
            home_tv_rights_revenue = ?,
            away_tv_rights_revenue = ?,
            home_prize_bonus = ?,
            away_prize_bonus = ?,
            home_total_earnings = ?,
            away_total_earnings = ?
        WHERE id = ?
    """, (
        finances['home_attendance_revenue'],
        finances['home_sponsor_premium'],
        finances['away_sponsor_premium'],
        finances['home_merchandise_revenue'],
        finances['away_merchandise_revenue'],
        finances['home_tv_rights_revenue'],
        finances['away_tv_rights_revenue'],
        finances['home_prize_bonus'],
        finances['away_prize_bonus'],
        finances['home_total_earnings'],
        finances['away_total_earnings'],
        game_id
    ))
    
    # Get team IDs from the game
    cursor.execute("SELECT home_team_id, away_team_id FROM league_games WHERE id = ?", (game_id,))
    result = cursor.fetchone()
    if not result:
        return
    
    home_team_id, away_team_id = result
    
    # Add earnings to team budgets
    cursor.execute("""
        UPDATE teams
        SET budget = budget + ?
        WHERE id = ?
    """, (finances['home_total_earnings'], home_team_id))
    
    cursor.execute("""
        UPDATE teams
        SET budget = budget + ?
        WHERE id = ?
    """, (finances['away_total_earnings'], away_team_id))


def process_game_finances(game_id: int, db_path: str = 'pes6_league_db.sqlite') -> Dict:
    """
    Main function to process finances for a completed game.
    
    Args:
        game_id: ID of the game in league_games table
        db_path: Path to database
    
    Returns:
        Dictionary with financial breakdown
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # Get game details
        cursor.execute("""
            SELECT lg.*, d.name as division_name
            FROM league_games lg
            JOIN divisions d ON lg.division_id = d.id
            WHERE lg.id = ? AND lg.is_played = 1
        """, (game_id,))
        
        game = cursor.fetchone()
        if not game:
            return {'error': 'Game not found or not played'}
        
        # Calculate finances
        finances = calculate_game_finances(
            cursor,
            game['id'],
            game['division_id'],
            game['division_name'],
            game['home_team_id'],
            game['away_team_id'],
            game['home_team_name'],
            game['away_team_name'],
            game['home_score'],
            game['away_score']
        )
        
        # Apply to database
        apply_game_finances_to_database(cursor, game_id, finances)
        
        conn.commit()
        
        return finances
        
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()


if __name__ == "__main__":
    # Test with a sample game
    print("CPU League Finances Module")
    print("Import this module to use financial calculations")

