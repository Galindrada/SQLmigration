#!/usr/bin/env python3
"""
Fix invalid face_type values in the players table.

face_type must be 0, 1, or 2 only. This script finds all players where
face_type is NULL or not in (0, 1, 2) and sets them to a random value in {0, 1, 2}.

Usage: python3 fix_face_type.py
"""

import os
import random
import sqlite3
import sys

# Use same DB as app if config available
try:
    from config import Config
    DB_PATH = Config.SQLITE_DB_PATH
except ImportError:
    DB_PATH = os.environ.get('SQLITE_DB_PATH', 'pes6_league_db.sqlite')


def main():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, face_type
        FROM players
        WHERE face_type IS NULL OR CAST(face_type AS INTEGER) NOT IN (0, 1, 2)
    """)
    rows = cur.fetchall()

    if not rows:
        print("✅ No players with invalid face_type found.")
        conn.close()
        return

    print(f"Found {len(rows)} player(s) with invalid face_type. Fixing...")
    for (player_id, old_val) in rows:
        new_val = random.choice([0, 1, 2])
        cur.execute("UPDATE players SET face_type = ? WHERE id = ?", (new_val, player_id))
        print(f"  Player id={player_id} face_type {old_val} → {new_val}")

    conn.commit()
    conn.close()
    print(f"✅ Updated {len(rows)} player(s). face_type is now 0, 1, or 2 for all.")


if __name__ == '__main__':
    main()
