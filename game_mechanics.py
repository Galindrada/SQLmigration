import pandas as pd
import numpy as np
import random
import math
import sqlite3
import re
import os
import shutil
from typing import Dict, List, Optional, Tuple

# --- Global Constants ---
GLOBAL_BASE_SALARY = 300000
SEED_VALUE = 40
random.seed(SEED_VALUE)
np.random.seed(SEED_VALUE)

# --- Salary Calculation Configuration ---
# Position-specific skill boost multipliers
# Goalkeepers (0): Boost Defense, Balance, Response, Agility, Goal Keeping
# Sweepers/Centre-backs (2, 3): Boost Defense, Balance, Heading, Jump
POSITION_SKILL_BOOST = 1.5  # Boost for key skills in these positions

# Positional salary boosts (affect all players in these positions regardless of ability)
GK_POSITION_BOOST = 5.0  # Overall boost for all goalkeepers (position 0)
DEF_POSITION_BOOST = 7.0  # Overall boost for all defenders (positions 2, 3 - sweepers/centre-backs)
SB_POSITION_BOOST = 3.0  # Overall boost for all side-backs (positions 4, 6 - fullbacks/wingbacks)

# Salary compression factors (smooth differences between top and lower-tier players)
# Compression pulls salaries toward a center point: low salaries increase, high salaries decrease
# Values: 0.0 = full compression (all salaries become equal), 1.0 = no compression
# Typical values: 0.3-0.7 for moderate compression, 0.8-1.0 for light compression
GK_SALARY_COMPRESSION = 0.3  # Compression factor for goalkeepers (0.0 = full compression, 1.0 = none)
DEF_SALARY_COMPRESSION = 0.2  # Compression factor for defenders (0.0 = full compression, 1.0 = none)
SB_SALARY_COMPRESSION = 0.5  # Compression factor for side-backs (0.0 = full compression, 1.0 = none)

# Reference overall rating for compression (used as fallback if player overall is missing)
GK_COMPRESSION_REFERENCE_OVERALL = 75  # Reference overall for goalkeeper compression
DEF_COMPRESSION_REFERENCE_OVERALL = 75  # Reference overall for defender compression
SB_COMPRESSION_REFERENCE_OVERALL = 75  # Reference overall for side-back compression

# Reference salary premiums for compression (base premium for overall 75)
# These determine the center point that salaries compress toward
# Higher values = higher reference salaries, lower values = lower reference salaries
GK_REFERENCE_PREMIUM = 2000000  # Base reference premium for goalkeepers at overall 75
DEF_REFERENCE_PREMIUM = 1500000  # Base reference premium for defenders at overall 75
SB_REFERENCE_PREMIUM = 2000000  # Base reference premium for side-backs at overall 75

# Global skill boosts (applied to all players regardless of position)
# These multiply the contribution of Defense and Goal Keeping skills
# Higher values = these skills have more impact on salary
GK_BOOST = 1.0  # Multiplier for Goal Keeping skill contribution
DEF_BOOST = 1.0  # Multiplier for Defense skill contribution

# Global cache for position averages
_POSITION_AVERAGES_CACHE = None
_POSITION_AVERAGES_CACHE_DB_PATH = None

# Cache for seed player targets from original.sqlite
_SEED_TARGETS_CACHE: Dict[int, Dict[str, int]] = {}

