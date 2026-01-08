#!/usr/bin/env python3
"""
Test script to verify regen generation:
1. New NATIONALITY_DATA dictionaries are being used
2. 80% right-footed players are generated
3. Probabilistic nationality selection works
4. Probabilistic skin color works
5. Name generation with new structure works
"""

import sys
import random
from game_mechanics import (
    NATIONALITY_DATA,
    select_nationality,
    generate_player_name,
    select_skin_color,
    generate_proper_regen
)

def test_regen_generation(num_tests=100):
    """Test regen generation with multiple samples"""
    print("="*80)
    print("🧪 TESTING REGEN GENERATION")
    print("="*80)
    
    # Test data
    test_retired_player = {
        'id': 9999,
        'player_name': 'Test Retired Player',
        'club_id': 1,
        'registered_position': 4,  # Center-Midfielder
        'age': 35
    }
    
    results = {
        'nationalities': {},
        'strong_foot': {'R': 0, 'L': 0},
        'skin_colors': {1: 0, 2: 0, 3: 0, 4: 0},
        'name_types': {'single_first': 0, 'single_surname': 0, 'two_part': 0},
        'name_lengths': [],
        'countries_used': set()
    }
    
    print(f"\nGenerating {num_tests} regens...\n")
    
    for i in range(num_tests):
        try:
            # Generate regen
            regen = generate_proper_regen(test_retired_player, db_path='pes6_league_db.sqlite')
            
            # Track nationality
            nat = regen['nationality']
            results['nationalities'][nat] = results['nationalities'].get(nat, 0) + 1
            results['countries_used'].add(nat)
            
            # Track strong foot
            foot = regen['strong_foot']
            results['strong_foot'][foot] = results['strong_foot'].get(foot, 0) + 1
            
            # Track skin color
            skin = regen['skin_color']
            results['skin_colors'][skin] = results['skin_colors'].get(skin, 0) + 1
            
            # Track name structure
            full_name = regen['player_name']
            name_parts = full_name.split()
            if len(name_parts) == 1:
                # Check if it's a first name or surname by checking against NATIONALITY_DATA
                nat_data = NATIONALITY_DATA.get(nat, {})
                first_names = nat_data.get('first_names', [])
                surnames = nat_data.get('surnames', [])
                if name_parts[0] in first_names:
                    results['name_types']['single_first'] += 1
                elif name_parts[0] in surnames:
                    results['name_types']['single_surname'] += 1
                else:
                    results['name_types']['single_first'] += 1  # Default assumption
            else:
                results['name_types']['two_part'] += 1
            
            # Track name length
            results['name_lengths'].append(len(full_name))
            
        except Exception as e:
            print(f"❌ Error generating regen {i+1}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Print results
    print("\n" + "="*80)
    print("📊 RESULTS")
    print("="*80)
    
    # Strong foot distribution
    print(f"\n🦶 STRONG FOOT DISTRIBUTION:")
    total_foot = sum(results['strong_foot'].values())
    right_pct = (results['strong_foot']['R'] / total_foot * 100) if total_foot > 0 else 0
    left_pct = (results['strong_foot']['L'] / total_foot * 100) if total_foot > 0 else 0
    print(f"  Right: {results['strong_foot']['R']} ({right_pct:.1f}%)")
    print(f"  Left:  {results['strong_foot']['L']} ({left_pct:.1f}%)")
    if 75 <= right_pct <= 85:
        print(f"  ✅ PASS: Right foot percentage is within expected range (75-85%)")
    else:
        print(f"  ❌ FAIL: Right foot percentage should be ~80% (got {right_pct:.1f}%)")
    
    # Nationality distribution
    print(f"\n🌍 NATIONALITY DISTRIBUTION (top 10):")
    sorted_nats = sorted(results['nationalities'].items(), key=lambda x: x[1], reverse=True)
    for nat, count in sorted_nats[:10]:
        pct = (count / num_tests * 100)
        nat_data = NATIONALITY_DATA.get(nat, {})
        expected_prob = nat_data.get('probability', 0) * 100
        print(f"  {nat:<25}: {count:3d} ({pct:5.1f}%) [expected: {expected_prob:.1f}%]")
    
    # Skin color distribution
    print(f"\n🎨 SKIN COLOR DISTRIBUTION:")
    total_skin = sum(results['skin_colors'].values())
    for skin in sorted(results['skin_colors'].keys()):
        count = results['skin_colors'][skin]
        pct = (count / total_skin * 100) if total_skin > 0 else 0
        print(f"  Skin {skin}: {count:3d} ({pct:5.1f}%)")
    
    # Name structure
    print(f"\n📝 NAME STRUCTURE:")
    total_names = sum(results['name_types'].values())
    for name_type, count in results['name_types'].items():
        pct = (count / total_names * 100) if total_names > 0 else 0
        print(f"  {name_type.replace('_', ' ').title()}: {count:3d} ({pct:5.1f}%)")
    
    # Name lengths
    if results['name_lengths']:
        avg_length = sum(results['name_lengths']) / len(results['name_lengths'])
        max_length = max(results['name_lengths'])
        print(f"\n📏 NAME LENGTHS:")
        print(f"  Average: {avg_length:.1f} characters")
        print(f"  Maximum: {max_length} characters")
        if max_length <= 15:
            print(f"  ✅ PASS: All names are within 15 character limit")
        else:
            print(f"  ❌ FAIL: Some names exceed 15 character limit (max: {max_length})")
    
    # Countries used
    print(f"\n🌐 COUNTRIES USED: {len(results['countries_used'])} different countries")
    print(f"  Total countries in NATIONALITY_DATA: {len(NATIONALITY_DATA)}")
    
    # Check if new structure is being used
    print(f"\n🔍 STRUCTURE VERIFICATION:")
    sample_countries = list(results['countries_used'])[:5]
    for country in sample_countries:
        nat_data = NATIONALITY_DATA.get(country, {})
        has_probability = 'probability' in nat_data
        has_first_names = 'first_names' in nat_data
        has_surnames = 'surnames' in nat_data
        has_skin_list = isinstance(nat_data.get('skin_color'), list)
        
        status = "✅" if (has_probability and has_first_names and has_surnames and has_skin_list) else "❌"
        print(f"  {status} {country}: prob={has_probability}, first_names={has_first_names}, surnames={has_surnames}, skin_list={has_skin_list}")
    
    print("\n" + "="*80)
    print("✅ TEST COMPLETE")
    print("="*80)

if __name__ == "__main__":
    num_tests = 100
    if len(sys.argv) > 1:
        try:
            num_tests = int(sys.argv[1])
        except ValueError:
            print("Usage: python test_regen_generation.py [num_tests]")
            sys.exit(1)
    
    test_regen_generation(num_tests)

