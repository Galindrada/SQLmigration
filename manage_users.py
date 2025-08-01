import os
import sqlite3
from config import Config

DB_PATH = getattr(Config, 'SQLITE_DB_PATH', 'pes6_league_db.sqlite')

def prompt_for_user_deletion():
    """Prompt the user to decide whether to delete existing users."""
    while True:
        response = input("\nDo you want to delete all existing users (except CPU)? (y/n): ").lower().strip()
        if response in ['y', 'yes']:
            return True
        elif response in ['n', 'no']:
            return False
        else:
            print("Please enter 'y' or 'n'.")

def list_users():
    """List all users in the database."""
    if not os.path.exists(DB_PATH):
        print(f"Database file {DB_PATH} does not exist.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id, username, email FROM users ORDER BY id")
        users = cursor.fetchall()
        
        if not users:
            print("No users found in the database.")
        else:
            print("\nCurrent users in the database:")
            print("-" * 50)
            for user in users:
                user_type = "CPU" if user[0] == 1 else "User"
                print(f"ID: {user[0]}, Username: {user[1]}, Email: {user[2]}, Type: {user_type}")
            print("-" * 50)
    except Exception as e:
        print(f"Error listing users: {e}")
    finally:
        cursor.close()
        conn.close()

def delete_users_except_cpu():
    """Delete all users except the CPU user (id=1)."""
    if not os.path.exists(DB_PATH):
        print(f"Database file {DB_PATH} does not exist.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON;')
    cursor = conn.cursor()
    
    try:
        # First, list current users
        print("Current users before deletion:")
        cursor.execute("SELECT id, username FROM users ORDER BY id")
        current_users = cursor.fetchall()
        for user in current_users:
            user_type = "CPU" if user[0] == 1 else "User"
            print(f"ID: {user[0]}, Username: {user[1]}, Type: {user_type}")
        
        # Delete all users except CPU (id=1)
        cursor.execute("DELETE FROM users WHERE id != 1")
        deleted_count = cursor.rowcount
        conn.commit()
        
        print(f"\nDeleted {deleted_count} users (kept CPU user).")
        
        # Verify CPU user still exists
        cursor.execute("SELECT id, username FROM users WHERE id = 1")
        cpu_user = cursor.fetchone()
        if cpu_user:
            print(f"CPU user verified: ID {cpu_user[0]}, Username: {cpu_user[1]}")
        else:
            print("Warning: CPU user not found after deletion!")
            
    except Exception as e:
        print(f"Error deleting users: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def ensure_cpu_user():
    """Ensure the CPU user exists in the database."""
    if not os.path.exists(DB_PATH):
        print(f"Database file {DB_PATH} does not exist.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON;')
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id FROM users WHERE id = 1")
        result = cursor.fetchone()
        if not result:
            cursor.execute("INSERT INTO users (id, username, password, email) VALUES (?, ?, ?, ?)", 
                         (1, 'CPU', '', 'cpu@localhost'))
            conn.commit()
            print('CPU user created successfully.')
        else:
            print('CPU user already exists.')
    except Exception as e:
        print(f"Error ensuring CPU user: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def main():
    print("=== User Management Script ===")
    print("This script allows you to manage users in the database.")
    print("\nOptions:")
    print("1. List all users")
    print("2. Delete all users except CPU")
    print("3. Ensure CPU user exists")
    print("4. Interactive user deletion (with prompt)")
    
    while True:
        choice = input("\nEnter your choice (1-4, or 'q' to quit): ").strip()
        
        if choice == 'q':
            print("Goodbye!")
            break
        elif choice == '1':
            list_users()
        elif choice == '2':
            delete_users_except_cpu()
        elif choice == '3':
            ensure_cpu_user()
        elif choice == '4':
            if prompt_for_user_deletion():
                delete_users_except_cpu()
            else:
                print("User deletion cancelled.")
        else:
            print("Invalid choice. Please enter 1-4 or 'q'.")

if __name__ == '__main__':
    main() 