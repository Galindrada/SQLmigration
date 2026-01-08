#!/usr/bin/env python3
"""Test script to verify CPU team stance population"""

import sqlite3
from team_management import TeamManager, populate_cpu_team_stances

def test_stance_population():
    """Test the stance population function"""
    print("🧪 Testing CPU Team Stance Population")
    print("="*80)
    
    manager = TeamManager()
    if not manager.connect():
        print("❌ Failed to connect to database")
        return False
    
    try:
        # Run the stance population
        result = populate_cpu_team_stances(manager)
        
        if result:
            print("\n✅ Test passed: Stance population completed successfully")
            
            # Verify some teams have stances
            cursor = manager.conn.cursor()
            cursor.execute("""
                SELECT stance, COUNT(*) as count
                FROM teams
                WHERE stance IS NOT NULL
                GROUP BY stance
                ORDER BY count DESC
            """)
            
            stance_counts = cursor.fetchall()
            print("\n📊 Stance Distribution:")
            print("-" * 40)
            for row in stance_counts:
                print(f"  {row['stance']:<15}: {row['count']} teams")
            
            # Show sample teams with each stance
            print("\n📋 Sample Teams by Stance:")
            print("-" * 80)
            for stance in ['Powerdog', 'Contender', 'Tinkering', 'Rebuilder']:
                cursor.execute("""
                    SELECT t.club_name, t.stance, ds.points, d.name as division_name
                    FROM teams t
                    LEFT JOIN division_standings ds ON t.id = ds.team_id
                    LEFT JOIN divisions d ON ds.division_id = d.id
                    WHERE t.stance = ?
                    LIMIT 3
                """, (stance,))
                
                teams = cursor.fetchall()
                if teams:
                    print(f"\n{stance}:")
                    for team in teams:
                        points = team['points'] if team['points'] else 0
                        div_name = team['division_name'] if team['division_name'] else 'N/A'
                        print(f"  • {team['club_name']:<30} ({div_name}) - {points} pts")
            
            return True
        else:
            print("\n❌ Test failed: Stance population returned False")
            return False
            
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        manager.disconnect()

if __name__ == "__main__":
    test_stance_population()
