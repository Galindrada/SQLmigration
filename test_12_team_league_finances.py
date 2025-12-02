#!/usr/bin/env python3
"""
Test 12-Team League Financial Simulation

Simulates a full season of a 12-team league to analyze financial distributions.
Tests both Tier 1 and Tier 2 scenarios.
"""

import sqlite3
import random
from cpu_league_finances import (
    calculate_game_finances,
    get_team_market_value,
    get_team_total_salaries,
    get_team_star_players
)

def simulate_12_team_league(tier=1):
    """Simulate a 12-team league season"""
    
    print("="*100)
    print(f"💰 12-TEAM LEAGUE FINANCIAL SIMULATION - TIER {tier}")
    print("="*100)
    
    conn = sqlite3.connect('pes6_league_db.sqlite')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # Get 12 teams with highest market values
        cursor.execute("""
            SELECT t.id, t.club_name
            FROM teams t
            JOIN (
                SELECT club_id, SUM(market_value) as total_mv
                FROM players
                WHERE club_id IS NOT NULL AND club_id != 141
                GROUP BY club_id
                ORDER BY total_mv DESC
                LIMIT 12
            ) tm ON t.id = tm.club_id
            ORDER BY tm.total_mv DESC
        """)
        
        teams = [dict(row) for row in cursor.fetchall()]
        
        if len(teams) < 12:
            print(f"❌ Not enough teams found (only {len(teams)})")
            return
        
        print(f"\n📋 Selected Teams:")
        for i, team in enumerate(teams, 1):
            mv = get_team_market_value(cursor, team['id'])
            salaries = get_team_total_salaries(cursor, team['id'])
            stars = get_team_star_players(cursor, team['id'])
            print(f"   {i:2d}. {team['club_name']:<30} MV: €{mv:>12,}  Salaries: €{salaries:>12,}  Stars: {stars}")
        
        # Simulate full season (each team plays each other twice = 22 games per team)
        # Total games = 12 * 11 = 132 games
        
        team_finances = {team['id']: {
            'team_name': team['club_name'],
            'games': 0,
            'home_games': 0,
            'away_games': 0,
            'wins': 0,
            'draws': 0,
            'losses': 0,
            'attendance': 0,
            'sponsor': 0,
            'merchandise': 0,
            'tv_rights': 0,
            'prizes': 0,
            'total': 0
        } for team in teams}
        
        print(f"\n🔄 Simulating full season...")
        print(f"   Total games: 132 (each team plays 22 games)")
        
        games_simulated = 0
        
        # Each team plays each other twice (home and away)
        for i, home_team in enumerate(teams):
            for j, away_team in enumerate(teams):
                if i == j:
                    continue
                
                # Simulate match result (random scores)
                home_score = random.randint(0, 4)
                away_score = random.randint(0, 4)
                
                # Calculate finances
                finances = calculate_game_finances(
                    cursor,
                    game_id=0,  # Dummy ID
                    division_id=0,  # Dummy ID
                    division_name="Division 1",  # For sponsor calculation
                    home_team_id=home_team['id'],
                    away_team_id=away_team['id'],
                    home_team_name=home_team['club_name'],
                    away_team_name=away_team['club_name'],
                    home_score=home_score,
                    away_score=away_score
                )
                
                # Override tier if testing Tier 2
                if tier == 2:
                    # Recalculate with tier 2
                    from cpu_league_finances import (
                        calculate_attendance_revenue,
                        calculate_sponsor_premium,
                        calculate_merchandise_revenue,
                        calculate_tv_rights_revenue,
                        calculate_prize_bonus
                    )
                    
                    home_mv = finances['home_market_value']
                    away_mv = finances['away_market_value']
                    home_salaries = finances['home_total_salaries']
                    away_salaries = finances['away_total_salaries']
                    home_stars = finances['home_star_players']
                    away_stars = finances['away_star_players']
                    home_position = finances['home_league_position']
                    total_teams = 12
                    
                    finances['home_attendance_revenue'] = calculate_attendance_revenue(home_mv, home_position, total_teams, tier)
                    finances['home_sponsor_premium'] = calculate_sponsor_premium(tier)
                    finances['away_sponsor_premium'] = calculate_sponsor_premium(tier)
                    finances['home_merchandise_revenue'] = calculate_merchandise_revenue(home_mv, home_stars, tier)
                    finances['away_merchandise_revenue'] = calculate_merchandise_revenue(away_mv, away_stars, tier)
                    finances['home_tv_rights_revenue'] = calculate_tv_rights_revenue(home_salaries, tier)
                    finances['away_tv_rights_revenue'] = calculate_tv_rights_revenue(away_salaries, tier)
                    home_prize, away_prize = calculate_prize_bonus(home_score, away_score, tier)
                    finances['home_prize_bonus'] = home_prize
                    finances['away_prize_bonus'] = away_prize
                    finances['home_total_earnings'] = (finances['home_attendance_revenue'] + 
                                                       finances['home_sponsor_premium'] + 
                                                       finances['home_merchandise_revenue'] + 
                                                       finances['home_tv_rights_revenue'] + 
                                                       finances['home_prize_bonus'])
                    finances['away_total_earnings'] = (finances['away_sponsor_premium'] + 
                                                       finances['away_merchandise_revenue'] + 
                                                       finances['away_tv_rights_revenue'] + 
                                                       finances['away_prize_bonus'])
                
                # Update home team stats
                team_finances[home_team['id']]['games'] += 1
                team_finances[home_team['id']]['home_games'] += 1
                team_finances[home_team['id']]['attendance'] += finances['home_attendance_revenue']
                team_finances[home_team['id']]['sponsor'] += finances['home_sponsor_premium']
                team_finances[home_team['id']]['merchandise'] += finances['home_merchandise_revenue']
                team_finances[home_team['id']]['tv_rights'] += finances['home_tv_rights_revenue']
                team_finances[home_team['id']]['prizes'] += finances['home_prize_bonus']
                team_finances[home_team['id']]['total'] += finances['home_total_earnings']
                
                # Update away team stats
                team_finances[away_team['id']]['games'] += 1
                team_finances[away_team['id']]['away_games'] += 1
                team_finances[away_team['id']]['sponsor'] += finances['away_sponsor_premium']
                team_finances[away_team['id']]['merchandise'] += finances['away_merchandise_revenue']
                team_finances[away_team['id']]['tv_rights'] += finances['away_tv_rights_revenue']
                team_finances[away_team['id']]['prizes'] += finances['away_prize_bonus']
                team_finances[away_team['id']]['total'] += finances['away_total_earnings']
                
                # Update match results
                if home_score > away_score:
                    team_finances[home_team['id']]['wins'] += 1
                    team_finances[away_team['id']]['losses'] += 1
                elif away_score > home_score:
                    team_finances[away_team['id']]['wins'] += 1
                    team_finances[home_team['id']]['losses'] += 1
                else:
                    team_finances[home_team['id']]['draws'] += 1
                    team_finances[away_team['id']]['draws'] += 1
                
                games_simulated += 1
        
        print(f"   ✅ Simulated {games_simulated} games")
        
        # Display results
        print(f"\n" + "="*100)
        print(f"📊 SEASON FINANCIAL RESULTS - TIER {tier}")
        print("="*100)
        
        # Sort by total revenue
        sorted_teams = sorted(team_finances.values(), key=lambda x: x['total'], reverse=True)
        
        print(f"\n{'Rank':<5} {'Team':<30} {'Games':<7} {'Total Revenue':<18} {'Per Game':<15}")
        print("-"*100)
        
        for rank, team in enumerate(sorted_teams, 1):
            per_game = team['total'] / team['games'] if team['games'] > 0 else 0
            print(f"{rank:<5} {team['team_name']:<30} {team['games']:<7} €{team['total']:>15,}  €{per_game:>13,.0f}")
        
        # Detailed breakdown for top 3
        print(f"\n" + "="*100)
        print(f"💵 DETAILED BREAKDOWN - TOP 3 TEAMS")
        print("="*100)
        
        for rank, team in enumerate(sorted_teams[:3], 1):
            print(f"\n{rank}. {team['team_name']}")
            print(f"   Games: {team['games']} ({team['home_games']} home, {team['away_games']} away)")
            print(f"   Record: {team['wins']}W-{team['draws']}D-{team['losses']}L")
            print(f"   ---")
            print(f"   🎟️  Attendance:   €{team['attendance']:>15,}  ({team['attendance']/team['total']*100:>5.1f}%)")
            print(f"   🤝 Sponsor:      €{team['sponsor']:>15,}  ({team['sponsor']/team['total']*100:>5.1f}%)")
            print(f"   👕 Merchandise:  €{team['merchandise']:>15,}  ({team['merchandise']/team['total']*100:>5.1f}%)")
            print(f"   📺 TV Rights:    €{team['tv_rights']:>15,}  ({team['tv_rights']/team['total']*100:>5.1f}%)")
            print(f"   🏆 Prizes:       €{team['prizes']:>15,}  ({team['prizes']/team['total']*100:>5.1f}%)")
            print(f"   💰 TOTAL:        €{team['total']:>15,}")
            print(f"   📊 Per Game:     €{team['total']/team['games']:>15,.0f}")
        
        # League-wide statistics
        print(f"\n" + "="*100)
        print(f"📈 LEAGUE-WIDE STATISTICS")
        print("="*100)
        
        total_revenue = sum(t['total'] for t in sorted_teams)
        avg_revenue = total_revenue / len(sorted_teams)
        max_revenue = sorted_teams[0]['total']
        min_revenue = sorted_teams[-1]['total']
        
        print(f"   Total Revenue Generated: €{total_revenue:,}")
        print(f"   Average per Team:        €{avg_revenue:,.0f}")
        print(f"   Highest (#{1}):          €{max_revenue:,} ({sorted_teams[0]['team_name']})")
        print(f"   Lowest (#{len(sorted_teams)}):           €{min_revenue:,} ({sorted_teams[-1]['team_name']})")
        print(f"   Revenue Gap:             €{max_revenue - min_revenue:,} ({(max_revenue/min_revenue):.2f}x)")
        
        # Component breakdown
        total_attendance = sum(t['attendance'] for t in sorted_teams)
        total_sponsor = sum(t['sponsor'] for t in sorted_teams)
        total_merch = sum(t['merchandise'] for t in sorted_teams)
        total_tv = sum(t['tv_rights'] for t in sorted_teams)
        total_prizes = sum(t['prizes'] for t in sorted_teams)
        
        print(f"\n   Revenue Breakdown:")
        print(f"   🎟️  Attendance:   €{total_attendance:>15,}  ({total_attendance/total_revenue*100:>5.1f}%)")
        print(f"   🤝 Sponsor:      €{total_sponsor:>15,}  ({total_sponsor/total_revenue*100:>5.1f}%)")
        print(f"   👕 Merchandise:  €{total_merch:>15,}  ({total_merch/total_revenue*100:>5.1f}%)")
        print(f"   📺 TV Rights:    €{total_tv:>15,}  ({total_tv/total_revenue*100:>5.1f}%)")
        print(f"   🏆 Prizes:       €{total_prizes:>15,}  ({total_prizes/total_revenue*100:>5.1f}%)")
        
        print("\n" + "="*100)
        
        return sorted_teams
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    # Test Tier 1
    print("\n")
    tier1_results = simulate_12_team_league(tier=1)
    
    # Test Tier 2
    print("\n\n")
    tier2_results = simulate_12_team_league(tier=2)
    
    # Compare tiers
    if tier1_results and tier2_results:
        print("\n" + "="*100)
        print("⚖️  TIER COMPARISON")
        print("="*100)
        
        tier1_total = sum(t['total'] for t in tier1_results)
        tier2_total = sum(t['total'] for t in tier2_results)
        
        print(f"\nTier 1 Total Revenue: €{tier1_total:,}")
        print(f"Tier 2 Total Revenue: €{tier2_total:,}")
        print(f"Tier 2 as % of Tier 1: {tier2_total/tier1_total*100:.1f}%")
        print(f"Reduction: {(1 - tier2_total/tier1_total)*100:.1f}%")
        print("\n" + "="*100)

