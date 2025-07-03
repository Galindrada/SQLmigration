import pandas as pd
import mysql.connector
#from dotenv import load_dotenv
import os


# Database connection details from config.py or .env
DB_CONFIG = {
    'host': 'localhost',
    'user': 'simpleuser',
    'password': '',  # or your password here
    'database': 'pes6_league_db'
}

CSV_FILE = 'pe6_player_data.csv'

def import_data():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # IMPORTANT: Specify encoding (try 'latin1' or 'cp1252')
        df = pd.read_csv(CSV_FILE, encoding='latin1')

        # --- Define mapping from ORIGINAL CSV Column Names to SQL Column Names ---
        raw_to_sql_column_map = {
            'ID': 'id',
            'NAME': 'player_name',
            'SHIRT_NAME': 'shirt_name',
            'CLUB TEAM': 'club_team_raw', # Temporary column to get club_id
            'REGISTERED POSITION': 'registered_position',
            'HEIGHT': 'height',
            'STRONG FOOT': 'strong_foot',
            'FAVOURED SIDE': 'favoured_side',
            'WEAK FOOT ACCURACY': 'weak_foot_accuracy', # Now removed from DB, but still in CSV/DataFrame
            'WEAK FOOT FREQUENCY': 'weak_foot_frequency', # Now removed from DB, but still in CSV/DataFrame
            'ATTACK': 'attack',
            'DEFENSE': 'defense',
            'BALANCE': 'balance',
            'STAMINA': 'stamina',
            'TOP SPEED': 'top_speed',
            'ACCELERATION': 'acceleration',
            'RESPONSE': 'response',
            'AGILITY': 'agility',
            'DRIBBLE ACCURACY': 'dribble_accuracy',
            'DRIBBLE SPEED': 'dribble_speed',
            'SHORT PASS ACCURACY': 'short_pass_accuracy',
            'SHORT PASS SPEED': 'short_pass_speed',
            'LONG PASS ACCURACY': 'long_pass_accuracy',
            'LONG PASS SPEED': 'long_pass_speed',
            'SHOT ACCURACY': 'shot_accuracy',
            'SHOT POWER': 'shot_power',
            'SHOT TECHNIQUE': 'shot_technique',
            'FREE KICK ACCURACY': 'free_kick_accuracy',
            'SWERVE': 'swerve',
            'HEADING': 'heading',
            'JUMP': 'jump',
            'TECHNIQUE': 'technique',
            'AGGRESSION': 'aggression',
            'MENTALITY': 'mentality',
            'GOAL KEEPING': 'goal_keeping',
            'TEAM WORK': 'team_work',
            'CONSISTENCY': 'consistency',
            'CONDITION / FITNESS': 'condition_fitness',
            'DRIBBLING': 'dribbling_skill',
            'TACTIAL DRIBBLE': 'tactical_dribble',
            'POSITIONING': 'positioning',
            'REACTION': 'reaction',
            'PLAYMAKING': 'playmaking',
            'PASSING': 'passing',
            'SCORING': 'scoring',
            '1-1 SCORING': 'one_one_scoring',
            'POST PLAYER': 'post_player',
            'LINES': 'lines',
            'MIDDLE SHOOTING': 'middle_shooting',
            'SIDE': 'side',
            'CENTRE': 'centre',
            'PENALTIES': 'penalties',
            '1-TOUCH PASS': 'one_touch_pass',
            'OUTSIDE': 'outside',
            'MARKING': 'marking',
            'SLIDING': 'sliding',
            'COVERING': 'covering',
            'D-LINE CONTROL': 'd_line_control',
            'PENALTY STOPPER': 'penalty_stopper',
            '1-ON-1 STOPPER': 'one_on_one_stopper',
            'LONG THROW': 'long_throw',
            'INJURY TOLERANCE': 'injury_tolerance',
            'DRIBBLE STYLE': 'dribble_style',
            'FREE KICK STYLE': 'free_kick_style',
            'PK STYLE': 'pk_style',
            'DROP KICK STYLE': 'drop_kick_style',
            'AGE': 'age',
            'WEIGHT': 'weight',
            'NATIONALITY': 'nationality',
            'SKIN COLOR': 'skin_color',
            'FACE TYPE': 'face_type',
            'PRESET FACE NUMBER': 'preset_face_number',
            'HEAD WIDTH': 'head_width',
            'NECK LENGTH': 'neck_length',
            'NECK WIDTH': 'neck_width',
            'SHOULDER HEIGHT': 'shoulder_height',
            'SHOULDER WIDTH': 'shoulder_width',
            'CHEST MEASUREMENT': 'chest_measurement',
            'WAIST CIRCUMFERENCE': 'waist_circumference',
            'ARM CIRCUMFERENCE': 'arm_circumference',
            'LEG CIRCUMFERENCE': 'leg_circumference',
            'CALF CIRCUMFERENCE': 'calf_circumference',
            'LEG LENGTH': 'leg_length',
            'WRISTBAND': 'wristband',
            'WRISTBAND COLOR': 'wristband_color',
            'INTERNATIONAL NUMBER': 'international_number',
            'CLASSIC NUMBER': 'classic_number',
            'CLUB NUMBER': 'club_number',
            'GK  0': 'gk',
            'CWP  2': 'cwp',
            'CBT  3': 'cbt',
            'SB  4': 'sb',
            'DMF  5': 'dmf',
            'WB  6': 'wb',
            'CMF  7': 'cmf',
            'SMF  8': 'smf',
            'AMF  9': 'amf',
            'WF 10': 'wf',
            'SS  11': 'ss',
            'CF  12': 'cf'
        }

        # Rename columns in the DataFrame using the map
        df = df.rename(columns=raw_to_sql_column_map)

        # --- Check for duplicate player IDs in the DataFrame ---
        duplicate_ids = df['id'][df['id'].duplicated()].unique()
        if len(duplicate_ids) > 0:
            print(f"ERROR: Duplicate player IDs found in CSV: {duplicate_ids}")
            print("Aborting import. Please fix the CSV to remove duplicates.")
            return

        # --- 1. Populate the 'teams' table ---
        print("Populating 'teams' table...")
        unique_clubs = df['club_team_raw'].dropna().unique()
        for club in unique_clubs:
            try:
                cursor.execute("INSERT INTO teams (club_name) VALUES (%s)", (club,))
            except mysql.connector.Error as err:
                if err.errno == 1062:
                    pass
                else:
                    print(f"Error inserting club {club}: {err}")
        conn.commit()
        print("Teams table populated.")

        # --- 2. Create a club_name to club_id mapping ---
        cursor.execute("SELECT id, club_name FROM teams")
        club_id_map = {name: id for id, name in cursor.fetchall()}

        # --- 3. Prepare data for 'players' table insertion ---
        print("Preparing player data for insertion...")

        # Map 'club_team_raw' to 'club_id' using the created map
        df['club_id'] = df['club_team_raw'].apply(lambda x: club_id_map.get(x) if pd.notna(x) else None)

        # --- NEW CONVERSION STEP FOR club_id ---
        if 'club_id' in df.columns and df['club_id'].isnull().any():
            df['club_id'] = df['club_id'].astype(pd.Int64Dtype())
        # ---------------------------------------

        # Drop the temporary raw club name column after mapping to club_id
        df = df.drop(columns=['club_team_raw'])

        # --- Define the final list of columns for SQL insert (un-backticked for Pandas) ---
        sql_insert_columns_unbackticked = [
            'id', 'player_name', 'shirt_name', 'club_id', 'registered_position', 'age', 'height', 'weight',
            'nationality', 'strong_foot', 'favoured_side', 'gk', 'cwp', 'cbt', 'sb', 'dmf',
            'wb', 'cmf', 'smf', 'amf', 'wf', 'ss', 'cf',
            'attack', 'defense', 'balance',
            'stamina', 'top_speed', 'acceleration', 'response', 'agility', 'dribble_accuracy',
            'dribble_speed', 'short_pass_accuracy', 'short_pass_speed', 'long_pass_accuracy',
            'long_pass_speed', 'shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy',
            'swerve', 'heading', 'jump', 'technique', 'aggression', 'mentality', 'goal_keeping',
            'team_work', 'consistency', 'condition_fitness', 'dribbling_skill', 'tactical_dribble',
            'positioning',
            'reaction',
            'playmaking',
            'passing',
            'scoring',
            'one_one_scoring',
            'post_player',
            'lines',
            'middle_shooting',
            'side',
            'centre',
            'penalties',
            'one_touch_pass',
            'outside',
            'marking',
            'sliding',
            'covering',
            'd_line_control',
            'penalty_stopper',
            'one_on_one_stopper',
            'long_throw',
            'injury_tolerance',
            'dribble_style',
            'free_kick_style',
            'pk_style',
            'drop_kick_style',
            'skin_color',
            'face_type',
            'preset_face_number',
            'head_width',
            'neck_length',
            'neck_width',
            'shoulder_height',
            'shoulder_width',
            'chest_measurement',
            'waist_circumference',
            'arm_circumference',
            'leg_circumference',
            'calf_circumference',
            'leg_length',
            'wristband',
            'wristband_color',
            'international_number',
            'classic_number',
            'club_number'
        ]

        # Select only the columns that are in our SQL insert list (unbackticked), and in that order
        df_to_insert = df[sql_insert_columns_unbackticked]

        # --- IMPORTANT: REMOVED df_to_insert.fillna(value=None) ---
        # The conversion to None will now happen explicitly in the loop below.

        # SQL INSERT statement for players
        column_names_for_sql = ', '.join([f"`{col}`" for col in sql_insert_columns_unbackticked])
        placeholders = ', '.join(['%s'] * len(sql_insert_columns_unbackticked))
        insert_player_sql = f"INSERT INTO players ({column_names_for_sql}) VALUES ({placeholders})"

        # --- DEBUG LINE ---
        print("--- DEBUG: Generated INSERT SQL ---")
        print(insert_player_sql)
        print("-----------------------------------")
        # --- END DEBUG LINE ---

        print(f"Inserting {len(df_to_insert)} players into 'players' table...")

        # Convert DataFrame rows to a list of tuples for executemany
        # This explicit conversion ensures all values are pure Python types (None for missing)
        data_to_insert = []
        for index, row in df_to_insert.iterrows():
            processed_row = []
            for item in row.values:
                # Check for any form of pandas/numpy NA and replace with None
                if pd.isna(item):
                    processed_row.append(None)
                else:
                    processed_row.append(item)
            data_to_insert.append(tuple(processed_row))

        # --- FINAL DEBUG OF data_to_insert ---
        if data_to_insert:
            print("\n--- DEBUG: First tuple in data_to_insert (after final processing) ---")
            print(data_to_insert[0])
            print("-----------------------------------------------------------------------")
        # --- END FINAL DEBUG ---

        cursor.executemany(insert_player_sql, data_to_insert)
        conn.commit()
        print("Players data imported successfully!")

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
    import_data()
