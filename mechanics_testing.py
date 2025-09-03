#!/usr/bin/env python3
"""
Game Mechanics Testing - Salary and Market Value Calculation
"""

import sqlite3
import pandas as pd
import game_mechanics
import random

def test_position_salaries():
    """Test salary calculation with 10 random players per position"""
    
    # Connect to database
    conn = sqlite3.connect('pes6_league_db.sqlite')
    cursor = conn.cursor()
    
    # Get all unique positions
    cursor.execute("""
        SELECT DISTINCT registered_position 
        FROM players 
        WHERE club_id != 141 
        ORDER BY registered_position
    """)
    positions = [row[0] for row in cursor.fetchall()]
    
    print("=" * 100)
    print("🧮 GAME MECHANICS TESTING - SALARY CALCULATION")
    print("=" * 100)
    print()
    
    all_results = []
    position_summaries = {}
    
    for position in positions:
        print(f"🎯 Processing position: {position}")
        
        # Get 10 random players for this position
        cursor.execute("""
            SELECT id, player_name, registered_position, age, club_id, salary, market_value, 
                   attack, defense, balance, stamina, top_speed, acceleration,
                   response, agility, dribble_accuracy, dribble_speed,
                   short_pass_accuracy, short_pass_speed, long_pass_accuracy, long_pass_speed,
                   shot_accuracy, shot_power, shot_technique, free_kick_accuracy, swerve,
                   heading, jump, technique, aggression, mentality, goal_keeping,
                   team_work, consistency, condition_fitness, dribbling_skill, tactical_dribble,
                   positioning, reaction, playmaking, passing, scoring, one_one_scoring,
                   post_player, lines, middle_shooting, side, centre, penalties,
                   one_touch_pass, outside, marking, sliding, covering, d_line_control,
                   penalty_stopper, one_on_one_stopper, long_throw, injury_tolerance,
                   dribble_style, free_kick_style, pk_style, drop_kick_style
            FROM players 
            WHERE club_id != 141 AND registered_position = ?
            ORDER BY RANDOM() 
            LIMIT 10
        """, (position,))
        
        players = cursor.fetchall()
        
        if not players:
            print(f"  ❌ No players found for position {position}")
            continue
        
        # Get column names
        columns = [description[0] for description in cursor.description]
        
        position_results = []
        
        for player_row in players:
            # Convert to dictionary
            player_data = dict(zip(columns, player_row))
            
            # Calculate new financials using game mechanics
            try:
                new_financials = game_mechanics.calculate_player_financials(player_data, 'pes6_league_db.sqlite')
                
                result = {
                    'player_name': player_data['player_name'],
                    'position': position,
                    'age': player_data['age'],
                    'club_id': player_data['club_id'],
                    'current_salary': player_data['salary'],
                    'new_salary': new_financials['salary'],
                    'salary_change': new_financials['salary'] - player_data['salary'],
                    'salary_change_pct': (new_financials['salary'] - player_data['salary']) / player_data['salary'] * 100,
                    'current_mv': player_data['market_value'],
                    'new_mv': new_financials['market_value'],
                    'mv_change': new_financials['market_value'] - player_data['market_value'],
                    'mv_change_pct': (new_financials['market_value'] - player_data['market_value']) / player_data['market_value'] * 100 if player_data['market_value'] > 0 else 0,
                    'contract_years': new_financials['contract_years_remaining'],
                    'yearly_wage_rise': new_financials['yearly_wage_rise']
                }
                
                position_results.append(result)
                all_results.append(result)
                
            except Exception as e:
                print(f"  ❌ Error calculating financials for {player_data['player_name']}: {e}")
        
        # Sort by new salary for this position
        position_results.sort(key=lambda x: x['new_salary'], reverse=True)
        position_summaries[position] = position_results
        
        print(f"  ✅ Processed {len(position_results)} players")
    
    # Display results by position
    print("\n" + "=" * 100)
    print("🏆 TOP 10 SALARIES PER REGISTERED POSITION")
    print("=" * 100)
    
    for position in sorted(position_summaries.keys()):
        players_in_position = position_summaries[position]
        
        if not players_in_position:
            continue
        
        print(f"\n🎯 POSITION: {position} ({len(players_in_position)} players)")
        print("-" * 80)
        print(f"{'Rank':<4} {'Player Name':<25} {'Age':<3} {'Current':<12} {'New':<12} {'Change':<12} {'%':<6}")
        print("-" * 80)
        
        for i, player in enumerate(players_in_position, 1):
            current_sal = f"€{player['current_salary']:,}"
            new_sal = f"€{player['new_salary']:,}"
            change = f"{player['salary_change']:+,}"
            change_pct = f"{player['salary_change_pct']:+.1f}%"
            
            print(f"{i:<4} {player['player_name']:<25} {player['age']:<3} {current_sal:<12} {new_sal:<12} {change:<12} {change_pct:<6}")
    
    # Overall summary
    print("\n" + "=" * 100)
    print("📊 SALARY CALCULATION SUMMARY")
    print("=" * 100)
    
    if all_results:
        total_players = len(all_results)
        avg_salary_change = sum(r['salary_change'] for r in all_results) / total_players
        avg_salary_change_pct = sum(r['salary_change_pct'] for r in all_results) / total_players
        
        print(f"✅ Total players processed: {total_players}")
        print(f"📈 Average salary change: €{avg_salary_change:+,} ({avg_salary_change_pct:+.1f}%)")
        
        # Top 10 overall salaries
        top_10_overall = sorted(all_results, key=lambda x: x['new_salary'], reverse=True)[:10]
        
        print(f"\n💰 TOP 10 OVERALL SALARIES (ALL POSITIONS)")
        print("-" * 90)
        print(f"{'Rank':<4} {'Player Name':<25} {'Position':<3} {'Age':<3} {'Current':<12} {'New':<12} {'Change':<12} {'%':<6}")
        print("-" * 90)
        
        for i, player in enumerate(top_10_overall, 1):
            current_sal = f"€{player['current_salary']:,}"
            new_sal = f"€{player['new_salary']:,}"
            change = f"{player['salary_change']:+,}"
            change_pct = f"{player['salary_change_pct']:+.1f}%"
            
            print(f"{i:<4} {player['player_name']:<25} {player['position']:<3} {player['age']:<3} {current_sal:<12} {new_sal:<12} {change:<12} {change_pct:<6}")
        
        # Position statistics
        print(f"\n📋 POSITION BREAKDOWN:")
        for position in sorted(position_summaries.keys()):
            players_in_position = position_summaries[position]
            if players_in_position:
                avg_change = sum(p['salary_change'] for p in players_in_position) / len(players_in_position)
                avg_change_pct = sum(p['salary_change_pct'] for p in players_in_position) / len(players_in_position)
                
                print(f"  {position}: {len(players_in_position)} players, avg change: €{avg_change:+,.0f} ({avg_change_pct:+.1f}%)")
    
    conn.close()

