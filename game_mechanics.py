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
    0: {'name': 'regular', 'rarity': 0.70, 'description': 'Follows positional skill averages'},
    1: {'name': 'jokester', 'rarity': 0.15, 'description': 'Develops wrong skills for position'},
    2: {'name': 'sharpie', 'rarity': 0.10, 'description': 'Overvalues shooting, decreases physical'},
    3: {'name': 'genetic_freak', 'rarity': 0.05, 'description': 'Opposite of sharpie - physical focus'}
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
        
        # Simple encoding: high bit + num_profiles + profiles + weights
        encoded = 0x80000000  # High bit indicates mixed
        encoded |= (num_profiles << 24)  # Number of profiles
        
        # Encode profiles (max 3 profiles, 4 bits each)
        for i, profile in enumerate(profiles):
            encoded |= (profile << (16 + i * 4))
        
        # Encode weights (max 3 weights, 8 bits each)
        for i, weight in enumerate(profile_weights):
            encoded |= (int(weight * 100) << (i * 8))
        
        return encoded
    else:
        # Single profile - use original system
        profile_type = random.choices(
            list(DEVELOPMENT_PROFILES.keys()),
            weights=[DEVELOPMENT_PROFILES[p]['rarity'] for p in DEVELOPMENT_PROFILES.keys()]
        )[0]
        base_multiplier = random.uniform(0.7, 1.5)
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
        # Extract number of profiles
        num_profiles = (development_key >> 24) & 0xFF
        
        profiles = []
        weights = []
        
        # Extract profiles (max 3 profiles, 4 bits each)
        for i in range(min(num_profiles, 3)):  # Limit to 3 profiles maximum
            profile_type = (development_key >> (16 + i * 4)) & 0xF
            if profile_type in DEVELOPMENT_PROFILES:  # Only add valid profiles
                profiles.append(profile_type)
        
        # Extract weights (max 3 weights, 8 bits each)
        for i in range(min(num_profiles, 3)):  # Limit to 3 weights maximum
            weight = ((development_key >> (i * 8)) & 0xFF) / 100.0
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
            return 0.8  # Good growth
        elif age <= 28:
            return 0.3  # Moderate growth
        elif age <= 32:
            return 0.0  # Stagnation
        elif age <= 35:
            return -0.2  # Mild decline
        else:
            return -0.5  # Strong decline
    
    elif profile_type == 1:  # Late bloomer
        if age <= 25:
            return 0.5  # Moderate growth
        elif age <= 30:
            return 1.0  # Strong growth
        elif age <= 34:
            return 0.2  # Mild growth
        elif age <= 37:
            return -0.1  # Very mild decline
        else:
            return -0.3  # Moderate decline
    
    elif profile_type == 2:  # Early peak
        if age <= 20:
            return 1.2  # Very strong growth
        elif age <= 25:
            return 0.6  # Good growth
        elif age <= 28:
            return 0.0  # Peak reached
        elif age <= 32:
            return -0.3  # Moderate decline
        else:
            return -0.7  # Strong decline
    
    elif profile_type == 3:  # Consistent
        if age <= 26:
            return 0.6  # Steady growth
        elif age <= 32:
            return 0.2  # Mild growth
        elif age <= 36:
            return -0.1  # Very mild decline
        else:
            return -0.2  # Mild decline
    
    elif profile_type == 4:  # Decliner
        if age <= 22:
            return 0.4  # Moderate growth
        elif age <= 26:
            return 0.1  # Mild growth
        elif age <= 30:
            return -0.2  # Early decline
        elif age <= 34:
            return -0.4  # Moderate decline
        else:
            return -0.8  # Strong decline
    
    elif profile_type == 5:  # Stronghold
        if age <= 25:
            return 0.7  # Good growth
        elif age <= 30:
            return 0.4  # Moderate growth
        elif age <= 35:
            return 0.2  # Mild growth
        elif age <= 40:
            return 0.0  # Stagnation
        else:
            return -0.1  # Very mild decline
    
    elif profile_type == 6:  # One-time wonder
        if age <= 20:
            return 0.6  # Moderate growth
        elif age <= 23:
            return 1.5  # Amazing growth period
        elif age <= 26:
            return 1.2  # Still strong
        elif age <= 29:
            return 0.1  # Decline starts
        else:
            return -0.5  # Sharp decline
    
    elif profile_type == 7:  # Bust
        if age <= 22:
            return 0.9  # Good start
        elif age <= 25:
            return 0.3  # Moderate growth
        elif age <= 28:
            return -0.3  # Abrupt decline
        else:
            return -0.7  # Severe decline
    
    elif profile_type == 8:  # GOAT
        if age <= 25:
            return 0.8  # Strong growth
        elif age <= 30:
            return 0.6  # Good growth
        elif age <= 35:
            return 0.4  # Moderate growth
        elif age <= 40:
            return 0.2  # Mild growth
        else:
            return 0.0  # Maintains level
    
    elif profile_type == 9:  # El Crapo
        if age <= 22:
            return 0.2  # Poor growth
        elif age <= 25:
            return 0.0  # Stagnation
        elif age <= 28:
            return -0.3  # Early decline
        elif age <= 32:
            return -0.6  # Moderate decline
        else:
            return -0.9  # Severe decline
    
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
    registered_position = player_data.get('registered_position', '7')
    
    # Calculate mixed profile multiplier if applicable
    if dev_info.get('is_mixed', False):
        # Mixed profile - combine multiple profiles
        profiles = dev_info['profiles']
        weights = dev_info['weights']
        
        # Calculate weighted average of age multipliers
        total_age_multiplier = 0
        for profile_type, weight in zip(profiles, weights):
            age_mult = get_age_development_multiplier(age, profile_type)
            total_age_multiplier += age_mult * weight
        
        age_multiplier = total_age_multiplier
        base_multiplier = 1.0  # Mixed profiles use 1.0 as base
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
        base_multiplier = dev_info['base_multiplier']
        age_multiplier = get_age_development_multiplier(age, profile_type)
        profile_name = dev_info['profile_name']
    
    # Get cached position averages for skill weights
    pos_avg_df = get_cached_position_averages('pes6_league_db.sqlite')
    
    # Get position-specific skill weights based on position averages
    position_weights = get_position_skill_weights_from_averages(pos_avg_df, registered_position)
    
    # Apply development trait effects
    position_weights = apply_development_trait_effects(position_weights, trait_info['trait_type'])
    
    # Calculate final development multiplier
    final_multiplier = age_multiplier * base_multiplier
    
    # Apply random variation (±25%)
    random_factor = random.uniform(0.75, 1.25)
    final_multiplier *= random_factor
    
    # Calculate performance-based boost
    performance_boost = calculate_performance_boost(player_data)
    
    # Define skills that can be developed
    skill_columns = [
        'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
        'response', 'agility', 'dribble_accuracy', 'dribble_speed',
        'short_pass_accuracy', 'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed',
        'shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy', 'swerve',
        'heading', 'jump', 'technique', 'aggression', 'mentality', 'goal_keeping',
        'team_work', 'consistency', 'condition_fitness'
    ]
    
    skill_changes = {}
    total_skill_change = 0
    
    for skill in skill_columns:
        if skill in player_data:
            current_value = int(player_data[skill])
            
            # Skip if skill is not applicable (e.g., goal_keeping for outfield players)
            if skill == 'goal_keeping' and registered_position != '0':
                continue
            
            # Get position weight for this skill from averages
            skill_weight = position_weights.get(skill, 1.0)
            
            # Calculate base skill change
            base_change = final_multiplier * skill_weight
            
            # Apply skill value-based progression modifier
            # Higher values are harder to improve, easier to decline
            if base_change > 0:  # Improvement
                # Difficulty increases exponentially with current value
                # 50-70: Easy to improve, 70-85: Moderate, 85-95: Hard, 95+: Very hard
                if current_value >= 95:
                    value_modifier = 0.3  # Very hard to improve
                elif current_value >= 90:
                    value_modifier = 0.5  # Hard to improve
                elif current_value >= 85:
                    value_modifier = 0.7  # Moderate difficulty
                elif current_value >= 75:
                    value_modifier = 0.9  # Easy to improve
                else:
                    value_modifier = 1.0  # Very easy to improve
            else:  # Decline
                # Easier to decline from higher values
                if current_value >= 95:
                    value_modifier = 1.5  # Easy to decline
                elif current_value >= 90:
                    value_modifier = 1.3  # Moderate decline
                elif current_value >= 85:
                    value_modifier = 1.1  # Slight decline boost
                else:
                    value_modifier = 1.0  # Normal decline
            
            base_change *= value_modifier
            
            # Apply performance boost for relevant skills
            if skill in ['attack', 'shot_accuracy', 'shot_power', 'shot_technique'] and player_data.get('goals', 0) > 0:
                base_change += performance_boost['goals_boost']
            elif skill in ['short_pass_accuracy', 'long_pass_accuracy', 'technique'] and player_data.get('assists', 0) > 0:
                base_change += performance_boost['assists_boost']
            elif skill in ['stamina', 'consistency', 'condition_fitness'] and player_data.get('games_played', 0) > 0:
                base_change += performance_boost['games_boost']
            
            # Apply some randomness to individual skills (±30%)
            skill_random = random.uniform(0.7, 1.3)
            skill_change = base_change * skill_random
            
            # Ensure skill stays within reasonable bounds (1-99) and convert to integer
            new_value = max(1, min(99, int(current_value + skill_change)))
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
            # Higher average = higher development weight
            weight = (avg_value / max_avg) * 2.0  # Scale to 0-2 range
            weights[skill] = max(0.5, min(2.0, weight))  # Clamp between 0.5 and 2.0
        else:
            weights[skill] = 0.5  # Low weight for skills not valued for this position
    
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
    pos_avg_df = get_cached_position_averages(db_path)
    
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

