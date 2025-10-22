import pandas as pd
import numpy as np
import random
import math
import time 
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker 
import seaborn as sns
import os 
import sqlite3 
import re 
import json 

# --- Global Constants ---
GLOBAL_BASE_SALARY = 300000
# Seed value from your uploaded script
SEED_VALUE = 40
random.seed(SEED_VALUE)
np.random.seed(SEED_VALUE)
print(f"Global random seed set to: {SEED_VALUE}")

USER_TEAMS = {
    "1": {"name": "Zé", "teams": ['West Ham United', 'Newcastle United']},
    "2": {"name": "Forneira", "teams": ['Olympique Lyonnais', 'PSV Eindhoven']},
    "3": {"name": "Ganso", "teams": ['Valencia C.F.', 'Arsenal']},
    "4": {"name": "Anibal", "teams": ['F.C. Barcelona', 'SBV Excelsior']},
    "5": {"name": "Rochinha", "teams": ['Manchester United', 'CSKA Moskva']},
    "6": {"name": "Bruno", "teams": ['Juventus', 'Ajax']},
    "7": {"name": "Nene", "teams": ['Inter', 'Manchester City']},
    "8": {"name": "Josue", "teams": ['Udinese', 'A.C. Milan']}
}


# --- Helper Functions ---
def millions_formatter(x, pos):
    """Formats a number into millions, e.g., 1.5M, 10M, 0.3M."""
    if x == 0: return '0'; abs_x = abs(x)
    if abs_x < 1_000_000 and abs_x >= 100_000: return f'{x / 1_000_000:.1f}M'
    elif abs_x < 100_000 and abs_x > 0: return f'{x / 1_000_000:.2f}M'
    else: return f'{x / 1_000_000:.0f}M'

def load_csv_for_utility(file_path):
    encodings_to_try = ['utf-8', 'latin1', 'cp1252']; df = None
    for et in encodings_to_try:
        try: df = pd.read_csv(file_path, encoding=et); print(f"Successfully read '{file_path}' with encoding: {et}"); return df
        except UnicodeDecodeError: print(f"Failed to decode '{file_path}' with {et}...")
        except FileNotFoundError: print(f"Error: File '{file_path}' not found."); return None
        except pd.errors.EmptyDataError: print(f"Error: File '{file_path}' is empty."); return None
        except Exception as e: print(f"Unexpected error reading '{file_path}' with {et}: {e}")
    if df is None: print(f"Error: Could not read '{file_path}' with any attempted encodings.")
    return df

def clean_sql_col_name(col_name):
    s = str(col_name); s = re.sub(r'[^\w\s-]', '', s); s = re.sub(r'[-\s]+', '_', s)
    if s and s[0].isdigit(): s = '_' + s
    if not s: s = 'unnamed_column'
    return s

def load_and_filter_pes_data_revised(csv_file_path, columns_to_keep_input):
    encodings_to_try = ['utf-8', 'latin1', 'cp1252']; df = None
    for et in encodings_to_try:
        try: df = pd.read_csv(csv_file_path, encoding=et); break
        except:
            if et == encodings_to_try[-1]: print(f"Load Error: Could not read '{csv_file_path}' with any encoding."); return None
    if df is None: print(f"Load Error: DataFrame is None for '{csv_file_path}'."); return None
    df.columns = [' '.join(str(c).split()) for c in df.columns] 
    ctkc = [' '.join(str(c).split()) for c in columns_to_keep_input]
    missing = [c for c in ctkc if c not in df.columns]
    if missing: 
        ctkf = [c for c in ctkc if c in df.columns]; 
        print(f"Warning: Requested columns missing from CSV: {missing}. Proceeding with available: {ctkf}")
        if not ctkf and columns_to_keep_input : print(f"Error: None of the essential requested columns found: {columns_to_keep_input}"); return None
        elif not ctkf : return None
    else: 
        ctkf = ctkc
    try: 
        if not ctkf: return df 
        return df[ctkf]
    except Exception as e: print(f"Error selecting columns: {e}"); return None

def identify_true_skill_columns(df, non_skill_cols_list):
    potential_skill_cols = []
    non_skill_cols_cleaned = [' '.join(col.split()) for col in non_skill_cols_list]
    for col in df.columns:
        if col not in non_skill_cols_cleaned:
            temp_series = pd.to_numeric(df[col], errors='coerce')
            if pd.api.types.is_numeric_dtype(temp_series) and not pd.api.types.is_bool_dtype(temp_series):
                if temp_series.isna().sum() < len(df) * 0.5: 
                    potential_skill_cols.append(col)
    return potential_skill_cols

def analyze_skill_averages_by_position(df, current_skill_columns):
    if 'REGISTERED POSITION' not in df.columns: print("AnalyzeSkills Error: 'REGISTERED POSITION' column not found."); return None;
    if not current_skill_columns: print("AnalyzeSkills Error: No skill columns provided."); return None
    valid_cols = [] ; df_copy = df.copy()
    for col in current_skill_columns:
        if col in df_copy.columns: 
            df_copy[col] = pd.to_numeric(df_copy[col], errors='coerce'); 
            valid_cols.append(col)
    if not valid_cols: print("AnalyzeSkills Error: No valid skill columns for averaging."); return None
    df_copy['REGISTERED POSITION'] = df_copy['REGISTERED POSITION'].fillna('Unknown Position')
    df_clean = df_copy.dropna(subset=valid_cols) 
    if df_clean.empty: print("AnalyzeSkills Warning: DataFrame empty after NaN drop (in skills) for averaging."); return None
    try: return df_clean.groupby('REGISTERED POSITION')[valid_cols].mean()
    except Exception as e: print(f"AnalyzeSkills Error: {e}"); return None

def identify_binary_skills(df, skill_cols_list):
    b_cand = []
    if df is None or df.empty: return b_cand
    for col in skill_cols_list:
        if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
            un_val = df[col].dropna().unique()
            if all(v in [0,1] for v in un_val) and len(un_val)>0: b_cand.append(col)
    return b_cand

def calculate_player_salary_base(player_row, pos_avg_df, skills, binaries):
    # Uses parameters from your uploaded script
    NORM=75.0; BIN_IMPACT=0.15; R_START=70.0; R_END=99.0; MIN_MULT=0.5; MAX_MULT=4.0
    DEF_BOOST=4.0; GK_BOOST=4.0; DEF_NAME='DEFENSE'; GK_NAME='GOAL KEEPING'
    DIV=1000.0; POW=3.0; SCALER=970000.0
    pos = player_row['REGISTERED POSITION']; pos_clean = pos if pd.notna(pos) else 'Unknown Position'
    
    if pos_avg_df is None or pos_clean not in pos_avg_df.index: 
        pos_spec_avg = pd.Series(NORM, index=skills)
    else: 
        pos_spec_avg = pos_avg_df.loc[pos_clean]
        if not isinstance(pos_spec_avg, pd.Series) : 
             pos_spec_avg = pd.Series(NORM, index=skills)

    twss = 0
    for skill_n in skills:
        if skill_n not in player_row or pd.isna(player_row[skill_n]): continue
        val = float(player_row[skill_n]); mult = MIN_MULT
        if val >= R_END: mult = MAX_MULT
        elif val > R_START:
            prog = (val - R_START) / (R_END - R_START)
            if MIN_MULT > 0 or MAX_MULT > 0:
                if MIN_MULT == 0 and MAX_MULT > 0: mult = MAX_MULT * math.pow(prog, 2)
                elif MIN_MULT > 0: mult = MIN_MULT * math.pow(MAX_MULT / MIN_MULT, prog)
        eff_val = val * mult
        skill_imp_val = pos_spec_avg.get(skill_n, NORM) if isinstance(pos_spec_avg, pd.Series) else NORM
        imp = skill_imp_val / NORM
        contrib = eff_val * imp
        if skill_n == DEF_NAME: contrib *= DEF_BOOST
        elif skill_n == GK_NAME: contrib *= GK_BOOST
        if skill_n in binaries: contrib *= BIN_IMPACT
        twss += contrib
    twss = max(0, twss); norm_twss = twss / DIV; pow_score = math.pow(max(0, norm_twss), POW)
    sal_skills = pow_score * SCALER; calc_sal = GLOBAL_BASE_SALARY + sal_skills
    return max(GLOBAL_BASE_SALARY, round(calc_sal / 1000) * 1000)