def test_position_market_values():
    """Test market value calculation with 10 random players per position"""
    
    # Connect to database
    conn = sqlite3.connect('pes6_league_db.sqlite')
    cursor = conn.cursor()
    
    # Get all unique positions
    cursor.execute("""
        SELECT DISTINCT registered_position 
        FROM players 
        WHERE club_id != 141 
        ORDER BY registered_position
    """)
    positions = [row[0] for row in cursor.fetchall()]
    
    print("=" * 100)
    print("💎 GAME MECHANICS TESTING - MARKET VALUE CALCULATION")
    print("=" * 100)
    print()
    
    all_results = []
    position_summaries = {}
    
    for position in positions:
        print(f"🎯 Processing position: {position}")
        
        # Get 10 random players for this position
        cursor.execute("""
            SELECT id, player_name, registered_position, age, club_id, salary, market_value, 
                   attack, defense, balance, stamina, top_speed, acceleration,
                   response, agility, dribble_accuracy, dribble_speed,
                   short_pass_accuracy, short_pass_speed, long_pass_accuracy, long_pass_speed,
                   shot_accuracy, shot_power, shot_technique, free_kick_accuracy, swerve,
                   heading, jump, technique, aggression, mentality, goal_keeping,
                   team_work, consistency, condition_fitness, dribbling_skill, tactical_dribble,
                   positioning, reaction, playmaking, passing, scoring, one_one_scoring,
                   post_player, lines, middle_shooting, side, centre, penalties,
                   one_touch_pass, outside, marking, sliding, covering, d_line_control,
                   penalty_stopper, one_on_one_stopper, long_throw, injury_tolerance,
                   dribble_style, free_kick_style, pk_style, drop_kick_style
            FROM players 
            WHERE club_id != 141 AND registered_position = ?
            ORDER BY RANDOM() 
            LIMIT 10
        """, (position,))
        
        players = cursor.fetchall()
        
        if not players:
            print(f"  ❌ No players found for position {position}")
            continue
        
        # Get column names
        columns = [description[0] for description in cursor.description]
        
        position_results = []
        
        for player_row in players:
            # Convert to dictionary
            player_data = dict(zip(columns, player_row))
            
            # Calculate new financials using game mechanics
            try:
                new_financials = game_mechanics.calculate_player_financials(player_data, 'pes6_league_db.sqlite')
                
                result = {
                    'player_name': player_data['player_name'],
                    'position': position,
                    'age': player_data['age'],
                    'club_id': player_data['club_id'],
                    'current_salary': player_data['salary'],
                    'new_salary': new_financials['salary'],
                    'current_mv': player_data['market_value'],
                    'new_mv': new_financials['market_value'],
                    'mv_change': new_financials['market_value'] - player_data['market_value'],
                    'mv_change_pct': (new_financials['market_value'] - player_data['market_value']) / player_data['market_value'] * 100 if player_data['market_value'] > 0 else 0,
                    'contract_years': new_financials['contract_years_remaining'],
                    'yearly_wage_rise': new_financials['yearly_wage_rise']
                }
                
                position_results.append(result)
                all_results.append(result)
                
            except Exception as e:
                print(f"  ❌ Error calculating financials for {player_data['player_name']}: {e}")
        
        # Sort by new market value for this position
        position_results.sort(key=lambda x: x['new_mv'], reverse=True)
        position_summaries[position] = position_results
        
        print(f"  ✅ Processed {len(position_results)} players")
    
    # Display results by position
    print("\n" + "=" * 100)
    print("💎 TOP 10 MARKET VALUES PER REGISTERED POSITION")
    print("=" * 100)
    
    for position in sorted(position_summaries.keys()):
        players_in_position = position_summaries[position]
        
        if not players_in_position:
            continue
        
        print(f"\n🎯 POSITION: {position} ({len(players_in_position)} players)")
        print("-" * 80)
        print(f"{'Rank':<4} {'Player Name':<25} {'Age':<3} {'Current':<12} {'New':<12} {'Change':<12} {'%':<6}")
        print("-" * 80)
        
        for i, player in enumerate(players_in_position, 1):
            current_mv = f"€{player['current_mv']:,}"
            new_mv = f"€{player['new_mv']:,}"
            change = f"{player['mv_change']:+,}"
            change_pct = f"{player['mv_change_pct']:+.1f}%"
            
            print(f"{i:<4} {player['player_name']:<25} {player['age']:<3} {current_mv:<12} {new_mv:<12} {change:<12} {change_pct:<6}")
    
    # Overall summary
    print("\n" + "=" * 100)
    print("📊 MARKET VALUE CALCULATION SUMMARY")
    print("=" * 100)
    
    if all_results:
        total_players = len(all_results)
        avg_mv_change = sum(r['mv_change'] for r in all_results) / total_players
        avg_mv_change_pct = sum(r['mv_change_pct'] for r in all_results) / total_players
        
        print(f"✅ Total players processed: {total_players}")
        print(f"📈 Average market value change: €{avg_mv_change:+,} ({avg_mv_change_pct:+.1f}%)")
        
        # Top 10 overall market values
        top_10_overall = sorted(all_results, key=lambda x: x['new_mv'], reverse=True)[:10]
        
        print(f"\n💎 TOP 10 OVERALL MARKET VALUES (ALL POSITIONS)")
        print("-" * 90)
        print(f"{'Rank':<4} {'Player Name':<25} {'Position':<3} {'Age':<3} {'Current':<12} {'New':<12} {'Change':<12} {'%':<6}")
        print("-" * 90)
        
        for i, player in enumerate(top_10_overall, 1):
            current_mv = f"€{player['current_mv']:,}"
            new_mv = f"€{player['new_mv']:,}"
            change = f"{player['mv_change']:+,}"
            change_pct = f"{player['mv_change_pct']:+.1f}%"
            
            print(f"{i:<4} {player['player_name']:<25} {player['position']:<3} {player['age']:<3} {current_mv:<12} {new_mv:<12} {change:<12} {change_pct:<6}")
        
        # Position statistics
        print(f"\n📋 POSITION BREAKDOWN:")
        for position in sorted(position_summaries.keys()):
            players_in_position = position_summaries[position]
            if players_in_position:
                avg_change = sum(p['mv_change'] for p in players_in_position) / len(players_in_position)
                avg_change_pct = sum(p['mv_change_pct'] for p in players_in_position) / len(players_in_position)
                
                print(f"  {position}: {len(players_in_position)} players, avg change: €{avg_change:+,.0f} ({avg_change_pct:+.1f}%)")
    
    conn.close()

