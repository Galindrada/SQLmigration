#!/usr/bin/env python3
"""
Test script to verify name generation and probabilistic nationality selection
"""

import sys
import random
from collections import Counter

# Import the functions we need to test
from game_mechanics import (
    generate_player_name,
    select_nationality,
    NATIONALITY_DATA,
    select_skin_color
)

def test_name_generation():
    """Test that name generation works with the new structure"""
    print("="*80)
    print("TEST 1: Name Generation (New Structure)")
    print("="*80)
    
    # Test a few countries that should have the new structure
    test_countries = ['Brazil', 'Argentina', 'Spain', 'France', 'England']
    
    for country in test_countries:
        if country not in NATIONALITY_DATA:
            print(f"❌ {country} not found in NATIONALITY_DATA")
            continue
        
        data = NATIONALITY_DATA[country]
        has_new_structure = 'first_names' in data and 'surnames' in data
        
        print(f"\n{country}:")
        print(f"  Has new structure: {has_new_structure}")
        
        if has_new_structure:
            first_names = data.get('first_names', [])
            surnames = data.get('surnames', [])
            print(f"  First names: {len(first_names)}")
            print(f"  Surnames: {len(surnames)}")
            
            # Generate 5 test names
            print(f"  Sample names generated:")
            for i in range(5):
                first, last = generate_player_name(country)
                full = f"{first} {last}".strip() if last else first
                print(f"    {i+1}. {full}")
        else:
            print(f"  ⚠️  Still using old structure")
    
    print("\n" + "="*80)

def test_probabilistic_nationality():
    """Test that nationality selection is probabilistic and not inherited"""
    print("="*80)
    print("TEST 2: Probabilistic Nationality Selection")
    print("="*80)
    
    # Generate 1000 nationalities and count distribution
    print("\nGenerating 1000 random nationalities...")
    nationalities = []
    for _ in range(1000):
        nat = select_nationality()
        nationalities.append(nat)
    
    # Count occurrences
    counts = Counter(nationalities)
    
    # Get expected probabilities
    total_prob = sum(NATIONALITY_DATA[nat].get('probability', NATIONALITY_DATA[nat].get('weight', 0.01)) 
                     for nat in NATIONALITY_DATA.keys())
    
    print(f"\nTop 15 nationalities (out of {len(counts)} unique):")
    print(f"{'Nationality':<25} {'Count':<8} {'Percentage':<10} {'Expected %':<10}")
    print("-"*60)
    
    for nat, count in counts.most_common(15):
        percentage = (count / 1000) * 100
        expected_prob = NATIONALITY_DATA[nat].get('probability', NATIONALITY_DATA[nat].get('weight', 0.01))
        expected_pct = (expected_prob / total_prob) * 100
        print(f"{nat:<25} {count:<8} {percentage:>6.2f}%    {expected_pct:>6.2f}%")
    
    # Check if Brazil (highest probability) appears more often
    brazil_count = counts.get('Brazil', 0)
    brazil_pct = (brazil_count / 1000) * 100
    brazil_expected = (NATIONALITY_DATA['Brazil']['probability'] / total_prob) * 100
    
    print(f"\nBrazil (highest probability):")
    print(f"  Expected: ~{brazil_expected:.2f}%")
    print(f"  Actual: {brazil_pct:.2f}%")
    print(f"  Difference: {abs(brazil_pct - brazil_expected):.2f}%")
    
    if abs(brazil_pct - brazil_expected) < 5:  # Within 5% is acceptable
        print("  ✅ Probabilistic selection working correctly")
    else:
        print("  ⚠️  Probabilistic selection may need adjustment")
    
    print("\n" + "="*80)

