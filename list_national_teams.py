#!/usr/bin/env python3
"""
List all available national teams, excluding duplicates for Serbia and USA
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db_helper

def list_national_teams():
    """List all international teams, excluding duplicates"""
    with app.app_context():
        cur = db_helper.get_cursor()
        
        # Get all international teams
        cur.execute("""
            SELECT it.id, it.nationality, it.team_name, 
                   COUNT(DISTINCT itp.player_id) as player_count
            FROM international_teams it
            LEFT JOIN international_team_players itp ON it.id = itp.international_team_id
            GROUP BY it.id, it.nationality, it.team_name
            ORDER BY it.nationality
        """)
        all_teams = cur.fetchall()
        
        print("="*80)
        print("AVAILABLE NATIONAL TEAMS")
        print("="*80)
        print(f"Total teams: {len(all_teams)}\n")
        
        # Track nationalities to identify duplicates
        nationality_counts = {}
        for team in all_teams:
            nat = team['nationality']
            nationality_counts[nat] = nationality_counts.get(nat, 0) + 1
        
        # Find duplicates
        duplicates = {nat: count for nat, count in nationality_counts.items() if count > 1}
        
        if duplicates:
            print("⚠️  DUPLICATE NATIONALITIES FOUND:")
            for nat, count in sorted(duplicates.items()):
                print(f"   {nat}: {count} teams")
            print()
        
        # Filter out Serbia and USA duplicates
        # Keep "Serbia" (ID: 12) and exclude "Serbia and Montenegro" (ID: 99)
        # Keep "USA" (ID: 31) and exclude "United States" (ID: 105)
        filtered_teams = []
        excluded_teams = []
        
        for team in all_teams:
            nat = team['nationality']
            team_id = team['id']
            
            # Exclude "Serbia and Montenegro" (keep "Serbia")
            if nat == 'Serbia and Montenegro':
                excluded_teams.append(team)
                continue
            
            # Exclude "United States" (keep "USA")
            if nat == 'United States':
                excluded_teams.append(team)
                continue
            
            filtered_teams.append(team)
        
        if excluded_teams:
            print("❌ EXCLUDED DUPLICATES:")
            for team in excluded_teams:
                print(f"   {team['team_name']} (ID: {team['id']}, {team['player_count']} players)")
            print()
        
        print("="*80)
        print(f"FILTERED LIST ({len(filtered_teams)} teams, excluding duplicates)")
        print("="*80)
        print()
        
        # Group by first letter for better readability
        current_letter = None
        for team in filtered_teams:
            nat = team['nationality']
            first_letter = nat[0].upper() if nat else '?'
            
            if first_letter != current_letter:
                if current_letter is not None:
                    print()
                print(f"--- {first_letter} ---")
                current_letter = first_letter
            
            print(f"  {team['nationality']:30s} | {team['player_count']:4d} players | ID: {team['id']}")
        
        print()
        print("="*80)
        print("SUMMARY")
        print("="*80)
        print(f"Total teams in database: {len(all_teams)}")
        print(f"Teams after filtering: {len(filtered_teams)}")
        print(f"Excluded duplicates: {len(all_teams) - len(filtered_teams)}")
        
        # Show which Serbia and USA teams were kept
        print("\nTeams kept (one of each duplicate):")
        for team in filtered_teams:
            if team['nationality'] in ['Serbia', 'USA']:
                print(f"  ✅ {team['team_name']} (ID: {team['id']}, {team['player_count']} players)")

if __name__ == '__main__':
    list_national_teams()

