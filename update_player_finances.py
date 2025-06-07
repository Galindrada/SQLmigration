import pandas as pd
import mysql.connector
from dotenv import load_dotenv
import os
import random

# Load environment variables from .env
load_dotenv()

# Database connection details from config.py or .env
DB_CONFIG = {
    'host': os.environ.get('MYSQL_HOST'),
    'user': os.environ.get('MYSQL_USER'),
    'password': os.environ.get('MYSQL_PASSWORD'),
    'database': os.environ.get('MYSQL_DB')
}

# --- GLOBAL CONSTANTS FOR CALCULATION ---
# Adjust these multipliers and factors to fine-tune salary/market values
GLOBAL_BASE_SALARY_MULTIPLIER = 10000  # Base salary per composite overall point
MARKET_VALUE_BASE_MULTIPLIER = 3.0    # Base multiplier for market value
MAX_COMPOSITE_SKILL_SCORE = 11 * 99   # Approx max sum of 11 selected skills (assuming max 99 per skill)
RANDOM_SALARY_VARIANCE = 50000        # Max random variance for salary
RANDOM_MARKET_VARIANCE = 2000000      # Max random variance for market value

# --- CALCULATION ROUTINES ---

def calculate_composite_overall(player_data):
    """
    Calculates a composite overall rating from a selection of key player skills.
    Uses fields available in the SQL 'players' table.
    """
    skills_to_sum = [
        'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
        'dribble_accuracy', 'short_pass_accuracy', 'shot_power', 'technique', 'team_work'
    ]
    
    composite_score = 0
    for skill in skills_to_sum:
        # Handle None values by treating them as 0 for calculation
        composite_score += player_data.get(skill, 0) if player_data.get(skill) is not None else 0
        
    return composite_score

def calculate_base_salary(age, composite_overall, consistency, injury_tolerance):
    """
    Calculates a base salary for a player based on composite overall, age, and consistency.
    Inspired by ModelSQL.py logic.
    """
    salary = composite_overall * GLOBAL_BASE_SALARY_MULTIPLIER

    # Age adjustment: Peak around 25-30, decline after 30, lower before 20
    if age < 20:
        age_factor = 0.6
    elif 20 <= age <= 24:
        age_factor = 0.9
    elif 25 <= age <= 30:
        age_factor = 1.1 # Peak earning years
    elif 31 <= age <= 34:
        age_factor = 0.95
    else: # age > 34
        age_factor = 0.7
    
    salary *= age_factor

    # Consistency adjustment (e.g., 1-8 scale)
    # Higher consistency increases salary, using (consistency / 8.0) * 0.2 + 0.9 to give a factor between 0.925 and 1.1
    consistency_factor = ((consistency if consistency is not None else 4) / 8.0) * 0.2 + 0.9
    salary *= consistency_factor

    # Injury tolerance adjustment (e.g., 'A', 'B', 'C' - A is less prone to injury)
    injury_factor = 1.0
    if injury_tolerance == 'A':
        injury_factor = 1.05 # Slightly higher for less injury prone
    elif injury_tolerance == 'C':
        injury_factor = 0.95 # Slightly lower for more injury prone
    salary *= injury_factor
    
    # Add random variance
    salary += random.randint(-RANDOM_SALARY_VARIANCE, RANDOM_SALARY_VARIANCE)

    return max(100000, int(salary)) # Minimum salary of 100,000

def calculate_contract_years_remaining():
    """Calculates random contract years remaining (e.g., 1 to 5 years)."""
    return random.randint(1, 5)

def calculate_yearly_wage_rise(salary):
    """Calculates a yearly wage rise as a percentage of salary."""
    # Random percentage between 2% and 10%
    rise_percentage = random.uniform(0.02, 0.10)
    return int(salary * rise_percentage)

def calculate_market_value(salary, contract_years_remaining, composite_overall):
    """
    Calculates market value based on salary, contract years, and composite overall.
    Inspired by ModelSQL.py logic.
    """
    # Market value is often a multiple of salary, weighted by contract length and overall skill
    # Higher overall and longer contract means higher market value
    overall_factor = (composite_overall / MAX_COMPOSITE_SKILL_SCORE) # Normalized overall factor (0-1)
    
    # Market value multiplier: (overall factor + contract_years_remaining factor) * base multiplier
    market_multiplier = (overall_factor * 2 + (contract_years_remaining / 5.0)) * MARKET_VALUE_BASE_MULTIPLIER

    market_value = salary * market_multiplier

    # Add random variance
    market_value += random.randint(-RANDOM_MARKET_VARIANCE, RANDOM_MARKET_VARIANCE)

    return max(500000, int(market_value)) # Minimum market value

def update_player_finances():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True) # Use dictionary=True to get column names

        print("Fetching player data from database...")
        # Fetch necessary columns for calculation and player ID.
        # Include all skills needed for composite_overall, plus age, consistency, injury_tolerance.
        columns_to_fetch = [
            'id', 'age', 'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
            'dribble_accuracy', 'short_pass_accuracy', 'shot_power', 'technique', 'team_work',
            'consistency', 'injury_tolerance' # Added injury_tolerance
        ]
        
        select_sql = f"SELECT {', '.join([f'`{col}`' for col in columns_to_fetch])} FROM players"
        cursor.execute(select_sql)
        players_data = cursor.fetchall()

        if not players_data:
            print("No players found in the database. Please import player data first.")
            return

        print(f"Calculating and updating financial data for {len(players_data)} players...")

        for player in players_data:
            player_id = player['id']
            age = player.get('age', 25) # Default if None
            consistency = player.get('consistency', 4) # Default if None
            injury_tolerance = player.get('injury_tolerance', 'B') # Default if None

            # Calculate composite overall rating
            composite_overall = calculate_composite_overall(player)

            # Calculate financial attributes
            salary = calculate_base_salary(age, composite_overall, consistency, injury_tolerance)
            contract_years_remaining = calculate_contract_years_remaining()
            yearly_wage_rise = calculate_yearly_wage_rise(salary)
            market_value = calculate_market_value(salary, contract_years_remaining, composite_overall)

            # Update the player's row in the database
            update_sql = """
            UPDATE players
            SET salary = %s,
                contract_years_remaining = %s,
                market_value = %s,
                yearly_wage_rise = %s
            WHERE id = %s
            """
            cursor.execute(update_sql, (salary, contract_years_remaining, market_value, yearly_wage_rise, player_id))

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
