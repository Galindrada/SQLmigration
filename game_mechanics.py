import pandas as pd
import numpy as np
import random
import math
import sqlite3
import re
from typing import Dict, List, Optional, Tuple

# --- Global Constants ---
GLOBAL_BASE_SALARY = 300000
SEED_VALUE = 40
random.seed(SEED_VALUE)
np.random.seed(SEED_VALUE)

# --- Helper Functions ---
def clean_sql_col_name(col_name: str) -> str:
    """Clean column name for SQL compatibility"""
    s = str(col_name)
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[-\s]+', '_', s)
    if s and s[0].isdigit():
        s = '_' + s
    if not s:
        s = 'unnamed_column'
    return s

def identify_true_skill_columns(df: pd.DataFrame, non_skill_cols_list: List[str]) -> List[str]:
    """Identify numeric skill columns from the dataframe"""
    potential_skill_cols = []
    non_skill_cols_cleaned = [' '.join(col.split()) for col in non_skill_cols_list]
    
    for col in df.columns:
        if col not in non_skill_cols_cleaned:
            temp_series = pd.to_numeric(df[col], errors='coerce')
            if pd.api.types.is_numeric_dtype(temp_series) and not pd.api.types.is_bool_dtype(temp_series):
                if temp_series.isna().sum() < len(df) * 0.5:
                    potential_skill_cols.append(col)
    return potential_skill_cols

def analyze_skill_averages_by_position(df: pd.DataFrame, current_skill_columns: List[str]) -> Optional[pd.DataFrame]:
    """Analyze skill averages by position"""
    if 'REGISTERED POSITION' not in df.columns:
        print("AnalyzeSkills Error: 'REGISTERED POSITION' column not found.")
        return None
    
    if not current_skill_columns:
        print("AnalyzeSkills Error: No skill columns provided.")
        return None
    
    valid_cols = []
    df_copy = df.copy()
    
    for col in current_skill_columns:
        if col in df_copy.columns:
            df_copy[col] = pd.to_numeric(df_copy[col], errors='coerce')
            valid_cols.append(col)
    
    if not valid_cols:
        print("AnalyzeSkills Error: No valid skill columns for averaging.")
        return None
    
    try:
        pos_avg = df_copy.groupby('REGISTERED POSITION')[valid_cols].mean()
        return pos_avg
    except Exception as e:
        print(f"AnalyzeSkills Error during averaging: {e}")
        return None

def identify_binary_skills(df: pd.DataFrame, skill_cols_list: List[str]) -> List[str]:
    """Identify binary skill columns (0/1 values)"""
    b_cand = []
    for col in skill_cols_list:
        if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
            un_val = df[col].dropna().unique()
            if all(v in [0, 1] for v in un_val) and len(un_val) > 0:
                b_cand.append(col)
    return b_cand

# --- Core Salary and Market Value Functions ---
def calculate_player_salary_base(player_row: pd.Series, pos_avg_df: pd.DataFrame, 
                                skills: List[str], binaries: List[str]) -> int:
    """
    Calculate base salary for a player based on their skills and position.
    
    Args:
        player_row: Player data row from dataframe
        pos_avg_df: Position-specific skill averages dataframe
        skills: List of skill column names
        binaries: List of binary skill column names
    
    Returns:
        Calculated base salary (integer)
    """
    # Parameters from the original model
    NORM = 75.0
    BIN_IMPACT = 0.15
    R_START = 70.0
    R_END = 99.0
    MIN_MULT = 0.5
    MAX_MULT = 4.0
    DEF_BOOST = 4.0
    GK_BOOST = 4.0
    DEF_NAME = 'DEFENSE'
    GK_NAME = 'GOAL KEEPING'
    DIV = 1000.0
    POW = 3.0
    SCALER = 1170000.0
    
    pos = player_row['registered_position']
    pos_clean = pos if pd.notna(pos) else 'Unknown Position'
    
    if pos_avg_df is None or pos_clean not in pos_avg_df.index:
        pos_spec_avg = pd.Series(NORM, index=skills)
    else:
        pos_spec_avg = pos_avg_df.loc[pos_clean]
        if not isinstance(pos_spec_avg, pd.Series):
            pos_spec_avg = pd.Series(NORM, index=skills)

    twss = 0
    for skill_n in skills:
        if skill_n not in player_row or pd.isna(player_row[skill_n]):
            continue
        
        val = float(player_row[skill_n])
        mult = MIN_MULT
        
        if val >= R_END:
            mult = MAX_MULT
        elif val > R_START:
            prog = (val - R_START) / (R_END - R_START)
            if MIN_MULT > 0 or MAX_MULT > 0:
                if MIN_MULT == 0 and MAX_MULT > 0:
                    mult = MAX_MULT * math.pow(prog, 2)
                elif MIN_MULT > 0:
                    mult = MIN_MULT * math.pow(MAX_MULT / MIN_MULT, prog)
        
        eff_val = val * mult
        skill_imp_val = pos_spec_avg.get(skill_n, NORM) if isinstance(pos_spec_avg, pd.Series) else NORM
        imp = skill_imp_val / NORM
        contrib = eff_val * imp
        
        if skill_n == DEF_NAME:
            contrib *= DEF_BOOST
        elif skill_n == GK_NAME:
            contrib *= GK_BOOST
        
        if skill_n in binaries:
            contrib *= BIN_IMPACT
        
        twss += contrib
    
    twss = max(0, twss)
    norm_twss = twss / DIV
    pow_score = math.pow(max(0, norm_twss), POW)
    sal_skills = pow_score * SCALER
    calc_sal = GLOBAL_BASE_SALARY + sal_skills
    
    return max(GLOBAL_BASE_SALARY, round(calc_sal / 1000) * 1000)

