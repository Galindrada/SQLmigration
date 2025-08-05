#!/usr/bin/env python3

import sqlite3

# Database path
DB_PATH = 'pes6_league_db.sqlite'

def reset_galindro_budget():
    print("=== Resetting Galindro's Budget ===")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Get Galindro's current budget
    cur.execute("SELECT budget FROM user_budgets WHERE user_id = (SELECT id FROM users WHERE username = 'Galindro')")
    current_budget = cur.fetchone()
    current_budget_amount = current_budget['budget'] if current_budget else 450000000
    
    print(f"Galindro's current budget: €{current_budget_amount:,}")
    
    # Reset to initial budget
    new_budget = 450000000
    cur.execute("UPDATE user_budgets SET budget = ? WHERE user_id = (SELECT id FROM users WHERE username = 'Galindro')", (new_budget,))
    
    # Add a movement record for the reset
    cur.execute("""
        INSERT INTO user_movements (user_id, type, description, amount, balance_after)
        VALUES ((SELECT id FROM users WHERE username = 'Galindro'), 'Budget Reset', 'Reset to initial budget for testing', ?, ?)
    """, (new_budget - current_budget_amount, new_budget))
    
    conn.commit()
    
    print(f"Galindro's budget reset to: €{new_budget:,}")
    print(f"Budget change: €{new_budget - current_budget_amount:,}")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    reset_galindro_budget() 