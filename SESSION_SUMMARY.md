# Session Summary - Database & Market Fixes

## Issues Fixed

### 1. ✅ Database Override Problem (WAL Mode)
**Problem:** When uploading a new database file, secondary teams kept reappearing
**Root Cause:** SQLite WAL (Write-Ahead Log) files were caching data
**Solution:** Delete WAL/SHM files before replacing database:
```bash
rm -f pes6_league_db.sqlite-wal pes6_league_db.sqlite-shm
```

### 2. ✅ Draftees Getting CPU Offers  
**Problem:** CPU teams were making free agent offers to draftees (draftee=1)
**Solution:** Added exclusion filter in 3 locations:
- `make_cpu_free_agency_offer()`
- `raise_cpu_free_agency_offer()`  
- `aggressively_raise_user_offers()`
```sql
AND (p.draftee IS NULL OR p.draftee = 0)
```

### 3. ✅ Secondary Teams Not Participating in Market
**Problem:** Query was comparing `teams.id` with `league_teams.id` (different ID systems)
**Solution:** Changed to compare by name:
```python
# BEFORE (broken):
WHERE t.id IN (SELECT DISTINCT lt.id FROM league_teams lt WHERE lt.user_id = 1)

# AFTER (fixed):
WHERE t.club_name IN (SELECT lt.team_name FROM league_teams lt WHERE lt.user_id = 1)
```
**Impact:** 89 CPU teams can now participate (including "Zero" secondary team)

### 4. ✅ Jorge Mendes System Rewrite
**Old System:** Generated 50 offers and picked the best
**New System:** Evaluates contract toxicity and direct placement

#### Contract Toxicity Calculation:
```python
toxicity = (current_salary - fair_salary) × contract_years × 1.03

• Overpaid (current > fair): positive toxicity → reduces sale price
• Underpaid (current < fair): negative toxicity → increases sale price
```

#### Sale Price Formula:
```python
sale_price = (market_value × 50-75%) - toxicity
commission = abs(sale_price) × 25%  # Always positive
net_amount = sale_price - commission
```

#### Key Features:
- ✅ Uses player's **database market_value** (not recalculated)
- ✅ Commission always **positive** (adds to expenses even for compensation)
- ✅ **No minimum price** (can go negative for toxic contracts)
- ✅ Places player on team with **fewest in that position**
- ✅ Blog post shows: player, clubs, fee/compensation

### 5. ✅ Salary Calculation Consistency
**Aligned Jorge Mendes with contract_renewal.py:**
```python
base_salary = calculate_player_salary_base(...)
if position in [0, 2, 3, 4]:  # GK, CBT, DMF, FB
    base_salary *= 1.75  # Defensive boost
fair_salary = apply_random_salary_adjustment(base_salary)  # ±15%
```

### 6. ✅ Blog Post Fixes
- Changed from `blog_posts` table to `posts` table (displays on blog page)
- Simplified content (removed excessive analysis)
- Shows only: player name, clubs, money

---

## Current System State

### Secondary Teams
- **"Zero"** team exists with €500M budget, 0 players, csv_visible=0
- ✅ Properly linked to league_teams with user_id=1
- ✅ Can participate in all CPU market activities
- ✅ Excluded from CSV exports (players show as "No Club")

### Database Mode
- **WAL mode ENABLED** (for concurrent operations)
- Works well for market bazaar concurrent actions
- Just need to clean WAL files before database replacement

### Jorge Mendes
- ✅ Evaluates contract toxicity
- ✅ Can handle negative sales (user pays compensation)
- ✅ Commission always positive
- ✅ Uses same salary calculation as contract renewals
- ✅ Places on team with optimal need

### Market Protection
- ✅ Draftees protected from CPU offers
- ✅ Secondary teams active in market
- ✅ 120 CPU teams total (including secondary)

---

## If You Need to Replace Database in Future

Run these commands BEFORE uploading new database:
```bash
rm -f pes6_league_db.sqlite-wal pes6_league_db.sqlite-shm
```

Then upload your new database file. WAL mode will auto-resume on next connection.

---

## Files Modified

1. **cpu_ai.py** - Fixed team queries, excluded draftees
2. **app.py** - Jorge Mendes rewrite, fixed team queries
3. **templates/market_bazaar.html** - Enhanced error handling

## Files Created
- `JORGE_MENDES_SUMMARY.md` - Complete Jorge Mendes documentation

---

All systems operational! 🎯

