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
    performance_boost = calculate_performance_boost(player_data)
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
                        # Already above seed target: make further growth increasingly harder
                        over_seed = -delta_to_target  # positive amount over target
                        # Soft zone: allow small drift above seed before penalty ramps
                        effective_over = max(0.0, over_seed - 2.0)
                        # Penalty factor grows with over_seed; keeps tiny chance of improvement (with floor)
                        penalty = max(0.12, 1.0 / (1.0 + 1.05 * effective_over))
                        # Retain some room to 99 but heavily penalized above seed
                        remaining_potential = max(0.0, (99 - current_value) * penalty)
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

            # Seed nudge: small push towards seed target on improvement years
            if seed_targets and final_multiplier > 0 and skill in seed_targets and seed_targets[skill] is not None:
                target = int(seed_targets[skill])
                gap = target - current_value
                if gap != 0:
                    # ε scaled by importance with curvature, still bounded to avoid jumps (stronger)
                    epsilon = 0.45  # stronger nudge per season baseline
                    nudge = epsilon * (max(0.5, skill_weight) ** 1.5)
                    # Move at most nudge toward the target; don't overshoot
                    if gap > 0:
                        skill_change += min(nudge, gap)
                    else:
                        # If already above seed, do not apply downward nudge
                        pass
            
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
        'mixed_weights': dev_info.get('weights', []) if dev_info.get('is_mixed', False) else None
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

