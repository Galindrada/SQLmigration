PRAGMA foreign_keys = ON;
-- SQLite version of the schema

-- Drop tables if they exist (order matters for FKs)
DROP TABLE IF EXISTS team_players;
DROP TABLE IF EXISTS player_performance;
DROP TABLE IF EXISTS league_teams;
DROP TABLE IF EXISTS comments;
DROP TABLE IF EXISTS posts;
DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS offers;
DROP TABLE IF EXISTS players;
DROP TABLE IF EXISTS teams;
DROP TABLE IF EXISTS users;

-- Table for Users
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table for Posts
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    media_type TEXT DEFAULT 'none',
    media_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Table for Comments
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Table for PES6 Club Teams
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    club_name TEXT UNIQUE NOT NULL
);

-- Table for PES6 Players
CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY, -- Use INTEGER PRIMARY KEY for autoincrement in SQLite
    player_name TEXT NOT NULL,
    shirt_name TEXT,
    club_id INTEGER,
    registered_position TEXT,
    age INTEGER,
    height INTEGER,
    weight INTEGER,
    nationality TEXT,
    strong_foot TEXT,
    favoured_side TEXT,
    gk INTEGER DEFAULT 0,
    cwp INTEGER DEFAULT 0,
    cbt INTEGER DEFAULT 0,
    sb INTEGER DEFAULT 0,
    dmf INTEGER DEFAULT 0,
    wb INTEGER DEFAULT 0,
    cmf INTEGER DEFAULT 0,
    smf INTEGER DEFAULT 0,
    amf INTEGER DEFAULT 0,
    wf INTEGER DEFAULT 0,
    ss INTEGER DEFAULT 0,
    cf INTEGER DEFAULT 0,
    attack INTEGER,
    defense INTEGER,
    balance INTEGER,
    stamina INTEGER,
    top_speed INTEGER,
    acceleration INTEGER,
    response INTEGER,
    agility INTEGER,
    dribble_accuracy INTEGER,
    dribble_speed INTEGER,
    short_pass_accuracy INTEGER,
    short_pass_speed INTEGER,
    long_pass_accuracy INTEGER,
    long_pass_speed INTEGER,
    shot_accuracy INTEGER,
    shot_power INTEGER,
    shot_technique INTEGER,
    free_kick_accuracy INTEGER,
    swerve INTEGER,
    heading INTEGER,
    jump INTEGER,
    technique INTEGER,
    aggression INTEGER,
    mentality INTEGER,
    goal_keeping INTEGER,
    team_work INTEGER,
    consistency INTEGER,
    condition_fitness INTEGER,
    dribbling_skill INTEGER DEFAULT 0,
    tactical_dribble INTEGER DEFAULT 0,
    positioning INTEGER DEFAULT 0,
    reaction INTEGER DEFAULT 0,
    playmaking INTEGER DEFAULT 0,
    passing INTEGER DEFAULT 0,
    scoring INTEGER DEFAULT 0,
    one_one_scoring INTEGER DEFAULT 0,
    post_player INTEGER DEFAULT 0,
    lines INTEGER DEFAULT 0,
    middle_shooting INTEGER DEFAULT 0,
    side INTEGER DEFAULT 0,
    centre INTEGER DEFAULT 0,
    penalties INTEGER DEFAULT 0,
    one_touch_pass INTEGER DEFAULT 0,
    outside INTEGER DEFAULT 0,
    marking INTEGER DEFAULT 0,
    sliding INTEGER DEFAULT 0,
    covering INTEGER DEFAULT 0,
    d_line_control INTEGER DEFAULT 0,
    penalty_stopper INTEGER DEFAULT 0,
    one_on_one_stopper INTEGER DEFAULT 0,
    long_throw INTEGER DEFAULT 0,
    injury_tolerance TEXT,
    dribble_style INTEGER,
    free_kick_style INTEGER,
    pk_style INTEGER,
    drop_kick_style INTEGER,
    skin_color INTEGER,
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
    wristband TEXT,
    wristband_color TEXT,
    international_number INTEGER,
    classic_number INTEGER,
    club_number INTEGER,
    salary INTEGER DEFAULT 0,
    contract_years_remaining INTEGER DEFAULT 0,
    market_value INTEGER DEFAULT 0,
    yearly_wage_rise INTEGER DEFAULT 0,
    -- Bundled skill areas for better player display
    attack_rating INTEGER DEFAULT 0,
    defense_rating INTEGER DEFAULT 0,
    physical_rating INTEGER DEFAULT 0,
    power_rating INTEGER DEFAULT 0,
    technique_rating INTEGER DEFAULT 0,
    goalkeeping_rating INTEGER DEFAULT 0,
    FOREIGN KEY (club_id) REFERENCES teams(id)
);

-- Table for Player Season Performance
CREATE TABLE IF NOT EXISTS player_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER,
    season TEXT,
    matches_played INTEGER,
    goals INTEGER,
    assists INTEGER,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

-- Table for user-managed teams in your league
CREATE TABLE IF NOT EXISTS league_teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    team_name TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    budget INTEGER DEFAULT 450000000,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Table for user-managed teams' players
CREATE TABLE IF NOT EXISTS team_players (
    team_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    PRIMARY KEY (team_id, player_id),
    FOREIGN KEY (team_id) REFERENCES league_teams(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

-- Table for messages
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER NOT NULL,
    receiver_id INTEGER NOT NULL,
    subject TEXT,
    content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (receiver_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Table for offers
CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER NOT NULL,
    receiver_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    offer_amount INTEGER NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (receiver_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

-- Table for blacklist
CREATE TABLE IF NOT EXISTS blacklist (
    user_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, player_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

-- Example queries (remove or comment out if not needed)
-- SELECT * FROM league_teams WHERE user_id = 1;
-- SELECT id FROM players;
-- SELECT id, user_id, team_name FROM league_teams;