def apply_random_salary_adjustment(base_salary):
    factor = random.uniform(-0.20, 0.20); adj_sal = base_salary * (1 + factor)
    return round(max(GLOBAL_BASE_SALARY, adj_sal) / 1000) * 1000

def get_age_market_value_multiplier(age_val):
    if pd.isna(age_val): return 1.0; age = float(age_val)
    y_ref, y_fact = 16.0, 4.0; p_ref, p_fact = 29.0, 1.0; o_ref, o_fact = 40.0, 0.01
    k_y, k_o = 1.5, 3.0
    if age <= y_ref: return y_fact
    elif age < p_ref: prog = (age - y_ref) / (p_ref - y_ref); return p_fact + (y_fact - p_fact) * math.pow(1-prog, k_y)
    elif age == p_ref: return p_fact
    elif age < o_ref: prog = (age - p_ref) / (o_ref - p_ref); return o_fact + (p_fact - o_fact) * math.pow(1-prog, k_o)
    else: return o_fact

def determine_contract_years(age_val):
    if pd.isna(age_val): return random.randint(2, 3)
    try: age = int(float(age_val))
    except ValueError: return random.randint(2,3)
    if age > 32: return random.randint(1, 2)
    elif age > 30: return random.randint(1, 3)
    else: return random.randint(2, 5)

def calculate_yearly_wage_raise(player_row, skills, binaries, salary):
    age_val = player_row['AGE']
    try: age = int(float(age_val)) if pd.notna(age_val) else 25
    except ValueError: age = 25
    num_skills = [s for s in skills if s not in binaries and s in player_row and pd.notna(player_row[s])]
    if not num_skills: avg_skill = 60.0
    else: 
        avg_skill = pd.to_numeric(player_row[num_skills], errors='coerce').mean();
        if pd.isna(avg_skill): avg_skill = 60.0
    rp = 0.0
    if age <= 23 and avg_skill >= 78: rp = random.uniform(0.15,0.25);
    elif age <= 23 and avg_skill >= 70: rp = random.uniform(0.10,0.20)
    elif age <= 26 and avg_skill >= 75: rp = random.uniform(0.08,0.18)
    elif age <= 29 and avg_skill >= 72: rp = random.uniform(0.05,0.12)
    elif age > 32 or avg_skill < 65: rp = random.uniform(0.00,0.05)
    else: rp = random.uniform(0.03,0.08)
    if salary < (GLOBAL_BASE_SALARY*5): rp *= 1.1
    return round(min(rp, 0.25), 3)

def update_sql_database_upsert(df_to_update_input, db_name, table_name, id_column_original_csv_name):
    if not os.path.exists(db_name):
        print(f"SQL Update Error: Database '{db_name}' does not exist. Please create it first (Routine 4).")
        return False
    df_to_update = df_to_update_input.copy()
    df_to_update.columns = [clean_sql_col_name(col) for col in df_to_update.columns]
    sql_id_column_name = clean_sql_col_name(id_column_original_csv_name)
    if sql_id_column_name not in df_to_update.columns:
        print(f"SQL Update Error: ID column '{sql_id_column_name}' not found in the DataFrame for update.")
        return False
    conn = None
    try:
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()
        cols_for_sql = df_to_update.columns.tolist()
        quoted_cols_str = ', '.join([f'"{c}"' for c in cols_for_sql])
        q_marks_str = ', '.join(['?'] * len(cols_for_sql))
        update_cols = [f'"{c}" = excluded."{c}"' for c in cols_for_sql if c != sql_id_column_name]
        if not update_cols: upsert_sql = f"INSERT OR IGNORE INTO \"{table_name}\" ({quoted_cols_str}) VALUES ({q_marks_str});"
        else:
            update_set_str = ', '.join(update_cols)
            upsert_sql = f"INSERT INTO \"{table_name}\" ({quoted_cols_str}) VALUES ({q_marks_str}) ON CONFLICT(\"{sql_id_column_name}\") DO UPDATE SET {update_set_str};"
        data_to_upsert = [tuple(None if pd.isna(val) else val for val in x) for x in df_to_update.to_numpy()]
        cursor.executemany(upsert_sql, data_to_upsert)
        conn.commit()
        print(f"SQL Update: Successfully upserted/processed {len(df_to_update)} records into table '{table_name}'.")
        return True
    except Exception as e:
        if conn: conn.rollback()
        print(f"SQL Update Error during upsert: {e}")
        return False
    finally:
        if conn: conn.close()

