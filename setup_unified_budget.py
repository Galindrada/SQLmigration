#!/usr/bin/env python3

import sqlite3
import os

# Database path
DB_PATH = 'pes6_league_db.sqlite'

def setup_unified_budget():
    print("=== Setting up Unified Budget System ===")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    try:
        # Create user_budgets table
        print("Creating user_budgets table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_budgets (
                user_id INTEGER PRIMARY KEY,
                budget INTEGER DEFAULT 45000000,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        # Create user_movements table
        print("Creating user_movements table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                description TEXT NOT NULL,
                amount INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        # Initialize user budgets for existing users
        print("Initializing user budgets...")
        cur.execute("SELECT id, username FROM users WHERE id != 1")  # Exclude CPU user
        users = cur.fetchall()
        
        for user in users:
            # Check if user already has a budget entry
            cur.execute("SELECT budget FROM user_budgets WHERE user_id = ?", (user['id'],))
            existing_budget = cur.fetchone()
            
            if not existing_budget:
                # Initialize with default budget
                cur.execute("""
                    INSERT INTO user_budgets (user_id, budget, created_at, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (user['id'], 45000000))
                print(f"  Initialized budget for {user['username']}: €45,000,000")
            else:
                print(f"  {user['username']} already has budget: €{existing_budget['budget']:,}")
        
        conn.commit()
        print("✅ Unified budget system setup complete!")
        
        # Show summary
        print("\n=== Budget Summary ===")
        cur.execute("""
            SELECT u.username, ub.budget 
            FROM users u 
            LEFT JOIN user_budgets ub ON u.id = ub.user_id 
            WHERE u.id != 1
            ORDER BY u.username
        """)
        budgets = cur.fetchall()
        
        for budget in budgets:
            username = budget['username']
            budget_amount = budget['budget'] if budget['budget'] else 45000000
            print(f"  {username}: €{budget_amount:,}")
        
    except Exception as e:
        print(f"❌ Error setting up unified budget: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    setup_unified_budget() 