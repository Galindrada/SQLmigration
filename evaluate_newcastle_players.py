#!/usr/bin/env python3
"""
Script to evaluate Newcastle players' acceptance price ranges using the good deal routine
"""

import sqlite3
from cpu_ai import CPUAI

def evaluate_newcastle_players():
    """Evaluate all Newcastle players and their good deal acceptance ranges"""
    
    # Initialize CPU AI
    cpu_ai = CPUAI()
    
    # Connect to database
    conn = sqlite3.connect('pes6_league_db.sqlite')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Find Newcastle team
    cur.execute("SELECT id, club_name FROM teams WHERE club_name LIKE '%Newcastle%' OR club_name LIKE '%Newcastle%'")
    newcastle_teams = cur.fetchall()
    
    if not newcastle_teams:
        print("❌ Newcastle team not found in database")
        return
    
    print(f"Found {len(newcastle_teams)} Newcastle team(s):")
    for team in newcastle_teams:
        print(f"  - {team['club_name']} (ID: {team['id']})")
    
    # Get all players from Newcastle (use first team if multiple)
    newcastle_id = newcastle_teams[0]['id']
    newcastle_name = newcastle_teams[0]['club_name']
    
    # Get all player data including all skill columns needed for salary calculation
    cur.execute("""
        SELECT p.*
        FROM players p
        WHERE p.club_id = ?
        ORDER BY p.overall DESC, p.player_name
    """, (newcastle_id,))
    
    players = cur.fetchall()
    
    if not players:
        print(f"❌ No players found for {newcastle_name}")
        return
    
    print(f"\n{'='*100}")
    print(f"Evaluating {len(players)} players from {newcastle_name}")
    print(f"{'='*100}\n")
    
    # Evaluate each player
    for player in players:
        player_id = player['id']
        player_name = player['player_name']
        position = player['registered_position']
        overall = player['overall'] or 0
        age = player['age'] or 25
        market_value = player['market_value'] or 1000000
        current_salary = player['salary'] or 0
        contract_years = player['contract_years_remaining'] or 1
        
        # Get player data as dict for CPU AI functions
        player_data = dict(player)
        
        # Calculate fair salary
        fair_salary = cpu_ai.calculate_fair_salary(player_data)
        
        # Check if toxic contract
        is_toxic, _ = cpu_ai.is_toxic_contract(player_data)
        
        # Calculate total overpayment (annual overpayment * contract years)
        annual_overpayment = current_salary - fair_salary if current_salary > fair_salary else 0
        total_overpayment = annual_overpayment * contract_years
        
        # Check if beneficial salary (low - underpaid)
        is_beneficial_salary = current_salary < fair_salary * 0.8  # 20% below fair salary
        
        # Check if young
        is_young = age < 25
        
        # Calculate acceptance price ranges based on good deal criteria using the CPU AI method
        max_acceptable_price = cpu_ai.calculate_good_deal_max_price(player_data)
        
        # Determine which criteria applies based on player characteristics
        if total_overpayment > 0:
            criteria_applied = f"90% MV - Total Overpayment (-€{total_overpayment:,.0f} over {contract_years} years)"
        elif is_beneficial_salary and is_young:
            criteria_applied = "120% MV (Young <25 AND Beneficial Salary)"
        elif is_beneficial_salary:
            criteria_applied = "105% MV (Older ≥25 AND Beneficial Salary)"
        elif is_young:
            criteria_applied = "100% MV (Young <25 with Fair Salary)"
        else:
            criteria_applied = "90% MV (Older ≥25 with Fair Salary)"
        
        # Format output
        print(f"Player: {player_name}")
        print(f"  Position: {position} | Overall: {overall} | Age: {age}")
        print(f"  Market Value: €{market_value:,}")
        print(f"  Current Salary: €{current_salary:,}")
        print(f"  Fair Salary: €{fair_salary:,}")
        print(f"  Contract Years: {contract_years}")
        print(f"  Toxic Contract: {'Yes' if is_toxic else 'No'} (Annual Overpayment: €{annual_overpayment:,.0f}, Total: €{total_overpayment:,.0f} over {contract_years} years)")
        print(f"  Beneficial Salary: {'Yes' if is_beneficial_salary else 'No'} (Underpaid by: €{fair_salary - current_salary:,})")
        print(f"  Young Player: {'Yes' if is_young else 'No'} (< 25 years)")
        print(f"  Good Deal Criteria: {criteria_applied}")
        print(f"  Max Acceptable Price: €{max_acceptable_price:,} ({max_acceptable_price/market_value*100:.1f}% of MV)" if max_acceptable_price > 0 else "  Max Acceptable Price: N/A (No good deal criteria met)")
        print(f"  Price Range: €0 - €{max_acceptable_price:,}" if max_acceptable_price > 0 else "  Price Range: N/A")
        print("-" * 100)
    
    conn.close()
    print(f"\n✅ Evaluation complete for {len(players)} players")

if __name__ == "__main__":
    evaluate_newcastle_players()

