package den

import (
	"encoding/json"
	"fmt"
	"log"
	"math/rand"
	"net/http"
	"sync"
	"time"

	"github.com/gorilla/websocket"

	"github.com/colados/go-season/internal/competition"
)

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool { return true },
}

type EventType string

const (
	EventKickoff   EventType = "kickoff"
	EventChance    EventType = "chance"
	EventGoal      EventType = "goal"
	EventCard      EventType = "card"
	EventInjury    EventType = "injury"
	EventSpecial   EventType = "special"
	EventHalftime  EventType = "halftime"
	EventFulltime  EventType = "fulltime"
	EventComment   EventType = "commentary"
	EventState     EventType = "state"
)

type Event struct {
	Type      EventType `json:"type"`
	Minute    int       `json:"minute"`
	Message   string    `json:"message"`
	HomeScore int       `json:"home_score"`
	AwayScore int       `json:"away_score"`
	Side      string    `json:"side,omitempty"` // home|away
	At        string    `json:"at"`
}

type MatchState struct {
	MatchID       int64  `json:"match_id"`
	CompetitionID int64  `json:"competition_id"`
	Competition   string `json:"competition"`
	Kind          string `json:"kind"`
	Round         string `json:"round"`
	HomeName      string `json:"home_name"`
	AwayName      string `json:"away_name"`
	HomeScore     int    `json:"home_score"`
	AwayScore     int    `json:"away_score"`
	Minute        int    `json:"minute"`
	Phase         string `json:"phase"` // lobby|live|finished
	RulesSummary  string `json:"rules_summary"`
}

type Hub struct {
	mu       sync.Mutex
	rooms    map[int64]*Room
	comps    *competition.Store
	tick     time.Duration
	onFinish func(matchID int64, home, away int)
}

func NewHub(comps *competition.Store, tick time.Duration, onFinish func(matchID int64, home, away int)) *Hub {
	if tick < 100*time.Millisecond {
		tick = 800 * time.Millisecond
	}
	return &Hub{
		rooms:    make(map[int64]*Room),
		comps:    comps,
		tick:     tick,
		onFinish: onFinish,
	}
}

type Room struct {
	hub      *Hub
	matchID  int64
	state    MatchState
	rules    competition.Rules
	mu       sync.Mutex
	clients  map[*websocket.Conn]struct{}
	running  bool
	stop     chan struct{}
	events   []Event
}

func (h *Hub) ServeWS(w http.ResponseWriter, r *http.Request, matchID int64) {
	room, err := h.ensureRoom(matchID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		return
	}

	room.mu.Lock()
	room.clients[conn] = struct{}{}
	snapshot := room.state
	history := append([]Event(nil), room.events...)
	room.mu.Unlock()

	_ = conn.WriteJSON(map[string]any{"type": EventState, "state": snapshot})
	for _, ev := range history {
		_ = conn.WriteJSON(ev)
	}

	go func() {
		defer func() {
			room.mu.Lock()
			delete(room.clients, conn)
			room.mu.Unlock()
			_ = conn.Close()
		}()
		for {
			_, msg, err := conn.ReadMessage()
			if err != nil {
				return
			}
			var cmd struct {
				Action string `json:"action"`
			}
			if err := json.Unmarshal(msg, &cmd); err != nil {
				continue
			}
			switch cmd.Action {
			case "start":
				room.Start()
			case "stop":
				room.Stop()
			}
		}
	}()
}

func (h *Hub) ensureRoom(matchID int64) (*Room, error) {
	h.mu.Lock()
	defer h.mu.Unlock()
	if room, ok := h.rooms[matchID]; ok {
		return room, nil
	}
	m, err := h.comps.GetMatch(matchID)
	if err != nil {
		return nil, fmt.Errorf("match not found")
	}
	comp, err := h.comps.Get(m.CompetitionID)
	if err != nil {
		return nil, fmt.Errorf("competition not found")
	}
	room := &Room{
		hub:     h,
		matchID: matchID,
		clients: make(map[*websocket.Conn]struct{}),
		stop:    make(chan struct{}),
		rules:   comp.Rules,
		state: MatchState{
			MatchID:       m.ID,
			CompetitionID: m.CompetitionID,
			Competition:   comp.Name,
			Kind:          string(comp.Kind),
			Round:         m.RoundLabel,
			HomeName:      m.HomeName,
			AwayName:      m.AwayName,
			HomeScore:     m.HomeScore,
			AwayScore:     m.AwayScore,
			Minute:        0,
			Phase:         "lobby",
			RulesSummary:  summarizeRules(comp.Kind, comp.Rules),
		},
	}
	if m.Status == "finished" {
		room.state.Phase = "finished"
	} else if m.Status == "live" {
		room.state.Phase = "live"
	}
	h.rooms[matchID] = room
	return room, nil
}

