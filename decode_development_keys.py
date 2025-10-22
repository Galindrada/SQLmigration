#!/usr/bin/env python3
"""
Script to decode and display development keys and traits.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from game_mechanics import decode_mixed_development_key, decode_development_trait
import sqlite3

def decode_player_keys():
    """Decode and display development keys for sample players."""
    print("🔐 DECODING DEVELOPMENT KEYS AND TRAITS")
    print("=" * 80)
    
    conn = sqlite3.connect('pes6_league_db.sqlite')
    cursor = conn.cursor()
    
    # Get sample players with their keys
    cursor.execute("""
        SELECT player_name, age, registered_position, development_key, trait_key
        FROM players 
        WHERE development_key > 0 
        ORDER BY RANDOM() 
        LIMIT 10
    """)
    
    players = cursor.fetchall()
    conn.close()
    
    print("📊 RAW DATABASE VALUES:")
    print("Player Name | Age | Pos | Development Key | Trait Key")
    print("-" * 70)
    
    for player in players:
        name, age, position, dev_key, trait_key = player
        print(f"{name:<15} | {age:3d} | {position:3s} | {dev_key:15d} | {trait_key:9d}")
    
    print("\n" + "=" * 80)
    print("🔍 DECODED VALUES:")
    print("=" * 80)
    
    for player in players:
        name, age, position, dev_key, trait_key = player
        
        # Decode development key
        profile_info = decode_mixed_development_key(dev_key)
        trait_info = decode_development_trait(trait_key)
        
        print(f"\n👤 {name} ({position}, {age}yo)")
        print(f"   🔑 Development Key: {dev_key}")
        print(f"   🎭 Trait Key: {trait_key}")
        
        # Show profile details
        if profile_info.get('is_mixed', False):
            print(f"   📊 Profile: MIXED")
            profiles = profile_info['profiles']
            weights = profile_info['weights']
            names = profile_info['profile_names']
            
            for i, (profile_id, weight, name) in enumerate(zip(profiles, weights, names)):
                percentage = weight * 100
                print(f"      {i+1}. {name} (ID: {profile_id}) - {percentage:.1f}%")
        else:
            profile_type = profile_info.get('profile_type', 'unknown')
            profile_name = profile_info.get('profile_name', 'unknown')
            base_multiplier = profile_info.get('base_multiplier', 0)
            print(f"   📊 Profile: PURE")
            print(f"      Type: {profile_name} (ID: {profile_type})")
            print(f"      Base Multiplier: {base_multiplier:.3f}")
        
        # Show trait details
        trait_type = trait_info.get('trait_type', 'unknown')
        trait_name = trait_info.get('trait_name', 'unknown')
        trait_desc = trait_info.get('description', 'unknown')
        print(f"   🎭 Trait: {trait_name} (ID: {trait_type})")
        print(f"      Description: {trait_desc}")
        
        print("-" * 60)

def explain_encryption():
    """Explain how the encryption works."""
    print("\n" + "=" * 80)
    print("🔐 ENCRYPTION EXPLANATION")
    print("=" * 80)
    
    print("\n📊 DEVELOPMENT KEY ENCRYPTION:")
    print("   The development_key is an encrypted integer that contains:")
    print("   - Profile type(s) and weights")
    print("   - Base multiplier (for pure profiles)")
    print("   - Mixed profile flag")
    
    print("\n🎭 TRAIT KEY ENCRYPTION:")
    print("   The trait_key is a simple integer (0-3) representing:")
    print("   0 = regular (70% of players)")
    print("   1 = jokester (15% of players)")
    print("   2 = sharpie (10% of players)")
    print("   3 = genetic_freak (5% of players)")
    
    print("\n🔍 ENCRYPTION DETAILS:")
    print("   - Development keys use bit manipulation for mixed profiles")
    print("   - High bit (0x80000000) indicates mixed profile")
    print("   - Profile IDs and weights are packed into 32-bit integer")
    print("   - Pure profiles use simple formula: profile_type * 1000 + multiplier * 100")
    print("   - Trait keys are stored as-is (no encryption needed)")

if __name__ == "__main__":
    decode_player_keys()
    explain_encryption() 