#!/usr/bin/env python3
"""
Test script to show what the seed goalkeeper assignment will do
WITHOUT actually making changes to the database.
"""

import sqlite3
import os
import random

def test_seed_assignment():
    """Show what would happen when assigning seeds"""
    
    print("="*80)
    print("🧤 SEED GOALKEEPER ASSIGNMENT TEST (DRY RUN)")
    print("="*80)
    
    # Check if databases exist
    if not os.path.exists('pes6_league_db.sqlite'):
        print("❌ pes6_league_db.sqlite not found")
        return
    
    if not os.path.exists('original.sqlite'):
        print("❌ original.sqlite not found")
        return
    
    # Connect to original database first to get name mappings
    original_conn = sqlite3.connect('original.sqlite')
    original_conn.row_factory = sqlite3.Row
    original_cursor = original_conn.cursor()
    
    # Get all players from original.sqlite for name comparison
    original_cursor.execute("""
        SELECT id, player_name
        FROM players
    """)
    original_players = {row['id']: row['player_name'] for row in original_cursor.fetchall()}
    
    # Connect to current database
    conn = sqlite3.connect('pes6_league_db.sqlite')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get goalkeepers without seeds
    cursor.execute("""
        SELECT id, player_name, goal_keeping, overall, seed_player
        FROM players
        WHERE registered_position = 0 
        AND (seed_player IS NULL OR seed_player = 0)
        ORDER BY goal_keeping DESC
    """)
    keepers_without_seeds = cursor.fetchall()
    
    # Filter out goalkeepers whose names match the original database
    eligible_keepers = []
    excluded_keepers = []
    
    for keeper in keepers_without_seeds:
        keeper_id = keeper['id']
        keeper_name = keeper['player_name']
        
        # Check if this ID exists in original.sqlite
        if keeper_id in original_players:
            original_name = original_players[keeper_id]
            
            # If names match, exclude this keeper (it's an original player)
            if keeper_name == original_name:
                excluded_keepers.append(keeper)
                continue
        
        # Name mismatch or ID doesn't exist in original - eligible for seed
        eligible_keepers.append(keeper)
    
    total_without_seeds = len(keepers_without_seeds)
    total_eligible = len(eligible_keepers)
    total_excluded = len(excluded_keepers)
    
    conn.close()
    
    print(f"\n📊 CURRENT STATE:")
    print(f"   Total goalkeepers without seeds: {total_without_seeds}")
    print(f"   ✅ Eligible (name mismatch/regen): {total_eligible}")
    print(f"   ❌ Excluded (original players): {total_excluded}")
    
    if excluded_keepers:
        print(f"\n   Sample EXCLUDED goalkeepers (original players, same name):")
        print(f"   {'ID':<8} {'Name':<30} {'GK':<5} {'OVR':<5}")
        print("   " + "-"*50)
        for keeper in excluded_keepers[:5]:
            print(f"   {keeper['id']:<8} {keeper['player_name']:<30} {keeper['goal_keeping']:<5} {keeper['overall']:<5}")
    
    if eligible_keepers:
        print(f"\n   Sample ELIGIBLE goalkeepers (will receive seeds):")
        print(f"   {'ID':<8} {'Name':<30} {'GK':<5} {'OVR':<5}")
        print("   " + "-"*50)
        for keeper in eligible_keepers[:10]:
            print(f"   {keeper['id']:<8} {keeper['player_name']:<30} {keeper['goal_keeping']:<5} {keeper['overall']:<5}")
    
    # Get elite goalkeepers
    original_cursor.execute("""
        SELECT id, player_name, goal_keeping, overall
        FROM players
        WHERE registered_position = 0 
        AND goal_keeping > 82
        ORDER BY goal_keeping DESC
    """)
    elite_keepers = original_cursor.fetchall()
    original_conn.close()
    
    print(f"\n📊 AVAILABLE SEEDS (from original.sqlite):")
    print(f"   Total elite goalkeepers (GK > 82): {len(elite_keepers)}")
    print(f"\n   Top 10 elite goalkeepers:")
    print(f"   {'ID':<8} {'Name':<30} {'GK':<5} {'OVR':<5}")
    print("   " + "-"*50)
    for i, keeper in enumerate(elite_keepers[:10]):
        print(f"   {keeper['id']:<8} {keeper['player_name']:<30} {keeper['goal_keeping']:<5} {keeper['overall']:<5}")
    
    print(f"\n✅ READY TO ASSIGN:")
    print(f"   {total_eligible} goalkeepers will receive seed_player values")
    print(f"   {total_excluded} original players will be EXCLUDED (same name in both databases)")
    print(f"   Seeds will be randomly selected from {len(elite_keepers)} elite goalkeepers")
    print(f"\n💡 To run the actual assignment:")
    print(f"   1. Run: python3 add_seed_goalkeepers.py")
    print(f"   2. Or use option 22 in team_management.py menu")
    print(f"\n📝 NOTE: Only goalkeepers with NAME MISMATCHES get seeds")
    print(f"   (Regens/replacements only, not original players)")
    print("="*80)

if __name__ == "__main__":
    test_seed_assignment()

