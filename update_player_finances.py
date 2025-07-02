import pandas as pd
import mysql.connector
#from dotenv import load_dotenv
import os

# Database connection details (simplified for local use)
DB_CONFIG = {
    'host': 'localhost',
    'user': 'simpleuser',
    'password': '',  # or your password here
    'database': 'pes6_league_db'
}

CSV_FILE = 'routine1_players_financials.csv'

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

        conn = mysql.connector.connect(**DB_CONFIG)
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
            SET salary = %s,
                contract_years_remaining = %s,
                yearly_wage_rise = %s,
                market_value = %s
            WHERE id = %s
            """
            cursor.execute(update_sql, (salary, contract_years_remaining, yearly_wage_rise, market_value, player_id))
            updated_count += 1

        conn.commit()
        print(f"Financial data updated successfully for {updated_count} players!")

    except mysql.connector.Error as err:
        print(f"Database Error: {err}")
    except FileNotFoundError:
        print(f"Error: CSV file '{CSV_FILE}' not found.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()
            print("MySQL connection closed.")

if __name__ == "__main__":
    update_player_finances()
