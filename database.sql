-- Create the database (if it doesn't exist already)
CREATE DATABASE IF NOT EXISTS pes6_league_db;

-- Use the database
USE pes6_league_db;

ALTER TABLE players
ADD COLUMN salary INT DEFAULT 0,
ADD COLUMN contract_years_remaining INT DEFAULT 0,
ADD COLUMN market_value BIGINT DEFAULT 0, -- Market value can be large
ADD COLUMN yearly_wage_rise INT DEFAULT 0;

-- Drop dependent tables first to avoid foreign key constraints issues when recreating
-- IMPORTANT: Only run these DROP statements if you are okay with deleting all existing data!
-- This will wipe all data in these tables and recreate them from scratch.
DROP TABLE IF EXISTS team_players;    -- Your league's user-managed teams' players (references 'league_teams' and 'players')
DROP TABLE IF EXISTS player_performance; -- PES6 player performance stats (references 'players')
DROP TABLE IF EXISTS league_teams;    -- Your league's user-managed teams (references 'users')
DROP TABLE IF EXISTS comments;        -- Blog comments (references 'posts' and 'users')
DROP TABLE IF EXISTS posts;           -- Blog posts (references 'users')
DROP TABLE IF EXISTS users;           -- User accounts for the website
DROP TABLE IF EXISTS players;         -- PES6 player data
DROP TABLE IF EXISTS teams;           -- PES6 club teams


-- Table for Users (for your website login)
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(80) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    email VARCHAR(120) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table for Posts (for your website blog)
CREATE TABLE IF NOT EXISTS posts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    media_type VARCHAR(50) DEFAULT 'none', -- 'image', 'video', 'none'
    media_path VARCHAR(255) NULL,         -- Path to the uploaded file
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Table for Comments (for your website blog)
CREATE TABLE IF NOT EXISTS comments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    post_id INT NOT NULL,
    user_id INT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Table for PES6 Club Teams (populated from 'CLUB TEAM' in CSV)
CREATE TABLE IF NOT EXISTS teams (
    id INT AUTO_INCREMENT PRIMARY KEY,
    club_name VARCHAR(100) UNIQUE NOT NULL
);

-- Table for PES6 Players (populated from CSV data)
CREATE TABLE IF NOT EXISTS players (
    `id` INT PRIMARY KEY, -- Enclosed in backticks as 'id' can sometimes be problematic
    player_name VARCHAR(100) NOT NULL,
    shirt_name VARCHAR(100),
    club_id INT, -- Foreign key referencing the teams table
    registered_position VARCHAR(50),
    age TINYINT,
    height SMALLINT,
    weight SMALLINT,
    nationality VARCHAR(100),
    strong_foot VARCHAR(10),
    favoured_side VARCHAR(10),

    -- Positional Awareness
    gk TINYINT DEFAULT 0,
    cwp TINYINT DEFAULT 0,
    cbt TINYINT DEFAULT 0,
    sb TINYINT DEFAULT 0,
    dmf TINYINT DEFAULT 0,
    wb TINYINT DEFAULT 0,
    cmf TINYINT DEFAULT 0,
    smf TINYINT DEFAULT 0,
    amf TINYINT DEFAULT 0,
    wf TINYINT DEFAULT 0,
    ss TINYINT DEFAULT 0,
    cf TINYINT DEFAULT 0,

    -- Basic Attributes (Skills)
    attack SMALLINT,
    defense SMALLINT,
    balance SMALLINT,
    stamina SMALLINT,
    top_speed SMALLINT,
    acceleration SMALLINT,
    response SMALLINT,
    agility SMALLINT,
    dribble_accuracy SMALLINT,
    dribble_speed SMALLINT,
    short_pass_accuracy SMALLINT,
    short_pass_speed SMALLINT,
    long_pass_accuracy SMALLINT,
    long_pass_speed SMALLINT,
    shot_accuracy SMALLINT,
    shot_power SMALLINT,
    shot_technique SMALLINT,
    free_kick_accuracy SMALLINT,
    swerve SMALLINT,
    heading SMALLINT,
    jump SMALLINT,
    technique SMALLINT,
    aggression SMALLINT,
    mentality SMALLINT,
    goal_keeping SMALLINT,
    team_work SMALLINT,
    consistency SMALLINT,
    condition_fitness SMALLINT,

    -- Special Player Skills (enclosed problematic ones in backticks)
    dribbling_skill TINYINT DEFAULT 0,
    tactical_dribble TINYINT DEFAULT 0,
    `positioning` TINYINT DEFAULT 0,
    `reaction` TINYINT DEFAULT 0,
    playmaking TINYINT DEFAULT 0,
    `passing` TINYINT DEFAULT 0,
    `scoring` TINYINT DEFAULT 0,
    one_one_scoring TINYINT DEFAULT 0,
    post_player TINYINT DEFAULT 0,
    `lines` TINYINT DEFAULT 0,
    middle_shooting TINYINT DEFAULT 0,
    `side` TINYINT DEFAULT 0,
    `centre` TINYINT DEFAULT 0,
    `penalties` TINYINT DEFAULT 0,
    one_touch_pass TINYINT DEFAULT 0,
    `outside` TINYINT DEFAULT 0,
    `marking` TINYINT DEFAULT 0,
    `sliding` TINYINT DEFAULT 0,
    `covering` TINYINT DEFAULT 0,
    d_line_control TINYINT DEFAULT 0,
    penalty_stopper TINYINT DEFAULT 0,
    one_on_one_stopper TINYINT DEFAULT 0,
    long_throw TINYINT DEFAULT 0,

    -- Other Details (from CSV, but not skills)
    injury_tolerance VARCHAR(10),
    dribble_style SMALLINT,
    free_kick_style SMALLINT,
    pk_style SMALLINT,
    drop_kick_style SMALLINT,
    skin_color SMALLINT,
    face_type SMALLINT,
    preset_face_number SMALLINT,
    head_width SMALLINT,
    neck_length SMALLINT,
    neck_width SMALLINT,
    shoulder_height SMALLINT,
    shoulder_width SMALLINT,
    chest_measurement SMALLINT,
    waist_circumference SMALLINT,
    arm_circumference SMALLINT,
    leg_circumference SMALLINT,
    calf_circumference SMALLINT,
    leg_length SMALLINT,
    wristband VARCHAR(10),
    wristband_color VARCHAR(50),
    international_number SMALLINT,
    classic_number SMALLINT,
    club_number SMALLINT,

    FOREIGN KEY (club_id) REFERENCES teams(id)
);

-- Table for Player Season Performance (optional, if you want to track stats)
-- THIS TABLE MUST BE DROPPED BEFORE 'players' and CREATED AFTER 'players'
CREATE TABLE IF NOT EXISTS player_performance (
    id INT AUTO_INCREMENT PRIMARY KEY,
    player_id INT,
    season VARCHAR(10), -- e.g., '2005-2006'
    matches_played INT,
    goals INT,
    assists INT,
    -- Add other relevant performance stats
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

-- Table for user-managed teams in your league (references 'users' and 'players')
-- This is your existing 'teams' table from your league setup.
CREATE TABLE IF NOT EXISTS league_teams (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL, -- The owner of the team
    team_name VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Table for user-managed teams' players (references 'league_teams' and 'players')
-- This is your existing 'team_players' table from your league setup.
CREATE TABLE IF NOT EXISTS team_players (
    team_id INT NOT NULL,         -- This is your league's user-created team_id from league_teams
    player_id INT NOT NULL,       -- This is the PES6 player_id from the new 'players' table
    PRIMARY KEY (team_id, player_id),
    FOREIGN KEY (team_id) REFERENCES league_teams(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

-- Table for user messages and league news (inbox)
CREATE TABLE IF NOT EXISTS messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sender_id INT NULL, -- NULL for league news
    recipient_id INT NOT NULL,
    subject VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    type ENUM('user', 'league') DEFAULT 'user',
    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (recipient_id) REFERENCES users(id) ON DELETE CASCADE
);

ALTER TABLE players ADD COLUMN salary INT DEFAULT 0;
ALTER TABLE players ADD COLUMN contract_years_remaining INT DEFAULT 0;
ALTER TABLE players ADD COLUMN yearly_wage_rise INT DEFAULT 0;
ALTER TABLE players ADD COLUMN market_value INT DEFAULT 0;