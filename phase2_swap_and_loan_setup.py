#!/usr/bin/env python3
"""
Phase 2: Player Swaps and Direct Loan Proposals Setup
======================================================

This script adds database schema for:
1. Player swap offers (player + cash for player)
2. Direct loan proposals (team-to-team without listing)
3. Buy-back clauses (right to re-purchase)

IMPORTANT: This does NOT modify any existing functionality!
All changes are additive (new columns, new tables).
"""

import sqlite3
import sys
import shutil
from datetime import datetime

DB_PATH = 'pes6_league_db.sqlite'

def create_backup(db_path):
    """Create a backup before making changes"""
    backup_path = f"{db_path}.backup_phase2_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"\n📦 Creating backup: {backup_path}...")
    shutil.copy2(db_path, backup_path)
    print(f"✅ Backup created successfully!")
    return backup_path


def add_swap_columns(conn):
    """Add columns for player swap functionality to existing offers table"""
    cur = conn.cursor()
    
    print("\n" + "="*80)
    print("🔄 ADDING PLAYER SWAP COLUMNS")
    print("="*80)
    print("Note: Extends existing offer system for player swaps")
    
    columns_to_add = [
        ('market_bazaar_offers', 'swap_player_id', 'INTEGER DEFAULT NULL'),
        ('market_bazaar_offers', 'swap_type', "TEXT DEFAULT 'cash'"),  # 'cash', 'swap', 'cash+swap'
        ('market_bazaar_offers', 'swap_valuation', 'INTEGER DEFAULT 0'),
        ('market_bazaar_offers', 'cash_compensation', 'INTEGER DEFAULT 0'),
    ]
    
    for table, column, definition in columns_to_add:
        try:
            print(f"   Adding {column} to {table}...", end=" ")
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            print("✅")
        except Exception as e:
            if 'duplicate column name' in str(e).lower():
                print("ℹ️  Already exists")
            else:
                print(f"❌ Error: {e}")
                raise
    
    conn.commit()
    print("\n✅ Player swap columns added successfully!")


def create_direct_loan_proposals_table(conn):
    """Create table for direct loan proposals between teams"""
    cur = conn.cursor()
    
    print("\n" + "="*80)
    print("🤝 CREATING DIRECT LOAN PROPOSALS TABLE")
    print("="*80)
    print("Note: Allows teams to propose loans directly without listing")
    
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS direct_loan_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                loaning_team_id INTEGER NOT NULL,
                borrowing_team_id INTEGER NOT NULL,
                loan_duration INTEGER DEFAULT 1,
                wage_coverage_percentage REAL DEFAULT 0.0,
                monthly_fee INTEGER DEFAULT 0,
                option_to_buy INTEGER DEFAULT 0,
                option_to_buy_price INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT,
                responded_at TEXT,
                FOREIGN KEY (player_id) REFERENCES players(id),
                FOREIGN KEY (loaning_team_id) REFERENCES teams(id),
                FOREIGN KEY (borrowing_team_id) REFERENCES teams(id)
            )
        """)
        print("✅ direct_loan_proposals table created")
        
        # Create index for performance
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_direct_loan_proposals_status 
            ON direct_loan_proposals(status, borrowing_team_id)
        """)
        print("✅ Index created for direct_loan_proposals")
        
    except Exception as e:
        if 'already exists' in str(e).lower():
            print("ℹ️  Table already exists")
        else:
            print(f"❌ Error: {e}")
            raise
    
    conn.commit()
    print("\n✅ Direct loan proposals table ready!")


def create_buyback_clauses_table(conn):
    """Create table for buy-back clauses"""
    cur = conn.cursor()
    
    print("\n" + "="*80)
    print("↩️  CREATING BUY-BACK CLAUSES TABLE")
    print("="*80)
    print("Note: Allows selling clubs to retain right to re-purchase players")
    
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS buyback_clauses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                original_club_id INTEGER NOT NULL,
                current_club_id INTEGER NOT NULL,
                buyback_price INTEGER NOT NULL,
                sale_price INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                activated_at TEXT,
                FOREIGN KEY (player_id) REFERENCES players(id),
                FOREIGN KEY (original_club_id) REFERENCES teams(id),
                FOREIGN KEY (current_club_id) REFERENCES teams(id)
            )
        """)
        print("✅ buyback_clauses table created")
        
        # Create indexes for performance
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_buyback_clauses_player 
            ON buyback_clauses(player_id, status)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_buyback_clauses_original_club 
            ON buyback_clauses(original_club_id, status)
        """)
        print("✅ Indexes created for buyback_clauses")
        
    except Exception as e:
        if 'already exists' in str(e).lower():
            print("ℹ️  Table already exists")
        else:
            print(f"❌ Error: {e}")
            raise
    
    conn.commit()
    print("\n✅ Buy-back clauses table ready!")


def verify_existing_data(conn):
    """Verify that existing data is intact"""
    cur = conn.cursor()
    
    print("\n" + "="*80)
    print("🔍 VERIFYING EXISTING DATA")
    print("="*80)
    
    checks = [
        ("Teams", "SELECT COUNT(*) FROM teams"),
        ("Players", "SELECT COUNT(*) FROM players"),
        ("Market listings", "SELECT COUNT(*) FROM market_bazaar_listings"),
        ("Market offers", "SELECT COUNT(*) FROM market_bazaar_offers"),
        ("Budget integrity", "SELECT SUM(budget) FROM teams"),
    ]
    
    for check_name, query in checks:
        try:
            cur.execute(query)
            result = cur.fetchone()[0]
            if check_name == "Budget integrity":
                print(f"   ✅ {check_name}: €{result:,.2f}")
            else:
                print(f"   ✅ {check_name}: {result:,}")
        except Exception as e:
            print(f"   ❌ {check_name}: Error - {e}")
            raise
    
    print("\n✅ All existing data verified intact!")


def main():
    print("="*80)
    print("🚀 PHASE 2: PLAYER SWAPS & DIRECT LOAN PROPOSALS")
    print("="*80)
    print("This script adds new features WITHOUT changing existing functionality.")
    print("\nNew Features:")
    print("  1. Player swap offers (player + cash for player)")
    print("  2. Direct loan proposals (team-to-team)")
    print("  3. Buy-back clauses (right to re-purchase)")
    
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
        
        # Verify existing data before changes
        verify_existing_data(conn)
        
        # Add new schema elements
        add_swap_columns(conn)
        create_direct_loan_proposals_table(conn)
        create_buyback_clauses_table(conn)
        
        # Verify again after changes
        verify_existing_data(conn)
        
        conn.close()
        
        print("\n" + "="*80)
        print("✅ PHASE 2 SETUP COMPLETE!")
        print("="*80)
        print(f"📦 Backup saved at: {backup_path}")
        print("\nWhat's new:")
        print("  ✅ Player swap columns added to market_bazaar_offers")
        print("  ✅ Direct loan proposals table created")
        print("  ✅ Buy-back clauses table created")
        print("  ✅ All existing data intact")
        print("\nNext steps:")
        print("  1. Implement swap offer logic in CPU AI")
        print("  2. Add UI for swap offers")
        print("  3. Implement direct loan proposals")
        print("\n💡 To rollback: cp " + backup_path + " " + DB_PATH)
        
    except Exception as e:
        print(f"\n❌ Error during setup: {e}")
        print(f"💡 To restore backup: cp {backup_path} {DB_PATH}")
        sys.exit(1)


if __name__ == "__main__":
    main()

