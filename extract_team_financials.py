#!/usr/bin/env python3
"""
Script to extract team financial data: total market value and total salaries per club.
Exports to CSV with team information and financial summaries.
"""

import sqlite3
import csv
import sys
import os
from datetime import datetime
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def get_team_financial_data():
    """Extract team financial data from the database."""
    conn = sqlite3.connect('pes6_league_db.sqlite')
    cursor = conn.cursor()
    
    try:
        # Get team financial data - simple version
        cursor.execute("""
            SELECT 
                t.id as team_id,
                t.club_name,
                COUNT(p.id) as player_count,
                SUM(p.market_value) as total_market_value,
                SUM(p.salary) as total_salaries
            FROM teams t
            LEFT JOIN players p ON t.id = p.club_id
            GROUP BY t.id, t.club_name
            ORDER BY total_market_value DESC
        """)
        
        team_data = cursor.fetchall()
        
        # Get column names
        column_names = [description[0] for description in cursor.description]
        
        return team_data, column_names
        
    finally:
        conn.close()

def format_currency(value):
    """Format currency values."""
    if value is None:
        return "0€"
    return f"{value:,.0f}€"

def export_team_financials():
    """Export team financial data to CSV."""
    print("📊 Extracting team financial data...")
    
    # Get main team data
    team_data, column_names = get_team_financial_data()
    
    # Create timestamp for filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Export main team financial data
    main_filename = f"team_financial_data_{timestamp}.csv"
    with open(main_filename, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        
        # Write header
        writer.writerow(column_names)
        
        # Write data
        for row in team_data:
            writer.writerow(row)
    
    # Print summary
    print(f"\n📈 TEAM FINANCIAL SUMMARY:")
    print(f"   Total Teams: {len(team_data)}")
    
    if team_data:
        # Calculate totals
        total_market_value = sum(row[3] for row in team_data if row[3])
        total_salaries = sum(row[4] for row in team_data if row[4])
        total_players = sum(row[2] for row in team_data if row[2])
        
        print(f"   Total Market Value: {format_currency(total_market_value)}")
        print(f"   Total Salaries: {format_currency(total_salaries)}")
        print(f"   Total Players: {total_players:,}")
        
        # Top 10 teams by market value
        print(f"\n🏆 TOP 10 TEAMS BY MARKET VALUE:")
        for i, team in enumerate(team_data[:10]):
            team_id, club_name, players, market_val, salaries = team
            print(f"   {i+1:2d}. {club_name:25s}: {format_currency(market_val):>15s} ({players:3d} players)")
        
        # Top 10 teams by salary spending
        print(f"\n💰 TOP 10 TEAMS BY SALARY SPENDING:")
        sorted_by_salary = sorted(team_data, key=lambda x: x[4] or 0, reverse=True)
        for i, team in enumerate(sorted_by_salary[:10]):
            team_id, club_name, players, market_val, salaries = team
            print(f"   {i+1:2d}. {club_name:25s}: {format_currency(salaries):>15s} ({players:3d} players)")
    
    print(f"\n💾 Data exported to: {main_filename}")
    
    return main_filename

def main():
    """Main function to extract and export team financial data."""
    print("=== Team Financial Data Extractor ===")
    print("Extracting market values and salaries for all teams...\n")
    
    try:
        main_file = export_team_financials()
        print(f"\n✅ Export completed successfully!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
