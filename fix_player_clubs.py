#!/usr/bin/env python3
import sqlite3
import os

def fix_player_clubs():
    """Fix players who were signed through free agency but still have club_id = 141"""
    
    # Connect to database
    db_path = 'pes6_league_db.sqlite'
    if not os.path.exists(db_path):
        print(f"Database file {db_path} not found!")
        return
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    try:
        # Find players who are assigned to user teams but still have club_id = 141
        cur.execute("""
            SELECT p.id, p.player_name, p.club_id, tp.team_id, lt.team_name, lt.user_id
            FROM players p 
            JOIN team_players tp ON p.id = tp.player_id 
            JOIN league_teams lt ON tp.team_id = lt.id 
            WHERE p.club_id = 141 AND lt.user_id != 1
        """)
        
        players_to_fix = cur.fetchall()
        
        if not players_to_fix:
            print("No players found that need fixing!")
            return
        
        print(f"Found {len(players_to_fix)} players that need club_id fixing:")
        
        fixed_count = 0
        
        for player in players_to_fix:
            print(f"  - {player['player_name']} (ID: {player['id']}) assigned to {player['team_name']}")
            
            # Find the corresponding PES6 team ID
            cur.execute("SELECT id FROM teams WHERE club_name = ?", (player['team_name'],))
            pes6_team_result = cur.fetchone()
            
            if pes6_team_result:
                pes6_team_id = pes6_team_result['id']
                
                # Update the player's club_id
                cur.execute("UPDATE players SET club_id = ? WHERE id = ?", (pes6_team_id, player['id']))
                fixed_count += 1
                print(f"    ✓ Updated club_id to {pes6_team_id} ({player['team_name']})")
            else:
                print(f"    ✗ PES6 team not found for: {player['team_name']}")
        
        conn.commit()
        print(f"\nFixed {fixed_count} players!")
        
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    fix_player_clubs() 