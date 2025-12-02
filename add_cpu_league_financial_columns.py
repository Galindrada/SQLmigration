#!/usr/bin/env python3
"""
Add financial tracking columns to league_games table for CPU leagues.
This script adds columns to track:
- Attendance revenue (home team only)
- Sponsor premium (both teams)
- Merchandise revenue (both teams)
- Prize bonus (winner or split for draw)
"""

import sqlite3

def add_financial_columns():
    """Add financial columns to league_games table"""
    
    print("="*80)
    print("💰 ADDING FINANCIAL COLUMNS TO CPU LEAGUE GAMES")
    print("="*80)
    
    conn = sqlite3.connect('pes6_league_db.sqlite')
    cursor = conn.cursor()
    
    try:
        # Check existing columns
        cursor.execute("PRAGMA table_info(league_games)")
        existing_columns = [row[1] for row in cursor.fetchall()]
        
        columns_to_add = [
            ('home_attendance_revenue', 'INTEGER DEFAULT 0'),
            ('home_sponsor_premium', 'INTEGER DEFAULT 0'),
            ('away_sponsor_premium', 'INTEGER DEFAULT 0'),
            ('home_merchandise_revenue', 'INTEGER DEFAULT 0'),
            ('away_merchandise_revenue', 'INTEGER DEFAULT 0'),
            ('home_prize_bonus', 'INTEGER DEFAULT 0'),
            ('away_prize_bonus', 'INTEGER DEFAULT 0'),
            ('home_total_earnings', 'INTEGER DEFAULT 0'),
            ('away_total_earnings', 'INTEGER DEFAULT 0'),
        ]
        
        added_count = 0
        skipped_count = 0
        
        for col_name, col_type in columns_to_add:
            if col_name not in existing_columns:
                print(f"  ➕ Adding column: {col_name}")
                cursor.execute(f"ALTER TABLE league_games ADD COLUMN {col_name} {col_type}")
                added_count += 1
            else:
                print(f"  ✅ Column already exists: {col_name}")
                skipped_count += 1
        
        conn.commit()
        
        print(f"\n✅ Successfully added {added_count} columns")
        print(f"ℹ️  Skipped {skipped_count} existing columns")
        
        # Show updated schema
        cursor.execute("PRAGMA table_info(league_games)")
        all_columns = cursor.fetchall()
        
        print(f"\n📋 Financial columns in league_games table:")
        for col in all_columns:
            if 'revenue' in col[1] or 'premium' in col[1] or 'bonus' in col[1] or 'earnings' in col[1]:
                print(f"   - {col[1]} ({col[2]})")
        
        print("\n" + "="*80)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    add_financial_columns()