# --- Routine 1: Salary and Value Calculator ---
def run_salary_and_value_calculator(input_csv_path, id_col_csv, club_team_col_csv, db_info):
    print(f"Starting Salary and Value Calculator using: {input_csv_path}")
    initial_columns_to_keep = [
        'NAME', 'REGISTERED POSITION', 'HEIGHT', 'ATTACK', 'DEFENSE', 'BALANCE', 'STAMINA', 'TOP SPEED', 
        'ACCELERATION', 'RESPONSE', 'AGILITY', 'DRIBBLE ACCURACY', 'DRIBBLE SPEED', 
        'SHORT PASS ACCURACY', 'SHORT PASS SPEED', 'LONG PASS ACCURACY', 'LONG PASS SPEED', 
        'SHOT ACCURACY', 'SHOT POWER', 'SHOT TECHNIQUE', 'FREE KICK ACCURACY', 'SWERVE', 
        'HEADING', 'JUMP', 'TECHNIQUE', 'AGGRESSION', 'MENTALITY', 'GOAL KEEPING', 
        'TEAM WORK', 'CONSISTENCY', 'CONDITION / FITNESS', 'DRIBBLING', 'TACTIAL DRIBBLE',
        'POSITIONING', 'REACTION', 'PLAYMAKING', 'PASSING', 'SCORING', '1-1 SCORING', 
        'POST PLAYER', 'LINES', 'MIDDLE SHOOTING', 'SIDE', 'CENTRE', 'PENALTIES', 
        '1-TOUCH PASS', 'OUTSIDE', 'MARKING', 'SLIDING', 'COVERING', 'D-LINE CONTROL', 
        'PENALTY STOPPER', '1-ON-1 STOPPER', 'LONG THROW', 'INJURY TOLERANCE', 'AGE',
        'WEAK FOOT ACCURACY', 'WEAK FOOT FREQUENCY']
    if id_col_csv not in initial_columns_to_keep: initial_columns_to_keep.append(id_col_csv)
    if club_team_col_csv not in initial_columns_to_keep: initial_columns_to_keep.append(club_team_col_csv)

    cleaned_id_col_name = ' '.join(id_col_csv.split())
    cleaned_club_team_col_name = ' '.join(club_team_col_csv.split())
    non_skill_cols_explicit = [' '.join(col.split()) for col in ['NAME', 'REGISTERED POSITION', 'HEIGHT', 'AGE']]
    if cleaned_id_col_name not in non_skill_cols_explicit: non_skill_cols_explicit.append(cleaned_id_col_name)
    if cleaned_club_team_col_name not in non_skill_cols_explicit: non_skill_cols_explicit.append(cleaned_club_team_col_name)
    
    output_prefix = "routine1_"
    output_averages_path = f"{output_prefix}pos_skill_averages.csv"; output_final_path = f"{output_prefix}players_financials.csv"
    summary_output_path = f"{output_prefix}player_summary.csv"; player_salary_graph_path = f"{output_prefix}top_player_salaries.png"
    market_value_graph_path = f"{output_prefix}top_market_values.png"; team_salary_csv_path = f"{output_prefix}team_salaries.csv"
    team_graph_path = f"{output_prefix}top_team_salaries.png"; density_graph_path = f"{output_prefix}salary_density.png"

    processed_df = load_and_filter_pes_data_revised(input_csv_path, initial_columns_to_keep)
    if processed_df is None or processed_df.empty: print("R1: Load failed."); return
    print(f"R1 - Step 1: Data loaded. Shape: {processed_df.shape}")
    if 'AGE' in processed_df.columns: processed_df['AGE'] = pd.to_numeric(processed_df['AGE'], errors='coerce')
    if cleaned_id_col_name in processed_df.columns: processed_df[cleaned_id_col_name] = processed_df[cleaned_id_col_name].astype(str)
    actual_skill_columns = identify_true_skill_columns(processed_df.copy(), non_skill_cols_explicit)
    if not actual_skill_columns: print("R1 - Error: No skills."); return
    print(f"R1 - Identified {len(actual_skill_columns)} skills.")
    for col in actual_skill_columns: 
        if col in processed_df.columns: processed_df[col] = pd.to_numeric(processed_df[col], errors='coerce')
    position_averages_df = analyze_skill_averages_by_position(processed_df.copy(), actual_skill_columns)
    if position_averages_df is None or position_averages_df.empty:
        _cols=actual_skill_columns if actual_skill_columns else ['ATTACK']
        _idx_data = processed_df['REGISTERED POSITION'].unique() if 'REGISTERED POSITION' in processed_df.columns else ['GK']
        _index = pd.Index([pos for pos in _idx_data if pd.notna(pos)]); 
        if _index.empty: _index = pd.Index(['GK']); 
        position_averages_df=pd.DataFrame(75.0,index=_index,columns=_cols)
    else: position_averages_df.to_csv(output_averages_path)
    binary_skill_cols = identify_binary_skills(processed_df, actual_skill_columns)
    print(f"R1 - Identified {len(binary_skill_cols)} binary skills.")
    print("R1 - Generating Base Salaries...")
    processed_df['Salary_Base_Calculated'] = processed_df.apply(
        lambda r: calculate_player_salary_base(r, position_averages_df, actual_skill_columns, binary_skill_cols), axis=1)
    print("R1 - Generating Market Values...")
    processed_df['Market Value'] = processed_df['Salary_Base_Calculated'] * 1.5
    processed_df['MV_Age_Mult'] = processed_df['AGE'].apply(get_age_market_value_multiplier)
    processed_df['Market Value'] = processed_df['Market Value'] * processed_df['MV_Age_Mult']
    if cleaned_club_team_col_name in processed_df.columns:
        processed_df[cleaned_club_team_col_name] = processed_df[cleaned_club_team_col_name].fillna('No Club').astype(str)
        no_club_cond = (processed_df[cleaned_club_team_col_name].str.strip()=='')|(processed_df[cleaned_club_team_col_name]=='No Club')
        processed_df.loc[no_club_cond, 'Market Value'] = 0
    processed_df['Market Value'] = processed_df['Market Value'].round(0).astype(int)
    print("R1 - Applying Random Adjustment to Salaries...")
    processed_df['Salary'] = processed_df['Salary_Base_Calculated'].apply(apply_random_salary_adjustment)
    print("R1 - Generating Contract Years..."); processed_df['Contract Years Remaining'] = processed_df['AGE'].apply(determine_contract_years)
    print("R1 - Generating Yearly Wage Raise..."); processed_df['Yearly Wage Raise'] = processed_df.apply(
        lambda r: calculate_yearly_wage_raise(r, actual_skill_columns, binary_skill_cols, r['Salary']), axis=1)
    df_save = processed_df.drop(columns=['Salary_Base_Calculated', 'MV_Age_Mult'], errors='ignore')
    df_save.to_csv(output_final_path, index=False); print(f"R1 - Final data saved to '{output_final_path}'")
    
    cols_summary = [c for c in [cleaned_id_col_name,'NAME','Salary','Market Value','Contract Years Remaining','Yearly Wage Raise'] if c in df_save.columns]
    if len(cols_summary) >= 5 : df_save[cols_summary].to_csv(summary_output_path, index=False); print(f"R1 - Financial summary saved.")

    print("\nR1 - Generating graphs...")
    comma_formatter = ticker.FuncFormatter(lambda x, p: f'{int(x):,}')
    
    # Top 10 Players Salary Graph
    if 'Salary' in df_save.columns and 'NAME' in df_save.columns:
        try:
            top_10_salary = df_save.sort_values(by='Salary', ascending=False).head(10)
            if not top_10_salary.empty:
                plt.figure(figsize=(12, 8)); bars = plt.bar(top_10_salary['NAME'], top_10_salary['Salary'], color='darkgoldenrod');
                plt.title("Top 10 Players by Salary", fontsize=14); plt.ylabel("Salary (Yearly)", fontsize=12); plt.xlabel("Player Name", fontsize=12)
                plt.xticks(rotation=45, ha="right", fontsize=10); plt.gca().yaxis.set_major_formatter(comma_formatter)
                for bar in bars: plt.text(bar.get_x() + bar.get_width()/2.0, bar.get_height(), f'{int(bar.get_height()):,}', ha='center', va='bottom', fontsize=9)
                plt.grid(axis='y', linestyle='--', alpha=0.7); plt.tight_layout(); plt.savefig(player_salary_graph_path); plt.show()
                print(f"R1 - Graph saved: {player_salary_graph_path}")
        except Exception as e: print(f"R1 - Error plotting top salaries: {e}")

    # Top 10 Players by Market Value Graph
    if 'Market Value' in df_save.columns and 'NAME' in df_save.columns:
        try:
            top_10_mv = df_save.sort_values(by='Market Value', ascending=False).head(10)
            if not top_10_mv.empty:
                plt.figure(figsize=(12, 8)); bars_mv = plt.bar(top_10_mv['NAME'], top_10_mv['Market Value'], color='forestgreen');
                plt.title("Top 10 Players by Market Value", fontsize=14); plt.ylabel("Market Value", fontsize=12); plt.xlabel("Player Name", fontsize=12)
                plt.xticks(rotation=45, ha="right", fontsize=10); plt.gca().yaxis.set_major_formatter(comma_formatter)
                for bar in bars_mv: plt.text(bar.get_x() + bar.get_width()/2.0, bar.get_height(), f'{int(bar.get_height()):,}', ha='center', va='bottom', fontsize=9)
                plt.grid(axis='y', linestyle='--', alpha=0.7); plt.tight_layout(); plt.savefig(market_value_graph_path); plt.show()
                print(f"R1 - Graph saved: {market_value_graph_path}")
        except Exception as e: print(f"R1 - Error plotting top MV: {e}")
    
    # Top 10 Teams by Total Salary Graph
    if cleaned_club_team_col_name in df_save.columns and 'Salary' in df_save.columns:
        valid_teams_df = df_save[df_save[cleaned_club_team_col_name].fillna('No Club').str.strip().ne('')]
        if not valid_teams_df.empty:
            team_salaries = valid_teams_df.groupby(cleaned_club_team_col_name)['Salary'].sum().sort_values(ascending=False).reset_index()
            team_salaries.rename(columns={'Salary': 'Total Salary Cost'}, inplace=True)
            team_salaries.to_csv(team_salary_csv_path, index=False)
            if not team_salaries.empty:
                top_10_teams = team_salaries.head(10)
                try:
                    plt.figure(figsize=(12, 8)); bars_team = plt.bar(top_10_teams[cleaned_club_team_col_name], top_10_teams['Total Salary Cost'], color='firebrick');
                    plt.title("Top 10 Teams by Total Salary Cost", fontsize=14); plt.ylabel("Total Salary Cost", fontsize=12); plt.xlabel("Club Team", fontsize=12)
                    plt.xticks(rotation=45, ha="right", fontsize=10); plt.gca().yaxis.set_major_formatter(comma_formatter)
                    for bar in bars_team: plt.text(bar.get_x() + bar.get_width()/2.0, bar.get_height(), f'{int(bar.get_height()):,}', ha='center', va='bottom', fontsize=9)
                    plt.grid(axis='y', linestyle='--', alpha=0.7); plt.tight_layout(); plt.savefig(team_graph_path); plt.show()
                    print(f"R1 - Top team salary graph saved.")
                except Exception as e: print(f"R1 - Error plotting team salaries: {e}")
                
    # Salary Distribution Density Plot
    if 'Salary' in df_save.columns:
        try:
            plt.figure(figsize=(10,6)); ax_density = sns.kdeplot(df_save['Salary'], fill=True, color="teal", bw_adjust=0.5);
            ax_density.xaxis.set_major_formatter(comma_formatter) 
            plt.title("Salary Distribution Density"); plt.xlabel("Salary"); plt.ylabel("Density"); 
            plt.grid(axis='y', linestyle='--', alpha=0.7); plt.tight_layout(); plt.savefig(density_graph_path); plt.show()
            print(f"R1 - Salary density graph saved.")
        except Exception as e: print(f"R1 - Error plotting salary density: {e}")
    
    update_prompt = input("Routine 1 finished. Update SQL database with this data? (Y/N): ").strip().upper()
    if update_prompt == 'Y':
        update_sql_database_upsert(df_save, db_info['name'], db_info['table'], id_column_original_csv_name=id_col_csv)
    print("Routine 1: New Salary and Value Calculator - Finished.")