def apply_random_salary_adjustment(base_salary: int) -> int:
    """Apply random adjustment to base salary"""
    factor = random.uniform(-0.20, 0.20)
    adj_sal = base_salary * (1 + factor)
    return round(max(GLOBAL_BASE_SALARY, adj_sal) / 1000) * 1000

def get_age_market_value_multiplier(age_val) -> float:
    """Get market value multiplier based on player age"""
    if pd.isna(age_val):
        return 1.0
    
    age = float(age_val)
    y_ref, y_fact = 16.0, 4.0
    p_ref, p_fact = 29.0, 1.0
    o_ref, o_fact = 40.0, 0.01
    k_y, k_o = 1.5, 3.0
    
    if age <= y_ref:
        return y_fact
    elif age < p_ref:
        prog = (age - y_ref) / (p_ref - y_ref)
        return p_fact + (y_fact - p_fact) * math.pow(1-prog, k_y)
    elif age == p_ref:
        return p_fact
    elif age < o_ref:
        prog = (age - p_ref) / (o_ref - p_ref)
        return o_fact + (p_fact - o_fact) * math.pow(1-prog, k_o)
    else:
        return o_fact

def determine_contract_years(age_val) -> int:
    """Determine contract years based on player age"""
    if pd.isna(age_val):
        return random.randint(2, 3)
    
    try:
        age = int(float(age_val))
    except ValueError:
        return random.randint(2, 3)
    
    if age > 32:
        return random.randint(1, 2)
    elif age > 30:
        return random.randint(1, 3)
    else:
        return random.randint(2, 5)

def calculate_yearly_wage_raise(player_row: pd.Series, skills: List[str], 
                              binaries: List[str], salary: int) -> float:
    """Calculate yearly wage raise percentage for a player"""
    age_val = player_row['age']
    try:
        age = int(float(age_val)) if pd.notna(age_val) else 25
    except ValueError:
        age = 25
    
    num_skills = [s for s in skills if s not in binaries and s in player_row and pd.notna(player_row[s])]
    
    if not num_skills:
        avg_skill = 60.0
    else:
        avg_skill = pd.to_numeric(player_row[num_skills], errors='coerce').mean()
        if pd.isna(avg_skill):
            avg_skill = 60.0
    
    rp = 0.0
    
    if age <= 23 and avg_skill >= 78:
        rp = random.uniform(0.15, 0.25)
    elif age <= 23 and avg_skill >= 70:
        rp = random.uniform(0.10, 0.20)
    elif age <= 26 and avg_skill >= 75:
        rp = random.uniform(0.08, 0.18)
    elif age <= 29 and avg_skill >= 72:
        rp = random.uniform(0.05, 0.12)
    elif age > 32 or avg_skill < 65:
        rp = random.uniform(0.00, 0.05)
    else:
        rp = random.uniform(0.03, 0.08)
    
    if salary < (GLOBAL_BASE_SALARY * 5):
        rp *= 1.1
    
    return round(min(rp, 0.25), 3)