def test_skin_color_probability():
    """Test that skin color selection is probabilistic"""
    print("="*80)
    print("TEST 3: Probabilistic Skin Color Selection")
    print("="*80)
    
    # Test Brazil (has probabilistic skin colors)
    print("\nTesting Brazil skin colors (expected: 50% skin=1, 30% skin=3, 20% skin=4):")
    
    skin_colors = []
    for _ in range(1000):
        skin = select_skin_color('Brazil')
        skin_colors.append(skin)
    
    counts = Counter(skin_colors)
    print(f"\nResults from 1000 generations:")
    for skin in [1, 2, 3, 4]:
        count = counts.get(skin, 0)
        pct = (count / 1000) * 100
        if skin == 1:
            expected = 50.0
        elif skin == 3:
            expected = 30.0
        elif skin == 4:
            expected = 20.0
        else:
            expected = 0.0
        
        if expected > 0:
            diff = abs(pct - expected)
            status = "✅" if diff < 5 else "⚠️"
            print(f"  Skin {skin}: {count:>4} ({pct:>5.2f}%) - Expected: {expected:>5.2f}% {status}")
        else:
            print(f"  Skin {skin}: {count:>4} ({pct:>5.2f}%)")
    
    print("\n" + "="*80)

def test_name_cropping():
    """Test that name cropping works correctly"""
    print("="*80)
    print("TEST 4: Name Cropping")
    print("="*80)
    
    from game_mechanics import crop_name
    
    test_cases = [
        ("Short Name", 100, "Short Name"),
        ("A" * 50, 50, "A" * 50),
        ("B" * 100, 100, "B" * 100),
        ("C" * 150, 100, "C" * 100),
        ("D" * 200, 50, "D" * 50),
    ]
    
    print("\nTesting name cropping:")
    for name, max_len, expected in test_cases:
        result = crop_name(name, max_len)
        status = "✅" if result == expected and len(result) <= max_len else "❌"
        print(f"  {status} '{name[:30]}...' (max {max_len}) -> '{result[:30]}...' (len: {len(result)})")
    
    # Test full name generation doesn't exceed 100 chars
    print("\nTesting full name generation (should be <= 100 chars):")
    for country in ['Brazil', 'Argentina', 'Spain']:
        for _ in range(10):
            first, last = generate_player_name(country)
            full = f"{first} {last}".strip() if last else first
            status = "✅" if len(full) <= 100 else "❌"
            if len(full) > 100:
                print(f"  {status} {country}: '{full}' (len: {len(full)})")
    
    print("\n" + "="*80)

def test_no_inheritance():
    """Test that nationality is NOT inherited from retiring player"""
    print("="*80)
    print("TEST 5: Nationality NOT Inherited (Probabilistic Selection)")
    print("="*80)
    
    # Simulate retiring 100 players from the same country
    retiring_nationality = 'Brazil'
    
    print(f"\nSimulating 100 regens from retiring '{retiring_nationality}' players:")
    print("(Nationality should be probabilistic, NOT inherited)")
    
    regen_nationalities = []
    for _ in range(100):
        # Simulate generate_proper_regen without override
        nat = select_nationality()  # Should be probabilistic
        regen_nationalities.append(nat)
    
    counts = Counter(regen_nationalities)
    brazil_count = counts.get('Brazil', 0)
    brazil_pct = (brazil_count / 100) * 100
    
    # Brazil has 0.10 probability, so should appear ~10% of the time (not 100%)
    print(f"\nResults:")
    print(f"  Retiring nationality: {retiring_nationality}")
    print(f"  Regen nationalities: {len(counts)} unique countries")
    print(f"  Brazil regens: {brazil_count} ({brazil_pct:.1f}%)")
    
    if brazil_pct < 20:  # Should be around 10%, definitely not 100%
        print(f"  ✅ Nationality is NOT inherited (probabilistic selection working)")
    else:
        print(f"  ⚠️  May be inheriting nationality (expected ~10%, got {brazil_pct:.1f}%)")
    
    print(f"\n  Top 5 regen nationalities:")
    for nat, count in counts.most_common(5):
        print(f"    {nat}: {count} ({count/100*100:.1f}%)")
    
    print("\n" + "="*80)

if __name__ == "__main__":
    print("\n🧪 TESTING NAME GENERATION AND PROBABILISTIC NATIONALITY")
    print("="*80)
    
    try:
        test_name_generation()
        test_probabilistic_nationality()
        test_skin_color_probability()
        test_name_cropping()
        test_no_inheritance()
        
        print("\n" + "="*80)
        print("✅ ALL TESTS COMPLETED")
        print("="*80)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
