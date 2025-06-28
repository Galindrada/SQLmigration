import pandas as pd
import mysql.connector
from dotenv import load_dotenv
import os
import random
import math # Needed for math.pow, math.uniform, etc.

# --- GLOBAL CONSTANTS FROM IMPORTTRYOUT.PY (ADJUST AS NEEDED) ---
GLOBAL_BASE_SALARY = 300000
SEED_VALUE = 40
random.seed(SEED_VALUE)
# np.random.seed(SEED_VALUE) # Numpy not directly used for random in these specific functions

# Salary and Market Value Calculator Specific Constants
NORM = 75.0
BIN_IMPACT = 0.15
R_START = 70.0
R_END = 99.0
MIN_MULT = 0.5
MAX_MULT = 4.0
DEF_BOOST = 4.0
GK_BOOST = 4.0
DEF_NAME = 'defense' # Lowercase to match SQL column name
GK_NAME = 'goal_keeping' # Lowercase to match SQL column name
DIV = 1000.0
POW = 3.0
SCALER = 970000.0

# --- Database Connection Details ---
load_dotenv()
DB_CONFIG = {
    'host': os.environ.get('MYSQL_HOST'),
    'user': os.environ.get('MYSQL_USER'),
    'password': os.environ.get('MYSQL_PASSWORD'),
    'database': os.environ.get('MYSQL_DB')
}

# --- HELPER FUNCTIONS ADAPTED FROM IMPORTTRYOUT.PY ---

def calculate_player_salary_base(player_row, pos_avg_df, skills, binaries):
    """
    Calculates the base salary for a player using multiple skill components,
    positional averages, and specific boosts.
    `player_row` is a dictionary (from MySQLdb.cursors.DictCursor)
    `pos_avg_df` is a pandas DataFrame.
    `skills` is a list of actual skill column names (SQL names).
    `binaries` is a list of actual binary skill column names (SQL names).
    """
    pos = player_row.get('registered_position')
    pos_clean = pos if pos is not None else 'Unknown Position'
    
    # Ensure pos_avg_df is not empty and contains the position
    if pos_avg_df is None or pos_clean not in pos_avg_df.index: 
        pos_spec_avg = pd.Series(NORM, index=skills) # Default to NORM if position not found
    else: 
        pos_spec_avg = pos_avg_df.loc[pos_clean]
        if not isinstance(pos_spec_avg, pd.Series): # Fallback if loc returns a scalar or unexpected type
             pos_spec_avg = pd.Series(NORM, index=skills)

    total_weighted_skill_score = 0
    for skill_n in skills:
        val = player_row.get(skill_n)
        if val is None: continue # Skip if skill value is None in player_row
        
        val = float(val) # Convert to float for calculations
        
        # Multiplier logic from importtryout.py
        mult = MIN_MULT
        if val >= R_END: 
            mult = MAX_MULT
        elif val > R_START:
            prog = (val - R_START) / (R_END - R_START)
            if MIN_MULT == 0 and MAX_MULT > 0: mult = MAX_MULT * math.pow(prog, 2)
            elif MIN_MULT > 0: mult = MIN_MULT * math.pow(MAX_MULT / MIN_MULT, prog)
        eff_val = val * mult

        # Impact value from positional averages
        skill_imp_val = pos_spec_avg.get(skill_n, NORM) if isinstance(pos_spec_avg, pd.Series) else NORM
        imp = skill_imp_val / NORM
        contrib = eff_val * imp

        # Specific boosts for DEFENSE and GOAL KEEPING
        if skill_n == DEF_NAME and player_row.get(DEF_NAME) is not None:
             contrib *= DEF_BOOST
        elif skill_n == GK_NAME and player_row.get(GK_NAME) is not None:
             contrib *= GK_BOOST
        
        # Binary skill impact
        if skill_n in binaries and player_row.get(skill_n) == 1: # Only if binary skill is active (1)
            contrib *= BIN_IMPACT
            
        total_weighted_skill_score += contrib
    
    total_weighted_skill_score = max(0, total_weighted_skill_score)
    norm_twss = total_weighted_skill_score / DIV
    pow_score = math.pow(max(0, norm_twss), POW) # Ensure non-negative for power function
    
    sal_skills = pow_score * SCALER
    calculated_salary = GLOBAL_BASE_SALARY + sal_skills
    
    return max(GLOBAL_BASE_SALARY, round(calculated_salary / 1000) * 1000)


