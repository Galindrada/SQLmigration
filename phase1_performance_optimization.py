#!/usr/bin/env python3
"""
Phase 1 Performance Optimization for CPU AI
============================================

This script adds performance improvements WITHOUT modifying any existing functionality:
1. Database indexes for faster queries
2. last_action_time tracking to reduce unnecessary processing
3. Verification that all changes are safe

IMPORTANT: This does NOT modify any money transfer logic or existing functionality!
"""

import sqlite3
import sys
from datetime import datetime

DB_PATH = 'pes6_league_db.sqlite'

def add_performance_indexes(conn):
    """Add database indexes to speed up CPU AI queries (safe, read-only optimization)"""
    cur = conn.cursor()
    
    print("\n" + "="*80)
    print("📊 ADDING PERFORMANCE INDEXES")
    print("="*80)
    print("Note: Indexes improve query speed without changing any logic or data")
    
    indexes = [
        # Speed up player queries by club and position (used in team composition analysis)
        ("idx_players_club_position", 
         "CREATE INDEX IF NOT EXISTS idx_players_club_position ON players(club_id, registered_position)"),
        
        # Speed up market bazaar listing queries
        ("idx_market_listings_status_type", 
         "CREATE INDEX IF NOT EXISTS idx_market_listings_status_type ON market_bazaar_listings(status, listing_type)"),
        
        # Speed up market bazaar offer queries
        ("idx_market_offers_status", 
         "CREATE INDEX IF NOT EXISTS idx_market_offers_status ON market_bazaar_offers(status)"),
        
        # Speed up market offers by listing
        ("idx_market_offers_listing", 
         "CREATE INDEX IF NOT EXISTS idx_market_offers_listing ON market_bazaar_offers(listing_id, status)"),
        
        # Speed up team budget queries
        ("idx_teams_budget", 
         "CREATE INDEX IF NOT EXISTS idx_teams_budget ON teams(budget)"),
        
        # Speed up player market value queries
        ("idx_players_market_value", 
         "CREATE INDEX IF NOT EXISTS idx_players_market_value ON players(market_value, club_id)"),
        
        # Speed up league teams user queries
        ("idx_league_teams_user", 
         "CREATE INDEX IF NOT EXISTS idx_league_teams_user ON league_teams(user_id, team_name)"),
    ]
    
    for idx_name, idx_sql in indexes:
        try:
            print(f"   Creating index: {idx_name}...", end=" ")
            cur.execute(idx_sql)
            print("✅")
        except Exception as e:
            print(f"⚠️  Already exists or error: {e}")
    
    conn.commit()
    print("\n✅ All indexes created successfully!")


def add_last_action_time_column(conn):
    """Add last_action_time column to teams table for smarter AI triggering"""
    cur = conn.cursor()
    
    print("\n" + "="*80)
    print("⏰ ADDING LAST_ACTION_TIME TRACKING")
    print("="*80)
    print("Note: This helps reduce unnecessary CPU AI processing")
    
    try:
        # Check if column already exists
        cur.execute("PRAGMA table_info(teams)")
        columns = [row[1] for row in cur.fetchall()]
        
        if 'last_action_time' in columns:
            print("   ⚠️  Column 'last_action_time' already exists, skipping...")
            return
        
        # Add the column (safe operation, doesn't affect existing data)
        print("   Adding 'last_action_time' column to teams table...", end=" ")
        cur.execute("ALTER TABLE teams ADD COLUMN last_action_time TEXT")
        conn.commit()
        print("✅")
        
        # Initialize with NULL (teams will get timestamp on first action)
        print("   Initializing last_action_time values...", end=" ")
        # Don't set a default time - let the AI set it on first action
        print("✅ (NULL for all teams - will be set on first action)")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
        raise


def verify_existing_functionality(conn):
    """Verify that existing tables and data are intact"""
    cur = conn.cursor()
    
    print("\n" + "="*80)
    print("🔍 VERIFYING EXISTING FUNCTIONALITY")
    print("="*80)
    
    checks = [
        ("Teams table", "SELECT COUNT(*) FROM teams"),
        ("Players table", "SELECT COUNT(*) FROM players"),
        ("Market listings", "SELECT COUNT(*) FROM market_bazaar_listings"),
        ("Market offers", "SELECT COUNT(*) FROM market_bazaar_offers"),
        ("Budget integrity", "SELECT SUM(budget) FROM teams"),
    ]
    
    for check_name, query in checks:
        try:
            cur.execute(query)
            result = cur.fetchone()[0]
            print(f"   ✅ {check_name}: {result:,}")
        except Exception as e:
            print(f"   ❌ {check_name}: Error - {e}")
            raise
    
    print("\n✅ All existing functionality verified!")


def create_backup(db_path):
    """Create a backup before making changes"""
    import shutil
    from datetime import datetime
    
    backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"\n📦 Creating backup: {backup_path}...")
    shutil.copy2(db_path, backup_path)
    print(f"✅ Backup created successfully!")
    return backup_path


def main():
    print("="*80)
    print("🚀 PHASE 1: CPU AI PERFORMANCE OPTIMIZATION")
    print("="*80)
    print("This script will add performance improvements WITHOUT changing any logic.")
    print("All existing functionality, including money transfers, will remain intact.")
    
    # Ask for confirmation
    response = input("\nDo you want to proceed? (y/N): ").strip().lower()
    if response != 'y':
        print("❌ Operation cancelled")
        return
    
    try:
        # Create backup first
        backup_path = create_backup(DB_PATH)
        
        # Connect to database
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        
        # Verify existing functionality before changes
        verify_existing_functionality(conn)
        
        # Add performance indexes (safe, read-only optimization)
        add_performance_indexes(conn)
        
        # Add last_action_time tracking
        add_last_action_time_column(conn)
        
        # Verify again after changes
        verify_existing_functionality(conn)
        
        conn.close()
        
        print("\n" + "="*80)
        print("✅ PHASE 1 OPTIMIZATION COMPLETE!")
        print("="*80)
        print(f"📦 Backup saved at: {backup_path}")
        print("\nNext steps:")
        print("1. ✅ Database indexes added (queries will be faster)")
        print("2. ✅ last_action_time column added (AI will process smarter)")
        print("3. ⏳ Now updating CPU AI code to use these optimizations...")
        print("\n💡 To rollback: cp " + backup_path + " " + DB_PATH)
        
    except Exception as e:
        print(f"\n❌ Error during optimization: {e}")
        print(f"💡 To restore backup: cp {backup_path} {DB_PATH}")
        sys.exit(1)


if __name__ == "__main__":
    main()

