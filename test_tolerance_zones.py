#!/usr/bin/env python3
"""
Test script to demonstrate tolerance zone behavior.
Shows how players can maintain skills 2-3 points above seed with strong development.
"""

import sqlite3
import random
from game_mechanics import calculate_player_skill_development

def create_test_player(seed_value, current_value, age, dev_key, trait_key):
    """Create a test player with specific attributes"""
    return {
        'id': 99999,
        'player_name': 'Test Player',
        'age': age,
        'registered_position': '7',
        'development_key': dev_key,
        'trait_key': trait_key,
        'seed_player': 2048,  # Roma
        'attack': current_value,
        'defense': 70,
        'balance': 70,
        'stamina': 70,
        'top_speed': 70,
        'acceleration': 70,
        'response': 70,
        'agility': 70,
        'dribble_accuracy': 70,
        'dribble_speed': 70,
        'short_pass_accuracy': 70,
        'short_pass_speed': 70,
        'long_pass_accuracy': 70,
        'long_pass_speed': 70,
        'shot_accuracy': 70,
        'shot_power': 70,
        'shot_technique': 70,
        'free_kick_accuracy': 70,
        'swerve': 70,
        'heading': current_value,  # Test skill
        'jump': 70,
        'technique': 70,
        'aggression': 70,
        'mentality': 70,
        'goal_keeping': 40,
        'team_work': 70,
        'consistency': 5,
        'condition_fitness': 5,
        'games_played': 30,
        'goals': 5,
        'assists': 3
    }

def test_tolerance_zones():
    """Test different tolerance zones"""
    
    print("="*100)
    print("🧪 TOLERANCE ZONE TEST - Development Strength vs Overseed Penalty")
    print("="*100)
    
    # Seed value for heading
    seed_value = 60
    
    # Test scenarios: (over_seed, age, dev_key, trait_key, description)
    scenarios = [
        (1, 20, 5245954, 1, "Young player, +1 over seed, strong development"),
        (2, 20, 5245954, 1, "Young player, +2 over seed, strong development"),
        (3, 20, 5245954, 1, "Young player, +3 over seed, strong development"),
        (4, 20, 5245954, 1, "Young player, +4 over seed, strong development"),
        (6, 20, 5245954, 1, "Young player, +6 over seed, strong development"),
        (9, 20, 5245954, 1, "Young player, +9 over seed, strong development"),
        (2, 27, 5245954, 1, "Peak player, +2 over seed, moderate development"),
        (3, 27, 5245954, 1, "Peak player, +3 over seed, moderate development"),
        (2, 32, 5245954, 1, "Declining player, +2 over seed, weak development"),
        (3, 32, 5245954, 1, "Declining player, +3 over seed, weak development"),
    ]
    
    print(f"\n📊 Seed Value: {seed_value}")
    print(f"\n{'Scenario':<50} {'Current':<10} {'Over':<8} {'Change':<10} {'New':<10} {'Zone':<15}")
    print("-"*100)
    
    for over_seed, age, dev_key, trait_key, description in scenarios:
        current_value = seed_value + over_seed
        
        # Create test player
        player = create_test_player(seed_value, current_value, age, dev_key, trait_key)
        
        # Simulate development
        result = calculate_player_skill_development(player, dev_key, trait_key)
        
        # Get heading change
        if 'heading' in result['skill_changes']:
            change = result['skill_changes']['heading']['change']
            new_value = result['skill_changes']['heading']['new']
        else:
            change = 0
            new_value = current_value
        
        # Determine zone
        if over_seed <= 3:
            zone = "✅ TOLERANCE"
        elif over_seed <= 6:
            zone = "⚠️ WARNING"
        else:
            zone = "❌ CRITICAL"
        
        change_str = f"{change:+d}" if change != 0 else "0"
        print(f"{description:<50} {current_value:<10} +{over_seed:<7} {change_str:<10} {new_value:<10} {zone:<15}")
    
    print("\n" + "="*100)
    print("📋 ZONE EXPLANATION")
    print("="*100)
    print()
    print("✅ TOLERANCE ZONE (0-3 over seed):")
    print("   - Player can maintain or slightly improve with strong development")
    print("   - Penalty grows quadratically: small at +1, moderate at +2, strong at +3")
    print("   - Young players with good development can sustain +2 to +3 over seed")
    print("   - Older/declining players will regress even at +2")
    print()
    print("⚠️ WARNING ZONE (4-6 over seed):")
    print("   - Strong penalty, hard to maintain")
    print("   - Requires exceptional development to avoid regression")
    print("   - Most players will regress -2 to -6 per season")
    print()
    print("❌ CRITICAL ZONE (7+ over seed):")
    print("   - Very strong regression")
    print("   - Almost impossible to maintain")
    print("   - Regression of -4 to -10+ per season")
    print()
    print("="*100)

def test_multi_season_trajectory():
    """Simulate multiple seasons to show trajectory"""
    
    print("\n" + "="*100)
    print("📈 MULTI-SEASON TRAJECTORY TEST")
    print("="*100)
    
    seed_value = 60
    starting_value = 63  # +3 over seed
    age = 20
    dev_key = 5245954
    trait_key = 1
    
    print(f"\nScenario: Young player (age {age}) with heading at {starting_value} (seed: {seed_value}, +3 over)")
    print(f"Development: Strong (young, good development key)")
    print()
    print(f"{'Season':<10} {'Age':<8} {'Heading':<10} {'Change':<10} {'Over Seed':<12} {'Status':<20}")
    print("-"*100)
    
    current_value = starting_value
    
    for season in range(1, 11):
        player = create_test_player(seed_value, current_value, age, dev_key, trait_key)
        result = calculate_player_skill_development(player, dev_key, trait_key)
        
        if 'heading' in result['skill_changes']:
            change = result['skill_changes']['heading']['change']
            new_value = result['skill_changes']['heading']['new']
        else:
            change = 0
            new_value = current_value
        
        over_seed = current_value - seed_value
        
        if over_seed <= 3:
            status = "✅ Tolerance zone"
        elif over_seed <= 6:
            status = "⚠️ Warning zone"
        else:
            status = "❌ Critical zone"
        
        change_str = f"{change:+d}" if change != 0 else "0"
        print(f"{season:<10} {age:<8} {current_value:<10} {change_str:<10} +{over_seed:<11} {status:<20}")
        
        current_value = new_value
        age += 1
        
        # Stop if reached seed
        if current_value <= seed_value:
            print(f"\n✅ Reached seed value at season {season}")
            break
    
    print("\n" + "="*100)

if __name__ == "__main__":
    test_tolerance_zones()
    test_multi_season_trajectory()

