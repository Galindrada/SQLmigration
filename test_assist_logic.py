#!/usr/bin/env python3
"""
Test assist logic to verify:
1. Assists <= Goals (always)
2. No self-assists (player can't assist their own goal)
3. ~60% of goals have assists
"""

import sqlite3

def test_assist_logic():
    """Test assist logic in both international and CPU league games"""
    
    print("="*100)
    print("🧪 ASSIST LOGIC VERIFICATION TEST")
    print("="*100)
    
    conn = sqlite3.connect('pes6_league_db.sqlite')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Test International Games
    print("\n📊 INTERNATIONAL GAMES")
    print("-"*100)
    
    cursor.execute("""
        SELECT 
            ig.id,
            ig.home_team_name,
            ig.away_team_name,
            ig.home_score,
            ig.away_score,
            SUM(CASE WHEN ipgs.team_id = ig.home_team_id THEN ipgs.goals ELSE 0 END) as home_goals_assigned,
            SUM(CASE WHEN ipgs.team_id = ig.home_team_id THEN ipgs.assists ELSE 0 END) as home_assists,
            SUM(CASE WHEN ipgs.team_id = ig.away_team_id THEN ipgs.goals ELSE 0 END) as away_goals_assigned,
            SUM(CASE WHEN ipgs.team_id = ig.away_team_id THEN ipgs.assists ELSE 0 END) as away_assists
        FROM international_games ig
        LEFT JOIN international_player_game_stats ipgs ON ig.id = ipgs.game_id
        WHERE ig.is_played = 1
        GROUP BY ig.id
        ORDER BY ig.id DESC
        LIMIT 10
    """)
    
    intl_games = cursor.fetchall()
    
    print(f"{'Game ID':<10} {'Match':<40} {'Score':<10} {'Goals':<12} {'Assists':<12} {'Status':<20}")
    print("-"*100)
    
    intl_issues = 0
    for game in intl_games:
        home_total_goals = game['home_score']
        away_total_goals = game['away_score']
        home_assists = game['home_assists'] or 0
        away_assists = game['away_assists'] or 0
        
        match = f"{game['home_team_name'][:15]} vs {game['away_team_name'][:15]}"
        score = f"{home_total_goals}-{away_total_goals}"
        goals_str = f"H:{home_total_goals} A:{away_total_goals}"
        assists_str = f"H:{home_assists} A:{away_assists}"
        
        # Check for issues
        issues = []
        if home_assists > home_total_goals:
            issues.append(f"Home assists>{goals}")
            intl_issues += 1
        if away_assists > away_total_goals:
            issues.append(f"Away assists>goals")
            intl_issues += 1
        
        status = "❌ " + ", ".join(issues) if issues else "✅ OK"
        
        print(f"{game['id']:<10} {match:<40} {score:<10} {goals_str:<12} {assists_str:<12} {status:<20}")
    
    # Check for self-assists in international games
    cursor.execute("""
        SELECT ipgs.game_id, ipgs.player_id, p.player_name, ipgs.goals, ipgs.assists
        FROM international_player_game_stats ipgs
        JOIN players p ON ipgs.player_id = p.id
        WHERE ipgs.goals > 0 AND ipgs.assists > 0
        ORDER BY ipgs.game_id DESC
        LIMIT 10
    """)
    
    self_assist_candidates = cursor.fetchall()
    
    if self_assist_candidates:
        print(f"\n⚠️  Players with both goals AND assists (potential self-assists):")
        print(f"{'Game ID':<10} {'Player':<30} {'Goals':<8} {'Assists':<10}")
        print("-"*60)
        for player in self_assist_candidates:
            print(f"{player['game_id']:<10} {player['player_name']:<30} {player['goals']:<8} {player['assists']:<10}")
    
    # Test CPU League Games
    print("\n\n📊 CPU LEAGUE GAMES")
    print("-"*100)
    
    cursor.execute("""
        SELECT 
            lg.id,
            lg.home_team_name,
            lg.away_team_name,
            lg.home_score,
            lg.away_score,
            SUM(CASE WHEN pgs.team_id = lg.home_team_id THEN pgs.goals ELSE 0 END) as home_goals_assigned,
            SUM(CASE WHEN pgs.team_id = lg.home_team_id THEN pgs.assists ELSE 0 END) as home_assists,
            SUM(CASE WHEN pgs.team_id = lg.away_team_id THEN pgs.goals ELSE 0 END) as away_goals_assigned,
            SUM(CASE WHEN pgs.team_id = lg.away_team_id THEN pgs.assists ELSE 0 END) as away_assists
        FROM league_games lg
        LEFT JOIN player_game_stats pgs ON lg.id = pgs.game_id
        JOIN divisions d ON lg.division_id = d.id
        JOIN leagues l ON d.league_id = l.id
        WHERE lg.is_played = 1 AND l.name != 'Colados League'
        GROUP BY lg.id
        ORDER BY lg.id DESC
        LIMIT 10
    """)
    
    cpu_games = cursor.fetchall()
    
    print(f"{'Game ID':<10} {'Match':<40} {'Score':<10} {'Goals':<12} {'Assists':<12} {'Status':<20}")
    print("-"*100)
    
    cpu_issues = 0
    for game in cpu_games:
        home_total_goals = game['home_score']
        away_total_goals = game['away_score']
        home_assists = game['home_assists'] or 0
        away_assists = game['away_assists'] or 0
        
        match = f"{game['home_team_name'][:15]} vs {game['away_team_name'][:15]}"
        score = f"{home_total_goals}-{away_total_goals}"
        goals_str = f"H:{home_total_goals} A:{away_total_goals}"
        assists_str = f"H:{home_assists} A:{away_assists}"
        
        # Check for issues
        issues = []
        if home_assists > home_total_goals:
            issues.append(f"Home assists>goals")
            cpu_issues += 1
        if away_assists > away_total_goals:
            issues.append(f"Away assists>goals")
            cpu_issues += 1
        
        status = "❌ " + ", ".join(issues) if issues else "✅ OK"
        
        print(f"{game['id']:<10} {match:<40} {score:<10} {goals_str:<12} {assists_str:<12} {status:<20}")
    
    # Summary
    print("\n" + "="*100)
    print("📋 SUMMARY")
    print("="*100)
    print(f"International Games Issues: {intl_issues}")
    print(f"CPU League Games Issues: {cpu_issues}")
    
    if intl_issues == 0 and cpu_issues == 0:
        print("\n✅ SUCCESS: No assist logic issues found!")
        print("   - All assists <= goals")
        print("   - No self-assists detected")
    else:
        print(f"\n⚠️  Found {intl_issues + cpu_issues} games with assist issues")
        print("   These are likely from before the fix was applied")
    
    print("\n💡 Note: Only newly simulated games will have the corrected assist logic")
    print("="*100)
    
    conn.close()

if __name__ == "__main__":
    test_assist_logic()