# --- Routine 2: End of the Year Player Age Updator ---
def run_age_updater(input_csv_path, output_csv_path, age_col_name, db_info, id_col_csv):
    print(f"Starting Age Updater using: {input_csv_path}")
    df = load_csv_for_utility(input_csv_path)
    if df is None: print("R2: Load failed."); return
    df.columns = [' '.join(str(col).split()) for col in df.columns]
    age_col_cleaned = ' '.join(age_col_name.split())
    if age_col_cleaned in df.columns:
        df[age_col_cleaned] = pd.to_numeric(df[age_col_cleaned], errors='coerce') + 1
        try:
            df.to_csv(output_csv_path, index=False); print(f"R2: Successfully updated ages and saved to '{output_csv_path}'")
            update_prompt = input("Routine 2 finished. Update SQL database with this aged data? (Y/N): ").strip().upper()
            if update_prompt == 'Y':
                update_sql_database_upsert(df, db_info['name'], db_info['table'], id_column_original_csv_name=id_col_csv)
        except Exception as e: print(f"R2: Error saving aged data: {e}")
    else: print(f"R2 - Error: Column '{age_col_cleaned}' not found.")
    print("Routine 2: End of the Year Player Age Updator - Finished.")

# --- Routine 3: Player Reaper (Retirement) ---
def get_retirement_probability(age_val):
    if pd.isna(age_val): return 0.0; age = int(age_val)
    if age <= 33: return 0.0; 
    elif age == 34: return 0.05; 
    elif age == 35: return 0.10;
    elif age == 36: return 0.20; 
    elif age == 37: return 0.35; 
    elif age == 38: return 0.50;
    elif age == 39: return 0.70; 
    elif age >= 40: return 0.90; 
    return 0.0

def run_player_reaper(input_csv_path, output_csv_path, age_col_name, db_info, id_col_csv):
    print(f"Starting Player Reaper using: {input_csv_path}")
    df = load_csv_for_utility(input_csv_path)
    if df is None: print("R3: Load failed."); return
    df.columns = [' '.join(str(col).split()) for col in df.columns]
    age_col_cleaned = ' '.join(age_col_name.split()); id_col_cleaned_for_access = ' '.join(id_col_csv.split())
    if age_col_cleaned in df.columns and id_col_cleaned_for_access in df.columns:
        df[age_col_cleaned] = pd.to_numeric(df[age_col_cleaned], errors='coerce')
        initial_count = len(df); retire_indices = []
        for idx, row in df.iterrows():
            age = row[age_col_cleaned]
            if pd.notna(age) and age > 33:
                if random.random() < get_retirement_probability(age): retire_indices.append(idx)
        df_surviving = df.drop(retire_indices); df_retired = df.loc[retire_indices]
        print(f"R3: Players retired in this run: {len(df_retired)} out of {initial_count}")
        try:
            df_surviving.to_csv(output_csv_path, index=False); print(f"R3: Surviving players saved.")
            update_prompt = input("R3 finished. Update SQL (Upsert survivors & delete retired)? (Y/N): ").strip().upper()
            if update_prompt == 'Y':
                print("R3 SQL Update: Upserting surviving players...")
                update_sql_database_upsert(df_surviving, db_info['name'], db_info['table'], id_column_original_csv_name=id_col_csv)
                if not df_retired.empty:
                    retired_ids_vals = df_retired[id_col_cleaned_for_access].tolist()
                    if retired_ids_vals:
                        conn = None
                        try:
                            conn = sqlite3.connect(db_info['name']); cursor = conn.cursor()
                            sql_id_col_sql = clean_sql_col_name(id_col_csv)
                            placeholders = ', '.join('?'*len(retired_ids_vals))
                            del_q = f"DELETE FROM \"{db_info['table']}\" WHERE \"{sql_id_col_sql}\" IN ({placeholders});"
                            cursor.execute(del_q, retired_ids_vals); conn.commit()
                            print(f"R3 SQL Update: Deleted {cursor.rowcount} retired from SQL.")
                        except Exception as e:
                            if conn: conn.rollback(); print(f"R3 SQL Delete Error: {e}")
                        finally:
                            if conn: conn.close()
        except Exception as e: print(f"R3: Error saving/processing: {e}")
    else: print(f"R3 - Error: Col '{age_col_cleaned}' or '{id_col_cleaned_for_access}' not found.")
    print("Routine 3: Player Reaper - Finished.")

