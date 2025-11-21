#!/usr/bin/env python3
"""
Script to fix historical season 01/02 data by syncing from backup database.

This script:
1. Iterates through each player in the main database (pes6_league_db.sqlite)
2. Checks if the player has historical data for season "01/02"
3. If they do, fetches current stats from the backup database
4. Updates the historical record with the backup data
"""

import sqlite3
import os
from pathlib import Path

# Database paths
MAIN_DB = "pes6_league_db.sqlite"
BACKUP_DB = "pes6_league_db(BackUP End Of Season).sqlite"
SEASON = "01/02"

def connect_db(db_path):
    """Connect to a database and return connection with row factory"""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def get_player_stats_from_backup(backup_conn, player_id):
    """Get current player stats from backup database"""
    cursor = backup_conn.cursor()
    
    # Try to get stats, handling MVP column gracefully
    try:
        cursor.execute("""
            SELECT games_played, goals, assists, MVP, club_id
            FROM players
            WHERE id = ?
        """, (player_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        # Check if MVP column exists by trying to access it
        try:
            mvp_value = row['MVP']
        except (KeyError, IndexError):
            mvp_value = 0
        
        # Get club_name from teams table
        club_id = row['club_id']
        club_name = None
        if club_id:
            cursor.execute("SELECT club_name FROM teams WHERE id = ?", (club_id,))
            club_row = cursor.fetchone()
            club_name = club_row['club_name'] if club_row else None
        
        return {
            'games_played': row['games_played'] or 0,
            'goals': row['goals'] or 0,
            'assists': row['assists'] or 0,
            'MVP': mvp_value or 0,
            'club_id': club_id,
            'club_name': club_name
        }
        
    except sqlite3.OperationalError as e:
        # If MVP column doesn't exist, try without it
        try:
            cursor.execute("""
                SELECT games_played, goals, assists, club_id
                FROM players
                WHERE id = ?
            """, (player_id,))
            row = cursor.fetchone()
            if not row:
                return None
            
            # Get club_name separately
            club_id = row['club_id']
            club_name = None
            if club_id:
                cursor.execute("SELECT club_name FROM teams WHERE id = ?", (club_id,))
                club_row = cursor.fetchone()
                club_name = club_row['club_name'] if club_row else None
            
            return {
                'games_played': row['games_played'] or 0,
                'goals': row['goals'] or 0,
                'assists': row['assists'] or 0,
                'MVP': 0,  # Default to 0 if column doesn't exist
                'club_id': club_id,
                'club_name': club_name
            }
        except Exception as e2:
            print(f"  ⚠️  Error fetching player {player_id} from backup: {e2}")
            return None
    except Exception as e:
        print(f"  ⚠️  Error fetching player {player_id} from backup: {e}")
        return None

def main():
    print("🔄 Starting historical data fix for season 01/02...")
    print(f"📁 Main DB: {MAIN_DB}")
    print(f"📁 Backup DB: {BACKUP_DB}")
    print(f"📅 Season: {SEASON}\n")
    
    # Check if databases exist
    if not os.path.exists(MAIN_DB):
        print(f"❌ Error: Main database not found: {MAIN_DB}")
        return
    
    if not os.path.exists(BACKUP_DB):
        print(f"❌ Error: Backup database not found: {BACKUP_DB}")
        return
    
    # Connect to databases
    try:
        main_conn = connect_db(MAIN_DB)
        backup_conn = connect_db(BACKUP_DB)
        print("✅ Connected to both databases\n")
    except Exception as e:
        print(f"❌ Error connecting to databases: {e}")
        return
    
    main_cursor = main_conn.cursor()
    backup_cursor = backup_conn.cursor()
    
    # Get all players from main database
    print("📋 Fetching all players from main database...")
    main_cursor.execute("SELECT id, player_name FROM players ORDER BY id")
    all_players = main_cursor.fetchall()
    print(f"✅ Found {len(all_players)} players\n")
    
    # Statistics
    stats = {
        'total_players': len(all_players),
        'has_historical_01_02': 0,
        'updated': 0,
        'not_found_in_backup': 0,
        'errors': 0
    }
    
    # Process each player
    print("🔄 Processing players...\n")
    for player in all_players:
        player_id = player['id']
        player_name = player['player_name']
        
        # Check if player has historical data for season 01/02
        main_cursor.execute("""
            SELECT id, games_played, goals, assists, MVP, club_id, club_name
            FROM player_season_history
            WHERE player_id = ? AND season = ?
        """, (player_id, SEASON))
        
        historical_record = main_cursor.fetchone()
        
        if not historical_record:
            # Player doesn't have historical record for 01/02, skip
            continue
        
        stats['has_historical_01_02'] += 1
        
        # Get current stats from backup database
        backup_stats = get_player_stats_from_backup(backup_conn, player_id)
        
        if not backup_stats:
            print(f"  ⚠️  Player {player_id} ({player_name}): Not found in backup database")
            stats['not_found_in_backup'] += 1
            continue
        
        # Update historical record with backup data
        try:
            # Get current values for comparison
            old_games = historical_record['games_played'] or 0
            old_goals = historical_record['goals'] or 0
            old_assists = historical_record['assists'] or 0
            # Handle MVP column - might not exist
            try:
                old_mvp = historical_record['MVP'] or 0
            except (KeyError, IndexError):
                old_mvp = 0
            
            new_games = backup_stats['games_played']
            new_goals = backup_stats['goals']
            new_assists = backup_stats['assists']
            new_mvp = backup_stats['MVP']
            
            # Only update if backup values are greater than or equal to current values
            # This prevents downgrading existing historical records
            should_update = False
            update_reason = []
            
            if new_games >= old_games:
                if new_games > old_games:
                    should_update = True
                    update_reason.append(f"Games: {old_games} → {new_games}")
            else:
                update_reason.append(f"Games: {old_games} (keeping {old_games}, backup has {new_games})")
            
            if new_goals >= old_goals:
                if new_goals > old_goals:
                    should_update = True
                    update_reason.append(f"Goals: {old_goals} → {new_goals}")
            else:
                update_reason.append(f"Goals: {old_goals} (keeping {old_goals}, backup has {new_goals})")
            
            if new_assists >= old_assists:
                if new_assists > old_assists:
                    should_update = True
                    update_reason.append(f"Assists: {old_assists} → {new_assists}")
            else:
                update_reason.append(f"Assists: {old_assists} (keeping {old_assists}, backup has {new_assists})")
            
            if new_mvp >= old_mvp:
                if new_mvp > old_mvp:
                    should_update = True
                    update_reason.append(f"MVP: {old_mvp} → {new_mvp}")
            else:
                update_reason.append(f"MVP: {old_mvp} (keeping {old_mvp}, backup has {new_mvp})")
            
            if should_update:
                # Use the maximum of old and new values for each stat
                final_games = max(old_games, new_games)
                final_goals = max(old_goals, new_goals)
                final_assists = max(old_assists, new_assists)
                final_mvp = max(old_mvp, new_mvp)
                
                main_cursor.execute("""
                    UPDATE player_season_history
                    SET games_played = ?,
                        goals = ?,
                        assists = ?,
                        MVP = ?,
                        club_id = ?,
                        club_name = ?
                    WHERE id = ?
                """, (
                    final_games,
                    final_goals,
                    final_assists,
                    final_mvp,
                    backup_stats['club_id'],
                    backup_stats['club_name'],
                    historical_record['id']
                ))
                
                print(f"  ✅ Player {player_id} ({player_name}): Updated 01/02")
                for reason in update_reason:
                    print(f"      {reason}")
                stats['updated'] += 1
            else:
                # Check if any values were lower (prevented downgrade)
                has_downgrade = (new_games < old_games or new_goals < old_goals or 
                               new_assists < old_assists or new_mvp < old_mvp)
                if has_downgrade:
                    print(f"  ⚠️  Player {player_id} ({player_name}): Skipped (backup values lower than historical)")
                    for reason in update_reason:
                        if "keeping" in reason:
                            print(f"      {reason}")
                else:
                    print(f"  ℹ️  Player {player_id} ({player_name}): Already correct, skipping")
                
        except Exception as e:
            print(f"  ❌ Error updating player {player_id} ({player_name}): {e}")
            stats['errors'] += 1
    
    # Commit changes
    try:
        main_conn.commit()
        print(f"\n✅ Changes committed to main database")
    except Exception as e:
        print(f"\n❌ Error committing changes: {e}")
        main_conn.rollback()
    
    # Print summary
    print("\n" + "="*60)
    print("📊 SUMMARY")
    print("="*60)
    print(f"Total players processed: {stats['total_players']}")
    print(f"Players with 01/02 historical data: {stats['has_historical_01_02']}")
    print(f"Records updated: {stats['updated']}")
    print(f"Not found in backup: {stats['not_found_in_backup']}")
    print(f"Errors: {stats['errors']}")
    print("="*60)
    
    # Close connections
    main_conn.close()
    backup_conn.close()
    print("\n✅ Script completed!")

if __name__ == "__main__":
    main()

