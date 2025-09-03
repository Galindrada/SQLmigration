#!/usr/bin/env python3
"""
Update all player salaries in the database using the improved game mechanics formula
"""

import sqlite3
import game_mechanics
import pandas as pd

def update_all_player_salaries():
    """Update all player salaries using the game mechanics formula"""
    
    print("=" * 100)
    print("💰 UPDATING ALL PLAYER SALARIES")
    print("=" * 100)
    print()
    
    # Connect to database
    conn = sqlite3.connect('pes6_league_db.sqlite')
    cursor = conn.cursor()
    
    # Get all players (excluding No Club players)
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
        WHERE club_id != 141
        ORDER BY id
    """)
    
    players = cursor.fetchall()
    
    if not players:
        print("❌ No players found")
        return
    
    # Get column names
    columns = [description[0] for description in cursor.description]
    
    print(f"🎯 Found {len(players)} players to update")
    print()
    
    updated_count = 0
    errors = 0
    total_salary_change = 0
    
    # Process players in batches for better performance
    batch_size = 100
    for i in range(0, len(players), batch_size):
        batch = players[i:i + batch_size]
        
        print(f"📊 Processing batch {i//batch_size + 1}/{(len(players) + batch_size - 1)//batch_size}")
        
        for player_row in batch:
            # Convert to dictionary
            player_data = dict(zip(columns, player_row))
            
            try:
                # Calculate new financials using game mechanics
                new_financials = game_mechanics.calculate_player_financials(player_data, 'pes6_league_db.sqlite')
                
                # Update salary in database
                cursor.execute("""
                    UPDATE players 
                    SET salary = ?, market_value = ?, contract_years_remaining = ?, yearly_wage_rise = ?
                    WHERE id = ?
                """, (
                    new_financials['salary'],
                    new_financials['market_value'],
                    new_financials['contract_years_remaining'],
                    new_financials['yearly_wage_rise'],
                    player_data['id']
                ))
                
                salary_change = new_financials['salary'] - player_data['salary']
                total_salary_change += salary_change
                updated_count += 1
                
            except Exception as e:
                print(f"  ❌ Error updating {player_data['player_name']}: {e}")
                errors += 1
        
        # Commit batch
        conn.commit()
        print(f"  ✅ Batch completed: {len(batch)} players processed")
    
    # Final summary
    print("\n" + "=" * 100)
    print("📊 SALARY UPDATE SUMMARY")
    print("=" * 100)
    
    print(f"✅ Players updated: {updated_count}")
    print(f"❌ Errors: {errors}")
    print(f"📈 Total salary change: €{total_salary_change:+,}")
    print(f"📊 Average salary change: €{total_salary_change/updated_count:+,}" if updated_count > 0 else "📊 No players updated")
    
    # Get some statistics
    cursor.execute("""
        SELECT 
            COUNT(*) as total_players,
            AVG(salary) as avg_salary,
            MIN(salary) as min_salary,
            MAX(salary) as max_salary
        FROM players 
        WHERE club_id != 141
    """)
    
    stats = cursor.fetchone()
    if stats:
        print(f"\n📋 DATABASE STATISTICS:")
        print(f"  Total players: {stats[0]}")
        print(f"  Average salary: €{stats[1]:,.0f}")
        print(f"  Salary range: €{stats[2]:,} - €{stats[3]:,}")
    
    # Top 10 highest salaries
    cursor.execute("""
        SELECT player_name, registered_position, age, salary
        FROM players 
        WHERE club_id != 141
        ORDER BY salary DESC
        LIMIT 10
    """)
    
    top_salaries = cursor.fetchall()
    if top_salaries:
        print(f"\n💰 TOP 10 HIGHEST SALARIES:")
        print("-" * 80)
        print(f"{'Rank':<4} {'Player Name':<25} {'Position':<3} {'Age':<3} {'Salary':<15}")
        print("-" * 80)
        
        for i, (name, position, age, salary) in enumerate(top_salaries, 1):
            print(f"{i:<4} {name:<25} {position:<3} {age:<3} €{salary:,}")
    
    conn.close()
    print(f"\n✅ Salary update completed successfully!")

if __name__ == "__main__":
    update_all_player_salaries() 