def test_retirement_checking():
    """Test retirement checking with players of different ages and circumstances"""
    
    # Connect to database
    conn = sqlite3.connect('pes6_league_db.sqlite')
    cursor = conn.cursor()
    
    print("=" * 100)
    print("👴 GAME MECHANICS TESTING - RETIREMENT CHECKING")
    print("=" * 100)
    print()
    
    # Test different age groups
    age_groups = [
        (25, 29, "Young players (25-29)"),
        (30, 34, "Mid-career players (30-34)"),
        (35, 39, "Veteran players (35-39)"),
        (40, 45, "Senior players (40-45)")
    ]
    
    all_results = []
    
    for min_age, max_age, group_name in age_groups:
        print(f"🎯 Testing {group_name}")
        
        # Get players in this age range
        cursor.execute("""
            SELECT id, player_name, registered_position, age, club_id, salary, market_value
            FROM players 
            WHERE age BETWEEN ? AND ?
            ORDER BY RANDOM() 
            LIMIT 100
        """, (min_age, max_age))
        
        players = cursor.fetchall()
        
        if not players:
            print(f"  ❌ No players found for age group {min_age}-{max_age}")
            continue
        
        # Get column names
        columns = [description[0] for description in cursor.description]
        
        group_results = []
        
        for player_row in players:
            # Convert to dictionary
            player_data = dict(zip(columns, player_row))
            
            # Check retirement
            try:
                retirement_check = game_mechanics.check_player_retirement(player_data)
                
                result = {
                    'player_name': player_data['player_name'],
                    'position': player_data['registered_position'],
                    'age': player_data['age'],
                    'club_id': player_data['club_id'],
                    'salary': player_data['salary'],
                    'wants_to_retire': retirement_check['wants_to_retire'],
                    'retirement_probability': retirement_check['retirement_probability'],
                    'reason': retirement_check['reason'],
                    'age_factor': retirement_check['age_factor'],
                    'salary_factor': retirement_check['salary_factor'],
                    'club_factor': retirement_check['club_factor']
                }
                
                group_results.append(result)
                all_results.append(result)
                
            except Exception as e:
                print(f"  ❌ Error checking retirement for {player_data['player_name']}: {e}")
        
        # Display results for this age group
        print(f"  ✅ Processed {len(group_results)} players")
        
        if len(group_results) > 0:
            retiring_players = [r for r in group_results if r['wants_to_retire']]
            continuing_players = [r for r in group_results if not r['wants_to_retire']]
            
            print(f"  📊 Retiring: {len(retiring_players)}/{len(group_results)} ({len(retiring_players)/len(group_results)*100:.1f}%)")
            
            if retiring_players:
                print(f"  🏃 Players retiring:")
                for player in retiring_players:
                    print(f"    - {player['player_name']} ({player['age']}): {player['reason']}")
            
            if continuing_players:
                print(f"  ⚽ Players continuing:")
                for player in continuing_players[:5]:  # Show first 5
                    print(f"    - {player['player_name']} ({player['age']}): {player['reason']}")
                if len(continuing_players) > 5:
                    print(f"    ... and {len(continuing_players) - 5} more")
        else:
            print("  📊 No players processed successfully")
        
        print()
    
    # Overall summary
    print("=" * 100)
    print("📊 RETIREMENT CHECKING SUMMARY")
    print("=" * 100)
    
    if all_results:
        total_players = len(all_results)
        retiring_players = [r for r in all_results if r['wants_to_retire']]
        continuing_players = [r for r in all_results if not r['wants_to_retire']]
        
        print(f"✅ Total players processed: {total_players}")
        print(f"🏃 Players retiring: {len(retiring_players)} ({len(retiring_players)/total_players*100:.1f}%)")
        print(f"⚽ Players continuing: {len(continuing_players)} ({len(continuing_players)/total_players*100:.1f}%)")
        
        # Average retirement probability by age
        age_ranges = [(25, 29), (30, 34), (35, 39), (40, 45)]
        for min_age, max_age in age_ranges:
            age_group = [r for r in all_results if min_age <= r['age'] <= max_age]
            if age_group:
                avg_prob = sum(r['retirement_probability'] for r in age_group) / len(age_group)
                retiring_count = len([r for r in age_group if r['wants_to_retire']])
                print(f"  Age {min_age}-{max_age}: Avg probability {avg_prob:.1%}, {retiring_count}/{len(age_group)} retiring")
        
        # Top 10 highest retirement probabilities
        top_10_retirement = sorted(all_results, key=lambda x: x['retirement_probability'], reverse=True)[:10]
        
        print(f"\n🏃 TOP 10 HIGHEST RETIREMENT PROBABILITIES")
        print("-" * 90)
        print(f"{'Rank':<4} {'Player Name':<25} {'Age':<3} {'Salary':<12} {'Probability':<12} {'Decision':<10}")
        print("-" * 90)
        
        for i, player in enumerate(top_10_retirement, 1):
            salary = f"€{player['salary']:,}"
            probability = f"{player['retirement_probability']:.1%}"
            decision = "🏃 Retire" if player['wants_to_retire'] else "⚽ Continue"
            
            print(f"{i:<4} {player['player_name']:<25} {player['age']:<3} {salary:<12} {probability:<12} {decision:<10}")
        
        # Random 50 players from all results
        import random
        random_50_players = random.sample(all_results, min(50, len(all_results)))
        random_50_players.sort(key=lambda x: x['retirement_probability'], reverse=True)
        
        print(f"\n🎲 RANDOM 50 PLAYERS (SORTED BY RETIREMENT PROBABILITY)")
        print("-" * 90)
        print(f"{'Rank':<4} {'Player Name':<25} {'Age':<3} {'Salary':<12} {'Probability':<12} {'Decision':<10}")
        print("-" * 90)
        
        for i, player in enumerate(random_50_players, 1):
            salary = f"€{player['salary']:,}"
            probability = f"{player['retirement_probability']:.1%}"
            decision = "🏃 Retire" if player['wants_to_retire'] else "⚽ Continue"
            
            print(f"{i:<4} {player['player_name']:<25} {player['age']:<3} {salary:<12} {probability:<12} {decision:<10}")
    else:
        print("❌ No players were processed successfully")
    
    conn.close()

def main():
    """Main function with user choice"""
    print("=" * 100)
    print("🎮 GAME MECHANICS TESTING")
    print("=" * 100)
    print()
    print("Choose which mechanism you want to test:")
    print("1. Salary Calculation")
    print("2. Market Value Calculation")
    print("3. Retirement Checking")
    print("4. All Tests")
    print()
    
    while True:
        choice = input("Enter your choice (1, 2, 3, or 4): ").strip()
        
        if choice == "1":
            test_position_salaries()
            break
        elif choice == "2":
            test_position_market_values()
            break
        elif choice == "3":
            test_retirement_checking()
            break
        elif choice == "4":
            test_position_salaries()
            print("\n" + "=" * 100)
            print("PRESS ENTER TO CONTINUE TO MARKET VALUE TESTING...")
            input()
            test_position_market_values()
            print("\n" + "=" * 100)
            print("PRESS ENTER TO CONTINUE TO RETIREMENT TESTING...")
            input()
            test_retirement_checking()
            break
        else:
            print("Invalid choice. Please enter 1, 2, 3, or 4.")

if __name__ == "__main__":
    main() 