# Nationality data with skin color mapping (PES6 numbering: 1=white, 2=light brown, 3=asian, 4=dark)
NATIONALITY_DATA = {
    'Brazil': {'skin_color': 2, 'weight': 0.15, 'names': ['João', 'Pedro', 'Lucas', 'Gabriel', 'Matheus', 'Rafael', 'Bruno', 'Carlos', 'André', 'Felipe']},
    'Argentina': {'skin_color': 1, 'weight': 0.12, 'names': ['Santiago', 'Mateo', 'Benjamín', 'Lucas', 'Nicolás', 'Alejandro', 'Diego', 'Martín', 'Javier', 'Gonzalo']},
    'Spain': {'skin_color': 1, 'weight': 0.10, 'names': ['Carlos', 'Miguel', 'Javier', 'Antonio', 'David', 'Daniel', 'Francisco', 'José', 'Manuel', 'Luis']},
    'France': {'skin_color': 1, 'weight': 0.09, 'names': ['Thomas', 'Pierre', 'Nicolas', 'Alexandre', 'Maxime', 'Antoine', 'Raphaël', 'Vincent', 'Julien', 'Baptiste']},
    'England': {'skin_color': 1, 'weight': 0.08, 'names': ['James', 'William', 'Oliver', 'Harry', 'Jack', 'Noah', 'Charlie', 'Oscar', 'George', 'Ethan']},
    'Germany': {'skin_color': 1, 'weight': 0.08, 'names': ['Maximilian', 'Alexander', 'Felix', 'Leon', 'Paul', 'Jonas', 'Julian', 'Niklas', 'Tim', 'Lukas']},
    'Italy': {'skin_color': 1, 'weight': 0.07, 'names': ['Marco', 'Alessandro', 'Matteo', 'Luca', 'Andrea', 'Giuseppe', 'Roberto', 'Antonio', 'Giovanni', 'Francesco']},
    'Portugal': {'skin_color': 1, 'weight': 0.06, 'names': ['João', 'Miguel', 'Diogo', 'Tiago', 'André', 'Pedro', 'Ricardo', 'Nuno', 'Rui', 'Carlos']},
    'Netherlands': {'skin_color': 1, 'weight': 0.05, 'names': ['Daan', 'Sem', 'Lucas', 'Milan', 'Levi', 'Finn', 'Jesse', 'Luuk', 'Bram', 'Thijs']},
    'Belgium': {'skin_color': 1, 'weight': 0.04, 'names': ['Lucas', 'Louis', 'Arthur', 'Victor', 'Adam', 'Nathan', 'Thomas', 'Maxime', 'Antoine', 'Raphaël']},
    'Croatia': {'skin_color': 1, 'weight': 0.04, 'names': ['Ivan', 'Marko', 'Luka', 'Petar', 'Ante', 'Josip', 'Matej', 'Filip', 'Domagoj', 'Borna']},
    'Serbia': {'skin_color': 1, 'weight': 0.03, 'names': ['Stefan', 'Nikola', 'Marko', 'Aleksandar', 'Milan', 'Petar', 'Dragan', 'Bojan', 'Dejan', 'Nemanja']},
    'Poland': {'skin_color': 1, 'weight': 0.03, 'names': ['Jakub', 'Kacper', 'Filip', 'Szymon', 'Michał', 'Jan', 'Piotr', 'Tomasz', 'Marek', 'Adam']},
    'Ukraine': {'skin_color': 1, 'weight': 0.03, 'names': ['Oleksandr', 'Andriy', 'Mykhailo', 'Vitaliy', 'Serhiy', 'Ihor', 'Vasyl', 'Roman', 'Yuriy', 'Dmytro']},
    'Russia': {'skin_color': 1, 'weight': 0.03, 'names': ['Alexander', 'Dmitri', 'Sergei', 'Andrei', 'Vladimir', 'Igor', 'Nikolai', 'Mikhail', 'Aleksei', 'Denis']},
    'Turkey': {'skin_color': 2, 'weight': 0.03, 'names': ['Mehmet', 'Mustafa', 'Ahmet', 'Ali', 'Hasan', 'Hüseyin', 'İbrahim', 'Murat', 'Ömer', 'Yusuf']},
    'Morocco': {'skin_color': 2, 'weight': 0.02, 'names': ['Youssef', 'Ahmad', 'Karim', 'Hassan', 'Omar', 'Khalid', 'Rachid', 'Nabil', 'Samir', 'Tariq']},
    'Algeria': {'skin_color': 2, 'weight': 0.02, 'names': ['Karim', 'Yacine', 'Sofiane', 'Riyad', 'Islam', 'Adel', 'Samir', 'Nabil', 'Hakim', 'Farid']},
    'Senegal': {'skin_color': 4, 'weight': 0.02, 'names': ['Mamadou', 'Ibrahima', 'Ousmane', 'Sadio', 'Kalidou', 'Cheikhou', 'Idrissa', 'Moussa', 'Pape', 'Youssouf']},
    'Nigeria': {'skin_color': 4, 'weight': 0.02, 'names': ['Victor', 'Kelechi', 'Alex', 'Wilfred', 'Oghenekaro', 'John', 'Ahmed', 'Emmanuel', 'Odion', 'Moses']},
    'Ghana': {'skin_color': 4, 'weight': 0.02, 'names': ['André', 'Thomas', 'Jordan', 'Daniel', 'Christian', 'Jeffrey', 'Mubarak', 'Emmanuel', 'Kwadwo', 'Asamoah']},
    'Ivory Coast': {'skin_color': 4, 'weight': 0.02, 'names': ['Yaya', 'Wilfried', 'Serge', 'Salomon', 'Didier', 'Kolo', 'Emmanuel', 'Gervinho', 'Cheick', 'Seydou']},
    'Cameroon': {'skin_color': 4, 'weight': 0.02, 'names': ['Samuel', 'Joel', 'Vincent', 'Eric', 'Pierre', 'Achille', 'Benjamin', 'Georges', 'Roger', 'Patrick']},
    'Egypt': {'skin_color': 2, 'weight': 0.02, 'names': ['Mohamed', 'Ahmed', 'Mahmoud', 'Omar', 'Karim', 'Amr', 'Hossam', 'Tarek', 'Wael', 'Hassan']},
    'Tunisia': {'skin_color': 2, 'weight': 0.01, 'names': ['Youssef', 'Wahbi', 'Hamza', 'Ferjani', 'Aymen', 'Naim', 'Saber', 'Karim', 'Oussama', 'Anis']},
    'South Africa': {'skin_color': 4, 'weight': 0.01, 'names': ['Percy', 'Steven', 'Dean', 'Bongani', 'Siyabonga', 'Thulani', 'Kagisho', 'Teko', 'Siphiwe', 'Katlego']},
    'Japan': {'skin_color': 3, 'weight': 0.02, 'names': ['Keisuke', 'Shinji', 'Yuto', 'Maya', 'Hiroshi', 'Takashi', 'Yasuhito', 'Makoto', 'Yoshinori', 'Eiji']},
    'South Korea': {'skin_color': 3, 'weight': 0.02, 'names': ['Son', 'Ki', 'Park', 'Lee', 'Kim', 'Jung', 'Choi', 'Kwon', 'Yoon', 'Han']},
    'China': {'skin_color': 3, 'weight': 0.01, 'names': ['Wu', 'Zhang', 'Li', 'Wang', 'Chen', 'Liu', 'Yang', 'Huang', 'Zhao', 'Zhou']},
    'Australia': {'skin_color': 1, 'weight': 0.01, 'names': ['Tim', 'Mathew', 'Mark', 'Joshua', 'Aaron', 'Mile', 'Tom', 'Jackson', 'Adam', 'Ryan']},
    'USA': {'skin_color': 1, 'weight': 0.03, 'names': ['Christian', 'Michael', 'Clint', 'Jozy', 'Brad', 'Tim', 'Geoff', 'Alejandro', 'Graham', 'Bobby']},
    'Mexico': {'skin_color': 2, 'weight': 0.02, 'names': ['Javier', 'Carlos', 'Andrés', 'Guillermo', 'Rafael', 'Jorge', 'Luis', 'Miguel', 'Diego', 'Eduardo']},
    'Colombia': {'skin_color': 2, 'weight': 0.02, 'names': ['James', 'Radamel', 'Juan', 'Carlos', 'David', 'Abel', 'Jackson', 'Luis', 'Fredy', 'Teófilo']},
    'Chile': {'skin_color': 2, 'weight': 0.01, 'names': ['Arturo', 'Alexis', 'Eduardo', 'Gary', 'Claudio', 'Jorge', 'Mauricio', 'Matías', 'Charles', 'Felipe']},
    'Uruguay': {'skin_color': 1, 'weight': 0.01, 'names': ['Luis', 'Edinson', 'Diego', 'Maxi', 'Álvaro', 'Sebastián', 'Cristian', 'Walter', 'Egidio', 'Nicolás']},
    'Paraguay': {'skin_color': 2, 'weight': 0.01, 'names': ['Roque', 'Nelson', 'Oscar', 'Cristian', 'Edgar', 'Julio', 'Dario', 'Lucas', 'Antonio', 'Carlos']},
    'Peru': {'skin_color': 2, 'weight': 0.01, 'names': ['Paolo', 'Jefferson', 'André', 'Christian', 'Yoshimar', 'Renato', 'Luis', 'Carlos', 'Miguel', 'Raúl']},
    'Ecuador': {'skin_color': 2, 'weight': 0.01, 'names': ['Antonio', 'Enner', 'Felipe', 'Michael', 'Christian', 'Renato', 'Carlos', 'Luis', 'Gabriel', 'Walter']},
    'Venezuela': {'skin_color': 2, 'weight': 0.01, 'names': ['Salomón', 'Tomás', 'Rómulo', 'Alejandro', 'Luis', 'Fernando', 'Carlos', 'Roberto', 'José', 'Manuel']},
    'Canada': {'skin_color': 1, 'weight': 0.01, 'names': ['Alphonso', 'Jonathan', 'Atiba', 'Scott', 'Samuel', 'Cyle', 'Mark', 'Tosaint', 'Russell', 'Will']}
}

