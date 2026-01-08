#!/usr/bin/env python3
"""
Team Roster Balancer Script

This script balances CPU team rosters to ensure all teams have between 16 and 32 players.
- Teams with >32 players: releases least valuable players
- Teams with <16 players: adds players from overloaded teams or free agents

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

def get_teams_with_available_slots(conn, max_players: int = 32) -> List[Dict]:
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

def get_teams_under_minimum(conn, min_players: int = 16) -> List[Dict]:
    """Get CPU teams that have fewer than min_players (excluding user-assigned teams)"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            t.id,
            t.club_name,
            COUNT(p.id) as current_count,
            ? - COUNT(p.id) as needed_players
        FROM teams t
        LEFT JOIN players p ON t.id = p.club_id
        LEFT JOIN league_teams lt ON t.club_name = lt.team_name AND lt.user_id IS NOT NULL AND lt.user_id != 1
        WHERE t.club_name != 'No Club' AND lt.id IS NULL
        GROUP BY t.id, t.club_name
        HAVING COUNT(p.id) < ?
        ORDER BY needed_players DESC
    """, (min_players, min_players))
    return cursor.fetchall()

def get_available_players_for_transfer(conn, exclude_team_id: int = None) -> List[Dict]:
    """Get players that can be transferred (from overloaded teams or free agents)"""
    cursor = conn.cursor()
    
    # First get free agents
    if exclude_team_id:
        cursor.execute("""
            SELECT 
                p.id,
                p.player_name,
                p.market_value,
                p.salary,
                p.age,
                p.game_position,
                p.club_id,
                t.club_name
            FROM players p
            LEFT JOIN teams t ON p.club_id = t.id
            WHERE (t.club_name = 'No Club' OR t.club_name IS NULL)
            AND (p.club_id != ? OR p.club_id IS NULL)
            ORDER BY 
                COALESCE(p.market_value, 0) ASC,
                COALESCE(p.salary, 0) ASC
        """, (exclude_team_id,))
    else:
        cursor.execute("""
            SELECT 
                p.id,
                p.player_name,
                p.market_value,
                p.salary,
                p.age,
                p.game_position,
                p.club_id,
                t.club_name
            FROM players p
            LEFT JOIN teams t ON p.club_id = t.id
            WHERE t.club_name = 'No Club' OR t.club_name IS NULL
            ORDER BY 
                COALESCE(p.market_value, 0) ASC,
                COALESCE(p.salary, 0) ASC
        """)
    
    free_agents = cursor.fetchall()
    
    # Then get players from overloaded teams (>32 players)
    cursor.execute("""
        SELECT 
            p.id,
            p.player_name,
            p.market_value,
            p.salary,
            p.age,
            p.game_position,
            p.club_id,
            t.club_name
        FROM players p
        JOIN teams t ON p.club_id = t.id
        WHERE t.club_name != 'No Club'
        AND (p.club_id != ? OR ? IS NULL)
        AND t.id IN (
            SELECT t2.id
            FROM teams t2
            LEFT JOIN players p2 ON t2.id = p2.club_id
            WHERE t2.club_name != 'No Club'
            GROUP BY t2.id
            HAVING COUNT(p2.id) > 32
        )
        ORDER BY 
            COALESCE(p.market_value, 0) ASC,
            COALESCE(p.salary, 0) ASC
    """, (exclude_team_id, exclude_team_id))
    
    overloaded_players = cursor.fetchall()
    
    # Combine: free agents first, then overloaded team players
    return list(free_agents) + list(overloaded_players)

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
        
        # Find teams with >32 players
        overloaded_teams = [team for team in team_counts if team['player_count'] > 32]
        print(f"\n🔍 Found {len(overloaded_teams)} CPU teams with >32 players:")
        
        for team in overloaded_teams:
            excess = team['player_count'] - 32
            print(f"  • {team['club_name']}: {team['player_count']} players (need to release {excess})")
        
        # Find teams with <16 players
        understaffed_teams = get_teams_under_minimum(conn, min_players=16)
        print(f"\n🔍 Found {len(understaffed_teams)} CPU teams with <16 players:")
        
        for team in understaffed_teams:
            needed = team['needed_players']
            print(f"  • {team['club_name']}: {team['current_count']} players (need {needed} more)")
        
        if not overloaded_teams and not understaffed_teams:
            print("✅ All CPU teams already have between 16 and 32 players!")
            return
        
        # Get CPU teams with available slots (for players from overloaded teams)
        available_teams = get_teams_with_available_slots(conn, max_players=32)
        print(f"\n📋 Found {len(available_teams)} CPU teams with available slots (for overloaded team players)")
        
        # Convert to dictionaries for easier manipulation
        available_teams = [dict(team) for team in available_teams]
        
        # Convert understaffed teams to dictionaries
        understaffed_teams = [dict(team) for team in understaffed_teams]
        
        # Process each overloaded team
        total_moved = 0
        if overloaded_teams:
        for team in overloaded_teams:
            team_id = team['id']
            team_name = team['club_name']
                excess_count = team['player_count'] - 32
            
            print(f"\n🔄 Processing {team_name} (releasing {excess_count} players)...")
            
            # Get players to release (least valuable first)
            players_to_release = get_players_to_release(conn, team_id, excess_count)
            
            if not players_to_release:
                print(f"  ⚠️  No players found to release from {team_name}")
                continue
            
            # Assign each player to a team with available slots (prioritize understaffed teams)
            for player in players_to_release:
                player_id = player['id']
                player_name = player['player_name']
                market_value = player['market_value'] or 0
                salary = player['salary'] or 0
                
                print(f"  📤 Releasing {player_name} (MV: €{market_value:,}, Salary: €{salary:,})")
                
                # First try to assign to understaffed teams
                assigned = False
                for understaffed_team in understaffed_teams:
                    if understaffed_team['current_count'] < 16:
                        assign_player_to_team(conn, player_id, understaffed_team['id'], 
                                            player_name, understaffed_team['club_name'])
                        understaffed_team['current_count'] += 1
                        understaffed_team['needed_players'] -= 1
                        total_moved += 1
                        assigned = True
                        break
                
                # If not assigned to understaffed team, assign to any available team
                if not assigned:
                for available_team in available_teams:
                    if available_team['available_slots'] > 0:
                        assign_player_to_team(conn, player_id, available_team['id'], 
                                            player_name, available_team['club_name'])
                        available_team['available_slots'] -= 1
                        available_team['current_count'] += 1
                        total_moved += 1
                        assigned = True
                        break
                
                if not assigned:
                    # If no team available, release to free agents
                    no_club_team_id = None
                        cursor = conn.cursor()
                    cursor.execute("SELECT id FROM teams WHERE club_name = 'No Club'")
                    no_club_result = cursor.fetchone()
                    if no_club_result:
                        no_club_team_id = no_club_result['id']
                    else:
                        # Create No Club if it doesn't exist
                        cursor.execute("INSERT INTO teams (club_name) VALUES ('No Club')")
                        no_club_team_id = cursor.lastrowid
                    
                    if no_club_team_id:
                        assign_player_to_team(conn, player_id, no_club_team_id, 
                                            player_name, 'No Club')
                        total_moved += 1
                        print(f"    ℹ️  Released {player_name} to free agents (No Club)")
                    else:
                    print(f"    ❌ No available slots for {player_name}")
        
        # Handle understaffed teams (<16 players) - fill from free agents or overloaded teams
        if understaffed_teams:
            print(f"\n🔄 Processing understaffed teams (<16 players)...")
            for team in understaffed_teams:
                team_id = team['id']
                team_name = team['club_name']
                needed_count = team['needed_players']
                
                print(f"\n🔄 Processing {team_name} (needs {needed_count} players)...")
                
                # Get available players (from overloaded teams or free agents)
                available_players = get_available_players_for_transfer(conn, exclude_team_id=team_id)
                
                assigned_count = 0
                for player in available_players[:needed_count]:
                    if assigned_count >= needed_count:
                    break
                    
                    player_id = player['id']
                    player_name = player['player_name']
                    market_value = player['market_value'] or 0
                    salary = player['salary'] or 0
                    
                    print(f"  📥 Adding {player_name} (MV: €{market_value:,}, Salary: €{salary:,})")
                    assign_player_to_team(conn, player_id, team_id, player_name, team_name)
                    assigned_count += 1
                    total_moved += 1
                
                if assigned_count < needed_count:
                    print(f"    ⚠️  Only found {assigned_count} players, still need {needed_count - assigned_count} more")
        
        # Commit all changes
        conn.commit()
        
        print(f"\n✅ Roster balancing complete!")
        print(f"📈 Total players moved: {total_moved}")
        
        # Show final CPU team counts
        print(f"\n📊 Final CPU team roster counts:")
        final_counts = get_team_player_counts(conn)
        overloaded_final = [team for team in final_counts if team['player_count'] > 32]
        understaffed_final = get_teams_under_minimum(conn, min_players=16)
        
        if overloaded_final:
            print("⚠️  CPU teams still with >32 players:")
            for team in overloaded_final:
                print(f"  • {team['club_name']}: {team['player_count']} players")
        
        if understaffed_final:
            print("⚠️  CPU teams still with <16 players:")
            for team in understaffed_final:
                print(f"  • {team['club_name']}: {team['current_count']} players")
        
        if not overloaded_final and not understaffed_final:
            print("🎉 All CPU teams now have between 16 and 32 players!")
        
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
