#!/usr/bin/env python3
"""
Test Salary Calculation Script
Calculates fair salaries for all players and exports to CSV for comparison
"""

import sqlite3
import pandas as pd
import random
import sys
import importlib

# Force reload of game_mechanics module to pick up any changes
if 'game_mechanics' in sys.modules:
    del sys.modules['game_mechanics']

# Import the module (not individual functions) so we can reload it
import game_mechanics

# Force reload to ensure we get the latest code
importlib.reload(game_mechanics)

# Now access functions through the module
calculate_player_salary_base = game_mechanics.calculate_player_salary_base
get_cached_position_averages = game_mechanics.get_cached_position_averages
apply_random_salary_adjustment = game_mechanics.apply_random_salary_adjustment
GLOBAL_BASE_SALARY = game_mechanics.GLOBAL_BASE_SALARY

def calculate_fair_salary(player_data, pos_avg_df):
    """Calculate fair salary using the same method as contract renewal"""
    try:
        import pandas as pd
        
        # Convert to pandas Series for salary calculation
        player_row = pd.Series(player_data)
        
        # Define skill lists (matching contract_renewal.py)
        skills = ['attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
                 'response', 'agility', 'dribble_accuracy', 'dribble_speed',
                 'short_pass_accuracy', 'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed',
                 'shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy', 'swerve',
                 'heading', 'jump', 'technique', 'aggression', 'mentality', 'goal_keeping',
                 'team_work', 'consistency', 'condition_fitness']
        
        binaries = ['dribbling_skill', 'tactical_dribble', 'positioning', 'reaction', 'playmaking',
                   'passing', 'scoring', 'one_one_scoring', 'post_player', 'lines', 'middle_shooting',
                   'side', 'centre', 'penalties', 'one_touch_pass', 'outside', 'marking', 'sliding',
                   'covering', 'd_line_control', 'penalty_stopper', 'one_on_one_stopper', 'long_throw']
        
        # Calculate base salary
        # Position-specific skill boosts are now applied inside calculate_player_salary_base:
        # - Goalkeepers (0): Defense, Balance, Response, Agility, Goal Keeping get 1.5x boost
        # - Sweepers/Centre-backs (2, 3): Defense, Balance, Heading, Jump get 1.5x boost
        base_salary = calculate_player_salary_base(player_row, pos_avg_df, skills, binaries)
        
        # Apply random salary adjustment (±20% variation, rounded to nearest 1000)
        # Use player ID as seed for deterministic results (same player always gets same adjustment)
        random.seed(player_data.get('id', 1))
        fair_salary = apply_random_salary_adjustment(base_salary)
        
        # Apply contract renewal variance (-5% to +20%) on top of fair salary
        # This is in addition to the ±20% variance already in fair_salary
        contract_renewal_variance = random.uniform(-0.05, 0.20)
        salary_demand = fair_salary * (1 + contract_renewal_variance)
        salary_demand = round(max(GLOBAL_BASE_SALARY, salary_demand) / 1000) * 1000
        
        random.seed()  # Reset seed
        
        # Also calculate without random adjustment for comparison
        fair_salary_no_random = round(base_salary / 1000) * 1000
        
        return {
            'base_salary': base_salary,
            'fair_salary': fair_salary,
            'salary_demand': salary_demand,  # Includes contract renewal variance
            'fair_salary_no_random': fair_salary_no_random
        }
    except Exception as e:
        print(f"Error calculating salary for player {player_data.get('id', 'unknown')}: {e}")
        fallback_salary = player_data.get('salary', GLOBAL_BASE_SALARY) or GLOBAL_BASE_SALARY
        return {
            'base_salary': fallback_salary,
            'fair_salary': fallback_salary,
            'salary_demand': fallback_salary,
            'fair_salary_no_random': fallback_salary
        }

