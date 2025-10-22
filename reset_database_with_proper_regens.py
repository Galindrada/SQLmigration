#!/usr/bin/env python3
"""
Complete database reset and regeneration system for PES6 League.
This script completely resets the database and creates a proper regeneration system.
"""

import sqlite3
import pandas as pd
import random
import os
import shutil
from datetime import datetime

# Configuration
DB_PATH = 'pes6_league_db.sqlite'
BACKUP_PATH = f'pes6_league_db_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.sqlite'

def create_backup():
    """Create a backup of the current database."""
    if os.path.exists(DB_PATH):
        shutil.copy2(DB_PATH, BACKUP_PATH)
        print(f"✅ Backup created: {BACKUP_PATH}")
    else:
        print("⚠️  No existing database to backup")

def reset_database():
    """Completely reset the database."""
    print("🔄 Resetting database...")
    
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print("✅ Old database removed")
    
    # Create new database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create tables with proper schema
    cursor.executescript("""
        -- Users table
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Teams table
        CREATE TABLE teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            club_name TEXT UNIQUE NOT NULL,
            total_salaries INTEGER DEFAULT 0,
            budget INTEGER DEFAULT 400000000,
            available_cap INTEGER DEFAULT 400000000
        );
        
        -- League teams table
        CREATE TABLE league_teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_name TEXT NOT NULL,
            user_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        
        -- Players table with all required fields
        CREATE TABLE players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_name TEXT NOT NULL,
            shirt_name TEXT,
            age INTEGER NOT NULL,
            nationality TEXT NOT NULL,
            skin_color INTEGER NOT NULL CHECK (skin_color >= 1 AND skin_color <= 4),
            strong_foot TEXT,
            favoured_side TEXT,
            registered_position TEXT NOT NULL,
            game_position TEXT,
            club_id INTEGER,
            salary INTEGER DEFAULT 0,
            contract_years_remaining INTEGER DEFAULT 0,
            market_value INTEGER DEFAULT 0,
            yearly_wage_rise REAL DEFAULT 0.0,
            development_key INTEGER DEFAULT 0,
            trait_key INTEGER DEFAULT 0,
            games_played INTEGER DEFAULT 0,
            goals INTEGER DEFAULT 0,
            assists INTEGER DEFAULT 0,
            
            -- Physical attributes
            height INTEGER,
            weight INTEGER,
            
            -- All skill attributes with proper constraints
            attack INTEGER DEFAULT 50 CHECK (attack >= 0 AND attack <= 99),
            defense INTEGER DEFAULT 50 CHECK (defense >= 0 AND defense <= 99),
            balance INTEGER DEFAULT 50 CHECK (balance >= 0 AND balance <= 99),
            stamina INTEGER DEFAULT 50 CHECK (stamina >= 0 AND stamina <= 99),
            top_speed INTEGER DEFAULT 50 CHECK (top_speed >= 0 AND top_speed <= 99),
            acceleration INTEGER DEFAULT 50 CHECK (acceleration >= 0 AND acceleration <= 99),
            response INTEGER DEFAULT 50 CHECK (response >= 0 AND response <= 99),
            agility INTEGER DEFAULT 50 CHECK (agility >= 0 AND agility <= 99),
            dribble_accuracy INTEGER DEFAULT 50 CHECK (dribble_accuracy >= 0 AND dribble_accuracy <= 99),
            dribble_speed INTEGER DEFAULT 50 CHECK (dribble_speed >= 0 AND dribble_speed <= 99),
            short_pass_accuracy INTEGER DEFAULT 50 CHECK (short_pass_accuracy >= 0 AND short_pass_accuracy <= 99),
            short_pass_speed INTEGER DEFAULT 50 CHECK (short_pass_speed >= 0 AND short_pass_speed <= 99),
            long_pass_accuracy INTEGER DEFAULT 50 CHECK (long_pass_accuracy >= 0 AND long_pass_accuracy <= 99),
            long_pass_speed INTEGER DEFAULT 50 CHECK (long_pass_speed >= 0 AND long_pass_speed <= 99),
            shot_accuracy INTEGER DEFAULT 50 CHECK (shot_accuracy >= 0 AND shot_accuracy <= 99),
            shot_power INTEGER DEFAULT 50 CHECK (shot_power >= 0 AND shot_power <= 99),
            shot_technique INTEGER DEFAULT 50 CHECK (shot_technique >= 0 AND shot_technique <= 99),
            free_kick_accuracy INTEGER DEFAULT 50 CHECK (free_kick_accuracy >= 0 AND free_kick_accuracy <= 99),
            swerve INTEGER DEFAULT 50 CHECK (swerve >= 0 AND swerve <= 99),
            heading INTEGER DEFAULT 50 CHECK (heading >= 0 AND heading <= 99),
            jump INTEGER DEFAULT 50 CHECK (jump >= 0 AND jump <= 99),
            technique INTEGER DEFAULT 50 CHECK (technique >= 0 AND technique <= 99),
            aggression INTEGER DEFAULT 50 CHECK (aggression >= 0 AND aggression <= 99),
            mentality INTEGER DEFAULT 50 CHECK (mentality >= 0 AND mentality <= 99),
            goal_keeping INTEGER DEFAULT 50 CHECK (goal_keeping >= 0 AND goal_keeping <= 99),
            team_work INTEGER DEFAULT 50 CHECK (team_work >= 0 AND team_work <= 99),
            consistency INTEGER DEFAULT 50 CHECK (consistency >= 0 AND consistency <= 99),
            condition_fitness INTEGER DEFAULT 50 CHECK (condition_fitness >= 0 AND condition_fitness <= 99),
            
            -- Positional ratings (binary: 0 = cannot play, 1 = can play)
            gk INTEGER DEFAULT 0 CHECK (gk IN (0, 1)),
            cwp INTEGER DEFAULT 0 CHECK (cwp IN (0, 1)),
            cbt INTEGER DEFAULT 0 CHECK (cbt IN (0, 1)),
            sb INTEGER DEFAULT 0 CHECK (sb IN (0, 1)),
            dmf INTEGER DEFAULT 0 CHECK (dmf IN (0, 1)),
            wb INTEGER DEFAULT 0 CHECK (wb IN (0, 1)),
            cmf INTEGER DEFAULT 0 CHECK (cmf IN (0, 1)),
            smf INTEGER DEFAULT 0 CHECK (smf IN (0, 1)),
            amf INTEGER DEFAULT 0 CHECK (amf IN (0, 1)),
            wf INTEGER DEFAULT 0 CHECK (wf IN (0, 1)),
            ss INTEGER DEFAULT 0 CHECK (ss IN (0, 1)),
            cf INTEGER DEFAULT 0 CHECK (cf IN (0, 1)),
            
            -- Special skills (binary 0/1)
            dribbling_skill INTEGER DEFAULT 0 CHECK (dribbling_skill IN (0, 1)),
            tactical_dribble INTEGER DEFAULT 0 CHECK (tactical_dribble IN (0, 1)),
            positioning INTEGER DEFAULT 0 CHECK (positioning IN (0, 1)),
            reaction INTEGER DEFAULT 0 CHECK (reaction IN (0, 1)),
            playmaking INTEGER DEFAULT 0 CHECK (playmaking IN (0, 1)),
            passing INTEGER DEFAULT 0 CHECK (passing IN (0, 1)),
            scoring INTEGER DEFAULT 0 CHECK (scoring IN (0, 1)),
            one_one_scoring INTEGER DEFAULT 0 CHECK (one_one_scoring IN (0, 1)),
            post_player INTEGER DEFAULT 0 CHECK (post_player IN (0, 1)),
            lines INTEGER DEFAULT 0 CHECK (lines IN (0, 1)),
            middle_shooting INTEGER DEFAULT 0 CHECK (middle_shooting IN (0, 1)),
            side INTEGER DEFAULT 0 CHECK (side IN (0, 1)),
            centre INTEGER DEFAULT 0 CHECK (centre IN (0, 1)),
            penalties INTEGER DEFAULT 0 CHECK (penalties IN (0, 1)),
            one_touch_pass INTEGER DEFAULT 0 CHECK (one_touch_pass IN (0, 1)),
            outside INTEGER DEFAULT 0 CHECK (outside IN (0, 1)),
            marking INTEGER DEFAULT 0 CHECK (marking IN (0, 1)),
            sliding INTEGER DEFAULT 0 CHECK (sliding IN (0, 1)),
            covering INTEGER DEFAULT 0 CHECK (covering IN (0, 1)),
            d_line_control INTEGER DEFAULT 0 CHECK (d_line_control IN (0, 1)),
            penalty_stopper INTEGER DEFAULT 0 CHECK (penalty_stopper IN (0, 1)),
            one_on_one_stopper INTEGER DEFAULT 0 CHECK (one_on_one_stopper IN (0, 1)),
            long_throw INTEGER DEFAULT 0 CHECK (long_throw IN (0, 1)),
            
            -- Additional attributes from CSV
            injury_tolerance TEXT,
            dribble_style TEXT,
            free_kick_style TEXT,
            pk_style TEXT,
            drop_kick_style TEXT,
            face_type INTEGER,
            preset_face_number INTEGER,
            head_width INTEGER,
            neck_length INTEGER,
            neck_width INTEGER,
            shoulder_height INTEGER,
            shoulder_width INTEGER,
            chest_measurement INTEGER,
            waist_circumference INTEGER,
            arm_circumference INTEGER,
            leg_circumference INTEGER,
            calf_circumference INTEGER,
            leg_length INTEGER,
            wristband INTEGER,
            wristband_color INTEGER,
            international_number INTEGER,
            classic_number INTEGER,
            club_number INTEGER,
            
            -- Calculated ratings
            attack_rating INTEGER DEFAULT 50,
            defense_rating INTEGER DEFAULT 50,
            physical_rating INTEGER DEFAULT 50,
            power_rating INTEGER DEFAULT 50,
            technique_rating INTEGER DEFAULT 50,
            goalkeeping_rating INTEGER DEFAULT 50,
            
            FOREIGN KEY (club_id) REFERENCES teams (id)
        );
        
        -- Posts table
        CREATE TABLE posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            media_type TEXT,
            media_path TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        
        -- User movements table
        CREATE TABLE user_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            amount INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        
        -- Offers table
        CREATE TABLE offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            offered_players TEXT,
            offered_money INTEGER DEFAULT 0,
            requested_players TEXT,
            requested_money INTEGER DEFAULT 0,
            sender_team_id INTEGER,
            receiver_team_id INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    conn.commit()
    conn.close()
    print("✅ New database created with proper schema")

def generate_proper_regen(retired_player_data, db_path):
    """Generate a proper regen based on the retiring player."""
    
    # Nationality data with proper skin color mapping
    NATIONALITY_DATA = {
        'Brazil': {'skin_color': 2, 'weight': 0.15, 'names': ['João', 'Pedro', 'Lucas', 'Gabriel', 'Matheus', 'Rafael', 'Bruno', 'Carlos', 'André', 'Felipe']},
        'Argentina': {'skin_color': 1, 'weight': 0.12, 'names': ['Santiago', 'Mateo', 'Benjamín', 'Lucas', 'Nicolás', 'Alejandro', 'Diego', 'Martín', 'Javier', 'Gonzalo']},
        'Spain': {'skin_color': 1, 'weight': 0.10, 'names': ['Carlos', 'Miguel', 'Javier', 'Antonio', 'David', 'Daniel', 'Francisco', 'José', 'Manuel', 'Luis']},
        'France': {'skin_color': 1, 'weight': 0.09, 'names': ['Thomas', 'Pierre', 'Nicolas', 'Alexandre', 'Maxime', 'Antoine', 'Raphaël', 'Vincent', 'Julien', 'Baptiste']},
        'England': {'skin_color': 1, 'weight': 0.08, 'names': ['James', 'William', 'Oliver', 'Harry', 'Jack', 'Noah', 'Charlie', 'Oscar', 'George', 'Ethan']},
        'Germany': {'skin_color': 1, 'weight': 0.08, 'names': ['Maximilian', 'Alexander', 'Felix', 'Leon', 'Paul', 'Jonas', 'Julian', 'Niklas', 'Tim', 'Lukas']},
        'Italy': {'skin_color': 1, 'weight': 0.07, 'names': ['Marco', 'Alessandro', 'Matteo', 'Luca', 'Andrea', 'Giuseppe', 'Roberto', 'Antonio', 'Giovanni', 'Francesco']},
        'Portugal': {'skin_color': 1, 'weight': 0.06, 'names': ['João', 'Miguel', 'Diogo', 'Tiago', 'André', 'Pedro', 'Ricardo', 'Nuno', 'Rui', 'Carlos']},
        'Netherlands': {'skin_color': 1, 'weight': 0.05, 'names': ['Daan', 'Sem', 'Lucas', 'Milan', 'Levi', 'Finn', 'Jesse', 'Luuk', 'Bram', 'Thijs']},
        'Belgium': {'skin_color': 1, 'weight': 0.04, 'names': ['Lucas', 'Louis', 'Arthur', 'Victor', 'Adam', 'Nathan', 'Thomas', 'Maxime', 'Antoine', 'Raphaël']},
        'Croatia': {'skin_color': 1, 'weight': 0.04, 'names': ['Ivan', 'Marko', 'Luka', 'Petar', 'Ante', 'Josip', 'Matej', 'Filip', 'Domagoj', 'Borna']},
        'Serbia': {'skin_color': 1, 'weight': 0.03, 'names': ['Stefan', 'Nikola', 'Marko', 'Aleksandar', 'Milan', 'Petar', 'Dragan', 'Bojan', 'Dejan', 'Nemanja']},
        'Poland': {'skin_color': 1, 'weight': 0.03, 'names': ['Jakub', 'Kacper', 'Filip', 'Szymon', 'Michał', 'Jan', 'Piotr', 'Tomasz', 'Marek', 'Adam']},
        'Ukraine': {'skin_color': 1, 'weight': 0.03, 'names': ['Oleksandr', 'Andriy', 'Mykhailo', 'Vitaliy', 'Serhiy', 'Ihor', 'Vasyl', 'Roman', 'Yuriy', 'Dmytro']},
        'Russia': {'skin_color': 1, 'weight': 0.03, 'names': ['Alexander', 'Dmitri', 'Sergei', 'Andrei', 'Vladimir', 'Igor', 'Nikolai', 'Mikhail', 'Aleksei', 'Denis']},
        'Turkey': {'skin_color': 2, 'weight': 0.03, 'names': ['Mehmet', 'Mustafa', 'Ahmet', 'Ali', 'Hasan', 'Hüseyin', 'İbrahim', 'Murat', 'Ömer', 'Yusuf']},
        'Morocco': {'skin_color': 2, 'weight': 0.02, 'names': ['Youssef', 'Ahmad', 'Karim', 'Hassan', 'Omar', 'Khalid', 'Rachid', 'Nabil', 'Samir', 'Tariq']},
        'Algeria': {'skin_color': 2, 'weight': 0.02, 'names': ['Karim', 'Yacine', 'Sofiane', 'Riyad', 'Islam', 'Adel', 'Samir', 'Nabil', 'Hakim', 'Farid']},
        'Senegal': {'skin_color': 4, 'weight': 0.02, 'names': ['Mamadou', 'Ibrahima', 'Ousmane', 'Sadio', 'Kalidou', 'Cheikhou', 'Idrissa', 'Moussa', 'Pape', 'Youssouf']},
        'Nigeria': {'skin_color': 4, 'weight': 0.02, 'names': ['Victor', 'Kelechi', 'Alex', 'Wilfred', 'Oghenekaro', 'John', 'Ahmed', 'Emmanuel', 'Odion', 'Moses']},
        'Ghana': {'skin_color': 4, 'weight': 0.02, 'names': ['André', 'Thomas', 'Jordan', 'Daniel', 'Christian', 'Jeffrey', 'Mubarak', 'Emmanuel', 'Kwadwo', 'Asamoah']},
        'Ivory Coast': {'skin_color': 4, 'weight': 0.02, 'names': ['Yaya', 'Wilfried', 'Serge', 'Salomon', 'Didier', 'Kolo', 'Emmanuel', 'Gervinho', 'Cheick', 'Seydou']},
        'Cameroon': {'skin_color': 4, 'weight': 0.02, 'names': ['Samuel', 'Joel', 'Vincent', 'Eric', 'Pierre', 'Achille', 'Benjamin', 'Georges', 'Roger', 'Patrick']},
        'Egypt': {'skin_color': 2, 'weight': 0.02, 'names': ['Mohamed', 'Ahmed', 'Mahmoud', 'Omar', 'Karim', 'Amr', 'Hossam', 'Tarek', 'Wael', 'Hassan']},
        'Tunisia': {'skin_color': 2, 'weight': 0.01, 'names': ['Youssef', 'Wahbi', 'Hamza', 'Ferjani', 'Aymen', 'Naim', 'Saber', 'Karim', 'Oussama', 'Anis']},
        'South Africa': {'skin_color': 4, 'weight': 0.01, 'names': ['Percy', 'Steven', 'Dean', 'Bongani', 'Siyabonga', 'Thulani', 'Kagisho', 'Teko', 'Siphiwe', 'Katlego']},
        'Japan': {'skin_color': 3, 'weight': 0.02, 'names': ['Keisuke', 'Shinji', 'Yuto', 'Maya', 'Hiroshi', 'Takashi', 'Yasuhito', 'Makoto', 'Yoshinori', 'Eiji']},
        'South Korea': {'skin_color': 3, 'weight': 0.02, 'names': ['Son', 'Ki', 'Park', 'Lee', 'Kim', 'Jung', 'Choi', 'Kwon', 'Yoon', 'Han']},
        'China': {'skin_color': 3, 'weight': 0.01, 'names': ['Wu', 'Zhang', 'Li', 'Wang', 'Chen', 'Liu', 'Yang', 'Huang', 'Zhao', 'Zhou']},
        'Australia': {'skin_color': 1, 'weight': 0.01, 'names': ['Tim', 'Mathew', 'Mark', 'Joshua', 'Aaron', 'Mile', 'Tom', 'Jackson', 'Adam', 'Ryan']},
        'USA': {'skin_color': 1, 'weight': 0.03, 'names': ['Christian', 'Michael', 'Clint', 'Jozy', 'Brad', 'Tim', 'Geoff', 'Alejandro', 'Graham', 'Bobby']},
        'Mexico': {'skin_color': 2, 'weight': 0.02, 'names': ['Javier', 'Carlos', 'Andrés', 'Guillermo', 'Rafael', 'Jorge', 'Luis', 'Miguel', 'Diego', 'Eduardo']},
        'Colombia': {'skin_color': 2, 'weight': 0.02, 'names': ['James', 'Radamel', 'Juan', 'Carlos', 'David', 'Abel', 'Jackson', 'Luis', 'Fredy', 'Teófilo']},
        'Chile': {'skin_color': 2, 'weight': 0.01, 'names': ['Arturo', 'Alexis', 'Eduardo', 'Gary', 'Claudio', 'Jorge', 'Mauricio', 'Matías', 'Charles', 'Felipe']},
        'Uruguay': {'skin_color': 1, 'weight': 0.01, 'names': ['Luis', 'Edinson', 'Diego', 'Maxi', 'Álvaro', 'Sebastián', 'Cristian', 'Walter', 'Egidio', 'Nicolás']},
        'Paraguay': {'skin_color': 2, 'weight': 0.01, 'names': ['Roque', 'Nelson', 'Oscar', 'Cristian', 'Edgar', 'Julio', 'Dario', 'Lucas', 'Antonio', 'Carlos']},
        'Peru': {'skin_color': 2, 'weight': 0.01, 'names': ['Paolo', 'Jefferson', 'André', 'Christian', 'Yoshimar', 'Renato', 'Luis', 'Carlos', 'Miguel', 'Raúl']},
        'Ecuador': {'skin_color': 2, 'weight': 0.01, 'names': ['Antonio', 'Enner', 'Felipe', 'Michael', 'Christian', 'Renato', 'Carlos', 'Luis', 'Gabriel', 'Walter']},
        'Venezuela': {'skin_color': 2, 'weight': 0.01, 'names': ['Salomón', 'Tomás', 'Rómulo', 'Alejandro', 'Luis', 'Fernando', 'Carlos', 'Roberto', 'José', 'Manuel']},
        'Canada': {'skin_color': 1, 'weight': 0.01, 'names': ['Alphonso', 'Jonathan', 'Atiba', 'Scott', 'Samuel', 'Cyle', 'Mark', 'Tosaint', 'Russell', 'Will']}
    }
    
    # Surname data
    SURNAME_DATA = {
        'Brazil': ['Silva', 'Santos', 'Oliveira', 'Souza', 'Rodrigues', 'Ferreira', 'Alves', 'Pereira', 'Lima', 'Gomes'],
        'Argentina': ['González', 'Rodríguez', 'Gómez', 'Fernández', 'López', 'Díaz', 'Martínez', 'Pérez', 'García', 'Sánchez'],
        'Spain': ['García', 'Rodríguez', 'González', 'Fernández', 'López', 'Martínez', 'Sánchez', 'Pérez', 'Gómez', 'Martín'],
        'France': ['Martin', 'Bernard', 'Dubois', 'Thomas', 'Robert', 'Richard', 'Petit', 'Durand', 'Leroy', 'Moreau'],
        'England': ['Smith', 'Jones', 'Williams', 'Brown', 'Taylor', 'Davies', 'Wilson', 'Evans', 'Thomas', 'Roberts'],
        'Germany': ['Müller', 'Schmidt', 'Schneider', 'Fischer', 'Weber', 'Meyer', 'Wagner', 'Becker', 'Schulz', 'Hoffmann'],
        'Italy': ['Rossi', 'Ferrari', 'Russo', 'Bianchi', 'Romano', 'Colombo', 'Ricci', 'Marino', 'Greco', 'Bruno'],
        'Portugal': ['Silva', 'Santos', 'Ferreira', 'Pereira', 'Oliveira', 'Costa', 'Rodrigues', 'Martins', 'Jesus', 'Sousa'],
        'Netherlands': ['de Jong', 'Jansen', 'de Vries', 'van den Berg', 'van Dijk', 'Bakker', 'Visser', 'Smit', 'Meijer', 'de Boer'],
        'Belgium': ['Peeters', 'Janssens', 'Maes', 'Jacobs', 'Mertens', 'Willems', 'Claes', 'Goossens', 'Wouters', 'De Smet'],
        'Croatia': ['Horvat', 'Kovačević', 'Novak', 'Knežević', 'Kovačić', 'Babić', 'Marić', 'Petrović', 'Vuković', 'Radić'],
        'Serbia': ['Jovanović', 'Petrović', 'Nikolić', 'Marković', 'Đorđević', 'Stojanović', 'Ilić', 'Stanković', 'Pavlović', 'Milošević'],
        'Poland': ['Nowak', 'Kowalski', 'Wiśniewski', 'Wójcik', 'Kowalczyk', 'Kamiński', 'Lewandowski', 'Zieliński', 'Szymański', 'Woźniak'],
        'Ukraine': ['Melnyk', 'Shevchenko', 'Bondarenko', 'Kovalenko', 'Tkachenko', 'Kravchenko', 'Kovalchuk', 'Oliynyk', 'Shevchuk', 'Polishchuk'],
        'Russia': ['Ivanov', 'Smirnov', 'Kuznetsov', 'Popov', 'Vasiliev', 'Petrov', 'Sokolov', 'Mikhailov', 'Novikov', 'Fedorov'],
        'Turkey': ['Yılmaz', 'Kaya', 'Demir', 'Çelik', 'Şahin', 'Yıldız', 'Yıldırım', 'Özdemir', 'Arslan', 'Doğan'],
        'Morocco': ['Benjelloun', 'Alaoui', 'Tazi', 'Bennani', 'Berrada', 'Chraibi', 'Fassi', 'Gharbi', 'Hassani', 'Idrissi'],
        'Algeria': ['Bouazza', 'Boumediene', 'Bouhani', 'Boukhari', 'Boukhobza', 'Boukhriss', 'Boumaaza', 'Boumediene', 'Bouras'],
        'Senegal': ['Diop', 'Diallo', 'Fall', 'Ndiaye', 'Ba', 'Sow', 'Thiam', 'Cissé', 'Gueye', 'Diagne'],
        'Nigeria': ['Okechukwu', 'Onyekachi', 'Onyekwelu', 'Onyemachi', 'Onyemaechi', 'Onyenachi', 'Onyenacho', 'Onyenachi', 'Onyenachi'],
        'Ghana': ['Mensah', 'Owusu', 'Addo', 'Asante', 'Boateng', 'Darko', 'Essien', 'Gyan', 'Muntari', 'Paintsil'],
        'Ivory Coast': ['Koné', 'Traoré', 'Ouattara', 'Bamba', 'Coulibaly', 'Diabaté', 'Drogba', 'Kalou', 'Tiéné', 'Zokora'],
        'Cameroon': ['Eto\'o', 'Song', 'M\'Bami', 'Womé', 'Kalla', 'N\'Kufo', 'M\'Boma', 'Song', 'Eto\'o', 'Song'],
        'Egypt': ['Hassan', 'Ahmed', 'Mahmoud', 'Ali', 'Mohamed', 'Hussein', 'Ibrahim', 'Omar', 'Khalil', 'Tarek'],
        'Tunisia': ['Ben', 'Trabelsi', 'Jaziri', 'Jemâa', 'Mnari', 'Nafti', 'Saïfi', 'Zitouni', 'Ben', 'Trabelsi'],
        'South Africa': ['Mokoena', 'Pienaar', 'Tshabalala', 'Khumalo', 'Masilela', 'Gaxa', 'Modise', 'Parker', 'Mphela', 'Nomvethe'],
        'Japan': ['Tanaka', 'Sato', 'Suzuki', 'Takahashi', 'Watanabe', 'Ito', 'Yamamoto', 'Nakamura', 'Kobayashi', 'Kato'],
        'South Korea': ['Kim', 'Lee', 'Park', 'Choi', 'Jung', 'Kang', 'Cho', 'Yoon', 'Jang', 'Lim'],
        'China': ['Wang', 'Li', 'Zhang', 'Liu', 'Chen', 'Yang', 'Huang', 'Zhao', 'Wu', 'Zhou'],
        'Australia': ['Smith', 'Jones', 'Williams', 'Brown', 'Taylor', 'Wilson', 'Johnson', 'Anderson', 'Thompson', 'White'],
        'USA': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez'],
        'Mexico': ['Hernández', 'García', 'Martínez', 'López', 'González', 'Pérez', 'Rodríguez', 'Sánchez', 'Ramírez', 'Cruz'],
        'Colombia': ['Rodríguez', 'González', 'García', 'Martínez', 'López', 'Hernández', 'Pérez', 'Sánchez', 'Ramírez', 'Torres'],
        'Chile': ['González', 'Muñoz', 'Rojas', 'Díaz', 'Pérez', 'Soto', 'Silva', 'Morales', 'Flores', 'Castro'],
        'Uruguay': ['Rodríguez', 'González', 'Silva', 'Pérez', 'García', 'Fernández', 'López', 'Martínez', 'Díaz', 'Hernández'],
        'Paraguay': ['González', 'Rodríguez', 'García', 'Martínez', 'López', 'Pérez', 'Sánchez', 'Fernández', 'Silva', 'Díaz'],
        'Peru': ['García', 'Rodríguez', 'López', 'González', 'Martínez', 'Pérez', 'Sánchez', 'Fernández', 'Silva', 'Díaz'],
        'Ecuador': ['García', 'Rodríguez', 'González', 'Martínez', 'López', 'Pérez', 'Sánchez', 'Fernández', 'Silva', 'Díaz'],
        'Venezuela': ['González', 'Rodríguez', 'García', 'Martínez', 'López', 'Pérez', 'Sánchez', 'Fernández', 'Silva', 'Díaz'],
        'Canada': ['Smith', 'Brown', 'Tremblay', 'Martin', 'Roy', 'Gagnon', 'Lee', 'Wilson', 'Johnson', 'MacDonald']
    }
    
    def select_nationality():
        """Select a nationality based on weighted probabilities."""
        nationalities = list(NATIONALITY_DATA.keys())
        weights = [NATIONALITY_DATA[nat]['weight'] for nat in nationalities]
        total_weight = sum(weights)
        normalized_weights = [w / total_weight for w in weights]
        return random.choices(nationalities, weights=normalized_weights)[0]
    
    def generate_player_name(nationality):
        """Generate a realistic first name and surname for a given nationality."""
        if nationality not in NATIONALITY_DATA:
            nationality = 'England'
        
        first_names = NATIONALITY_DATA[nationality]['names']
        surnames = SURNAME_DATA.get(nationality, SURNAME_DATA['England'])
        
        first_name = random.choice(first_names)
        surname = random.choice(surnames)
        
        return first_name, surname
    
    # Generate regen based on retiring player
    nationality = select_nationality()
    first_name, surname = generate_player_name(nationality)
    full_name = f"{first_name} {surname}"
    
    # Age: 16-18 for regens
    age = random.randint(16, 18)
    
    # Skin color from nationality
    skin_color = NATIONALITY_DATA[nationality]['skin_color']
    
    # Position: Keep the same as retiring player
    registered_position = retired_player_data['registered_position']
    
    # Financial data: Lower for young players
    base_salary = random.randint(30000, 120000)
    contract_years = random.randint(3, 5)
    yearly_wage_rise = random.uniform(0.03, 0.10)
    
    # Generate development keys (mixed profiles 95% of the time)
    if random.random() < 0.95:
        # Mixed profile
        profiles = list(range(10))  # 0-9
        weights = [random.randint(10, 80) for _ in range(3)]
        total_weight = sum(weights)
        normalized_weights = [w / total_weight for w in weights]
        
        selected_profiles = random.choices(profiles, weights=normalized_weights, k=3)
        development_key = (selected_profiles[0] << 20) | (selected_profiles[1] << 10) | selected_profiles[2]
    else:
        # Pure profile
        development_key = random.randint(0, 9)
    
    # Trait key (0-3)
    trait_key = random.randint(0, 3)
    
    # Base the regen's attributes on the retiring player's attributes
    # but scaled down for age and with some randomness
    age_factor = 0.6 + (age - 16) * 0.075  # 16yo = 60%, 17yo = 67.5%, 18yo = 75%
    
    # Skill attributes: base on retiring player but scaled down
    skill_attributes = {}
    skill_fields = [
        'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
        'response', 'agility', 'dribble_accuracy', 'dribble_speed',
        'short_pass_accuracy', 'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed',
        'shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy', 'swerve',
        'heading', 'jump', 'technique', 'aggression', 'mentality', 'goal_keeping',
        'team_work', 'consistency', 'condition_fitness'
    ]
    
    for skill in skill_fields:
        if skill in retired_player_data:
            base_value = retired_player_data[skill]
            # Scale down for age and add randomness
            variation = random.uniform(-8, 8)
            final_value = int(base_value * age_factor + variation)
            # Ensure within valid range
            final_value = max(1, min(99, final_value))
            skill_attributes[skill] = final_value
        else:
            # Default value if skill not found
            skill_attributes[skill] = random.randint(50, 70)
    
    # Positional ratings: base on retiring player
    positional_fields = ['gk', 'cwp', 'cbt', 'sb', 'dmf', 'wb', 'cmf', 'smf', 'amf', 'wf', 'ss', 'cf']
    positional_attributes = {}
    
    for pos in positional_fields:
        if pos in retired_player_data:
            base_value = retired_player_data[pos]
            variation = random.uniform(-8, 8)
            final_value = int(base_value * age_factor + variation)
            final_value = max(1, min(99, final_value))
            positional_attributes[pos] = final_value
        else:
            positional_attributes[pos] = random.randint(50, 70)
    
    # Special skills: inherit some from retiring player
    special_fields = [
        'dribbling_skill', 'tactical_dribble', 'positioning', 'reaction', 'playmaking',
        'passing', 'scoring', 'one_one_scoring', 'post_player', 'lines', 'middle_shooting',
        'side', 'centre', 'penalties', 'one_touch_pass', 'outside', 'marking', 'sliding',
        'covering', 'd_line_control', 'penalty_stopper', 'one_on_one_stopper', 'long_throw'
    ]
    
    special_attributes = {}
    for skill in special_fields:
        if skill in retired_player_data:
            # 70% chance to inherit the skill
            if random.random() < 0.7:
                special_attributes[skill] = retired_player_data[skill]
            else:
                special_attributes[skill] = 0
        else:
            special_attributes[skill] = 0
    
    # Calculated ratings (will be calculated by the system)
    calculated_ratings = {
        'attack_rating': 50,
        'defense_rating': 50,
        'physical_rating': 50,
        'power_rating': 50,
        'technique_rating': 50,
        'goalkeeping_rating': 50
    }
    
    # Create the complete regen data
    regen_data = {
        'player_name': full_name,
        'age': age,
        'nationality': nationality,
        'skin_color': skin_color,
        'strong_foot': random.choice(['Right', 'Left']),
        'favoured_side': random.choice(['Right', 'Left']),
        'registered_position': registered_position,
        'game_position': registered_position,
        'club_id': retired_player_data['club_id'],
        'salary': base_salary,
        'contract_years_remaining': contract_years,
        'market_value': 0,  # Will be calculated
        'yearly_wage_rise': yearly_wage_rise,
        'development_key': development_key,
        'trait_key': trait_key,
        'games_played': 0,
        'goals': 0,
        'assists': 0,
        **skill_attributes,
        **positional_attributes,
        **special_attributes,
        **calculated_ratings
    }
    
    return regen_data

def import_csv_data():
    """Import data from pe6_player_data.csv into the database."""
    print("📥 Importing data from pe6_player_data.csv...")
    
    CSV_FILE = 'pe6_player_data.csv'
    
    if not os.path.exists(CSV_FILE):
        print(f"❌ Error: {CSV_FILE} not found!")
        print("Please ensure the CSV file is in the same directory as this script.")
        return False
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('PRAGMA foreign_keys = ON;')
        cursor = conn.cursor()

        # Read CSV with proper encoding
        df = pd.read_csv(CSV_FILE, encoding='latin1')
        print(f"✅ Loaded {len(df)} players from CSV")

        # Define mapping from CSV Column Names to SQL Column Names
        raw_to_sql_column_map = {
            'ID': 'id',
            'NAME': 'player_name',
            'SHIRT_NAME': 'shirt_name',
            'CLUB TEAM': 'club_team_raw',  # Temporary column to get club_id
            'REGISTERED POSITION': 'registered_position',
            'HEIGHT': 'height',
            'STRONG FOOT': 'strong_foot',
            'FAVOURED SIDE': 'favoured_side',
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
            'AGE': 'age',
            'WEIGHT': 'weight',
            'NATIONALITY': 'nationality',
            'SKIN COLOR': 'skin_color',
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
            'CF  12': 'cf',
            'INJURY TOLERANCE': 'injury_tolerance',
            'DRIBBLE STYLE': 'dribble_style',
            'FREE KICK STYLE': 'free_kick_style',
            'PK STYLE': 'pk_style',
            'DROP KICK STYLE': 'drop_kick_style',
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
            'CLUB NUMBER': 'club_number'
        }

        # Rename columns in the DataFrame using the map
        df = df.rename(columns=raw_to_sql_column_map)

        # Check for duplicate player IDs
        duplicate_ids = df['id'][df['id'].duplicated()].unique()
        if len(duplicate_ids) > 0:
            print(f"❌ Error: Duplicate player IDs found in CSV: {duplicate_ids}")
            return False

        # 1. Populate the 'teams' table
        print("🏢 Creating teams from CSV data...")
        unique_clubs = df['club_team_raw'].dropna().unique()
        for club in unique_clubs:
            try:
                cursor.execute("INSERT OR IGNORE INTO teams (club_name) VALUES (?)", (club,))
            except Exception as err:
                print(f"Error inserting club {club}: {err}")
        
        # Ensure 'No Club' exists
        cursor.execute("INSERT OR IGNORE INTO teams (club_name) VALUES (?)", ("No Club",))
        conn.commit()
        print(f"✅ Created {len(unique_clubs) + 1} teams")

        # 2. Create club_name to club_id mapping
        cursor.execute("SELECT id, club_name FROM teams")
        club_id_map = {name: id for id, name in cursor.fetchall()}
        no_club_id = club_id_map.get("No Club")

        # 3. Map club_team_raw to club_id
        def map_club_id(x):
            if pd.isna(x):
                return no_club_id
            return club_id_map.get(x, no_club_id)
        
        df['club_id'] = df['club_team_raw'].apply(map_club_id)
        df = df.drop(columns=['club_team_raw'])

        # 4. Define columns for SQL insert
        sql_insert_columns = [
            'id', 'player_name', 'shirt_name', 'club_id', 'registered_position', 'age', 'height', 'weight',
            'nationality', 'strong_foot', 'favoured_side', 'skin_color',
            'gk', 'cwp', 'cbt', 'sb', 'dmf', 'wb', 'cmf', 'smf', 'amf', 'wf', 'ss', 'cf',
            'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration', 'response', 'agility', 
            'dribble_accuracy', 'dribble_speed', 'short_pass_accuracy', 'short_pass_speed', 'long_pass_accuracy',
            'long_pass_speed', 'shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy',
            'swerve', 'heading', 'jump', 'technique', 'aggression', 'mentality', 'goal_keeping',
            'team_work', 'consistency', 'condition_fitness', 'dribbling_skill', 'tactical_dribble',
            'positioning', 'reaction', 'playmaking', 'passing', 'scoring', 'one_one_scoring',
            'post_player', 'lines', 'middle_shooting', 'side', 'centre', 'penalties', 'one_touch_pass',
            'outside', 'marking', 'sliding', 'covering', 'd_line_control', 'penalty_stopper',
            'one_on_one_stopper', 'long_throw', 'injury_tolerance', 'dribble_style', 'free_kick_style',
            'pk_style', 'drop_kick_style', 'face_type', 'preset_face_number', 'head_width',
            'neck_length', 'neck_width', 'shoulder_height', 'shoulder_width', 'chest_measurement',
            'waist_circumference', 'arm_circumference', 'leg_circumference', 'calf_circumference',
            'leg_length', 'wristband', 'wristband_color', 'international_number', 'classic_number', 'club_number'
        ]

        # 5. Prepare data for insertion
        data_to_insert = []
        for row in df[sql_insert_columns].itertuples(index=False, name=None):
            processed_row = [None if pd.isna(x) else x for x in row]
            data_to_insert.append(processed_row)

        print(f"👥 Inserting {len(data_to_insert)} players...")
        cursor.executemany(
            f"INSERT OR REPLACE INTO players ({', '.join(sql_insert_columns)}) VALUES ({', '.join(['?' for _ in sql_insert_columns])})",
            data_to_insert
        )
        conn.commit()
        print("✅ Players imported successfully!")

        # 6. Add default values for new columns
        print("🔧 Adding default values for new columns...")
        cursor.execute("""
            UPDATE players SET 
                salary = 0,
                contract_years_remaining = 3,
                market_value = 0,
                yearly_wage_rise = 0.05,
                development_key = 0,
                trait_key = 0,
                games_played = 0,
                goals = 0,
                assists = 0
            WHERE salary IS NULL
        """)
        conn.commit()
        print("✅ Default values added!")

        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error during CSV import: {e}")
        return False

def main():
    """Main function to reset database and implement proper regen system."""
    print("🔄 PES6 LEAGUE DATABASE RESET AND REGEN SYSTEM")
    print("=" * 60)
    
    # Create backup
    create_backup()
    
    # Reset database
    reset_database()
    
    # Import CSV data
    if import_csv_data():
        print("\n✅ Database reset and import completed!")
        print("🎯 The database now contains:")
        print("   - All teams from the CSV")
        print("   - All players from the CSV")
        print("   - Proper schema with all required fields")
        print("   - Default values for new columns")
        print("   - Ready for the proper regen system")
    else:
        print("\n❌ CSV import failed!")
        print("The database has been reset but no data was imported.")
        print("Please check that pe6_player_data.csv exists and try again.")
    
    print(f"\n📁 Backup saved as: {BACKUP_PATH}")
    print("⚠️  Original database has been reset!")

if __name__ == "__main__":
    main() 