# --- Routine 4: Create SQL Database ---
def run_create_sql_database(input_csv_path, db_name, table_name, column_map_file, id_col_csv_original):
    print(f"Attempting to create SQL DB '{db_name}' table '{table_name}' from '{input_csv_path}'.")
    if os.path.exists(db_name): print(f"DB Creation Error: DB '{db_name}' already exists."); return
    df_for_schema = load_csv_for_utility(input_csv_path)
    if df_for_schema is None or df_for_schema.empty: print(f"DB Creation Error: Load failed."); return
    original_columns = df_for_schema.columns.tolist(); cleaned_cols = [clean_sql_col_name(c) for c in original_columns]
    cleaned_map = dict(zip(original_columns, cleaned_cols)); df_insert = df_for_schema.copy(); df_insert.columns = cleaned_cols
    sql_id_col = clean_sql_col_name(id_col_csv_original)
    if sql_id_col not in df_insert.columns: print(f"DB Creation Error: SQL ID col '{sql_id_col}' not found."); return
    conn = None
    try:
        conn = sqlite3.connect(db_name); cursor = conn.cursor(); cols_types = []
        for orig_c, clean_c in cleaned_map.items():
            dtype = df_for_schema[orig_c].dtype
            if clean_c == sql_id_col: sql_type = "TEXT PRIMARY KEY"
            elif pd.api.types.is_integer_dtype(dtype): sql_type = "INTEGER"
            elif pd.api.types.is_float_dtype(dtype): sql_type = "REAL"
            elif pd.api.types.is_bool_dtype(dtype): sql_type = "INTEGER"
            else: sql_type = "TEXT"
            cols_types.append(f'"{clean_c}" {sql_type}')
        create_sql = f"CREATE TABLE IF NOT EXISTS \"{table_name}\" ({', '.join(cols_types)})"
        cursor.execute(create_sql); conn.commit()
        df_insert.to_sql(table_name, conn, if_exists='append', index=False)
        print(f"DB '{db_name}' table '{table_name}' created with {len(df_insert)} records.");
        with open(column_map_file, 'w') as f: json.dump(cleaned_map, f, indent=4); print(f"Map saved: {column_map_file}")
    except Exception as e: print(f"DB Creation Error: {e}")
    finally:
        if conn: conn.close()
    print("Routine 4: Create SQL Database - Finished.")

# --- Routine 5: Export SQL to CSV ---
def run_export_sql_to_csv(db_name, table_name, output_csv_path, column_map_file):
    print(f"Exporting SQL table '{table_name}' from DB '{db_name}' to '{output_csv_path}'.")
    if not os.path.exists(db_name): print(f"Export Error: DB '{db_name}' missing."); return
    if not os.path.exists(column_map_file): print(f"Export Error: Map '{column_map_file}' missing."); return
    try:
        with open(column_map_file, 'r') as f: o2s_map = json.load(f); s2o_map = {v:k for k,v in o2s_map.items()}
    except Exception as e: print(f"Export Error loading map: {e}"); return
    conn = None
    try:
        conn = sqlite3.connect(db_name); df_sql = pd.read_sql_query(f"SELECT * FROM \"{table_name}\"", conn)
        df_sql.rename(columns=s2o_map, inplace=True); df_sql.to_csv(output_csv_path, index=False)
        print(f"Successfully exported to '{output_csv_path}'.")
    except Exception as e: print(f"Export Error: {e}")
    finally:
        if conn: conn.close()
    print("Routine 5: Export SQL to CSV - Finished.")

# --- Routine 6: Find Player Replacement (Standard) ---
def run_find_replacement(routine1_output_path, id_col_csv, club_team_col_csv, non_skill_cols_info):
    print(f"Starting Player Replacement Finder using: {routine1_output_path}")
    if not os.path.exists(routine1_output_path): print(f"Error: Input file '{routine1_output_path}' not found. Please run Routine 1 first."); return
    df = load_csv_for_utility(routine1_output_path)
    if df is None or df.empty: print("Failed to load data for Replacement Finder. Aborting routine."); return
    df.columns = [' '.join(str(c).split()) for c in df.columns]
    id_col_cleaned = ' '.join(id_col_csv.split())
    club_team_col_cleaned = ' '.join(club_team_col_csv.split())
    if id_col_cleaned not in df.columns: print(f"Error: ID column '{id_col_cleaned}' not found."); return
    df[id_col_cleaned] = df[id_col_cleaned].astype(str)
    skill_cols = identify_true_skill_columns(df.copy(), non_skill_cols_info)
    if not skill_cols: print("Error: Could not identify skill columns."); return
    while True:
        sold_player_id = input("Which player was sold? (Enter player ID, or type 'back' to return to main menu): ").strip()
        if sold_player_id.lower() == 'back': break
        sold_player_series = df[df[id_col_cleaned] == sold_player_id]
        if sold_player_series.empty: print(f"Error: Player with ID '{sold_player_id}' not found."); continue
        sold_player = sold_player_series.iloc[0]
        sold_player_name=sold_player.get('NAME','N/A'); sold_player_pos=sold_player.get('REGISTERED POSITION','N/A')
        available_funds = sold_player.get('Salary', 0) + sold_player.get('Market Value', 0)
        print(f"\n--- Player Sold: {sold_player_name} ({sold_player_pos}) ---")
        print(f"Funds available: {available_funds:,.0f}")
        sold_player_skills = sold_player[skill_cols].fillna(0)
        replacements_df = df[(df['REGISTERED POSITION'] == sold_player_pos) & (df[id_col_cleaned] != sold_player_id)].copy()
        if replacements_df.empty: print(f"No other players found with the same position."); continue
        print("\nCalculating similarity...")
        replacements_df['SimilarityDistance'] = replacements_df.apply(lambda r: np.linalg.norm(sold_player_skills.values - r[skill_cols].fillna(0).values), axis=1)
        top_10_replacements = replacements_df.sort_values(by='SimilarityDistance').head(10).reset_index(drop=True)
        replacement_accepted = False
        for i, suggested_player in top_10_replacements.iterrows():
            s_name = suggested_player.get('NAME', 'N/A'); s_club = suggested_player.get(club_team_col_cleaned, 'N/A')
            s_mv = suggested_player.get('Market Value', 0); s_salary = suggested_player.get('Salary', 0)
            s_contract = suggested_player.get('Contract Years Remaining', 0)
            print("\n-------------------------------------------")
            print(f"Suggestion {i + 1} of {len(top_10_replacements)} (Most similar first)")
            print(f"       Name: {s_name}\n  Club Team: {s_club}\nMarket Value: {s_mv:,.0f}\n      Salary: {s_salary:,.0f}\nContract Yrs: {s_contract}")
            print("-------------------------------------------")
            while True:
                choice = input("Accept this player as the replacement? (Y/N): ").strip().upper()
                if choice == 'Y': print(f"\n✅ Player '{s_name}' accepted!"); replacement_accepted = True; break
                elif choice == 'N': print("... Checking next suggestion ..."); break
                else: print("Invalid input. Please enter 'Y' or 'N'.")
            if replacement_accepted: break
        if not replacement_accepted: print("\nNo replacement was accepted from the top 10 suggestions.")
        print("\nReturning to replacement finder prompt...")

