#!/usr/bin/env python3
"""
Team Roster Balancer Script

This script balances CPU team rosters to ensure no team has more than 30 players.
It releases the least valuable players (by market value) from teams with >30 players
and assigns them to teams with available slots.

Usage: python3 balance_team_rosters.py
"""

import sqlite3
import sys
from typing import List, Dict, Tuple

DB_PATH = 'pes6_league_db.sqlite'

def get_db_connection():
    """Get database connection with row factory"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_team_player_counts(conn) -> List[Dict]:
    """Get all CPU teams with their player counts (excluding user-assigned teams)"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            t.id,
            t.club_name,
            COUNT(p.id) as player_count
        FROM teams t
        LEFT JOIN players p ON t.id = p.club_id
        LEFT JOIN league_teams lt ON t.club_name = lt.team_name AND lt.user_id IS NOT NULL AND lt.user_id != 1
        WHERE t.club_name != 'No Club' AND lt.id IS NULL
        GROUP BY t.id, t.club_name
        ORDER BY player_count DESC
    """)
    return cursor.fetchall()

def get_players_to_release(conn, team_id: int, excess_count: int) -> List[Dict]:
    """Get the least valuable players from a team that need to be released"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            p.id,
            p.player_name,
            p.market_value,
            p.salary,
            p.age,
            p.game_position
        FROM players p
        WHERE p.club_id = ?
        ORDER BY 
            COALESCE(p.market_value, 0) ASC,
            COALESCE(p.salary, 0) ASC,
            p.age DESC
        LIMIT ?
    """, (team_id, excess_count))
    return cursor.fetchall()

def get_teams_with_available_slots(conn, max_players: int = 30) -> List[Dict]:
    """Get CPU teams that have available slots (less than max_players, excluding user-assigned teams)"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            t.id,
            t.club_name,
            COUNT(p.id) as current_count,
            ? - COUNT(p.id) as available_slots
        FROM teams t
        LEFT JOIN players p ON t.id = p.club_id
        LEFT JOIN league_teams lt ON t.club_name = lt.team_name AND lt.user_id IS NOT NULL AND lt.user_id != 1
        WHERE t.club_name != 'No Club' AND lt.id IS NULL
        GROUP BY t.id, t.club_name
        HAVING COUNT(p.id) < ?
        ORDER BY available_slots DESC
    """, (max_players, max_players))
    return cursor.fetchall()

def assign_player_to_team(conn, player_id: int, new_team_id: int, player_name: str, new_team_name: str):
    """Assign a player to a new team"""
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE players 
        SET club_id = ?
        WHERE id = ?
    """, (new_team_id, player_id))
    print(f"  ✅ Moved {player_name} to {new_team_name}")

def balance_team_rosters():
    """Main function to balance team rosters"""
    print("🏈 Team Roster Balancer")
    print("=" * 50)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Get current CPU team player counts (excluding user-assigned teams)
        print("📊 Analyzing current CPU team rosters (user teams will remain untouched)...")
        team_counts = get_team_player_counts(conn)
        
        # Find teams with >30 players
        overloaded_teams = [team for team in team_counts if team['player_count'] > 30]
        print(f"\n🔍 Found {len(overloaded_teams)} CPU teams with >30 players:")
        
        for team in overloaded_teams:
            excess = team['player_count'] - 30
            print(f"  • {team['club_name']}: {team['player_count']} players (need to release {excess})")
        
        if not overloaded_teams:
            print("✅ All CPU teams already have 30 or fewer players!")
            return
        
        # Get CPU teams with available slots
        available_teams = get_teams_with_available_slots(conn)
        print(f"\n📋 Found {len(available_teams)} CPU teams with available slots")
        
        if not available_teams:
            print("❌ No CPU teams with available slots found!")
            return
        
        # Convert to dictionaries for easier manipulation
        available_teams = [dict(team) for team in available_teams]
        
        # Process each overloaded team
        total_moved = 0
        for team in overloaded_teams:
            team_id = team['id']
            team_name = team['club_name']
            excess_count = team['player_count'] - 30
            
            print(f"\n🔄 Processing {team_name} (releasing {excess_count} players)...")
            
            # Get players to release (least valuable first)
            players_to_release = get_players_to_release(conn, team_id, excess_count)
            
            if not players_to_release:
                print(f"  ⚠️  No players found to release from {team_name}")
                continue
            
            # Assign each player to a team with available slots
            for player in players_to_release:
                player_id = player['id']
                player_name = player['player_name']
                market_value = player['market_value'] or 0
                salary = player['salary'] or 0
                
                print(f"  📤 Releasing {player_name} (MV: €{market_value:,}, Salary: €{salary:,})")
                
                # Find a team with available slots
                assigned = False
                for available_team in available_teams:
                    if available_team['available_slots'] > 0:
                        # Assign player to this team
                        assign_player_to_team(conn, player_id, available_team['id'], 
                                            player_name, available_team['club_name'])
                        
                        # Update available slots count
                        available_team['available_slots'] -= 1
                        available_team['current_count'] += 1
                        total_moved += 1
                        assigned = True
                        break
                
                if not assigned:
                    print(f"    ❌ No available slots for {player_name}")
                    break
        
        # Commit all changes
        conn.commit()
        
        print(f"\n✅ Roster balancing complete!")
        print(f"📈 Total players moved: {total_moved}")
        
        # Show final CPU team counts
        print(f"\n📊 Final CPU team roster counts:")
        final_counts = get_team_player_counts(conn)
        overloaded_final = [team for team in final_counts if team['player_count'] > 30]
        
        if overloaded_final:
            print("⚠️  CPU teams still with >30 players:")
            for team in overloaded_final:
                print(f"  • {team['club_name']}: {team['player_count']} players")
        else:
            print("🎉 All CPU teams now have 30 or fewer players!")
        
        # Show CPU teams with most available slots
        available_final = get_teams_with_available_slots(conn)
        if available_final:
            print(f"\n📋 CPU teams with most available slots:")
            for team in available_final[:10]:  # Show top 10
                print(f"  • {team['club_name']}: {team['available_slots']} slots available")
        
    except Exception as e:
        print(f"❌ Error during roster balancing: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    try:
        balance_team_rosters()
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)