def main():
    db_path = 'pes6_league_db.sqlite'
    
    print("🔍 Testing Salary Calculation...")
    print("="*80)
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Get position averages
    print("📊 Loading position averages...")
    pos_avg_df = get_cached_position_averages(db_path)
    
    # Get all players with their current data
    print("👥 Fetching all players...")
    cur.execute("""
        SELECT p.*, t.club_name
        FROM players p
        LEFT JOIN teams t ON p.club_id = t.id
        WHERE p.club_id != 141  -- Exclude free agents
        ORDER BY p.id
    """)
    
    players = cur.fetchall()
    print(f"Found {len(players)} players to analyze\n")
    
    # Calculate salaries for each player
    results = []
    
    for i, player in enumerate(players):
        if (i + 1) % 100 == 0:
            print(f"  Processing player {i+1}/{len(players)}...")
        
        player_dict = dict(player)
        
        # Calculate fair salary
        salary_data = calculate_fair_salary(player_dict, pos_avg_df)
        
        # Calculate difference (using salary_demand which includes contract renewal variance)
        current_salary = player_dict.get('salary', 0) or 0
        calculated_demand = salary_data['salary_demand']  # This is what contract renewal would use
        calculated_fair = salary_data['fair_salary']  # Fair salary without contract renewal variance
        difference = calculated_demand - current_salary
        difference_pct = (difference / current_salary * 100) if current_salary > 0 else 0
        
        results.append({
            'id': player_dict['id'],
            'player_name': player_dict['player_name'],
            'age': player_dict.get('age', 0),
            'overall': player_dict.get('overall', 0),
            'registered_position': player_dict.get('registered_position', ''),
            'club_name': player_dict.get('club_name', ''),
            'current_salary': current_salary,
            'base_salary_calculated': salary_data['base_salary'],
            'fair_salary_no_random': salary_data['fair_salary_no_random'],
            'fair_salary_calculated': calculated_fair,
            'salary_demand_calculated': calculated_demand,  # Includes contract renewal variance
            'difference': difference,
            'difference_percent': round(difference_pct, 2),
            'market_value': player_dict.get('market_value', 0) or 0
        })
    
    # Create DataFrame
    df = pd.DataFrame(results)
    
    # Sort by difference (most underpaid first)
    df = df.sort_values('difference', ascending=False)
    
    # Export to CSV
    output_file = 'salary_calculation_test.csv'
    df.to_csv(output_file, index=False)
    
    print(f"\n✅ Results exported to {output_file}")
    print(f"\n📊 Summary Statistics:")
    print(f"  Total players analyzed: {len(results)}")
    print(f"  Average current salary: €{df['current_salary'].mean():,.0f}")
    print(f"  Average calculated fair salary: €{df['fair_salary_calculated'].mean():,.0f}")
    print(f"  Average calculated salary demand: €{df['salary_demand_calculated'].mean():,.0f}")
    print(f"  Average difference: €{df['difference'].mean():,.0f}")
    print(f"\n  Players with calculated salary > current: {len(df[df['difference'] > 0])}")
    print(f"  Players with calculated salary < current: {len(df[df['difference'] < 0])}")
    print(f"  Players with calculated salary = current: {len(df[df['difference'] == 0])}")
    
    # Show top 20 most underpaid (calculated > current)
    print(f"\n🔝 Top 20 Most Underpaid Players (calculated > current):")
    print("-"*80)
    underpaid = df[df['difference'] > 0].head(20)
    for idx, row in underpaid.iterrows():
        print(f"  {row['player_name']:30} | Current: €{row['current_salary']:>12,} | "
              f"Calculated: €{row['fair_salary_calculated']:>12,} | "
              f"Diff: €{row['difference']:>12,} ({row['difference_percent']:>6.1f}%)")
    
    # Show top 20 most overpaid (calculated < current)
    print(f"\n🔻 Top 20 Most Overpaid Players (calculated < current):")
    print("-"*80)
    overpaid = df[df['difference'] < 0].sort_values('difference').head(20)
    for idx, row in overpaid.iterrows():
        print(f"  {row['player_name']:30} | Current: €{row['current_salary']:>12,} | "
              f"Demand: €{row['salary_demand_calculated']:>12,} | "
              f"Diff: €{row['difference']:>12,} ({row['difference_percent']:>6.1f}%)")
    
    # Check Cassano specifically
    cassano = df[df['player_name'].str.contains('Cassano', case=False, na=False)]
    if not cassano.empty:
        print(f"\n🎯 Cassano Analysis:")
        print("-"*80)
        for idx, row in cassano.iterrows():
            print(f"  {row['player_name']:30} | Age: {row['age']:2} | Overall: {row['overall']:2} | Position: {row['registered_position']}")
            print(f"  Current Salary:     €{row['current_salary']:>12,}")
            print(f"  Base Salary:        €{row['base_salary_calculated']:>12,}")
            print(f"  Fair Salary:        €{row['fair_salary_calculated']:>12,}")
            print(f"  Difference:         €{row['difference']:>12,} ({row['difference_percent']:>6.1f}%)")
            print(f"  Market Value:       €{row['market_value']:>12,}")
    
    conn.close()
    print(f"\n✅ Complete! Check {output_file} for full details.")

if __name__ == "__main__":
    main()
