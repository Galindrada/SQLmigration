#!/usr/bin/env python3

import sqlite3

# Database path
DB_PATH = 'pes6_league_db.sqlite'

def debug_team_calculation():
    print("=== Debugging Team Salary Calculation ===")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Get Galindro's current budget
    cur.execute("SELECT budget FROM user_budgets WHERE user_id = (SELECT id FROM users WHERE username = 'Galindro')")
    current_budget = cur.fetchone()
    current_budget_amount = current_budget['budget'] if current_budget else 450000000
    
    print(f"Galindro's current budget: €{current_budget_amount:,}")
    
    # Get Galindro's teams
    cur.execute("SELECT id, team_name FROM league_teams WHERE user_id = (SELECT id FROM users WHERE username = 'Galindro')")
    teams = cur.fetchall()
    
    print(f"\nGalindro's teams:")
    for team in teams:
        print(f"  - {team['team_name']} (ID: {team['id']})")
    
    # Calculate current salaries per team
    print(f"\nCurrent salaries per team:")
    total_current_salary = 0
    
    for team in teams:
        cur.execute("""
            SELECT SUM(p.salary) as team_salary
            FROM players p
            JOIN team_players tp ON p.id = tp.player_id
            WHERE tp.team_id = ?
        """, (team['id'],))
        team_salary = cur.fetchone()['team_salary'] or 0
        total_current_salary += team_salary
        print(f"  - {team['team_name']}: €{team_salary:,}")
    
    print(f"Total current salary: €{total_current_salary:,}")
    
    # Calculate what the new salary would be after dividing by 2
    new_total_salary = total_current_salary // 2
    
    print(f"\nAfter salary reduction (//2):")
    print(f"  - New total salary: €{new_total_salary:,}")
    
    # Calculate budget impact
    new_budget = current_budget_amount - new_total_salary
    
    print(f"\nBudget calculation:")
    print(f"  - Current budget: €{current_budget_amount:,}")
    print(f"  - New salary bill: €{new_total_salary:,}")
    print(f"  - New budget: €{new_budget:,}")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    debug_team_calculation() 