func summarizeRules(kind competition.Kind, r competition.Rules) string {
	parts := []string{fmt.Sprintf("kind=%s", kind), fmt.Sprintf("sim=%s", r.SimStyle)}
	if r.SalaryCap > 0 {
		parts = append(parts, fmt.Sprintf("cap=%dM", r.SalaryCap/1_000_000))
	}
	flags := []string{}
	if r.AllowCards {
		flags = append(flags, "cards")
	}
	if r.AllowInjuries {
		flags = append(flags, "injuries")
	}
	if r.AllowPenalties {
		flags = append(flags, "pens")
	}
	if r.AllowSpecialEvents {
		flags = append(flags, "specials")
	}
	if r.ExtraTime {
		flags = append(flags, "ET")
	}
	if len(flags) > 0 {
		parts = append(parts, "events="+join(flags, "+"))
	}
	return join(parts, " · ")
}

func join(xs []string, sep string) string {
	out := ""
	for i, x := range xs {
		if i > 0 {
			out += sep
		}
		out += x
	}
	return out
}

func (r *Room) Start() {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.running || r.state.Phase == "finished" {
		return
	}
	r.running = true
	r.state.Phase = "live"
	r.state.Minute = 0
	r.stop = make(chan struct{})
	go r.loop()
}

func (r *Room) Stop() {
	r.mu.Lock()
	defer r.mu.Unlock()
	if !r.running {
		return
	}
	close(r.stop)
	r.running = false
}

func (r *Room) loop() {
	ticker := time.NewTicker(r.hub.tick)
	defer ticker.Stop()

	r.emit(Event{
		Type:      EventKickoff,
		Minute:    0,
		Message:   fmt.Sprintf("Kick-off! %s vs %s", r.state.HomeName, r.state.AwayName),
		HomeScore: r.state.HomeScore,
		AwayScore: r.state.AwayScore,
	})

	for minute := 1; minute <= 90; minute++ {
		select {
		case <-r.stop:
			return
		case <-ticker.C:
		}

		r.mu.Lock()
		r.state.Minute = minute
		r.mu.Unlock()

		if minute == 45 {
			r.emit(Event{
				Type: EventHalftime, Minute: 45,
				Message:   "Half-time",
				HomeScore: r.state.HomeScore, AwayScore: r.state.AwayScore,
			})
		}

		r.tickMinute(minute)
		// Always push a lightweight tick so clients keep the clock moving.
		r.emit(Event{
			Type: EventState, Minute: minute,
			Message:   "",
			HomeScore: r.state.HomeScore, AwayScore: r.state.AwayScore,
		})
	}

	// Optional ET for knockout-style hybrid/user when rules allow and draw
	r.mu.Lock()
	draw := r.state.HomeScore == r.state.AwayScore
	et := r.rules.ExtraTime && draw
	r.mu.Unlock()
	if et {
		r.emit(Event{Type: EventComment, Minute: 90, Message: "Scores level — extra time!", HomeScore: r.state.HomeScore, AwayScore: r.state.AwayScore})
		for minute := 91; minute <= 120; minute++ {
			select {
			case <-r.stop:
				return
			case <-ticker.C:
			}
			r.mu.Lock()
			r.state.Minute = minute
			r.mu.Unlock()
			r.tickMinute(minute)
		}
	}

	r.mu.Lock()
	r.state.Phase = "finished"
	r.running = false
	home, away := r.state.HomeScore, r.state.AwayScore
	r.mu.Unlock()

	r.emit(Event{
		Type: EventFulltime, Minute: r.state.Minute,
		Message:   fmt.Sprintf("Full-time %d-%d", home, away),
		HomeScore: home, AwayScore: away,
	})
	if r.hub.onFinish != nil {
		r.hub.onFinish(r.matchID, home, away)
	}
}