# --- NEW Routine 7: Find Player Replacement (Targeted Clubs with Negotiation) ---
def run_targeted_replacement_finder(routine1_output_path, id_col_csv, club_team_col_csv, non_skill_cols_info):
    print(f"Starting Targeted Replacement Finder using: {routine1_output_path}")
    if not os.path.exists(routine1_output_path): print(f"Error: Input file '{routine1_output_path}' not found. Run R1 first."); return
    df = load_csv_for_utility(routine1_output_path)
    if df is None or df.empty: print("Failed to load data for Targeted Finder."); return
    df.columns = [' '.join(str(c).split()) for c in df.columns]
    id_col_cleaned = ' '.join(id_col_csv.split()); club_team_col_cleaned = ' '.join(club_team_col_csv.split())
    if id_col_cleaned not in df.columns: print(f"Error: ID column '{id_col_cleaned}' not found."); return
    df[id_col_cleaned] = df[id_col_cleaned].astype(str)
    skill_cols = identify_true_skill_columns(df.copy(), non_skill_cols_info)
    if not skill_cols: print("Error: Could not identify skill columns."); return
    target_clubs = ['A.C. Milan', 'Ajax', 'Arsenal', 'CSKA Moskva', 'F.C. Barcelona', 'Inter', 'Juventus', 'Manchester City', 'Manchester United', 'Newcastle United', 'PSV Eindhoven', 'SBV Excelsior', 'Udinese', 'West Ham United', 'Valencia C.F.', 'Olympique Lyonnais']
    
    while True:
        sold_player_id = input("\nWhich player was sold? (Enter ID, or 'back'): ").strip()
        if sold_player_id.lower() == 'back': break
        sold_player_series = df[df[id_col_cleaned] == sold_player_id]
        if sold_player_series.empty: print(f"Error: Player with ID '{sold_player_id}' not found."); continue
        sold_player = sold_player_series.iloc[0]
        sold_player_name=sold_player.get('NAME','N/A'); sold_player_pos=sold_player.get('REGISTERED POSITION','N/A')
        print(f"\n--- Player Sold: {sold_player_name} ({sold_player_pos}) ---")
        sold_player_skills = sold_player[skill_cols].fillna(0)
        replacements_df = df[(df[club_team_col_cleaned].isin(target_clubs)) & (df['REGISTERED POSITION'] == sold_player_pos) & (df[id_col_cleaned] != sold_player_id)].copy()
        
        player_accepted = False
        if not replacements_df.empty:
            print("\nCalculating similarity for players from target clubs...")
            replacements_df['SimilarityDistance'] = replacements_df.apply(lambda r: np.linalg.norm(sold_player_skills.values - r[skill_cols].fillna(0).values), axis=1)
            top_10_replacements = replacements_df.sort_values(by='SimilarityDistance').head(10).reset_index(drop=True)
            for i, suggested_player in top_10_replacements.iterrows():
                os.system('cls' if os.name == 'nt' else 'clear'); print(f"--- Presenting Suggestion {i + 1} of {len(top_10_replacements)} from Target Clubs ---")
                s_name = suggested_player.get('NAME','N/A'); s_club = suggested_player.get(club_team_col_cleaned,'N/A'); s_mv = suggested_player.get('Market Value',0)
                s_salary = suggested_player.get('Salary', 0); s_contract = suggested_player.get('Contract Years Remaining', 0)
                current_offer = s_mv * random.uniform(0.25, 0.75); negotiation_prob = 0.75
                while True:
                    print(f"\nTarget: {s_name} ({s_club})\nMarket Value: {s_mv:,.0f}\nSalary: {s_salary:,.0f} | Contract: {s_contract} yrs\n\nOFFER: {current_offer:,.0f}")
                    action = input("Decision? (1: Accept, 2: Negotiate, 3: Reject & Next): ").strip()
                    if action == '1': print(f"\n✅ OFFER ACCEPTED! Signed {s_name}."); player_accepted = True; break
                    elif action == '2':
                        if random.random() < negotiation_prob:
                            new_offer = current_offer * (1 + random.uniform(0.05, 0.15))
                            print(f"\nIMPROVED OFFER: {new_offer:,.0f}"); current_offer = new_offer
                            negotiation_prob -= random.uniform(0.05, 0.15)
                        else: print("\nNegotiations broke down!"); break
                    elif action == '3': print("... Rejecting suggestion ..."); break
                    else: print("Invalid choice.")
                if player_accepted: break
        
        if player_accepted: continue
        print("\n--- No player signed. Searching for best free agent... ---")
        free_agents_df = df[(df[club_team_col_cleaned] == 'No Club') & (df['REGISTERED POSITION'] == sold_player_pos) & (df[id_col_cleaned] != sold_player_id)].copy()
        if free_agents_df.empty: print(f"No free agents found at position '{sold_player_pos}'.")
        else:
            free_agents_df['SimilarityDistance'] = free_agents_df.apply(lambda r: np.linalg.norm(sold_player_skills.values - r[skill_cols].fillna(0).values), axis=1)
            best_free_agent = free_agents_df.sort_values(by='SimilarityDistance').iloc[0]
            s_name=best_free_agent.get('NAME','N/A'); s_mv=best_free_agent.get('Market Value',0); s_sal=best_free_agent.get('Salary',0)
            print(f"\n--- Fallback Suggestion ---\nName: {s_name}\nClub: No Club\nMarket Value: {s_mv:,.0f}\nSalary: {s_sal:,.0f}")

# --- NEW Routine 8: Sell a Player (Negotiation) ---
def generate_initial_offer(player_to_sell, bidding_club_squad):
    sold_player_mv = player_to_sell.get('Market Value', 0)
    target_offer_value = sold_player_mv * random.uniform(0.25, 0.75)
    if random.random() < 0.3 and not bidding_club_squad.empty:
        suitable_exchange = bidding_club_squad[bidding_club_squad['Market Value'] < target_offer_value]
        if not suitable_exchange.empty:
            exchange_player = suitable_exchange.sample(1).iloc[0]
            cash_component = max(0, target_offer_value - exchange_player.get('Market Value', 0))
            return {'cash': cash_component, 'player_swap': exchange_player, 'loan': None}
    return {'cash': target_offer_value, 'player_swap': None, 'loan': None}

def generate_counter_offer(current_offer, player_to_sell, bidding_club_squad):
    current_cash = current_offer.get('cash', 0)
    swap_player = current_offer.get('player_swap')
    swap_player_mv = swap_player.get('Market Value', 0) if swap_player is not None else 0
    current_total_value = current_cash + swap_player_mv
    new_total_value = current_total_value * (1 + random.uniform(0.05, 0.15))
    offer_type = random.choices(['cash', 'player_swap', 'loan'], weights=[0.55, 0.3, 0.15], k=1)[0]
    
    if offer_type == 'cash':
        print(f"\nThey have improved their cash offer!")
        return {'cash': new_total_value, 'player_swap': None, 'loan': None}
    elif offer_type == 'player_swap' and not bidding_club_squad.empty:
        suitable_exchange = bidding_club_squad[bidding_club_squad['Market Value'] < new_total_value]
        if not suitable_exchange.empty:
            exchange_player = suitable_exchange.sample(1).iloc[0]
            exchange_name = exchange_player.get('NAME', 'N/A'); exchange_mv = exchange_player.get('Market Value', 0)
            cash_component = max(0, new_total_value - exchange_mv)
            print(f"\nAs a counter-offer, they are now offering {exchange_name} (MV: {exchange_mv:,.0f}) plus cash!")
            return {'cash': cash_component, 'player_swap': exchange_player, 'loan': current_offer.get('loan')}
    elif offer_type == 'loan' and not bidding_club_squad.empty and current_offer.get('loan') is None:
        salary_out = player_to_sell.get('Salary', 0)
        salary_in = swap_player.get('Salary', 0) if swap_player is not None else 0
        if salary_out > (salary_in + 1000000):
            loan_candidates = bidding_club_squad[bidding_club_squad['AGE'] <= 24]
            if loan_candidates.empty: loan_candidates = bidding_club_squad
            loan_player = loan_candidates.sample(1).iloc[0]
            loan_name = loan_player.get('NAME', 'N/A'); loan_salary = loan_player.get('Salary', 0)
            print(f"\nTo help with wages, they also offer to send {loan_name} (Salary: {loan_salary:,.0f}) to you on a fully paid loan!")
            return {'cash': current_cash, 'player_swap': swap_player, 'loan': loan_player}
    
    print(f"\nThey have improved their cash offer!") # Fallback
    return {'cash': new_total_value, 'player_swap': None, 'loan': None}

