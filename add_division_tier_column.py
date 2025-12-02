#!/usr/bin/env python3
"""
Add tier column to divisions table for financial calculations.
Tier 1 = full financial values
Tier 2 = 40% of Tier 1 values (60% reduction)
"""

import sqlite3

def add_tier_column():
    """Add tier column to divisions table"""
    
    print("="*80)
    print("🏆 ADDING TIER COLUMN TO DIVISIONS TABLE")
    print("="*80)
    
    conn = sqlite3.connect('pes6_league_db.sqlite')
    cursor = conn.cursor()
    
    try:
        # Add tier column
        try:
            cursor.execute("ALTER TABLE divisions ADD COLUMN tier INTEGER DEFAULT 1")
            print("  ✅ Added tier column to divisions table")
        except Exception as e:
            if 'duplicate column name' not in str(e):
                print(f"  ❌ Error adding tier column: {e}")
                raise
            else:
                print("  ℹ️  tier column already exists")
        
        # Add tv_rights_revenue column to league_games
        try:
            cursor.execute("ALTER TABLE league_games ADD COLUMN home_tv_rights_revenue INTEGER DEFAULT 0")
            print("  ✅ Added home_tv_rights_revenue column to league_games")
        except Exception as e:
            if 'duplicate column name' not in str(e):
                print(f"  ❌ Error: {e}")
            else:
                print("  ℹ️  home_tv_rights_revenue column already exists")
        
        try:
            cursor.execute("ALTER TABLE league_games ADD COLUMN away_tv_rights_revenue INTEGER DEFAULT 0")
            print("  ✅ Added away_tv_rights_revenue column to league_games")
        except Exception as e:
            if 'duplicate column name' not in str(e):
                print(f"  ❌ Error: {e}")
            else:
                print("  ℹ️  away_tv_rights_revenue column already exists")
        
        conn.commit()
        
        print(f"\n✅ Schema updated successfully!")
        print(f"\n📋 Tier System:")
        print(f"   Tier 1: Full financial values (100%)")
        print(f"   Tier 2: Reduced financial values (40% of Tier 1)")
        
        print("\n" + "="*80)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    add_tier_column()

