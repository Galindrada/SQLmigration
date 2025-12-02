#!/usr/bin/env python3
"""
Print total market value for each team owned by a user
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db_helper

def print_team_market_values():
    """Print total market value for each user's team"""
    with app.app_context():
        cur = db_helper.get_cursor()
        
        # Get all teams owned by users (not CPU teams - exclude user_id = 1)
        # Teams are linked to users through league_teams table
        cur.execute("""
            SELECT t.id, t.club_name, u.id as user_id, u.username, lt.team_name as league_team_name
            FROM league_teams lt
            JOIN users u ON lt.user_id = u.id
            JOIN teams t ON lt.team_name = t.club_name
            WHERE lt.user_id IS NOT NULL AND lt.user_id != 1
            ORDER BY u.username, t.club_name
        """)
        user_teams = cur.fetchall()
        
        if not user_teams:
            print("No user teams found.")
            return
        
        print("="*80)
        print("TEAM MARKET VALUES BY USER")
        print("="*80)
        
        current_user = None
        total_user_value = 0
        
        for team in user_teams:
            team_id = team['id']
            team_name = team['club_name']
            user_id = team['user_id']
            username = team['username']
            
            # If new user, print previous user's total
            if current_user is not None and current_user != user_id:
                print(f"\n  Total for {current_username}: €{total_user_value:,.2f}")
                print("-"*80)
                total_user_value = 0
            
            # Get total market value for this team
            cur.execute("""
                SELECT COALESCE(SUM(market_value), 0) as total_value, COUNT(*) as player_count
                FROM players
                WHERE club_id = ?
            """, (team_id,))
            result = cur.fetchone()
            team_value = result['total_value'] or 0
            player_count = result['player_count']
            
            # Print team info
            if current_user != user_id:
                print(f"\n👤 {username} (User ID: {user_id})")
                print("-"*80)
            
            print(f"  📊 {team_name}: €{team_value:,.2f} ({player_count} players)")
            
            current_user = user_id
            current_username = username
            total_user_value += team_value
        
        # Print last user's total
        if current_user is not None:
            print(f"\n  Total for {current_username}: €{total_user_value:,.2f}")
        
        # Summary statistics
        print("\n" + "="*80)
        print("SUMMARY STATISTICS")
        print("="*80)
        
        # Get overall stats (excluding CPU teams - user_id = 1)
        cur.execute("""
            SELECT 
                COUNT(DISTINCT lt.user_id) as total_users,
                COUNT(DISTINCT t.id) as total_teams,
                COALESCE(SUM(p.market_value), 0) as total_market_value,
                COALESCE(AVG(team_values.total), 0) as avg_team_value,
                COALESCE(MAX(team_values.total), 0) as max_team_value,
                COALESCE(MIN(team_values.total), 0) as min_team_value
            FROM league_teams lt
            JOIN teams t ON lt.team_name = t.club_name
            LEFT JOIN (
                SELECT club_id, SUM(market_value) as total
                FROM players
                WHERE club_id IN (
                    SELECT t.id FROM teams t
                    JOIN league_teams lt ON t.club_name = lt.team_name
                    WHERE lt.user_id IS NOT NULL AND lt.user_id != 1
                )
                GROUP BY club_id
            ) team_values ON t.id = team_values.club_id
            LEFT JOIN players p ON t.id = p.club_id
            WHERE lt.user_id IS NOT NULL AND lt.user_id != 1
        """)
        stats = cur.fetchone()
        
        print(f"Total Users: {stats['total_users']}")
        print(f"Total Teams: {stats['total_teams']}")
        print(f"Total Market Value (all user teams): €{stats['total_market_value']:,.2f}")
        print(f"Average Team Value: €{stats['avg_team_value']:,.2f}")
        print(f"Highest Team Value: €{stats['max_team_value']:,.2f}")
        print(f"Lowest Team Value: €{stats['min_team_value']:,.2f}")
        
        # Top 10 teams by value
        print("\n" + "="*80)
        print("TOP 10 TEAMS BY MARKET VALUE")
        print("="*80)
        
        cur.execute("""
            SELECT 
                t.club_name,
                u.username,
                COALESCE(SUM(p.market_value), 0) as total_value,
                COUNT(p.id) as player_count
            FROM league_teams lt
            JOIN teams t ON lt.team_name = t.club_name
            JOIN users u ON lt.user_id = u.id
            LEFT JOIN players p ON t.id = p.club_id
            WHERE lt.user_id IS NOT NULL AND lt.user_id != 1
            GROUP BY t.id, t.club_name, u.username
            ORDER BY total_value DESC
            LIMIT 30
        """)
        top_teams = cur.fetchall()
        
        for i, team in enumerate(top_teams, 1):
            print(f"{i:2d}. {team['club_name']} ({team['username']}): €{team['total_value']:,.2f} ({team['player_count']} players)")

if __name__ == '__main__':
    print_team_market_values()

