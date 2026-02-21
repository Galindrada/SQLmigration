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
    """Main function to balance team rosters (interactive suggestions only)."""
    print("🏈 Team Roster Balancer")
    print("=" * 50)

    conn = get_db_connection()
    cursor = conn.cursor()  # kept for potential future use

    try:
        # Get current CPU team player counts (excluding user-assigned teams)
        print("📊 Analyzing current CPU team rosters (user teams will remain untouched)...")
        team_counts = get_team_player_counts(conn)

        # Teams with >32 players
        overloaded_teams = [dict(team) for team in team_counts if team['player_count'] > 32]
        print(f"\n🔍 Found {len(overloaded_teams)} CPU teams with >32 players:")
        for team in overloaded_teams:
            excess = team['player_count'] - 32
            print(f"  • {team['club_name']}: {team['player_count']} players (need to release {excess})")

        # Teams with <16 players
        understaffed_teams = [dict(team) for team in get_teams_under_minimum(conn, min_players=16)]
        print(f"\n🔍 Found {len(understaffed_teams)} CPU teams with <16 players:")
        for team in understaffed_teams:
            needed = team['needed_players']
            print(f"  • {team['club_name']}: {team['current_count']} players (need {needed} more)")

        if not overloaded_teams and not understaffed_teams:
            print("✅ All CPU teams already have between 16 and 32 players! Nothing to do.")
            return

        # CPU teams with available slots (for incoming players)
        available_teams = [dict(team) for team in get_teams_with_available_slots(conn, max_players=32)]
        print(f"\n📋 Found {len(available_teams)} CPU teams with available slots (for overloaded team players)")

        total_moved = 0

        # Helper: suggest a move and ask the user
        def suggest_move(player, from_team_name, to_team_id, to_team_name):
            nonlocal total_moved
            player_name = player['player_name']
            mv = player.get('market_value') or 0
            salary = player.get('salary') or 0
            while True:
                print(
                    f"\n👉 Suggestion: move {player_name} from {from_team_name} to {to_team_name} "
                    f"(MV: €{mv:,}, Salary: €{salary:,})"
                )
                resp = input("Accept this move? [y = yes, n = no, s = skip player, q = quit]: ").strip().lower()
                if resp == 'y':
                    assign_player_to_team(conn, player['id'], to_team_id, player_name, to_team_name)
                    total_moved += 1
                    return 'accepted'
                elif resp == 'n':
                    return 'reject_destination'
                elif resp == 's':
                    return 'skip_player'
                elif resp == 'q':
                    raise KeyboardInterrupt("User aborted roster balancing.")
                else:
                    print("Please answer with y, n, s, or q.")

        # Process each overloaded team: suggest moves instead of auto-balancing
        for team in overloaded_teams:
            team_id = team['id']
            team_name = team['club_name']
            excess_count = team['player_count'] - 32

            print(f"\n🔄 Processing overloaded team {team_name} (needs to release {excess_count} players)...")

            # Least valuable players first
            players_to_release = get_players_to_release(conn, team_id, excess_count)
            if not players_to_release:
                print(f"  ⚠️  No players found to release from {team_name}")
                continue

            for player in players_to_release:
                # Ensure we have a plain dict (sqlite3.Row has no .get method)
                player = dict(player)
                # Build candidate destinations:
                # 1) Understaffed teams (<16 players)
                # 2) Any team with available slots
                candidate_teams = []

                for ut in understaffed_teams:
                    if ut['current_count'] < 16:
                        candidate_teams.append(ut)

                for at in available_teams:
                    if at.get('available_slots', 0) > 0 and at not in candidate_teams:
                        candidate_teams.append(at)

                if not candidate_teams:
                    print(f"  ⚠️  No suitable destination teams found for {player['player_name']} from {team_name}.")
                    continue

                moved = False
                for dest in candidate_teams:
                    result = suggest_move(player, team_name, dest['id'], dest['club_name'])
                    if result == 'accepted':
                        # Update cached counts
                        if dest in understaffed_teams:
                            dest['current_count'] += 1
                            dest['needed_players'] = max(0, dest['needed_players'] - 1)
                        if dest in available_teams:
                            dest['available_slots'] = max(0, dest.get('available_slots', 0) - 1)
                            dest['current_count'] = dest.get('current_count', 0) + 1
                        moved = True
                        break
                    elif result == 'skip_player':
                        moved = True  # considered handled; go to next player
                        break
                    elif result == 'reject_destination':
                        continue  # try next destination

                if not moved:
                    print(f"  ℹ️  No accepted destination for {player['player_name']} from {team_name}.")

        # Only commit the moves the user accepted
        conn.commit()

        print(f"\n✅ Suggestion run complete. Confirmed moves performed: {total_moved}")

        # Show final CPU team counts for visibility
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

    except KeyboardInterrupt as e:
        print(f"\n❌ {e}")
        print("Rolling back uncommitted changes...")
        conn.rollback()
    except Exception as e:
        print(f"\n❌ Error during roster balancing: {e}")
        conn.rollback()
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