def apply_random_salary_adjustment(base_salary):
    """Applies a random percentage adjustment to the base salary."""
    factor = random.uniform(-0.20, 0.20)
    adj_sal = base_salary * (1 + factor)
    return max(GLOBAL_BASE_SALARY, round(adj_sal / 1000) * 1000)

def get_age_market_value_multiplier(age_val):
    """Calculates age-based multiplier for market value."""
    if age_val is None: return 1.0
    age = float(age_val)
    y_ref, y_fact = 16.0, 4.0
    p_ref, p_fact = 29.0, 1.0 # Peak around 29
    o_ref, o_fact = 40.0, 0.01 # Decline towards 40

    k_y, k_o = 1.5, 3.0 # Curvature of the age curve

    if age <= y_ref: return y_fact
    elif age < p_ref:
        prog = (age - y_ref) / (p_ref - y_ref)
        return p_fact + (y_fact - p_fact) * math.pow(1 - prog, k_y)
    elif age == p_ref: return p_fact
    elif age < o_ref:
        prog = (age - p_ref) / (o_ref - p_ref)
        return o_fact + (p_fact - o_fact) * math.pow(1 - prog, k_o)
    else: return o_fact

def determine_contract_years(age_val):
    """Determines random contract years remaining based on age."""
    if age_val is None: return random.randint(2, 3)
    try: age = int(float(age_val))
    except ValueError: return random.randint(2,3)
    if age > 32: return random.randint(1, 2)
    elif age > 30: return random.randint(1, 3)
    else: return random.randint(2, 5)

def calculate_yearly_wage_raise(player_row, skills, binaries, salary):
    """Calculates yearly wage raise based on age, skill average, and current salary."""
    age_val = player_row.get('age')
    try: age = int(float(age_val)) if age_val is not None else 25
    except ValueError: age = 25

    # Filter for numeric skills, ensure they exist and are not None
    num_skills_values = [
        player_row.get(s) for s in skills if s not in binaries and player_row.get(s) is not None
    ]
    
    if not num_skills_values:
        avg_skill = 60.0
    else: 
        # Convert values to numeric, handle potential non-numeric data safely
        numeric_values = [float(v) for v in num_skills_values if isinstance(v, (int, float))]
        if numeric_values:
            avg_skill = sum(numeric_values) / len(numeric_values)
        else:
            avg_skill = 60.0 # Default if no valid numeric skills found
    
    raise_percentage = 0.0
    if age <= 23 and avg_skill >= 78: raise_percentage = random.uniform(0.15,0.25)
    elif age <= 23 and avg_skill >= 70: raise_percentage = random.uniform(0.10,0.20)
    elif age <= 26 and avg_skill >= 75: raise_percentage = random.uniform(0.08,0.18)
    elif age <= 29 and avg_skill >= 72: raise_percentage = random.uniform(0.05,0.12)
    elif age > 32 or avg_skill < 65: raise_percentage = random.uniform(0.00,0.05)
    else: raise_percentage = random.uniform(0.03,0.08)
    
    if salary < (GLOBAL_BASE_SALARY * 5): raise_percentage *= 1.1 # Boost for lower salaries
    
    return round(min(salary * raise_percentage, salary * 0.25)) # Max raise capped at 25% of salary


# --- MAIN UPDATE FUNCTION ---

