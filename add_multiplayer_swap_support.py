#!/usr/bin/env python3
"""
Add Multi-Player Swap Support
=============================

This script adds database schema support for multiple players in swap offers.
"""

import sqlite3
import os
from datetime import datetime

def add_multiplayer_swap_support(db_path: str = 'pes6_league_db.sqlite'):
    """Add database schema for multiple players in swap offers"""
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    try:
        print("\n" + "="*80)
        print("🔄 ADDING MULTI-PLAYER SWAP SUPPORT")
        print("="*80)
        
        # Create table for multiple swap players per offer
        print("\n📋 Creating swap_offer_players table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS swap_offer_players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                offer_id INTEGER NOT NULL,
                player_id INTEGER NOT NULL,
                market_value INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (offer_id) REFERENCES market_bazaar_offers(id) ON DELETE CASCADE,
                FOREIGN KEY (player_id) REFERENCES players(id),
                UNIQUE(offer_id, player_id)
            )
        """)
        
        # Create index for faster lookups
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_swap_offer_players_offer 
            ON swap_offer_players(offer_id)
        """)
        
        print("  ✅ Created swap_offer_players table")
        print("  ✅ Created index on offer_id")
        
        conn.commit()
        print("\n✅ Multi-player swap support added successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error adding multi-player swap support: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    add_multiplayer_swap_support()