def run_sell_player(routine1_output_path, id_col_csv, club_team_col_csv):
    print(f"Starting Player Seller using: {routine1_output_path}")
    if not os.path.exists(routine1_output_path): print(f"Error: Input file '{routine1_output_path}' not found. Run R1 first."); return
    df = load_csv_for_utility(routine1_output_path)
    if df is None or df.empty: print("Failed to load data for Player Seller."); return
    df.columns = [' '.join(str(c).split()) for c in df.columns]
    id_col_cleaned = ' '.join(id_col_csv.split()); club_team_col_cleaned = ' '.join(club_team_col_csv.split())
    if id_col_cleaned not in df.columns or club_team_col_cleaned not in df.columns: print(f"Error: Essential columns missing."); return
    df[id_col_cleaned] = df[id_col_cleaned].astype(str)
    
    top_clubs = ['A.C. Milan', 'Ajax', 'Arsenal', 'CSKA Moskva', 'F.C. Barcelona', 'Inter', 'Juventus', 'Manchester City', 'Manchester United', 'Newcastle United', 'PSV Eindhoven', 'SBV Excelsior', 'Udinese', 'West Ham United', 'Valencia C.F.', 'Olympique Lyonnais']
    all_clubs = df[club_team_col_cleaned].dropna().unique().tolist()
    other_clubs = [club for club in all_clubs if club not in top_clubs and club != 'No Club']
    if not other_clubs: print("Error: No 'other' clubs available to make offers."); return

    while True:
        player_to_sell_id = input("\nWhich player do you want to sell? (Enter player ID, or 'back'): ").strip()
        if player_to_sell_id.lower() == 'back': break
        player_to_sell_series = df[df[id_col_cleaned] == player_to_sell_id]
        if player_to_sell_series.empty: print(f"Error: Player with ID '{player_to_sell_id}' not found."); continue
        player_to_sell = player_to_sell_series.iloc[0]
        player_name = player_to_sell.get('NAME', 'N/A'); player_mv = player_to_sell.get('Market Value', 0)
        print(f"\nPutting {player_name} (MV: {player_mv:,.0f}) on the market...")
        time.sleep(1)

        new_club_interest_prob = 1.0; bidding_clubs_tried = []; deal_done = False
        
        while True: 
            if random.random() > new_club_interest_prob and len(bidding_clubs_tried) > 0:
                print("\nNo other clubs have shown interest at this time."); break
            
            available_bidders = [c for c in other_clubs if c not in bidding_clubs_tried]
            if not available_bidders: print("\nNo more clubs available to make an offer."); break
            
            bidding_club_name = random.choice(available_bidders); bidding_clubs_tried.append(bidding_club_name)
            bidding_club_squad = df[df[club_team_col_cleaned] == bidding_club_name]
            negotiation_prob = 0.75
            current_offer = generate_initial_offer(player_to_sell, bidding_club_squad)
            print(f"\n... News coming in ...\n{bidding_club_name} is interested in {player_name}.")

            while True:
                cash_val = current_offer.get('cash', 0); swap_player = current_offer.get('player_swap'); loan_player = current_offer.get('loan')
                swap_player_mv = swap_player.get('Market Value', 0) if swap_player is not None else 0
                total_value = cash_val + swap_player_mv
                print("\n" + "="*40); print(f"Negotiating with: {bidding_club_name}")
                print(f"CURRENT OFFER (Total Value: {total_value:,.0f}):")
                print(f"  Cash: {cash_val:,.0f}")
                if swap_player is not None: print(f"  + Player: {swap_player['NAME']} (MV: {swap_player_mv:,.0f})")
                if loan_player is not None: print(f"  + Player on Loan: {loan_player['NAME']}")
                print("="*40)
                
                action = input("Your decision? (1: Accept, 2: Negotiate, 3: Reject & Walk Away): ").strip()
                if action == '1': print(f"\n✅ DEAL! {player_name} sold to {bidding_club_name}."); deal_done = True; break
                elif action == '2':
                    if random.random() < negotiation_prob:
                        print("...Their representative is considering a new proposal..."); time.sleep(1.5)
                        current_offer = generate_counter_offer(current_offer, player_to_sell, bidding_club_squad)
                        negotiation_prob -= random.uniform(0.05, 0.15)
                    else: print("\nThey've walked away from negotiations!"); break
                elif action == '3': print("You have walked away."); break
                else: print("Invalid choice.")
            
            if deal_done: break 
            new_club_interest_prob *= (1 - random.uniform(0.15, 0.25))
            if new_club_interest_prob > 0.01 : print(f"Probability of new club interest is now: {new_club_interest_prob:.0%}")

# --- NEW Routine 9: Buy a Player from CPU ---
def generate_cpu_counter_proposal(current_deal, buying_user_squad):
    """Generates a CPU counter-offer, which is a lower total demand, possibly with a player request."""
    current_cash_demand = current_deal.get('cash_paid', 0)
    player_demand = current_deal.get('player_given')
    player_demand_mv = player_demand.get('Market Value', 0) if player_demand is not None else 0
    current_total_demand_value = current_cash_demand + player_demand_mv
    
    # CPU makes a concession, reducing its total demand value by 5-15%
    new_total_demand_value = current_total_demand_value * (1 - random.uniform(0.05, 0.15))
    
    # High chance CPU just lowers the cash price
    if random.random() < 0.7 or buying_user_squad.empty:
        print("\nThey've considered your position and are willing to lower the cash price.")
        return {'cash_paid': new_total_demand_value, 'player_given': None}
    
    # Lesser chance the CPU asks for one of your players to reduce the cash part
    else:
        # CPU looks for a player from your squad with a value less than the new total demand
        suitable_players = buying_user_squad[buying_user_squad['Market Value'] < new_total_demand_value]
        if not suitable_players.empty:
            player_request = suitable_players.sample(1).iloc[0]
            player_request_name = player_request.get('NAME', 'N/A')
            player_request_mv = player_request.get('Market Value', 0)
            new_cash_demand = max(0, new_total_demand_value - player_request_mv)
            print(f"\nThey have a new proposal. They will lower the price if you include {player_request_name} (MV: {player_request_mv:,.0f}) in the deal!")
            return {'cash_paid': new_cash_demand, 'player_given': player_request}

    # Fallback to simple cash reduction
    print("\nThey have considered your position and are willing to lower the cash price.")
    return {'cash_paid': new_total_demand_value, 'player_given': None}

