# Go Season

Continuous season engine for Colados / CPU / Inter-Leagues style competitions.

Runs **beside** the PythonAnywhere Flask site, using the **same SQLite** `users` table for login (Werkzeug `pbkdf2:sha256` hashes). Competition/match tables are prefixed `go_*` so they do not collide with Flask schema.

## Quick start

```bash
cd go-season
export GO_SEASON_SQLITE=../pes6_league_db.sqlite
export GO_SEASON_ADDR=:8080
export GO_SEASON_ADMINS=SeasonAdmin,Galindro
go run ./cmd/server
```

Open http://localhost:8080 — demo admin `SeasonAdmin` / `season-demo`.

## What's in this scaffold

- Minimal login against shared `users`
- Admin competitions menu: create **user / cpu / hybrid** comps
- Rules editor (cards, injuries, pens, specials, salary cap, Elifoot style)
- Schedule editor (manual / fixed / recurring timestamps)
- **Playing den** with WebSocket minute-by-minute event feed (same pipeline for every kind; rules gate event types)

## Fly.io

```bash
fly launch --name colados-go-season --region iad
fly secrets set GO_SEASON_SECRET=... GO_SEASON_ADMINS=SeasonAdmin
# Mount or sync your sqlite (or switch to remote DB later)
fly deploy
```

WebSockets work on Fly with the included `fly.toml` HTTP service (HTTP/2 + WS upgrade).

## Manual SQLite sync back to PythonAnywhere

Export season results when you want:

```bash
sqlite3 "$GO_SEASON_SQLITE" ".dump go_competitions go_competition_rules go_competition_schedules go_matches" > season_export.sql
```

Import on PA into a copy of the DB (or via an admin import endpoint later). Do **not** concurrently write the same SQLite file from Fly and PA.

## Layout

```
go-season/
  cmd/server/          entrypoint
  internal/auth/       Werkzeug password check + sessions
  internal/competition/ rules + schedules + matches
  internal/den/         WebSocket playing den
  internal/web/         HTTP UI + embedded templates/static
```
