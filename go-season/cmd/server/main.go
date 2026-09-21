package main

import (
	"log"
	"net/http"

	"github.com/colados/go-season/internal/config"
	"github.com/colados/go-season/internal/db"
	"github.com/colados/go-season/internal/web"
)

func main() {
	cfg := config.Load()
	database, err := db.Open(cfg.SQLitePath)
	if err != nil {
		log.Fatalf("sqlite open %s: %v", cfg.SQLitePath, err)
	}
	defer database.Close()

	// Scaffold convenience: ensure demo admin exists against the shared users table.
	demoHash := "pbkdf2:sha256:1000000$OPs5ADZ46vcXxgsu$74947ed45cdd88c3a8f8562546a0f07b8b36b4d90eb412ab37cd08281b7014b4"
	if err := db.EnsureDemoAdmin(database, demoHash); err != nil {
		log.Printf("demo admin ensure: %v", err)
	}

	app, err := web.New(cfg, database)
	if err != nil {
		log.Fatalf("web app: %v", err)
	}

	log.Printf("go-season listening on %s (db=%s)", cfg.Addr, cfg.SQLitePath)
	if err := http.ListenAndServe(cfg.Addr, app.Handler()); err != nil {
		log.Fatal(err)
	}
}
