#!/usr/bin/env python3
"""
Test script to verify seed regression mechanics work correctly.
Tests players who are above their seed targets to ensure regression occurs.
"""

import sqlite3
import sys
from game_mechanics import calculate_player_skill_development, get_seed_player_targets

def test_seed_regression():
    """Test that players above seed targets regress towards them"""
    
    print("="*80)
    print("🧪 SEED REGRESSION TEST")
    print("="*80)
    
    # Connect to database
    conn = sqlite3.connect('pes6_league_db.sqlite')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get Emre Arslan as test case
    cursor.execute("""
        SELECT id, player_name, age, registered_position, development_key, trait_key, seed_player,
               attack, defense, balance, stamina, top_speed, acceleration,
               response, agility, dribble_accuracy, dribble_speed,
               short_pass_accuracy, short_pass_speed, long_pass_accuracy, long_pass_speed,
               shot_accuracy, shot_power, shot_technique, free_kick_accuracy, swerve,
               heading, jump, technique, aggression, mentality, goal_keeping, team_work
        FROM players
        WHERE id = 4697
    """)
    
    player = cursor.fetchone()
    
    if not player:
        print("❌ Player ID 4697 (Emre Arslan) not found")
        conn.close()
        return
    
    player_data = dict(player)
    
    print(f"\n📋 Test Player: {player_data['player_name']} (ID: {player_data['id']})")
    print(f"   Age: {player_data['age']}")
    print(f"   Seed Player ID: {player_data['seed_player']}")
    print(f"   Development Key: {player_data['development_key']}")
    print(f"   Trait Key: {player_data['trait_key']}")
    
    # Get seed targets
    seed_targets = get_seed_player_targets(player_data['seed_player'])
    
    if not seed_targets:
        print("❌ Could not fetch seed targets")
        conn.close()
        return
    
    # Get seed player name
    original_conn = sqlite3.connect('original.sqlite')
    original_cursor = original_conn.cursor()
    original_cursor.execute("SELECT player_name FROM players WHERE id = ?", (player_data['seed_player'],))
    seed_name_row = original_cursor.fetchone()
    seed_name = seed_name_row[0] if seed_name_row else "Unknown"
    original_conn.close()
    
    print(f"   Seed Player: {seed_name} (ID: {player_data['seed_player']})")
    
    # Find skills where player is above seed
    skills_above_seed = []
    skills_below_seed = []
    skills_at_seed = []
    
    for skill, target in seed_targets.items():
        if target is not None and skill in player_data:
            current = player_data[skill]
            if current > target:
                skills_above_seed.append((skill, current, target, current - target))
            elif current < target:
                skills_below_seed.append((skill, current, target, target - current))
            else:
                skills_at_seed.append((skill, current, target))
    
    print(f"\n📊 Skill Analysis:")
    print(f"   ✅ At seed target: {len(skills_at_seed)}")
    print(f"   ⬆️  Below seed (should grow): {len(skills_below_seed)}")
    print(f"   ⬇️  Above seed (should regress): {len(skills_above_seed)}")
    
    if skills_above_seed:
        print(f"\n🔍 Skills Above Seed (Testing Regression):")
        print(f"   {'Skill':<25} {'Current':<10} {'Seed':<10} {'Over By':<10}")
        print("   " + "-"*55)
        for skill, current, target, over_by in sorted(skills_above_seed, key=lambda x: x[3], reverse=True)[:10]:
            print(f"   {skill:<25} {current:<10} {target:<10} +{over_by:<10}")
    
    # Simulate development
    print(f"\n🔄 Simulating Development...")
    result = calculate_player_skill_development(
        player_data,
        player_data['development_key'],
        player_data['trait_key']
    )
    
    # Analyze results for skills above seed
    print(f"\n📈 Development Results for Skills Above Seed:")
    print(f"   {'Skill':<25} {'Current':<10} {'Change':<10} {'New':<10} {'Seed':<10} {'Status':<15}")
    print("   " + "-"*85)
    
    regression_count = 0
    growth_count = 0
    stable_count = 0
    
    for skill, current, target, over_by in sorted(skills_above_seed, key=lambda x: x[3], reverse=True)[:15]:
        if skill in result['skill_changes']:
            change_info = result['skill_changes'][skill]
            change = change_info['change']
            new_value = change_info['new']
            
            if change < 0:
                status = "✅ REGRESSING"
                regression_count += 1
            elif change > 0:
                status = "❌ GROWING"
                growth_count += 1
            else:
                status = "➖ STABLE"
                stable_count += 1
            
            change_str = f"{change:+d}" if change != 0 else "0"
            print(f"   {skill:<25} {current:<10} {change_str:<10} {new_value:<10} {target:<10} {status:<15}")
    
    print(f"\n📊 Summary for Skills Above Seed:")
    print(f"   ✅ Regressing (good): {regression_count}")
    print(f"   ➖ Stable: {stable_count}")
    print(f"   ❌ Growing (bad): {growth_count}")
    
    if growth_count > 0:
        print(f"\n⚠️  WARNING: {growth_count} skills above seed are still growing!")
        print(f"   This indicates the regression mechanism may need adjustment.")
    elif regression_count > 0:
        print(f"\n✅ SUCCESS: Skills above seed are regressing towards seed target!")
    else:
        print(f"\n➖ NEUTRAL: Skills above seed are stable (not growing, but not regressing)")
    
    # Test a few skills below seed
    if skills_below_seed:
        print(f"\n📈 Sample Skills Below Seed (Should Grow):")
        print(f"   {'Skill':<25} {'Current':<10} {'Change':<10} {'New':<10} {'Seed':<10} {'Status':<15}")
        print("   " + "-"*85)
        
        for skill, current, target, gap in sorted(skills_below_seed, key=lambda x: x[3], reverse=True)[:5]:
            if skill in result['skill_changes']:
                change_info = result['skill_changes'][skill]
                change = change_info['change']
                new_value = change_info['new']
                
                if change > 0:
                    status = "✅ GROWING"
                elif change < 0:
                    status = "❌ DECLINING"
                else:
                    status = "➖ STABLE"
                
                change_str = f"{change:+d}" if change != 0 else "0"
                print(f"   {skill:<25} {current:<10} {change_str:<10} {new_value:<10} {target:<10} {status:<15}")
    
    print("\n" + "="*80)
    
    conn.close()

if __name__ == "__main__":
    test_seed_regression()