def run_buy_player(routine1_output_path, id_col_csv, club_team_col_csv):
    print(f"Starting 'Buy a Player' module using: {routine1_output_path}")
    if not os.path.exists(routine1_output_path): print(f"Error: Input file '{routine1_output_path}' not found. Run R1 first."); return
    df = load_csv_for_utility(routine1_output_path)
    if df is None or df.empty: print("Failed to load data for 'Buy a Player'."); return
    
    df.columns = [' '.join(str(c).split()) for c in df.columns]
    id_col_cleaned = ' '.join(id_col_csv.split()); club_team_col_cleaned = ' '.join(club_team_col_csv.split())
    if id_col_cleaned not in df.columns or club_team_col_cleaned not in df.columns: print(f"Error: Essential columns missing."); return
    df[id_col_cleaned] = df[id_col_cleaned].astype(str)

    while True:
        target_player_id = input("\nWhich player do you want to buy? (Enter player ID, or 'back'): ").strip()
        if target_player_id.lower() == 'back': break

        target_player_series = df[df[id_col_cleaned] == target_player_id]
        if target_player_series.empty: print(f"Error: Player with ID '{target_player_id}' not found."); continue
        
        target_player = target_player_series.iloc[0]
        target_name = target_player.get('NAME', 'N/A'); target_mv = target_player.get('Market Value', 0)
        selling_club = target_player.get(club_team_col_cleaned, 'N/A')
        
        print("\nWhich user is buying?")
        for key, user_info in USER_TEAMS.items(): print(f"{key}: {user_info['name']} (Manages: {', '.join(user_info['teams'])})")
        
        buyer_choice = input(f"Select the number of the buying user (1-{len(USER_TEAMS)}): ").strip()
        if buyer_choice not in USER_TEAMS: print("Invalid user choice."); continue
        
        buying_user = USER_TEAMS[buyer_choice]
        if selling_club in buying_user['teams']: print(f"Error: You cannot buy a player from one of your own teams ({selling_club})."); continue
        if selling_club == 'No Club': print(f"Error: You can sign free agents, not 'buy' them. This module is for transfers between clubs."); continue

        print(f"\n{buying_user['name']} is attempting to buy {target_name} from {selling_club}...")
        buying_user_squad = df[df[club_team_col_cleaned].isin(buying_user['teams'])]
        
        initial_asking_price = target_mv * random.uniform(1.25, 1.75)
        current_deal = {'cash_paid': initial_asking_price, 'player_given': None}
        negotiation_prob = 0.75
        deal_done = False

        while True:
            cash_demand = current_deal.get('cash_paid', 0); player_demand = current_deal.get('player_given')
            print("\n" + "="*40); print(f"Negotiating for: {target_name} (MV: {target_mv:,.0f})")
            print(f"Selling club ({selling_club}) is demanding:")
            print(f"  Cash Payment: {cash_demand:,.0f}")
            if player_demand is not None:
                player_demand_name = player_demand.get('NAME', 'N/A'); player_demand_mv = player_demand.get('Market Value', 0)
                print(f"  + Your Player: {player_demand_name} (MV: {player_demand_mv:,.0f})")
            print("="*40)

            action = input("Your decision? (1: Accept Demands, 2: Negotiate for a better deal, 3: Walk Away): ").strip()
            if action == '1': print(f"\n✅ DEAL! {target_name} will join {buying_user['name']}'s club."); deal_done = True; break
            elif action == '2':
                if random.random() < negotiation_prob:
                    print("...Their Director of Football is considering your request..."); time.sleep(1.5)
                    current_deal = generate_cpu_counter_proposal(current_deal, buying_user_squad)
                    negotiation_prob -= random.uniform(0.05, 0.15)
                else: print("\nThey are firm on their price and have ended negotiations!"); break
            elif action == '3': print("You have walked away from the negotiation."); break
            else: print("Invalid choice.")
        
        if deal_done: break


# --- Main Menu & Execution ---
def display_menu():
    print("\n--- PES Data Management Tool ---")
    print("1. Run New Salary and Value Calculator")
    print("2. Run End of the Year Player Age Updator")
    print("3. Run Player Reaper (Retirement)")
    print("4. Create SQL Database from CSV")
    print("5. Export SQL data to CSV")
    print("6. Find Player Replacement (Standard)")
    print("7. Find Player Replacement (Targeted Clubs)")
    print("8. Sell a Player (Negotiation)")
    print("9. Buy a Player from CPU")
    print("10. Exit")
    choice = input("Enter your choice (1-10): ")
    return choice

if __name__ == "__main__":
    id_col_name_in_csv = 'ID'                 
    club_team_col_name_in_csv = 'CLUB TEAM'   
    age_col_name_in_csv = 'AGE'           
    main_input_csv = '/home/anibalgalindro/Downloads/testfile.csv' 

    db_info = {"name": "PES6data.db", "table": "player_data", "map_file": "PES6data_column_map.json"}

    while True:
        user_choice = display_menu()
        if user_choice == '1':
            print("\n>>> Routine 1: Salary and Value Calculator")
            run_salary_and_value_calculator(main_input_csv, id_col_csv=id_col_name_in_csv, club_team_col_csv=club_team_col_name_in_csv, db_info=db_info)
        elif user_choice == '2':
            print("\n>>> Routine 2: Age Updator")
            run_age_updater(main_input_csv, 'output_aged_players.csv', age_col_name=age_col_name_in_csv, db_info=db_info, id_col_csv=id_col_name_in_csv)
        elif user_choice == '3':
            print("\n>>> Routine 3: Player Reaper")
            run_player_reaper(main_input_csv, 'output_surviving_players.csv', age_col_name=age_col_name_in_csv, db_info=db_info, id_col_csv=id_col_name_in_csv)
        elif user_choice == '4':
            print("\n>>> Routine 4: Create SQL Database")
            run_create_sql_database(main_input_csv, db_name=db_info['name'], table_name=db_info['table'], column_map_file=db_info['map_file'], id_col_csv_original=id_col_name_in_csv)
        elif user_choice == '5':
            print("\n>>> Routine 5: Export SQL data to CSV")
            run_export_sql_to_csv(db_name=db_info['name'], table_name=db_info['table'], output_csv_path='output_from_sql.csv', column_map_file=db_info['map_file'])
        elif user_choice == '6':
             print("\n>>> Routine 6: Find Player Replacement (Standard)")
             routine1_output_file = 'routine1_players_financials.csv'
             cleaned_id = ' '.join(id_col_name_in_csv.split()); cleaned_club = ' '.join(club_team_col_name_in_csv.split())
             non_skills = ['NAME', 'REGISTERED POSITION', 'HEIGHT', 'AGE', cleaned_id, cleaned_club]
             run_find_replacement(routine1_output_file, id_col_csv=id_col_name_in_csv, club_team_col_csv=club_team_col_name_in_csv, non_skill_cols_info=non_skills)
        elif user_choice == '7':
            print("\n>>> Routine 7: Find Player Replacement (Targeted Clubs)")
            routine1_output_file = 'routine1_players_financials.csv'
            cleaned_id = ' '.join(id_col_name_in_csv.split()); cleaned_club = ' '.join(club_team_col_name_in_csv.split())
            non_skills = ['NAME', 'REGISTERED POSITION', 'HEIGHT', 'AGE', cleaned_id, cleaned_club]
            run_targeted_replacement_finder(routine1_output_file, id_col_csv=id_col_name_in_csv, club_team_col_csv=club_team_col_name_in_csv, non_skill_cols_info=non_skills)
        elif user_choice == '8':
            print("\n>>> Routine 8: Sell a Player (Negotiation)")
            routine1_output_file = 'routine1_players_financials.csv'
            run_sell_player(routine1_output_file, id_col_csv=id_col_name_in_csv, club_team_col_csv=club_team_col_name_in_csv)
        elif user_choice == '9':
            print("\n>>> Routine 9: Buy a Player from CPU")
            routine1_output_file = 'routine1_players_financials.csv'
            run_buy_player(routine1_output_file, id_col_csv=id_col_name_in_csv, club_team_col_csv=club_team_col_name_in_csv)
        elif user_choice == '10':
            print("Exiting program. Goodbye!"); break
        else:
            print("Invalid choice.")
        print("-" * 40)