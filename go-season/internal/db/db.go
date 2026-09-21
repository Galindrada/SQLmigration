package db

import (
	"database/sql"
	"fmt"
	"strings"

	_ "modernc.org/sqlite"
)

func Open(path string) (*sql.DB, error) {
	dsn := fmt.Sprintf("file:%s?_pragma=foreign_keys(1)&_pragma=busy_timeout(5000)", path)
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(1) // SQLite-friendly
	if err := db.Ping(); err != nil {
		_ = db.Close()
		return nil, err
	}
	if err := migrate(db); err != nil {
		_ = db.Close()
		return nil, err
	}
	return db, nil
}

// EnsureDemoAdmin creates SeasonAdmin / season-demo when missing (local scaffold only).
func EnsureDemoAdmin(db *sql.DB, hash string) error {
	var id int64
	err := db.QueryRow(`SELECT id FROM users WHERE username = 'SeasonAdmin'`).Scan(&id)
	if err == nil {
		return nil
	}
	if err != sql.ErrNoRows {
		return err
	}
	_, err = db.Exec(
		`INSERT INTO users (username, password, email) VALUES ('SeasonAdmin', ?, 'season-admin@localhost')`,
		hash,
	)
	return err
}

func migrate(db *sql.DB) error {
	stmts := []string{
		`CREATE TABLE IF NOT EXISTS go_competitions (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			name TEXT NOT NULL,
			kind TEXT NOT NULL CHECK (kind IN ('user','cpu','hybrid')),
			description TEXT NOT NULL DEFAULT '',
			status TEXT NOT NULL DEFAULT 'draft'
				CHECK (status IN ('draft','scheduled','live','completed','archived')),
			created_by INTEGER,
			created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
			updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
		)`,
		`CREATE TABLE IF NOT EXISTS go_competition_rules (
			competition_id INTEGER PRIMARY KEY,
			team_count INTEGER NOT NULL DEFAULT 16,
			group_count INTEGER NOT NULL DEFAULT 4,
			home_and_away INTEGER NOT NULL DEFAULT 1,
			salary_cap INTEGER NOT NULL DEFAULT 0,
			allow_cards INTEGER NOT NULL DEFAULT 1,
			allow_injuries INTEGER NOT NULL DEFAULT 1,
			allow_penalties INTEGER NOT NULL DEFAULT 1,
			allow_special_events INTEGER NOT NULL DEFAULT 1,
			extra_time INTEGER NOT NULL DEFAULT 1,
			sim_style TEXT NOT NULL DEFAULT 'elifoot',
			notes TEXT NOT NULL DEFAULT '',
			FOREIGN KEY (competition_id) REFERENCES go_competitions(id) ON DELETE CASCADE
		)`,
		`CREATE TABLE IF NOT EXISTS go_competition_schedules (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			competition_id INTEGER NOT NULL UNIQUE,
			mode TEXT NOT NULL DEFAULT 'manual'
				CHECK (mode IN ('manual','fixed','recurring')),
			kickoff_at TEXT,
			timezone TEXT NOT NULL DEFAULT 'UTC',
			interval_minutes INTEGER NOT NULL DEFAULT 0,
			matchday_duration_minutes INTEGER NOT NULL DEFAULT 12,
			enabled INTEGER NOT NULL DEFAULT 0,
			FOREIGN KEY (competition_id) REFERENCES go_competitions(id) ON DELETE CASCADE
		)`,
		`CREATE TABLE IF NOT EXISTS go_matches (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			competition_id INTEGER NOT NULL,
			round_label TEXT NOT NULL DEFAULT 'Friendly',
			home_name TEXT NOT NULL,
			away_name TEXT NOT NULL,
			home_score INTEGER NOT NULL DEFAULT 0,
			away_score INTEGER NOT NULL DEFAULT 0,
			status TEXT NOT NULL DEFAULT 'scheduled'
				CHECK (status IN ('scheduled','live','finished')),
			kickoff_at TEXT,
			created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
			FOREIGN KEY (competition_id) REFERENCES go_competitions(id) ON DELETE CASCADE
		)`,
	}
	for _, s := range stmts {
		if _, err := db.Exec(s); err != nil {
			return fmt.Errorf("migrate: %w\nstmt: %s", err, strings.Split(s, "\n")[0])
		}
	}
	return nil
}

type UserRow struct {
	ID       int64
	Username string
	Password string
	Email    string
}

func FindUserByUsername(db *sql.DB, username string) (*UserRow, error) {
	row := db.QueryRow(
		`SELECT id, username, password, email FROM users WHERE username = ? COLLATE NOCASE`,
		username,
	)
	var u UserRow
	if err := row.Scan(&u.ID, &u.Username, &u.Password, &u.Email); err != nil {
		return nil, err
	}
	return &u, nil
}