func (r *Room) tickMinute(minute int) {
	// Lightweight Elifoot-flavoured event stream — same pipeline for all kinds.
	// Kind/rules only gate which event types can fire.
	roll := rand.Float64()
	switch {
	case roll < 0.08:
		r.maybeGoal(minute)
	case roll < 0.14:
		r.maybeChance(minute)
	case roll < 0.17 && r.rules.AllowCards:
		r.maybeCard(minute)
	case roll < 0.185 && r.rules.AllowInjuries:
		r.maybeInjury(minute)
	case roll < 0.20 && r.rules.AllowSpecialEvents:
		r.maybeSpecial(minute)
	default:
		// quiet minute — still push state heartbeat every 10'
		if minute%10 == 0 {
			r.emit(Event{
				Type: EventComment, Minute: minute,
				Message:   fmt.Sprintf("%d' — midfield battle continues", minute),
				HomeScore: r.state.HomeScore, AwayScore: r.state.AwayScore,
			})
		}
	}
}

func (r *Room) side() (string, string) {
	if rand.Float64() < 0.52 {
		return "home", r.state.HomeName
	}
	return "away", r.state.AwayName
}

func (r *Room) maybeGoal(minute int) {
	side, name := r.side()
	r.mu.Lock()
	if side == "home" {
		r.state.HomeScore++
	} else {
		r.state.AwayScore++
	}
	hs, as := r.state.HomeScore, r.state.AwayScore
	r.mu.Unlock()
	r.emit(Event{
		Type: EventGoal, Minute: minute, Side: side,
		Message:   fmt.Sprintf("%d' GOAL! %s find the net (%d-%d)", minute, name, hs, as),
		HomeScore: hs, AwayScore: as,
	})
}

func (r *Room) maybeChance(minute int) {
	side, name := r.side()
	r.emit(Event{
		Type: EventChance, Minute: minute, Side: side,
		Message:   fmt.Sprintf("%d' Great chance for %s — saved/wide!", minute, name),
		HomeScore: r.state.HomeScore, AwayScore: r.state.AwayScore,
	})
}

func (r *Room) maybeCard(minute int) {
	side, name := r.side()
	colour := "Yellow"
	if rand.Float64() < 0.15 {
		colour = "Red"
	}
	r.emit(Event{
		Type: EventCard, Minute: minute, Side: side,
		Message:   fmt.Sprintf("%d' %s card for %s", minute, colour, name),
		HomeScore: r.state.HomeScore, AwayScore: r.state.AwayScore,
	})
}

func (r *Room) maybeInjury(minute int) {
	side, name := r.side()
	r.emit(Event{
		Type: EventInjury, Minute: minute, Side: side,
		Message:   fmt.Sprintf("%d' Injury concern for %s", minute, name),
		HomeScore: r.state.HomeScore, AwayScore: r.state.AwayScore,
	})
}

func (r *Room) maybeSpecial(minute int) {
	side, name := r.side()
	kinds := []string{"penalty shout", "hail-mary corner", "dangerous free-kick"}
	if !r.rules.AllowPenalties {
		kinds = []string{"hail-mary corner", "dangerous free-kick"}
	}
	k := kinds[rand.Intn(len(kinds))]
	r.emit(Event{
		Type: EventSpecial, Minute: minute, Side: side,
		Message:   fmt.Sprintf("%d' Special moment — %s for %s", minute, k, name),
		HomeScore: r.state.HomeScore, AwayScore: r.state.AwayScore,
	})
}

func (r *Room) emit(ev Event) {
	ev.At = time.Now().UTC().Format(time.RFC3339Nano)
	r.mu.Lock()
	r.events = append(r.events, ev)
	clients := make([]*websocket.Conn, 0, len(r.clients))
	for c := range r.clients {
		clients = append(clients, c)
	}
	state := r.state
	r.mu.Unlock()

	payload := map[string]any{
		"type":       ev.Type,
		"minute":     ev.Minute,
		"message":    ev.Message,
		"home_score": ev.HomeScore,
		"away_score": ev.AwayScore,
		"side":       ev.Side,
		"at":         ev.At,
		"state":      state,
	}
	for _, c := range clients {
		if err := c.WriteJSON(payload); err != nil {
			log.Printf("den ws write: %v", err)
		}
	}
}
