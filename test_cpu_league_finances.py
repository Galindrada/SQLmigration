#!/usr/bin/env python3
"""
Test CPU League Financial System

Tests the financial calculations for CPU league games.
"""

import sqlite3
from cpu_league_finances import (
    calculate_game_finances,
    get_team_market_value,
    get_team_star_players,
    calculate_attendance_revenue,
    calculate_sponsor_premium,
    calculate_merchandise_revenue,
    calculate_prize_bonus
)

def test_financial_system():
    """Test the financial system with real data"""
    
    print("="*100)
    print("💰 CPU LEAGUE FINANCIAL SYSTEM TEST")
    print("="*100)
    
    conn = sqlite3.connect('pes6_league_db.sqlite')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # Get a sample played game
        cursor.execute("""
            SELECT lg.*, d.name as division_name, l.name as league_name
            FROM league_games lg
            JOIN divisions d ON lg.division_id = d.id
            JOIN leagues l ON d.league_id = l.id
            WHERE lg.is_played = 1 
              AND l.name != 'Colados League'
            ORDER BY lg.id DESC
            LIMIT 1
        """)
        
        game = cursor.fetchone()
        
        if not game:
            print("❌ No played CPU league games found")
            print("   Please simulate a CPU league game first")
            return
        
        game_dict = dict(game)
        
        print(f"\n📋 Test Game:")
        print(f"   Game ID: {game_dict['id']}")
        print(f"   Division: {game_dict['division_name']}")
        print(f"   Match: {game_dict['home_team_name']} vs {game_dict['away_team_name']}")
        print(f"   Score: {game_dict['home_score']} - {game_dict['away_score']}")
        
        # Calculate finances
        print(f"\n🔄 Calculating finances...")
        
        finances = calculate_game_finances(
            cursor,
            game_dict['id'],
            game_dict['division_id'],
            game_dict['division_name'],
            game_dict['home_team_id'],
            game_dict['away_team_id'],
            game_dict['home_team_name'],
            game_dict['away_team_name'],
            game_dict['home_score'],
            game_dict['away_score']
        )
        
        # Display results
        print(f"\n" + "="*100)
        print(f"💵 FINANCIAL BREAKDOWN")
        print("="*100)
        
        print(f"\n🏠 HOME TEAM: {game_dict['home_team_name']}")
        print(f"   Market Value: €{finances['home_market_value']:,}")
        print(f"   Star Players (>€50M): {finances['home_star_players']}")
        print(f"   League Position: {finances['home_league_position']}/{finances['total_teams']}")
        print(f"   ---")
        print(f"   🎟️  Attendance Revenue: €{finances['home_attendance_revenue']:,}")
        print(f"   🤝 Sponsor Premium: €{finances['home_sponsor_premium']:,}")
        print(f"   👕 Merchandise Revenue: €{finances['home_merchandise_revenue']:,}")
        print(f"   🏆 Prize Bonus: €{finances['home_prize_bonus']:,}")
        print(f"   💰 TOTAL EARNINGS: €{finances['home_total_earnings']:,}")
        
        print(f"\n✈️  AWAY TEAM: {game_dict['away_team_name']}")
        print(f"   Market Value: €{finances['away_market_value']:,}")
        print(f"   Star Players (>€50M): {finances['away_star_players']}")
        print(f"   ---")
        print(f"   🤝 Sponsor Premium: €{finances['away_sponsor_premium']:,}")
        print(f"   👕 Merchandise Revenue: €{finances['away_merchandise_revenue']:,}")
        print(f"   🏆 Prize Bonus: €{finances['away_prize_bonus']:,}")
        print(f"   💰 TOTAL EARNINGS: €{finances['away_total_earnings']:,}")
        
        print(f"\n📊 DIVISION INFO")
        print(f"   Division: {game_dict['division_name']}")
        print(f"   Tier: {finances['division_tier']} ({'Division 1' if finances['division_tier'] == 1 else 'Division 2' if finances['division_tier'] == 2 else 'Division 3+'})")
        print(f"   Total Teams: {finances['total_teams']}")
        
        # Show match result impact
        if game_dict['home_score'] > game_dict['away_score']:
            result = f"🏆 HOME WIN - Home gets €{finances['home_prize_bonus']:,} bonus"
        elif game_dict['away_score'] > game_dict['home_score']:
            result = f"🏆 AWAY WIN - Away gets €{finances['away_prize_bonus']:,} bonus"
        else:
            result = f"🤝 DRAW - Both teams get €{finances['home_prize_bonus']:,}"
        
        print(f"\n🎯 Match Result: {result}")
        
        # Calculate percentages
        home_attendance_pct = (finances['home_attendance_revenue'] / finances['home_total_earnings'] * 100) if finances['home_total_earnings'] > 0 else 0
        home_sponsor_pct = (finances['home_sponsor_premium'] / finances['home_total_earnings'] * 100) if finances['home_total_earnings'] > 0 else 0
        home_merch_pct = (finances['home_merchandise_revenue'] / finances['home_total_earnings'] * 100) if finances['home_total_earnings'] > 0 else 0
        home_prize_pct = (finances['home_prize_bonus'] / finances['home_total_earnings'] * 100) if finances['home_total_earnings'] > 0 else 0
        
        print(f"\n📈 HOME TEAM REVENUE BREAKDOWN:")
        print(f"   Attendance: {home_attendance_pct:.1f}%")
        print(f"   Sponsor: {home_sponsor_pct:.1f}%")
        print(f"   Merchandise: {home_merch_pct:.1f}%")
        print(f"   Prize: {home_prize_pct:.1f}%")
        
        print("\n" + "="*100)
        print("✅ Financial calculations completed successfully!")
        print("="*100)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    test_financial_system()