# Surname data by nationality
SURNAME_DATA = {
    'Brazil': ['Silva', 'Santos', 'Oliveira', 'Souza', 'Rodrigues', 'Ferreira', 'Alves', 'Pereira', 'Lima', 'Gomes'],
    'Argentina': ['González', 'Rodríguez', 'Gómez', 'Fernández', 'López', 'Díaz', 'Martínez', 'Pérez', 'García', 'Sánchez'],
    'Spain': ['García', 'Rodríguez', 'González', 'Fernández', 'López', 'Martínez', 'Sánchez', 'Pérez', 'Gómez', 'Martín'],
    'France': ['Martin', 'Bernard', 'Dubois', 'Thomas', 'Robert', 'Richard', 'Petit', 'Durand', 'Leroy', 'Moreau'],
    'England': ['Smith', 'Jones', 'Williams', 'Brown', 'Taylor', 'Davies', 'Wilson', 'Evans', 'Thomas', 'Roberts'],
    'Germany': ['Müller', 'Schmidt', 'Schneider', 'Fischer', 'Weber', 'Meyer', 'Wagner', 'Becker', 'Schulz', 'Hoffmann'],
    'Italy': ['Rossi', 'Ferrari', 'Russo', 'Bianchi', 'Romano', 'Colombo', 'Ricci', 'Marino', 'Greco', 'Bruno'],
    'Portugal': ['Silva', 'Santos', 'Ferreira', 'Pereira', 'Oliveira', 'Costa', 'Rodrigues', 'Martins', 'Jesus', 'Sousa'],
    'Netherlands': ['de Jong', 'Jansen', 'de Vries', 'van den Berg', 'van Dijk', 'Bakker', 'Visser', 'Smit', 'Meijer', 'de Boer'],
    'Belgium': ['Peeters', 'Janssens', 'Maes', 'Jacobs', 'Mertens', 'Willems', 'Claes', 'Goossens', 'Wouters', 'De Smet'],
    'Croatia': ['Horvat', 'Kovačević', 'Novak', 'Knežević', 'Kovačić', 'Babić', 'Marić', 'Petrović', 'Vuković', 'Radić'],
    'Serbia': ['Jovanović', 'Petrović', 'Nikolić', 'Marković', 'Đorđević', 'Stojanović', 'Ilić', 'Stanković', 'Pavlović', 'Milošević'],
    'Poland': ['Nowak', 'Kowalski', 'Wiśniewski', 'Wójcik', 'Kowalczyk', 'Kamiński', 'Lewandowski', 'Zieliński', 'Szymański', 'Woźniak'],
    'Ukraine': ['Melnyk', 'Shevchenko', 'Bondarenko', 'Kovalenko', 'Tkachenko', 'Kravchenko', 'Kovalchuk', 'Oliynyk', 'Shevchuk', 'Polishchuk'],
    'Russia': ['Ivanov', 'Smirnov', 'Kuznetsov', 'Popov', 'Vasiliev', 'Petrov', 'Sokolov', 'Mikhailov', 'Novikov', 'Fedorov'],
    'Turkey': ['Yılmaz', 'Kaya', 'Demir', 'Çelik', 'Şahin', 'Yıldız', 'Yıldırım', 'Özdemir', 'Arslan', 'Doğan'],
    'Morocco': ['Benjelloun', 'Alaoui', 'Tazi', 'Bennani', 'Berrada', 'Chraibi', 'Fassi', 'Gharbi', 'Hassani', 'Idrissi'],
    'Algeria': ['Bouazza', 'Boumediene', 'Bouhani', 'Boukhari', 'Boukhobza', 'Boukhriss', 'Boumaaza', 'Boumediene', 'Bouras'],
    'Senegal': ['Diop', 'Diallo', 'Fall', 'Ndiaye', 'Ba', 'Sow', 'Thiam', 'Cissé', 'Gueye', 'Diagne'],
    'Nigeria': ['Okechukwu', 'Onyekachi', 'Onyekwelu', 'Onyemachi', 'Onyemaechi', 'Onyenachi', 'Onyenacho', 'Onyenachi', 'Onyenachi', 'Onyenachi'],
    'Ghana': ['Mensah', 'Owusu', 'Addo', 'Asante', 'Boateng', 'Darko', 'Essien', 'Gyan', 'Muntari', 'Paintsil'],
    'Ivory Coast': ['Koné', 'Traoré', 'Ouattara', 'Bamba', 'Coulibaly', 'Diabaté', 'Drogba', 'Kalou', 'Tiéné', 'Zokora'],
    'Cameroon': ['Eto\'o', 'Song', 'M\'Bami', 'Womé', 'Kalla', 'N\'Kufo', 'M\'Boma', 'Song', 'Eto\'o', 'Song'],
    'Egypt': ['Hassan', 'Ahmed', 'Mahmoud', 'Ali', 'Mohamed', 'Hussein', 'Ibrahim', 'Omar', 'Khalil', 'Tarek'],
    'Tunisia': ['Ben', 'Trabelsi', 'Jaziri', 'Jemâa', 'Mnari', 'Nafti', 'Saïfi', 'Zitouni', 'Ben', 'Trabelsi'],
    'South Africa': ['Mokoena', 'Pienaar', 'Tshabalala', 'Khumalo', 'Masilela', 'Gaxa', 'Modise', 'Parker', 'Mphela', 'Nomvethe'],
    'Japan': ['Tanaka', 'Sato', 'Suzuki', 'Takahashi', 'Watanabe', 'Ito', 'Yamamoto', 'Nakamura', 'Kobayashi', 'Kato'],
    'South Korea': ['Kim', 'Lee', 'Park', 'Choi', 'Jung', 'Kang', 'Cho', 'Yoon', 'Jang', 'Lim'],
    'China': ['Wang', 'Li', 'Zhang', 'Liu', 'Chen', 'Yang', 'Huang', 'Zhao', 'Wu', 'Zhou'],
    'Australia': ['Smith', 'Jones', 'Williams', 'Brown', 'Taylor', 'Wilson', 'Johnson', 'Anderson', 'Thompson', 'White'],
    'USA': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez'],
    'Mexico': ['Hernández', 'García', 'Martínez', 'López', 'González', 'Pérez', 'Rodríguez', 'Sánchez', 'Ramírez', 'Cruz'],
    'Colombia': ['Rodríguez', 'González', 'García', 'Martínez', 'López', 'Hernández', 'Pérez', 'Sánchez', 'Ramírez', 'Torres'],
    'Chile': ['González', 'Muñoz', 'Rojas', 'Díaz', 'Pérez', 'Soto', 'Silva', 'Morales', 'Flores', 'Castro'],
    'Uruguay': ['Rodríguez', 'González', 'Silva', 'Pérez', 'García', 'Fernández', 'López', 'Martínez', 'Díaz', 'Hernández'],
    'Paraguay': ['González', 'Rodríguez', 'García', 'Martínez', 'López', 'Pérez', 'Sánchez', 'Fernández', 'Silva', 'Díaz'],
    'Peru': ['García', 'Rodríguez', 'López', 'González', 'Martínez', 'Pérez', 'Sánchez', 'Fernández', 'Silva', 'Díaz'],
    'Ecuador': ['García', 'Rodríguez', 'González', 'Martínez', 'López', 'Pérez', 'Sánchez', 'Fernández', 'Silva', 'Díaz'],
    'Venezuela': ['González', 'Rodríguez', 'García', 'Martínez', 'López', 'Pérez', 'Sánchez', 'Fernández', 'Silva', 'Díaz'],
    'Canada': ['Smith', 'Brown', 'Tremblay', 'Martin', 'Roy', 'Gagnon', 'Lee', 'Wilson', 'Johnson', 'MacDonald']
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

def generate_proper_regen(retired_player_data: Dict, db_path: str = None) -> Dict:
    """
    Generate a proper regen based on the retiring player's attributes.
    
    Args:
        retired_player_data: Dictionary containing the retiring player's data
        db_path: Path to the database (optional, for position averages)
    
    Returns:
        Dictionary with the new regen player data
    """
    # Nationality data with proper skin color mapping
    NATIONALITY_DATA = {
        'Brazil': {'skin_color': 2, 'weight': 0.15, 'names': ['João', 'Pedro', 'Lucas', 'Gabriel', 'Matheus', 'Rafael', 'Bruno', 'Carlos', 'André', 'Felipe']},
        'Argentina': {'skin_color': 1, 'weight': 0.12, 'names': ['Santiago', 'Mateo', 'Benjamín', 'Lucas', 'Nicolás', 'Alejandro', 'Diego', 'Martín', 'Javier', 'Gonzalo']},
        'Spain': {'skin_color': 1, 'weight': 0.10, 'names': ['Carlos', 'Miguel', 'Javier', 'Antonio', 'David', 'Daniel', 'Francisco', 'José', 'Manuel', 'Luis']},
        'France': {'skin_color': 1, 'weight': 0.09, 'names': ['Thomas', 'Pierre', 'Nicolas', 'Alexandre', 'Maxime', 'Antoine', 'Raphaël', 'Vincent', 'Julien', 'Baptiste']},
        'England': {'skin_color': 1, 'weight': 0.08, 'names': ['James', 'William', 'Oliver', 'Harry', 'Jack', 'Noah', 'Charlie', 'Oscar', 'George', 'Ethan']},
        'Germany': {'skin_color': 1, 'weight': 0.08, 'names': ['Maximilian', 'Alexander', 'Felix', 'Leon', 'Paul', 'Jonas', 'Julian', 'Niklas', 'Tim', 'Lukas']},
        'Italy': {'skin_color': 1, 'weight': 0.07, 'names': ['Marco', 'Alessandro', 'Matteo', 'Luca', 'Andrea', 'Giuseppe', 'Roberto', 'Antonio', 'Giovanni', 'Francesco']},
        'Portugal': {'skin_color': 1, 'weight': 0.06, 'names': ['João', 'Miguel', 'Diogo', 'Tiago', 'André', 'Pedro', 'Ricardo', 'Nuno', 'Rui', 'Carlos']},
        'Netherlands': {'skin_color': 1, 'weight': 0.05, 'names': ['Daan', 'Sem', 'Lucas', 'Milan', 'Levi', 'Finn', 'Jesse', 'Luuk', 'Bram', 'Thijs']},
        'Belgium': {'skin_color': 1, 'weight': 0.04, 'names': ['Lucas', 'Louis', 'Arthur', 'Victor', 'Adam', 'Nathan', 'Thomas', 'Maxime', 'Antoine', 'Raphaël']},
        'Croatia': {'skin_color': 1, 'weight': 0.04, 'names': ['Ivan', 'Marko', 'Luka', 'Petar', 'Ante', 'Josip', 'Matej', 'Filip', 'Domagoj', 'Borna']},
        'Serbia': {'skin_color': 1, 'weight': 0.03, 'names': ['Stefan', 'Nikola', 'Marko', 'Aleksandar', 'Milan', 'Petar', 'Dragan', 'Bojan', 'Dejan', 'Nemanja']},
        'Poland': {'skin_color': 1, 'weight': 0.03, 'names': ['Jakub', 'Kacper', 'Filip', 'Szymon', 'Michał', 'Jan', 'Piotr', 'Tomasz', 'Marek', 'Adam']},
        'Ukraine': {'skin_color': 1, 'weight': 0.03, 'names': ['Oleksandr', 'Andriy', 'Mykhailo', 'Vitaliy', 'Serhiy', 'Ihor', 'Vasyl', 'Roman', 'Yuriy', 'Dmytro']},
        'Russia': {'skin_color': 1, 'weight': 0.03, 'names': ['Alexander', 'Dmitri', 'Sergei', 'Andrei', 'Vladimir', 'Igor', 'Nikolai', 'Mikhail', 'Aleksei', 'Denis']},
        'Turkey': {'skin_color': 2, 'weight': 0.03, 'names': ['Mehmet', 'Mustafa', 'Ahmet', 'Ali', 'Hasan', 'Hüseyin', 'İbrahim', 'Murat', 'Ömer', 'Yusuf']},
        'Morocco': {'skin_color': 2, 'weight': 0.02, 'names': ['Youssef', 'Ahmad', 'Karim', 'Hassan', 'Omar', 'Khalid', 'Rachid', 'Nabil', 'Samir', 'Tariq']},
        'Algeria': {'skin_color': 2, 'weight': 0.02, 'names': ['Karim', 'Yacine', 'Sofiane', 'Riyad', 'Islam', 'Adel', 'Samir', 'Nabil', 'Hakim', 'Farid']},
        'Senegal': {'skin_color': 4, 'weight': 0.02, 'names': ['Mamadou', 'Ibrahima', 'Ousmane', 'Sadio', 'Kalidou', 'Cheikhou', 'Idrissa', 'Moussa', 'Pape', 'Youssouf']},
        'Nigeria': {'skin_color': 4, 'weight': 0.02, 'names': ['Victor', 'Kelechi', 'Alex', 'Wilfred', 'Oghenekaro', 'John', 'Ahmed', 'Emmanuel', 'Odion', 'Moses']},
        'Ghana': {'skin_color': 4, 'weight': 0.02, 'names': ['André', 'Thomas', 'Jordan', 'Daniel', 'Christian', 'Jeffrey', 'Mubarak', 'Emmanuel', 'Kwadwo', 'Asamoah']},
        'Ivory Coast': {'skin_color': 4, 'weight': 0.02, 'names': ['Yaya', 'Wilfried', 'Serge', 'Salomon', 'Didier', 'Kolo', 'Emmanuel', 'Gervinho', 'Cheick', 'Seydou']},
        'Cameroon': {'skin_color': 4, 'weight': 0.02, 'names': ['Samuel', 'Joel', 'Vincent', 'Eric', 'Pierre', 'Achille', 'Benjamin', 'Georges', 'Roger', 'Patrick']},
        'Egypt': {'skin_color': 2, 'weight': 0.02, 'names': ['Mohamed', 'Ahmed', 'Mahmoud', 'Omar', 'Karim', 'Amr', 'Hossam', 'Tarek', 'Wael', 'Hassan']},
        'Tunisia': {'skin_color': 2, 'weight': 0.01, 'names': ['Youssef', 'Wahbi', 'Hamza', 'Ferjani', 'Aymen', 'Naim', 'Saber', 'Karim', 'Oussama', 'Anis']},
        'South Africa': {'skin_color': 4, 'weight': 0.01, 'names': ['Percy', 'Steven', 'Dean', 'Bongani', 'Siyabonga', 'Thulani', 'Kagisho', 'Teko', 'Siphiwe', 'Katlego']},
        'Japan': {'skin_color': 3, 'weight': 0.02, 'names': ['Keisuke', 'Shinji', 'Yuto', 'Maya', 'Hiroshi', 'Takashi', 'Yasuhito', 'Makoto', 'Yoshinori', 'Eiji']},
        'South Korea': {'skin_color': 3, 'weight': 0.02, 'names': ['Son', 'Ki', 'Park', 'Lee', 'Kim', 'Jung', 'Choi', 'Kwon', 'Yoon', 'Han']},
        'China': {'skin_color': 3, 'weight': 0.01, 'names': ['Wu', 'Zhang', 'Li', 'Wang', 'Chen', 'Liu', 'Yang', 'Huang', 'Zhao', 'Zhou']},
        'Australia': {'skin_color': 1, 'weight': 0.01, 'names': ['Tim', 'Mathew', 'Mark', 'Joshua', 'Aaron', 'Mile', 'Tom', 'Jackson', 'Adam', 'Ryan']},
        'USA': {'skin_color': 1, 'weight': 0.03, 'names': ['Christian', 'Michael', 'Clint', 'Jozy', 'Brad', 'Tim', 'Geoff', 'Alejandro', 'Graham', 'Bobby']},
        'Mexico': {'skin_color': 2, 'weight': 0.02, 'names': ['Javier', 'Carlos', 'Andrés', 'Guillermo', 'Rafael', 'Jorge', 'Luis', 'Miguel', 'Diego', 'Eduardo']},
        'Colombia': {'skin_color': 2, 'weight': 0.02, 'names': ['James', 'Radamel', 'Juan', 'Carlos', 'David', 'Abel', 'Jackson', 'Luis', 'Fredy', 'Teófilo']},
        'Chile': {'skin_color': 2, 'weight': 0.01, 'names': ['Arturo', 'Alexis', 'Eduardo', 'Gary', 'Claudio', 'Jorge', 'Mauricio', 'Matías', 'Charles', 'Felipe']},
        'Uruguay': {'skin_color': 1, 'weight': 0.01, 'names': ['Luis', 'Edinson', 'Diego', 'Maxi', 'Álvaro', 'Sebastián', 'Cristian', 'Walter', 'Egidio', 'Nicolás']},
        'Paraguay': {'skin_color': 2, 'weight': 0.01, 'names': ['Roque', 'Nelson', 'Oscar', 'Cristian', 'Edgar', 'Julio', 'Dario', 'Lucas', 'Antonio', 'Carlos']},
        'Peru': {'skin_color': 2, 'weight': 0.01, 'names': ['Paolo', 'Jefferson', 'André', 'Christian', 'Yoshimar', 'Renato', 'Luis', 'Carlos', 'Miguel', 'Raúl']},
        'Ecuador': {'skin_color': 2, 'weight': 0.01, 'names': ['Antonio', 'Enner', 'Felipe', 'Michael', 'Christian', 'Renato', 'Carlos', 'Luis', 'Gabriel', 'Walter']},
        'Venezuela': {'skin_color': 2, 'weight': 0.01, 'names': ['Salomón', 'Tomás', 'Rómulo', 'Alejandro', 'Luis', 'Fernando', 'Carlos', 'Roberto', 'José', 'Manuel']},
        'Canada': {'skin_color': 1, 'weight': 0.01, 'names': ['Alphonso', 'Jonathan', 'Atiba', 'Scott', 'Samuel', 'Cyle', 'Mark', 'Tosaint', 'Russell', 'Will']}
    }
    
    # Surname data
    SURNAME_DATA = {
        'Brazil': ['Silva', 'Santos', 'Oliveira', 'Souza', 'Rodrigues', 'Ferreira', 'Alves', 'Pereira', 'Lima', 'Gomes'],
        'Argentina': ['González', 'Rodríguez', 'Gómez', 'Fernández', 'López', 'Díaz', 'Martínez', 'Pérez', 'García', 'Sánchez'],
        'Spain': ['García', 'Rodríguez', 'González', 'Fernández', 'López', 'Martínez', 'Sánchez', 'Pérez', 'Gómez', 'Martín'],
        'France': ['Martin', 'Bernard', 'Dubois', 'Thomas', 'Robert', 'Richard', 'Petit', 'Durand', 'Leroy', 'Moreau'],
        'England': ['Smith', 'Jones', 'Williams', 'Brown', 'Taylor', 'Davies', 'Wilson', 'Evans', 'Thomas', 'Roberts'],
        'Germany': ['Müller', 'Schmidt', 'Schneider', 'Fischer', 'Weber', 'Meyer', 'Wagner', 'Becker', 'Schulz', 'Hoffmann'],
        'Italy': ['Rossi', 'Ferrari', 'Russo', 'Bianchi', 'Romano', 'Colombo', 'Ricci', 'Marino', 'Greco', 'Bruno'],
        'Portugal': ['Silva', 'Santos', 'Ferreira', 'Pereira', 'Oliveira', 'Costa', 'Rodrigues', 'Martins', 'Jesus', 'Sousa'],
        'Netherlands': ['de Jong', 'Jansen', 'de Vries', 'van den Berg', 'van Dijk', 'Bakker', 'Visser', 'Smit', 'Meijer', 'de Boer'],
        'Belgium': ['Peeters', 'Janssens', 'Maes', 'Jacobs', 'Mertens', 'Willems', 'Claes', 'Goossens', 'Wouters', 'De Smet'],
        'Croatia': ['Horvat', 'Kovačević', 'Novak', 'Knežević', 'Kovačić', 'Babić', 'Marić', 'Petrović', 'Vuković', 'Radić'],
        'Serbia': ['Jovanović', 'Petrović', 'Nikolić', 'Marković', 'Đorđević', 'Stojanović', 'Ilić', 'Stanković', 'Pavlović', 'Milošević'],
        'Poland': ['Nowak', 'Kowalski', 'Wiśniewski', 'Wójcik', 'Kowalczyk', 'Kamiński', 'Lewandowski', 'Zieliński', 'Szymański', 'Woźniak'],
        'Ukraine': ['Melnyk', 'Shevchenko', 'Bondarenko', 'Kovalenko', 'Tkachenko', 'Kravchenko', 'Kovalchuk', 'Oliynyk', 'Shevchuk', 'Polishchuk'],
        'Russia': ['Ivanov', 'Smirnov', 'Kuznetsov', 'Popov', 'Vasiliev', 'Petrov', 'Sokolov', 'Mikhailov', 'Novikov', 'Fedorov'],
        'Turkey': ['Yılmaz', 'Kaya', 'Demir', 'Çelik', 'Şahin', 'Yıldız', 'Yıldırım', 'Özdemir', 'Arslan', 'Doğan'],
        'Morocco': ['Benjelloun', 'Alaoui', 'Tazi', 'Bennani', 'Berrada', 'Chraibi', 'Fassi', 'Gharbi', 'Hassani', 'Idrissi'],
        'Algeria': ['Bouazza', 'Boumediene', 'Bouhani', 'Boukhari', 'Boukhobza', 'Boukhriss', 'Boumaaza', 'Boumediene', 'Bouras'],
        'Senegal': ['Diop', 'Diallo', 'Fall', 'Ndiaye', 'Ba', 'Sow', 'Thiam', 'Cissé', 'Gueye', 'Diagne'],
        'Nigeria': ['Okechukwu', 'Onyekachi', 'Onyekwelu', 'Onyemachi', 'Onyemaechi', 'Onyenachi', 'Onyenacho', 'Onyenachi', 'Onyenachi'],
        'Ghana': ['Mensah', 'Owusu', 'Addo', 'Asante', 'Boateng', 'Darko', 'Essien', 'Gyan', 'Muntari', 'Paintsil'],
        'Ivory Coast': ['Koné', 'Traoré', 'Ouattara', 'Bamba', 'Coulibaly', 'Diabaté', 'Drogba', 'Kalou', 'Tiéné', 'Zokora'],
        'Cameroon': ['Eto\'o', 'Song', 'M\'Bami', 'Womé', 'Kalla', 'N\'Kufo', 'M\'Boma', 'Song', 'Eto\'o', 'Song'],
        'Egypt': ['Hassan', 'Ahmed', 'Mahmoud', 'Ali', 'Mohamed', 'Hussein', 'Ibrahim', 'Omar', 'Khalil', 'Tarek'],
        'Tunisia': ['Ben', 'Trabelsi', 'Jaziri', 'Jemâa', 'Mnari', 'Nafti', 'Saïfi', 'Zitouni', 'Ben', 'Trabelsi'],
        'South Africa': ['Mokoena', 'Pienaar', 'Tshabalala', 'Khumalo', 'Masilela', 'Gaxa', 'Modise', 'Parker', 'Mphela', 'Nomvethe'],
        'Japan': ['Tanaka', 'Sato', 'Suzuki', 'Takahashi', 'Watanabe', 'Ito', 'Yamamoto', 'Nakamura', 'Kobayashi', 'Kato'],
        'South Korea': ['Kim', 'Lee', 'Park', 'Choi', 'Jung', 'Kang', 'Cho', 'Yoon', 'Jang', 'Lim'],
        'China': ['Wang', 'Li', 'Zhang', 'Liu', 'Chen', 'Yang', 'Huang', 'Zhao', 'Wu', 'Zhou'],
        'Australia': ['Smith', 'Jones', 'Williams', 'Brown', 'Taylor', 'Wilson', 'Johnson', 'Anderson', 'Thompson', 'White'],
        'USA': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez'],
        'Mexico': ['Hernández', 'García', 'Martínez', 'López', 'González', 'Pérez', 'Rodríguez', 'Sánchez', 'Ramírez', 'Cruz'],
        'Colombia': ['Rodríguez', 'González', 'García', 'Martínez', 'López', 'Hernández', 'Pérez', 'Sánchez', 'Ramírez', 'Torres'],
        'Chile': ['González', 'Muñoz', 'Rojas', 'Díaz', 'Pérez', 'Soto', 'Silva', 'Morales', 'Flores', 'Castro'],
        'Uruguay': ['Rodríguez', 'González', 'Silva', 'Pérez', 'García', 'Fernández', 'López', 'Martínez', 'Díaz', 'Hernández'],
        'Paraguay': ['González', 'Rodríguez', 'García', 'Martínez', 'López', 'Pérez', 'Sánchez', 'Fernández', 'Silva', 'Díaz'],
        'Peru': ['García', 'Rodríguez', 'López', 'González', 'Martínez', 'Pérez', 'Sánchez', 'Fernández', 'Silva', 'Díaz'],
        'Ecuador': ['García', 'Rodríguez', 'González', 'Martínez', 'López', 'Pérez', 'Sánchez', 'Fernández', 'Silva', 'Díaz'],
        'Venezuela': ['González', 'Rodríguez', 'García', 'Martínez', 'López', 'Pérez', 'Sánchez', 'Fernández', 'Silva', 'Díaz'],
        'Canada': ['Smith', 'Brown', 'Tremblay', 'Martin', 'Roy', 'Gagnon', 'Lee', 'Wilson', 'Johnson', 'MacDonald']
    }
    
    def select_nationality():
        """Select a nationality based on weighted probabilities."""
        nationalities = list(NATIONALITY_DATA.keys())
        weights = [NATIONALITY_DATA[nat]['weight'] for nat in nationalities]
        total_weight = sum(weights)
        normalized_weights = [w / total_weight for w in weights]
        return random.choices(nationalities, weights=normalized_weights)[0]
    
    def generate_player_name(nationality):
        """Generate a realistic first name and surname for a given nationality."""
        if nationality not in NATIONALITY_DATA:
            nationality = 'England'
        
        first_names = NATIONALITY_DATA[nationality]['names']
        surnames = SURNAME_DATA.get(nationality, SURNAME_DATA['England'])
        
        first_name = random.choice(first_names)
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
    nationality = select_nationality()
    first_name, surname = generate_player_name(nationality)
    full_name = f"{first_name} {surname}"
    
    # Age: 16-18 for regens
    age = random.randint(16, 18)
    
    # Skin color from nationality
    skin_color = NATIONALITY_DATA[nationality]['skin_color']
    
    # Position: Keep the same as retiring player
    registered_position = retired_player_data['registered_position']
    
    # Financial data: Lower for young players
    base_salary = random.randint(30000, 120000)
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
    
    # Base the regen's attributes on the retiring player's attributes
    # but scaled down for age and with some randomness
    age_factor = 0.6 + (age - 16) * 0.075  # 16yo = 60%, 17yo = 67.5%, 18yo = 75%
    
    # Skill attributes: base on retiring player but scaled down
    skill_attributes = {}
    skill_fields = [
        'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
        'response', 'agility', 'dribble_accuracy', 'dribble_speed',
        'short_pass_accuracy', 'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed',
        'shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy', 'swerve',
        'heading', 'jump', 'technique', 'aggression', 'mentality', 'goal_keeping',
        'team_work', 'consistency', 'condition_fitness'
    ]
    
    for skill in skill_fields:
        if skill in retired_player_data:
            base_value = retired_player_data[skill]
            # Scale down for age and add randomness
            variation = random.uniform(-8, 8)
            final_value = int(base_value * age_factor + variation)
            
            # Use realistic range from database if available
            if skill in column_ranges:
                min_val, max_val = column_ranges[skill]
                final_value = max(min_val, min(max_val, final_value))
            else:
                # Default range if not found in database
                final_value = max(1, min(99, final_value))
            
            # Special handling for condition_fitness (should be 4-8)
            if skill == 'condition_fitness':
                final_value = max(4, min(8, final_value))
            
            # Special handling for consistency (should be 4-8)
            if skill == 'consistency':
                final_value = max(4, min(8, final_value))
            
            skill_attributes[skill] = final_value
        else:
            # Default value if skill not found
            if skill == 'condition_fitness':
                skill_attributes[skill] = random.randint(4, 8)
            elif skill == 'consistency':
                skill_attributes[skill] = random.randint(4, 8)
            else:
                skill_attributes[skill] = random.randint(50, 70)
    
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
    
    main_position_field = position_to_field.get(str(registered_position), 'cf')
    
    for pos in positional_fields:
        if pos == main_position_field:
            positional_attributes[pos] = 1  # Can play this position
        else:
            positional_attributes[pos] = 0  # Cannot play this position
    
    # Special skills: inherit some from retiring player
    special_fields = [
        'dribbling_skill', 'tactical_dribble', 'positioning', 'reaction', 'playmaking',
        'passing', 'scoring', 'one_one_scoring', 'post_player', 'lines', 'middle_shooting',
        'side', 'centre', 'penalties', 'one_touch_pass', 'outside', 'marking', 'sliding',
        'covering', 'd_line_control', 'penalty_stopper', 'one_on_one_stopper', 'long_throw'
    ]
    
    special_attributes = {}
    for skill in special_fields:
        if skill in retired_player_data:
            # 70% chance to inherit the skill
            if random.random() < 0.7:
                special_attributes[skill] = retired_player_data[skill]
            else:
                special_attributes[skill] = 0
        else:
            special_attributes[skill] = 0
    
    # Physical attributes: use realistic ranges
    physical_attributes = {}
    if 'height' in column_ranges:
        min_height, max_height = column_ranges['height']
        physical_attributes['height'] = random.randint(min_height, max_height)
    else:
        physical_attributes['height'] = random.randint(160, 200)
    
    if 'weight' in column_ranges:
        min_weight, max_weight = column_ranges['weight']
        physical_attributes['weight'] = random.randint(min_weight, max_weight)
    else:
        physical_attributes['weight'] = random.randint(60, 90)
    
    # Calculated ratings (will be calculated by the system)
    calculated_ratings = {
        'attack_rating': 50,
        'defense_rating': 50,
        'physical_rating': 50,
        'power_rating': 50,
        'technique_rating': 50,
        'goalkeeping_rating': 50
    }
    
    # Create the complete regen data
    regen_data = {
        'player_name': full_name,
        'age': age,
        'nationality': nationality,
        'skin_color': skin_color,
        'strong_foot': random.choice(['R', 'L']),
        'favoured_side': random.choice(['R', 'L']),
        'registered_position': registered_position,
        'game_position': registered_position,
        'club_id': retired_player_data['club_id'],
        'salary': base_salary,
        'contract_years_remaining': contract_years,
        'market_value': 0,  # Will be calculated
        'yearly_wage_rise': yearly_wage_rise,
        'development_key': development_key,
        'trait_key': trait_key,
        'games_played': 0,
        'goals': 0,
        'assists': 0,
        **skill_attributes,
        **positional_attributes,
        **special_attributes,
        **physical_attributes,
        **calculated_ratings
    }
    
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
            SELECT id, player_name, age, registered_position, salary, club_id, nationality
            FROM players 
            WHERE age >= 30
            ORDER BY age DESC
        """)
        
        players_to_check = cursor.fetchall()
        retired_players = []
        continuing_players = []
        
        print(f"  📊 Checking {len(players_to_check)} players aged 30+ for retirement...")
        
        # Check each player for retirement
        for player in players_to_check:
            player_data = {
                'id': player[0],
                'player_name': player[1],
                'age': player[2],
                'registered_position': player[3],
                'salary': player[4],
                'club_id': player[5],
                'nationality': player[6]
            }
            
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
        
        # For now, just return the retirement information
        # The actual replacement will be handled by the calling function
        # to avoid database locking issues
        
        conn.close()
        
        return {
            'retired_players': retired_players,
            'continuing_players': continuing_players,
            'replacements_generated': 0,  # Will be calculated by caller
            'teams_updated': [],  # Will be calculated by caller
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
    full_name = f"{first_name} {surname}"
    
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