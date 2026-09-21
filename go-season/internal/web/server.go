package web

import (
	"database/sql"
	"embed"
	"fmt"
	"html/template"
	"io/fs"
	"log"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/colados/go-season/internal/auth"
	"github.com/colados/go-season/internal/competition"
	"github.com/colados/go-season/internal/config"
	dbpkg "github.com/colados/go-season/internal/db"
	"github.com/colados/go-season/internal/den"
)

//go:embed templates/* static/*
var embedded embed.FS

type App struct {
	cfg   config.Config
	db    *sql.DB
	sess  *auth.Store
	comps *competition.Store
	den   *den.Hub
	tmpl  *template.Template
}

func New(cfg config.Config, database *sql.DB) (*App, error) {
	comps := &competition.Store{DB: database}
	app := &App{
		cfg:   cfg,
		db:    database,
		sess:  auth.NewStore(false),
		comps: comps,
	}
	app.den = den.NewHub(comps, time.Duration(cfg.TickIntervalMS)*time.Millisecond, func(matchID int64, home, away int) {
		if err := comps.FinishMatch(matchID, home, away); err != nil {
			log.Printf("finish match %d: %v", matchID, err)
		}
	})

	funcs := template.FuncMap{
		"kindLabel": func(k competition.Kind) string {
			switch k {
			case competition.KindUser:
				return "User (Colados)"
			case competition.KindCPU:
				return "CPU simulated"
			case competition.KindHybrid:
				return "Hybrid (Inter-Leagues)"
			default:
				return string(k)
			}
		},
		"boolYes": func(v bool) string {
			if v {
				return "yes"
			}
			return "no"
		},
	}

	t, err := template.New("root").Funcs(funcs).ParseFS(embedded, "templates/*.html")
	if err != nil {
		return nil, err
	}
	app.tmpl = t
	return app, nil
}

func (a *App) Handler() http.Handler {
	mux := http.NewServeMux()

	staticFS, err := fs.Sub(embedded, "static")
	if err != nil {
		panic(err)
	}
	mux.Handle("GET /static/", http.StripPrefix("/static/", http.FileServer(http.FS(staticFS))))

	mux.HandleFunc("GET /login", a.handleLoginGet)
	mux.HandleFunc("POST /login", a.handleLoginPost)
	mux.HandleFunc("POST /logout", a.requireAuth(a.handleLogout))
	mux.HandleFunc("GET /", a.requireAuth(a.handleHome))
	mux.HandleFunc("GET /admin/competitions", a.requireAdmin(a.handleAdminCompetitions))
	mux.HandleFunc("POST /admin/competitions", a.requireAdmin(a.handleCreateCompetition))
	mux.HandleFunc("GET /admin/competitions/{id}", a.requireAdmin(a.handleCompetitionDetail))
	mux.HandleFunc("POST /admin/competitions/{id}/rules", a.requireAdmin(a.handleUpdateRules))
	mux.HandleFunc("POST /admin/competitions/{id}/schedule", a.requireAdmin(a.handleUpdateSchedule))
	mux.HandleFunc("POST /admin/competitions/{id}/matches", a.requireAdmin(a.handleCreateMatch))
	mux.HandleFunc("GET /den/{id}", a.requireAuth(a.handleDenPage))
	mux.HandleFunc("GET /ws/den/{id}", a.requireAuth(a.handleDenWS))
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})

	return logging(mux)
}

func logging(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		next.ServeHTTP(w, r)
		log.Printf("%s %s %s", r.Method, r.URL.Path, time.Since(start))
	})
}

type pageData struct {
	Title    string
	User     auth.User
	Flash    string
	Error    string
	Data     any
}

func (a *App) currentUser(r *http.Request) (auth.User, bool) {
	return a.sess.UserFromRequest(r)
}

func (a *App) requireAuth(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if _, ok := a.currentUser(r); !ok {
			http.Redirect(w, r, "/login", http.StatusSeeOther)
			return
		}
		next(w, r)
	}
}

