package competition

import (
	"database/sql"
	"fmt"
	"strings"
	"time"
)

type Kind string

const (
	KindUser   Kind = "user"   // Colados-style user leagues
	KindCPU    Kind = "cpu"    // fully simulated CPU leagues
	KindHybrid Kind = "hybrid" // Inter-Leagues style
)

type Status string

const (
	StatusDraft     Status = "draft"
	StatusScheduled Status = "scheduled"
	StatusLive      Status = "live"
	StatusCompleted Status = "completed"
	StatusArchived  Status = "archived"
)

type ScheduleMode string

const (
	ScheduleManual    ScheduleMode = "manual"
	ScheduleFixed     ScheduleMode = "fixed"
	ScheduleRecurring ScheduleMode = "recurring"
)

type Competition struct {
	ID          int64
	Name        string
	Kind        Kind
	Description string
	Status      Status
	CreatedBy   sql.NullInt64
	CreatedAt   string
	UpdatedAt   string
	Rules       Rules
	Schedule    Schedule
}

type Rules struct {
	TeamCount           int
	GroupCount          int
	HomeAndAway         bool
	SalaryCap           int64
	AllowCards          bool
	AllowInjuries       bool
	AllowPenalties      bool
	AllowSpecialEvents  bool
	ExtraTime           bool
	SimStyle            string
	Notes               string
}

type Schedule struct {
	ID                       int64
	Mode                     ScheduleMode
	KickoffAt                string
	Timezone                 string
	IntervalMinutes          int
	MatchdayDurationMinutes  int
	Enabled                  bool
}

type Match struct {
	ID            int64
	CompetitionID int64
	RoundLabel    string
	HomeName      string
	AwayName      string
	HomeScore     int
	AwayScore     int
	Status        string
	KickoffAt     string
}

type Store struct {
	DB *sql.DB
}

func DefaultsForKind(kind Kind) (Rules, Schedule) {
	rules := Rules{
		TeamCount:          16,
		GroupCount:         4,
		HomeAndAway:        true,
		SalaryCap:          0,
		AllowCards:         true,
		AllowInjuries:      true,
		AllowPenalties:     true,
		AllowSpecialEvents: true,
		ExtraTime:          true,
		SimStyle:           "elifoot",
	}
	sched := Schedule{
		Mode:                    ScheduleManual,
		Timezone:                "UTC",
		IntervalMinutes:         0,
		MatchdayDurationMinutes: 12,
		Enabled:                 false,
	}
	switch kind {
	case KindUser:
		rules.TeamCount = 8
		rules.GroupCount = 1
		rules.AllowSpecialEvents = true
		rules.Notes = "User-managed Colados-style competition"
	case KindCPU:
		rules.TeamCount = 20
		rules.GroupCount = 1
		rules.SalaryCap = 0
		rules.Notes = "Fully CPU-simulated domestic league"
		sched.Mode = ScheduleRecurring
		sched.IntervalMinutes = 60
		sched.Enabled = false
	case KindHybrid:
		rules.TeamCount = 16
		rules.GroupCount = 4
		rules.SalaryCap = 500_000_000
		rules.Notes = "Hybrid Inter-Leagues cup (user + CPU)"
		sched.Mode = ScheduleFixed
		sched.MatchdayDurationMinutes = 15
	}
	return rules, sched
}

