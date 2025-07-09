import pandas as pd
import sqlite3
import os
from config import Config

CSV_FILE = 'routine1_players_financials.csv'
DB_PATH = getattr(Config, 'SQLITE_DB_PATH', 'pes6_league_db.sqlite')

def update_player_finances():
    try:
        # Read the financials CSV, assuming ID is the first column and the last 4 columns are the required fields
        df = pd.read_csv(CSV_FILE)
        # Set index to ID for fast lookup
        df.set_index('ID', inplace=True)
        # Use the actual column names from the CSV
        required_cols = ['Salary', 'Contract Years Remaining', 'Yearly Wage Raise', 'Market Value']
        for col in required_cols:
            if col not in df.columns:
                raise Exception(f"Column '{col}' not found in {CSV_FILE}")

        conn = sqlite3.connect(DB_PATH)
        conn.execute('PRAGMA foreign_keys = ON;')
        cursor = conn.cursor()

        print(f"Updating player finances for {len(df)} players from CSV...")
        updated_count = 0
        for player_id, row in df.iterrows():
            salary = row['Salary']
            contract_years_remaining = row['Contract Years Remaining']
            yearly_wage_rise = row['Yearly Wage Raise']
            market_value = row['Market Value']

            update_sql = """
            UPDATE players
            SET salary = ?,
                contract_years_remaining = ?,
                yearly_wage_rise = ?,
                market_value = ?
            WHERE id = ?
            """
            cursor.execute(update_sql, (salary, contract_years_remaining, yearly_wage_rise, market_value, player_id))
            updated_count += 1

        conn.commit()
        print(f"Financial data updated successfully for {updated_count} players!")

        cursor.close()
        conn.close()

    except FileNotFoundError:
        print(f"Error: CSV file '{CSV_FILE}' not found.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    update_player_finances()
