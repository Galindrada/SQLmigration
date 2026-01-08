# Swap Team ID Fix ✅

## Problem Found

**Issue:** Swap player wasn't transferring to user's team correctly

**Root Cause:** 
- The code was using a roundabout way to get the team ID
- Should use the same pattern as `buy_player_from_transfer_list` which uses `league_teams.id` directly
- `league_teams.id` matches `teams.id` (they're the same), so we can use it directly

## Fix Applied

**File:** `app.py` line ~6903

**Before:**
```python
# Get league_teams.id, then get team_name, then get teams.id
cur.execute("SELECT id FROM league_teams WHERE user_id = ? LIMIT 1", ...)
user_league_team_id = ...
cur.execute("SELECT id FROM teams WHERE club_name = (SELECT team_name FROM league_teams WHERE id = ?)", ...)
user_team_id = ...
```

**After:**
```python
# Use league_teams.id directly (same as buy_player_from_transfer_list)
cur.execute("SELECT DISTINCT lt.id FROM league_teams lt WHERE lt.user_id = ? LIMIT 1", ...)
user_team_id = user_team_result['id']  # This is both league_teams.id and teams.id
```

## Why This Works

- `league_teams.id` and `teams.id` match (verified in database)
- `buy_player_from_transfer_list` uses `league_teams.id` directly for `club_id`
- Using the same pattern ensures consistency

## Result

✅ Swap completion now uses the same team ID resolution as regular transfers
✅ Swap player should now correctly transfer to user's team
✅ Simplified code that matches existing patterns

## Status

✅ Fixed to match `buy_player_from_transfer_list` pattern
✅ Code simplified and consistent
✅ Ready for testing