def calculate_performance_boost(player_data: dict) -> dict:
    """
    Calculate performance-based development boost.
    
    Args:
        player_data: Player data dictionary
    
    Returns:
        Dictionary with performance boosts
    """
    games_played = player_data.get('games_played', 0)
    goals = player_data.get('goals', 0)
    assists = player_data.get('assists', 0)
    
    # Base boosts
    games_boost = min(0.5, games_played * 0.02)  # Max 0.5 boost from games
    goals_boost = min(0.8, goals * 0.1)  # Max 0.8 boost from goals
    assists_boost = min(0.6, assists * 0.08)  # Max 0.6 boost from assists
    
    # Additional random factor for performance
    performance_random = random.uniform(0.8, 1.2)
    
    return {
        'games_boost': games_boost * performance_random,
        'goals_boost': goals_boost * performance_random,
        'assists_boost': assists_boost * performance_random,
        'total_boost': (games_boost + goals_boost + assists_boost) * performance_random
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
    if contract_years_remaining >= 1:
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
    
    # Calculate base salary (before random adjustments)
    base_salary = calculate_player_salary_base(player_row, pos_avg_df, skill_columns, binary_skills)
    
    # Apply 30% boost for defensive positions (GK=0, CB=2, DMF=3, FB=4)
    registered_position = player_data.get('registered_position')
    try:
        # Handle both string and integer formats, strip whitespace if string
        if isinstance(registered_position, str):
            pos_int = int(registered_position.strip())
        elif isinstance(registered_position, (int, float)):
            pos_int = int(registered_position)
        else:
            pos_int = -1
        
        if pos_int in [0, 2, 3, 4]:
            base_salary = int(base_salary * 1.75)
    except (ValueError, TypeError) as e:
        # Keep base_salary as-is if position is invalid
        pass
    
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
NATIONALITY_DATA = {
    'Brazil': {'skin_color': 3, 'weight': 0.10, 'names': ['Joelinton','Beto','Aloisio','Evandro','Didinho','Alan','Jair','Preto','Rato','Dudu','Junior','Zelito','Zeca','Thiago','Edilson','Wallyson','Gedson','Sonny','Sidney','Paulinho']},
    'Argentina': {'skin_color': 1, 'weight': 0.07, 'names': ['Javier','Sergio','Enzo','Nicolas','Franco','Ezequiel','Alejandro','Facundo','Lisandro','Luzo','Agustin','Maxi','Sebastian','Osvaldo','Ramon','Hector','Diego','Esteban','Pablo','Nando']},
    'Spain': {'skin_color': 1, 'weight': 0.05, 'names': ['Roberto','Iker','Andres','Xavier','Gerard','Chico','Carles','Juanito','Michel','Victor','Julen','Pipi','Dani','Lobo','Antonio','Santi','Raul','Pico','Ferran','Nacho']},
    'France': {'skin_color': 1, 'weight': 0.04, 'names': ['Antoine','Robert','Olivier','Marcel','Didier','Claude','Fabien','Pierre','Raymond','Raphael','Aurelie','Edouard','Kyllian','Jeremy','Dominique','Florent','Bernard','Samir','Andreu','Djibril']},
    'England': {'skin_color': 1, 'weight': 0.03, 'names': ['Bobby','Wayne','Frank','Joseph','John','Harry','Phil','Gary','Kyle','Jordan','Peter','James','Joe','Andy', 'Michael','Steve','Richard','William','Charles','Winston']},
    'Germany': {'skin_color': 1, 'weight': 0.03, 'names': ['Philip','Franz','Adolf','Bastian','Jurgen','Fritz','Andrea','Felix','Thomas','Karl','Bernard','Stefan','Marcus','Mario','Max','Robin','Deniz','Julian','Heinz','Lukas']},
    'Italy': {'skin_color': 1, 'weight': 0.03, 'names': ['Vito','Carlo','Fredo','Salvatore','Bruno','Amerigo','Tomaso','Francesco','Giorgino','Fabrizio','Benito','Gianluigi','Gianluca','Giuseppe','Leonardo','Filippo','Gennaro','Luigi','Vincenzo','Riccardo']},
    'Portugal': {'skin_color': 1, 'weight': 0.03, 'names': ['Zequinha','Tiago','Bruno','Litos','Josue','Nelson','Anibal','Pedrinho','Fábio','Quim','Luciano','Jota','Ricardinho','Nandinho','Joca','Titinho','David','Nuno','Diogo','Filipe']},
    'Netherlands': {'skin_color': 1, 'weight': 0.03, 'names': ['Jan','Jaap','Frank','Memphis','Virgil','Clarence','Wesley','Edwin','Dennis','Ruud','Luuk','Justin','Kevin','Jetro','Maarten','Ronald','Robin','Arjen','Dick','Roy']},
    'Belgium': {'skin_color': 1, 'weight': 0.03, 'names': ['Vincent','Thibaut','Wilfried','Fernand','Dries','Divock','Timothy','Jeremy','Emile','Silvio','Matz','Simon','Jean','Claude','Sven','Maxim','Filip','Arthur','Charles','Luc']},
    'Croatia': {'skin_color': 1, 'weight': 0.03, 'names': ['Luka','Ivan','Dejan','Andrej','Marko','Ante','Josko','Igor','Mila','Nikola']},
    'Serbia': {'skin_color': 1, 'weight': 0.03, 'names': ['Milic','Srdjan','Milos','Ludovic','Nikola','Lukic','Savo','Alek','Lazar','Josevic']},
    'Poland': {'skin_color': 1, 'weight': 0.03, 'names': ['Henryk','Pawel','Lukas','Tomasz','Jakub','Marek','Jerzy','Gregor','Euzebiusz','Karol']},
    'Ukraine': {'skin_color': 1, 'weight': 0.03, 'names': ['Valdomir','Andrey','Artem','Dmytro','Viktor','Vitaliy','Mykola','Roman','Yuri','Vasyl']},
    'Russia': {'skin_color': 1, 'weight': 0.03, 'names': ['Lev','Igor','Vladimir','Yuri','Sergey','Dmitri','Denis','Roman','Aleksei','Marat','Ivan']},
    'Turkey': {'skin_color': 3, 'weight': 0.03, 'names': ['Hakan','Arda','Hasan','Ozan','Volkan','Fatih','Hamit','Kazim','Sabri','Gokhan']},
    'Morocco': {'skin_color': 3, 'weight': 0.03, 'names': ['Hakim','Nassir','Youssef','Brahim','Omar','Yassine','Younes','Adel','Medhi','Marrouane']},
    'Algeria': {'skin_color': 3, 'weight': 0.03, 'names': ['Yacine','Nabil','Rabah','Islam','Mehdi','Zinedine','Oussama','Youcef','Ismael','Karim']},
    'Senegal': {'skin_color': 4, 'weight': 0.03, 'names': ['Lamine','Pape','Papiss','Issa','Idrissa','Saido','Moussa','Demba','Salif','Fode']},
    'Nigeria': {'skin_color': 4, 'weight': 0.03, 'names': ['John','Joseph','Kalu','Ola','Sanusi','Haruna','Julius','Ideye','Tony','Sam']},
    'Ghana': {'skin_color': 4, 'weight': 0.03, 'names': ['Samuel','Thomas','Jeffrey','Tony','Michael','Asamoah','Jordan','Raphael','Christian','Eric']},
    'Ivory Coast': {'skin_color': 4, 'weight': 0.03, 'names': ['Yaya','Didier','Emmanuel','Bakari','Seydou','Sylvain','Siaka','Patrice','Lassina','Wilfried']},
    'Cameroon': {'skin_color': 4, 'weight': 0.03, 'names': ['Roger','Samuel','Lauren','Lucien','Stephane','Joel','Vincent','Benjamim','Fabrice','Pierre']},
    'Egypt': {'skin_color': 3, 'weight': 0.03, 'names': ['Mohamed','Ahmed','Hossan','Yasser','Ismail','Mustafa','Omar','Saleh','Mokthar','Ibrahim']},
    'Tunisia': {'skin_color': 3, 'weight': 0.02, 'names': ['Youssef','Hatem','Riad','Nabil','Oussef','Karim','Nizar','Ali','Sofie','Ziad']},
    'South Africa': {'skin_color': 4, 'weight': 0.02, 'names': ['Bennedict','Quinton','Phil','Aaron','John','Andre','Steven','Eric','David','Manuel']},
    'Japan': {'skin_color': 3, 'weight': 0.02, 'names': ['Keisuke','Hidetoshi','Sakura','Ryo','Genzo','Ozora','Akira','Hikaro', 'Sheinsuke','Takeshi']},
    'South Korea': {'skin_color': 3, 'weight': 0.02, 'names': ['Son','Sung','Young','Lee','Heung','Ping','Pee','Jing','Din','Sun']},
    'China': {'skin_color': 2, 'weight': 0.02, 'names': ['Wu', 'Zhang', 'Li', 'Wang', 'Chen', 'Liu', 'Yang', 'Huang', 'Zhao', 'Zhou', 'An', 'Bao', 'Dong', 'En', 'Feng', 'Gang', 'Hao', 'In', 'Jian']},
    'Australia': {'skin_color': 1, 'weight': 0.02, 'names': ['John','Tim', 'Robert','Hugh','Lauren','Joe','Aaron','Harry','Craig','Mark','Sam']},
    'USA': {'skin_color': 1, 'weight': 0.03, 'names': ['Kevin','Lebron','Barrack','Denzel','Michael','Donald','Geogre','Vince','Cody', 'Randy']},
    'Mexico': {'skin_color': 3, 'weight': 0.03, 'names': ['Javier','Roberto','Rafael','Gepeto','Jorge','Kinkin','Luis','Ramon','Octavio','Gonzalo']},
    'Colombia': {'skin_color': 3, 'weight': 0.03, 'names': ['Tolo','Hernan', 'Faustino','Carlitos','Radamel','Andres','Rubio','Jackson','Manel','Panzo']},
    'Chile': {'skin_color': 3, 'weight': 0.02, 'names': ['Arturo', 'Alexis', 'Eduardo','Claudio', 'Jorge', 'Mauricio', 'Matías', 'Alejandro', 'Diego']},
    'Uruguay': {'skin_color': 1, 'weight': 0.02, 'names': ['Luis', 'Edinson', 'Diego', 'Maxi', 'Álvaro', 'Sebastián', 'Romero','Armando','Miguel','Gonzalo']},
    'Paraguay': {'skin_color': 3, 'weight': 0.02, 'names': ['Roque', 'Nelson', 'Oscar', 'Cristian', 'Edgar', 'Julio', 'Dario', 'Lucas', 'Antonio', 'Carlos']},
    'Peru': {'skin_color': 3, 'weight': 0.02, 'names': ['Paolo', 'Jefferson', 'André', 'Christian', 'Yoshimar', 'Renato', 'Luis', 'Carlos', 'Miguel', 'Raúl']},
    'Ecuador': {'skin_color': 3, 'weight': 0.02, 'names': ['Antonio', 'Enner', 'Felipe', 'Michael', 'Christian', 'Renato', 'Carlos', 'Gabriel', 'Walter', 'Benito']},
    'Venezuela': {'skin_color': 3, 'weight': 0.02, 'names': ['Salomón', 'Rómulo', 'Fernando', 'Carlos', 'Roberto', 'José', 'Manuel', 'Eduardo', 'Gabriel', 'Héctor']},
    'Canada': {'skin_color': 1, 'weight': 0.02, 'names': ['Mitch', 'Alphonso', 'Jonathan','Scott', 'Samuel', 'Mark', 'Russell', 'Blake', 'Declan', 'Ethan']},
    
    # Additional countries from database
    'Austria': {'skin_color': 1, 'weight': 0.02, 'names': ['Adolf','Jurgen','Heinrich','Michael','George','Manuel','Lukas','Angel','Markus','Julian']},
    'Switzerland': {'skin_color': 1, 'weight': 0.02, 'names': ['Lionel','Granit','Henrique','Michel','Jean','Diego','Lukas','Patrick','Markus','Julles']},
    'Sweden': {'skin_color': 1, 'weight': 0.02, 'names': ['Viktor','Henrik','Andreas','Olaf','Merk','Isak','Manuel','Fredrik','Joseph','Max']},
    'Norway': {'skin_color': 1, 'weight': 0.02, 'names': ['Viktor','Henrik','John','Olef','Erling','Alexander','Gustav','Fredrik','Puntus','Max']},
    'Denmark': {'skin_color': 1, 'weight': 0.02, 'names': ['Viktor','Henrik','Christian','Rasmus','Peter','Hugh','Greg','Fredrik','Leonel','Dedrik']},
    'Finland': {'skin_color': 1, 'weight': 0.02, 'names': ['Viktor','Henrik','Jared','Olav','Peter','Mika','Jasper','Fredrik','Thor','Lukas']},
    'Iceland': {'skin_color': 1, 'weight': 0.02, 'names': ['Viktor','Henrik','Gylfi','Bjorn','Herman','Johan','Jasper','Fredrik','Alfred','Lukas']},
    'Ireland': {'skin_color': 1, 'weight': 0.02, 'names': ['Henry','Josh','George','Mark','Alfred','Bob','Gareth','Louis','Keith','Steven']},
    'Scotland': {'skin_color': 1, 'weight': 0.01, 'names': ['Henry','Josh','George','Mark','Alfred','Bob','Gareth','Louis','Keith','Steven']},
    'Wales': {'skin_color': 1, 'weight': 0.01, 'names': ['Henry','Josh','George','Mark','Alfred','Bob','Gareth','Louis','Keith','Steven']},
    'Northern Ireland': {'skin_color': 1, 'weight': 0.01, 'names': ['Henry','Josh','George','Mark','Alfred','Bob','Gareth','Louis','Keith','Steven']},
    
    # Additional missing countries from database
    'Albania': {'skin_color': 1, 'weight': 0.005, 'names': ['Abazi', 'Xerdan', 'Granit', 'Endrit', 'Kavor', 'Lorik', 'Luka', 'Semir', 'Jeton', 'Kastriot']},
    'Angola': {'skin_color': 4, 'weight': 0.005, 'names': ['Jorginho', 'Bruno', 'Carlos', 'Domingos', 'Manel', 'Fernando', 'Gilberto', 'Leao', 'Ivan', 'João']},
    'Armenia': {'skin_color': 1, 'weight': 0.005, 'names': ['Arman', 'David', 'Gor', 'Hayk', 'Karen', 'Levon', 'Mher', 'Narek', 'Ruben', 'Sargis']},
    'Belarus': {'skin_color': 1, 'weight': 0.005, 'names': ['Aliaksandr', 'Dzmitry', 'Ihar', 'Kanstantsin', 'Maksim', 'Pavel', 'Siarhei', 'Uladzimir', 'Vitali', 'Yury']},
    'Benin': {'skin_color': 4, 'weight': 0.005, 'names': ['Abel', 'Benoît', 'Célestin', 'Désiré', 'Emmanuel', 'Félix', 'Gabriel', 'Henri', 'Ignace', 'Jean']},
    'Bolivia': {'skin_color': 3, 'weight': 0.005, 'names': ['Carlos', 'Diego', 'Eduardo', 'Fernando', 'Gabriel', 'Hugo', 'Iván', 'Jorge', 'Luis', 'Miguel']},
    'Bosnia and Herzegovina': {'skin_color': 1, 'weight': 0.005, 'names': ['Adnan', 'Benjamin', 'Srdjan', 'Emir', 'Faruk', 'Goran', 'Haris', 'Ivan', 'Jasmin', 'Kenan']},
    'Bulgaria': {'skin_color': 1, 'weight': 0.005, 'names': ['Aleksandar', 'Boris', 'Dimitar', 'Emil', 'Georgi', 'Hristo', 'Ivan', 'Jordan', 'Krasimir', 'Lyubomir']},
    'Burkina Faso': {'skin_color': 4, 'weight': 0.005, 'names': ['Abdoulaye', 'Boureima', 'Cheick', 'Daouda', 'Emmanuel', 'François', 'Gérard', 'Hervé', 'Issouf', 'Jean']},
    'Cape Verde': {'skin_color': 4, 'weight': 0.005, 'names': ['Adilson', 'Bruno', 'Carlos', 'Domingos', 'Eduardo', 'Fernando', 'Gilberto', 'Helder', 'Ivan', 'João']},
    'Congo': {'skin_color': 4, 'weight': 0.005, 'names': ['Alain', 'Boris', 'Christian', 'Daniel', 'Emmanuel', 'François', 'Gabriel', 'Henri', 'Ivan', 'Jean']},
    'Costa Rica': {'skin_color': 3, 'weight': 0.005, 'names': ['Alejandro', 'Carlos', 'Diego', 'Eduardo', 'Fernando', 'Gabriel', 'Héctor', 'Iván', 'Jorge', 'Luis']},
    'Cote d\'Ivoire': {'skin_color': 4, 'weight': 0.005, 'names': ['Abou', 'Bakary', 'Cheick', 'Didier', 'Emmanuel', 'Franck', 'Gervinho', 'Hervé', 'Ibrahim', 'Jean']},
    'Cyprus': {'skin_color': 1, 'weight': 0.005, 'names': ['Andreas', 'Christos', 'Demetris', 'Elias', 'Georgios', 'Haris', 'Ioannis', 'Kyriakos', 'Lefteris', 'Michalis']},
    'Czech Republic': {'skin_color': 1, 'weight': 0.005, 'names': ['David', 'Jakub', 'Jan', 'Lukáš', 'Martin', 'Michal', 'Ondřej', 'Pavel', 'Tomáš', 'Václav']},
    'DR Congo': {'skin_color': 4, 'weight': 0.005, 'names': ['Alain', 'Boris', 'Christian', 'Daniel', 'Emmanuel', 'François', 'Gabriel', 'Henri', 'Ivan', 'Jean']},
    'Equatorial Guinea': {'skin_color': 4, 'weight': 0.005, 'names': ['Abel', 'Benito', 'Carlos', 'Diego', 'Emilio', 'Fernando', 'Gabriel', 'Héctor', 'Iván', 'Jorge']},
    'Estonia': {'skin_color': 1, 'weight': 0.005, 'names': ['Andres', 'Erik', 'Jaan', 'Kristjan', 'Marten', 'Ott', 'Priit', 'Raivo', 'Siim', 'Tarmo']},
    'Free Nationality': {'skin_color': 1, 'weight': 0.005, 'names': ['Alex', 'Ben', 'Chris', 'David', 'Erik', 'Frank', 'George', 'Henry', 'Ivan', 'John']},
    'Gabon': {'skin_color': 4, 'weight': 0.002, 'names': ['Alain', 'Bruno', 'Christian', 'Daniel', 'Emmanuel', 'François', 'Gabriel', 'Henri', 'Ivan', 'Jean']},
    'Gambia': {'skin_color': 4, 'weight': 0.002, 'names': ['Abdoulie', 'Bakary', 'Cherno', 'Demba', 'Ebrima', 'Foday', 'Gibril', 'Habib', 'Ibrahim', 'Jallow']},
    'Georgia': {'skin_color': 1, 'weight': 0.003, 'names': ['Aleksandre', 'Beka', 'Davit', 'Giorgi', 'Irakli', 'Jaba', 'Kakha', 'Levan', 'Mikheil', 'Nika']},
    'Greece': {'skin_color': 1, 'weight': 0.01, 'names': ['Alexandros', 'Dimitrios', 'Georgios', 'Ioannis', 'Konstantinos', 'Michalis', 'Nikolaos', 'Panagiotis', 'Spyros', 'Vasileios']},
    'Grenada': {'skin_color': 4, 'weight': 0.001, 'names': ['Anthony', 'Brian', 'Carl', 'David', 'Eric', 'Frank', 'George', 'Henry', 'Ivan', 'John']},
    'Guadeloupe': {'skin_color': 4, 'weight': 0.001, 'names': ['Alain', 'Bruno', 'Christian', 'Daniel', 'Emmanuel', 'François', 'Gabriel', 'Henri', 'Ivan', 'Jean']},
    'Guinea': {'skin_color': 4, 'weight': 0.001, 'names': ['Aboubacar', 'Boubacar', 'Cheick', 'Daouda', 'Emmanuel', 'François', 'Gabriel', 'Henri', 'Ibrahim', 'Jean']},
    'Guinea-Bissau': {'skin_color': 4, 'weight': 0.001, 'names': ['Abel', 'Bruno', 'Carlos', 'Daniel', 'Emmanuel', 'Fernando', 'Gabriel', 'Henri', 'Ivan', 'João']},
    'Honduras': {'skin_color': 3, 'weight': 0.001, 'names': ['Alejandro', 'Carlos', 'Diego', 'Eduardo', 'Fernando', 'Gabriel', 'Héctor', 'Iván', 'Jorge', 'Luis']},
    'Hungary': {'skin_color': 1, 'weight': 0.005, 'names': ['Ádám', 'Bence', 'Dániel', 'Erik', 'Gábor', 'István', 'János', 'Krisztián', 'László', 'Márk']},
    'Iran': {'skin_color': 2, 'weight': 0.005, 'names': ['Ali', 'Amir', 'Arash', 'Behnam', 'Dariush', 'Ehsan', 'Farhad', 'Gholam', 'Hassan', 'Iraj']},
    'Israel': {'skin_color': 1, 'weight': 0.003, 'names': ['Avi', 'Ben', 'David', 'Eli', 'Gabriel', 'Haim', 'Itai', 'Jonathan', 'Kobi', 'Lior']},
    'Jamaica': {'skin_color': 4, 'weight': 0.005, 'names': ['Anthony', 'Brian', 'Carl', 'David', 'Eric', 'Frank', 'George', 'Henry', 'Ivan', 'John']},
    'Kenya': {'skin_color': 4, 'weight': 0.001, 'names': ['Abel', 'Brian', 'Collins', 'David', 'Eric', 'Frank', 'George', 'Henry', 'Ivan', 'John']},
    'Latvia': {'skin_color': 1, 'weight': 0.003, 'names': ['Aivis', 'Dainis', 'Eduards', 'Guntis', 'Haralds', 'Igors', 'Juris', 'Kaspars', 'Lauris', 'Māris']},
    'Liberia': {'skin_color': 4, 'weight': 0.003, 'names': ['Abel', 'Ben', 'Carl', 'David', 'Eric', 'Frank', 'George', 'Henry', 'Ivan', 'John']},
    'Liechtenstein': {'skin_color': 1, 'weight': 0.001, 'names': ['Alexander', 'Benjamin', 'Christian', 'Daniel', 'Erik', 'Fabian', 'Gabriel', 'Hans', 'Ivan', 'Josef']},
    'Lithuania': {'skin_color': 1, 'weight': 0.001, 'names': ['Arvydas', 'Darius', 'Egidijus', 'Gediminas', 'Henrikas', 'Ignas', 'Jonas', 'Kęstutis', 'Linas', 'Mindaugas']},
    'Macedonia': {'skin_color': 1, 'weight': 0.001, 'names': ['Aleksandar', 'Bojan', 'Darko', 'Emil', 'Filip', 'Goran', 'Hristijan', 'Ivan', 'Jovan', 'Kristijan']},
    'Mali': {'skin_color': 4, 'weight': 0.001, 'names': ['Abdoulaye', 'Boureima', 'Cheick', 'Daouda', 'Emmanuel', 'François', 'Gérard', 'Hervé', 'Issouf', 'Jean']},
    'Martinique': {'skin_color': 4, 'weight': 0.001, 'names': ['Alain', 'Bruno', 'Christian', 'Daniel', 'Emmanuel', 'François', 'Gabriel', 'Henri', 'Ivan', 'Jean']},
    'Mozambique': {'skin_color': 4, 'weight': 0.001, 'names': ['Abel', 'Bruno', 'Carlos', 'Daniel', 'Emmanuel', 'Fernando', 'Gabriel', 'Henri', 'Ivan', 'João']},
    'Netherlands Antilles': {'skin_color': 3, 'weight': 0.001, 'names': ['Anthony', 'Brian', 'Carl', 'David', 'Eric', 'Frank', 'George', 'Henry', 'Ivan', 'John']},
    'New Zealand': {'skin_color': 1, 'weight': 0.002, 'names': ['Aaron', 'Ben', 'Chris', 'David', 'Erik', 'Frank', 'George', 'Henry', 'Ivan', 'John', 'Blake', 'Connor', 'Declan', 'Ethan', 'Flynn', 'Harrison', 'Isaac', 'Jake']},
    'Oman': {'skin_color': 2, 'weight': 0.001, 'names': ['Ahmed', 'Badr', 'Fahad', 'Hamed', 'Ibrahim', 'Jaber', 'Khalid', 'Majid', 'Nasser', 'Omar']},
    'Panama': {'skin_color': 3, 'weight': 0.001, 'names': ['Alejandro', 'Carlos', 'Diego', 'Eduardo', 'Fernando', 'Gabriel', 'Héctor', 'Iván', 'Jorge', 'Luis']},
    'Romania': {'skin_color': 1, 'weight': 0.01, 'names': ['Alexandru', 'Bogdan', 'Cristian', 'Daniel', 'Eduard', 'Florin', 'Gabriel', 'Horia', 'Ionut', 'Johan']},
    'Saudi Arabia': {'skin_color': 2, 'weight': 0.003, 'names': ['Ahmed', 'Badr', 'Fahad', 'Hamed', 'Ibrahim', 'Jaber', 'Khalid', 'Majid', 'Nasser', 'Omar']},
    'Serbia and Montenegro': {'skin_color': 1, 'weight': 0.001, 'names': ['Aleksandar', 'Bojan', 'Darko', 'Emil', 'Filip', 'Goran', 'Hristijan', 'Ivan', 'Jovan', 'Kristijan']},
    'Sierra Leone': {'skin_color': 4, 'weight': 0.001, 'names': ['Abel', 'Ben', 'Carl', 'David', 'Eric', 'Frank', 'George', 'Henry', 'Ivan', 'John']},
    'Slovakia': {'skin_color': 1, 'weight': 0.001, 'names': ['Adam', 'Branislav', 'Daniel', 'Erik', 'Filip', 'Gabriel', 'Henrich', 'Ivan', 'Jozef', 'Kamil']},
    'Slovenia': {'skin_color': 1, 'weight': 0.001, 'names': ['Aleš', 'Bojan', 'Dejan', 'Erik', 'Filip', 'Gregor', 'Henrik', 'Igor', 'Jure', 'Klemen']},
    'Togo': {'skin_color': 4, 'weight': 0.001, 'names': ['Abel', 'Benoît', 'Célestin', 'Désiré', 'Emmanuel', 'Félix', 'Gabriel', 'Henri', 'Ignace', 'Jean']},
    'Trinidad and Tobago': {'skin_color': 4, 'weight': 0.001, 'names': ['Anthony', 'Brian', 'Carl', 'David', 'Eric', 'Frank', 'George', 'Henry', 'Ivan', 'John']},
    'United States': {'skin_color': 1, 'weight': 0.001, 'names': ['Aaron', 'Ben', 'Chris', 'David', 'Erik', 'Frank', 'George', 'Henry', 'Ivan', 'John', 'Blake', 'Connor', 'Declan', 'Ethan', 'Flynn', 'Harrison', 'Isaac', 'Jake']},
    'Uzbekistan': {'skin_color': 2, 'weight': 0.001, 'names': ['Akmal', 'Bakhtiyor', 'Dilshod', 'Eldor', 'Farrukh', 'Gulom', 'Hikmat', 'Ibrohim', 'Javlon', 'Karim']},
    'Zambia': {'skin_color': 4, 'weight': 0.001, 'names': ['Abel', 'Ben', 'Carl', 'David', 'Eric', 'Frank', 'George', 'Henry', 'Ivan', 'John']},
    'Zimbabwe': {'skin_color': 4, 'weight': 0.001, 'names': ['Abel', 'Ben', 'Carl', 'David', 'Eric', 'Frank', 'George', 'Henry', 'Ivan', 'John']}
}

# Surname data by nationality
SURNAME_DATA = {
    'Brazil': ['Maravilha','Cruel','Xareca','Silva','Mineiro','Paulista','Pinga','Gaucho','Baiano','Chupeta','Damiao','Pikachu','Santana','Jesus','Junior','Galindro','Oliveira','Nitro','Filho','Ronaldo'],
    'Argentina': ['Palermo','Cruz','Almeyda','Castro','Valdano','Diaz','Messi','Maria','Gallego','Lopez','Sotto','Correa','Rulli','Martinez','Farias','Mareque','Toro','Pibe','Burrito','Gomez'],
    'Spain': ['Banderas','Hernandez','Gonzalez','de la Costa','Laporte','de Marcos','Garcia','Honesto','Salazar','Gusto','Perez','Rico','Pino','Fernandez','Lopetegui','Enrique','Guerrero','Sanchez','Camacho','de la Buena'],
    'France': ['Benoit','Saint Laurent','Chanel','Givenchy','Gaultier','Papisse','Candela','Papin','Patrice','Fontaine','Remy','Pavard','Ratatouille','Gusteau','Jacquin','Bonaparte','Dior','Chalamet','Brouyche','Dujardin'],
    'England': ['Beckham','Adams','Cole','McCoy','Xavier','Pearce','Baines','Holmes','Wallace','Potter','Weasley','Baggins','Reigns','Kross','McDonagh','Flair','Owen','Charlton','Stark','King'],
    'Germany': ['Meyer','Muller','Nicholas','Schumacher','Schawrz','Einstein','Kant','Marx','Kaiser','Panzer','von Bismarck','Fassbender','Otto','Kruger','Rudof','Hoss','Goring','Effenberg','Himmler','Schneider'],
    'Italy': ['Corleone','Rossi','Gentile','Zola','Dimarco','Di Lorenzo','Bastoni','Gorgonzola','Fetuccini','Rossini','Clemenza','Fanucci','del Neri','Bello','Lamberto','Berlusconi','da Vinci','Baggio','Pavarotti','Bocetti'],
    'Portugal': ['Silva','Galindro','Da Rocha','Rochinha','Amaral','Felix','Capelao','Quaresma','Carvalho','Leitinho','Madureira','Fernandes','Da Costa','Abreu','Seabra','Cardoso','Ferreirinha','Varandas','Leão','Martins','Moreira'],
    'Netherlands': ['van der Vaart','Kluivert','De Jong','Van Bommel','de Boer','Janssen','van de Beek','de Vrijens','van Gallen','Basten','Berg','Bosman','Rijens','Schaar','Cruijff','Wetterman','Dumfries','Stan','de Ligt'],
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
    'Ghana': ['Diouf','Atsu','Boateng','Prince','Addo','Kudus','Mensah','Fatu','Gyan','Sunday'],
    'Ivory Coast': ['Ettien','Rochelu','Konan','Traore','Fofana','Kalou','Keita','Coulibaly','Sanogo'],
    'Cameroon': ['Mbeuna','Kongolo','Ekotto','Milla','Song','Bilong','Nego','Onana','Matip'],
    'Egypt': ['Marmoush','Ghaly','Imoteph','Zidan','Elneny','Faisel','Nahmed','Saleht','Rafaat','Zamal'],
    'Tunisia': ['Trabelsi','Jaziri','Khazim','Quedir','Nejib','Houssem','Slim','Meriah','Belaid','Achouri'],
    'South Africa': ['Fortune','McCarthy','Zuma','Mokoena','John','Joseph','Pistorious','Kulele','Fish','Zwane'],
    'Japan': ['Hyuga','Wakabayashi','Misaki','Tsubasa','Inamoto','Nakamura','Nakazawa','Gohan','Nakata','Fujimoto'],
    'South Korea': ['Ming','Park','Ling','Chun','Gun','Son','Young','Ben','Choy','Mill'],
    'China': ['Wang', 'Li', 'Zhang', 'Liu', 'Chen', 'Yang', 'Huang', 'Zhao', 'Wu', 'Zhou'],
    'Australia': ['Cahill','Ingles','Viduka','Markus','Kennedy','Foster','Rodwell','Rocha','Tulius','Kerr'],
    'USA': ['James','Page','Rhodes','Heyman','Curry','Jordan','Michaels','London','Summer','Copeland','Saint John'],
    'Mexico': ['Hernandez','Gutierrez','Banderas','Martinez','Fonseca','Herrera','Sanchez','Lopez','Fernandez'],
    'Colombia': ['Martinez','Diaz','Escobar','Yepes','Leon','Ortiz','Rincon','Eusebio','Marillo','Rodriguez'],
    'Chile': ['González', 'Muñoz', 'Rojas', 'Díaz', 'Pérez', 'Soto', 'Silva', 'Morales', 'Flores', 'Castro'],
    'Uruguay': ['Rodríguez', 'González', 'Silva', 'Pérez', 'García', 'Fernández', 'López', 'Martínez', 'Díaz', 'Hernández'],
    'Paraguay': ['Cardozo', 'González', 'Silva', 'Pérez', 'Santa Cruz', 'Fernández', 'López', 'Martínez', 'Díaz', 'Hernández'],
    'Peru': ['Rodríguez', 'González', 'Silva', 'Pérez', 'García', 'Fernández', 'López', 'Martínez', 'Díaz', 'Hernández'],
    'Ecuador': ['Rodríguez', 'González', 'Silva', 'Cabra', 'García', 'Fernández', 'López', 'Martínez', 'Díaz', 'Hernández'],
    'Venezuela': ['Rodríguez', 'González', 'Lucho', 'Pérez', 'García', 'Fernández', 'Libre', 'Martínez', 'Díaz', 'Hernández'],
    'Canada': ['Mark', 'Thomas','Rodrigo','Edgar','Philip','Kirr','Dacourt','Falurein','Gustaff','Moore'],
    
    # Additional countries surnames
    'Austria': ['Müller', 'Schmidt', 'Schneider', 'Fischer', 'Weber', 'Meyer', 'Wagner', 'Becker', 'Schulz', 'Hoffmann', 'Bauer', 'Wagner', 'Schwarz', 'Huber', 'Klein', 'Richter', 'Wolf', 'Neumann', 'Schwarz', 'Zimmermann', 'Braun', 'Krüger', 'Hofmann', 'Lange', 'Schmitt', 'Werner', 'Krause', 'Meier', 'Lehmann', 'Schmid', 'Schulze', 'Maier', 'Köhler', 'Herrmann', 'König', 'Walter', 'Mayer', 'Huber', 'Kaiser', 'Fuchs', 'Peters', 'Lang', 'Scholz', 'Möller', 'Weiß', 'Jung', 'Hahn', 'Schubert', 'Schwarz', 'Ziegler'],
    'Switzerland': ['Müller', 'Schmidt', 'Schneider', 'Fischer', 'Weber', 'Meyer', 'Wagner', 'Becker', 'Schulz', 'Hoffmann', 'Bauer', 'Wagner', 'Schwarz', 'Huber', 'Klein', 'Richter', 'Wolf', 'Neumann', 'Schwarz', 'Zimmermann', 'Braun', 'Krüger', 'Hofmann', 'Lange', 'Schmitt', 'Werner', 'Krause', 'Meier', 'Lehmann', 'Schmid', 'Schulze', 'Maier', 'Köhler', 'Herrmann', 'König', 'Walter', 'Mayer', 'Huber', 'Kaiser', 'Fuchs', 'Peters', 'Lang', 'Scholz', 'Möller', 'Weiß', 'Jung', 'Hahn', 'Schubert', 'Schwarz', 'Ziegler'],
    'Sweden': ['Liljgren', 'Rantanen', 'Sundin', 'Nylander', 'Andersson', 'Johansson', 'Karlsson', 'Nilsson', 'Eriksson', 'Larsson', 'Olsson', 'Persson', 'Svensson', 'Gustafsson', 'Pettersson', 'Jonsson', 'Jansson', 'Hansson', 'Bengtsson', 'Jönsson', 'Lindberg', 'Jakobsson', 'Magnusson', 'Olofsson', 'Lindström', 'Eklund', 'Lindqvist', 'Lindgren', 'Axelsson', 'Bergström', 'Lundberg', 'Mattsson', 'Holmberg', 'Sandberg', 'Nyström', 'Lundqvist', 'Holm', 'Månsson', 'Palm', 'Hellström', 'Björk', 'Ekström', 'Berg', 'Lundin', 'Ström', 'Hedberg', 'Sjöberg', 'Forsberg', 'Engström', 'Lundgren', 'Blomqvist', 'Nordström', 'Samuelsson'],
    'Norway': ['Hansen', 'Johansen', 'Olsen', 'Larsen', 'Andersen', 'Pedersen', 'Nilsen', 'Kristiansen', 'Jensen', 'Karlsen', 'Johnsen', 'Pettersen', 'Eriksen', 'Berg', 'Haugen', 'Hagen', 'Johannessen', 'Andreassen', 'Jacobsen', 'Dahl', 'Henriksen', 'Jørgensen', 'Halvorsen', 'Lund', 'Sørensen', 'Jakobsen', 'Moen', 'Gundersen', 'Iversen', 'Svendsen', 'Knudsen', 'Eide', 'Hauge', 'Solberg', 'Bakke', 'Danielsen', 'Berntsen', 'Christensen', 'Rasmussen', 'Lien', 'Mathisen', 'Paulsen', 'Holm', 'Aas', 'Sandvik', 'Lie', 'Haugland', 'Nygård', 'Vik', 'Ødegård'],
    'Denmark': ['Nielsen', 'Jensen', 'Hansen', 'Pedersen', 'Andersen', 'Christensen', 'Larsen', 'Sørensen', 'Rasmussen', 'Jørgensen', 'Petersen', 'Madsen', 'Kristensen', 'Olsen', 'Thomsen', 'Christiansen', 'Poulsen', 'Johansen', 'Møller', 'Knudsen', 'Andreasen', 'Iversen', 'Jeppesen', 'Mikkelsen', 'Frederiksen', 'Jakobsen', 'Lauridsen', 'Henriksen', 'Lund', 'Svendsen', 'Eriksen', 'Holm', 'Bach', 'Bech', 'Bendtsen', 'Birk', 'Bjerre', 'Bøgh', 'Carlsen', 'Dahl', 'Dam', 'Eskildsen', 'Frandsen', 'Gravesen', 'Hansen', 'Hedegaard', 'Hjorth', 'Hoffmann', 'Jensen', 'Kjær'],
    'Finland': ['Virtanen', 'Korhonen', 'Mäkinen', 'Nieminen', 'Mäkelä', 'Hämäläinen', 'Laine', 'Heikkinen', 'Koskinen', 'Järvinen', 'Lehtonen', 'Saarinen', 'Salminen', 'Heinonen', 'Niemi', 'Heikkilä', 'Kinnunen', 'Salonen', 'Turunen', 'Salo', 'Laitinen', 'Rantanen', 'Ahonen', 'Ojala', 'Lehto', 'Väisänen', 'Miettinen', 'Pitkänen', 'Hakkarainen', 'Mattila', 'Anttila', 'Hiltunen', 'Simonen', 'Manninen', 'Kivinen', 'Koski', 'Kangas', 'Peltola', 'Toivonen', 'Kokkonen', 'Nurmi', 'Kettunen', 'Seppänen', 'Aaltonen', 'Kallio', 'Karjalainen', 'Koivisto', 'Lindberg', 'Pekkanen', 'Rautio'],
    'Iceland': ['Jónsson', 'Sigurðsson', 'Guðmundsson', 'Gunnarsson', 'Ólafsson', 'Einarsson', 'Kristjánsson', 'Magnússon', 'Stefánsson', 'Jóhannesson', 'Björnsson', 'Helgason', 'Pétursson', 'Óskarsson', 'Sveinsson', 'Þorsteinsson', 'Haraldsson', 'Árnason', 'Baldursson', 'Eiríksson', 'Friðriksson', 'Geirsson', 'Hauksson', 'Ingvarsson', 'Jónasson', 'Karlsson', 'Lárusson', 'Mársson', 'Níels', 'Ólafursson', 'Pállsson', 'Ragnarsson', 'Sigfússon', 'Tómas', 'Úlfsson', 'Vilhjálmsson', 'Þórsson', 'Ægirsson', 'Örnsson', 'Ásgeirsson', 'Bragi', 'Dagursson', 'Eiríkursson', 'Freyrsson', 'Gísli', 'Hrafnsson', 'Ívarsson', 'Jökull', 'Kári', 'Loki'],
    'Ireland': ['Murphy', 'Kelly', 'O\'Sullivan', 'Walsh', 'Smith', 'O\'Brien', 'Byrne', 'Ryan', 'O\'Connor', 'O\'Neill', 'McCarthy', 'O\'Reilly', 'Doyle', 'Kennedy', 'Lynch', 'Quinn', 'Moore', 'O\'Callaghan', 'O\'Donnell', 'O\'Mahony', 'Burke', 'O\'Shea', 'O\'Leary', 'Daly', 'O\'Connell', 'Wilson', 'Dunne', 'Brennan', 'Murray', 'Collins', 'Campbell', 'Clarke', 'Johnston', 'Hughes', 'O\'Farrell', 'Fitzgerald', 'O\'Grady', 'Power', 'Sullivan', 'White', 'Hayes', 'O\'Dwyer', 'Martin', 'O\'Keeffe', 'O\'Rourke', 'O\'Malley', 'O\'Hara', 'O\'Donovan', 'O\'Sullivan', 'O\'Brien', 'O\'Connor'],
    'Scotland': ['Smith', 'Brown', 'Wilson', 'Stewart', 'Thomson', 'Robertson', 'Campbell', 'Anderson', 'MacDonald', 'Scott', 'Reid', 'Murray', 'Taylor', 'Clark', 'Ross', 'Watson', 'Morrison', 'Paterson', 'Young', 'Mitchell', 'Fraser', 'Walker', 'Graham', 'Hamilton', 'Johnston', 'Cameron', 'Hunter', 'Kelly', 'Bell', 'Grant', 'McDonald', 'Miller', 'McLeod', 'McKenzie', 'Allan', 'Black', 'McKay', 'McLean', 'McIntosh', 'McPherson', 'McLaren', 'McGregor', 'McLaughlin', 'McBride', 'McFarlane', 'McTavish', 'McDougall', 'McInnes', 'McLennan', 'McNab', 'McNeill'],
    'Wales': ['Jones', 'Williams', 'Davies', 'Evans', 'Thomas', 'Roberts', 'Lewis', 'Hughes', 'Morgan', 'Griffiths', 'Edwards', 'Owen', 'James', 'Price', 'Rees', 'Jenkins', 'Phillips', 'Harris', 'Lloyd', 'Powell', 'Morris', 'Richards', 'Taylor', 'Watkins', 'Bennett', 'Cook', 'Wood', 'Bailey', 'Cooper', 'Ward', 'Turner', 'Parker', 'Gray', 'Collins', 'Bell', 'Murphy', 'Cox', 'Howard', 'Ward', 'Torres', 'Peterson', 'Gray', 'Ramirez', 'James', 'Watson', 'Brooks', 'Kelly', 'Sanders', 'Price', 'Bennett'],
    'Northern Ireland': ['Murphy', 'Kelly', 'O\'Sullivan', 'Walsh', 'Smith', 'O\'Brien', 'Byrne', 'Ryan', 'O\'Connor', 'O\'Neill', 'McCarthy', 'O\'Reilly', 'Doyle', 'Kennedy', 'Lynch', 'Quinn', 'Moore', 'O\'Callaghan', 'O\'Donnell', 'O\'Mahony', 'Burke', 'O\'Shea', 'O\'Leary', 'Daly', 'O\'Connell', 'Wilson', 'Dunne', 'Brennan', 'Murray', 'Collins', 'Campbell', 'Clarke', 'Johnston', 'Hughes', 'O\'Farrell', 'Fitzgerald', 'O\'Grady', 'Power', 'Sullivan', 'White', 'Hayes', 'O\'Dwyer', 'Martin', 'O\'Keeffe', 'O\'Rourke', 'O\'Malley', 'O\'Hara', 'O\'Donovan', 'O\'Sullivan', 'O\'Brien', 'O\'Connor'],
    
    # Additional missing countries surnames
    'Albania': ['Hoxha', 'Krasniqi', 'Berisha', 'Gashi', 'Kadriu', 'Morina', 'Pajaziti', 'Rexhepi', 'Shala', 'Zejnullahu'],
    'Angola': ['Santos', 'Fernandes', 'Teta', 'Costa', 'Ferradura', 'Oliveira', 'Rodrigues', 'Ferreira', 'Alves', 'Gomes'],
    'Armenia': ['Grigoryan', 'Khachatryan', 'Harutyunyan', 'Sargsyan', 'Vardanyan', 'Petrosyan', 'Karapetyan', 'Ghazaryan', 'Mkrtchyan', 'Avetisyan'],
    'Belarus': ['Ivanov', 'Petrov', 'Sidorov', 'Kozlov', 'Morozov', 'Volkov', 'Alekseev', 'Lebedev', 'Semenov', 'Egorov'],
    'Cape Verde': ['Santos', 'Fernandes', 'Patrao', 'Costa', 'Pereira', 'Mota', 'Rodrigues', 'Luvinha', 'Alves', 'Gomes'],
    'Benin': ['Adjanohoun', 'Agbessi', 'Akplogan', 'Bokonon', 'Dossou', 'Gbaguidi', 'Houngbédji', 'Kouassi', 'Migan', 'Tchibozo'],
    'Bolivia': ['García', 'Rodríguez', 'González', 'Martínez', 'López', 'Pérez', 'Sánchez', 'Fernández', 'Silva', 'Díaz'],
    'Bosnia and Herzegovina': ['Kovačević', 'Petrović', 'Nikolić', 'Marković', 'Đorđević', 'Stojanović', 'Ilić', 'Stanković', 'Pavlović', 'Milošević'],
    'Bulgaria': ['Ivanov', 'Petrov', 'Georgiev', 'Dimitrov', 'Stoyanov', 'Nikolov', 'Todorov', 'Hristov', 'Atanasov', 'Vasilev'],
    'Burkina Faso': ['Ouédraogo', 'Traoré', 'Sawadogo', 'Kaboré', 'Zongo', 'Ouattara', 'Bikienga', 'Boukary', 'Compaoré', 'Dabiré'],
    'Congo': ['Mabiala', 'Nkounkou', 'Moukila', 'Bouanga', 'Makengo', 'Ndinga', 'Mabika', 'Bouanga', 'Moukila', 'Nkounkou'],
    'Costa Rica': ['Rodríguez', 'González', 'García', 'Martínez', 'López', 'Pérez', 'Sánchez', 'Fernández', 'Silva', 'Díaz'],
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
    'Greece': ['Papadopoulos', 'Georgiou', 'Karagiannis', 'Nikolaou', 'Antoniou', 'Vasileiou', 'Ioannou', 'Christou', 'Dimitriou', 'Konstantinou'],
    'Grenada': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez'],
    'Guadeloupe': ['Mabiala', 'Nkounkou', 'Moukila', 'Bouanga', 'Makengo', 'Ndinga', 'Mabika', 'Bouanga', 'Moukila', 'Nkounkou'],
    'Guinea': ['Diallo', 'Bah', 'Camara', 'Traoré', 'Sow', 'Barry', 'Keita', 'Sylla', 'Cissé', 'Touré'],
    'Guinea-Bissau': ['Mendes', 'Fernandes', 'Silva', 'Costa', 'Pereira', 'Oliveira', 'Rodrigues', 'Ferreira', 'Alves', 'Gomes'],
    'Honduras': ['Rodríguez', 'González', 'García', 'Martínez', 'López', 'Pérez', 'Sánchez', 'Fernández', 'Silva', 'Díaz'],
    'Hungary': ['Nagy', 'Kovács', 'Tóth', 'Szabó', 'Horváth', 'Varga', 'Kiss', 'Molnár', 'Németh', 'Farkas'],
    'Iran': ['Mohammadi', 'Rezaei', 'Hassani', 'Karimi', 'Ahmadi', 'Nouri', 'Gholami', 'Faraji', 'Ebrahimi', 'Rahmani'],
    'Israel': ['Cohen', 'Levy', 'Mizrahi', 'Avraham', 'David', 'Shalom', 'Ben-David', 'Rosenberg', 'Goldberg', 'Weiss'],
    'Jamaica': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez'],
    'Kenya': ['Mwangi', 'Njoroge', 'Kipchoge', 'Ochieng', 'Wanjiku', 'Kamau', 'Nyong\'o', 'Odinga', 'Kenyatta', 'Moi'],
    'Latvia': ['Bērziņš', 'Kalniņš', 'Ozols', 'Liepiņš', 'Dzērve', 'Priede', 'Eglītis', 'Vītols', 'Mežs', 'Silis'],
    'Liberia': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez'],
    'Liechtenstein': ['Müller', 'Schmidt', 'Schneider', 'Fischer', 'Weber', 'Meyer', 'Wagner', 'Becker', 'Schulz', 'Hoffmann'],
    'Lithuania': ['Kazlauskas', 'Petraitis', 'Jankauskas', 'Stankevičius', 'Vasiliauskas', 'Butkus', 'Grigas', 'Lukšys', 'Mickevičius', 'Navickas'],
    'Macedonia': ['Nikolovski', 'Petrovski', 'Georgievski', 'Dimitrovski', 'Stojanovski', 'Todorovski', 'Hristovski', 'Atanasovski', 'Vasilevski', 'Ilievski'],
    'Mali': ['Traoré', 'Keita', 'Coulibaly', 'Diallo', 'Sangaré', 'Diarra', 'Koné', 'Doumbia', 'Touré', 'Sissoko'],
    'Martinique': ['Mabiala', 'Nkounkou', 'Moukila', 'Bouanga', 'Makengo', 'Ndinga', 'Mabika', 'Bouanga', 'Moukila', 'Nkounkou'],
    'Mozambique': ['Mabiala', 'Nkounkou', 'Moukila', 'Bouanga', 'Makengo', 'Ndinga', 'Mabika', 'Bouanga', 'Moukila', 'Nkounkou'],
    'Netherlands Antilles': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez'],
    'New Zealand': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez'],
    'Oman': ['Al-Rashid', 'Al-Zahra', 'Al-Mansouri', 'Al-Hajri', 'Al-Balushi', 'Al-Saadi', 'Al-Mahrouqi', 'Al-Hinai', 'Al-Kharusi', 'Al-Shamsi'],
    'Panama': ['Rodríguez', 'González', 'García', 'Martínez', 'López', 'Pérez', 'Sánchez', 'Fernández', 'Silva', 'Díaz'],
    'Romania': ['Popescu', 'Ionescu', 'Popa', 'Radu', 'Stoica', 'Stan', 'Dumitrescu', 'Gheorghe', 'Constantinescu', 'Marin'],
    'Saudi Arabia': ['Al-Rashid', 'Al-Zahra', 'Al-Mansouri', 'Al-Hajri', 'Al-Balushi', 'Al-Saadi', 'Al-Mahrouqi', 'Al-Hinai', 'Al-Kharusi', 'Al-Shamsi'],
    'Serbia and Montenegro': ['Jovanović', 'Petrović', 'Nikolić', 'Marković', 'Đorđević', 'Stojanović', 'Ilić', 'Stanković', 'Pavlović', 'Milošević'],
    'Sierra Leone': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez'],
    'Slovakia': ['Horváth', 'Kováč', 'Varga', 'Tóth', 'Nagy', 'Szabó', 'Molnár', 'Németh', 'Balog', 'Lukáč'],
    'Slovenia': ['Novak', 'Horvat', 'Krajnc', 'Zupančič', 'Kovačič', 'Mlakar', 'Vidmar', 'Petek', 'Kos', 'Zajc'],
    'Togo': ['Adjanohoun', 'Agbessi', 'Akplogan', 'Bokonon', 'Dossou', 'Gbaguidi', 'Houngbédji', 'Kouassi', 'Migan', 'Tchibozo'],
    'Trinidad and Tobago': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez'],
    'United States': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez'],
    'Uzbekistan': ['Karimov', 'Rashidov', 'Toshev', 'Nazirov', 'Khamidov', 'Usmanov', 'Yuldashev', 'Rakhimov', 'Saidov', 'Kurbanov'],
    'Zambia': ['Mwamba', 'Chilufya', 'Banda', 'Mwanza', 'Sichone', 'Katongo', 'Kalaba', 'Mweene', 'Sunzu', 'Mulenga'],
    'Zimbabwe': ['Mugabe', 'Tsvangirai', 'Nkomo', 'Mugabe', 'Chinamasa', 'Mpofu', 'Mugabe', 'Tsvangirai', 'Nkomo', 'Mugabe']
}

def generate_player_name(nationality: str) -> Tuple[str, str]:
    """Generate a realistic first name and surname for a given nationality."""
    if nationality not in NATIONALITY_DATA:
        nationality = 'England'  # Default fallback
    
    # Get first names and surnames for this nationality
    first_names = NATIONALITY_DATA[nationality]['names']
    surnames = SURNAME_DATA.get(nationality, SURNAME_DATA['England'])  # Fallback to English surnames
    
    # Generate name
    first_name = random.choice(first_names)
    
    # 30% chance to have only one name (no surname)
    if random.random() < 0.30:
        surname = ""  # No surname
    else:
        surname = random.choice(surnames)
    
    return first_name, surname

def select_nationality() -> str:
    """Select a nationality based on weighted probabilities."""
    nationalities = list(NATIONALITY_DATA.keys())
    weights = [NATIONALITY_DATA[nat]['weight'] for nat in nationalities]
    
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
            age_modifier = 4 + random.randint(-2, 2)  # Youngest = most penalty
        elif age == 16:
            age_modifier = 2 + random.randint(-2, 2)
        elif age == 17:
            age_modifier = 1 + random.randint(-2, 2)
        elif age == 18:
            age_modifier = -2 + random.randint(-2, 2)  # Baseline
        elif age == 19:
            age_modifier = -4 + random.randint(-2, 2)   # Older = less penalty
        elif age == 20:
            age_modifier = -6 + random.randint(-2, 2)   # Oldest = least penalty
        
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
        
        # Define special attributes (overwrite with base player values)
        special_attributes = {
            'dribbling_skill': base_player_dict.get('dribbling_skill', 0),
            'tactical_dribble': base_player_dict.get('tactical_dribble', 0),
            'positioning': base_player_dict.get('positioning', 0),
            'reaction': base_player_dict.get('reaction', 0),
            'playmaking': base_player_dict.get('playmaking', 0),
            'passing': base_player_dict.get('passing', 0),
            'scoring': base_player_dict.get('scoring', 0),
            'one_one_scoring': base_player_dict.get('one_one_scoring', 0),
            'post_player': base_player_dict.get('post_player', 0),
            'lines': base_player_dict.get('lines', 0),
            'middle_shooting': base_player_dict.get('middle_shooting', 0),
            'side': base_player_dict.get('side', 0),
            'centre': base_player_dict.get('centre', 0),
            'penalties': base_player_dict.get('penalties', 0),
            'one_touch_pass': base_player_dict.get('one_touch_pass', 0),
            'outside': base_player_dict.get('outside', 0),
            'marking': base_player_dict.get('marking', 0),
            'sliding': base_player_dict.get('sliding', 0),
            'covering': base_player_dict.get('covering', 0),
            'd_line_control': base_player_dict.get('d_line_control', 0),
            'penalty_stopper': base_player_dict.get('penalty_stopper', 0),
            'one_on_one_stopper': base_player_dict.get('one_on_one_stopper', 0),
            'long_throw': base_player_dict.get('long_throw', 0)
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
                # Apply inner_strength penalty + age modifier, but ensure minimum value of 1
                total_penalty = inner_strength_penalty + age_modifier
                skill_attributes[skill] = max(1, int(base_value - total_penalty))
            else:
                skill_attributes[skill] = 1
        
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

def generate_proper_regen(retired_player_data: Dict, db_path: str = None) -> Dict:
    """
    Generate a proper regen based on the retiring player's attributes.
    
    Args:
        retired_player_data: Dictionary containing the retiring player's data
        db_path: Path to the database (optional, for position averages)
    
    Returns:
        Dictionary with the new regen player data
    """
    # Use the global NATIONALITY_DATA (extensive list with 50 names per country)
    # No need to redefine it here
    
    
    def select_nationality():
        """Select a nationality based on weighted probabilities."""
        nationalities = list(NATIONALITY_DATA.keys())
        weights = [NATIONALITY_DATA[nat]['weight'] for nat in nationalities]
        total_weight = sum(weights)
        normalized_weights = [w / total_weight for w in weights]
        return random.choices(nationalities, weights=normalized_weights)[0]
    
    def generate_player_name(nationality):
        """Generate a realistic first name and surname for a given nationality."""
        # Fallback to England if missing or invalid
        if not nationality or nationality not in NATIONALITY_DATA:
            nationality = 'England'
        
        first_names = NATIONALITY_DATA[nationality]['names']
        surnames = SURNAME_DATA.get(nationality, SURNAME_DATA['England'])
        
        first_name = random.choice(first_names)
        
        # 10% chance to have only one name (no surname)
        if random.random() < 0.10:
            surname = ""  # No surname
        else:
            surname = random.choice(surnames)
        
        return first_name, surname
    
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
    nationality = retired_player_data.get('nationality', 'England')  # Use retiring player's nationality, fallback to England
    
    first_name, surname = generate_player_name(nationality)
    full_name = f"{first_name} {surname}".strip() if surname else first_name
    
    # Age: 16-18 for regens
    age = random.randint(16, 18)
    
    # Skin color from nationality
    skin_color = NATIONALITY_DATA[nationality]['skin_color']
    
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
    
    # Special skills: inherit some from retiring player + 10% chance for new abilities
    special_fields = [
        'dribbling_skill', 'tactical_dribble', 'positioning', 'reaction', 'playmaking',
        'passing', 'scoring', 'one_one_scoring', 'post_player', 'lines', 'middle_shooting',
        'side', 'centre', 'penalties', 'one_touch_pass', 'outside', 'marking', 'sliding',
        'covering', 'd_line_control', 'penalty_stopper', 'one_on_one_stopper', 'long_throw'
    ]
    
    special_attributes = {}
    
    # For positions 2-12: 10% chance for special abilities
    if registered_position_num in [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]:
        special_abilities = [
            'dribbling_skill', 'tactical_dribble', 'positioning', 'reaction', 
            'playmaking', 'passing', 'scoring', 'one_one_scoring', 'post_player', 
            'lines', 'middle_shooting', 'side', 'centre', 'penalties', 
            'one_touch_pass', 'outside', 'marking', 'sliding', 'covering', 'long_throw'
        ]
        
        for skill in special_fields:
            if skill in special_abilities:
                # 10% chance to get the ability as 1, 90% chance to get 0
                special_attributes[skill] = 1 if random.random() < 0.05 else 0
            else:
                # For other skills, inherit from retiring player or set to 0
                if skill in retired_player_data:
                    # 70% chance to inherit the skill
                    if random.random() < 0.7:
                        special_attributes[skill] = retired_player_data[skill]
                    else:
                        special_attributes[skill] = 0
                else:
                    special_attributes[skill] = 0
    
    # For goalkeepers (position 0): 10% chance for goalkeeper abilities
    elif registered_position_num == 0:
        gk_abilities = ['penalty_stopper', 'one_on_one_stopper']
        
        for skill in special_fields:
            if skill in gk_abilities:
                # 10% chance to get the ability as 1, 90% chance to get 0
                special_attributes[skill] = 1 if random.random() < 0.1 else 0
            else:
                # For other skills, inherit from retiring player or set to 0
                if skill in retired_player_data:
                    # 70% chance to inherit the skill
                    if random.random() < 0.7:
                        special_attributes[skill] = retired_player_data[skill]
                    else:
                        special_attributes[skill] = 0
                else:
                    special_attributes[skill] = 0
    
    # For other positions (shouldn't happen, but safety fallback)
    else:
        for skill in special_fields:
            if skill in retired_player_data:
                # 70% chance to inherit the skill
                if random.random() < 0.7:
                    special_attributes[skill] = retired_player_data[skill]
                else:
                    special_attributes[skill] = 0
            else:
                special_attributes[skill] = 0
    
    # Physical attributes: use realistic ranges (override database ranges if unrealistic)
    physical_attributes = {}
    
    # Height: realistic range for footballers (160-200cm, not 148-203cm)
    # Override database range if it includes unrealistic values
    if 'height' in column_ranges:
        db_min_height, db_max_height = column_ranges['height']
        # Use database range only if it's realistic
        if db_min_height >= 160 and db_max_height <= 200:
            physical_attributes['height'] = random.randint(db_min_height, db_max_height)
        else:
            # Use realistic range instead
            physical_attributes['height'] = random.randint(160, 200)
    else:
        physical_attributes['height'] = random.randint(160, 200)
    
    # Weight: realistic range for footballers (66-100kg, not 0-105kg)
    # Override database range if it includes unrealistic values
    if 'weight' in column_ranges:
        db_min_weight, db_max_weight = column_ranges['weight']
        # Use database range only if it's realistic
        if db_min_weight >= 66 and db_max_weight <= 100:
            physical_attributes['weight'] = random.randint(db_min_weight, db_max_weight)
        else:
            # Use realistic range instead
            physical_attributes['weight'] = random.randint(66, 100)
    else:
        physical_attributes['weight'] = random.randint(66, 100)
    
    # Physical appearance attributes: generate realistic values
    appearance_attributes = {}
    
    # Face and appearance settings
    appearance_attributes['face_type'] = random.randint(0, 2)  # 0-2
    appearance_attributes['preset_face_number'] = random.randint(1, 361)  # 1-361
    
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
        'age': age,
        'nationality': nationality,
        'skin_color': skin_color,
        'strong_foot': random.choice(['R', 'L']),
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
            SELECT games_played, goals, assists, salary, market_value
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
    """Recalculate salaries for all free agents (club_id = 141) using proper salary calculation."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Get all free agents (No Club players)
        cursor.execute("""
            SELECT * FROM players 
            WHERE club_id = 141
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
                # Calculate new salary
                new_salary = calculate_player_salary_base(player_row, pos_avg_df, skill_columns, binary_skills)
                
                # Apply 30% boost for defensive positions (GK=0, CB=2, DMF=3, FB=4)
                registered_position = player_row.get('registered_position')
                try:
                    # Handle both string and integer formats
                    if isinstance(registered_position, str):
                        pos_int = int(registered_position.strip())
                    elif isinstance(registered_position, (int, float)):
                        pos_int = int(registered_position)
                    else:
                        pos_int = -1
                    
                    if pos_int in [0, 2, 3, 4]:
                        new_salary = int(new_salary * 1.75)
                except (ValueError, TypeError):
                    pass  # Keep new_salary as-is if position is invalid
                
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
    full_name = f"{first_name} {surname}".strip() if surname else first_name
    
    # Get skin color from nationality
    skin_color = NATIONALITY_DATA[nationality]['skin_color']
    
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
        **attributes
    }
    
    return player_data