func (s *Store) List() ([]Competition, error) {
	rows, err := s.DB.Query(`
		SELECT c.id, c.name, c.kind, c.description, c.status, c.created_by, c.created_at, c.updated_at,
		       COALESCE(r.team_count,16), COALESCE(r.group_count,4), COALESCE(r.home_and_away,1),
		       COALESCE(r.salary_cap,0), COALESCE(r.allow_cards,1), COALESCE(r.allow_injuries,1),
		       COALESCE(r.allow_penalties,1), COALESCE(r.allow_special_events,1), COALESCE(r.extra_time,1),
		       COALESCE(r.sim_style,'elifoot'), COALESCE(r.notes,''),
		       COALESCE(sch.id,0), COALESCE(sch.mode,'manual'), COALESCE(sch.kickoff_at,''),
		       COALESCE(sch.timezone,'UTC'), COALESCE(sch.interval_minutes,0),
		       COALESCE(sch.matchday_duration_minutes,12), COALESCE(sch.enabled,0)
		FROM go_competitions c
		LEFT JOIN go_competition_rules r ON r.competition_id = c.id
		LEFT JOIN go_competition_schedules sch ON sch.competition_id = c.id
		ORDER BY c.id DESC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []Competition
	for rows.Next() {
		var c Competition
		var homeAway, cards, injuries, pens, specials, et, enabled int
		if err := rows.Scan(
			&c.ID, &c.Name, &c.Kind, &c.Description, &c.Status, &c.CreatedBy, &c.CreatedAt, &c.UpdatedAt,
			&c.Rules.TeamCount, &c.Rules.GroupCount, &homeAway, &c.Rules.SalaryCap,
			&cards, &injuries, &pens, &specials, &et, &c.Rules.SimStyle, &c.Rules.Notes,
			&c.Schedule.ID, &c.Schedule.Mode, &c.Schedule.KickoffAt, &c.Schedule.Timezone,
			&c.Schedule.IntervalMinutes, &c.Schedule.MatchdayDurationMinutes, &enabled,
		); err != nil {
			return nil, err
		}
		c.Rules.HomeAndAway = homeAway == 1
		c.Rules.AllowCards = cards == 1
		c.Rules.AllowInjuries = injuries == 1
		c.Rules.AllowPenalties = pens == 1
		c.Rules.AllowSpecialEvents = specials == 1
		c.Rules.ExtraTime = et == 1
		c.Schedule.Enabled = enabled == 1
		out = append(out, c)
	}
	return out, rows.Err()
}

func (s *Store) Get(id int64) (*Competition, error) {
	list, err := s.List()
	if err != nil {
		return nil, err
	}
	for i := range list {
		if list[i].ID == id {
			return &list[i], nil
		}
	}
	return nil, sql.ErrNoRows
}

type CreateInput struct {
	Name        string
	Kind        Kind
	Description string
	CreatedBy   int64
	Rules       Rules
	Schedule    Schedule
}

func (s *Store) Create(in CreateInput) (int64, error) {
	in.Name = strings.TrimSpace(in.Name)
	if in.Name == "" {
		return 0, fmt.Errorf("name is required")
	}
	switch in.Kind {
	case KindUser, KindCPU, KindHybrid:
	default:
		return 0, fmt.Errorf("invalid kind %q", in.Kind)
	}
	if in.Rules.SimStyle == "" {
		in.Rules.SimStyle = "elifoot"
	}
	if in.Schedule.Timezone == "" {
		in.Schedule.Timezone = "UTC"
	}
	if in.Schedule.Mode == "" {
		in.Schedule.Mode = ScheduleManual
	}

	tx, err := s.DB.Begin()
	if err != nil {
		return 0, err
	}
	defer func() { _ = tx.Rollback() }()

	now := time.Now().UTC().Format(time.RFC3339)
	res, err := tx.Exec(`
		INSERT INTO go_competitions (name, kind, description, status, created_by, created_at, updated_at)
		VALUES (?, ?, ?, 'draft', ?, ?, ?)`,
		in.Name, string(in.Kind), in.Description, in.CreatedBy, now, now)
	if err != nil {
		return 0, err
	}
	id, err := res.LastInsertId()
	if err != nil {
		return 0, err
	}

	_, err = tx.Exec(`
		INSERT INTO go_competition_rules (
			competition_id, team_count, group_count, home_and_away, salary_cap,
			allow_cards, allow_injuries, allow_penalties, allow_special_events,
			extra_time, sim_style, notes
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		id, in.Rules.TeamCount, in.Rules.GroupCount, boolInt(in.Rules.HomeAndAway), in.Rules.SalaryCap,
		boolInt(in.Rules.AllowCards), boolInt(in.Rules.AllowInjuries), boolInt(in.Rules.AllowPenalties),
		boolInt(in.Rules.AllowSpecialEvents), boolInt(in.Rules.ExtraTime), in.Rules.SimStyle, in.Rules.Notes,
	)
	if err != nil {
		return 0, err
	}

	_, err = tx.Exec(`
		INSERT INTO go_competition_schedules (
			competition_id, mode, kickoff_at, timezone, interval_minutes,
			matchday_duration_minutes, enabled
		) VALUES (?, ?, ?, ?, ?, ?, ?)`,
		id, string(in.Schedule.Mode), nullEmpty(in.Schedule.KickoffAt), in.Schedule.Timezone,
		in.Schedule.IntervalMinutes, in.Schedule.MatchdayDurationMinutes, boolInt(in.Schedule.Enabled),
	)
	if err != nil {
		return 0, err
	}

	if err := tx.Commit(); err != nil {
		return 0, err
	}
	return id, nil
}

func (s *Store) UpdateSchedule(competitionID int64, sch Schedule) error {
	_, err := s.DB.Exec(`
		UPDATE go_competition_schedules
		SET mode = ?, kickoff_at = ?, timezone = ?, interval_minutes = ?,
		    matchday_duration_minutes = ?, enabled = ?
		WHERE competition_id = ?`,
		string(sch.Mode), nullEmpty(sch.KickoffAt), sch.Timezone, sch.IntervalMinutes,
		sch.MatchdayDurationMinutes, boolInt(sch.Enabled), competitionID,
	)
	if err != nil {
		return err
	}
	_, err = s.DB.Exec(`UPDATE go_competitions SET updated_at = ?, status = CASE
		WHEN status = 'draft' AND ? = 1 THEN 'scheduled'
		ELSE status END WHERE id = ?`,
		time.Now().UTC().Format(time.RFC3339), boolInt(sch.Enabled), competitionID)
	return err
}

func (s *Store) UpdateRules(competitionID int64, r Rules) error {
	_, err := s.DB.Exec(`
		UPDATE go_competition_rules SET
			team_count=?, group_count=?, home_and_away=?, salary_cap=?,
			allow_cards=?, allow_injuries=?, allow_penalties=?, allow_special_events=?,
			extra_time=?, sim_style=?, notes=?
		WHERE competition_id=?`,
		r.TeamCount, r.GroupCount, boolInt(r.HomeAndAway), r.SalaryCap,
		boolInt(r.AllowCards), boolInt(r.AllowInjuries), boolInt(r.AllowPenalties),
		boolInt(r.AllowSpecialEvents), boolInt(r.ExtraTime), r.SimStyle, r.Notes, competitionID,
	)
	if err != nil {
		return err
	}
	_, err = s.DB.Exec(`UPDATE go_competitions SET updated_at = ? WHERE id = ?`,
		time.Now().UTC().Format(time.RFC3339), competitionID)
	return err
}

func (s *Store) CreateDemoMatch(competitionID int64, home, away, round string) (int64, error) {
	if home == "" || away == "" {
		return 0, fmt.Errorf("home and away names required")
	}
	if round == "" {
		round = "Matchday 1"
	}
	res, err := s.DB.Exec(`
		INSERT INTO go_matches (competition_id, round_label, home_name, away_name, status, kickoff_at)
		VALUES (?, ?, ?, ?, 'scheduled', ?)`,
		competitionID, round, home, away, time.Now().UTC().Format(time.RFC3339))
	if err != nil {
		return 0, err
	}
	return res.LastInsertId()
}

func (s *Store) GetMatch(id int64) (*Match, error) {
	row := s.DB.QueryRow(`
		SELECT id, competition_id, round_label, home_name, away_name, home_score, away_score, status, COALESCE(kickoff_at,'')
		FROM go_matches WHERE id = ?`, id)
	var m Match
	if err := row.Scan(&m.ID, &m.CompetitionID, &m.RoundLabel, &m.HomeName, &m.AwayName,
		&m.HomeScore, &m.AwayScore, &m.Status, &m.KickoffAt); err != nil {
		return nil, err
	}
	return &m, nil
}

func (s *Store) ListMatches(competitionID int64) ([]Match, error) {
	rows, err := s.DB.Query(`
		SELECT id, competition_id, round_label, home_name, away_name, home_score, away_score, status, COALESCE(kickoff_at,'')
		FROM go_matches WHERE competition_id = ? ORDER BY id DESC`, competitionID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Match
	for rows.Next() {
		var m Match
		if err := rows.Scan(&m.ID, &m.CompetitionID, &m.RoundLabel, &m.HomeName, &m.AwayName,
			&m.HomeScore, &m.AwayScore, &m.Status, &m.KickoffAt); err != nil {
			return nil, err
		}
		out = append(out, m)
	}
	return out, rows.Err()
}

func (s *Store) FinishMatch(id int64, homeScore, awayScore int) error {
	_, err := s.DB.Exec(`UPDATE go_matches SET status='finished', home_score=?, away_score=? WHERE id=?`,
		homeScore, awayScore, id)
	return err
}

func boolInt(v bool) int {
	if v {
		return 1
	}
	return 0
}

func nullEmpty(s string) any {
	s = strings.TrimSpace(s)
	if s == "" {
		return nil
	}
	return s
}