# --- Main Calculator Function ---
def calculate_position_averages_from_db(db_path: str) -> pd.DataFrame:
    """
    Calculate position-specific skill averages from the database.
    
    Args:
        db_path: Path to the SQLite database
    
    Returns:
        DataFrame with position averages for each skill
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get all players with their skills
        cursor.execute("""
            SELECT registered_position, 
                   attack, defense, balance, stamina, top_speed, acceleration,
                   response, agility, dribble_accuracy, dribble_speed,
                   short_pass_accuracy, short_pass_speed, long_pass_accuracy, long_pass_speed,
                   shot_accuracy, shot_power, shot_technique, free_kick_accuracy, swerve,
                   heading, jump, technique, aggression, mentality, goal_keeping,
                   team_work, consistency, condition_fitness, dribbling_skill, tactical_dribble,
                   positioning, reaction, playmaking, passing, scoring, one_one_scoring,
                   post_player, lines, middle_shooting, side, centre, penalties,
                   one_touch_pass, outside, marking, sliding, covering, d_line_control,
                   penalty_stopper, one_on_one_stopper, long_throw
            FROM players 
            WHERE club_id != 141  -- Exclude No Club players
        """)
        
        players = cursor.fetchall()
        
        if not players:
            print("No players found for position averages calculation")
            return None
        
        # Convert to DataFrame
        columns = [description[0] for description in cursor.description]
        df = pd.DataFrame(players, columns=columns)
        
        # Convert numeric columns
        skill_columns = [col for col in columns if col != 'registered_position']
        for col in skill_columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Calculate position averages
        position_averages = df.groupby('registered_position')[skill_columns].mean()
        
        conn.close()
        
        print(f"✅ Calculated position averages for {len(position_averages)} positions")
        return position_averages
        
    except Exception as e:
        print(f"Error calculating position averages: {e}")
        if conn:
            conn.close()
        return None

def check_player_retirement(player_data: Dict) -> Dict:
    """
    Check if a player wants to retire based on age, salary, and club status.
    
    Args:
        player_data: Dictionary containing player information
    
    Returns:
        Dictionary with retirement check results
    """
    age = player_data.get('age', 25)
    salary = player_data.get('salary', GLOBAL_BASE_SALARY)
    club_id = player_data.get('club_id')
    
    # Base retirement probability starts at age 30
    if age < 30:
        return {
            'wants_to_retire': False,
            'retirement_probability': 0.0,
            'reason': 'Too young to consider retirement'
        }
    
    # Calculate base retirement probability based on age
    # Probability increases with age - reduced age factor for more moderate progression
    age_factor = (age - 30) / 13.0  # 0 at age 30, 1 at age 44 (slightly slower increase)
    age_probability = min(0.8, age_factor * 0.75)  # Max 90% at age 44+, moderate base rate
    
    # Salary factor - higher salary reduces retirement probability
    # Normalize salary to 0-1 range (0 = low salary, 1 = high salary)
    salary_normalized = min(1.0, salary / (GLOBAL_BASE_SALARY * 15))  # 15x base salary = max
    salary_factor = 1.0 - salary_normalized  # Higher salary = lower retirement chance
    
    # Club status factor - No Club players more likely to retire
    club_factor = 0.0
    if club_id == 141 or club_id is None:  # No Club
        club_factor = 0.25  # 25% additional probability (reduced from 30%)
    
    # Calculate final retirement probability
    base_probability = age_probability
    salary_adjustment = salary_factor * 0.3  # Salary can reduce probability by up to 30%
    final_probability = base_probability + club_factor - salary_adjustment
    
    # Clamp probability between 0 and 1
    final_probability = max(0.0, min(1.0, final_probability))
    
    # Generate random number to determine retirement
    random_value = random.random()
    wants_to_retire = random_value < final_probability
    
    # Generate reason for retirement decision
    if wants_to_retire:
        if club_id == 141 or club_id is None:
            reason = f"Retired due to age ({age}) and being without a club"
        elif salary < GLOBAL_BASE_SALARY * 2:
            reason = f"Retired due to age ({age}) and low salary (€{salary:,})"
        else:
            reason = f"Retired due to age ({age}) despite good salary (€{salary:,})"
    else:
        if salary > GLOBAL_BASE_SALARY * 10:
            reason = f"Continues due to high salary (€{salary:,}) despite age ({age})"
        elif club_id != 141 and club_id is not None:
            reason = f"Continues due to being under contract at age ({age})"
        else:
            reason = f"Continues despite age ({age}) and current circumstances"
    
    return {
        'wants_to_retire': wants_to_retire,
        'retirement_probability': final_probability,
        'reason': reason,
        'age_factor': age_probability,
        'salary_factor': salary_factor,
        'club_factor': club_factor
    }

def apply_market_value_adjustment(market_value: int) -> int:
    """Apply random adjustment to market value (similar to salary but with different range)"""
    # Market values can vary more than salaries, so use a wider range
    factor = random.uniform(-0.15, 0.25)  # -15% to +25% variation
    adj_mv = market_value * (1 + factor)
    return max(0, round(adj_mv / 1000) * 1000)  # Round to nearest 1000

def calculate_player_financials(player_data: Dict, db_path: str = 'pes6_league_db.sqlite') -> Dict:
    """
    Calculate salary and market value for a single player.
    
    Args:
        player_data: Dictionary containing player information with skills
        db_path: Path to the database for position averages calculation
    
    Returns:
        Dictionary with calculated financial data
    """
    # Convert to pandas Series for compatibility
    player_row = pd.Series(player_data)
    
    # Define skill columns (these should match your database schema)
    skill_columns = [
        'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
        'response', 'agility', 'dribble_accuracy', 'dribble_speed',
        'short_pass_accuracy', 'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed',
        'shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy', 'swerve',
        'heading', 'jump', 'technique', 'aggression', 'mentality', 'goal_keeping',
        'team_work', 'consistency', 'condition_fitness', 'dribbling_skill', 'tactical_dribble',
        'positioning', 'reaction', 'playmaking', 'passing', 'scoring', 'one_one_scoring',
        'post_player', 'lines', 'middle_shooting', 'side', 'centre', 'penalties',
        'one_touch_pass', 'outside', 'marking', 'sliding', 'covering', 'd_line_control',
        'penalty_stopper', 'one_on_one_stopper', 'long_throw'
    ]
    
    # Identify binary skills
    binary_skills = identify_binary_skills(pd.DataFrame([player_data]), skill_columns)
    
    # Calculate position averages from database
    pos_avg_df = calculate_position_averages_from_db(db_path)
    
    # Calculate base salary (before random adjustments)
    base_salary = calculate_player_salary_base(player_row, pos_avg_df, skill_columns, binary_skills)
    
    # Calculate market value based on BASE salary (not final salary)
    # This matches the original model.py logic
    market_value = base_salary * 1.5  # Base multiplier
    age_multiplier = get_age_market_value_multiplier(player_data.get('age', 25))
    market_value = market_value * age_multiplier
    
    # Apply random adjustment to market value
    market_value = apply_market_value_adjustment(market_value)
    
    # Apply random adjustment to salary (this doesn't affect market value)
    final_salary = apply_random_salary_adjustment(base_salary)
    
    # Set market value to 0 for free agents
    if player_data.get('club_id') == 141 or player_data.get('club_id') is None:
        market_value = 0
    
    # Calculate contract years
    contract_years = determine_contract_years(player_data.get('age', 25))
    
    # Calculate yearly wage raise
    yearly_wage_raise = calculate_yearly_wage_raise(player_row, skill_columns, binary_skills, final_salary)
    
    return {
        'salary': int(final_salary),
        'market_value': int(market_value),
        'contract_years_remaining': contract_years,
        'yearly_wage_rise': yearly_wage_raise
    }

def calculate_team_financials(team_players: List[Dict]) -> Dict:
    """
    Calculate financial summary for a team.
    
    Args:
        team_players: List of player dictionaries for the team
    
    Returns:
        Dictionary with team financial summary
    """
    total_salary = 0
    total_market_value = 0
    player_count = len(team_players)
    
    for player in team_players:
        financials = calculate_player_financials(player)
        total_salary += financials['salary']
        total_market_value += financials['market_value']
    
    return {
        'total_salary': total_salary,
        'total_market_value': total_market_value,
        'player_count': player_count,
        'average_salary': total_salary // player_count if player_count > 0 else 0,
        'average_market_value': total_market_value // player_count if player_count > 0 else 0
    }

# --- Database Integration Functions ---
def update_player_financials_in_db(player_id: int, db_path: str) -> bool:
    """
    Update a single player's financial data in the database.
    
    Args:
        player_id: Player ID in the database
        db_path: Path to the SQLite database
    
    Returns:
        True if successful, False otherwise
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get player data
        cursor.execute("""
            SELECT * FROM players WHERE id = ?
        """, (player_id,))
        
        player_row = cursor.fetchone()
        if not player_row:
            print(f"Player {player_id} not found")
            return False
        
        # Convert to dictionary
        columns = [description[0] for description in cursor.description]
        player_data = dict(zip(columns, player_row))
        
        # Calculate financials
        financials = calculate_player_financials(player_data)
        
        # Update database
        cursor.execute("""
            UPDATE players 
            SET salary = ?, market_value = ?, contract_years_remaining = ?, yearly_wage_rise = ?
            WHERE id = ?
        """, (
            financials['salary'],
            financials['market_value'],
            financials['contract_years_remaining'],
            financials['yearly_wage_rise'],
            player_id
        ))
        
        conn.commit()
        conn.close()
        
        print(f"Updated financials for player {player_id}: Salary €{financials['salary']:,}, Market Value €{financials['market_value']:,}")
        return True
        
    except Exception as e:
        print(f"Error updating player {player_id} financials: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

def update_player_market_values_only(db_path: str) -> Dict:
    """
    Update market value data for all players in the database (excluding No Club players).
    Salaries remain unchanged.
    
    Args:
        db_path: Path to the SQLite database
    
    Returns:
        Dictionary with update summary
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get all players except those with No Club (club_id = 141)
        cursor.execute("SELECT * FROM players WHERE club_id != 141")
        players = cursor.fetchall()
        
        if not players:
            print("No players found in database (excluding No Club)")
            return {'success': False, 'message': 'No players found (excluding No Club)'}
        
        # Get column names
        columns = [description[0] for description in cursor.description]
        
        updated_count = 0
        errors = 0
        position_top_players = {}  # Track top 5 players per position
        
        for player_row in players:
            try:
                # Convert to dictionary
                player_data = dict(zip(columns, player_row))
                
                # Calculate only market value (keep existing salary)
                market_value = calculate_player_market_value_only(player_data)
                
                # Update only market value in database
                cursor.execute("""
                    UPDATE players 
                    SET market_value = ?
                    WHERE id = ?
                """, (market_value, player_data['id']))
                
                # Track for top players by position
                position = player_data.get('position', 'Unknown')
                if position not in position_top_players:
                    position_top_players[position] = []
                
                position_top_players[position].append({
                    'name': player_data.get('player_name', 'Unknown'),
                    'market_value': market_value,
                    'club_name': player_data.get('club_name', 'Unknown')
                })
                
                updated_count += 1
                
            except Exception as e:
                print(f"Error updating player {player_data.get('id', 'unknown')}: {e}")
                errors += 1
        
        # Sort top players by position and get top 5
        top_players_by_position = {}
        for position, players_list in position_top_players.items():
            sorted_players = sorted(players_list, key=lambda x: x['market_value'], reverse=True)
            top_players_by_position[position] = sorted_players[:5]
        
        conn.commit()
        conn.close()
        
        return {
            'success': True,
            'updated_count': updated_count,
            'errors': errors,
            'top_players_by_position': top_players_by_position,
            'message': f'Updated market values for {updated_count} players, {errors} errors'
        }
        
    except Exception as e:
        print(f"Error updating player market values: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return {'success': False, 'message': str(e)}

def calculate_player_market_value_only(player_data: Dict) -> int:
    """
    Calculate market value for a single player (salary remains unchanged).
    
    Args:
        player_data: Dictionary containing player information with skills
    
    Returns:
        Calculated market value (integer)
    """
    # Convert to pandas Series for compatibility
    player_row = pd.Series(player_data)
    
    # Get current salary (don't recalculate)
    current_salary = player_data.get('salary', GLOBAL_BASE_SALARY)
    
    # Calculate market value based on current salary
    market_value = current_salary * 1.5
    age_multiplier = get_age_market_value_multiplier(player_data.get('AGE', 25))
    market_value = market_value * age_multiplier
    
    # Set market value to 0 for free agents (No Club)
    if player_data.get('club_id') == 141 or player_data.get('club_id') is None:
        market_value = 0
    
    return int(market_value) 