def get_seed_player_targets(seed_player_id: int, original_db_path: str = 'original.sqlite') -> Optional[Dict[str, int]]:
    """Fetch and cache seed player's target skills from original.sqlite.
    Returns a dict mapping skill names used by development to target ints.
    """
    try:
        if not seed_player_id:
            return None
        if seed_player_id in _SEED_TARGETS_CACHE:
            return _SEED_TARGETS_CACHE[seed_player_id]
        conn = sqlite3.connect(original_db_path)
        cur = conn.cursor()
        # Columns aligned with development skill set
        cur.execute(
            """
            SELECT 
                attack, defense, balance, stamina, top_speed, acceleration,
                response, agility, dribble_accuracy, dribble_speed,
                short_pass_accuracy, short_pass_speed, long_pass_accuracy, long_pass_speed,
                shot_accuracy, shot_power, shot_technique, free_kick_accuracy, swerve,
                heading, jump, technique, aggression, mentality, goal_keeping,
                team_work
            FROM players WHERE id = ?
            """,
            (seed_player_id,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        cols = [
            'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
            'response', 'agility', 'dribble_accuracy', 'dribble_speed',
            'short_pass_accuracy', 'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed',
            'shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy', 'swerve',
            'heading', 'jump', 'technique', 'aggression', 'mentality', 'goal_keeping',
            'team_work'
        ]
        targets = {col: int(row[idx]) if row[idx] is not None else None for idx, col in enumerate(cols)}
        _SEED_TARGETS_CACHE[seed_player_id] = targets
        return targets
    except Exception:
        return None

def get_cached_position_averages(db_path: str) -> pd.DataFrame:
    """
    Get cached position averages or calculate them if not cached.
    
    Args:
        db_path: Path to the database
    
    Returns:
        DataFrame with position averages
    """
    global _POSITION_AVERAGES_CACHE, _POSITION_AVERAGES_CACHE_DB_PATH
    
    # Check if we have cached data for this database
    if (_POSITION_AVERAGES_CACHE is not None and 
        _POSITION_AVERAGES_CACHE_DB_PATH == db_path):
        return _POSITION_AVERAGES_CACHE
    
    # Calculate and cache position averages
    print("📊 Calculating position averages (this will be cached)...")
    _POSITION_AVERAGES_CACHE = calculate_position_averages_from_db(db_path)
    _POSITION_AVERAGES_CACHE_DB_PATH = db_path
    
    return _POSITION_AVERAGES_CACHE

def clear_position_averages_cache():
    """Clear the position averages cache (useful for testing)"""
    global _POSITION_AVERAGES_CACHE, _POSITION_AVERAGES_CACHE_DB_PATH
    _POSITION_AVERAGES_CACHE = None
    _POSITION_AVERAGES_CACHE_DB_PATH = None

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
    # Use global constants for GK_BOOST and DEF_BOOST (defined at module level)
    DEF_NAME = 'DEFENSE'
    GK_NAME = 'GOAL KEEPING'
    DIV = 1000.0
    POW = 3.0
    SCALER = 1170000.0
    
    pos = player_row['registered_position']
    pos_clean = pos if pd.notna(pos) else 'Unknown Position'
    
    # Get position as integer for position-specific boosts
    try:
        if isinstance(pos, str):
            pos_int = int(pos.strip())
        elif isinstance(pos, (int, float)):
            pos_int = int(pos)
        else:
            pos_int = -1
    except (ValueError, TypeError):
        pos_int = -1
    
    if pos_avg_df is None or pos_clean not in pos_avg_df.index:
        pos_spec_avg = pd.Series(NORM, index=skills)
    else:
        pos_spec_avg = pos_avg_df.loc[pos_clean]
        if not isinstance(pos_spec_avg, pd.Series):
            pos_spec_avg = pd.Series(NORM, index=skills)

    # Use global constants for salary configuration (defined at module level, lines 21-31)
    # Define which skills get boosted for each position (case-insensitive matching)
    gk_boost_skills = ['defense', 'balance', 'response', 'agility', 'goal_keeping']
    cb_boost_skills = ['defense', 'balance', 'heading', 'jump']

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
        
        # Apply position-specific skill boosts (before global boosts)
        # Convert skill name to lowercase for case-insensitive matching
        skill_n_lower = skill_n.lower()
        if pos_int == 0 and skill_n_lower in gk_boost_skills:
            # Goalkeeper: boost key defensive skills (Defense, Balance, Response, Agility, Goal Keeping)
            contrib *= POSITION_SKILL_BOOST
        elif pos_int in [2, 3] and skill_n_lower in cb_boost_skills:
            # Sweeper/Centre-back: boost key defensive skills (Defense, Balance, Heading, Jump)
            contrib *= POSITION_SKILL_BOOST
        
        # Apply existing global skill boosts (these are still applied on top of position boosts)
        # Note: DEF_NAME is 'DEFENSE', GK_NAME is 'GOAL KEEPING' (with space), but skill_n is 'goal_keeping' (with underscore)
        if skill_n.upper() == DEF_NAME.upper() or skill_n_lower == 'defense':
            contrib *= DEF_BOOST
        elif skill_n.upper().replace('_', ' ') == GK_NAME.upper() or skill_n_lower == 'goal_keeping':
            contrib *= GK_BOOST
        
        if skill_n in binaries:
            contrib *= BIN_IMPACT
        
        twss += contrib
    
    twss = max(0, twss)
    norm_twss = twss / DIV
    pow_score = math.pow(max(0, norm_twss), POW)
    sal_skills = pow_score * SCALER
    calc_sal = GLOBAL_BASE_SALARY + sal_skills
    
    # Apply positional salary boosts (affect all players in these positions regardless of ability)
    if pos_int == 0:
        # Goalkeeper position boost
        calc_sal = calc_sal * GK_POSITION_BOOST
        
        # Apply salary compression: compress toward a reference salary based on overall rating
        # This pulls low salaries up and high salaries down toward a center point
        try:
            overall = float(player_row.get('overall', GK_COMPRESSION_REFERENCE_OVERALL))
            if pd.isna(overall) or overall <= 0:
                overall = GK_COMPRESSION_REFERENCE_OVERALL
        except (ValueError, TypeError):
            overall = GK_COMPRESSION_REFERENCE_OVERALL
        
        # Estimate reference salary for this overall rating (using power law approximation)
        # Reference scales with overall^3 to match the salary calculation's power function
        overall_factor = (overall / 75.0) ** 3
        reference_premium = GK_REFERENCE_PREMIUM * overall_factor  # Uses module-level constant
        reference_salary = GLOBAL_BASE_SALARY + reference_premium
        
        # Compress toward reference: low salaries increase, high salaries decrease
        # compression_factor: 0.0 = full compression (all become reference), 1.0 = no compression
        calc_sal = reference_salary + (calc_sal - reference_salary) * GK_SALARY_COMPRESSION
        
    elif pos_int in [2, 3]:
        # Defender position boost (sweepers/centre-backs)
        calc_sal = calc_sal * DEF_POSITION_BOOST
        
        # Apply salary compression: compress toward a reference salary based on overall rating
        try:
            overall = float(player_row.get('overall', DEF_COMPRESSION_REFERENCE_OVERALL))
            if pd.isna(overall) or overall <= 0:
                overall = DEF_COMPRESSION_REFERENCE_OVERALL
        except (ValueError, TypeError):
            overall = DEF_COMPRESSION_REFERENCE_OVERALL
        
        # Estimate reference salary for this overall rating
        overall_factor = (overall / 75.0) ** 3
        reference_premium = DEF_REFERENCE_PREMIUM * overall_factor  # Uses module-level constant
        reference_salary = GLOBAL_BASE_SALARY + reference_premium
        
        # Compress toward reference: low salaries increase, high salaries decrease
        calc_sal = reference_salary + (calc_sal - reference_salary) * DEF_SALARY_COMPRESSION
    
    elif pos_int in [4, 6]:
        # Side-back position boost (fullbacks/wingbacks - positions 4 and 6)
        calc_sal = calc_sal * SB_POSITION_BOOST
        
        # Apply salary compression: compress toward a reference salary based on overall rating
        try:
            overall = float(player_row.get('overall', SB_COMPRESSION_REFERENCE_OVERALL))
            if pd.isna(overall) or overall <= 0:
                overall = SB_COMPRESSION_REFERENCE_OVERALL
        except (ValueError, TypeError):
            overall = SB_COMPRESSION_REFERENCE_OVERALL
        
        # Estimate reference salary for this overall rating
        overall_factor = (overall / 75.0) ** 3
        reference_premium = SB_REFERENCE_PREMIUM * overall_factor  # Uses module-level constant
        reference_salary = GLOBAL_BASE_SALARY + reference_premium
        
        # Compress toward reference: low salaries increase, high salaries decrease
        calc_sal = reference_salary + (calc_sal - reference_salary) * SB_SALARY_COMPRESSION
    
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

# --- Player Development System ---

# Development Profiles with rarity and characteristics
DEVELOPMENT_PROFILES = {
    0: {'name': 'regular', 'rarity': 0.40, 'description': 'Standard development curve'},
    1: {'name': 'late_bloomer', 'rarity': 0.15, 'description': 'Peaks later in career'},
    2: {'name': 'early_peak', 'rarity': 0.12, 'description': 'Peaks early, declines faster'},
    3: {'name': 'consistent', 'rarity': 0.10, 'description': 'Steady development throughout'},
    4: {'name': 'decliner', 'rarity': 0.08, 'description': 'Declines earlier than normal'},
    5: {'name': 'stronghold', 'rarity': 0.05, 'description': 'Ages gracefully, minimal decline'},
    6: {'name': 'one_time_wonder', 'rarity': 0.04, 'description': '2-3 years of amazing growth, then decline'},
    7: {'name': 'bust', 'rarity': 0.03, 'description': 'Good start, abrupt decline'},
    8: {'name': 'GOAT', 'rarity': 0.02, 'description': 'Consistent excellence throughout career'},
    9: {'name': 'el_crapo', 'rarity': 0.01, 'description': 'Poor development, struggles to improve'}
}

# Development Traits (complementary to profiles)
DEVELOPMENT_TRAITS = {
    0: {'name': 'regular', 'rarity': 0.90, 'description': 'Follows positional skill averages'},
    1: {'name': 'jokester', 'rarity': 0.03, 'description': 'Develops wrong skills for position'},
    2: {'name': 'sharpie', 'rarity': 0.05, 'description': 'Overvalues shooting, decreases physical'},
    3: {'name': 'genetic_freak', 'rarity': 0.02, 'description': 'Opposite of sharpie - physical focus'}
}

def generate_development_key(profile_type: int = 0, base_multiplier: float = 1.0) -> int:
    """
    Generate an encrypted development key for a player.
    
    Args:
        profile_type: Type of development profile (0-4)
        base_multiplier: Base growth/decline multiplier (0.5-2.0)
    
    Returns:
        Encrypted development key (integer)
    """
    # Simple encryption: combine profile type and multiplier
    # In a real system, this would be more sophisticated
    profile_encoded = profile_type * 1000
    multiplier_encoded = int(base_multiplier * 100)
    
    # Combine into a single key
    development_key = profile_encoded + multiplier_encoded
    
    return development_key

def decode_development_key(development_key: int) -> dict:
    """
    Decode a development key to get profile information.
    
    Args:
        development_key: The encrypted development key
    
    Returns:
        Dictionary with profile_type and base_multiplier
    """
    profile_type = development_key // 1000
    multiplier_encoded = development_key % 1000
    base_multiplier = multiplier_encoded / 100.0
    
    return {
        'profile_type': profile_type,
        'base_multiplier': base_multiplier,
        'profile_name': DEVELOPMENT_PROFILES.get(profile_type, {}).get('name', 'unknown')
    }

def generate_mixed_development_key() -> int:
    """
    Generate a mixed development key with multiple profiles.
    
    Returns:
        Integer key representing mixed development profiles
    """
    # 95% chance for mixed profiles, 5% for pure profiles
    if random.random() < 0.95:
        # Mixed profile - combine 2-3 profiles with minimum 10% chunks
        num_profiles = random.randint(2, 3)
        profiles = []
        
        # Select profiles based on rarity
        available_profiles = list(DEVELOPMENT_PROFILES.keys())
        weights = [DEVELOPMENT_PROFILES[p]['rarity'] for p in available_profiles]
        
        # Normalize weights
        total_weight = sum(weights)
        weights = [w/total_weight for w in weights]
        
        # Select profiles (ensure we get valid profiles)
        attempts = 0
        while len(profiles) < num_profiles and attempts < 20:
            profile = random.choices(available_profiles, weights=weights)[0]
            if profile not in profiles and profile in DEVELOPMENT_PROFILES:
                profiles.append(profile)
            attempts += 1
        
        # If we still don't have enough profiles, fill with regular
        while len(profiles) < num_profiles:
            profiles.append(0)  # Add regular profile as fallback
        
        # Generate weights for each profile (must sum to 1.0, minimum 10% each)
        profile_weights = []
        remaining_weight = 1.0
        
        for i, profile in enumerate(profiles):
            if i == len(profiles) - 1:
                # Last profile gets remaining weight (minimum 10%)
                profile_weights.append(max(0.1, remaining_weight))
            else:
                # Random weight between 10% and remaining_weight - 10% * remaining profiles
                min_weight = 0.1
                max_weight = remaining_weight - 0.1 * (len(profiles) - i - 1)
                weight = random.uniform(min_weight, max_weight)
                profile_weights.append(weight)
                remaining_weight -= weight
        
        # Normalize weights to ensure they sum to exactly 1.0
        total_weight = sum(profile_weights)
        profile_weights = [w / total_weight for w in profile_weights]
        
        # Generate base_multiplier using Beta distribution (same as single profiles)
        base_multiplier = 0.1 + 2.9 * random.betavariate(2, 2)
        
        # Enhanced encoding: high bit + num_profiles + profiles + weights + base_multiplier
        encoded = 0x80000000  # High bit indicates mixed
        encoded |= (num_profiles << 24)  # Number of profiles
        
        # Encode profiles (max 3 profiles, 4 bits each)
        for i, profile in enumerate(profiles):
            encoded |= (profile << (16 + i * 4))
        
        # Encode weights (max 3 weights, 8 bits each)
        for i, weight in enumerate(profile_weights):
            encoded |= (int(weight * 100) << (i * 8))
        
        # Encode base_multiplier (multiply by 1000 for precision, use remaining bits)
        # We'll use a different approach: store base_multiplier in the lower 16 bits
        # by shifting everything else up
        encoded = (encoded << 16) | (int(base_multiplier * 1000) & 0xFFFF)
        
        return encoded
    else:
        # Single profile - use original system
        profile_type = random.choices(
            list(DEVELOPMENT_PROFILES.keys()),
            weights=[DEVELOPMENT_PROFILES[p]['rarity'] for p in DEVELOPMENT_PROFILES.keys()]
        )[0]
        # Use Beta distribution: mean ~1.5, 90% between 0.5-2.5, 5% tails
        base_multiplier = 0.1 + 2.9 * random.betavariate(2, 2)
        return generate_development_key(profile_type, base_multiplier)

def generate_development_trait() -> int:
    """
    Generate a development trait for a player.
    
    Returns:
        Integer representing the development trait
    """
    trait_type = random.choices(
        list(DEVELOPMENT_TRAITS.keys()),
        weights=[DEVELOPMENT_TRAITS[t]['rarity'] for t in DEVELOPMENT_TRAITS.keys()]
    )[0]
    
    # Simple encoding: trait type in the lower 8 bits
    return trait_type

def decode_development_trait(trait_key: int) -> dict:
    """
    Decode a development trait key.
    
    Args:
        trait_key: Integer trait key
    
    Returns:
        Dictionary with trait information
    """
    trait_type = trait_key & 0xFF  # Lower 8 bits
    
    return {
        'trait_type': trait_type,
        'trait_name': DEVELOPMENT_TRAITS.get(trait_type, {}).get('name', 'unknown'),
        'description': DEVELOPMENT_TRAITS.get(trait_type, {}).get('description', 'Unknown trait')
    }

def apply_development_trait_effects(position_weights: dict, trait_type: int) -> dict:
    """
    Apply development trait effects to position weights.
    
    Args:
        position_weights: Original position weights
        trait_type: Development trait type
    
    Returns:
        Modified position weights
    """
    modified_weights = position_weights.copy()
    
    if trait_type == 1:  # Jokester - develop wrong skills
        # Invert the weights (skills with low weights get high weights)
        max_weight = max(modified_weights.values())
        for skill in modified_weights:
            if modified_weights[skill] > 1.0:
                modified_weights[skill] = max(1.0, max_weight - modified_weights[skill] + 1.0)
    
    elif trait_type == 2:  # Sharpie - overvalue shooting, decrease physical
        # Boost shooting-related skills
        shooting_skills = ['shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy']
        physical_skills = ['top_speed', 'acceleration', 'stamina', 'jump', 'balance']
        
        for skill in shooting_skills:
            if skill in modified_weights:
                modified_weights[skill] *= 1.5
        
        for skill in physical_skills:
            if skill in modified_weights:
                modified_weights[skill] *= 0.7
    
    elif trait_type == 3:  # Genetic freak - opposite of sharpie
        # Boost physical skills, decrease shooting
        shooting_skills = ['shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy']
        physical_skills = ['top_speed', 'acceleration', 'stamina', 'jump', 'balance']
        
        for skill in physical_skills:
            if skill in modified_weights:
                modified_weights[skill] *= 1.5
        
        for skill in shooting_skills:
            if skill in modified_weights:
                modified_weights[skill] *= 0.7
    
    # Regular trait (0) doesn't modify weights
    return modified_weights

def generate_complete_development_key() -> tuple:
    """
    Generate a complete development key with both profile and trait.
    
    Returns:
        Tuple of (profile_key, trait_key)
    """
    profile_key = generate_mixed_development_key()
    trait_key = generate_development_trait()
    
    return profile_key, trait_key

def decode_complete_development_key(profile_key: int, trait_key: int) -> dict:
    """
    Decode a complete development key with both profile and trait.
    
    Args:
        profile_key: Profile development key
        trait_key: Trait development key
    
    Returns:
        Dictionary with complete development information
    """
    profile_info = decode_mixed_development_key(profile_key)
    trait_info = decode_development_trait(trait_key)
    
    return {
        'profile': profile_info,
        'trait': trait_info
    }

def decode_mixed_development_key(development_key: int) -> dict:
    """
    Decode a mixed development key.
    
    Args:
        development_key: Integer key to decode
    
    Returns:
        Dictionary with profile information
    """
    if development_key & 0x80000000:  # Mixed profile
        # Extract base_multiplier from lower 16 bits
        base_multiplier_encoded = development_key & 0xFFFF
        base_multiplier = base_multiplier_encoded / 1000.0
        
        # Extract other data from upper bits (shifted right by 16)
        shifted_key = development_key >> 16
        
        # Extract number of profiles
        num_profiles = (shifted_key >> 24) & 0xFF
        
        profiles = []
        weights = []
        
        # Extract profiles (max 3 profiles, 4 bits each)
        for i in range(min(num_profiles, 3)):  # Limit to 3 profiles maximum
            profile_type = (shifted_key >> (16 + i * 4)) & 0xF
            if profile_type in DEVELOPMENT_PROFILES:  # Only add valid profiles
                profiles.append(profile_type)
        
        # Extract weights (max 3 weights, 8 bits each)
        for i in range(min(num_profiles, 3)):  # Limit to 3 weights maximum
            weight = ((shifted_key >> (i * 8)) & 0xFF) / 100.0
            weights.append(weight)
        
        # Ensure we have matching numbers of profiles and weights
        while len(weights) < len(profiles):
            weights.append(0.0)
        while len(profiles) < len(weights):
            profiles.append(0)  # Default to regular
        
        # Normalize weights to sum to 1.0
        if weights:
            total_weight = sum(weights)
            if total_weight > 0:
                weights = [w / total_weight for w in weights]
        
        return {
            'is_mixed': True,
            'profiles': profiles,
            'weights': weights,
            'base_multiplier': base_multiplier,
            'profile_names': [DEVELOPMENT_PROFILES.get(p, {}).get('name', 'unknown') for p in profiles],
            'descriptions': [DEVELOPMENT_PROFILES.get(p, {}).get('description', 'Unknown profile') for p in profiles]
        }
    else:
        # Single profile - use original decoding
        return decode_development_key(development_key)

def get_age_development_multiplier(age: int, profile_type: int) -> float:
    """
    Get development multiplier based on age and profile type.
    
    Args:
        age: Player age
        profile_type: Development profile type (0-9)
    
    Returns:
        Development multiplier (positive for growth, negative for decline)
    """
    if profile_type == 0:  # Regular
        if age <= 23:
            return 1.2825  # Good growth (1.425 * 0.9)
        elif age <= 28:
            return 0.6075  # Moderate growth (0.675 * 0.9)
        elif age <= 32:
            # Minimal random floor in late-20s/early-30s to avoid stasis
            return random.uniform(-2, 0)
        elif age <= 35:
            return -0.4725  # Mild decline (-0.525 * 0.9)
        else:
            return -0.8775  # Strong decline (-0.975 * 0.9)
    
    elif profile_type == 1:  # Late bloomer
        if age <= 25:
            return 0.8775  # Moderate growth (0.975 * 0.9)
        elif age <= 30:
            return 1.5525  # Strong growth (1.725 * 0.9)
        elif age <= 34:
            return 0.4725  # Mild growth (0.525 * 0.9)
        elif age <= 37:
            return -0.4725  # Very mild decline (-0.525 * 0.9)
        else:
            return -1.2825  # Moderate decline (-1.425 * 0.9)
    
    elif profile_type == 2:  # Early peak
        if age <= 20:
            return 2.0925  # Very strong growth (2.325 * 0.9)
        elif age <= 25:
            return 1.1475  # Good growth (1.275 * 0.9)
        elif age <= 28:
            return 0.0  # Peak reached (0.0 * 0.9)
        elif age <= 32:
            return -0.7425  # Moderate decline (-0.825 * 0.9)
        else:
            return -1.2825  # Strong decline (-1.425 * 0.9)
    
    elif profile_type == 3:  # Consistent
        if age <= 26:
            return 1.0125  # Steady growth (1.125 * 0.9)
        elif age <= 32:
            return 0.6075  # Mild growth (0.675 * 0.9)
        elif age <= 36:
            return -0.3375  # Very mild decline (-0.375 * 0.9)
        else:
            return -0.4725  # Mild decline (-0.525 * 0.9)
    
    elif profile_type == 4:  # Decliner
        if age <= 22:
            return 0.54  # Moderate growth (0.6 * 0.9)
        elif age <= 26:
            return 0.135  # Mild growth (0.15 * 0.9)
        elif age <= 30:
            return -0.6075  # Early decline (-0.675 * 0.9)
        elif age <= 34:
            return -0.8775  # Moderate decline (-0.975 * 0.9)
        else:
            return -1.2825  # Strong decline (-1.425 * 0.9)
    
    elif profile_type == 5:  # Stronghold
        if age <= 25:
            return 1.2825  # Good growth (1.425 * 0.9)
        elif age <= 30:
            return 0.8775  # Moderate growth (0.975 * 0.9)
        elif age <= 35:
            return 0.6075  # Mild growth (0.675 * 0.9)
        elif age <= 40:
            return 0.0  # Stagnation (0.0 * 0.9)
        else:
            return -0.3375  # Very mild decline (-0.375 * 0.9)
    
    elif profile_type == 6:  # One-time wonder
        if age <= 20:
            return 0.4725  # Moderate growth (0.525 * 0.9)
        elif age <= 23:
            return 2.4975  # Amazing growth period (2.775 * 0.9)
        elif age <= 26:
            return 1.35  # Still strong (1.5 * 0.9)
        elif age <= 29:
            return 0.2025  # Decline starts (0.225 * 0.9)
        else:
            return -0.8775  # Sharp decline (-0.975 * 0.9)
    
    elif profile_type == 7:  # Bust
        if age <= 22:
            return 1.215  # Good start (1.35 * 0.9)
        elif age <= 25:
            return 0.2025  # Moderate growth (0.225 * 0.9)
        elif age <= 28:
            return -0.7425  # Abrupt decline (-0.825 * 0.9)
        else:
            return -1.2825  # Severe decline (-1.425 * 0.9)
    
    elif profile_type == 8:  # GOAT
        if age <= 25:
            return 1.35  # Strong growth (1.5 * 0.9)
        elif age <= 30:
            return 1.1475  # Good growth (1.275 * 0.9)
        elif age <= 35:
            return 0.7425  # Moderate growth (0.825 * 0.9)
        elif age <= 40:
            return -0.2025  # Mild growth (-0.225 * 0.9)
        else:
            return -0.6075  # Maintains level (-0.675 * 0.9)
    
    elif profile_type == 9:  # El Crapo
        if age <= 22:
            return 0.27  # Poor growth (0.3 * 0.9)
        elif age <= 25:
            return 0.0  # Stagnation (0.0 * 0.9)
        elif age <= 28:
            return -0.7425  # Early decline (-0.825 * 0.9)
        elif age <= 32:
            return -0.8775  # Moderate decline (-0.975 * 0.9)
        else:
            return -1.2825  # Severe decline (-1.425 * 0.9)
    
    else:  # Default to regular
        return get_age_development_multiplier(age, 0)

def calculate_player_skill_development(player_data: dict, development_key: int = 0, trait_key: int = 0) -> dict:
    """
    Calculate skill development for a player based on their development key, trait, and position.
    
    Args:
        player_data: Player data dictionary
        development_key: Encrypted development key (can be mixed or single)
        trait_key: Development trait key
    
    Returns:
        Dictionary with skill changes for the player
    """
    # Decode development key (handles both mixed and single profiles)
    dev_info = decode_mixed_development_key(development_key)
    trait_info = decode_development_trait(trait_key)
    
    # Get age and position
    age = player_data.get('age', 25)
    registered_position = str(player_data.get('registered_position', 7))
    
    # Calculate mixed profile multiplier if applicable
    if dev_info.get('is_mixed', False):
        profiles = dev_info['profiles']
        weights = dev_info['weights']
        
        # Calculate weighted average of age multipliers
        total_age_multiplier = 0
        for profile_type, weight in zip(profiles, weights):
            age_mult = get_age_development_multiplier(age, profile_type)
            total_age_multiplier += age_mult * weight
        
        age_multiplier = total_age_multiplier
        # Mixed profiles use stored base_multiplier from development key
        # Scale from current range (0-10) to target range (0.5-5)
        raw_base_multiplier = dev_info['base_multiplier']
        base_multiplier = 0.5 + (raw_base_multiplier / 10.0) * 4.5  # Scale 0-10 to 0.5-5
        # Create clean mixed profile name
        mixed_parts = []
        for i, name in enumerate(dev_info['profile_names']):
            weight = dev_info['weights'][i] * 100
            mixed_parts.append(f"{name}({weight:.0f}%)")
        profile_name = f"Mixed: {'/'.join(mixed_parts)}"
        profile_type = profiles[0]  # Use first profile for reference
    else:
        # Single profile
        profile_type = dev_info['profile_type']
        # Scale from current range (0-10) to target range (0.5-5)
        raw_base_multiplier = dev_info['base_multiplier']
        base_multiplier = 0.5 + (raw_base_multiplier / 10.0) * 4.5  # Scale 0-10 to 0.5-5
        age_multiplier = get_age_development_multiplier(age, profile_type)
        profile_name = dev_info['profile_name']
    
    # Get cached position averages for skill weights
    pos_avg_df = get_cached_position_averages('pes6_league_db.sqlite')
    
    # Get position-specific skill weights based on position averages
    position_weights = get_position_skill_weights_from_averages(pos_avg_df, registered_position)
    
    # Apply development trait effects
    position_weights = apply_development_trait_effects(position_weights, trait_info['trait_type'])
    
    # Harden decline after age 32 across profiles: make negative age multipliers more negative
    try:
        age_int = int(age)
    except Exception:
        age_int = 25
    if age_int > 32 and age_multiplier < 0:
        age_multiplier -= random.uniform(0.5, 3.0)
    # Additional decline step after 36
    if age_int > 36 and age_multiplier < 0:
        age_multiplier -= random.uniform(-0.2, 3.0)
    # Additional decline step after 40
    if age_int > 40 and age_multiplier < 0:
        age_multiplier -= random.uniform(1.0, 4.0)

    # Calculate final development multiplier (separate natural vs performance components)
    base_growth = age_multiplier * base_multiplier
    
    # Calculate performance-based boost
    # Get db_path from player_data if available, otherwise use default
    db_path = player_data.get('db_path', 'pes6_league_db.sqlite')
    performance_boost = calculate_performance_boost(player_data, db_path)
    # Separate natural development from performance-driven development
    # Natural works even at 0 games (drives youth growth and veteran decline)
    natural_weight = 0.4
    performance_weight = 0.6
    games_played = int(player_data.get('games_played', 0) or 0)
    # Assume ~34 league matches as reference; clamp to 1.0
    games_ratio = min(1.0, max(0.0, games_played / 34.0))
    # Youth floor: allow some growth even with few/no games for young players
    # Stronger floor for <=20, tapering off with age
    if age <= 20:
        youth_floor = 0.35
    elif age <= 22:
        youth_floor = 0.25
    elif age <= 24:
        youth_floor = 0.15
    else:
        youth_floor = 0.05
    effective_games_factor = max(games_ratio, youth_floor)
    perf_factor = 1.0 + 0.6 * float(performance_boost.get('total_boost', 0.0))
    # Compose additively: performance term decoupled from age sign so it mitigates decline
    natural_component = base_multiplier * age_multiplier * natural_weight
    performance_component = base_multiplier * performance_weight * effective_games_factor * perf_factor
    final_multiplier = natural_component + performance_component
    # Define skills that can be developed
    skill_columns = [
        'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
        'response', 'agility', 'dribble_accuracy', 'dribble_speed',
        'short_pass_accuracy', 'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed',
        'shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy', 'swerve',
        'heading', 'jump', 'technique', 'aggression', 'mentality', 'goal_keeping',
        'team_work'
    ]
    
    skill_changes = {}
    total_skill_change = 0
    
    # If player has a seed base, fetch targets
    seed_player_id = None
    try:
        seed_player_id = int(player_data.get('seed_player', 0)) if player_data.get('seed_player') is not None else 0
    except Exception:
        seed_player_id = 0
    seed_targets = get_seed_player_targets(seed_player_id) if seed_player_id else None

    for skill in skill_columns:
        if skill in player_data:
            current_value = int(player_data[skill])
            
            # Skip if skill is not applicable (e.g., goal_keeping for outfield players)
            if skill == 'goal_keeping' and registered_position != '0':
                continue
            
            # Get position weight for this skill from averages
            skill_weight = position_weights.get(skill, 1.0)
            
            # Calculate skill change based on remaining potential or seed target if available
            if final_multiplier > 0:  # Improvement
                # Default remaining potential to 99 ceiling
                remaining_potential = (99) - current_value
                # If seed target exists, steer towards it
                if seed_targets and skill in seed_targets and seed_targets[skill] is not None:
                    target = int(seed_targets[skill])
                    delta_to_target = target - current_value
                    if delta_to_target > 0:
                        # Grow towards seed target rather than 99 ceiling
                        remaining_potential = min(remaining_potential, delta_to_target)
                        # Emphasize important skills more when below target (stronger skew)
                        remaining_potential *= max(1.0, skill_weight ** 1.6)
                    else:
                        # Already above seed target: apply growing penalty that competes with development
                        over_seed = -delta_to_target  # positive amount over target
                        
                        # Tolerance zone (0-3 points over): Player can maintain or slightly improve
                        # This represents natural variance and peak performance capability
                        if over_seed <= 3:
                            # Small penalty that development can overcome
                            # Penalty grows quadratically: 0.1 at +1, 0.4 at +2, 0.9 at +3
                            penalty_factor = (over_seed / 3.0) ** 2
                            remaining_potential = (99 - current_value) * (0.3 - (penalty_factor * 0.25))
                            # At +1: 0.3 - 0.11 = 0.19 (can still grow with good development)
                            # At +2: 0.3 - 0.44 = -0.14 (slight regression unless strong development)
                            # At +3: 0.3 - 0.9 = -0.6 (regression unless exceptional development)
                        
                        # Warning zone (4-6 points over): Strong penalty, hard to maintain
                        elif over_seed <= 6:
                            # Penalty increases significantly
                            # Development strength must be very high to maintain
                            penalty_strength = 0.8 + ((over_seed - 3) * 0.3)  # 0.8 to 1.7
                            importance_factor = max(0.5, skill_weight)
                            penalty_rate = penalty_strength / importance_factor
                            remaining_potential = -penalty_rate * 8.0
                            # Results in -6 to -14 per season depending on importance
                        
                        # Critical zone (7+ points over): Very strong regression
                        else:
                            # Heavy penalty, almost impossible to maintain
                            penalty_strength = 1.5 + ((over_seed - 6) * 0.2)
                            importance_factor = max(0.5, skill_weight)
                            penalty_rate = penalty_strength / importance_factor
                            remaining_potential = -penalty_rate * 12.0
                            # Results in -18 to -30+ per season
                # Apply multiplier scaled down for realistic changes
                # Stronger pull when seed is present (smaller divisor)
                divisor = 24.0 if seed_targets else 45.0
                base_change = (final_multiplier * skill_weight * remaining_potential) / divisor
            else:  # Decline
                # For decline, apply multiplier to current value, scaled down
                base_change = (final_multiplier * skill_weight * current_value) / 100.0
            
            # Performance boost is now applied to final_multiplier, not per skill
            
            # Randomness: tighter when seed-targeted to improve convergence
            if seed_targets:
                skill_random = random.uniform(0.95, 1.05)
            else:
                skill_random = random.uniform(0.7, 1.3)
            skill_change = base_change * skill_random

            # Seed nudge: push towards seed target (with tolerance zone)
            if seed_targets and skill in seed_targets and seed_targets[skill] is not None:
                target = int(seed_targets[skill])
                gap = target - current_value
                if gap != 0:
                    # ε scaled by importance with curvature, still bounded to avoid jumps
                    epsilon = 0.45  # nudge strength per season baseline
                    nudge = epsilon * (max(0.5, skill_weight) ** 1.5)
                    
                    if gap > 0:
                        # Below target: push up (only on improvement years)
                        if final_multiplier > 0:
                            skill_change += min(nudge, gap)
                    else:
                        # Above target: apply downward nudge based on how far over
                        over_amount = abs(gap)
                        
                        # Tolerance zone (0-3 over): minimal to no downward nudge
                        # Let development strength determine if player maintains or regresses
                        if over_amount <= 3:
                            # Very light nudge that only activates if already declining
                            if final_multiplier < 0:  # Only on decline years
                                downward_nudge = min(nudge * 0.3, over_amount)
                                skill_change -= downward_nudge
                        
                        # Warning zone (4-6 over): moderate downward nudge
                        elif over_amount <= 6:
                            downward_nudge = min(nudge * 0.6, over_amount)
                            skill_change -= downward_nudge
                        
                        # Critical zone (7+ over): strong downward nudge
                        else:
                            downward_nudge = min(nudge, over_amount)
                            skill_change -= downward_nudge
            
            # Ensure skill stays within reasonable bounds (1-99) and convert to integer with proper rounding
            new_value = max(1, min(99, round(current_value + skill_change)))
            actual_change = new_value - current_value
            
            skill_changes[skill] = {
                'current': current_value,
                'change': actual_change,
                'new': new_value,
                'weight': skill_weight,
                'performance_boost': performance_boost.get(f'{skill}_boost', 0)
            }
            
            total_skill_change += actual_change
    
    return {
        'development_key': development_key,
        'trait_key': trait_key,
        'profile_type': profile_type,
        'profile_name': profile_name,
        'trait_name': trait_info['trait_name'],
        'trait_description': trait_info['description'],
        'age_multiplier': age_multiplier,
        'base_multiplier': base_multiplier,
        'final_multiplier': final_multiplier,
        'performance_boost': performance_boost,
        'skill_changes': skill_changes,
        'total_skill_change': total_skill_change,
        'skills_improved': len([s for s in skill_changes.values() if s['change'] > 0]),
        'skills_declined': len([s for s in skill_changes.values() if s['change'] < 0]),
        'is_mixed': dev_info.get('is_mixed', False),
        'mixed_profiles': dev_info.get('profile_names', []) if dev_info.get('is_mixed', False) else None,
        'mixed_weights': dev_info.get('weights', []) if dev_info.get('is_mixed', False) else None,
        'binary_skill_changes': develop_binary_skills(player_data)
    }

def develop_binary_skills(player_data: dict) -> dict:
    """
    Develop binary skills for a player based on their seed player or random chance.
    
    Binary skills start at 0 for regens. During development:
    - If player has a seed: 15% chance to gain each binary skill that seed has (value = 1)
    - If player has no seed: 5% chance to gain any binary skill
    - Only grants skills the player doesn't already have (value = 1)
    
    Args:
        player_data: Player data dictionary (must include seed_player if available)
    
    Returns:
        Dictionary mapping binary skill names to their new values (0 or 1)
    """
    import sqlite3
    import random
    
    # List of all binary skills
    binary_skills = [
        'dribbling_skill', 'tactical_dribble', 'positioning', 'reaction', 'playmaking',
        'passing', 'scoring', 'one_one_scoring', 'post_player', 'lines', 'middle_shooting',
        'side', 'centre', 'penalties', 'one_touch_pass', 'outside', 'marking', 'sliding',
        'covering', 'd_line_control', 'penalty_stopper', 'one_on_one_stopper', 'long_throw'
    ]
    
    binary_skill_changes = {}
    
    # Get seed player ID
    seed_player_id = None
    try:
        seed_player_id = int(player_data.get('seed_player', 0)) if player_data.get('seed_player') is not None else 0
    except Exception:
        seed_player_id = 0
    
    # Get seed player's binary skills if seed exists
    seed_binary_skills = {}
    if seed_player_id and seed_player_id > 0:
        try:
            original_db_path = '/home/anibalgalindro/SQLiteMigration/original.sqlite'
            conn = sqlite3.connect(original_db_path)
            cursor = conn.cursor()
            
            # Get seed player's binary skills
            cursor.execute("SELECT * FROM players WHERE id = ?", (seed_player_id,))
            seed_player = cursor.fetchone()
            
            if seed_player:
                # Get column names
                cursor.execute("PRAGMA table_info(players)")
                columns = [col[1] for col in cursor.fetchall()]
                seed_player_dict = dict(zip(columns, seed_player))
                
                # Extract binary skills from seed player
                for skill in binary_skills:
                    seed_binary_skills[skill] = seed_player_dict.get(skill, 0)
            
            conn.close()
        except Exception as e:
            # If we can't get seed data, treat as no seed
            seed_player_id = 0
    
    # Process each binary skill INDIVIDUALLY (not as a batch)
    # Each skill has its own independent 15% chance per season if seed has it
    for skill in binary_skills:
        # Get current value (default to 0 if not set)
        current_value = player_data.get(skill, 0)
        
        # If player already has the skill, don't change it
        if current_value == 1:
            binary_skill_changes[skill] = 1
            continue
        
        # Determine probability based on seed
        if seed_player_id and seed_player_id > 0:
            # Player has a seed: 15% chance if seed has the skill
            # NOTE: Each skill is processed INDIVIDUALLY, not as a batch
            if seed_binary_skills.get(skill, 0) == 1:
                probability = 0.15
            else:
                # Seed doesn't have this skill, no chance to gain it
                probability = 0.0
        else:
            # No seed: 5% chance for any binary skill
            probability = 0.05
        
        # Roll for the skill INDIVIDUALLY (each skill gets its own random roll)
        if random.random() < probability:
            binary_skill_changes[skill] = 1
        else:
            binary_skill_changes[skill] = 0
    
    return binary_skill_changes

def get_position_skill_weights_from_averages(pos_avg_df: pd.DataFrame, registered_position: str) -> dict:
    """
    Get skill weights for a specific position based on position averages.
    
    Args:
        pos_avg_df: Position averages dataframe
        registered_position: Player's registered position
    
    Returns:
        Dictionary with skill weights for the position
    """
    if registered_position not in pos_avg_df.index:
        return {'balance': 1.0, 'consistency': 1.0, 'condition_fitness': 1.0}
    
    # Get position averages
    pos_averages = pos_avg_df.loc[registered_position]
    
    # Normalize weights based on position averages
    # Higher average = higher weight for development
    weights = {}
    max_avg = pos_averages.max()
    
    for skill, avg_value in pos_averages.items():
        if avg_value > 0:
            # Weight based on how much this skill is valued for this position
            # Higher average = higher weight for overall calculation
            # For overall calculation, we want weights that sum to 1.0 for the most important skills
            weight = avg_value / max_avg  # Scale to 0-1 range based on position averages
            
            # Only include skills that are significantly important for this position
            if weight >= 0.7:  # Only skills that are at least 70% as important as the most important skill
                weights[skill] = weight
        else:
            weights[skill] = 0.0  # No weight for skills not valued for this position
    
    return weights

def calculate_nationality_strength(nationality: str, db_path: str = 'pes6_league_db.sqlite') -> float:
    """
    Calculate nationality strength based on the number of available players for that country.
    
    Small countries (few players) = lower strength (easier to get selected)
    Large countries (many players) = higher strength (harder to get selected, more prestigious)
    
    Args:
        nationality: Player's nationality
        db_path: Path to database
    
    Returns:
        Strength multiplier (0.5 to 2.0)
        - 0.5 for very small countries (< 20 players)
        - 1.0 for medium countries (20-100 players)
        - 2.0 for large countries (> 200 players)
    """
    if not nationality:
        return 1.0  # Default if no nationality
    
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Count players available for selection (non-draftees with clubs)
        cursor.execute("""
            SELECT COUNT(*) as player_count
            FROM players
            WHERE (nationality = ? OR nationality = ?)
            AND club_id IS NOT NULL
            AND (draftee = 0 OR draftee IS NULL)
        """, (nationality, nationality.strip()))
        
        result = cursor.fetchone()
        player_count = result['player_count'] if result else 0
        conn.close()
        
        # Calculate strength based on player count
        # Very small countries (< 20): 0.5x (easy to get selected)
        # Small countries (20-50): 0.7x
        # Medium countries (50-100): 1.0x (baseline)
        # Large countries (100-200): 1.5x
        # Very large countries (> 200): 2.0x (very prestigious)
        
        if player_count < 20:
            return 0.5
        elif player_count < 50:
            return 0.5 + (player_count - 20) * 0.0067  # Linear from 0.5 to 0.7
        elif player_count < 100:
            return 0.7 + (player_count - 50) * 0.006  # Linear from 0.7 to 1.0
        elif player_count < 200:
            return 1.0 + (player_count - 100) * 0.005  # Linear from 1.0 to 1.5
        else:
            return min(2.0, 1.5 + (player_count - 200) * 0.0025)  # Linear from 1.5 to 2.0 (capped)
            
    except Exception as e:
        # Fallback to default if database query fails
        return 1.0

def calculate_performance_boost(player_data: dict, db_path: str = 'pes6_league_db.sqlite') -> dict:
    """
    Calculate performance-based development boost.
    
    Distributes existing boost between club and international performance.
    International performance is weighted by nationality strength.
    
    Args:
        player_data: Player data dictionary
        db_path: Path to database (for nationality strength calculation)
    
    Returns:
        Dictionary with performance boosts
    """
    # Club performance stats
    games_played = player_data.get('games_played', 0)
    goals = player_data.get('goals', 0)
    assists = player_data.get('assists', 0)
    mvp = player_data.get('MVP', 0)
    
    # International performance stats (current season)
    int_caps = player_data.get('current_season_caps', 0)
    int_goals = player_data.get('current_international_goals', 0)
    int_assists = player_data.get('current_international_assists', 0)
    
    # Calculate nationality strength (affects international boost value)
    nationality = player_data.get('nationality', '')
    nationality_strength = calculate_nationality_strength(nationality, db_path)
    
    # Club performance boosts (original values - these define the baseline)
    games_boost = min(1, games_played * 0.04)  # Max 0.5 boost from games
    goals_mvp_combined = goals + mvp
    goals_boost = min(0.55, goals_mvp_combined * 0.03)  # Max 0.8 boost from goals + MVP combined
    assists_boost = min(0.35, assists * 0.02)  # Max 0.6 boost from assists
    total_club_boost = games_boost + goals_boost + assists_boost
    
    # International performance boosts (scaled to match club boost ranges, then weighted by nationality)
    # Use same formulas as club but apply nationality strength multiplier
    int_games_equivalent = int_caps * nationality_strength
    int_goals_equivalent = int_goals * nationality_strength
    int_assists_equivalent = int_assists * nationality_strength
    
    int_caps_boost = min(0.9, int_games_equivalent * 0.05)  # Same max as club games
    int_goals_boost = min(0.6, int_goals_equivalent * 0.05)  # Same max as club goals
    int_assists_boost = min(0.4, int_assists_equivalent * 0.05)  # Same max as club assists
    total_int_boost = int_caps_boost + int_goals_boost + int_assists_boost
    
    # Distribute boost between club and international (not additive)
    # If player has both, blend them proportionally
    # If player has only one, use that one
    # Total should remain similar to original club-only boost
    
    # Calculate relative contribution
    club_contribution = total_club_boost if total_club_boost > 0 else 0
    int_contribution = total_int_boost if total_int_boost > 0 else 0
    total_contribution = club_contribution + int_contribution
    
    if total_contribution > 0:
        # Blend: if both exist, distribute proportionally
        # But cap total to maintain similar magnitude to original
        club_weight = club_contribution / total_contribution if total_contribution > 0 else 1.0
        int_weight = int_contribution / total_contribution if total_contribution > 0 else 0.0
        
        # Distribute the boost (total should be similar to original club boost)
        # If international exists, it replaces part of club boost
        blended_boost = (club_contribution * club_weight) + (int_contribution * int_weight)
        # Cap at original maximum (1.9 = 0.5 + 0.8 + 0.6)
        blended_boost = min(2.2, blended_boost)
    else:
        blended_boost = 0.0
    
    # Additional random factor for performance
    performance_random = random.uniform(0.8, 1.2)
    
    # Final total boost (distributed, not additive)
    total_boost = blended_boost * performance_random
    
    return {
        'games_boost': games_boost * performance_random,
        'goals_boost': goals_boost * performance_random,
        'assists_boost': assists_boost * performance_random,
        'int_caps_boost': int_caps_boost * performance_random,
        'int_goals_boost': int_goals_boost * performance_random,
        'int_assists_boost': int_assists_boost * performance_random,
        'nationality_strength': nationality_strength,
        'total_boost': total_boost
    }

def check_player_retirement(player_data: Dict) -> Dict:
    """
    Check if a player wants to retire based on age, salary, club status, contract, and games played.
    
    Args:
        player_data: Dictionary containing player information
    
    Returns:
        Dictionary with retirement check results
    """
    age = player_data.get('age', 25)
    salary = player_data.get('salary', GLOBAL_BASE_SALARY)
    club_id = player_data.get('club_id')
    contract_years_remaining = player_data.get('contract_years_remaining', 0)
    games_played = player_data.get('games_played', 0)
    
    # Base retirement probability starts at age 30
    if age < 30:
        return {
            'wants_to_retire': False,
            'retirement_probability': 0.0,
            'reason': 'Too young to consider retirement'
        }
    
    # Players with 1+ years contract remaining are not eligible for retirement
    # (This check happens after contract years are reduced at end of season)
    # EXCEPTION: "No Club" players (club_id = 141 or None) ignore contract status
    # Their "contract" represents what they're asking for, not an actual binding contract
    if contract_years_remaining >= 1 and club_id != 141 and club_id is not None:
        return {
            'wants_to_retire': False,
            'retirement_probability': 0.0,
            'reason': f'Under contract for {contract_years_remaining} more years - not eligible for retirement'
        }
    
    # Calculate base retirement probability based on age
    # Probability increases with age - reduced age factor for more moderate progression
    age_factor = (age - 30) / 13.0  # 0 at age 30, 1 at age 44 (slightly slower increase)
    age_probability = min(0.95, age_factor * 0.90)  # Max 80% at age 44+, moderate base rate
    
    # Salary factor - higher salary reduces retirement probability
    # Normalize salary to 0-1 range (0 = low salary, 1 = high salary)
    salary_normalized = min(1.0, salary / 30000000)  # 30M salary = max
    salary_factor = 1.0 - salary_normalized  # Higher salary = lower retirement chance
    
    # Club status factor - No Club players more likely to retire
    club_factor = 0.0
    if club_id == 141 or club_id is None:  # No Club
        club_factor = 0.35  # 25% additional probability
    
    # Games played factor - more games played reduces retirement probability
    # Normalize games played to 0-1 range (0 = no games, 1 = many games)
    # Assuming 30+ games in a season is "very active"
    games_normalized = min(1.0, games_played / 30.0)
    games_factor = games_normalized * 0.25  # Games can reduce probability by up to 25%
    
    # Calculate final retirement probability
    base_probability = age_probability
    salary_adjustment = salary_factor * 0.20  # Salary can reduce probability by up to 20%
    final_probability = base_probability + club_factor - salary_adjustment - games_factor
    
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
        'club_factor': club_factor,
        'games_factor': games_factor
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
    pos_avg_df = get_cached_position_averages(db_path)
    
    # Calculate base salary (includes all position-specific boosts and compression)
    # Position boosts (GK_POSITION_BOOST, DEF_POSITION_BOOST, SB_POSITION_BOOST) and
    # compression are already applied inside calculate_player_salary_base
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
    Calculate market value for a single player using estimated salary.
    
    Args:
        player_data: Dictionary containing player information with skills
    
    Returns:
        Calculated market value (integer)
    """
    # Convert to pandas Series for compatibility
    player_row = pd.Series(player_data)
    
    # Calculate estimated salary instead of using current salary
    try:
        # Get position averages for salary calculation
        pos_avg_df = get_cached_position_averages('pes6_league_db.sqlite')
        
        # Define skill lists (same as in the main salary calculation)
        skills = ['attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
                 'response', 'agility', 'dribble_accuracy', 'dribble_speed',
                 'short_pass_accuracy', 'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed',
                 'shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy', 'swerve',
                 'heading', 'jump', 'technique', 'aggression', 'mentality', 'goal_keeping',
                 'team_work', 'consistency', 'condition_fitness']
        
        binaries = ['dribbling', 'tactical_dribble', 'positioning', 'reaction', 'play_making',
                   'passing', 'scoring', '1-1_score', 'post_player', 'lines', 'middle_shooting',
                   'side', 'centre', 'penalties', '1-touch_pass', 'outside', 'marking', 'sliding',
                   'covering', 'd_line_control', 'penalty_stopper', '1-on-1_stopper', 'long_throw']
        
        # Calculate estimated salary
        estimated_salary = calculate_player_salary_base(player_row, pos_avg_df, skills, binaries)
        
    except Exception as e:
        # Fallback to current salary if calculation fails
        print(f"Warning: Could not calculate estimated salary for market value: {e}")
        estimated_salary = player_data.get('salary', GLOBAL_BASE_SALARY)
    
    # Calculate market value based on estimated salary
    market_value = estimated_salary * 1.5
    age_multiplier = get_age_market_value_multiplier(player_data.get('age', 25))
    market_value = market_value * age_multiplier
    
    # Set market value to 0 for free agents (No Club)
    if player_data.get('club_id') == 141 or player_data.get('club_id') is None:
        market_value = 0
    
    return int(market_value) 

def assign_development_keys_to_players(db_path: str) -> dict:
    """
    Assign development keys (profile + trait) to all players who don't have them.
    
    Args:
        db_path: Path to the SQLite database
    
    Returns:
        Dictionary with assignment results
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # First, check if trait_key column exists, if not add it
        cursor.execute("PRAGMA table_info(players)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'trait_key' not in columns:
            print("📊 Adding trait_key column to players table...")
            cursor.execute("ALTER TABLE players ADD COLUMN trait_key INTEGER DEFAULT 0")
            conn.commit()
            print("✅ Added trait_key column")
        
        # Get all players without development keys or with development_key = 0
        cursor.execute("""
            SELECT id, player_name, age, registered_position, development_key, trait_key
            FROM players 
            WHERE development_key = 0 OR development_key IS NULL
        """)
        
        players_without_keys = cursor.fetchall()
        
        if not players_without_keys:
            print("✅ All players already have development keys assigned")
            conn.close()
            return {
                'players_processed': 0,
                'new_keys_assigned': 0,
                'existing_keys_preserved': 0
            }
        
        print(f"📊 Found {len(players_without_keys)} players without development keys")
        
        # Assign development keys to each player
        new_keys_assigned = 0
        
        for player in players_without_keys:
            player_id, player_name, age, position, dev_key, trait_key = player
            
            # Generate complete development key (profile + trait)
            profile_key, trait_key = generate_complete_development_key()
            
            # Update the player's development keys
            cursor.execute("""
                UPDATE players 
                SET development_key = ?, trait_key = ?
                WHERE id = ?
            """, (profile_key, trait_key, player_id))
            
            new_keys_assigned += 1
            
            # Progress indicator
            if new_keys_assigned % 100 == 0:
                print(f"📈 Processed {new_keys_assigned} players...")
        
        conn.commit()
        conn.close()
        
        print(f"✅ Successfully assigned development keys to {new_keys_assigned} players")
        
        return {
            'players_processed': len(players_without_keys),
            'new_keys_assigned': new_keys_assigned,
            'existing_keys_preserved': 0
        }
        
    except Exception as e:
        print(f"❌ Error assigning development keys: {e}")
        if conn:
            conn.close()
        return {
            'players_processed': 0,
            'new_keys_assigned': 0,
            'existing_keys_preserved': 0,
            'error': str(e)
        }

def verify_development_keys(db_path: str) -> dict:
    """
    Verify that all players have development keys assigned.
    
    Args:
        db_path: Path to the SQLite database
    
    Returns:
        Dictionary with verification results
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if trait_key column exists
        cursor.execute("PRAGMA table_info(players)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'trait_key' not in columns:
            print("❌ trait_key column not found in players table")
            conn.close()
            return {'error': 'trait_key column not found'}
        
        # Count players with and without development keys
        cursor.execute("""
            SELECT 
                COUNT(*) as total_players,
                SUM(CASE WHEN development_key = 0 OR development_key IS NULL THEN 1 ELSE 0 END) as without_profile,
                SUM(CASE WHEN trait_key IS NULL THEN 1 ELSE 0 END) as without_trait,
                SUM(CASE WHEN development_key > 0 AND trait_key IS NOT NULL THEN 1 ELSE 0 END) as with_both_keys
            FROM players
        """)
        
        result = cursor.fetchone()
        total_players, without_profile, without_trait, with_both_keys = result
        
        # Show trait distribution
        cursor.execute("""
            SELECT trait_key, COUNT(*) as count
            FROM players 
            WHERE trait_key IS NOT NULL
            GROUP BY trait_key
            ORDER BY trait_key
        """)
        
        trait_distribution = cursor.fetchall()
        
        # Get some sample players with their keys
        cursor.execute("""
            SELECT player_name, age, registered_position, development_key, trait_key
            FROM players 
            WHERE development_key > 0 AND trait_key IS NOT NULL
            ORDER BY RANDOM() 
            LIMIT 5
        """)
        
        sample_players = cursor.fetchall()
        
        conn.close()
        
        print(f"📊 DEVELOPMENT KEYS VERIFICATION:")
        print(f"   Total Players: {total_players}")
        print(f"   Without Profile Key: {without_profile}")
        print(f"   Without Trait Key: {without_trait}")
        print(f"   With Both Keys: {with_both_keys}")
        
        print(f"\n🎭 TRAIT DISTRIBUTION:")
        for trait_key, count in trait_distribution:
            trait_name = DEVELOPMENT_TRAITS.get(trait_key, {}).get('name', f'unknown_{trait_key}')
            percentage = (count / total_players) * 100
            print(f"   {trait_name}: {count} ({percentage:.1f}%)")
        
        if sample_players:
            print(f"\n🎭 SAMPLE PLAYERS WITH DEVELOPMENT KEYS:")
            for player in sample_players:
                name, age, position, profile_key, trait_key = player
                profile_info = decode_mixed_development_key(profile_key)
                trait_info = decode_development_trait(trait_key)
                
                if profile_info.get('is_mixed', False):
                    # For mixed profiles, show the first profile name
                    profile_names = profile_info.get('profile_names', ['mixed'])
                    profile_name = profile_names[0] if profile_names else 'mixed'
                else:
                    profile_name = profile_info.get('profile_name', 'unknown')
                
                trait_name = trait_info.get('trait_name', 'unknown')
                
                print(f"   {name} ({position}, {age}yo): {profile_name} | {trait_name}")
        
        return {
            'total_players': total_players,
            'without_profile': without_profile,
            'without_trait': without_trait,
            'with_both_keys': with_both_keys,
            'sample_players': sample_players
        }
        
    except Exception as e:
        print(f"❌ Error verifying development keys: {e}")
        if conn:
            conn.close()
        return {'error': str(e)} 

# Global cache for position averages
_POSITION_AVERAGES_CACHE = None
_POSITION_AVERAGES_CACHE_DB_PATH = None

# Cache for seed player targets from original.sqlite
_SEED_TARGETS_CACHE: Dict[int, Dict[str, int]] = {}

def get_seed_player_targets(seed_player_id: int, original_db_path: str = 'original.sqlite') -> Optional[Dict[str, int]]:
    """Fetch and cache seed player's target skills from original.sqlite.
    Returns a dict mapping skill names used by development to target ints.
    """
    try:
        if not seed_player_id:
            return None
        if seed_player_id in _SEED_TARGETS_CACHE:
            return _SEED_TARGETS_CACHE[seed_player_id]
        conn = sqlite3.connect(original_db_path)
        cur = conn.cursor()
        # Columns aligned with development skill set
        cur.execute(
            """
            SELECT 
                attack, defense, balance, stamina, top_speed, acceleration,
                response, agility, dribble_accuracy, dribble_speed,
                short_pass_accuracy, short_pass_speed, long_pass_accuracy, long_pass_speed,
                shot_accuracy, shot_power, shot_technique, free_kick_accuracy, swerve,
                heading, jump, technique, aggression, mentality, goal_keeping,
                team_work
            FROM players WHERE id = ?
            """,
            (seed_player_id,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        cols = [
            'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
            'response', 'agility', 'dribble_accuracy', 'dribble_speed',
            'short_pass_accuracy', 'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed',
            'shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy', 'swerve',
            'heading', 'jump', 'technique', 'aggression', 'mentality', 'goal_keeping',
            'team_work'
        ]
        targets = {col: int(row[idx]) if row[idx] is not None else None for idx, col in enumerate(cols)}
        _SEED_TARGETS_CACHE[seed_player_id] = targets
        return targets
    except Exception:
        return None

def get_cached_position_averages(db_path: str) -> pd.DataFrame:
    """
    Get cached position averages or calculate them if not cached.
    
    Args:
        db_path: Path to the database
    
    Returns:
        DataFrame with position averages
    """
    global _POSITION_AVERAGES_CACHE, _POSITION_AVERAGES_CACHE_DB_PATH
    
    # Check if we have cached data for this database
    if (_POSITION_AVERAGES_CACHE is not None and 
        _POSITION_AVERAGES_CACHE_DB_PATH == db_path):
        return _POSITION_AVERAGES_CACHE
    
    # Calculate and cache position averages
    print("📊 Calculating position averages (this will be cached)...")
    _POSITION_AVERAGES_CACHE = calculate_position_averages_from_db(db_path)
    _POSITION_AVERAGES_CACHE_DB_PATH = db_path
    
    return _POSITION_AVERAGES_CACHE

def clear_position_averages_cache():
    """Clear the position averages cache (useful for testing)"""
    global _POSITION_AVERAGES_CACHE, _POSITION_AVERAGES_CACHE_DB_PATH
    _POSITION_AVERAGES_CACHE = None
    _POSITION_AVERAGES_CACHE_DB_PATH = None

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
    # Use global constants for GK_BOOST and DEF_BOOST (defined at module level)
    DEF_NAME = 'DEFENSE'
    GK_NAME = 'GOAL KEEPING'
    DIV = 1000.0
    POW = 3.0
    SCALER = 1170000.0
    
    pos = player_row['registered_position']
    pos_clean = pos if pd.notna(pos) else 'Unknown Position'
    
    # Get position as integer for position-specific boosts
    try:
        if isinstance(pos, str):
            pos_int = int(pos.strip())
        elif isinstance(pos, (int, float)):
            pos_int = int(pos)
        else:
            pos_int = -1
    except (ValueError, TypeError):
        pos_int = -1
    
    if pos_avg_df is None or pos_clean not in pos_avg_df.index:
        pos_spec_avg = pd.Series(NORM, index=skills)
    else:
        pos_spec_avg = pos_avg_df.loc[pos_clean]
        if not isinstance(pos_spec_avg, pd.Series):
            pos_spec_avg = pd.Series(NORM, index=skills)

    # Use global constants for salary configuration (defined at module level, lines 21-31)
    # Define which skills get boosted for each position (case-insensitive matching)
    gk_boost_skills = ['defense', 'balance', 'response', 'agility', 'goal_keeping']
    cb_boost_skills = ['defense', 'balance', 'heading', 'jump']

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
        
        # Apply position-specific skill boosts (before global boosts)
        # Convert skill name to lowercase for case-insensitive matching
        skill_n_lower = skill_n.lower()
        if pos_int == 0 and skill_n_lower in gk_boost_skills:
            # Goalkeeper: boost key defensive skills (Defense, Balance, Response, Agility, Goal Keeping)
            contrib *= POSITION_SKILL_BOOST
        elif pos_int in [2, 3] and skill_n_lower in cb_boost_skills:
            # Sweeper/Centre-back: boost key defensive skills (Defense, Balance, Heading, Jump)
            contrib *= POSITION_SKILL_BOOST
        
        # Apply existing global skill boosts (these are still applied on top of position boosts)
        # Note: DEF_NAME is 'DEFENSE', GK_NAME is 'GOAL KEEPING' (with space), but skill_n is 'goal_keeping' (with underscore)
        if skill_n.upper() == DEF_NAME.upper() or skill_n_lower == 'defense':
            contrib *= DEF_BOOST
        elif skill_n.upper().replace('_', ' ') == GK_NAME.upper() or skill_n_lower == 'goal_keeping':
            contrib *= GK_BOOST
        
        if skill_n in binaries:
            contrib *= BIN_IMPACT
        
        twss += contrib
    
    twss = max(0, twss)
    norm_twss = twss / DIV
    pow_score = math.pow(max(0, norm_twss), POW)
    sal_skills = pow_score * SCALER
    calc_sal = GLOBAL_BASE_SALARY + sal_skills
    
    # Apply positional salary boosts (affect all players in these positions regardless of ability)
    if pos_int == 0:
        # Goalkeeper position boost
        calc_sal = calc_sal * GK_POSITION_BOOST
        
        # Apply salary compression: compress toward a reference salary based on overall rating
        # This pulls low salaries up and high salaries down toward a center point
        try:
            overall = float(player_row.get('overall', GK_COMPRESSION_REFERENCE_OVERALL))
            if pd.isna(overall) or overall <= 0:
                overall = GK_COMPRESSION_REFERENCE_OVERALL
        except (ValueError, TypeError):
            overall = GK_COMPRESSION_REFERENCE_OVERALL
        
        # Estimate reference salary for this overall rating (using power law approximation)
        # Reference scales with overall^3 to match the salary calculation's power function
        overall_factor = (overall / 75.0) ** 3
        reference_premium = GK_REFERENCE_PREMIUM * overall_factor  # Uses module-level constant
        reference_salary = GLOBAL_BASE_SALARY + reference_premium
        
        # Compress toward reference: low salaries increase, high salaries decrease
        # compression_factor: 0.0 = full compression (all become reference), 1.0 = no compression
        calc_sal = reference_salary + (calc_sal - reference_salary) * GK_SALARY_COMPRESSION
        
    elif pos_int in [2, 3]:
        # Defender position boost (sweepers/centre-backs)
        calc_sal = calc_sal * DEF_POSITION_BOOST
        
        # Apply salary compression: compress toward a reference salary based on overall rating
        try:
            overall = float(player_row.get('overall', DEF_COMPRESSION_REFERENCE_OVERALL))
            if pd.isna(overall) or overall <= 0:
                overall = DEF_COMPRESSION_REFERENCE_OVERALL
        except (ValueError, TypeError):
            overall = DEF_COMPRESSION_REFERENCE_OVERALL
        
        # Estimate reference salary for this overall rating
        overall_factor = (overall / 75.0) ** 3
        reference_premium = DEF_REFERENCE_PREMIUM * overall_factor  # Uses module-level constant
        reference_salary = GLOBAL_BASE_SALARY + reference_premium
        
        # Compress toward reference: low salaries increase, high salaries decrease
        calc_sal = reference_salary + (calc_sal - reference_salary) * DEF_SALARY_COMPRESSION
    
    elif pos_int in [4, 6]:
        # Side-back position boost (fullbacks/wingbacks - positions 4 and 6)
        calc_sal = calc_sal * SB_POSITION_BOOST
        
        # Apply salary compression: compress toward a reference salary based on overall rating
        try:
            overall = float(player_row.get('overall', SB_COMPRESSION_REFERENCE_OVERALL))
            if pd.isna(overall) or overall <= 0:
                overall = SB_COMPRESSION_REFERENCE_OVERALL
        except (ValueError, TypeError):
            overall = SB_COMPRESSION_REFERENCE_OVERALL
        
        # Estimate reference salary for this overall rating
        overall_factor = (overall / 75.0) ** 3
        reference_premium = SB_REFERENCE_PREMIUM * overall_factor  # Uses module-level constant
        reference_salary = GLOBAL_BASE_SALARY + reference_premium
        
        # Compress toward reference: low salaries increase, high salaries decrease
        calc_sal = reference_salary + (calc_sal - reference_salary) * SB_SALARY_COMPRESSION
    
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

# --- Player Development System ---

# Development Profiles with rarity and characteristics
DEVELOPMENT_PROFILES = {
    0: {'name': 'regular', 'rarity': 0.40, 'description': 'Standard development curve'},
    1: {'name': 'late_bloomer', 'rarity': 0.15, 'description': 'Peaks later in career'},
    2: {'name': 'early_peak', 'rarity': 0.12, 'description': 'Peaks early, declines faster'},
    3: {'name': 'consistent', 'rarity': 0.10, 'description': 'Steady development throughout'},
    4: {'name': 'decliner', 'rarity': 0.08, 'description': 'Declines earlier than normal'},
    5: {'name': 'stronghold', 'rarity': 0.05, 'description': 'Ages gracefully, minimal decline'},
    6: {'name': 'one_time_wonder', 'rarity': 0.04, 'description': '2-3 years of amazing growth, then decline'},
    7: {'name': 'bust', 'rarity': 0.03, 'description': 'Good start, abrupt decline'},
    8: {'name': 'GOAT', 'rarity': 0.02, 'description': 'Consistent excellence throughout career'},
    9: {'name': 'el_crapo', 'rarity': 0.01, 'description': 'Poor development, struggles to improve'}
}

# Development Traits (complementary to profiles)
DEVELOPMENT_TRAITS = {
    0: {'name': 'regular', 'rarity': 0.90, 'description': 'Follows positional skill averages'},
    1: {'name': 'jokester', 'rarity': 0.03, 'description': 'Develops wrong skills for position'},
    2: {'name': 'sharpie', 'rarity': 0.05, 'description': 'Overvalues shooting, decreases physical'},
    3: {'name': 'genetic_freak', 'rarity': 0.02, 'description': 'Opposite of sharpie - physical focus'}
}

def generate_development_key(profile_type: int = 0, base_multiplier: float = 1.0) -> int:
    """
    Generate an encrypted development key for a player.
    
    Args:
        profile_type: Type of development profile (0-4)
        base_multiplier: Base growth/decline multiplier (0.5-2.0)
    
    Returns:
        Encrypted development key (integer)
    """
    # Simple encryption: combine profile type and multiplier
    # In a real system, this would be more sophisticated
    profile_encoded = profile_type * 1000
    multiplier_encoded = int(base_multiplier * 100)
    
    # Combine into a single key
    development_key = profile_encoded + multiplier_encoded
    
    return development_key

def decode_development_key(development_key: int) -> dict:
    """
    Decode a development key to get profile information.
    
    Args:
        development_key: The encrypted development key
    
    Returns:
        Dictionary with profile_type and base_multiplier
    """
    profile_type = development_key // 1000
    multiplier_encoded = development_key % 1000
    base_multiplier = multiplier_encoded / 100.0
    
    return {
        'profile_type': profile_type,
        'base_multiplier': base_multiplier,
        'profile_name': DEVELOPMENT_PROFILES.get(profile_type, {}).get('name', 'unknown')
    }

def generate_mixed_development_key() -> int:
    """
    Generate a mixed development key with multiple profiles.
    
    Returns:
        Integer key representing mixed development profiles
    """
    # 95% chance for mixed profiles, 5% for pure profiles
    if random.random() < 0.95:
        # Mixed profile - combine 2-3 profiles with minimum 10% chunks
        num_profiles = random.randint(2, 3)
        profiles = []
        
        # Select profiles based on rarity
        available_profiles = list(DEVELOPMENT_PROFILES.keys())
        weights = [DEVELOPMENT_PROFILES[p]['rarity'] for p in available_profiles]
        
        # Normalize weights
        total_weight = sum(weights)
        weights = [w/total_weight for w in weights]
        
        # Select profiles (ensure we get valid profiles)
        attempts = 0
        while len(profiles) < num_profiles and attempts < 20:
            profile = random.choices(available_profiles, weights=weights)[0]
            if profile not in profiles and profile in DEVELOPMENT_PROFILES:
                profiles.append(profile)
            attempts += 1
        
        # If we still don't have enough profiles, fill with regular
        while len(profiles) < num_profiles:
            profiles.append(0)  # Add regular profile as fallback
        
        # Generate weights for each profile (must sum to 1.0, minimum 10% each)
        profile_weights = []
        remaining_weight = 1.0
        
        for i, profile in enumerate(profiles):
            if i == len(profiles) - 1:
                # Last profile gets remaining weight (minimum 10%)
                profile_weights.append(max(0.1, remaining_weight))
            else:
                # Random weight between 10% and remaining_weight - 10% * remaining profiles
                min_weight = 0.1
                max_weight = remaining_weight - 0.1 * (len(profiles) - i - 1)
                weight = random.uniform(min_weight, max_weight)
                profile_weights.append(weight)
                remaining_weight -= weight
        
        # Normalize weights to ensure they sum to exactly 1.0
        total_weight = sum(profile_weights)
        profile_weights = [w / total_weight for w in profile_weights]
        
        # Generate base_multiplier using Beta distribution (same as single profiles)
        base_multiplier = 0.1 + 2.9 * random.betavariate(2, 2)
        
        # Enhanced encoding: high bit + num_profiles + profiles + weights + base_multiplier
        encoded = 0x80000000  # High bit indicates mixed
        encoded |= (num_profiles << 24)  # Number of profiles
        
        # Encode profiles (max 3 profiles, 4 bits each)
        for i, profile in enumerate(profiles):
            encoded |= (profile << (16 + i * 4))
        
        # Encode weights (max 3 weights, 8 bits each)
        for i, weight in enumerate(profile_weights):
            encoded |= (int(weight * 100) << (i * 8))
        
        # Encode base_multiplier (multiply by 1000 for precision, use remaining bits)
        # We'll use a different approach: store base_multiplier in the lower 16 bits
        # by shifting everything else up
        encoded = (encoded << 16) | (int(base_multiplier * 1000) & 0xFFFF)
        
        return encoded
    else:
        # Single profile - use original system
        profile_type = random.choices(
            list(DEVELOPMENT_PROFILES.keys()),
            weights=[DEVELOPMENT_PROFILES[p]['rarity'] for p in DEVELOPMENT_PROFILES.keys()]
        )[0]
        # Use Beta distribution: mean ~1.5, 90% between 0.5-2.5, 5% tails
        base_multiplier = 0.1 + 2.9 * random.betavariate(2, 2)
        return generate_development_key(profile_type, base_multiplier)

def generate_development_trait() -> int:
    """
    Generate a development trait for a player.
    
    Returns:
        Integer representing the development trait
    """
    trait_type = random.choices(
        list(DEVELOPMENT_TRAITS.keys()),
        weights=[DEVELOPMENT_TRAITS[t]['rarity'] for t in DEVELOPMENT_TRAITS.keys()]
    )[0]
    
    # Simple encoding: trait type in the lower 8 bits
    return trait_type

def decode_development_trait(trait_key: int) -> dict:
    """
    Decode a development trait key.
    
    Args:
        trait_key: Integer trait key
    
    Returns:
        Dictionary with trait information
    """
    trait_type = trait_key & 0xFF  # Lower 8 bits
    
    return {
        'trait_type': trait_type,
        'trait_name': DEVELOPMENT_TRAITS.get(trait_type, {}).get('name', 'unknown'),
        'description': DEVELOPMENT_TRAITS.get(trait_type, {}).get('description', 'Unknown trait')
    }

def apply_development_trait_effects(position_weights: dict, trait_type: int) -> dict:
    """
    Apply development trait effects to position weights.
    
    Args:
        position_weights: Original position weights
        trait_type: Development trait type
    
    Returns:
        Modified position weights
    """
    modified_weights = position_weights.copy()
    
    if trait_type == 1:  # Jokester - develop wrong skills
        # Invert the weights (skills with low weights get high weights)
        max_weight = max(modified_weights.values())
        for skill in modified_weights:
            if modified_weights[skill] > 1.0:
                modified_weights[skill] = max(1.0, max_weight - modified_weights[skill] + 1.0)
    
    elif trait_type == 2:  # Sharpie - overvalue shooting, decrease physical
        # Boost shooting-related skills
        shooting_skills = ['shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy']
        physical_skills = ['top_speed', 'acceleration', 'stamina', 'jump', 'balance']
        
        for skill in shooting_skills:
            if skill in modified_weights:
                modified_weights[skill] *= 1.5
        
        for skill in physical_skills:
            if skill in modified_weights:
                modified_weights[skill] *= 0.7
    
    elif trait_type == 3:  # Genetic freak - opposite of sharpie
        # Boost physical skills, decrease shooting
        shooting_skills = ['shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy']
        physical_skills = ['top_speed', 'acceleration', 'stamina', 'jump', 'balance']
        
        for skill in physical_skills:
            if skill in modified_weights:
                modified_weights[skill] *= 1.5
        
        for skill in shooting_skills:
            if skill in modified_weights:
                modified_weights[skill] *= 0.7
    
    # Regular trait (0) doesn't modify weights
    return modified_weights

def generate_complete_development_key() -> tuple:
    """
    Generate a complete development key with both profile and trait.
    
    Returns:
        Tuple of (profile_key, trait_key)
    """
    profile_key = generate_mixed_development_key()
    trait_key = generate_development_trait()
    
    return profile_key, trait_key

def decode_complete_development_key(profile_key: int, trait_key: int) -> dict:
    """
    Decode a complete development key with both profile and trait.
    
    Args:
        profile_key: Profile development key
        trait_key: Trait development key
    
    Returns:
        Dictionary with complete development information
    """
    profile_info = decode_mixed_development_key(profile_key)
    trait_info = decode_development_trait(trait_key)
    
    return {
        'profile': profile_info,
        'trait': trait_info
    }

def decode_mixed_development_key(development_key: int) -> dict:
    """
    Decode a mixed development key.
    
    Args:
        development_key: Integer key to decode
    
    Returns:
        Dictionary with profile information
    """
    if development_key & 0x80000000:  # Mixed profile
        # Extract base_multiplier from lower 16 bits
        base_multiplier_encoded = development_key & 0xFFFF
        base_multiplier = base_multiplier_encoded / 1000.0
        
        # Extract other data from upper bits (shifted right by 16)
        shifted_key = development_key >> 16
        
        # Extract number of profiles
        num_profiles = (shifted_key >> 24) & 0xFF
        
        profiles = []
        weights = []
        
        # Extract profiles (max 3 profiles, 4 bits each)
        for i in range(min(num_profiles, 3)):  # Limit to 3 profiles maximum
            profile_type = (shifted_key >> (16 + i * 4)) & 0xF
            if profile_type in DEVELOPMENT_PROFILES:  # Only add valid profiles
                profiles.append(profile_type)
        
        # Extract weights (max 3 weights, 8 bits each)
        for i in range(min(num_profiles, 3)):  # Limit to 3 weights maximum
            weight = ((shifted_key >> (i * 8)) & 0xFF) / 100.0
            weights.append(weight)
        
        # Ensure we have matching numbers of profiles and weights
        while len(weights) < len(profiles):
            weights.append(0.0)
        while len(profiles) < len(weights):
            profiles.append(0)  # Default to regular
        
        # Normalize weights to sum to 1.0
        if weights:
            total_weight = sum(weights)
            if total_weight > 0:
                weights = [w / total_weight for w in weights]
        
        return {
            'is_mixed': True,
            'profiles': profiles,
            'weights': weights,
            'base_multiplier': base_multiplier,
            'profile_names': [DEVELOPMENT_PROFILES.get(p, {}).get('name', 'unknown') for p in profiles],
            'descriptions': [DEVELOPMENT_PROFILES.get(p, {}).get('description', 'Unknown profile') for p in profiles]
        }
    else:
        # Single profile - use original decoding
        return decode_development_key(development_key)

def get_age_development_multiplier(age: int, profile_type: int) -> float:
    """
    Get development multiplier based on age and profile type.
    
    Args:
        age: Player age
        profile_type: Development profile type (0-9)
    
    Returns:
        Development multiplier (positive for growth, negative for decline)
    """
    if profile_type == 0:  # Regular
        if age <= 23:
            return 1.2825  # Good growth (1.425 * 0.9)
        elif age <= 28:
            return 0.6075  # Moderate growth (0.675 * 0.9)
        elif age <= 32:
            # Minimal random floor in late-20s/early-30s to avoid stasis
            return random.uniform(-2, 0)
        elif age <= 35:
            return -0.4725  # Mild decline (-0.525 * 0.9)
        else:
            return -0.8775  # Strong decline (-0.975 * 0.9)
    
    elif profile_type == 1:  # Late bloomer
        if age <= 25:
            return 0.8775  # Moderate growth (0.975 * 0.9)
        elif age <= 30:
            return 1.5525  # Strong growth (1.725 * 0.9)
        elif age <= 34:
            return 0.4725  # Mild growth (0.525 * 0.9)
        elif age <= 37:
            return -0.4725  # Very mild decline (-0.525 * 0.9)
        else:
            return -1.2825  # Moderate decline (-1.425 * 0.9)
    
    elif profile_type == 2:  # Early peak
        if age <= 20:
            return 2.0925  # Very strong growth (2.325 * 0.9)
        elif age <= 25:
            return 1.1475  # Good growth (1.275 * 0.9)
        elif age <= 28:
            return 0.0  # Peak reached (0.0 * 0.9)
        elif age <= 32:
            return -0.7425  # Moderate decline (-0.825 * 0.9)
        else:
            return -1.2825  # Strong decline (-1.425 * 0.9)
    
    elif profile_type == 3:  # Consistent
        if age <= 26:
            return 1.0125  # Steady growth (1.125 * 0.9)
        elif age <= 32:
            return 0.6075  # Mild growth (0.675 * 0.9)
        elif age <= 36:
            return -0.3375  # Very mild decline (-0.375 * 0.9)
        else:
            return -0.4725  # Mild decline (-0.525 * 0.9)
    
    elif profile_type == 4:  # Decliner
        if age <= 22:
            return 0.54  # Moderate growth (0.6 * 0.9)
        elif age <= 26:
            return 0.135  # Mild growth (0.15 * 0.9)
        elif age <= 30:
            return -0.6075  # Early decline (-0.675 * 0.9)
        elif age <= 34:
            return -0.8775  # Moderate decline (-0.975 * 0.9)
        else:
            return -1.2825  # Strong decline (-1.425 * 0.9)
    
    elif profile_type == 5:  # Stronghold
        if age <= 25:
            return 1.2825  # Good growth (1.425 * 0.9)
        elif age <= 30:
            return 0.8775  # Moderate growth (0.975 * 0.9)
        elif age <= 35:
            return 0.6075  # Mild growth (0.675 * 0.9)
        elif age <= 40:
            return 0.0  # Stagnation (0.0 * 0.9)
        else:
            return -0.3375  # Very mild decline (-0.375 * 0.9)
    
    elif profile_type == 6:  # One-time wonder
        if age <= 20:
            return 0.4725  # Moderate growth (0.525 * 0.9)
        elif age <= 23:
            return 2.4975  # Amazing growth period (2.775 * 0.9)
        elif age <= 26:
            return 1.35  # Still strong (1.5 * 0.9)
        elif age <= 29:
            return 0.2025  # Decline starts (0.225 * 0.9)
        else:
            return -0.8775  # Sharp decline (-0.975 * 0.9)
    
    elif profile_type == 7:  # Bust
        if age <= 22:
            return 1.215  # Good start (1.35 * 0.9)
        elif age <= 25:
            return 0.2025  # Moderate growth (0.225 * 0.9)
        elif age <= 28:
            return -0.7425  # Abrupt decline (-0.825 * 0.9)
        else:
            return -1.2825  # Severe decline (-1.425 * 0.9)
    
    elif profile_type == 8:  # GOAT
        if age <= 25:
            return 1.35  # Strong growth (1.5 * 0.9)
        elif age <= 30:
            return 1.1475  # Good growth (1.275 * 0.9)
        elif age <= 35:
            return 0.7425  # Moderate growth (0.825 * 0.9)
        elif age <= 40:
            return -0.2025  # Mild growth (-0.225 * 0.9)
        else:
            return -0.6075  # Maintains level (-0.675 * 0.9)
    
    elif profile_type == 9:  # El Crapo
        if age <= 22:
            return 0.27  # Poor growth (0.3 * 0.9)
        elif age <= 25:
            return 0.0  # Stagnation (0.0 * 0.9)
        elif age <= 28:
            return -0.7425  # Early decline (-0.825 * 0.9)
        elif age <= 32:
            return -0.8775  # Moderate decline (-0.975 * 0.9)
        else:
            return -1.2825  # Severe decline (-1.425 * 0.9)
    
    else:  # Default to regular
        return get_age_development_multiplier(age, 0)

def calculate_player_skill_development(player_data: dict, development_key: int = 0, trait_key: int = 0) -> dict:
    """
    Calculate skill development for a player based on their development key, trait, and position.
    
    Args:
        player_data: Player data dictionary
        development_key: Encrypted development key (can be mixed or single)
        trait_key: Development trait key
    
    Returns:
        Dictionary with skill changes for the player
    """
    # Decode development key (handles both mixed and single profiles)
    dev_info = decode_mixed_development_key(development_key)
    trait_info = decode_development_trait(trait_key)
    
    # Get age and position
    age = player_data.get('age', 25)
    registered_position = str(player_data.get('registered_position', 7))
    
    # Calculate mixed profile multiplier if applicable
    if dev_info.get('is_mixed', False):
        profiles = dev_info['profiles']
        weights = dev_info['weights']
        
        # Calculate weighted average of age multipliers
        total_age_multiplier = 0
        for profile_type, weight in zip(profiles, weights):
            age_mult = get_age_development_multiplier(age, profile_type)
            total_age_multiplier += age_mult * weight
        
        age_multiplier = total_age_multiplier
        # Mixed profiles use stored base_multiplier from development key
        # Scale from current range (0-10) to target range (0.5-5)
        raw_base_multiplier = dev_info['base_multiplier']
        base_multiplier = 0.5 + (raw_base_multiplier / 10.0) * 4.5  # Scale 0-10 to 0.5-5
        # Create clean mixed profile name
        mixed_parts = []
        for i, name in enumerate(dev_info['profile_names']):
            weight = dev_info['weights'][i] * 100
            mixed_parts.append(f"{name}({weight:.0f}%)")
        profile_name = f"Mixed: {'/'.join(mixed_parts)}"
        profile_type = profiles[0]  # Use first profile for reference
    else:
        # Single profile
        profile_type = dev_info['profile_type']
        # Scale from current range (0-10) to target range (0.5-5)
        raw_base_multiplier = dev_info['base_multiplier']
        base_multiplier = 0.5 + (raw_base_multiplier / 10.0) * 4.5  # Scale 0-10 to 0.5-5
        age_multiplier = get_age_development_multiplier(age, profile_type)
        profile_name = dev_info['profile_name']
    
    # Get cached position averages for skill weights
    pos_avg_df = get_cached_position_averages('pes6_league_db.sqlite')
    
    # Get position-specific skill weights based on position averages
    position_weights = get_position_skill_weights_from_averages(pos_avg_df, registered_position)
    
    # Apply development trait effects
    position_weights = apply_development_trait_effects(position_weights, trait_info['trait_type'])
    
    # Harden decline after age 32 across profiles: make negative age multipliers more negative
    try:
        age_int = int(age)
    except Exception:
        age_int = 25
    if age_int > 32 and age_multiplier < 0:
        age_multiplier -= random.uniform(-0.2, 2.75)
    # Additional decline step after 36
    if age_int > 36 and age_multiplier < 0:
        age_multiplier -= random.uniform(-0.2, 3.25)
    # Additional decline step after 40
    if age_int > 40 and age_multiplier < 0:
        age_multiplier -= random.uniform(1.0, 4.0)

    # Calculate final development multiplier (separate natural vs performance components)
    base_growth = age_multiplier * base_multiplier
    
    # Calculate performance-based boost
    # Get db_path from player_data if available, otherwise use default
    db_path = player_data.get('db_path', 'pes6_league_db.sqlite')
    performance_boost = calculate_performance_boost(player_data, db_path)
    # Separate natural development from performance-driven development
    # Natural works even at 0 games (drives youth growth and veteran decline)
    natural_weight = 0.4
    performance_weight = 0.6
    games_played = int(player_data.get('games_played', 0) or 0)
    # Assume ~34 league matches as reference; clamp to 1.0
    games_ratio = min(1.0, max(0.0, games_played / 34.0))
    # Youth floor: allow some growth even with few/no games for young players
    # Stronger floor for <=20, tapering off with age
    if age <= 20:
        youth_floor = 0.35
    elif age <= 22:
        youth_floor = 0.25
    elif age <= 24:
        youth_floor = 0.15
    else:
        youth_floor = 0.05
    effective_games_factor = max(games_ratio, youth_floor)
    perf_factor = 1.0 + 0.6 * float(performance_boost.get('total_boost', 0.0))
    # Compose additively: performance term decoupled from age sign so it mitigates decline
    natural_component = base_multiplier * age_multiplier * natural_weight
    performance_component = base_multiplier * performance_weight * effective_games_factor * perf_factor
    final_multiplier = natural_component + performance_component
    # Define skills that can be developed
    skill_columns = [
        'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
        'response', 'agility', 'dribble_accuracy', 'dribble_speed',
        'short_pass_accuracy', 'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed',
        'shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy', 'swerve',
        'heading', 'jump', 'technique', 'aggression', 'mentality', 'goal_keeping',
        'team_work'
    ]
    
    skill_changes = {}
    total_skill_change = 0
    
    # If player has a seed base, fetch targets
    seed_player_id = None
    try:
        seed_player_id = int(player_data.get('seed_player', 0)) if player_data.get('seed_player') is not None else 0
    except Exception:
        seed_player_id = 0
    seed_targets = get_seed_player_targets(seed_player_id) if seed_player_id else None

    for skill in skill_columns:
        if skill in player_data:
            current_value = int(player_data[skill])
            
            # Skip if skill is not applicable (e.g., goal_keeping for outfield players)
            if skill == 'goal_keeping' and registered_position != '0':
                continue
            
            # Get position weight for this skill from averages
            skill_weight = position_weights.get(skill, 1.0)
            
            # Calculate skill change based on remaining potential or seed target if available
            if final_multiplier > 0:  # Improvement
                # Default remaining potential to 99 ceiling
                remaining_potential = (99) - current_value
                # If seed target exists, steer towards it
                if seed_targets and skill in seed_targets and seed_targets[skill] is not None:
                    target = int(seed_targets[skill])
                    delta_to_target = target - current_value
                    if delta_to_target > 0:
                        # Grow towards seed target rather than 99 ceiling
                        remaining_potential = min(remaining_potential, delta_to_target)
                        # Emphasize important skills more when below target (stronger skew)
                        remaining_potential *= max(1.0, skill_weight ** 1.6)
                    else:
                        # Already above seed target: apply growing penalty that competes with development
                        over_seed = -delta_to_target  # positive amount over target
                        
                        # Tolerance zone (0-3 points over): Player can maintain or slightly improve
                        # This represents natural variance and peak performance capability
                        if over_seed <= 3:
                            # Small penalty that development can overcome
                            # Penalty grows quadratically: 0.1 at +1, 0.4 at +2, 0.9 at +3
                            penalty_factor = (over_seed / 3.0) ** 2
                            remaining_potential = (99 - current_value) * (0.3 - (penalty_factor * 0.25))
                            # At +1: 0.3 - 0.11 = 0.19 (can still grow with good development)
                            # At +2: 0.3 - 0.44 = -0.14 (slight regression unless strong development)
                            # At +3: 0.3 - 0.9 = -0.6 (regression unless exceptional development)
                        
                        # Warning zone (4-6 points over): Strong penalty, hard to maintain
                        elif over_seed <= 6:
                            # Penalty increases significantly
                            # Development strength must be very high to maintain
                            penalty_strength = 0.8 + ((over_seed - 3) * 0.3)  # 0.8 to 1.7
                            importance_factor = max(0.5, skill_weight)
                            penalty_rate = penalty_strength / importance_factor
                            remaining_potential = -penalty_rate * 8.0
                            # Results in -6 to -14 per season depending on importance
                        
                        # Critical zone (7+ points over): Very strong regression
                        else:
                            # Heavy penalty, almost impossible to maintain
                            penalty_strength = 1.5 + ((over_seed - 6) * 0.2)
                            importance_factor = max(0.5, skill_weight)
                            penalty_rate = penalty_strength / importance_factor
                            remaining_potential = -penalty_rate * 12.0
                            # Results in -18 to -30+ per season
                # Apply multiplier scaled down for realistic changes
                # Stronger pull when seed is present (smaller divisor)
                divisor = 24.0 if seed_targets else 45.0
                base_change = (final_multiplier * skill_weight * remaining_potential) / divisor
            else:  # Decline
                # For decline, apply multiplier to current value, scaled down
                base_change = (final_multiplier * skill_weight * current_value) / 100.0
            
            # Performance boost is now applied to final_multiplier, not per skill
            
            # Randomness: tighter when seed-targeted to improve convergence
            if seed_targets:
                skill_random = random.uniform(0.95, 1.05)
            else:
                skill_random = random.uniform(0.7, 1.3)
            skill_change = base_change * skill_random

            # Seed nudge: push towards seed target (with tolerance zone)
            if seed_targets and skill in seed_targets and seed_targets[skill] is not None:
                target = int(seed_targets[skill])
                gap = target - current_value
                if gap != 0:
                    # ε scaled by importance with curvature, still bounded to avoid jumps
                    epsilon = 0.45  # nudge strength per season baseline
                    nudge = epsilon * (max(0.5, skill_weight) ** 1.5)
                    
                    if gap > 0:
                        # Below target: push up (only on improvement years)
                        if final_multiplier > 0:
                            skill_change += min(nudge, gap)
                    else:
                        # Above target: apply downward nudge based on how far over
                        over_amount = abs(gap)
                        
                        # Tolerance zone (0-3 over): minimal to no downward nudge
                        # Let development strength determine if player maintains or regresses
                        if over_amount <= 3:
                            # Very light nudge that only activates if already declining
                            if final_multiplier < 0:  # Only on decline years
                                downward_nudge = min(nudge * 0.3, over_amount)
                                skill_change -= downward_nudge
                        
                        # Warning zone (4-6 over): moderate downward nudge
                        elif over_amount <= 6:
                            downward_nudge = min(nudge * 0.6, over_amount)
                            skill_change -= downward_nudge
                        
                        # Critical zone (7+ over): strong downward nudge
                        else:
                            downward_nudge = min(nudge, over_amount)
                            skill_change -= downward_nudge
            
            # Ensure skill stays within reasonable bounds (1-99) and convert to integer with proper rounding
            new_value = max(1, min(99, round(current_value + skill_change)))
            actual_change = new_value - current_value
            
            skill_changes[skill] = {
                'current': current_value,
                'change': actual_change,
                'new': new_value,
                'weight': skill_weight,
                'performance_boost': performance_boost.get(f'{skill}_boost', 0)
            }
            
            total_skill_change += actual_change
    
    return {
        'development_key': development_key,
        'trait_key': trait_key,
        'profile_type': profile_type,
        'profile_name': profile_name,
        'trait_name': trait_info['trait_name'],
        'trait_description': trait_info['description'],
        'age_multiplier': age_multiplier,
        'base_multiplier': base_multiplier,
        'final_multiplier': final_multiplier,
        'performance_boost': performance_boost,
        'skill_changes': skill_changes,
        'total_skill_change': total_skill_change,
        'skills_improved': len([s for s in skill_changes.values() if s['change'] > 0]),
        'skills_declined': len([s for s in skill_changes.values() if s['change'] < 0]),
        'is_mixed': dev_info.get('is_mixed', False),
        'mixed_profiles': dev_info.get('profile_names', []) if dev_info.get('is_mixed', False) else None,
        'mixed_weights': dev_info.get('weights', []) if dev_info.get('is_mixed', False) else None,
        'binary_skill_changes': develop_binary_skills(player_data)
    }

def get_position_skill_weights_from_averages(pos_avg_df: pd.DataFrame, registered_position: str) -> dict:
    """
    Get skill weights for a specific position based on position averages.
    
    Args:
        pos_avg_df: Position averages dataframe
        registered_position: Player's registered position
    
    Returns:
        Dictionary with skill weights for the position
    """
    if registered_position not in pos_avg_df.index:
        return {'balance': 1.0, 'consistency': 1.0, 'condition_fitness': 1.0}
    
    # Get position averages
    pos_averages = pos_avg_df.loc[registered_position]
    
    # Normalize weights based on position averages
    # Higher average = higher weight for development
    weights = {}
    max_avg = pos_averages.max()
    
    for skill, avg_value in pos_averages.items():
        if avg_value > 0:
            # Weight based on how much this skill is valued for this position
            # Higher average = higher weight for overall calculation
            # For overall calculation, we want weights that sum to 1.0 for the most important skills
            weight = avg_value / max_avg  # Scale to 0-1 range based on position averages
            
            # Only include skills that are significantly important for this position
            if weight >= 0.7:  # Only skills that are at least 70% as important as the most important skill
                weights[skill] = weight
        else:
            weights[skill] = 0.0  # No weight for skills not valued for this position
    
    return weights

def calculate_nationality_strength(nationality: str, db_path: str = 'pes6_league_db.sqlite') -> float:
    """
    Calculate nationality strength based on the number of available players for that country.
    
    Small countries (few players) = lower strength (easier to get selected)
    Large countries (many players) = higher strength (harder to get selected, more prestigious)
    
    Args:
        nationality: Player's nationality
        db_path: Path to database
    
    Returns:
        Strength multiplier (0.5 to 2.0)
        - 0.5 for very small countries (< 20 players)
        - 1.0 for medium countries (20-100 players)
        - 2.0 for large countries (> 200 players)
    """
    if not nationality:
        return 1.0  # Default if no nationality
    
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Count players available for selection (non-draftees with clubs)
        cursor.execute("""
            SELECT COUNT(*) as player_count
            FROM players
            WHERE (nationality = ? OR nationality = ?)
            AND club_id IS NOT NULL
            AND (draftee = 0 OR draftee IS NULL)
        """, (nationality, nationality.strip()))
        
        result = cursor.fetchone()
        player_count = result['player_count'] if result else 0
        conn.close()
        
        # Calculate strength based on player count
        # Very small countries (< 20): 0.5x (easy to get selected)
        # Small countries (20-50): 0.7x
        # Medium countries (50-100): 1.0x (baseline)
        # Large countries (100-200): 1.5x
        # Very large countries (> 200): 2.0x (very prestigious)
        
        if player_count < 20:
            return 0.5
        elif player_count < 50:
            return 0.5 + (player_count - 20) * 0.0067  # Linear from 0.5 to 0.7
        elif player_count < 100:
            return 0.7 + (player_count - 50) * 0.006  # Linear from 0.7 to 1.0
        elif player_count < 200:
            return 1.0 + (player_count - 100) * 0.005  # Linear from 1.0 to 1.5
        else:
            return min(2.0, 1.5 + (player_count - 200) * 0.0025)  # Linear from 1.5 to 2.0 (capped)
            
    except Exception as e:
        # Fallback to default if database query fails
        return 1.0

def calculate_performance_boost(player_data: dict, db_path: str = 'pes6_league_db.sqlite') -> dict:
    """
    Calculate performance-based development boost.
    
    Distributes existing boost between club and international performance.
    International performance is weighted by nationality strength.
    
    Args:
        player_data: Player data dictionary
        db_path: Path to database (for nationality strength calculation)
    
    Returns:
        Dictionary with performance boosts
    """
    # Club performance stats
    games_played = player_data.get('games_played', 0)
    goals = player_data.get('goals', 0)
    assists = player_data.get('assists', 0)
    mvp = player_data.get('MVP', 0)
    
    # International performance stats (current season)
    int_caps = player_data.get('current_season_caps', 0)
    int_goals = player_data.get('current_international_goals', 0)
    int_assists = player_data.get('current_international_assists', 0)
    
    # Calculate nationality strength (affects international boost value)
    nationality = player_data.get('nationality', '')
    nationality_strength = calculate_nationality_strength(nationality, db_path)
    
    # Club performance boosts (original values - these define the baseline)
    games_boost = min(0.5, games_played * 0.02)  # Max 0.5 boost from games
    goals_mvp_combined = goals + mvp
    goals_boost = min(0.8, goals_mvp_combined * 0.1)  # Max 0.8 boost from goals + MVP combined
    assists_boost = min(0.6, assists * 0.08)  # Max 0.6 boost from assists
    total_club_boost = games_boost + goals_boost + assists_boost
    
    # International performance boosts (scaled to match club boost ranges, then weighted by nationality)
    # Use same formulas as club but apply nationality strength multiplier
    int_games_equivalent = int_caps * nationality_strength
    int_goals_equivalent = int_goals * nationality_strength
    int_assists_equivalent = int_assists * nationality_strength
    
    int_caps_boost = min(0.5, int_games_equivalent * 0.02)  # Same max as club games
    int_goals_boost = min(0.8, int_goals_equivalent * 0.1)  # Same max as club goals
    int_assists_boost = min(0.6, int_assists_equivalent * 0.08)  # Same max as club assists
    total_int_boost = int_caps_boost + int_goals_boost + int_assists_boost
    
    # Distribute boost between club and international (not additive)
    # If player has both, blend them proportionally
    # If player has only one, use that one
    # Total should remain similar to original club-only boost
    
    # Calculate relative contribution
    club_contribution = total_club_boost if total_club_boost > 0 else 0
    int_contribution = total_int_boost if total_int_boost > 0 else 0
    total_contribution = club_contribution + int_contribution
    
    if total_contribution > 0:
        # Blend: if both exist, distribute proportionally
        # But cap total to maintain similar magnitude to original
        club_weight = club_contribution / total_contribution if total_contribution > 0 else 1.0
        int_weight = int_contribution / total_contribution if total_contribution > 0 else 0.0
        
        # Distribute the boost (total should be similar to original club boost)
        # If international exists, it replaces part of club boost
        blended_boost = (club_contribution * club_weight) + (int_contribution * int_weight)
        # Cap at original maximum (1.9 = 0.5 + 0.8 + 0.6)
        blended_boost = min(1.9, blended_boost)
    else:
        blended_boost = 0.0
    
    # Additional random factor for performance
    performance_random = random.uniform(0.8, 1.2)
    
    # Final total boost (distributed, not additive)
    total_boost = blended_boost * performance_random
    
    return {
        'games_boost': games_boost * performance_random,
        'goals_boost': goals_boost * performance_random,
        'assists_boost': assists_boost * performance_random,
        'int_caps_boost': int_caps_boost * performance_random,
        'int_goals_boost': int_goals_boost * performance_random,
        'int_assists_boost': int_assists_boost * performance_random,
        'nationality_strength': nationality_strength,
        'total_boost': total_boost
    }

def check_player_retirement(player_data: Dict) -> Dict:
    """
    Check if a player wants to retire based on age, salary, club status, contract, and games played.
    
    Args:
        player_data: Dictionary containing player information
    
    Returns:
        Dictionary with retirement check results
    """
    age = player_data.get('age', 25)
    salary = player_data.get('salary', GLOBAL_BASE_SALARY)
    club_id = player_data.get('club_id')
    contract_years_remaining = player_data.get('contract_years_remaining', 0)
    games_played = player_data.get('games_played', 0)
    
    # Base retirement probability starts at age 30
    if age < 30:
        return {
            'wants_to_retire': False,
            'retirement_probability': 0.0,
            'reason': 'Too young to consider retirement'
        }
    
    # Players with 1+ years contract remaining are not eligible for retirement
    # (This check happens after contract years are reduced at end of season)
    # EXCEPTION: "No Club" players (club_id = 141 or None) ignore contract status
    # Their "contract" represents what they're asking for, not an actual binding contract
    if contract_years_remaining >= 1 and club_id != 141 and club_id is not None:
        return {
            'wants_to_retire': False,
            'retirement_probability': 0.0,
            'reason': f'Under contract for {contract_years_remaining} more years - not eligible for retirement'
        }
    
    # Calculate base retirement probability based on age
    # Probability increases with age - reduced age factor for more moderate progression
    age_factor = (age - 30) / 13.0  # 0 at age 30, 1 at age 44 (slightly slower increase)
    age_probability = min(0.95, age_factor * 0.90)  # Max 80% at age 44+, moderate base rate
    
    # Salary factor - higher salary reduces retirement probability
    # Normalize salary to 0-1 range (0 = low salary, 1 = high salary)
    salary_normalized = min(1.0, salary / 30000000)  # 30M salary = max
    salary_factor = 1.0 - salary_normalized  # Higher salary = lower retirement chance
    
    # Club status factor - No Club players more likely to retire
    club_factor = 0.0
    if club_id == 141 or club_id is None:  # No Club
        club_factor = 0.35  # 25% additional probability
    
    # Games played factor - more games played reduces retirement probability
    # Normalize games played to 0-1 range (0 = no games, 1 = many games)
    # Assuming 30+ games in a season is "very active"
    games_normalized = min(1.0, games_played / 30.0)
    games_factor = games_normalized * 0.25  # Games can reduce probability by up to 25%
    
    # Calculate final retirement probability
    base_probability = age_probability
    salary_adjustment = salary_factor * 0.20  # Salary can reduce probability by up to 20%
    final_probability = base_probability + club_factor - salary_adjustment - games_factor
    
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
        'club_factor': club_factor,
        'games_factor': games_factor
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
    pos_avg_df = get_cached_position_averages(db_path)
    
    # Calculate base salary (includes all position-specific boosts and compression)
    # Position boosts (GK_POSITION_BOOST, DEF_POSITION_BOOST, SB_POSITION_BOOST) and
    # compression are already applied inside calculate_player_salary_base
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
    Calculate market value for a single player using estimated salary.
    
    Args:
        player_data: Dictionary containing player information with skills
    
    Returns:
        Calculated market value (integer)
    """
    # Convert to pandas Series for compatibility
    player_row = pd.Series(player_data)
    
    # Calculate estimated salary instead of using current salary
    try:
        # Get position averages for salary calculation
        pos_avg_df = get_cached_position_averages('pes6_league_db.sqlite')
        
        # Define skill lists (same as in the main salary calculation)
        skills = ['attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
                 'response', 'agility', 'dribble_accuracy', 'dribble_speed',
                 'short_pass_accuracy', 'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed',
                 'shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy', 'swerve',
                 'heading', 'jump', 'technique', 'aggression', 'mentality', 'goal_keeping',
                 'team_work', 'consistency', 'condition_fitness']
        
        binaries = ['dribbling', 'tactical_dribble', 'positioning', 'reaction', 'play_making',
                   'passing', 'scoring', '1-1_score', 'post_player', 'lines', 'middle_shooting',
                   'side', 'centre', 'penalties', '1-touch_pass', 'outside', 'marking', 'sliding',
                   'covering', 'd_line_control', 'penalty_stopper', '1-on-1_stopper', 'long_throw']
        
        # Calculate estimated salary
        estimated_salary = calculate_player_salary_base(player_row, pos_avg_df, skills, binaries)
        
    except Exception as e:
        # Fallback to current salary if calculation fails
        print(f"Warning: Could not calculate estimated salary for market value: {e}")
        estimated_salary = player_data.get('salary', GLOBAL_BASE_SALARY)
    
    # Calculate market value based on estimated salary
    market_value = estimated_salary * 1.5
    age_multiplier = get_age_market_value_multiplier(player_data.get('age', 25))
    market_value = market_value * age_multiplier
    
    # Set market value to 0 for free agents (No Club)
    if player_data.get('club_id') == 141 or player_data.get('club_id') is None:
        market_value = 0
    
    return int(market_value) 

def assign_development_keys_to_players(db_path: str) -> dict:
    """
    Assign development keys (profile + trait) to all players who don't have them.
    
    Args:
        db_path: Path to the SQLite database
    
    Returns:
        Dictionary with assignment results
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # First, check if trait_key column exists, if not add it
        cursor.execute("PRAGMA table_info(players)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'trait_key' not in columns:
            print("📊 Adding trait_key column to players table...")
            cursor.execute("ALTER TABLE players ADD COLUMN trait_key INTEGER DEFAULT 0")
            conn.commit()
            print("✅ Added trait_key column")
        
        # Get all players without development keys or with development_key = 0
        cursor.execute("""
            SELECT id, player_name, age, registered_position, development_key, trait_key
            FROM players 
            WHERE development_key = 0 OR development_key IS NULL
        """)
        
        players_without_keys = cursor.fetchall()
        
        if not players_without_keys:
            print("✅ All players already have development keys assigned")
            conn.close()
            return {
                'players_processed': 0,
                'new_keys_assigned': 0,
                'existing_keys_preserved': 0
            }
        
        print(f"📊 Found {len(players_without_keys)} players without development keys")
        
        # Assign development keys to each player
        new_keys_assigned = 0
        
        for player in players_without_keys:
            player_id, player_name, age, position, dev_key, trait_key = player
            
            # Generate complete development key (profile + trait)
            profile_key, trait_key = generate_complete_development_key()
            
            # Update the player's development keys
            cursor.execute("""
                UPDATE players 
                SET development_key = ?, trait_key = ?
                WHERE id = ?
            """, (profile_key, trait_key, player_id))
            
            new_keys_assigned += 1
            
            # Progress indicator
            if new_keys_assigned % 100 == 0:
                print(f"📈 Processed {new_keys_assigned} players...")
        
        conn.commit()
        conn.close()
        
        print(f"✅ Successfully assigned development keys to {new_keys_assigned} players")
        
        return {
            'players_processed': len(players_without_keys),
            'new_keys_assigned': new_keys_assigned,
            'existing_keys_preserved': 0
        }
        
    except Exception as e:
        print(f"❌ Error assigning development keys: {e}")
        if conn:
            conn.close()
        return {
            'players_processed': 0,
            'new_keys_assigned': 0,
            'existing_keys_preserved': 0,
            'error': str(e)
        }

def verify_development_keys(db_path: str) -> dict:
    """
    Verify that all players have development keys assigned.
    
    Args:
        db_path: Path to the SQLite database
    
    Returns:
        Dictionary with verification results
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if trait_key column exists
        cursor.execute("PRAGMA table_info(players)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'trait_key' not in columns:
            print("❌ trait_key column not found in players table")
            conn.close()
            return {'error': 'trait_key column not found'}
        
        # Count players with and without development keys
        cursor.execute("""
            SELECT 
                COUNT(*) as total_players,
                SUM(CASE WHEN development_key = 0 OR development_key IS NULL THEN 1 ELSE 0 END) as without_profile,
                SUM(CASE WHEN trait_key IS NULL THEN 1 ELSE 0 END) as without_trait,
                SUM(CASE WHEN development_key > 0 AND trait_key IS NOT NULL THEN 1 ELSE 0 END) as with_both_keys
            FROM players
        """)
        
        result = cursor.fetchone()
        total_players, without_profile, without_trait, with_both_keys = result
        
        # Show trait distribution
        cursor.execute("""
            SELECT trait_key, COUNT(*) as count
            FROM players 
            WHERE trait_key IS NOT NULL
            GROUP BY trait_key
            ORDER BY trait_key
        """)
        
        trait_distribution = cursor.fetchall()
        
        # Get some sample players with their keys
        cursor.execute("""
            SELECT player_name, age, registered_position, development_key, trait_key
            FROM players 
            WHERE development_key > 0 AND trait_key IS NOT NULL
            ORDER BY RANDOM() 
            LIMIT 5
        """)
        
        sample_players = cursor.fetchall()
        
        conn.close()
        
        print(f"📊 DEVELOPMENT KEYS VERIFICATION:")
        print(f"   Total Players: {total_players}")
        print(f"   Without Profile Key: {without_profile}")
        print(f"   Without Trait Key: {without_trait}")
        print(f"   With Both Keys: {with_both_keys}")
        
        print(f"\n🎭 TRAIT DISTRIBUTION:")
        for trait_key, count in trait_distribution:
            trait_name = DEVELOPMENT_TRAITS.get(trait_key, {}).get('name', f'unknown_{trait_key}')
            percentage = (count / total_players) * 100
            print(f"   {trait_name}: {count} ({percentage:.1f}%)")
        
        if sample_players:
            print(f"\n🎭 SAMPLE PLAYERS WITH DEVELOPMENT KEYS:")
            for player in sample_players:
                name, age, position, profile_key, trait_key = player
                profile_info = decode_mixed_development_key(profile_key)
                trait_info = decode_development_trait(trait_key)
                
                if profile_info.get('is_mixed', False):
                    # For mixed profiles, show the first profile name
                    profile_names = profile_info.get('profile_names', ['mixed'])
                    profile_name = profile_names[0] if profile_names else 'mixed'
                else:
                    profile_name = profile_info.get('profile_name', 'unknown')
                
                trait_name = trait_info.get('trait_name', 'unknown')
                
                print(f"   {name} ({position}, {age}yo): {profile_name} | {trait_name}")
        
        return {
            'total_players': total_players,
            'without_profile': without_profile,
            'without_trait': without_trait,
            'with_both_keys': with_both_keys,
            'sample_players': sample_players
        }
        
    except Exception as e:
        print(f"❌ Error verifying development keys: {e}")
        if conn:
            conn.close()
        return {'error': str(e)} 

# ============================================================================
# PLAYER GENERATION SYSTEM
# ============================================================================

import random
import json
from typing import Dict, List, Tuple

# Nationality data with skin color mapping (PES6 numbering: 1python 4=dark)
# ============================================================================
# NATIONALITY DATA STRUCTURE
# ============================================================================
# Each nationality entry should have:
#   - probability: Generation probability (0.0 to 1.0) - UPFRONT for clarity
#   - skin_color: List of tuples [(skin_value, probability), ...] for probabilistic selection
#                 Example: [(1, 0.5), (3, 0.3), (4, 0.2)] means 50% skin=1, 30% skin=3, 20% skin=4
#   - first_names: List of first names (separate from surnames)
#   - surnames: List of surnames (separate from first_names)
#
# NOTE: The code supports both old structure (with 'weight'/'names'/'skin_color' as int + SURNAME_DATA)
#       and new structure (with 'probability'/'first_names'/'surnames'/'skin_color' as list) for
#       backward compatibility during migration.
# ============================================================================

def select_skin_color(nationality: str) -> int:
    """
    Select skin color probabilistically based on nationality.
    Supports both old structure (single int) and new structure (list of tuples).
    
    Args:
        nationality: Nationality name
        
    Returns:
        Skin color value (1-4)
    """
    if nationality not in NATIONALITY_DATA:
        return 1  # Default fallback
    
    skin_color_data = NATIONALITY_DATA[nationality].get('skin_color', 1)
    
    # New structure: list of tuples [(skin_value, probability), ...]
    if isinstance(skin_color_data, list):
        skin_values = [sc[0] for sc in skin_color_data]
        probabilities = [sc[1] for sc in skin_color_data]
        # Normalize probabilities
        total_prob = sum(probabilities)
        if total_prob > 0:
            normalized_probs = [p / total_prob for p in probabilities]
            return random.choices(skin_values, weights=normalized_probs)[0]
        else:
            return 1  # Fallback if probabilities sum to 0
    
    # Old structure: single integer
    return int(skin_color_data)
NATIONALITY_DATA = {
    'Brazil': {
        'probability': 0.050655,
        'skin_color': [(1, 0.50), (3, 0.30), (4, 0.20)],  # 50% skin=1, 30% skin=3, 20% skin=4
        'first_names': ['Puca','Chama','Alex','Julius','Magno','Romeu','Estevio','Junior','Gerson','Lituca','Cravão','Jaco','Gusto','Setembrino','Susu','Vitelinho','Juninho','Murici','Joelinton','Beto','Aloisio','Evandro','Didinho','Alex','Jair','Preto','Otavio','Dudu','Junior','Zelito','Zeca','Thiago','Diego','Givanildo','Roque','Sonny','Sidney','Matheus'],
        'surnames': ['Ponteiro','Morteiro','Hassel','Muniz','Quitaça','Maravilha','Amazonia','Xareca','Silva','Mineiro','Paulista','Luso','Gaucho','Baiano','Chupeta','Nazario','Aveiro','Santana','Jesus','Junior','Galindro','Souza','Nitro','Melo','Ronaldo','Pato','Ribas']
    },
    'Argentina': {
        'probability': 0.036215,
        'skin_color': [(1, 0.90), (3, 0.10)],  # 90% skin=1, 10% skin=3
        'first_names': ['Mario','Fede','Juliano','Fernando','Alberto','Javier','Martin','Rocco','Queiroga','Juasmin','Nendez','Iturra','Salesio','Sergio','Enzo','Nicolas','Franco','Ezequiel','Alejandro','Facundo','Lisandro','Esteban','Agustin','Maxi','Sebastian','Osvaldo','Giovanni','Hector','Diego','Rodrigo','Pablo','Hernando'],
        'surnames': ['Ximenes','Cortaluca','Cerdo','Pavillán','Chicorito','Palermo','Cruz','Almeyda','Varela','Valdano','Diaz','Messi','Bautista','Simeone','Lopez','Sotto','Correa','Rulli','Farias','Mareque','Toro','Pavon','Di Santi','Gomez']
    },
    'Spain': {
        'probability': 0.026594,
        'skin_color': [(1, 0.90), (3, 0.10)],  # 90% skin=1, 10% skin=3
        'first_names': ['Rócio','Dorian','Arzo','Alphonso','Sergi','Roberto','Iker','Andres','Xavier','Gerardo','Kiko','Carles','Juanito','Alberto','Alfonso','Ituxarra','Goskitz','Arturo','Sibutche','Michel','Marc','Julen','Ruben','Daniel','Lobo','Pep','Santi','Raul','Pico','Ferran','Nacho'],
        'surnames': ['Makez','Hernandez','Cócio','Chávez','Wozkitz','Ruggeri','Banderas','Hernandez','Gonzalez','de la Costa','Laporte','del Campo','Garcia','Navarro','Salazar','Gusto','Peralta','Rico','Pinjuan','Fernandez','Lopetegui','Enrique','del Rio','Begiristáin','Camacho','de la Buena']
    },
    'France': {
        'probability': 0.021794,
        'skin_color': [(1, 0.75), (3, 0.15), (4, 0.10)],  # 75% skin=1, 15% skin=3, 10% skin=4
            'first_names': ['Dominic','Gil','Guy','Emmanuel','Cyprien','Antoine','Robert','Olivier','Marcel','Didier','Claude','Le Savoir','Lemarchall','Julian','Sosy','Zargoiux','Molinneux','Fabien','Pierre','Raymond','Raphael','Aurelie','Edouard','Kyllian','Jeremy','Dominique','Florent','Bernard','Samir','Andreu','Djibril'],
            'surnames': ['Morel','Chaute','Joubert','Calvaire','Carré','Lacroix','Santana','Le Vasseur','Guillotine','Benoit','Saint Laurent','Chanel','Givenchy','Gaultier','Papisse','Candela','Papin','Patrice','Fontaine','Remy','Pavard','Ratatouille','Gusteau','Jacquin','Bonaparte','Dior','Chalamet','Brouyche','Dujardin','Sauvignon','Capucine','Labonne','La Croix','Kebechet','Mauve','Xerouzhi','Wazebechet','Rogier']
    },
    'England': {
        'probability': 0.016983,
        'skin_color': [(1, 0.80), (3, 0.15), (4, 0.05)],  # 80% skin=1, 15% skin=3, 5% skin=4
        'first_names': ['Frank','Demp','Cole','Kyre','Mason','Erick','Shawn','Pierce','Jimmy','Jamie','Wayne','Frank','Joseph','Edward','Harry','Phil','Gary','Kyle','Jordan','Peter','Keith','Clint','Mac','Christopher','Souls','Drown','James','Joe','Andrew','Henry','David','Richard','William','Charles','Jude'],
        'surnames': ['Passington','Harding','Eastbrook','Hog','Buffer','Williams','MacCarrick','Beckham','Adams','Cole','McCoy','Xavier','Pearce','Baines','Holmes','Wallace','Potter','Weasley','Baggins','Reigns','Kross','McDonagh','Flair','Owen','Charlton','Stark','King']
    },
    'Germany': {
        'probability': 0.016983,
        'skin_color': [(1, 0.90), (3, 0.10)],  # 90% skin=1, 10% skin=3
        'first_names': ['Hans','Joh','Gentz','Wills','Bolt','Krimzom','Philip','Franz','Adolf','Bastian','Jurgen','Fritz','Andrea','Felix','Thomas','Karl','Bernard','Stefan','Marcus','Mario','Max','Robin','Deniz','Julian','Heinz','Lukas','Gerb','Leon','Jurgenspittzer','Kirstenwolff','Gutten','Daven','Nistchze','Neuville','Soth','Dutreisch','Kloden','Drikens','Muff','Der Gutz'],
        'surnames': ['Bach','Lonnemeier','Bors','Dehl','Kehl','Brandt','Meyer','Muller','Nicholas','Schumacher','Schawrz','Einstein','Kant','Marx','Kaiser','Panzer','von Bismarck','Fassbender','Otto','Kruger','Rudof','Hoss','Goring','Effenberg','Himmler','Schneider']
    },
    'Italy': {
        'probability': 0.016983,
        'skin_color': [(1, 0.90), (3, 0.10)],  # 90% skin=1, 10% skin=3
        'first_names': ['Rodolfo','Aimo','Angelo','Pier','Maggi','Vito','Carlo','Fredo','Salvatore','Bruno','Amerigo','Tomaso','Francesco','Giorgino','Fabrizio','Benito','Gianluigi','Gianluca','Giuseppe','Leonardo','Lorentino','Moscardo','Sauvino','Antonio','Popo','Filippo','Gennaro','Luigi','Vincenzo','Riccardo'],
        'surnames': ['Maggiolli','Florenzi','Anselmi','Pretchi','Siciglia','Vannata','Corleone','Rossi','Gentile','Zola','Dimarco','Della Rocca','Bastoni','Negroni','Fetuccini','Rossini','Clemenza','Fanucci','del Neri','Constanzini','Lamberto','Berlusconi','da Vinci','Baggio','Pavarotti','Bucetti']
    },
    'Portugal': {
        'probability': 0.016983,
        'skin_color': [(1, 0.70), (3, 0.25), (4, 0.05)],  # 70% skin=1, 25% skin=3, 5% skin=4
        'first_names': ['Manuel','José','Alfredo','Luis','Pedro','Carlos','Márcio','Mário','Zéquinha','Toni','Pedro','Mário','Rubén','André','Ricardo','Leandro','Diogo','Tarcisio','Filomeno','Tiago','Bruno','Carlos','Josué','Nélson','Aníbal','Pedrinho','Fábio','Quim','Leonardo','Jota','Ricardinho','Vasco','Joca','Santiago','David','Nuno','Diogo','Cristiano'],
        'surnames': ['Silvares','Ponte Sor','Regueiras','Barroso','Vilares','Neto','Silva','Galindro','Da Rocha','Rochinha','Amaral','Felix','Capelao','Quaresma','Carvalho','Leitinho','Fernandes','Da Costa','Abreu','Seabra','Cardoso','Ferreirinha','Varandas','Martins','Gastão','Guedes']
    },
    'Netherlands': {
        'probability': 0.016983,
        'skin_color': [(1, 0.80), (3, 0.15), (4, 0.05)],  # 80% skin=1, 15% skin=3, 5% skin=4
        'first_names': ['Gor','Sigh','Dan','Laak','Hij','Jan','Jaap','Frank','Memphis','Virgil','Clarence','Wesley','Edwin','Dennis','Ruud','Luuk','Justin','Kevin','Jetro','Maarten','Ronald','Robin','Arjen','Dick','Roy','Fehn','Drost','Van de'],
        'surnames': ['Soussij','Invlaar','Wirz','DeMelo','Hooveer','Pasveer','van der Vaart','Kluivert','De Jong','Van Bommel','de Boer','Janssen','van de Beek','de Vrijens','van Gallen','Basten','Berg','Bosman','Rijens','Schaar','Cruijff','Wetterman','Dumfries','Stan','de Ligt']
    },
    'Belgium': {
        'probability': 0.016983,
        'skin_color': [(1, 0.75), (3, 0.15), (4, 0.10)],  # 75% skin=1, 15% skin=3, 10% skin=4
        'first_names': ['Porchetain','Ambion','Vuuk','Vincent','Thibaut','Wilfried','Fernand','Dries','Divock','Timothy','Jeremy','Emile','Silvio','Matz','Simon','Jean','Claude','Sven','Maxim','Filip','Arthur','Charles','Luc','Boir','Chemo','Bizimana'],
        'surnames': ['Ceulaer','De Ruuk','Koeelers','Le Ceire','Pan','den Borr','Meunier','Preud','Yannick','Gillet','Praet','Sels','van Prist','Chalomet','van Zeno','Cuyper','Wilde','Brunyet','Castagne','Weiss','Goose','Bruyne','Ruus','Emmers','Boyata']
    },
    'Croatia': {
        'probability': 0.016983,
        'skin_color': [(1, 0.95), (3, 0.05)],  # 95% skin=1, 5% skin=3
        'first_names': ['Dalibor','Vimior','Cruko','Lorko','Dado','Andres','Sinisa','Luka','Ivan','Dejan','Andrej','Marko','Ante','Josko','Igor','Mila','Nikola','Karl','Marsej','Dalibor','Davor'],
        'surnames': ['Suker','Vida','Demko','Kolasinac','Prosinecki','Stanic','Vidalic','Benkovic','Subasic','Kovacic','Petric','Vlasic','Pilitic','Milic','Bilic','Pjaca','Zivjaca','Badelj']
    },
    'Serbia': {
        'probability': 0.016983,
        'skin_color': [(1, 0.95), (3, 0.05)],  # 95% skin=1, 5% skin=3
        'first_names': ['Dalibor','Vimior','Cruko','Lorko','Dado','Andres','Sinisa','Milic','Srdjan','Milos','Ludovic','Nikola','Lukic','Savo','Alek','Lazar','Josevic','Kristian','Mikokola','Palik','Salim'],
        'surnames': ['Markovic','Jokinovic','Jeker','Melovic','Danicelic','Chakic','Slagalo','Jovanovic','Milosevic','Ibisevic','Drulovic','Rochovic','Milosevic','Popovic','Krenkov','Dukic']
    },
    'Poland': {
        'probability': 0.016983,
        'skin_color': [(1, 0.95), (3, 0.05)],  # 95% skin=1, 5% skin=3
        'first_names': ['Henryk','Pawel','Lukas','Tomasz','Jakub','Marek','Jerzy','Gregor','Euzebiusz','Karol','Krystowik','Schzlyonyk','Garzcsinktz'],
        'surnames': ['Milik','Piatek','Zalewski','Dudek','Zielinski','Rybus','Panterizki','Razça','Boniek','Caganarek']
    },
    'Ukraine': {
        'probability': 0.016983,
        'skin_color': [(1, 0.95), (3, 0.05)],  # 95% skin=1, 5% skin=3
        'first_names': ['Valdomir','Andrey','Artem','Dmytro','Viktor','Vitaliy','Mykola','Roman','Yuri','Vasyl','Artemi','Ivan','Alexander','Yevgeny','Golovka'],
        'surnames': ['Stepanenko','Rebrov','Maluchencko','Milesvkiy','Mykolenko','Gansov','Litochencko','Koval','Zielinski','Malyshev']
    },
    'Russia': {
        'probability': 0.016983,
        'skin_color': [(1, 0.90), (2, 0.05), (3, 0.05)],  # 90% skin=1, 5% skin=2, 5% skin=3
        'first_names': ['Lev','Igor','Vladimir','Yuri','Sergey','Dmitri','Denis','Roman','Aleksei','Marat','Ivan','Denis','Alieksey','Fedor'],
        'surnames': ['Alenitchev','Stallin','Romanoff','Bereshakov','Kutin','Maloev','Sychevchenko','Joorgev','Dubrovski','Zasputin']
    },
    'Turkey': {
        'probability': 0.016983,
        'skin_color': [(1, 0.20), (2, 0.30), (3, 0.50)],  # 20% skin=1, 30% skin=2, 50% skin=3
        'first_names': ['Hakan','Arda','Hasan','Ozan','Volkan','Fatih','Hamit','Kazim','Sabri','Gokhan','Zorkan','Okan','Zermit','Jukhan','Ozzimen'],
        'surnames': ['Coçalhoglu','Terim','Tosun','Cetin','Tuncay','Sukur','Yilmaz','Demiral','Guler','Betozoglu']
    },
    'Morocco': {
        'probability': 0.016983,
        'skin_color': [(2, 0.20), (3, 0.60), (4, 0.20)],  # 20% skin=2, 60% skin=3, 20% skin=4
        'first_names': ['Hakim','Nassir','Youssef','Brahim','Omar','Yassine','Younes','Adel','Medhi','Marrouane','Zalladin','Mokhtari','Al','Rabat'],
        'surnames': ['Belhanda','Rabat','Chafik','Moufassa','Kabella','Nazer','Chamakh','Zairi','Naybet','Boussaf']
    },
    'Algeria': {
        'probability': 0.016983,
        'skin_color': [(2, 0.15), (3, 0.70), (4, 0.15)],  # 15% skin=2, 70% skin=3, 15% skin=4
        'first_names': ['Yacine','Nabil','Rabah','Islam','Mehdi','Zinedine','Oussama','Youcef','Ismael','Karim','Cahri','Souleimahne','Al-Ranjit'],
        'surnames': ['Madjer','Assad','Kadir','Soudani','Ghilas','Saifi','Djebour','Saiid','Brahimi','Boudaoui']
    },
    'Senegal': {
        'probability': 0.016983,
        'skin_color': [(3, 0.20), (4, 0.80)],  # 20% skin=3, 80% skin=4
        'first_names': ['Lamine','Pape','Papiss','Issa','Idrissa','Saido','Moussa','Demba','Salif','Fode','Bobo','Kalulu','Zohne','Guitane'],
        'surnames': ['Sylva','Diop','Ndiaye','Sow','Gueye','Babacar','Diao','Diarra','Gomis','Ba']
    },
    'Nigeria': {
        'probability': 0.016983,
        'skin_color': [(3, 0.15), (4, 0.85)],  # 15% skin=3, 85% skin=4
        'first_names': ['Obi','Joseph','Kalu','Ola','Sanusi','Haruna','Julius','Ideye','Obafemi','Sam','Emmanuel','Martial','Orunfinjana','Horogulushe','Tembo'],
        'surnames': ['Zaidu','Agu','Kanu','Taribo','Babayaro','Omeru','Akwue','Obafemi','Aina','Owusuwelele']
    },
    'Ghana': {
        'probability': 0.016983,
        'skin_color': [(3, 0.20), (4, 0.80)],  # 20% skin=3, 80% skin=4
        'first_names': ['Samuel','Thomas','Jeffrey','Tony','Michael','Asamoah','Jordan','Raphael','Christian','Eric','Manfred','Jules','Erique'],
        'surnames': ['Diouf','Atsu','Boateng','Prince','Addo','Kudus','Mensah','Fatu','Gyan','Sunday','Essien']
    },
    'Cameroon': {
        'probability': 0.016983,
        'skin_color': [(3, 0.25), (4, 0.75)],  # 25% skin=3, 75% skin=4
        'first_names': ['Roger','Samuel','Lauren','Lucien','Stephane','Joel','Vincent','Benjamim','Fabrice','Pierre','Columbu','Sanoh','Le-Merrienne'],
        'surnames': ['Mbeuna','Kongolo','Ekotto','Milla','Song','Bilong','Nego','Onana','Matip','Preto o']
    },
    'Egypt': {
        'probability': 0.016983,
        'skin_color': [(2, 0.30), (3, 0.70)],  # 30% skin=2, 70% skin=3
        'first_names': ['Mohamed','Ahmed','Hossan','Yasser','Ismail','Mustafa','Omar','Saleh','Mokthar','Ibrahim','Yamine','Ecleh','Hassan'],
        'surnames': ['Marmoush','Ghaly','Imoteph','Zidan','Elneny','Faisel','Nahmed','Saleht','Rafaat','Zamal']
    },
    'Tunisia': {
        'probability': 0.012173,
        'skin_color': [(2, 0.25), (3, 0.75)],  # 25% skin=2, 75% skin=3
        'first_names': ['Youssef','Hatem','Riad','Nabil','Oussef','Karim','Nizar','Ali','Sofie','Ziad','Zorbon','Nikia','Gille'],
        'surnames': ['Trabelsi','Jaziri','Khazim','Quedir','Nejib','Houssem','Slim','Meriah','Belaid','Achouri']
    },
    'South Africa': {
        'probability': 0.012173,
        'skin_color': [(1, 0.10), (3, 0.20), (4, 0.70)],  # 10% skin=1, 20% skin=3, 70% skin=4
        'first_names': ['Bennedict','Quinton','Phil','Aaron','John','Andre','Steven','Eric','David','Manuel','Kerwit','Durmu','Vincent','Weld','Hansi'],
        'surnames': ['Fortune','McCarthy','Zuma','Mokoena','Mandela','Joseph','Pistorious','Kulele','Tsahbalala','Zwane']
    },
    'Japan': {
        'probability': 0.012173,
        'skin_color': [(2, 0.90), (3, 0.10)],  # 90% skin=2, 10% skin=3
        'first_names': ['Keisuke','Hidetoshi','Sakura','Ryo','Genzo','Ozora','Akira','Hikaro', 'Sheinsuke','Takeshi','Suneo','Kenzo','Koji'],
        'surnames': ['Hyuga','Wakabayashi','Misaki','Tsubasa','Inamoto','Nakamura','Nakazawa','Gohan','Nakata','Fujimoto']
    },
    'South Korea': {
        'probability': 0.012173,
        'skin_color': [(2, 0.90), (3, 0.10)],  # 90% skin=2, 10% skin=3
        'first_names': ['Son','Sung','Young','Lee','Heung','Ping','Pee','Jing','Din','Sun','Hoon','Soon','Geung'],
        'surnames': ['Ming','Park','Ling','Chun','Gun','Son','Young','Ben','Choy','Mill']
    },
    'China': {
        'probability': 0.012173,
        'skin_color': [(2, 0.95), (3, 0.05)],  # 95% skin=2, 5% skin=3
        'first_names': ['Wu', 'Zhang', 'Li', 'Wang', 'Chen', 'Liu', 'Yang', 'Huang', 'Zhao', 'Zhou', 'An', 'Bao', 'Dong', 'En', 'Feng', 'Gang', 'Hao', 'In', 'Jian'],
        'surnames': ['Wang', 'Li', 'Zhang', 'Liu', 'Chen', 'Yang', 'Huang', 'Zhao', 'Wu', 'Zhou']
    },
    'Australia': {
        'probability': 0.012173,
        'skin_color': [(1, 0.70), (2, 0.20), (3, 0.10)],  # 70% skin=1, 20% skin=2, 10% skin=3
        'first_names': ['John','Tim', 'Robert','Hugh','Lauren','Joe','Aaron','Harry','Craig','Mark','Sam','Mark','Daniel','Marshment'],
        'surnames': ['Cahill','Ingles','Viduka','Morten','Kennedy','Foster','Rodwell','Winchester','Jackman','Kerr']
    },
    'Mexico': {
        'probability': 0.016983,
        'skin_color': [(1, 0.20), (3, 0.60), (4, 0.20)],  # 20% skin=1, 60% skin=3, 20% skin=4
        'first_names': ['Javier','Roberto','Rafael','Alejandro','Jorge','Kinkin','Luiz','Ramon','Hector','Gonzalo','Rivero','Juanito','Cabezo','Rogério','Lo Chito','Lionel','Hernando','Vidal'],
        'surnames': ['Hernandez','Gutierrez','Banderas','Martinez','Fonseca','Herrera','Sanchez','Marquez','de la Vega']
    },
    'Colombia': {
        'probability': 0.016983,
        'skin_color': [(1, 0.15), (3, 0.65), (4, 0.20)],  # 15% skin=1, 65% skin=3, 20% skin=4
        'first_names': ['Ricco','Tisco','Torpedero','Tolo','Hernan', 'Faustino','Carlitos','Radamel','Andres','Rubio','Jackson','Manelito','Panzo'],
        'surnames': ['Martinez','Diaz','Escobar','Yepes','Leon','Ortiz','Rincon','Eusebio','Rios','Rodriguez']
    },
    'Chile': {
        'probability': 0.012173,
        'skin_color': [(1, 0.30), (3, 0.60), (4, 0.10)],  # 30% skin=1, 60% skin=3, 10% skin=4
        'first_names': ['Carlos','Juan','Jose','Miguel','Albino','Nicolás','Arturo', 'Alexis', 'Eduardo','Claudio', 'Jorge', 'Mauricio', 'Matías', 'Cassandro', 'Diego'],
        'surnames': ['González', 'Muñoz', 'Rojas', 'Díaz', 'Pérez', 'Soto', 'Silva', 'Morales', 'Flores', 'Castro']
    },
    'Uruguay': {
        'probability': 0.012173,
        'skin_color': [(1, 0.85), (3, 0.15)],  # 85% skin=1, 15% skin=3
        'first_names': ['Fede','Antonio','Silvio','Diego','Luis', 'Edinson', 'Diego', 'Maxi', 'Álvaro', 'Sebastián', 'Romero','Armando','Miguel','Gonzalo'],
        'surnames': ['Rodríguez', 'González', 'Silva', 'Pastore', 'García', 'Formentera', 'Ruiz', 'Martínez', 'Díaz', 'Hernández']
    },
    'Paraguay': {
        'probability': 0.012173,
        'skin_color': [(1, 0.25), (3, 0.65), (4, 0.10)],  # 25% skin=1, 65% skin=3, 10% skin=4
        'first_names': ['Roque', 'Nelson', 'Oscar', 'Cristian', 'Edgar', 'Julio', 'Dario', 'Lucas', 'Antonio', 'Carlos','Rocio','Ponzio','Nel'],
        'surnames': ['Cardozo', 'González', 'Silva', 'Pérez', 'Santa Cruz', 'Ballasteros', 'López', 'Martínez', 'Díaz', 'Hernández']
    },
    'Peru': {
        'probability': 0.012173,
        'skin_color': [(1, 0.20), (2, 0.10), (3, 0.60), (4, 0.10)],  # 20% skin=1, 10% skin=2, 60% skin=3, 10% skin=4
        'first_names': ['Paolo', 'Jefferson', 'André', 'Christian', 'Yoshimar', 'Renato', 'Luis', 'Carlos', 'Miguel', 'Raúl','Damian','Lamino','Laro','Rimondes'],
        'surnames': ['Rodríguez', 'González', 'Silva', 'Bakero', 'García', 'Fernández', 'López', 'Martínez', 'Díaz', 'Hernández']
    },
    'Ecuador': {
        'probability': 0.012173,
        'skin_color': [(1, 0.15), (3, 0.70), (4, 0.15)],  # 15% skin=1, 70% skin=3, 15% skin=4
        'first_names': ['Antonio', 'Enner', 'Felipe', 'Michael', 'Christian', 'Renato', 'Carlos', 'Gabriel', 'Walter', 'Benito','Engelmann'],
        'surnames': ['Rodríguez', 'González', 'Silva', 'Cabra', 'García', 'Fernández', 'Vasquez', 'Martínez', 'Díaz', 'Hernández']
    },
    'Venezuela': {
        'probability': 0.012173,
        'skin_color': [(1, 0.25), (3, 0.60), (4, 0.15)],  # 25% skin=1, 60% skin=3, 15% skin=4
        'first_names': ['Salomón', 'Rómulo', 'Fernando', 'Carlos', 'Roberto', 'José', 'Camilo', 'Eduardo', 'Gabriel', 'Héctor','Portillez','Navez','De la Playa'],
        'surnames': ['Rodríguez', 'González', 'Lucho', 'Pérez', 'García', 'Buenavista', 'Libre', 'Martínez', 'Díaz', 'Hernández']
    },
    'Canada': {
        'probability': 0.012173,
        'skin_color': [(1, 0.70), (2, 0.15), (3, 0.10), (4, 0.05)],  # 70% skin=1, 15% skin=2, 10% skin=3, 5% skin=4
        'first_names': ['Mitch', 'Alphonso', 'Jonathan','Scott', 'Samuel', 'Mark', 'Russell', 'Blake', 'Declan', 'Ethan','Mikey','Macklin','Connor','Brandon','Jake','Saint'],
        'surnames': ['Mark', 'Thomas','Rodrigo','Edgar','Philip','Kirr','Dacourt','Falurein','Gustaff','Moore']
    },
    
    # Additional countries from database
    'Austria': {
        'probability': 0.012173,
        'skin_color': [(1, 0.95), (3, 0.05)],  # 95% skin=1, 5% skin=3
        'first_names': ['Adolf','Jurgen','Heinrich','Michael','George','Manuel','Lukas','Angel','Markus','Julian'],
        'surnames': ['Müller', 'Schmidt', 'Schneider', 'Fischer', 'Weber', 'Meyer', 'Muschaft', 'Becker', 'Schulz', 'Goring', 'Eisenwoer','Ziegler']
    },
    'Switzerland': {
        'probability': 0.012173,
        'skin_color': [(1, 0.85), (3, 0.10), (4, 0.05)],  # 85% skin=1, 10% skin=3, 5% skin=4
        'first_names': ['Lionel','Granit','Henrique','Michel','Jean','Diego','Lukas','Patrick','Markus','Julles','Lohren','Karim','Volz','Gennaro'],
        'surnames': ['Blanc', 'Schmidt', 'Dubois', 'Robertstein', 'Frei', 'Meyer', 'Raffaello', 'Becker', 'Schulz', 'Perrin', 'Silva','Ziegler']
    },
    'Sweden': {
        'probability': 0.012173,
        'skin_color': [(1, 0.90), (3, 0.10)],  # 90% skin=1, 10% skin=3
        'first_names': ['Viktor','Henrik','Andreas','Olaf','Merk','Isak','Manuel','Fredrik','Joseph','Max','William','Alexander','Alfred'],
        'surnames': ['Marksson', 'Larsson', 'Svensson', 'Karlsson', 'Eriksson', 'Junstorm', 'Hallstrom', 'Rottenberg', 'Storm', 'Vannaheim', 'Andersson','Hiccup']
    },
    'Norway': {
        'probability': 0.012173,
        'skin_color': [(1, 0.95), (3, 0.05)],  # 95% skin=1, 5% skin=3
        'first_names': ['Viktor','Henrik','John','Olef','Erling','Alexander','Gustav','Fredrik','Puntus','Max','Tore','Perth','Oslo'],
        'surnames': ['Markssen', 'Larssen', 'Olsen', 'Vaalaand', 'Erikssen', 'Braut', 'Pedersen', 'Berg', 'Dahl', 'Haaland', 'Andersen','Estoic']
    },
    'Denmark': {
        'probability': 0.012173,
        'skin_color': [(1, 0.90), (3, 0.10)],  # 90% skin=1, 10% skin=3
        'first_names': ['Viktor','Henrik','Christian','Rasmus','Peter','Hugh','Greg','Fredrik','Leonel','Dedrik','Morten','Morgan','Brian','Samuel'],
        'surnames': ['Eriksen', 'Larsen', 'Kjaer', 'Froholt', 'Huljmand', 'Tommasson', 'Jorgensen', 'Kasper', 'Hojlmund', 'Christensen', 'Andersen','Sorensen']
    },
    'Finland': {
        'probability': 0.012173,
        'skin_color': [(1, 0.95), (3, 0.05)],  # 95% skin=1, 5% skin=3
        'first_names': ['Viktor','Henrik','Jared','Olav','Peter','Mika','Jasper','Fredrik','Thor','Lukas','Lauri','Mika','Christopher'],
        'surnames': ['Heikinen', 'Makela', 'Litmanem', 'Hyppia', 'Moller', 'Trosten', 'Niemi', 'Koivist', 'Virtanen', 'Iltamen', 'Jarvinen','Sulkvist']
    },
    'Iceland': {
        'probability': 0.012173,
        'skin_color': [(1, 0.95), (3, 0.05)],  # 95% skin=1, 5% skin=3
        'first_names': ['Viktor','Henrik','Gylfi','Bjorn','Herman','Johan','Jasper','Fredrik','Alfred','Lukas','Fylkir','Lyomir','Gryk'],
        'surnames': ['Jónsson', 'Sigurðsson', 'Guðmundsson', 'Gunnarsson', 'Ólafsson', 'Einarsson', 'Kristjánsson', 'Magnússon', 'Stefánsson', 'Jóhannesson', 'Björnsson','Loki']
    },
    'Ireland': {
        'probability': 0.012173,
        'skin_color': [(1, 0.95), (3, 0.05)],  # 95% skin=1, 5% skin=3
        'first_names': ['Henry','Josh','George','Mark','Alfred','Bob','Gareth','Louis','Keith','Steven','Roy','Olmen'],
        'surnames': ['Murphy', 'Kelly', 'Sullivan', 'Guiness', 'Smith', 'O\'Brien',  'O\'Connor', 'O\'Neill', 'O\'Reilly' 'Quinn','O\'Callaghan', 'O\'Shea', 'Dunne', 'Fitzgerald']
    },
    'Scotland': {
        'probability': 0.007362,
        'skin_color': [(1, 0.95), (3, 0.05)],  # 95% skin=1, 5% skin=3
        'first_names': ['Henry','Josh','George','Mark','Alfred','Bob','Gareth','Louis','Keith','Steven','Ballantines','Logan'],
        'surnames': ['Smith', 'MacGregor','Ferguson','MacDonald','McLean','Stewart','Robertson','Murray','Graham','Armstrong','Douglas']
    },
    'Wales': {
        'probability': 0.007362,
        'skin_color': [(1, 0.95), (3, 0.05)],  # 95% skin=1, 5% skin=3
        'first_names': ['Henry','Josh','George','Mark','Alfred','Bob','Gareth','Louis','Keith','Steven','Logan'],
        'surnames': ['Williams','Evans','Hughes','Pritchard','Powell','Bale','Griffiths','Lancelot','Percival','Price']
    },
    'Northern Ireland': {
        'probability': 0.007362,
        'skin_color': [(1, 0.95), (3, 0.05)],  # 95% skin=1, 5% skin=3
        'first_names': ['Henry','Josh','George','Mark','Alfred','Bob','Gareth','Louis','Keith','Steven','Bono'],
        'surnames': ['Murphy', 'Kelly', 'Sullivan', 'Guiness', 'Smith', 'O\'Brien',  'O\'Connor', 'O\'Neill', 'O\'Reilly' 'Quinn','O\'Callaghan', 'O\'Shea', 'Dunne', 'Fitzgerald']
    },
    
    # Additional missing countries from database
    'Albania': {
        'probability': 0.004962,
        'skin_color': [(1, 0.90), (3, 0.10)],  # 90% skin=1, 10% skin=3
        'first_names': ['Krish','Eduard', 'Xerdan', 'Granit', 'Endrit', 'Kavor', 'Lorik', 'Luka', 'Semir', 'Jeton', 'Petro'],
        'surnames': ['Abazaj', 'Mitaj', 'Berisha', 'Gashi', 'Kadriu', 'Euzabaj', 'Pajaziti', 'Rexhepi', 'Durmisi', 'Cana']
    },
    'Angola': {
        'probability': 0.004962,
        'skin_color': [(3, 0.20), (4, 0.80)],  # 20% skin=3, 80% skin=4
        'first_names': ['Lumueno','Kiko','Jorginho', 'Bruno', 'Carlinhos', 'Domingos', 'Manel', 'Nandinho', 'Gilberto', 'Rafa', 'Rogério', 'João','Gervásio'],
        'surnames': ['Santos', 'Fernandes', 'Teta', 'Costa', 'Ferradura', 'Cacimbo', 'Rodrigues', 'Ferreira', 'Vemba', 'Gomes']
    },
    'Armenia': {
        'probability': 0.004962,
        'skin_color': [(1, 0.85), (2, 0.10), (3, 0.05)],  # 85% skin=1, 10% skin=2, 5% skin=3
        'first_names': ['Yermen','Islam','Arman', 'David', 'Gor', 'Hayk', 'Karen', 'Levon', 'Mher', 'Narek', 'Ruben', 'Sargis'],
        'surnames': ['Grigoryan', 'Khachatryan', 'Harutyunyan', 'Sargsyan', 'Vardanyan', 'Petrosyan', 'Mkhitaryan', 'Ghazaryan', 'Chyan', 'Avetisyan']
    },
    'Belarus': {
        'probability': 0.004962,
        'skin_color': [(1, 0.95), (3, 0.05)],  # 95% skin=1, 5% skin=3
        'first_names': ['Boronov','Aliaksandr', 'Dzmitry', 'Ihar', 'Kanstantsin', 'Maksim', 'Pavel', 'Siarhei', 'Uladzimir', 'Vitali', 'Yury'],
        'surnames': ['Ivanov', 'Petrov', 'Sidorov', 'Kozlov', 'Morozov', 'Volkov', 'Alekseev', 'Lebedev', 'Semenov', 'Egorov']
    },
    'Benin': {
        'probability': 0.004962,
        'skin_color': [(3, 0.25), (4, 0.75)],  # 25% skin=3, 75% skin=4
        'first_names': ['Abel', 'Benoît', 'Célestin', 'Désiré', 'Emmanuel', 'Félix', 'Gabriel', 'Henri', 'Ignace', 'Jean'],
        'surnames': ['Adjanohoun', 'Agbessi', 'Akplogan', 'Bokonon', 'Dossou', 'Gbaguidi', 'Houngbédji', 'Kouassi', 'Migan', 'Tchibozo']
    },
    'Bolivia': {
        'probability': 0.004962,
        'skin_color': [(1, 0.20), (2, 0.10), (3, 0.60), (4, 0.10)],  # 20% skin=1, 10% skin=2, 60% skin=3, 10% skin=4
        'first_names': ['Carlos', 'Diego', 'Eduardo', 'Fernando', 'Gabriel', 'Hugo', 'Iván', 'Jorge', 'Luis', 'Miguel'],
        'surnames': ['García', 'Rodríguez', 'González', 'Martínez', 'López', 'Pérez', 'Sánchez', 'Fernández', 'Silva', 'Díaz']
    },
    'Bosnia and Herzegovina': {
        'probability': 0.004962,
        'skin_color': [(1, 0.90), (3, 0.10)],  # 90% skin=1, 10% skin=3
        'first_names': ['Adnan', 'Benjamin', 'Srdjan', 'Emir', 'Faruk', 'Goran', 'Haris', 'Ivan', 'Jasmin', 'Kenan'],
        'surnames': ['Kovačević', 'Petrović', 'Nikolić', 'Marković', 'Đorđević', 'Stojanović', 'Ilić', 'Stanković', 'Pavlović', 'Milošević']
    },
    'Bulgaria': {
        'probability': 0.004962,
        'skin_color': [(1, 0.90), (3, 0.10)],  # 90% skin=1, 10% skin=3
        'first_names': ['Aleksandar', 'Boris', 'Dimitar', 'Emil', 'Georgi', 'Hristo', 'Ivan', 'Jordan', 'Krasimir', 'Lyubomir'],
        'surnames': ['Ivanov', 'Petrov', 'Georgiev', 'Dimitrov', 'Stoyanov', 'Nikolov', 'Todorov', 'Hristov', 'Atanasov', 'Vasilev']
    },
    'Burkina Faso': {
        'probability': 0.004962,
        'skin_color': [(3, 0.20), (4, 0.80)],  # 20% skin=3, 80% skin=4
        'first_names': ['Abdoulaye', 'Boureima', 'Cheick', 'Daouda', 'Emmanuel', 'François', 'Gérard', 'Hervé', 'Issouf', 'Jean'],
        'surnames': ['Ouédraogo', 'Traoré', 'Sawadogo', 'Kaboré', 'Zongo', 'Ouattara', 'Bikienga', 'Boukary', 'Compaoré', 'Dabiré']
    },
    'Cape Verde': {
        'probability': 0.004962,
        'skin_color': [(3, 0.30), (4, 0.70)],  # 30% skin=3, 70% skin=4
        'first_names': ['Adilson', 'Bruno', 'Litos', 'Domingos', 'Eduardo', 'Quinzinho', 'Gilberto', 'Chiquinho', 'Manecas', 'João'],
        'surnames': ['Santos', 'Varela', 'Patrao', 'Costa', 'Pereira', 'Mota', 'Rodrigues', 'Luvinha', 'Alves', 'Gomes']
    },
    'Congo': {
        'probability': 0.004962,
        'skin_color': [(3, 0.20), (4, 0.80)],  # 20% skin=3, 80% skin=4
        'first_names': ['Alain', 'Boris', 'Christian', 'Daniel', 'Emmanuel', 'François', 'Gabriel', 'Henri', 'Ivan', 'Jean'],
        'surnames': ['Mabiala', 'Nkounkou', 'Moukila', 'Bouanga', 'Makengo', 'Ndinga', 'Mabika', 'Bouanga', 'Moukila', 'Nkounkou']
    },
    'Costa Rica': {
        'probability': 0.004962,
        'skin_color': [(1, 0.30), (3, 0.60), (4, 0.10)],  # 30% skin=1, 60% skin=3, 10% skin=4
        'first_names': ['Alejandro', 'Carlos', 'Diego', 'Eduardo', 'Fernando', 'Gabriel', 'Héctor', 'Iván', 'Jorge', 'Luis'],
        'surnames': ['Rodríguez', 'González', 'Romero', 'Martínez', 'López', 'Pérez', 'Sánchez', 'Fernández', 'Bolanos', 'Díaz']
    },
    'Cote d\'Ivoire': {
        'probability': 0.004962,
        'skin_color': [(3, 0.20), (4, 0.80)],  # 20% skin=3, 80% skin=4
        'first_names': ['Abou', 'Bakary', 'Cheick', 'Didier', 'Emmanuel', 'Franck', 'Gervinho', 'Hervé', 'Ibrahim', 'Jean'],
        'surnames': ['Traoré', 'Ouattara', 'Koné', 'Diabaté', 'Bamba', 'Coulibaly', 'Drogba', 'Kalou', 'Tiéné', 'Zokora']
    },
    'Cyprus': {
        'probability': 0.004962,
        'skin_color': [(1, 0.80), (2, 0.15), (3, 0.05)],  # 80% skin=1, 15% skin=2, 5% skin=3
        'first_names': ['Andreas', 'Christos', 'Demetris', 'Elias', 'Georgios', 'Haris', 'Ioannis', 'Kyriakos', 'Lefteris', 'Michalis'],
        'surnames': ['Georgiou', 'Ioannou', 'Christou', 'Michael', 'Andreou', 'Constantinou', 'Papa', 'Kyprianou', 'Charalambous', 'Demetriou']
    },
    'Czech Republic': {
        'probability': 0.004962,
        'skin_color': [(1, 0.95), (3, 0.05)],  # 95% skin=1, 5% skin=3
        'first_names': ['David', 'Jakub', 'Jan', 'Lukáš', 'Martin', 'Michal', 'Ondřej', 'Pavel', 'Tomáš', 'Václav'],
        'surnames': ['Novák', 'Svoboda', 'Novotný', 'Dvořák', 'Černý', 'Procházka', 'Kučera', 'Veselý', 'Horák', 'Němec']
    },
    'DR Congo': {
        'probability': 0.004962,
        'skin_color': [(3, 0.20), (4, 0.80)],  # 20% skin=3, 80% skin=4
        'first_names': ['Alain', 'Boris', 'Christian', 'Daniel', 'Emmanuel', 'François', 'Gabriel', 'Henri', 'Ivan', 'Jean'],
        'surnames': ['Mabiala', 'Nkounkou', 'Moukila', 'Bouanga', 'Makengo', 'Ndinga', 'Mabika', 'Bouanga', 'Moukila', 'Nkounkou']
    },
    'Equatorial Guinea': {
        'probability': 0.004962,
        'skin_color': [(3, 0.30), (4, 0.70)],  # 30% skin=3, 70% skin=4
        'first_names': ['Abel', 'Benito', 'Carlos', 'Diego', 'Emilio', 'Fernando', 'Gabriel', 'Héctor', 'Iván', 'Jorge'],
        'surnames': ['Mba', 'Nguema', 'Obiang', 'Mangue', 'Nsue', 'Bikoro', 'Sipoto', 'Mangue', 'Nsue', 'Bikoro']
    },
    'Estonia': {
        'probability': 0.004962,
        'skin_color': [(1, 0.95), (3, 0.05)],  # 95% skin=1, 5% skin=3
        'first_names': ['Andres', 'Erik', 'Jaan', 'Kristjan', 'Marten', 'Ott', 'Priit', 'Raivo', 'Siim', 'Tarmo'],
        'surnames': ['Tamm', 'Saar', 'Sepp', 'Mägi', 'Kask', 'Kukk', 'Ilves', 'Rebane', 'Karu', 'Lepik']
    },
    'Free Nationality': {
        'probability': 0.004962,
        'skin_color': [(1, 0.50), (2, 0.20), (3, 0.20), (4, 0.10)],  # Equal distribution
        'first_names': ['Alex', 'Ben', 'Chris', 'David', 'Erik', 'Frank', 'George', 'Henry', 'Ivan', 'John'],
        'surnames': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez']
    },
    'Gabon': {
        'probability': 0.003514,
        'skin_color': [(3, 0.25), (4, 0.75)],  # 25% skin=3, 75% skin=4
        'first_names': ['Alain', 'Bruno', 'Christian', 'Daniel', 'Emmanuel', 'François', 'Gabriel', 'Henri', 'Ivan', 'Jean'],
        'surnames': ['Mabiala', 'Nkounkou', 'Moukila', 'Bouanga', 'Makengo', 'Ndinga', 'Mabika', 'Bouanga', 'Moukila', 'Nkounkou']
    },
    'Gambia': {
        'probability': 0.003514,
        'skin_color': [(3, 0.20), (4, 0.80)],  # 20% skin=3, 80% skin=4
        'first_names': ['Abdoulie', 'Bakary', 'Cherno', 'Demba', 'Ebrima', 'Foday', 'Gibril', 'Habib', 'Ibrahim', 'Jallow'],
        'surnames': ['Jallow', 'Sanneh', 'Ceesay', 'Jobe', 'Manneh', 'Colley', 'Barry', 'Sarr', 'Gomez', 'Bojang']
    },
    'Georgia': {
        'probability': 0.004,
        'skin_color': [(1, 0.85), (2, 0.10), (3, 0.05)],  # 85% skin=1, 10% skin=2, 5% skin=3
        'first_names': ['Aleksandre', 'Beka', 'Davit', 'Giorgi', 'Irakli', 'Jaba', 'Kakha', 'Levan', 'Mikheil', 'Nika'],
        'surnames': ['Gelashvili', 'Kvaratskhelia', 'Mamardashvili', 'Kakabadze', 'Davitashvili', 'Kvaratskhelia', 'Mamardashvili', 'Kakabadze', 'Davitashvili', 'Gelashvili']
    },
    'Greece': {
        'probability': 0.007362,
        'skin_color': [(1, 0.90), (3, 0.10)],  # 90% skin=1, 10% skin=3
        'first_names': ['Labros','Takis','Pakis','Alexandros', 'Dimitrios', 'Georgios', 'Ioannis', 'Konstantinos', 'Josuelius', 'Nikolaos', 'Panagiotis', 'Alexios', 'Vannidis'],
        'surnames': ['Papadopoulos', 'Forneiridis', 'Karagiannis', 'Leonidas', 'Kratos', 'Nikolaidis', 'Samaris', 'Malakaidis', 'Pretorius', 'Pyssas']
    },
    'Grenada': {
        'probability': 0.003038,
        'skin_color': [(3, 0.30), (4, 0.70)],  # 30% skin=3, 70% skin=4
        'first_names': ['Anthony', 'Brian', 'Carl', 'David', 'Eric', 'Frank', 'George', 'Henry', 'Ivan', 'John'],
        'surnames': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez']
    },
    'Guadeloupe': {
        'probability': 0.003038,
        'skin_color': [(3, 0.30), (4, 0.70)],  # 30% skin=3, 70% skin=4
        'first_names': ['Alain', 'Bruno', 'Christian', 'Daniel', 'Emmanuel', 'François', 'Gabriel', 'Henri', 'Ivan', 'Jean'],
        'surnames': ['Mabiala', 'Nkounkou', 'Moukila', 'Bouanga', 'Makengo', 'Ndinga', 'Mabika', 'Bouanga', 'Moukila', 'Nkounkou']
    },
    'Guinea': {
        'probability': 0.003038,
        'skin_color': [(3, 0.20), (4, 0.80)],  # 20% skin=3, 80% skin=4
        'first_names': ['Aboubacar', 'Boubacar', 'Cheick', 'Daouda', 'Emmanuel', 'François', 'Gabriel', 'Henri', 'Ibrahim', 'Jean'],
        'surnames': ['Diallo', 'Bah', 'Camara', 'Traoré', 'Sow', 'Barry', 'Keita', 'Sylla', 'Cissé', 'Touré']
    },
    'Guinea-Bissau': {
        'probability': 0.003038,
        'skin_color': [(3, 0.30), (4, 0.70)],  # 30% skin=3, 70% skin=4
        'first_names': ['Abel', 'Bruno', 'Carlos', 'Daniel', 'Emmanuel', 'Fernando', 'Gabriel', 'Henri', 'Ivan', 'João'],
        'surnames': ['Mendes', 'Fernandes', 'Silva', 'Costa', 'Pereira', 'Oliveira', 'Rodrigues', 'Ferreira', 'Alves', 'Gomes']
    },
    'Honduras': {
        'probability': 0.003038,
        'skin_color': [(1, 0.20), (3, 0.70), (4, 0.10)],  # 20% skin=1, 70% skin=3, 10% skin=4
        'first_names': ['Alejandro', 'Carlos', 'Diego', 'Eduardo', 'Fernando', 'Gabriel', 'Héctor', 'Iván', 'Jorge', 'Luis'],
        'surnames': ['Rodríguez', 'González', 'García', 'Martínez', 'López', 'Pérez', 'Suazo', 'Fernández', 'Rondon', 'Díaz']
    },
    'Hungary': {
        'probability': 0.004962,
        'skin_color': [(1, 0.95), (3, 0.05)],  # 95% skin=1, 5% skin=3
        'first_names': ['Ádám', 'Bence', 'Dániel', 'Erik', 'Gábor', 'István', 'János', 'Krisztián', 'László', 'Márk'],
        'surnames': ['Nagy', 'Kovács', 'Tóth', 'Szabó', 'Horváth', 'Varga', 'Kiss', 'Molnár', 'Németh', 'Farkas']
    },
    'Iran': {
        'probability': 0.004962,
        'skin_color': [(2, 0.70), (3, 0.30)],  # 70% skin=2, 30% skin=3
        'first_names': ['Ali', 'Amir', 'Arash', 'Behnam', 'Dariush', 'Ehsan', 'Farhad', 'Gholam', 'Hassan', 'Iraj'],
        'surnames': ['Mohammadi', 'Rezaei', 'Hassani', 'Karimi', 'Ahmadi', 'Nouri', 'Gholami', 'Faraji', 'Ebrahimi', 'Rahmani']
    },
    'Israel': {
        'probability': 0.004,
        'skin_color': [(1, 0.60), (2, 0.30), (3, 0.10)],  # 60% skin=1, 30% skin=2, 10% skin=3
        'first_names': ['Avi', 'Ben', 'David', 'Eli', 'Gabriel', 'Haim', 'Itai', 'Jonathan', 'Kobi', 'Lior'],
        'surnames': ['Cohen', 'Levy', 'Mizrahi', 'Avraham', 'David', 'Shalom', 'Ben-David', 'Rosenberg', 'Goldberg', 'Weiss']
    },
    'Jamaica': {
        'probability': 0.004962,
        'skin_color': [(3, 0.20), (4, 0.80)],  # 20% skin=3, 80% skin=4
        'first_names': ['Anthony', 'Brian', 'Carl', 'David', 'Eric', 'Frank', 'George', 'Henry', 'Ivan', 'John'],
        'surnames': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Kingston', 'Marley']
    },
    'Kenya': {
        'probability': 0.003038,
        'skin_color': [(3, 0.15), (4, 0.85)],  # 15% skin=3, 85% skin=4
        'first_names': ['Abel', 'Brian', 'Collins', 'David', 'Eric', 'Frank', 'George', 'Henry', 'Ivan', 'John'],
        'surnames': ['Mwangi', 'Njoroge', 'Kipchoge', 'Ochieng', 'Wanjiku', 'Kamau', 'Nyong\'o', 'Odinga', 'Kenyatta', 'Moi']
    },
    'Latvia': {
        'probability': 0.004,
        'skin_color': [(1, 0.95), (3, 0.05)],  # 95% skin=1, 5% skin=3
        'first_names': ['Aivis', 'Dainis', 'Eduards', 'Guntis', 'Haralds', 'Igors', 'Juris', 'Kaspars', 'Lauris', 'Māris'],
        'surnames': ['Bērziņš', 'Kalniņš', 'Ozols', 'Liepiņš', 'Dzērve', 'Priede', 'Eglītis', 'Vītols', 'Mežs', 'Silis']
    },
    'Liberia': {
        'probability': 0.004,
        'skin_color': [(3, 0.20), (4, 0.80)],  # 20% skin=3, 80% skin=4
        'first_names': ['Abel', 'Ben', 'Carl', 'David', 'Eric', 'Frank', 'George', 'Henry', 'Ivan', 'John'],
        'surnames': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez']
    },
    'Liechtenstein': {
        'probability': 0.003038,
        'skin_color': [(1, 0.95), (3, 0.05)],  # 95% skin=1, 5% skin=3
        'first_names': ['Alexander', 'Benjamin', 'Christian', 'Daniel', 'Erik', 'Fabian', 'Gabriel', 'Hans', 'Ivan', 'Josef'],
        'surnames': ['Müller', 'Schmidt', 'Schneider', 'Fischer', 'Weber', 'Meyer', 'Wagner', 'Becker', 'Schulz', 'Hoffmann']
    },
    'Lithuania': {
        'probability': 0.003038,
        'skin_color': [(1, 0.95), (3, 0.05)],  # 95% skin=1, 5% skin=3
        'first_names': ['Arvydas', 'Darius', 'Egidijus', 'Gediminas', 'Henrikas', 'Ignas', 'Jonas', 'Kęstutis', 'Linas', 'Mindaugas'],
        'surnames': ['Kazlauskas', 'Petraitis', 'Jankauskas', 'Stankevičius', 'Vasiliauskas', 'Butkus', 'Grigas', 'Lukšys', 'Mickevičius', 'Navickas']
    },
    'Macedonia': {
        'probability': 0.003038,
        'skin_color': [(1, 0.90), (3, 0.10)],  # 90% skin=1, 10% skin=3
        'first_names': ['Aleksandar', 'Bojan', 'Darko', 'Emil', 'Filip', 'Goran', 'Hristijan', 'Ivan', 'Jovan', 'Kristijan'],
        'surnames': ['Nikolovski', 'Petrovski', 'Georgievski', 'Dimitrovski', 'Stojanovski', 'Todorovski', 'Hristovski', 'Atanasovski', 'Vasilevski', 'Ilievski']
    },
    'Mali': {
        'probability': 0.003038,
        'skin_color': [(3, 0.20), (4, 0.80)],  # 20% skin=3, 80% skin=4
        'first_names': ['Abdoulaye', 'Boureima', 'Cheick', 'Daouda', 'Emmanuel', 'François', 'Gérard', 'Hervé', 'Issouf', 'Jean'],
        'surnames': ['Traoré', 'Keita', 'Coulibaly', 'Diallo', 'Sangaré', 'Diarra', 'Koné', 'Doumbia', 'Touré', 'Sissoko']
    },
    'Martinique': {
        'probability': 0.003038,
        'skin_color': [(3, 0.30), (4, 0.70)],  # 30% skin=3, 70% skin=4
        'first_names': ['Alain', 'Bruno', 'Christian', 'Daniel', 'Emmanuel', 'François', 'Gabriel', 'Henri', 'Ivan', 'Jean'],
        'surnames': ['Mabiala', 'Nkounkou', 'Moukila', 'Bouanga', 'Makengo', 'Ndinga', 'Mabika', 'Bouanga', 'Moukila', 'Nkounkou']
    },
    'Mozambique': {
        'probability': 0.003038,
        'skin_color': [(3, 0.25), (4, 0.75)],  # 25% skin=3, 75% skin=4
        'first_names': ['Abel', 'Gildo', 'Carlos', 'Clésio', 'Emmanuel', 'Edson', 'Gabriel', 'Rique', 'Reinildo', 'Ronaldo'],
        'surnames': ['Mabiala', 'Silva', 'Mexer', 'Quembo', 'Makengo', 'Néné', 'Lourenço', 'Catamo', 'Martins', 'Dove']
    },
    'Netherlands Antilles': {
        'probability': 0.003038,
        'skin_color': [(1, 0.20), (3, 0.60), (4, 0.20)],  # 20% skin=1, 60% skin=3, 20% skin=4
        'first_names': ['Anthony', 'Brian', 'Carl', 'David', 'Eric', 'Frank', 'George', 'Henry', 'Ivan', 'John'],
        'surnames': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez']
    },
    'New Zealand': {
        'probability': 0.003514,
        'skin_color': [(1, 0.60), (2, 0.25), (3, 0.15)],  # 60% skin=1, 25% skin=2, 15% skin=3
        'first_names': ['Aaron', 'Ben', 'Chris', 'David', 'Erik', 'Frank', 'George', 'Henry', 'Ivan', 'John', 'Blake', 'Connor', 'Declan', 'Ethan', 'Flynn', 'Harrison', 'Isaac', 'Jake'],
        'surnames': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez']
    },
    'Oman': {
        'probability': 0.003038,
        'skin_color': [(2, 0.70), (3, 0.30)],  # 70% skin=2, 30% skin=3
        'first_names': ['Ahmed', 'Badr', 'Fahad', 'Hamed', 'Ibrahim', 'Jaber', 'Khalid', 'Majid', 'Nasser', 'Omar'],
        'surnames': ['Al-Rashid', 'Al-Zahra', 'Al-Mansouri', 'Al-Hajri', 'Al-Balushi', 'Al-Saadi', 'Al-Mahrouqi', 'Al-Hinai', 'Al-Kharusi', 'Al-Shamsi']
    },
    'Panama': {
        'probability': 0.003038,
        'skin_color': [(1, 0.25), (3, 0.65), (4, 0.10)],  # 25% skin=1, 65% skin=3, 10% skin=4
        'first_names': ['Alejandro', 'Carlos', 'Diego', 'Eduardo', 'Fernando', 'Gabriel', 'Héctor', 'Iván', 'Jorge', 'Luis'],
        'surnames': ['Rodríguez', 'González', 'García', 'Martínez', 'López', 'Pérez', 'Sánchez', 'Fernández', 'Silva', 'Díaz']
    },
    'Romania': {
        'probability': 0.007362,
        'skin_color': [(1, 0.90), (3, 0.10)],  # 90% skin=1, 10% skin=3
        'first_names': ['Alexandru', 'Bogdan', 'Cristian', 'Daniel', 'Eduard', 'Florin', 'Adrian', 'Razvan', 'Iannis', 'Leo'],
        'surnames': ['Popescu', 'Ionescu', 'Popa', 'Radu', 'Mutu', 'Hagi', 'Dumitrescu', 'Pilitanescu', 'Constantinescu', 'Marin']
    },
    'Saudi Arabia': {
        'probability': 0.004,
        'skin_color': [(2, 0.60), (3, 0.40)],  # 60% skin=2, 40% skin=3
        'first_names': ['Ahmed','Jehad','Abdulelah','Yasser','Mohammed','Ziyad','Saleh','Turki','Ali','Mukhtar'],
        'surnames': ['Kadesh','Hamidou','Ali','Hazzazi','Fallatah','Saad','Salem','Hassan','Al-Najei','Al-Boushal']
    },
    'Serbia and Montenegro': {
        'probability': 0.003038,
        'skin_color': [(1, 0.90), (3, 0.10)],  # 90% skin=1, 10% skin=3
        'first_names': ['Aleksandar', 'Bojan', 'Darko', 'Nikolas', 'Filip', 'Goran', 'Srdjan', 'Ivan', 'Jovan', 'Kristijan'],
        'surnames': ['Jovanović', 'Petrović', 'Nikolić', 'Marković', 'Đorđević','Slagalo', 'Stojanović', 'Ilić', 'Stanković', 'Pavlović', 'Milošević']
    },
    'Sierra Leone': {
        'probability': 0.003038,
        'skin_color': [(3, 0.20), (4, 0.80)],  # 20% skin=3, 80% skin=4
        'first_names': ['Abel', 'Ben', 'Carl', 'David', 'Eric', 'Frank', 'George', 'Henry', 'Ivan', 'John'],
        'surnames': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez']
    },
    'Slovakia': {
        'probability': 0.003038,
        'skin_color': [(1, 0.95), (3, 0.05)],  # 95% skin=1, 5% skin=3
        'first_names': ['Adam', 'Branislav', 'Daniel', 'Erik', 'Filip', 'Gabriel', 'Henrich', 'Ivan', 'Jozef', 'Kamil'],
        'surnames': ['Horváth', 'Kováč', 'Varga', 'Tóth', 'Nagy', 'Szabó', 'Molnár', 'Németh', 'Balog', 'Lukáč']
    },
    'Slovenia': {
        'probability': 0.003038,
        'skin_color': [(1, 0.95), (3, 0.05)],  # 95% skin=1, 5% skin=3
        'first_names': ['Aleš', 'Bojan', 'Dejan', 'Erik', 'Filip', 'Gregor', 'Henrik', 'Igor', 'Jure', 'Klemen'],
        'surnames': ['Novak', 'Horvat', 'Krajnc', 'Zupančič', 'Kovačič', 'Mlakar', 'Vidmar', 'Petek', 'Kos', 'Zajc']
    },
    'Togo': {
        'probability': 0.003038,
        'skin_color': [(3, 0.25), (4, 0.75)],  # 25% skin=3, 75% skin=4
        'first_names': ['Franck','Emmanuel','Eric','Prince','Désire','Moustapha','Richmond','Adékambi','Jean-Paul','Ouro'],
        'surnames': ['Adebayor','Salifou','Atsou','Akotou','Abalo','Boukari','Senaya','Touré','Salou','Wazo']
    },
    'Trinidad and Tobago': {
        'probability': 0.003038,
        'skin_color': [(1, 0.10), (3, 0.40), (4, 0.50)],  # 10% skin=1, 40% skin=3, 50% skin=4
        'first_names': ['Anthony', 'Brian', 'Carl', 'David', 'Eric', 'Frank', 'George', 'Henry', 'Ivan', 'John'],
        'surnames': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Latapy', 'Miller', 'Davis', 'Rodriguez', 'Sparow']
    },
    'United States': {
        'probability': 0.003038,
        'skin_color': [(1, 0.60), (3, 0.25), (4, 0.15)],  # 60% skin=1, 25% skin=3, 15% skin=4
        'first_names': ['Kevin','Lebron','Barrack','Denzel','Michael','Donald','Geogre','Vince','Cody', 'Randy'],
        'surnames': ['James','Page','Rhodes','Heyman','Curry','Jordan','Michaels','London','Summer','Copeland','Saint-John']
    },
    'Uzbekistan': {
        'probability': 0.003038,
        'skin_color': [(2, 0.80), (3, 0.20)],  # 80% skin=2, 20% skin=3
        'first_names': ['Akmal', 'Bakhtiyor', 'Dilshod', 'Eldor', 'Farrukh', 'Gulom', 'Hikmat', 'Ibrohim', 'Javlon', 'Karim'],
        'surnames': ['Karimov', 'Rashidov', 'Toshev', 'Nazirov', 'Khamidov', 'Usmanov', 'Yuldashev', 'Rakhimov', 'Saidov', 'Kurbanov']
    },
    'Zambia': {
        'probability': 0.003038,
        'skin_color': [(3, 0.20), (4, 0.80)],  # 20% skin=3, 80% skin=4
        'first_names': ['Abel', 'Ben', 'Carl', 'David', 'Eric', 'Frank', 'George', 'Henry', 'Ivan', 'John'],
        'surnames': ['Mwamba', 'Chilufya', 'Banda', 'Mwanza', 'Sichone', 'Katongo', 'Kalaba', 'Mweene', 'Sunzu', 'Mulenga']
    },
    'Zimbabwe': {
        'probability': 0.003038,
        'skin_color': [(3, 0.15), (4, 0.85)],  # 15% skin=3, 85% skin=4
        'first_names': ['Abel', 'Ben', 'Carl', 'David', 'Eric', 'Frank', 'George', 'Henry', 'Ivan', 'John'],
        'surnames': ['Mugabe', 'Tsvangirai', 'Nkomo', 'Mugabe', 'Chinamasa', 'Mpofu', 'Mugabe', 'Tsvangirai', 'Nkomo', 'Mugabe']
    }
}

# Surname data by nationality
# NOTE: This is now only used for backward compatibility.
# All countries in NATIONALITY_DATA now have 'surnames' included.
# This can be removed once all code paths are confirmed to use the new structure.
SURNAME_DATA = {
    'Brazil': ['Maravilha','Amazonia','Xareca','Silva','Mineiro','Paulista','Luso','Gaucho','Baiano','Chupeta','Nazario','Aveiro','Santana','Jesus','Junior','Galindro','Souza','Nitro','Melo','Ronaldo','Pato','Ribas'],
    'Argentina': ['Palermo','Cruz','Almeyda','Varela','Valdano','Diaz','Messi','Bautista','Simeone','Lopez','Sotto','Correa','Rulli','Farias','Mareque','Toro','Pavon','Di Santi','Gomez'],
    'Spain': ['Banderas','Hernandez','Gonzalez','de la Costa','Laporte','del Campo','Garcia','Navarro','Salazar','Gusto','Peralta','Rico','Pinjuan','Fernandez','Lopetegui','Enrique','del Rio','Begiristáin','Camacho','de la Buena'],
    'France': ['Benoit','Saint Laurent','Chanel','Givenchy','Gaultier','Papisse','Candela','Papin','Patrice','Fontaine','Remy','Pavard','Ratatouille','Gusteau','Jacquin','Bonaparte','Dior','Chalamet','Brouyche','Dujardin'],
    'England': ['Beckham','Adams','Cole','McCoy','Xavier','Pearce','Baines','Holmes','Wallace','Potter','Weasley','Baggins','Reigns','Kross','McDonagh','Flair','Owen','Charlton','Stark','King'],
    'Germany': ['Meyer','Muller','Nicholas','Schumacher','Schawrz','Einstein','Kant','Marx','Kaiser','Panzer','von Bismarck','Fassbender','Otto','Kruger','Rudof','Hoss','Goring','Effenberg','Himmler','Schneider'],
    'Italy': ['Corleone','Rossi','Gentile','Zola','Dimarco','Della Rocca','Bastoni','Negroni','Fetuccini','Rossini','Clemenza','Fanucci','del Neri','Constanzini','Lamberto','Berlusconi','da Vinci','Baggio','Pavarotti','Bucetti'],
    'Portugal': ['Silva','Galindro','Da Rocha','Rochinha','Amaral','Felix','Capelao','Quaresma','Carvalho','Leitinho','Fernandes','Da Costa','Abreu','Seabra','Cardoso','Ferreirinha','Varandas','Martins','Gastão','Guedes'],
    'Netherlands': ['van der Vaart','Kluivert','De Jong','Van Bommel','de Boer','Janssen','van de Beek','de Vrijens','van Gallen','Basten','Berg','Bosman','Rijens','Schaar','Cruijff','Wetterman','Dumfries','Stan','de Ligt',],
    'Belgium': ['den Borr','Meunier','Preud','Yannick','Gillet','Praet','Sels','van Prist','Chalomet','van Zeno','Cuyper','Wilde','Brunyet','Castagne','Weiss','Goose','Bruyne','Ruus','Emmers','Boyata'],
    'Croatia': ['Subasic','Kovacic','Petric','Vlasic','Pilitic','Milic','Bilic','Pjaca','Zivjaca','Badelj'],
    'Serbia': ['Slagalo','Jovanovic','Milosevic','Ibisevic','Drulovic','Rochovic','Milosevic','Popovic','Krenkov','Dukic'],
    'Poland': ['Milik','Piatek','Zalewski','Dudek','Zielinski','Rybus','Panterizki','Razça','Boniek','Caganarek'],
    'Ukraine': ['Stepanenko','Rebrov','Maluchencko','Milesvkiy','Mykolenko','Gansov','Litochencko','Koval','Zielinski','Malyshev'],
    'Russia': ['Alenitchev','Stallin','Romanoff','Bereshakov','Kutin','Maloev','Sychevchenko','Joorgev','Dubrovski','Zasputin'],
    'Turkey': ['Coçalhoglu','Terim','Tosun','Cetin','Tuncay','Sukur','Yilmaz','Demiral','Guler','Betozoglu'],
    'Morocco': ['Belhanda','Rabat','Chafik','Moufassa','Kabella','Nazer','Chamakh','Zairi','Naybet','Boussaf'],
    'Algeria': ['Madjer','Assad','Kadir','Soudani','Ghilas','Saifi','Djebour','Saiid','Brahimi','Boudaoui'],
    'Senegal': ['Sylva','Diop','Ndiaye','Sow','Gueye','Babacar','Diao','Diarra','Gomis','Ba'],
    'Nigeria': ['Zaidu','Agu','Kanu','Taribo','Babayaro','Omeru','Akwue','Obafemi','Aina','Owusuwelele'],
    'Ghana': ['Diouf','Atsu','Boateng','Prince','Addo','Kudus','Mensah','Fatu','Gyan','Sunday','Essien'],
    'Cameroon': ['Mbeuna','Kongolo','Ekotto','Milla','Song','Bilong','Nego','Onana','Matip','Preto o'],
    'Egypt': ['Marmoush','Ghaly','Imoteph','Zidan','Elneny','Faisel','Nahmed','Saleht','Rafaat','Zamal'],
    'Tunisia': ['Trabelsi','Jaziri','Khazim','Quedir','Nejib','Houssem','Slim','Meriah','Belaid','Achouri'],
    'South Africa': ['Fortune','McCarthy','Zuma','Mokoena','Mandela','Joseph','Pistorious','Kulele','Tsahbalala','Zwane'],
    'Japan': ['Hyuga','Wakabayashi','Misaki','Tsubasa','Inamoto','Nakamura','Nakazawa','Gohan','Nakata','Fujimoto'],
    'South Korea': ['Ming','Park','Ling','Chun','Gun','Son','Young','Ben','Choy','Mill'],
    'China': ['Wang', 'Li', 'Zhang', 'Liu', 'Chen', 'Yang', 'Huang', 'Zhao', 'Wu', 'Zhou'],
    'Australia': ['Cahill','Ingles','Viduka','Morten','Kennedy','Foster','Rodwell','Winchester','Jackman','Kerr'],
    'Mexico': ['Hernandez','Gutierrez','Banderas','Martinez','Fonseca','Herrera','Sanchez','Marquez','de la Vega'],
    'Colombia': ['Martinez','Diaz','Escobar','Yepes','Leon','Ortiz','Rincon','Eusebio','Rios','Rodriguez'],
    'Chile': ['González', 'Muñoz', 'Rojas', 'Díaz', 'Pérez', 'Soto', 'Silva', 'Morales', 'Flores', 'Castro'],
    'Uruguay': ['Rodríguez', 'González', 'Silva', 'Pastore', 'García', 'Formentera', 'Ruiz', 'Martínez', 'Díaz', 'Hernández'],
    'Paraguay': ['Cardozo', 'González', 'Silva', 'Pérez', 'Santa Cruz', 'Ballasteros', 'López', 'Martínez', 'Díaz', 'Hernández'],
    'Peru': ['Rodríguez', 'González', 'Silva', 'Bakero', 'García', 'Fernández', 'López', 'Martínez', 'Díaz', 'Hernández'],
    'Ecuador': ['Rodríguez', 'González', 'Silva', 'Cabra', 'García', 'Fernández', 'Vasquez', 'Martínez', 'Díaz', 'Hernández'],
    'Venezuela': ['Rodríguez', 'González', 'Lucho', 'Pérez', 'García', 'Buenavista', 'Libre', 'Martínez', 'Díaz', 'Hernández'],
    'Canada': ['Mark', 'Thomas','Rodrigo','Edgar','Philip','Kirr','Dacourt','Falurein','Gustaff','Moore'],
    
    # Additional countries surnames
    'Austria': ['Müller', 'Schmidt', 'Schneider', 'Fischer', 'Weber', 'Meyer', 'Muschaft', 'Becker', 'Schulz', 'Goring', 'Eisenwoer','Ziegler'],
    'Switzerland': ['Blanc', 'Schmidt', 'Dubois', 'Robertstein', 'Frei', 'Meyer', 'Raffaello', 'Becker', 'Schulz', 'Perrin', 'Silva','Ziegler'],
    'Sweden': ['Marksson', 'Larsson', 'Svensson', 'Karlsson', 'Eriksson', 'Junstorm', 'Hallstrom', 'Rottenberg', 'Storm', 'Vannaheim', 'Andersson','Hiccup'],
    'Norway': ['Markssen', 'Larssen', 'Olsen', 'Vaalaand', 'Erikssen', 'Braut', 'Pedersen', 'Berg', 'Dahl', 'Haaland', 'Andersen','Estoic'],
    'Denmark': ['Eriksen', 'Larsen', 'Kjaer', 'Froholt', 'Huljmand', 'Tommasson', 'Jorgensen', 'Kasper', 'Hojlmund', 'Christensen', 'Andersen','Sorensen'],
    'Finland': ['Heikinen', 'Makela', 'Litmanem', 'Hyppia', 'Moller', 'Trosten', 'Niemi', 'Koivist', 'Virtanen', 'Iltamen', 'Jarvinen','Sulkvist'],
    'Iceland': ['Jónsson', 'Sigurðsson', 'Guðmundsson', 'Gunnarsson', 'Ólafsson', 'Einarsson', 'Kristjánsson', 'Magnússon', 'Stefánsson', 'Jóhannesson', 'Björnsson','Loki'],
    'Ireland': ['Murphy', 'Kelly', 'Sullivan', 'Guiness', 'Smith', 'O\'Brien',  'O\'Connor', 'O\'Neill', 'O\'Reilly' 'Quinn','O\'Callaghan', 'O\'Shea', 'Dunne', 'Fitzgerald'],
    'Scotland': ['Smith', 'MacGregor','Ferguson','MacDonald','McLean','Stewart','Robertson','Murray','Graham','Armstrong','Douglas'],
    'Wales': ['Williams','Evans','Hughes','Pritchard','Powell','Bale','Griffiths','Lancelot','Percival','Price'],
    'Northern Ireland': ['Murphy', 'Kelly', 'Sullivan', 'Guiness', 'Smith', 'O\'Brien',  'O\'Connor', 'O\'Neill', 'O\'Reilly' 'Quinn','O\'Callaghan', 'O\'Shea', 'Dunne', 'Fitzgerald'],
    
    # Additional missing countries surnames
    'Albania': ['Abazaj', 'Mitaj', 'Berisha', 'Gashi', 'Kadriu', 'Euzabaj', 'Pajaziti', 'Rexhepi', 'Durmisi', 'Cana'],
    'Angola': ['Santos', 'Fernandes', 'Teta', 'Costa', 'Ferradura', 'Cacimbo', 'Rodrigues', 'Ferreira', 'Vemba', 'Gomes'],
    'Armenia': ['Grigoryan', 'Khachatryan', 'Harutyunyan', 'Sargsyan', 'Vardanyan', 'Petrosyan', 'Mkhitaryan', 'Ghazaryan', 'Chyan', 'Avetisyan'],
    'Belarus': ['Ivanov', 'Petrov', 'Sidorov', 'Kozlov', 'Morozov', 'Volkov', 'Alekseev', 'Lebedev', 'Semenov', 'Egorov'],
    'Cape Verde': ['Santos', 'Varela', 'Patrao', 'Costa', 'Pereira', 'Mota', 'Rodrigues', 'Luvinha', 'Alves', 'Gomes'],
    'Benin': ['Adjanohoun', 'Agbessi', 'Akplogan', 'Bokonon', 'Dossou', 'Gbaguidi', 'Houngbédji', 'Kouassi', 'Migan', 'Tchibozo'],
    'Bolivia': ['García', 'Rodríguez', 'González', 'Martínez', 'López', 'Pérez', 'Sánchez', 'Fernández', 'Silva', 'Díaz'],
    'Bosnia and Herzegovina': ['Kovačević', 'Petrović', 'Nikolić', 'Marković', 'Đorđević', 'Stojanović', 'Ilić', 'Stanković', 'Pavlović', 'Milošević'],
    'Bulgaria': ['Ivanov', 'Petrov', 'Georgiev', 'Dimitrov', 'Stoyanov', 'Nikolov', 'Todorov', 'Hristov', 'Atanasov', 'Vasilev'],
    'Burkina Faso': ['Ouédraogo', 'Traoré', 'Sawadogo', 'Kaboré', 'Zongo', 'Ouattara', 'Bikienga', 'Boukary', 'Compaoré', 'Dabiré'],
    'Congo': ['Mabiala', 'Nkounkou', 'Moukila', 'Bouanga', 'Makengo', 'Ndinga', 'Mabika', 'Bouanga', 'Moukila', 'Nkounkou'],
    'Costa Rica': ['Rodríguez', 'González', 'Romero', 'Martínez', 'López', 'Pérez', 'Sánchez', 'Fernández', 'Bolanos', 'Díaz'],
    'Cote d\'Ivoire': ['Traoré', 'Ouattara', 'Koné', 'Diabaté', 'Bamba', 'Coulibaly', 'Drogba', 'Kalou', 'Tiéné', 'Zokora'],
    'Cyprus': ['Georgiou', 'Ioannou', 'Christou', 'Michael', 'Andreou', 'Constantinou', 'Papa', 'Kyprianou', 'Charalambous', 'Demetriou'],
    'Czech Republic': ['Novák', 'Svoboda', 'Novotný', 'Dvořák', 'Černý', 'Procházka', 'Kučera', 'Veselý', 'Horák', 'Němec'],
    'DR Congo': ['Mabiala', 'Nkounkou', 'Moukila', 'Bouanga', 'Makengo', 'Ndinga', 'Mabika', 'Bouanga', 'Moukila', 'Nkounkou'],
    'Equatorial Guinea': ['Mba', 'Nguema', 'Obiang', 'Mangue', 'Nsue', 'Bikoro', 'Sipoto', 'Mangue', 'Nsue', 'Bikoro'],
    'Estonia': ['Tamm', 'Saar', 'Sepp', 'Mägi', 'Kask', 'Kukk', 'Ilves', 'Rebane', 'Karu', 'Lepik'],
    'Free Nationality': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez'],
    'Gabon': ['Mabiala', 'Nkounkou', 'Moukila', 'Bouanga', 'Makengo', 'Ndinga', 'Mabika', 'Bouanga', 'Moukila', 'Nkounkou'],
    'Gambia': ['Jallow', 'Sanneh', 'Ceesay', 'Jobe', 'Manneh', 'Colley', 'Barry', 'Sarr', 'Gomez', 'Bojang'],
    'Georgia': ['Gelashvili', 'Kvaratskhelia', 'Mamardashvili', 'Kakabadze', 'Davitashvili', 'Kvaratskhelia', 'Mamardashvili', 'Kakabadze', 'Davitashvili', 'Gelashvili'],
    'Greece': ['Papadopoulos', 'Forneiridis', 'Karagiannis', 'Leonidas', 'Kratos', 'Nikolaidis', 'Samaris', 'Malakaidis', 'Pretorius', 'Pyssas'],
    'Grenada': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez'],
    'Guadeloupe': ['Mabiala', 'Nkounkou', 'Moukila', 'Bouanga', 'Makengo', 'Ndinga', 'Mabika', 'Bouanga', 'Moukila', 'Nkounkou'],
    'Guinea': ['Diallo', 'Bah', 'Camara', 'Traoré', 'Sow', 'Barry', 'Keita', 'Sylla', 'Cissé', 'Touré'],
    'Guinea-Bissau': ['Mendes', 'Fernandes', 'Silva', 'Costa', 'Pereira', 'Oliveira', 'Rodrigues', 'Ferreira', 'Alves', 'Gomes'],
    'Honduras': ['Rodríguez', 'González', 'García', 'Martínez', 'López', 'Pérez', 'Suazo', 'Fernández', 'Rondon', 'Díaz'],
    'Hungary': ['Nagy', 'Kovács', 'Tóth', 'Szabó', 'Horváth', 'Varga', 'Kiss', 'Molnár', 'Németh', 'Farkas'],
    'Iran': ['Mohammadi', 'Rezaei', 'Hassani', 'Karimi', 'Ahmadi', 'Nouri', 'Gholami', 'Faraji', 'Ebrahimi', 'Rahmani'],
    'Israel': ['Cohen', 'Levy', 'Mizrahi', 'Avraham', 'David', 'Shalom', 'Ben-David', 'Rosenberg', 'Goldberg', 'Weiss'],
    'Jamaica': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Kingston', 'Marley'],
    'Kenya': ['Mwangi', 'Njoroge', 'Kipchoge', 'Ochieng', 'Wanjiku', 'Kamau', 'Nyong\'o', 'Odinga', 'Kenyatta', 'Moi'],
    'Latvia': ['Bērziņš', 'Kalniņš', 'Ozols', 'Liepiņš', 'Dzērve', 'Priede', 'Eglītis', 'Vītols', 'Mežs', 'Silis'],
    'Liberia': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez'],
    'Liechtenstein': ['Müller', 'Schmidt', 'Schneider', 'Fischer', 'Weber', 'Meyer', 'Wagner', 'Becker', 'Schulz', 'Hoffmann'],
    'Lithuania': ['Kazlauskas', 'Petraitis', 'Jankauskas', 'Stankevičius', 'Vasiliauskas', 'Butkus', 'Grigas', 'Lukšys', 'Mickevičius', 'Navickas'],
    'Macedonia': ['Nikolovski', 'Petrovski', 'Georgievski', 'Dimitrovski', 'Stojanovski', 'Todorovski', 'Hristovski', 'Atanasovski', 'Vasilevski', 'Ilievski'],
    'Mali': ['Traoré', 'Keita', 'Coulibaly', 'Diallo', 'Sangaré', 'Diarra', 'Koné', 'Doumbia', 'Touré', 'Sissoko'],
    'Martinique': ['Mabiala', 'Nkounkou', 'Moukila', 'Bouanga', 'Makengo', 'Ndinga', 'Mabika', 'Bouanga', 'Moukila', 'Nkounkou'],
    'Mozambique': ['Mabiala', 'Silva', 'Mexer', 'Quembo', 'Makengo', 'Néné', 'Lourenço', 'Catamo', 'Martins', 'Dove'],
    'Netherlands Antilles': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez'],
    'New Zealand': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez'],
    'Oman': ['Al-Rashid', 'Al-Zahra', 'Al-Mansouri', 'Al-Hajri', 'Al-Balushi', 'Al-Saadi', 'Al-Mahrouqi', 'Al-Hinai', 'Al-Kharusi', 'Al-Shamsi'],
    'Panama': ['Rodríguez', 'González', 'García', 'Martínez', 'López', 'Pérez', 'Sánchez', 'Fernández', 'Silva', 'Díaz'],
    'Romania': ['Popescu', 'Ionescu', 'Popa', 'Radu', 'Mutu', 'Hagi', 'Dumitrescu', 'Pilitanescu', 'Constantinescu', 'Marin'],
    'Saudi Arabia': ['Kadesh','Hamidou','Ali','Hazzazi','Fallatah','Saad','Salem','Hassan','Al-Najei','Al-Boushal'],
    'Serbia and Montenegro': ['Jovanović', 'Petrović', 'Nikolić', 'Marković', 'Đorđević','Slagalo', 'Stojanović', 'Ilić', 'Stanković', 'Pavlović', 'Milošević'],
    'Sierra Leone': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez'],
    'Slovakia': ['Horváth', 'Kováč', 'Varga', 'Tóth', 'Nagy', 'Szabó', 'Molnár', 'Németh', 'Balog', 'Lukáč'],
    'Slovenia': ['Novak', 'Horvat', 'Krajnc', 'Zupančič', 'Kovačič', 'Mlakar', 'Vidmar', 'Petek', 'Kos', 'Zajc'],
    'Togo': ['Adebayor','Salifou','Atsou','Akotou','Abalo','Boukari','Senaya','Touré','Salou','Wazo'],
    'Trinidad and Tobago': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Latapy', 'Miller', 'Davis', 'Rodriguez', 'Sparow'],
    'United States': ['James','Page','Rhodes','Heyman','Curry','Jordan','Michaels','London','Summer','Copeland','Saint-John'],
    'Uzbekistan': ['Karimov', 'Rashidov', 'Toshev', 'Nazirov', 'Khamidov', 'Usmanov', 'Yuldashev', 'Rakhimov', 'Saidov', 'Kurbanov'],
    'Zambia': ['Mwamba', 'Chilufya', 'Banda', 'Mwanza', 'Sichone', 'Katongo', 'Kalaba', 'Mweene', 'Sunzu', 'Mulenga'],
    'Zimbabwe': ['Mugabe', 'Tsvangirai', 'Nkomo', 'Mugabe', 'Chinamasa', 'Mpofu', 'Mugabe', 'Tsvangirai', 'Nkomo', 'Mugabe']
}

def crop_name(name: str, max_length: int = 25) -> str:
    """Crop a name to fit database limits (default 15 characters for PES6)."""
    if len(name) <= max_length:
        return name
    return name[:max_length].rstrip()

def generate_player_name(nationality: str) -> Tuple[str, str]:
    """Generate a realistic first name and surname for a given nationality."""
    if nationality not in NATIONALITY_DATA:
        nationality = 'England'  # Default fallback
    
    # Support both old structure (with 'names' and SURNAME_DATA) and new structure
    nat_data = NATIONALITY_DATA[nationality]
    if 'first_names' in nat_data:
        # New structure: first_names and surnames in same dict
        first_names = nat_data['first_names']
        surnames = nat_data.get('surnames', [])
    else:
        # Old structure: 'names' in NATIONALITY_DATA, surnames in SURNAME_DATA
        first_names = nat_data.get('names', [])
        surnames = SURNAME_DATA.get(nationality, SURNAME_DATA.get('England', []))
    
    # 30% chance to have only one name (either first name OR surname)
    if random.random() < 0.30 or not surnames:
        # Single name: 50% chance first name, 50% chance surname
        if random.random() < 0.50 and first_names:
            # Use first name only
            first_name = random.choice(first_names) if first_names else 'John'
            surname = ""
        elif surnames:
            # Use surname only
            first_name = ""
            surname = random.choice(surnames)
        else:
            # Fallback to first name if no surnames available
            first_name = random.choice(first_names) if first_names else 'John'
            surname = ""
    else:
        # Two names: first name + surname
        first_name = random.choice(first_names) if first_names else 'John'
        surname = random.choice(surnames)
    
    # Crop names to fit database limits (15 chars for PES6)
    # For full names: first_name + " " + surname must be <= 15
    # For single names: just the name must be <= 15
    if surname:
        # Two names: ensure total length <= 15 (including space)
        # If too long, prioritize first name (max 7) and surname (max 7), leaving 1 for space
        if len(first_name) + len(surname) + 1 > 15:
            # Need to crop both to fit
            max_first = min(7, len(first_name))
            max_surname = min(7, len(surname))
            # Adjust if one is shorter
            if len(first_name) <= 7:
                max_surname = 15 - len(first_name) - 1
            elif len(surname) <= 7:
                max_first = 15 - len(surname) - 1
            first_name = crop_name(first_name, max_first)
            surname = crop_name(surname, max_surname)
        else:
            # Both fit, but still crop individual parts to 15 max each
            first_name = crop_name(first_name, 15)
            surname = crop_name(surname, 15)
    else:
        # Single name: crop to 15
        if first_name:
            first_name = crop_name(first_name, 15)
        elif surname:
            surname = crop_name(surname, 15)
    
    return first_name, surname

def select_nationality() -> str:
    """Select a nationality based on weighted probabilities."""
    nationalities = list(NATIONALITY_DATA.keys())
    # Support both old 'weight' and new 'probability' keys for backward compatibility
    weights = [NATIONALITY_DATA[nat].get('probability', NATIONALITY_DATA[nat].get('weight', 0.01)) for nat in nationalities]
    
    # Normalize weights to sum to 1
    total_weight = sum(weights)
    normalized_weights = [w / total_weight for w in weights]
    
    return random.choices(nationalities, weights=normalized_weights)[0]

def generate_player_attributes(age: int, position: str, db_path: str = None) -> Dict[str, int]:
    """Generate realistic player attributes based on age and position using existing positional averages."""
    # Get cached position averages
    if db_path:
        position_averages = get_cached_position_averages(db_path)
    else:
        # Use default averages if no database path provided
        position_averages = None
    
    # Age-based development factor (younger players have lower attributes)
    # For 16-18 year olds, they should be 60-75% of peak attributes
    age_factor = 0.6 + (age - 16) * 0.075  # 16yo = 60%, 17yo = 67.5%, 18yo = 75%
    
    # Generate attributes based on position averages
    attributes = {}
    
    if position_averages is not None and position in position_averages.index:
        # Get the position averages
        pos_avg = position_averages.loc[position]
        
        # Generate attributes based on position averages
        for skill in pos_avg.index:
            if pd.notna(pos_avg[skill]):  # Check if the skill exists for this position
                base_value = pos_avg[skill]
                
                # Apply age factor and add some randomness
                variation = random.uniform(-8, 8)  # ±8 points variation
                final_value = int(base_value * age_factor + variation)
                
                # Ensure values are within valid range (1-99)
                final_value = max(1, min(99, final_value))
                attributes[skill] = final_value
    else:
        # Fallback to basic attributes if no position averages available
        basic_attrs = {
            'attack': 50, 'defense': 50, 'balance': 60, 'stamina': 70, 
            'top_speed': 60, 'acceleration': 60, 'response': 60, 'agility': 60,
            'dribble_accuracy': 50, 'dribble_speed': 50, 'short_pass_accuracy': 50,
            'short_pass_speed': 50, 'long_pass_accuracy': 50, 'long_pass_speed': 50,
            'shot_accuracy': 50, 'shot_power': 50, 'shot_technique': 50,
            'free_kick_accuracy': 50, 'swerve': 50, 'heading': 50, 'jump': 50,
            'technique': 50, 'aggression': 50, 'mentality': 50, 'goal_keeping': 50,
            'team_work': 50, 'consistency': 50, 'condition_fitness': 50
        }
        
        for skill, base_value in basic_attrs.items():
            variation = random.uniform(-8, 8)
            final_value = int(base_value * age_factor + variation)
            final_value = max(1, min(99, final_value))
            attributes[skill] = final_value
    
    return attributes

def get_position_name_mapping():
    """Get mapping from position numbers to position names (matches refresh_and_reimport.py)."""
    return {
        0: 'Goal-Keeper',
        2: 'Sweeper',
        3: 'Centre-Back',
        4: 'Side-Back',
        5: 'Defensive Midfielder',
        6: 'Wing-Back',
        7: 'Center-Midfielder',
        8: 'Side-Midfielder',
        9: 'Attacking Midfielder',
        10: 'Winger',
        11: 'Shadow Striker',
        12: 'Striker',
        13: 'Unknown'  # Handle position 13
    }

def calculate_bundled_skill_ratings(skill_attributes: Dict) -> Dict:
    """Calculate bundled skill ratings from individual skills."""
    return {
        'attack_rating': (skill_attributes['attack'] + skill_attributes['shot_technique'] + 
                         skill_attributes['shot_accuracy'] + skill_attributes['aggression']) // 4,
        'defense_rating': (skill_attributes['defense'] + skill_attributes['heading'] + 
                          skill_attributes['jump'] + skill_attributes['balance']) // 4,
        'physical_rating': (skill_attributes['stamina'] + skill_attributes['top_speed'] + 
                          skill_attributes['acceleration'] + skill_attributes['response'] + 
                          skill_attributes['agility'] + skill_attributes['jump']) // 6,
        'power_rating': (skill_attributes['shot_power'] + skill_attributes['balance'] + 
                       skill_attributes['mentality']) // 3,
        'technique_rating': (skill_attributes['technique'] + skill_attributes['swerve'] + 
                           skill_attributes['free_kick_accuracy'] + skill_attributes['dribble_accuracy'] + 
                           skill_attributes['dribble_speed'] + skill_attributes['short_pass_accuracy'] + 
                           skill_attributes['short_pass_speed'] + skill_attributes['long_pass_accuracy'] + 
                           skill_attributes['long_pass_speed']) // 9,
        'goalkeeping_rating': (skill_attributes['defense'] + skill_attributes['goal_keeping'] + 
                             skill_attributes['response'] + skill_attributes['agility']) // 4
    }

def modify_regen_with_base_player(regen_data: Dict, db_path: str = None) -> Dict:
    """
    Modify regen_data by using attributes from a base player in original.sqlite.
    For testing purposes, always uses player ID 3226.
    
    Args:
        regen_data: The regen data dictionary to modify
        db_path: Path to the database (optional)
    
    Returns:
        Modified regen_data dictionary
    """
    import sqlite3
    import random
    import time
    
    # Seed the random number generator to ensure different results on each restart
    random.seed(time.time())
    
    # Randomly select a base player ID from 1 to 4783
    base_player_id = random.randint(1, 4783)
    
    try:
        # Connect to original.sqlite database
        original_db_path = '/home/anibalgalindro/SQLiteMigration/original.sqlite'
        conn = sqlite3.connect(original_db_path)
        cursor = conn.cursor()
        
        # Get base player data
        cursor.execute("SELECT * FROM players WHERE id = ?", (base_player_id,))
        base_player = cursor.fetchone()
        
        if not base_player:
            print(f"Warning: Base player with ID {base_player_id} not found in original.sqlite")
            conn.close()
            return regen_data
        
        # Get column names
        cursor.execute("PRAGMA table_info(players)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Create base player dictionary
        base_player_dict = dict(zip(columns, base_player))
        
        conn.close()
        
        # Persist the seed for downstream development orientation
        regen_data['seed_player'] = int(base_player_id)

        # Generate random age between 15-20
        age = random.randint(15, 20)
        regen_data['age'] = age
        
        # Calculate age-based skill modifier
        age_modifier = 0
        if age == 15:
            age_modifier = 4 + random.randint(-3, 3)  # Youngest = most penalty
        elif age == 16:
            age_modifier = 2 + random.randint(-3, 3)
        elif age == 17:
            age_modifier = 1 + random.randint(-3, 3)
        elif age == 18:
            age_modifier = -2 + random.randint(-3, 3)  # Baseline
        elif age == 19:
            age_modifier = -4 + random.randint(-3, 3)   # Older = less penalty
        elif age == 20:
            age_modifier = -6 + random.randint(-3, 3)   # Oldest = least penalty
        
        # Get inner_strength from regen_data (should be set previously)
        inner_strength = regen_data.get('inner_strength', 5)  # Default to 5 if not set
        
        # Calculate inner_strength-based penalty
        if inner_strength == 9:
            inner_strength_penalty = 15 + random.randint(-3, 3)
        elif inner_strength == 1:
            inner_strength_penalty = 30
        else:
            # Linear interpolation between 1 and 9
            inner_strength_penalty = 30 - ((inner_strength - 1) / 8) * 15 + random.randint(-3, 3)
        
        # Define positional attributes (overwrite with base player values)
        positional_attributes = {
            'gk': base_player_dict.get('gk', 0),
            'cwp': base_player_dict.get('cwp', 0),
            'cbt': base_player_dict.get('cbt', 0),
            'sb': base_player_dict.get('sb', 0),
            'dmf': base_player_dict.get('dmf', 0),
            'wb': base_player_dict.get('wb', 0),
            'cmf': base_player_dict.get('cmf', 0),
            'smf': base_player_dict.get('smf', 0),
            'amf': base_player_dict.get('amf', 0),
            'wf': base_player_dict.get('wf', 0),
            'ss': base_player_dict.get('ss', 0),
            'cf': base_player_dict.get('cf', 0)
        }
        
        # Inherit registered position from base player
        regen_data['registered_position'] = base_player_dict.get('registered_position', 'CMF')
        regen_data['game_position'] = base_player_dict.get('registered_position', 'CMF')
        
        # Get registered position to check if player is a goalkeeper (position 0)
        base_registered_position = base_player_dict.get('registered_position', None)
        is_goalkeeper = False
        if base_registered_position is not None:
            # Handle both string and integer formats
            if base_registered_position == 0 or base_registered_position == '0' or str(base_registered_position) == '0':
                is_goalkeeper = True
        
        # Define special attributes (binary skills) - all start at 0 for regens
        # They will be developed during the development process based on seed or random chance
        special_attributes = {
            'dribbling_skill': 0,
            'tactical_dribble': 0,
            'positioning': 0,
            'reaction': 0,
            'playmaking': 0,
            'passing': 0,
            'scoring': 0,
            'one_one_scoring': 0,
            'post_player': 0,
            'lines': 0,
            'middle_shooting': 0,
            'side': 0,
            'centre': 0,
            'penalties': 0,
            'one_touch_pass': 0,
            'outside': 0,
            'marking': 0,
            'sliding': 0,
            'covering': 0,
            'd_line_control': 0,
            'penalty_stopper': 0,
            'one_on_one_stopper': 0,
            'long_throw': 0
        }
        
        # Define skill attributes (apply penalties based on inner_strength and age, except consistency)
        skill_attributes = {}
        skill_fields = [
            'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
            'response', 'agility', 'dribble_accuracy', 'dribble_speed', 'short_pass_accuracy',
            'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed', 'shot_accuracy',
            'shot_power', 'shot_technique', 'free_kick_accuracy', 'swerve', 'heading',
            'jump', 'technique', 'aggression', 'goal_keeping', 'team_work', 'mentality'
        ]
        
        for skill in skill_fields:
            base_value = base_player_dict.get(skill, 0)
            if base_value is not None:
                # Apply inner_strength penalty + age modifier with per-skill randomness (-6 to +6)
                total_penalty = inner_strength_penalty + age_modifier
                # Add per-skill random variation (-6 to +6)
                skill_randomness = random.randint(-6, 6)
                skill_attributes[skill] = max(1, int(base_value - total_penalty + skill_randomness))
            else:
                skill_attributes[skill] = 1
        
        # If player is not a goalkeeper, set goal_keeping to 50
        if not is_goalkeeper:
            skill_attributes['goal_keeping'] = 50
        
        # Keep consistency unchanged
        skill_attributes['consistency'] = int(base_player_dict.get('consistency', 50))
        skill_attributes['condition_fitness'] = int(base_player_dict.get('condition_fitness', 50))
        
        # Update regen_data with modified attributes
        regen_data.update(positional_attributes)
        regen_data.update(special_attributes)
        regen_data.update(skill_attributes)
        
        print(f"Modified regen using base player ID {base_player_id} ({base_player_dict.get('player_name', 'Unknown')})")
        print(f"Age: {age}, Inner Strength: {inner_strength}, Total penalty: {inner_strength_penalty + age_modifier}")
        
    except Exception as e:
        print(f"Error modifying regen with base player: {e}")
    
    return regen_data

def generate_proper_regen(retired_player_data: Dict, db_path: str = None, override_nationality: str = None) -> Dict:
    """
    Generate a proper regen based on the retiring player's attributes.
    
    Args:
        retired_player_data: Dictionary containing the retiring player's data
        db_path: Path to the database (optional, for position averages)
        override_nationality: Optional nationality to use instead of random selection
    
    Returns:
        Dictionary with the new regen player data
    """
    # Use the global NATIONALITY_DATA and functions
    # Import the global functions to ensure consistency
    
    # Use the global generate_player_name function instead of duplicating logic
    # This ensures consistency and uses the correct 30% single-name probability
    
    def get_column_ranges():
        """Get min/max ranges for numerical columns from the database."""
        if not db_path:
            return {}
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Get column info
            cursor.execute("PRAGMA table_info(players)")
            columns = cursor.fetchall()
            
            ranges = {}
            for col in columns:
                col_name = col[1]
                col_type = col[2].upper()
                
                # Only check numerical columns
                if 'INTEGER' in col_type or 'REAL' in col_type:
                    try:
                        cursor.execute(f"SELECT MIN({col_name}), MAX({col_name}) FROM players WHERE {col_name} IS NOT NULL")
                        result = cursor.fetchone()
                        if result and result[0] is not None and result[1] is not None:
                            ranges[col_name] = (int(result[0]), int(result[1]))
                    except:
                        pass
            
            conn.close()
            return ranges
        except:
            return {}
    
    # Generate regen based on retiring player
    # Use override nationality if provided, otherwise use probabilistic selection (not inherited)
    if override_nationality and override_nationality in NATIONALITY_DATA:
        nationality = override_nationality
    else:
        # Always use probabilistic selection - do NOT inherit from retiring player
        nationality = select_nationality()
    
    # Use the global generate_player_name function (supports new structure with cropping)
    first_name, surname = generate_player_name(nationality)
    full_name = f"{first_name} {surname}".strip() if surname else first_name
    # Ensure full name doesn't exceed 15 characters (PES6 limit)
    full_name = crop_name(full_name, 15)
    
    # Shirt name: surname in uppercase (or first name if no surname)
    shirt_name = (surname.upper() if surname else first_name.upper())[:100]  # Crop to 100
    
    # Age: 16-18 for regens
    age = random.randint(16, 18)
    
    # Skin color from nationality (probabilistic)
    skin_color = select_skin_color(nationality)
    
    # Position: Keep the same as retiring player, UNLESS it's an Unused/Edited player
    position_mapping = get_position_name_mapping()
    
    # Check if this is an Unused/Edited player - randomize their position
    player_name = retired_player_data.get('player_name', '')
    if 'Unused' in player_name or 'Edited' in player_name:
        # Randomize position for Unused/Edited players to prevent position concentration
        # Valid positions: 0,2,3,4,5,6,7,8,9,10,11,12 (position 1 doesn't exist)
        valid_positions = [0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
        registered_position_num = random.choice(valid_positions)
        print(f"  🎲 Randomized position for {player_name}: {registered_position_num}")
    else:
        # Normal players keep their position
        registered_position_num = int(retired_player_data['registered_position'])  # Convert to int
    
    registered_position = position_mapping.get(registered_position_num, 'Center-Midfielder')
    
    contract_years = random.randint(3, 5)
    yearly_wage_rise = random.uniform(0.03, 0.10)
    
    # Generate development keys (mixed profiles 95% of the time)
    if random.random() < 0.95:
        # Mixed profile - select 3 random profiles
        profiles = list(range(10))  # 0-9
        selected_profiles = random.sample(profiles, 3)
        development_key = (selected_profiles[0] << 20) | (selected_profiles[1] << 10) | selected_profiles[2]
    else:
        # Pure profile
        development_key = random.randint(0, 9)
    
    # Trait key (0-3)
    trait_key = random.randint(0, 3)
    
    # Get realistic ranges from database
    column_ranges = get_column_ranges()
    
    # Generate Inner Strength Index (1-9) - determines base skill level
    # Most regens have average strength (around 4), only few have 8-9
    strength_weights = [0.05, 0.10, 0.15, 0.30, 0.20, 0.10, 0.05, 0.03, 0.02]  # 1-9
    inner_strength = random.choices(range(1, 10), weights=strength_weights)[0]
    
    # Get position averages from database
    position_averages = None
    if db_path:
        try:
            position_averages = get_cached_position_averages(db_path)
        except:
            print("Warning: Could not load position averages")
    
    # Skill attributes: position-aware generation using inner strength
    skill_attributes = {}
    skill_fields = [
        'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
        'response', 'agility', 'dribble_accuracy', 'dribble_speed',
        'short_pass_accuracy', 'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed',
        'shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy', 'swerve',
        'heading', 'jump', 'technique', 'aggression', 'mentality', 'goal_keeping',
        'team_work', 'consistency', 'condition_fitness'
    ]
    
    # Inner strength determines base range: 1=35-45, 4=40-55, 9=55-70
    base_min = 45 + (inner_strength - 1) * 2.5  # 35 to 55
    base_max = 55 + (inner_strength - 1) * 2.8  # 45 to 67.2
    
    spikes_generated = 0
    max_spikes = 10  # Allow up to 2 skill spikes per regen
    
    for skill in skill_fields:
        # Get positional average for this skill
        position_base = None
        if position_averages is not None and str(registered_position_num) in position_averages.index:
            if skill in position_averages.columns:
                position_base = position_averages.loc[str(registered_position_num), skill]
        
        if position_base is not None and not pd.isna(position_base):
            # Use position average as guidance
            if position_base > 70:  # High position average - potential for spikes
                skill_base = position_base * 0.6 + (inner_strength / 9) * 20  # Scale down but allow growth
                # 15% chance for exceptional spike for high positional skills
                if random.random() < 0.15 and spikes_generated < max_spikes and inner_strength >= 5:
                    skill_base = position_base * 0.85  # Close to position average
                    spikes_generated += 1
            elif position_base > 60:  # Medium-high position average
                skill_base = position_base * 0.65 + (inner_strength / 9) * 15
                # 10% chance for spike
                if random.random() < 0.10 and spikes_generated < max_spikes and inner_strength >= 6:
                    skill_base = position_base * 0.80
                    spikes_generated += 1
            else:
                # Normal position average
                skill_base = position_base * 0.7 + (inner_strength / 9) * 10
        else:
            # No position data - use inner strength base range
            skill_base = random.uniform(base_min, base_max)
        
        # Add small random variation
        variation = random.uniform(-3, 3)
        final_value = int(skill_base + variation)
        
        # Apply database constraints if available
        if skill in column_ranges:
            min_val, max_val = column_ranges[skill]
            final_value = max(min_val, min(max_val, final_value))
        else:
            final_value = max(1, min(99, final_value))
        
        # Special handling for condition_fitness (should be 3-8 random)
        if skill == 'condition_fitness':
            final_value = random.randint(3, 8)
        
        # Special handling for consistency (should be 3-8 random)
        if skill == 'consistency':
            final_value = random.randint(3, 8)
        
        skill_attributes[skill] = final_value
    
    # Calculate proper salary using the actual formula after skills are generated
    # Create a temporary player row for salary calculation
    temp_player_data = {
        'registered_position': registered_position_num,  # Use position number for salary calculation
        'age': age,
        **skill_attributes  # Include all the generated skills
    }
    
    # Convert to pandas Series for salary calculation
    player_row = pd.Series(temp_player_data)
    
    # Get position averages for salary calculation
    position_averages = None
    if db_path:
        try:
            position_averages = get_cached_position_averages(db_path)
        except:
            print("Warning: Could not load position averages for salary calculation")
    
    # Calculate base salary using the actual formula
    skill_columns = [
        'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
        'response', 'agility', 'dribble_accuracy', 'dribble_speed',
        'short_pass_accuracy', 'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed',
        'shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy', 'swerve',
        'heading', 'jump', 'technique', 'aggression', 'mentality', 'goal_keeping',
        'team_work', 'consistency', 'condition_fitness'
    ]
    
    binary_skills = ['gk', 'cwp', 'cbt', 'sb', 'dmf', 'wb', 'cmf', 'smf', 'amf', 'wf', 'ss', 'cf']
    
    base_salary = calculate_player_salary_base(player_row, position_averages, skill_columns, binary_skills)
    
    # Apply random adjustment to salary
    final_salary = apply_random_salary_adjustment(base_salary)
    
    # Log the salary calculation
    print(f"💰 Regen salary: Base={base_salary:,}€, Final={final_salary:,}€ (Inner Strength: {inner_strength})")
    
    
    # Positional ratings: binary (0 or 1) - only the main position gets 1
    positional_fields = ['gk', 'cwp', 'cbt', 'sb', 'dmf', 'wb', 'cmf', 'smf', 'amf', 'wf', 'ss', 'cf']
    positional_attributes = {}
    
    # Position mapping to determine which positional rating should be 1
    position_to_field = {
        '0': 'gk',    # Goalkeeper
        '2': 'cwp',   # Sweeper
        '3': 'cbt',   # Centre-Back
        '4': 'sb',    # Side-Back
        '5': 'dmf',   # Defensive Midfielder
        '6': 'wb',    # Wing-Back
        '7': 'cmf',   # Center-Midfielder
        '8': 'smf',   # Side-Midfielder
        '9': 'amf',   # Attacking Midfielder
        '10': 'wf',   # Winger
        '11': 'ss',   # Shadow Striker
        '12': 'cf',   # Striker
        '13': 'cf'    # Unknown -> Striker
    }
    
    main_position_field = position_to_field.get(str(registered_position_num), 'cf')
    
    for pos in positional_fields:
        if pos == main_position_field:
            positional_attributes[pos] = 1  # Can play this position
        else:
            positional_attributes[pos] = 0  # Cannot play this position
    
    # Add position column logic for CSV compatibility
    # Set the correct position column to 1 based on registered_position
    position_column_attributes = {}
    if registered_position_num == 0:
        position_column_attributes['GK  0'] = 1
    elif registered_position_num == 2:
        position_column_attributes['CWP  2'] = 1
    elif registered_position_num == 3:
        position_column_attributes['CBT  3'] = 1
    elif registered_position_num == 4:
        position_column_attributes['SB  4'] = 1
    elif registered_position_num == 5:
        position_column_attributes['DMF  5'] = 1
    elif registered_position_num == 6:
        position_column_attributes['WB  6'] = 1
    elif registered_position_num == 7:
        position_column_attributes['CMF  7'] = 1
    elif registered_position_num == 8:
        position_column_attributes['SMF  8'] = 1
    elif registered_position_num == 9:
        position_column_attributes['AMF  9'] = 1
    elif registered_position_num == 10:
        position_column_attributes['WF 10'] = 1
    elif registered_position_num == 11:
        position_column_attributes['SS  11'] = 1
    elif registered_position_num == 12:
        position_column_attributes['CF  12'] = 1
    
    # Special skills (binary skills): all start at 0 for regens
    # They will be developed during the development process based on seed or random chance
    special_fields = [
        'dribbling_skill', 'tactical_dribble', 'positioning', 'reaction', 'playmaking',
        'passing', 'scoring', 'one_one_scoring', 'post_player', 'lines', 'middle_shooting',
        'side', 'centre', 'penalties', 'one_touch_pass', 'outside', 'marking', 'sliding',
        'covering', 'd_line_control', 'penalty_stopper', 'one_on_one_stopper', 'long_throw'
    ]
    
    # All binary skills start at 0 - they will be developed during development process
    special_attributes = {skill: 0 for skill in special_fields}
    
    # Physical attributes: use realistic ranges with distribution
    physical_attributes = {}
    
    # Height: Normal distribution centered at 177cm, range 148-205cm
    # Use normal distribution (mean=177, std=12) to create bell curve with extremes possible
    height = int(np.random.normal(177, 12))
    
    # Clamp to realistic min/max
    height = max(148, min(205, height))
    
    # Apply position-based height boost for defensive positions (GK=0, CB=2, DMF=3, DM=5)
    # These positions benefit from extra height if they're below 180cm
    if registered_position_num in [0, 2, 3, 5] and height < 180:
        height_boost = random.randint(8, 15)
        height = min(205, height + height_boost)  # Still respect max limit
    
    physical_attributes['height'] = height
    
    # Weight: calculated from height with random variation
    # Formula: weight = height - 100 + random(-8, 8)
    weight = height - 100 + random.randint(-8, 8)
    
    # Ensure weight stays in reasonable bounds (50-120kg)
    weight = max(50, min(120, weight))
    
    physical_attributes['weight'] = weight
    
    # Physical appearance attributes: generate realistic values
    appearance_attributes = {}
    
    # Face and appearance settings
    appearance_attributes['face_type'] = random.randint(0, 2)  # 0-2
    
    # Preset face number depends on skin color (only use combinations that exist in original.sqlite IDs 1-4783)
    VALID_FACES_BY_SKIN = {
        1: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 34, 36, 37, 38, 40, 41, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 102, 104, 105, 106, 107, 108, 109, 110, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 123, 124, 125, 126, 129, 130, 131, 133, 134, 135, 136, 138, 139, 140, 141, 142, 143, 147, 148, 149, 150, 151, 152, 153, 154, 155, 156, 158, 159, 160, 161, 162, 163, 164, 167, 168, 169, 170, 171, 172, 174, 175, 176, 177, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187, 188, 190, 191, 193, 194, 196, 197, 198, 199, 200, 201, 203, 206, 207, 208, 212, 215, 219, 221, 222, 224, 225, 226, 228, 230, 235, 236, 239, 242, 246, 247, 249, 250, 251, 252, 255, 260, 263, 266, 268, 269, 274, 275, 278, 283, 288, 295, 296, 298, 301, 304, 305, 306, 308, 311, 313, 314, 315, 316, 317, 318, 319, 320, 321, 322, 323, 324, 325, 327, 328, 329, 330, 331, 332, 333, 334, 338, 340, 341, 342, 343, 345, 346, 350, 354, 356, 361],
        2: [1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 17, 18, 19, 21, 22, 23, 24, 25, 26, 27, 29, 30, 33, 34, 36, 39, 42, 43, 45, 48, 50, 51, 59, 69, 81, 82, 83, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 103, 104, 105, 107, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 126, 130, 148, 149, 152, 164, 168, 169, 171, 172],
        3: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 35, 36, 38, 39, 40, 41, 44, 45, 46, 48, 49, 50, 53, 54, 55, 58, 61, 63, 64, 66, 67, 68],
        4: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 17, 18, 19, 20, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 36, 37, 42, 43, 44, 47]
    }
    
    valid_faces = VALID_FACES_BY_SKIN.get(skin_color, VALID_FACES_BY_SKIN[1])  # Default to skin_color 1 if not found
    appearance_attributes['preset_face_number'] = random.choice(valid_faces)
    
    # Body measurements: realistic ranges for footballers (-7 to +7, but weighted toward 0)
    body_measurements = ['head_width', 'neck_length', 'neck_width', 'shoulder_height', 
                        'shoulder_width', 'chest_measurement', 'waist_circumference', 
                        'arm_circumference', 'leg_circumference', 'calf_circumference', 'leg_length']
    
    for measurement in body_measurements:
        # Weighted toward 0 (average) with some variation
        if random.random() < 0.7:  # 70% chance for average (0)
            appearance_attributes[measurement] = 0
        else:
            # 30% chance for variation (-3 to +3, mostly closer to 0)
            variation = random.choices([-3, -2, -1, 0, 1, 2, 3], weights=[1, 2, 3, 4, 3, 2, 1])[0]
            appearance_attributes[measurement] = variation
    
    # Equipment attributes
    equipment_attributes = {}
    
    # Wristband: 75% no wristband, 25% with wristband
    if random.random() < 0.25:
        wristband_colors = ['White', 'Red', 'Blue', 'Green', 'Black']
        equipment_attributes['wristband'] = random.choice(['L', 'R', 'B'])  # Left, Right, Both
        equipment_attributes['wristband_color'] = random.choice(wristband_colors)
    else:
        equipment_attributes['wristband'] = 'N'  # None
        equipment_attributes['wristband_color'] = 'None'
    
    # Numbers: realistic ranges
    equipment_attributes['international_number'] = random.randint(0, 44)  # 0-44
    equipment_attributes['classic_number'] = random.randint(0, 23)  # 0-23
    equipment_attributes['club_number'] = random.randint(0, 99)  # 0-99
    
    # Style attributes
    style_attributes = {}
    
    # Dribble style: 1-4, weighted toward basic styles
    style_attributes['dribble_style'] = random.choices([1, 2, 3, 4], weights=[40, 30, 20, 10])[0]
    
    # Free kick style: 1-10, weighted toward basic styles
    style_attributes['free_kick_style'] = random.choices(range(1, 11), weights=[25, 20, 15, 10, 8, 6, 5, 4, 3, 2])[0]
    
    # PK style: 1-5, weighted toward basic styles
    style_attributes['pk_style'] = random.choices([1, 2, 3, 4, 5], weights=[40, 30, 20, 8, 2])[0]
    
    # Drop kick style: 1-4, weighted toward basic styles
    style_attributes['drop_kick_style'] = random.choices([1, 2, 3, 4], weights=[50, 30, 15, 5])[0]
    
    # Injury tolerance: mostly A (high), some B (medium), rarely C (low)
    style_attributes['injury_tolerance'] = random.choices(['A', 'B', 'C'], weights=[70, 25, 5])[0]
    
    # Calculate bundled skill ratings from individual skills
    bundled_ratings = calculate_bundled_skill_ratings(skill_attributes)
    
    # Create the complete regen data
    regen_data = {
        'player_name': full_name,
        'shirt_name': shirt_name,
        'age': age,
        'nationality': nationality,
        'skin_color': skin_color,
        'strong_foot': random.choices(['R', 'L'], weights=[0.80, 0.20])[0],  # 80% Right, 20% Left
        'favoured_side': random.choice(['R', 'L']),
        'registered_position': int(registered_position_num),  # Store position number as integer
        'game_position': registered_position,  # Store position name
        'club_id': retired_player_data['club_id'],
        'salary': final_salary,
        'contract_years_remaining': contract_years,
        'market_value': 0,  # Will be calculated
        'yearly_wage_rise': yearly_wage_rise,
        'development_key': development_key,
        'trait_key': trait_key,
        'inner_strength': inner_strength,  # Store inner_strength for modify_regen_with_base_player
        'games_played': 0,
        'goals': 0,
        'assists': 0,
        'international_caps_total': 0,
        'international_goals': 0,
        'international_assists': 0,
        'current_season_caps': 0,
        **skill_attributes,
        **positional_attributes,
        **special_attributes,
        **physical_attributes,
        **appearance_attributes,
        **equipment_attributes,
        **style_attributes,
        **bundled_ratings
    }
    
    # Modify regen_data using base player from original.sqlite
    regen_data = modify_regen_with_base_player(regen_data, db_path)
    
    return regen_data

def assign_regen_face(player_id: int, skin_color: int, app_root: str = None) -> Optional[str]:
    """
    Pick a random face from the regen_faces folder based on skin_color,
    move it to player_images, and return the filename.
    
    Args:
        player_id: The ID of the player to assign the face to
        skin_color: The skin color (1-4) to select from appropriate folder
        app_root: Root path of the application (defaults to current directory)
    
    Returns:
        The filename of the assigned image (e.g., 'player_123.png'), or None if no face available
    """
    if app_root is None:
        app_root = os.path.dirname(os.path.abspath(__file__))
    
    # Ensure skin_color is in valid range (1-4)
    if not (1 <= skin_color <= 4):
        skin_color = 1  # Default to skin_1 if invalid
    
    # Paths
    regen_faces_folder = os.path.join(app_root, 'static', 'regen_faces', f'skin_{skin_color}')
    player_images_folder = os.path.join(app_root, 'static', 'player_images')
    
    # Create player_images folder if it doesn't exist
    os.makedirs(player_images_folder, exist_ok=True)
    
    # Check if regen_faces folder exists and has PNG files
    if not os.path.exists(regen_faces_folder):
        print(f"  ⚠️  Regen faces folder not found: {regen_faces_folder}")
        return None
    
    # Get all PNG files from the skin color folder
    png_files = [f for f in os.listdir(regen_faces_folder) if f.lower().endswith('.png')]
    
    if not png_files:
        print(f"  ⚠️  No PNG files found in {regen_faces_folder}")
        return None
    
    # Pick a random PNG file
    selected_file = random.choice(png_files)
    source_path = os.path.join(regen_faces_folder, selected_file)
    
    # Destination filename: player_{player_id}.png
    destination_filename = f'player_{player_id}.png'
    destination_path = os.path.join(player_images_folder, destination_filename)
    
    # Delete old image if it exists (to replace with new regen face)
    if os.path.exists(destination_path):
        try:
            os.remove(destination_path)
            print(f"  🗑️  Deleted old profile image for player {player_id}")
        except Exception as delete_error:
            print(f"  ⚠️  Could not delete old image: {delete_error}")
    
    try:
        # Resize image to 250x250 before moving
        try:
            from PIL import Image
            img = Image.open(source_path)
            # Resize to 250x250 with high-quality resampling
            img = img.resize((250, 250), Image.Resampling.LANCZOS)
            # Convert to RGB if necessary (for formats like PNG with transparency)
            if img.mode in ('RGBA', 'LA', 'P'):
                # Create a white background
                background = Image.new('RGB', (250, 250), (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            # Save as PNG at destination
            img.save(destination_path, 'PNG', quality=95)
            # Remove original file from regen_faces
            os.remove(source_path)
            print(f"  ✅ Assigned face {selected_file} to player {player_id} (resized to 250x250 and moved to {destination_filename})")
        except ImportError:
            # If PIL is not available, just move the file
            shutil.move(source_path, destination_path)
            print(f"  ✅ Assigned face {selected_file} to player {player_id} (moved to {destination_filename}, PIL not available for resizing)")
        except Exception as resize_error:
            # If resizing fails, just move the file
            shutil.move(source_path, destination_path)
            print(f"  ⚠️  Assigned face {selected_file} to player {player_id} (moved without resizing: {resize_error})")
        
        return destination_filename
    except Exception as e:
        print(f"  ❌ Error processing face file: {e}")
        return None

def generate_players_for_team(team_id: int, num_players: int = 1) -> List[Dict]:
    """Generate multiple new players for a team."""
    players = []
    for _ in range(num_players):
        player = generate_new_player(team_id)
        players.append(player)
    return players

def insert_new_player_to_database(db_path: str, player_data: Dict) -> int:
    """Insert a new player into the database and return the player ID."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Prepare the SQL insert statement
        columns = list(player_data.keys())
        placeholders = ', '.join(['?' for _ in columns])
        column_names = ', '.join(columns)
        
        sql = f"INSERT INTO players ({column_names}) VALUES ({placeholders})"
        values = tuple(player_data.values())
        
        cursor.execute(sql, values)
        player_id = cursor.lastrowid
        
        conn.commit()
        return player_id
        
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def replace_retired_players(db_path: str, num_players: int = 10) -> Dict:
    """Replace retired players with new generated players."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Get teams that need players (CPU teams and user teams)
        cursor.execute("""
            SELECT DISTINCT t.id, t.club_name, lt.user_id
            FROM teams t
            JOIN league_teams lt ON t.club_name = lt.team_name
            ORDER BY RANDOM()
        """)
        teams = cursor.fetchall()
        
        if not teams:
            return {'error': 'No teams found'}
        
        players_generated = 0
        teams_updated = []
        
        for i in range(num_players):
            # Select a team (round-robin if more players than teams)
            team = teams[i % len(teams)]
            team_id = team[0]
            team_name = team[1]
            user_id = team[2]
            
            # Generate a new player
            player_data = generate_new_player(team_id, db_path=db_path)
            
            # Insert into database
            player_id = insert_new_player_to_database(db_path, player_data)
            
            players_generated += 1
            teams_updated.append(team_name)
            
            print(f"  ✅ Generated {player_data['player_name']} ({player_data['nationality']}, {player_data['age']}yo) for {team_name}")
        
        conn.close()
        
        return {
            'players_generated': players_generated,
            'teams_updated': list(set(teams_updated)),
            'success': True
        }
        
    except Exception as e:
        conn.close()
        return {'error': str(e)}

def calculate_player_career_stats(cursor, player_id: int) -> Dict:
    """
    Calculate comprehensive career statistics for a retiring player.
    
    Args:
        cursor: Database cursor
        player_id: ID of the player
    
    Returns:
        Dictionary with career statistics
    """
    try:
        # Get current season stats (from player table)
        cursor.execute("""
            SELECT games_played, goals, assists, MVP, salary, market_value
            FROM players WHERE id = ?
        """, (player_id,))
        current_stats = cursor.fetchone()
        
        current_games = current_stats[0] if current_stats and current_stats[0] else 0
        current_goals = current_stats[1] if current_stats and current_stats[1] else 0
        current_assists = current_stats[2] if current_stats and current_stats[2] else 0
        current_salary = current_stats[3] if current_stats and current_stats[3] else 0
        
        # Get historical stats from player_performance table
        cursor.execute("""
            SELECT SUM(matches_played), SUM(goals), SUM(assists), COUNT(DISTINCT season)
            FROM player_performance WHERE player_id = ?
        """, (player_id,))
        historical_stats = cursor.fetchone()
        
        historical_games = historical_stats[0] if historical_stats and historical_stats[0] else 0
        historical_goals = historical_stats[1] if historical_stats and historical_stats[1] else 0
        historical_assists = historical_stats[2] if historical_stats and historical_stats[2] else 0
        seasons_in_history = historical_stats[3] if historical_stats and historical_stats[3] else 0
        
        # Calculate total career stats
        total_games = current_games + historical_games
        total_goals = current_goals + historical_goals
        total_assists = current_assists + historical_assists
        
        # Get career earnings from database (updated by end-of-season process)
        cursor.execute("SELECT career_earnings FROM players WHERE id = ?", (player_id,))
        career_earnings_result = cursor.fetchone()
        career_earnings = career_earnings_result[0] if career_earnings_result and career_earnings_result[0] else 0
        
        return {
            'total_games': total_games,
            'total_goals': total_goals,
            'total_assists': total_assists,
            'career_earnings': career_earnings,
            'seasons_played': seasons_in_history + 1  # +1 for current season
        }
        
    except Exception as e:
        print(f"Error calculating career stats for player {player_id}: {e}")
        return {
            'total_games': 0,
            'total_goals': 0,
            'total_assists': 0,
            'career_earnings': 0,
            'seasons_played': 1
        }

def process_player_retirements_and_replacements(db_path: str) -> Dict:
    """
    Process player retirements and replace retired players with new young players.
    
    Args:
        db_path: Path to the database
    
    Returns:
        Dictionary with retirement and replacement results
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Get all players aged 30+ for retirement checking
        cursor.execute("""
            SELECT id, player_name, age, registered_position, salary, club_id, nationality, contract_years_remaining, games_played
            FROM players 
            WHERE age >= 30
            ORDER BY age DESC
        """)
        
        players_to_check = cursor.fetchall()
        retired_players = []
        continuing_players = []
        
        print(f"  📊 Checking {len(players_to_check)} players (aged 30+) for retirement...")
        
        # Check each player for retirement
        for player in players_to_check:
            player_data = {
                'id': player[0],
                'player_name': player[1],
                'age': player[2],
                'registered_position': player[3],
                'salary': player[4],
                'club_id': player[5],
                'nationality': player[6],
                'contract_years_remaining': player[7],
                'games_played': player[8]
            }
            
            # Normal retirement check for age-based retirements
            retirement_check = check_player_retirement(player_data)
            
            if retirement_check['wants_to_retire']:
                retired_players.append({
                    'id': player[0],
                    'player_name': player[1],
                    'age': player[2],
                    'registered_position': player[3],
                    'club_id': player[5],
                    'reason': retirement_check['reason']
                })
            else:
                continuing_players.append(player_data['player_name'])
        
        # Note: Hall of Fame population is now handled in app.py end-of-season process
        # to ensure it happens right before players are replaced with regens
        
        # Now generate proper regens for retired players
        regens_generated = 0
        teams_updated = []
        
        print(f"  👶 Generating {len(retired_players)} regens for retired players...")
        
        for retired_player in retired_players:
            try:
                # Get full retired player data for regen generation
                cursor.execute("""
                    SELECT * FROM players WHERE id = ?
                """, (retired_player['id'],))
                
                full_retired_data = cursor.fetchone()
                if full_retired_data:
                    # Convert to dictionary
                    column_names = [description[0] for description in cursor.description]
                    retired_player_dict = dict(zip(column_names, full_retired_data))
                    
                    # Generate proper regen
                    regen_data = generate_proper_regen(retired_player_dict, db_path)
                    
                    # Insert regen into database
                    regen_id = insert_new_player_to_database(db_path, regen_data)
                    regens_generated += 1
                    
                    # Track team
                    cursor.execute("SELECT club_name FROM teams WHERE id = ?", (regen_data['club_id'],))
                    team_result = cursor.fetchone()
                    if team_result:
                        teams_updated.append(team_result[0])
                    
                    print(f"    ✅ Generated regen {regen_data['player_name']} (pos: {regen_data['registered_position']}) for retired {retired_player['player_name']}")
                    
            except Exception as e:
                print(f"    ❌ Failed to generate regen for {retired_player['player_name']}: {e}")
                continue
        
        conn.close()
        
        return {
            'retired_players': retired_players,
            'continuing_players': continuing_players,
            'replacements_generated': regens_generated,
            'teams_updated': list(set(teams_updated)),
            'success': True
        }
        
    except Exception as e:
        conn.close()
        return {'error': str(e)} 

def recalculate_free_agent_salaries(db_path: str) -> Dict:
    """Recalculate salaries for all free agents (club_id = 141) using proper salary calculation.
    Excludes draftees (draftee = 1)."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Get all free agents (No Club players), excluding draftees
        cursor.execute("""
            SELECT * FROM players 
            WHERE club_id = 141
            AND (draftee IS NULL OR draftee = 0)
        """)
        
        free_agents = cursor.fetchall()
        if not free_agents:
            conn.close()
            return {'free_agents_updated': 0, 'success': True, 'message': 'No free agents found'}
        
        print(f"  💰 Recalculating salaries for {len(free_agents)} free agents...")
        
        # Get column names for DataFrame conversion
        column_names = [description[0] for description in cursor.description]
        
        # Convert to DataFrame for salary calculation
        import pandas as pd
        df = pd.DataFrame(free_agents, columns=column_names)
        
        # Get position averages for salary calculation
        try:
            pos_avg_df = get_cached_position_averages(db_path)
        except Exception as e:
            print(f"Warning: Could not load position averages for salary calculation: {e}")
            pos_avg_df = None
            
        if pos_avg_df is None:
            conn.close()
            return {'error': 'Could not load position averages for salary calculation'}
        
        # Define skill columns (same as in salary calculation)
        skill_columns = [
            'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
            'response', 'agility', 'dribble_accuracy', 'dribble_speed', 'short_pass_accuracy',
            'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed', 'shot_accuracy',
            'shot_power', 'shot_technique', 'free_kick_accuracy', 'swerve', 'heading',
            'jump', 'technique', 'aggression', 'mentality', 'goal_keeping', 'team_work',
            'consistency', 'condition_fitness'
        ]
        
        binary_skills = ['gk', 'cwp', 'cbt', 'sb', 'dmf', 'wb', 'cmf', 'smf', 'amf', 'wf', 'ss', 'cf']
        
        updated_count = 0
        
        # Process each free agent
        for idx, player_row in df.iterrows():
            try:
                # Calculate new salary (includes all position-specific boosts and compression)
                # Position boosts (GK_POSITION_BOOST, DEF_POSITION_BOOST, SB_POSITION_BOOST) and
                # compression are already applied inside calculate_player_salary_base
                new_salary = calculate_player_salary_base(player_row, pos_avg_df, skill_columns, binary_skills)
                
                # Update salary and set market_value to zero for free agents
                cursor.execute("""
                    UPDATE players 
                    SET salary = ?, market_value = 0 
                    WHERE id = ?
                """, (new_salary, player_row['id']))
                
                updated_count += 1
                
                if updated_count <= 5:  # Show first 5 examples
                    old_salary = player_row['salary']
                    print(f"    ✅ {player_row['player_name']}: €{old_salary:,} → €{new_salary:,}")
                    
            except Exception as e:
                print(f"    ❌ Failed to update salary for {player_row['player_name']}: {e}")
                continue
        
        conn.commit()
        conn.close()
        
        print(f"  ✅ Updated salaries for {updated_count}/{len(free_agents)} free agents")
        
        return {
            'free_agents_updated': updated_count,
            'total_free_agents': len(free_agents),
            'success': True
        }
        
    except Exception as e:
        conn.close()
        return {'error': str(e)}

def generate_new_player(team_id: int, position: str = None, db_path: str = None) -> Dict:
    """Generate a complete new player for a team."""
    # Generate age (16-18 for new players)
    age = random.randint(16, 18)
    
    # Select position if not provided
    if not position:
        positions = ['GK', 'CB', 'SB', 'DMF', 'CMF', 'SMF', 'AMF', 'WF', 'SS', 'CF']
        position = random.choice(positions)
    
    # Generate nationality and name
    nationality = select_nationality()
    first_name, surname = generate_player_name(nationality)
    full_name = f"{first_name} {surname}".strip() if surname else (first_name if first_name else surname)
    # Ensure full name doesn't exceed 15 characters (PES6 limit)
    full_name = crop_name(full_name, 15)
    
    # Get skin color from nationality (probabilistic)
    skin_color = select_skin_color(nationality)
    
    # Generate attributes using position averages
    attributes = generate_player_attributes(age, position, db_path)
    
    # Generate financial data (lower for young players)
    base_salary = random.randint(30000, 120000)  # €30k-€120k for young players
    contract_years = random.randint(3, 5)  # 3-5 year contracts
    yearly_wage_rise = random.uniform(0.03, 0.10)  # 3-10% yearly rise (higher potential)
    
    # Generate development keys
    profile_key, trait_key = generate_complete_development_key()
    
    # Create player data
    player_data = {
        'player_name': full_name,
        'age': age,
        'nationality': nationality,
        'skin_color': skin_color,
        'strong_foot': random.choices(['R', 'L'], weights=[0.80, 0.20])[0],  # 80% Right, 20% Left
        'favoured_side': random.choice(['R', 'L']),
        'registered_position': position,
        'club_id': team_id,
        'salary': base_salary,
        'contract_years_remaining': contract_years,
        'yearly_wage_rise': yearly_wage_rise,
        'development_key': profile_key,
        'trait_key': trait_key,
        'games_played': 0,
        'goals': 0,
        'assists': 0,
        'international_caps_total': 0,
        'international_goals': 0,
        'international_assists': 0,
        'current_season_caps': 0,
        **attributes
    }
    
    return player_data
