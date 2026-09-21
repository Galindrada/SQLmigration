package config

import (
	"os"
	"strconv"
	"strings"
)

type Config struct {
	Addr            string
	SQLitePath      string
	SessionSecret   string
	AdminUsernames  map[string]bool
	TickIntervalMS  int
}

func Load() Config {
	admins := map[string]bool{}
	for _, name := range strings.Split(env("GO_SEASON_ADMINS", "SeasonAdmin,Galindro"), ",") {
		name = strings.TrimSpace(name)
		if name != "" {
			admins[strings.ToLower(name)] = true
		}
	}

	tick, err := strconv.Atoi(env("GO_SEASON_TICK_MS", "800"))
	if err != nil || tick < 100 {
		tick = 800
	}

	return Config{
		Addr:           env("GO_SEASON_ADDR", ":8080"),
		SQLitePath:     env("GO_SEASON_SQLITE", "../pes6_league_db.sqlite"),
		SessionSecret:  env("GO_SEASON_SECRET", "dev-season-secret-change-me"),
		AdminUsernames: admins,
		TickIntervalMS: tick,
	}
}

func env(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
