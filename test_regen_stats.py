#!/usr/bin/env python3
"""Test regen generation to verify:
1. Binary skills start at 0
2. 80% right-footed players
3. New dictionaries are used properly
"""

import sys
sys.path.insert(0, '/home/anibalgalindro/SQLiteMigration')
from game_mechanics import generate_proper_regen
import random

# Test data
retired_player = {
    'id': 1,
    'player_name': 'Test Player',
    'registered_position': 7,  # CMF
    'club_id': 1,
    'age': 35
}

print("="*60)
print("TESTING REGEN GENERATION")
print("="*60)

# Generate 100 regens to test statistics
right_footed = 0
left_footed = 0
binary_skills_at_zero = 0
total_binary_skills_checked = 0

binary_skill_list = [
    'dribbling_skill', 'tactical_dribble', 'positioning', 'reaction', 'playmaking',
    'passing', 'scoring', 'one_one_scoring', 'post_player', 'lines', 'middle_shooting',
    'side', 'centre', 'penalties', 'one_touch_pass', 'outside', 'marking', 'sliding',
    'covering', 'd_line_control', 'penalty_stopper', 'one_on_one_stopper', 'long_throw'
]

for i in range(100):
    regen = generate_proper_regen(retired_player, 'pes6_league_db.sqlite')
    
    # Check strong foot
    if regen.get('strong_foot') == 'R':
        right_footed += 1
    elif regen.get('strong_foot') == 'L':
        left_footed += 1
    
    # Check binary skills start at 0
    for skill in binary_skill_list:
        total_binary_skills_checked += 1
        if regen.get(skill, 0) == 0:
            binary_skills_at_zero += 1

print(f"\nStrong Foot Distribution:")
print(f"  Right-footed: {right_footed}% ({right_footed}/100)")
print(f"  Left-footed: {left_footed}% ({left_footed}/100)")
print(f"  Expected: ~80% Right, ~20% Left")

print(f"\nBinary Skills:")
print(f"  Skills starting at 0: {binary_skills_at_zero}/{total_binary_skills_checked} ({binary_skills_at_zero*100/total_binary_skills_checked:.1f}%)")
print(f"  Expected: 100% start at 0")

print(f"\nSample Regen:")
sample_regen = generate_proper_regen(retired_player, 'pes6_league_db.sqlite')
print(f"  Name: {sample_regen.get('player_name')}")
print(f"  Nationality: {sample_regen.get('nationality')}")
print(f"  Strong Foot: {sample_regen.get('strong_foot')}")
print(f"  Binary Skills: dribbling_skill={sample_regen.get('dribbling_skill')}, tactical_dribble={sample_regen.get('tactical_dribble')}")
print(f"  Seed Player: {sample_regen.get('seed_player', 'None')}")

print("\n" + "="*60)
print("TEST COMPLETE")
print("="*60)
