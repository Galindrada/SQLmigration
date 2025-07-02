import os
import mysql.connector
import import_pes6_data
import update_player_finances

# Database connection details (hardcoded for local use)
DB_CONFIG = {
    'host': 'localhost',
    'user': 'simpleuser',
    'password': '',  # or your password here
    'database': 'pes6_league_db'
}

SQL_SCHEMA_FILE = 'database.sql'


def refresh_database():
    print('Refreshing database schema...')
    with open(SQL_SCHEMA_FILE, 'r') as f:
        sql_commands = f.read().split(';')
    conn = mysql.connector.connect(
        host=DB_CONFIG['host'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password']
    )
    cursor = conn.cursor()
    # Create DB if not exists
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']}")
    cursor.execute(f"USE {DB_CONFIG['database']}")
    for command in sql_commands:
        cmd = command.strip()
        if cmd:
            try:
                cursor.execute(cmd)
            except Exception as e:
                print(f"Error executing SQL: {cmd[:60]}...\n{e}")
    conn.commit()
    cursor.close()
    conn.close()
    print('Database schema refreshed.')


def main():
    refresh_database()
    print('Importing PES6 player and team data...')
    import_pes6_data.import_data()
    print('Updating player finances...')
    update_player_finances.update_player_finances()
    print('All done!')

if __name__ == '__main__':
    main() 