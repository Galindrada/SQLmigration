import sqlite3
import os
from config import Config

DB_PATH = getattr(Config, 'SQLITE_DB_PATH', 'pes6_league_db.sqlite')

def calculate_skill_ratings():
    """Calculate and update bundled skill ratings for all players."""
    if not os.path.exists(DB_PATH):
        print(f"Database file {DB_PATH} does not exist.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # First, add the new columns if they don't exist
        cursor.execute("PRAGMA table_info(players)")
        columns = [column[1] for column in cursor.fetchall()]
        
        new_columns = [
            'attack_rating', 'defense_rating', 'physical_rating', 
            'power_rating', 'technique_rating', 'goalkeeping_rating'
        ]
        
        for column in new_columns:
            if column not in columns:
                cursor.execute(f"ALTER TABLE players ADD COLUMN {column} INTEGER DEFAULT 0")
                print(f"Added column: {column}")

        # Get all players
        cursor.execute("SELECT id, attack, defense, aggression, stamina, top_speed, acceleration, response, agility, jump, shot_power, balance, mentality, technique, swerve, free_kick_accuracy, goal_keeping, dribble_accuracy, dribble_speed, short_pass_accuracy, short_pass_speed, long_pass_accuracy, long_pass_speed FROM players")
        players = cursor.fetchall()

        updated_count = 0
        for player in players:
            player_id = player[0]
            
            # Calculate Attack Rating (average of 'Attack')
            attack_rating = player[1] if player[1] is not None else 0
            
            # Calculate Defense Rating (average of 'Defense' and 'Aggression')
            defense_values = [player[2], player[3]]  # defense, aggression
            defense_values = [v for v in defense_values if v is not None]
            defense_rating = sum(defense_values) // len(defense_values) if defense_values else 0
            
            # Calculate Physical Rating (average of stamina, top_speed, acceleration, response, agility, jump)
            physical_values = [player[4], player[5], player[6], player[7], player[8], player[9]]  # stamina, top_speed, acceleration, response, agility, jump
            physical_values = [v for v in physical_values if v is not None]
            physical_rating = sum(physical_values) // len(physical_values) if physical_values else 0
            
            # Calculate Power Rating (average of shot_power, balance, mentality)
            power_values = [player[10], player[11], player[12]]  # shot_power, balance, mentality
            power_values = [v for v in power_values if v is not None]
            power_rating = sum(power_values) // len(power_values) if power_values else 0
            
            # Calculate Technique Rating (average of technique, swerve, free_kick_accuracy, and all pass/dribble skills)
            technique_values = [player[13], player[14], player[15]]  # technique, swerve, free_kick_accuracy
            # Add pass and dribble skills
            pass_dribble_values = [player[16], player[17], player[18], player[19], player[20], player[21], player[22]]  # dribble_accuracy, dribble_speed, short_pass_accuracy, short_pass_speed, long_pass_accuracy, long_pass_speed
            technique_values.extend([v for v in pass_dribble_values if v is not None])
            technique_rating = sum(technique_values) // len(technique_values) if technique_values else 0
            
            # Calculate Goalkeeping Rating (average of defense, goal_keeping, response, agility)
            gk_values = [player[2], player[15], player[7], player[8]]  # defense, goal_keeping, response, agility
            gk_values = [v for v in gk_values if v is not None]
            goalkeeping_rating = sum(gk_values) // len(gk_values) if gk_values else 0
            
            # Update the player record
            cursor.execute("""
                UPDATE players 
                SET attack_rating = ?, defense_rating = ?, physical_rating = ?, 
                    power_rating = ?, technique_rating = ?, goalkeeping_rating = ?
                WHERE id = ?
            """, (attack_rating, defense_rating, physical_rating, power_rating, technique_rating, goalkeeping_rating, player_id))
            
            updated_count += 1

        conn.commit()
        print(f"Successfully updated {updated_count} players with bundled skill ratings.")

    except Exception as e:
        print(f"Error updating skill ratings: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def main():
    print("=== Player Skill Ratings Update Script ===")
    print("This script will calculate and update bundled skill ratings for all players.")
    
    confirm = input("\nContinue? (y/n): ").lower().strip()
    if confirm in ['y', 'yes']:
        calculate_skill_ratings()
        print("Skill ratings update complete!")
    else:
        print("Operation cancelled.")

if __name__ == '__main__':
    main() 