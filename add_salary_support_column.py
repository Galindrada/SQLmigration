#!/usr/bin/env python3
"""
Migration script to add salary_support_percentage column to market_bazaar_listings table
"""

import sqlite3

def migrate_database():
    """Add salary_support_percentage column to market_bazaar_listings table"""
    db_path = 'pes6_league_db.sqlite'
    
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        # Check if column already exists
        cur.execute("PRAGMA table_info(market_bazaar_listings)")
        columns = [row[1] for row in cur.fetchall()]
        
        if 'salary_support_percentage' in columns:
            print("✅ Column salary_support_percentage already exists")
            conn.close()
            return
        
        # Add the column
        print("Adding salary_support_percentage column to market_bazaar_listings...")
        cur.execute("ALTER TABLE market_bazaar_listings ADD COLUMN salary_support_percentage REAL DEFAULT 0.0")
        conn.commit()
        
        print("✅ Successfully added salary_support_percentage column")
        conn.close()
        
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
            print("✅ Column already exists (caught duplicate error)")
        else:
            print(f"❌ Error: {e}")
            raise
    except Exception as e:
        print(f"❌ Error: {e}")
        raise

if __name__ == '__main__':
    migrate_database()