func (a *App) requireAdmin(next http.HandlerFunc) http.HandlerFunc {
	return a.requireAuth(func(w http.ResponseWriter, r *http.Request) {
		u, _ := a.currentUser(r)
		if !u.IsAdmin {
			http.Error(w, "admin only", http.StatusForbidden)
			return
		}
		next(w, r)
	})
}

func (a *App) render(w http.ResponseWriter, r *http.Request, name, title string, data any, errMsg string) {
	u, _ := a.currentUser(r)
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	if err := a.tmpl.ExecuteTemplate(w, name, pageData{
		Title: title,
		User:  u,
		Error: errMsg,
		Data:  data,
	}); err != nil {
		log.Printf("template %s: %v", name, err)
		http.Error(w, "template error", http.StatusInternalServerError)
	}
}

func (a *App) handleLoginGet(w http.ResponseWriter, r *http.Request) {
	if _, ok := a.currentUser(r); ok {
		http.Redirect(w, r, "/", http.StatusSeeOther)
		return
	}
	a.render(w, r, "login.html", "Login", nil, "")
}

func (a *App) handleLoginPost(w http.ResponseWriter, r *http.Request) {
	if err := r.ParseForm(); err != nil {
		a.render(w, r, "login.html", "Login", nil, "Invalid form")
		return
	}
	username := strings.TrimSpace(r.FormValue("username"))
	password := r.FormValue("password")
	row, err := dbpkg.FindUserByUsername(a.db, username)
	if err != nil || !auth.CheckWerkzeugPassword(row.Password, password) {
		a.render(w, r, "login.html", "Login", nil, "Invalid username or password")
		return
	}
	user := auth.User{
		ID:       row.ID,
		Username: row.Username,
		Email:    row.Email,
		IsAdmin:  a.cfg.AdminUsernames[strings.ToLower(row.Username)],
	}
	if err := a.sess.Create(w, user); err != nil {
		a.render(w, r, "login.html", "Login", nil, "Could not create session")
		return
	}
	http.Redirect(w, r, "/", http.StatusSeeOther)
}

func (a *App) handleLogout(w http.ResponseWriter, r *http.Request) {
	a.sess.Clear(w, r)
	http.Redirect(w, r, "/login", http.StatusSeeOther)
}

func (a *App) handleHome(w http.ResponseWriter, r *http.Request) {
	list, err := a.comps.List()
	if err != nil {
		a.render(w, r, "home.html", "Season Home", nil, err.Error())
		return
	}
	a.render(w, r, "home.html", "Season Home", list, "")
}

func (a *App) handleAdminCompetitions(w http.ResponseWriter, r *http.Request) {
	list, err := a.comps.List()
	if err != nil {
		a.render(w, r, "admin_competitions.html", "Competitions", nil, err.Error())
		return
	}
	a.render(w, r, "admin_competitions.html", "Competitions", map[string]any{
		"Competitions": list,
		"Kinds": []competition.Kind{
			competition.KindUser, competition.KindCPU, competition.KindHybrid,
		},
	}, "")
}

func (a *App) handleCreateCompetition(w http.ResponseWriter, r *http.Request) {
	u, _ := a.currentUser(r)
	if err := r.ParseForm(); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	kind := competition.Kind(r.FormValue("kind"))
	rules, sched := competition.DefaultsForKind(kind)
	rules.Notes = r.FormValue("notes")
	id, err := a.comps.Create(competition.CreateInput{
		Name:        r.FormValue("name"),
		Kind:        kind,
		Description: r.FormValue("description"),
		CreatedBy:   u.ID,
		Rules:       rules,
		Schedule:    sched,
	})
	if err != nil {
		list, _ := a.comps.List()
		a.render(w, r, "admin_competitions.html", "Competitions", map[string]any{
			"Competitions": list,
			"Kinds": []competition.Kind{
				competition.KindUser, competition.KindCPU, competition.KindHybrid,
			},
		}, err.Error())
		return
	}
	http.Redirect(w, r, fmt.Sprintf("/admin/competitions/%d", id), http.StatusSeeOther)
}