def update_player_finances():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True) # Use dictionary=True for column names

        print("Fetching all player data from database for calculations...")
        # Fetch all columns (especially skills) needed for calculations
        # Ensure all columns referenced in calculate_player_salary_base and calculate_yearly_wage_raise are selected
        cursor.execute("SELECT * FROM players")
        players_data_raw = cursor.fetchall()
        
        if not players_data_raw:
            print("No players found in the database. Please import player data first.")
            return

        print(f"Calculating and updating financial data for {len(players_data_raw)} players...")

        # Convert to DataFrame for easier processing, especially for skill identification and positional averages
        df_players = pd.DataFrame(players_data_raw)

        # Identify actual skill columns present in the DataFrame
        # These columns must match the SQL column names
        non_skill_cols_list = [
            'id', 'player_name', 'shirt_name', 'club_id', 'registered_position', 'age', 'height', 'weight',
            'nationality', 'strong_foot', 'favoured_side', 'is_transfer_listed', # Non-skill columns
            'salary', 'contract_years_remaining', 'market_value', 'yearly_wage_rise', # Financial columns
            'dribble_style', 'free_kick_style', 'pk_style', 'drop_kick_style', 'skin_color', 'face_type',
            'preset_face_number', 'head_width', 'neck_length', 'neck_width', 'shoulder_height',
            'shoulder_width', 'chest_measurement', 'waist_circumference', 'arm_circumference',
            'leg_circumference', 'calf_circumference', 'leg_length', 'wristband', 'wristband_color',
            'international_number', 'classic_number', 'club_number'
            # Add any other non-skill columns that are integers/numeric
        ]
        
        # Ensure 'REGISTERED POSITION' is part of non_skill_cols for salary calc, but it's used for grouping
        # Filter for skills actually present in DF.columns (which are already SQL-friendly names)
        # Note: Skills are typically integers.
        actual_skill_columns = [
            col for col in df_players.columns 
            if col not in non_skill_cols_list and 
            pd.api.types.is_numeric_dtype(df_players[col]) and 
            not pd.api.types.is_bool_dtype(df_players[col]) and
            df_players[col].dropna().nunique() > 1 # Must have more than one unique value (not just 0 or 1 for non-binary skills)
        ]
        
        # Manually add known binary/positional skills if they were identified as numeric but often just 0/1
        # Ensure these are SQL column names
        binary_skill_cols = [
            'gk', 'cwp', 'cbt', 'sb', 'dmf', 'wb', 'cmf', 'smf', 'amf', 'wf', 'ss', 'cf',
            'dribbling_skill', 'tactical_dribble', 'positioning', 'reaction', 'playmaking',
            'passing', 'scoring', 'one_one_scoring', 'post_player', 'lines', 'middle_shooting',
            'side', 'centre', 'penalties', 'one_touch_pass', 'outside', 'marking', 'sliding',
            'covering', 'd_line_control', 'penalty_stopper', 'one_on_one_stopper', 'long_throw'
        ]
        # Filter binary_skill_cols to only include those actually present in the DataFrame's columns
        binary_skill_cols = [col for col in binary_skill_cols if col in df_players.columns]


        # Convert skill columns to numeric, coercing errors to NaN
        for col in actual_skill_columns + binary_skill_cols + ['age', 'consistency']:
            if col in df_players.columns:
                df_players[col] = pd.to_numeric(df_players[col], errors='coerce')
        
        # Calculate positional averages for relevant skills
        # Ensure 'registered_position' is also part of the grouping key
        if 'registered_position' in df_players.columns and actual_skill_columns:
            position_averages_df = df_players.groupby('registered_position')[actual_skill_columns].mean()
        else:
            position_averages_df = pd.DataFrame() # Empty if no positions or skills

        # Iterate through players (as dictionaries) for calculation and update
        for player_dict in players_data_raw: # Use raw fetched dicts for iteration
            player_id = player_dict['id']
            
            # Extract relevant attributes for calculation, providing defaults for None
            age = player_dict.get('age', 25)
            consistency = player_dict.get('consistency', 4)
            injury_tolerance = player_dict.get('injury_tolerance', 'B')

            # Pass the player_dict itself for accessing all skills
            calculated_salary = calculate_player_salary_base(player_dict, position_averages_df, actual_skill_columns, binary_skill_cols)
            
            final_salary = apply_random_salary_adjustment(calculated_salary)
            contract_years_remaining = determine_contract_years(age)
            yearly_wage_raise = calculate_yearly_wage_raise(player_dict, actual_skill_columns, binary_skill_cols, final_salary)
            market_value = calculate_market_value(final_salary, contract_years_remaining, sum(player_dict.get(s, 0) for s in actual_skill_columns)) # Simple sum of actual_skills for market value overall

            # Update the player's row in the database
            update_sql = """
            UPDATE players
            SET salary = %s,
                contract_years_remaining = %s,
                market_value = %s,
                yearly_wage_rise = %s
            WHERE id = %s
            """
            cursor.execute(update_sql, (final_salary, contract_years_remaining, market_value, yearly_wage_raise, player_id))

        conn.commit()
        print("Financial data updated successfully for all players!")

    except mysql.connector.Error as err:
        print(f"Database Error: {err}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()
            print("MySQL connection closed.")

if __name__ == "__main__":
    update_player_finances()
