#!/usr/bin/env python3
"""
Test script to verify "No Club" players over 30 are eligible for retirement.
"""

import sqlite3
from game_mechanics import check_player_retirement

def test_no_club_retirement():
    """Test that No Club players over 30 can retire regardless of contract"""
    
    print("="*80)
    print("🧪 NO CLUB RETIREMENT TEST")
    print("="*80)
    
    # Connect to database
    conn = sqlite3.connect('pes6_league_db.sqlite')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get No Club players over 30
    cursor.execute("""
        SELECT id, player_name, age, club_id, contract_years_remaining, 
               salary, games_played, registered_position
        FROM players 
        WHERE age >= 30 
          AND (club_id = 141 OR club_id IS NULL)
          AND (draftee = 0 OR draftee IS NULL)
        ORDER BY age DESC
        LIMIT 20
    """)
    
    no_club_players = cursor.fetchall()
    
    print(f"\n📊 Found {len(no_club_players)} No Club players aged 30+")
    print(f"\n{'Name':<25} {'Age':<5} {'Contract':<10} {'Eligible':<12} {'Probability':<12} {'Decision':<15}")
    print("-"*80)
    
    eligible_count = 0
    blocked_count = 0
    will_retire_count = 0
    
    for player in no_club_players:
        player_data = {
            'id': player['id'],
            'player_name': player['player_name'],
            'age': player['age'],
            'registered_position': player['registered_position'],
            'salary': player['salary'],
            'club_id': player['club_id'],
            'contract_years_remaining': player['contract_years_remaining'],
            'games_played': player['games_played']
        }
        
        # Check retirement eligibility
        result = check_player_retirement(player_data)
        
        eligible = "✅ YES" if result['retirement_probability'] > 0 else "❌ NO"
        probability = f"{result['retirement_probability']:.1%}"
        decision = "👴 RETIRING" if result['wants_to_retire'] else "➖ Continuing"
        
        if result['retirement_probability'] > 0:
            eligible_count += 1
        else:
            blocked_count += 1
        
        if result['wants_to_retire']:
            will_retire_count += 1
        
        print(f"{player['player_name']:<25} {player['age']:<5} {player['contract_years_remaining']:<10} {eligible:<12} {probability:<12} {decision:<15}")
    
    print("\n" + "="*80)
    print("📊 SUMMARY")
    print("="*80)
    print(f"Total No Club players (30+): {len(no_club_players)}")
    print(f"✅ Eligible for retirement: {eligible_count}")
    print(f"❌ Blocked by contract: {blocked_count}")
    print(f"👴 Will retire this check: {will_retire_count}")
    
    if blocked_count > 0:
        print(f"\n⚠️  WARNING: {blocked_count} No Club players are still blocked by contract!")
        print("   The fix may not be working correctly.")
    else:
        print(f"\n✅ SUCCESS: All No Club players over 30 are eligible for retirement!")
        print("   Contract status is correctly being ignored for No Club players.")
    
    # Get total count in database
    cursor.execute("""
        SELECT COUNT(*) as total
        FROM players 
        WHERE age >= 30 
          AND (club_id = 141 OR club_id IS NULL)
          AND (draftee = 0 OR draftee IS NULL)
    """)
    total_result = cursor.fetchone()
    total_no_club = total_result['total']
    
    print(f"\n📋 Total No Club players aged 30+ in database: {total_no_club}")
    
    # Compare with players in regular clubs
    cursor.execute("""
        SELECT COUNT(*) as total
        FROM players 
        WHERE age >= 30 
          AND club_id != 141 
          AND club_id IS NOT NULL
          AND (draftee = 0 OR draftee IS NULL)
    """)
    total_with_club = cursor.fetchone()['total']
    
    print(f"📋 Players with clubs aged 30+: {total_with_club}")
    print(f"📋 Total players aged 30+ (eligible for retirement check): {total_no_club + total_with_club}")
    
    print("\n" + "="*80)
    
    conn.close()

if __name__ == "__main__":
    test_no_club_retirement()