func (a *App) handleCompetitionDetail(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil {
		http.NotFound(w, r)
		return
	}
	comp, err := a.comps.Get(id)
	if err != nil {
		http.NotFound(w, r)
		return
	}
	matches, err := a.comps.ListMatches(id)
	if err != nil {
		a.render(w, r, "competition_detail.html", comp.Name, nil, err.Error())
		return
	}
	a.render(w, r, "competition_detail.html", comp.Name, map[string]any{
		"Competition": comp,
		"Matches":     matches,
	}, "")
}

func (a *App) handleUpdateRules(w http.ResponseWriter, r *http.Request) {
	id, _ := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err := r.ParseForm(); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	rules := competition.Rules{
		TeamCount:          atoiDefault(r.FormValue("team_count"), 16),
		GroupCount:         atoiDefault(r.FormValue("group_count"), 4),
		HomeAndAway:        r.FormValue("home_and_away") == "on",
		SalaryCap:          int64(atoiDefault(r.FormValue("salary_cap"), 0)),
		AllowCards:         r.FormValue("allow_cards") == "on",
		AllowInjuries:      r.FormValue("allow_injuries") == "on",
		AllowPenalties:     r.FormValue("allow_penalties") == "on",
		AllowSpecialEvents: r.FormValue("allow_special_events") == "on",
		ExtraTime:          r.FormValue("extra_time") == "on",
		SimStyle:           defaultString(r.FormValue("sim_style"), "elifoot"),
		Notes:              r.FormValue("notes"),
	}
	if err := a.comps.UpdateRules(id, rules); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	http.Redirect(w, r, fmt.Sprintf("/admin/competitions/%d", id), http.StatusSeeOther)
}

func (a *App) handleUpdateSchedule(w http.ResponseWriter, r *http.Request) {
	id, _ := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err := r.ParseForm(); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	sch := competition.Schedule{
		Mode:                    competition.ScheduleMode(r.FormValue("mode")),
		KickoffAt:               r.FormValue("kickoff_at"),
		Timezone:                defaultString(r.FormValue("timezone"), "UTC"),
		IntervalMinutes:         atoiDefault(r.FormValue("interval_minutes"), 0),
		MatchdayDurationMinutes: atoiDefault(r.FormValue("matchday_duration_minutes"), 12),
		Enabled:                 r.FormValue("enabled") == "on",
	}
	if err := a.comps.UpdateSchedule(id, sch); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	http.Redirect(w, r, fmt.Sprintf("/admin/competitions/%d", id), http.StatusSeeOther)
}

func (a *App) handleCreateMatch(w http.ResponseWriter, r *http.Request) {
	id, _ := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err := r.ParseForm(); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	matchID, err := a.comps.CreateDemoMatch(id, r.FormValue("home_name"), r.FormValue("away_name"), r.FormValue("round_label"))
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	http.Redirect(w, r, fmt.Sprintf("/den/%d", matchID), http.StatusSeeOther)
}

func (a *App) handleDenPage(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil {
		http.NotFound(w, r)
		return
	}
	m, err := a.comps.GetMatch(id)
	if err != nil {
		http.NotFound(w, r)
		return
	}
	comp, err := a.comps.Get(m.CompetitionID)
	if err != nil {
		http.NotFound(w, r)
		return
	}
	a.render(w, r, "den.html", "Playing Den", map[string]any{
		"Match":       m,
		"Competition": comp,
	}, "")
}

func (a *App) handleDenWS(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil {
		http.Error(w, "bad id", http.StatusBadRequest)
		return
	}
	a.den.ServeWS(w, r, id)
}

func atoiDefault(s string, def int) int {
	n, err := strconv.Atoi(strings.TrimSpace(s))
	if err != nil {
		return def
	}
	return n
}

func defaultString(s, def string) string {
	s = strings.TrimSpace(s)
	if s == "" {
		return def
	}
	return s
}
