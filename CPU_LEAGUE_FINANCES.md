# CPU League Financial System

## Overview

The CPU League Financial System automatically calculates and distributes match-day revenues for all CPU league games. Financial data is tracked per game and added to team budgets.

## Revenue Components

### 1. 🎟️ Attendance Revenue (Home Team Only)

**Formula**:
```
Base = 15% of team market value
Position Factor = 1.0 (1st place) to 0.3 (last place)
Guaranteed = 30% of base
Variable = 70% of base × position factor
Total = Guaranteed + Variable
```

**Factors**:
- **Team Market Value** (100%): Higher value = more fans
- **League Position** (70% weight): Better position = more attendance
  - 1st place: 100% of position component
  - Mid-table: ~65% of position component  
  - Last place: 30% of position component

**Example** (€80M team, 4th/4 teams):
- Base: €80M × 15% = €12M
- Guaranteed: €12M × 30% = €3.6M
- Position factor: 0.3 (last place)
- Variable: €12M × 70% × 0.3 = €2.52M
- **Total: €6.12M**

### 2. 🤝 Sponsor Premium (Both Teams)

**Formula**: Fixed amount based on division tier

**Division Tiers**:
- **Division 1**: €500,000 per game
- **Division 2**: €300,000 per game
- **Division 3+**: €150,000 per game

**Tier Detection**: Based on division name
- "Division 1" or "Div 1" → Tier 1
- "Division 2" or "Div 2" → Tier 2
- All others → Tier 3

**Example**:
- Division 1 game: Both teams get €500k
- Division 2 game: Both teams get €300k
- Cup/Other: Both teams get €150k

### 3. 👕 Merchandise Revenue (Both Teams)

**Formula**:
```
Base Merch = 8% of team market value
MV Component = 50% of base
Star Component = 50% of base × (star_players / 5)
Total = MV Component + Star Component
```

**Factors**:
- **50%**: Team market value (higher value = more sales)
- **50%**: Star players (>€50M market value, up to 5)
  - 0 stars: 0% of star component
  - 1 star: 20% of star component
  - 3 stars: 60% of star component
  - 5 stars: 100% of star component

**Example** (€88M team, 0 stars):
- Base: €88M × 8% = €7.04M
- MV component: €7.04M × 50% = €3.52M
- Star component: €7.04M × 50% × (0/5) = €0
- **Total: €3.52M**

**Example** (€200M team, 3 stars):
- Base: €200M × 8% = €16M
- MV component: €16M × 50% = €8M
- Star component: €16M × 50% × (3/5) = €4.8M
- **Total: €12.8M**

### 4. 🏆 Prize Bonus (Result-Based)

**Formula**:
- **Win**: €300,000 to winner
- **Draw**: €150,000 split (€75,000 each)
- **Loss**: €0

**Example**:
- Home 2-1 Away: Home gets €300k, Away gets €0
- Home 1-1 Away: Both get €75k
- Home 0-2 Away: Home gets €0, Away gets €300k

## Total Earnings

### Home Team
```
Total = Attendance + Sponsor + Merchandise + Prize
```

**Typical Breakdown** (mid-table team, €80M MV, win):
- Attendance: €8M (60%)
- Sponsor: €500k (4%)
- Merchandise: €4M (30%)
- Prize: €300k (2%)
- **Total: €12.8M**

### Away Team
```
Total = Sponsor + Merchandise + Prize
```

**Typical Breakdown** (€80M MV, loss):
- Sponsor: €500k (11%)
- Merchandise: €4M (89%)
- Prize: €0 (0%)
- **Total: €4.5M**

## Database Schema

### New Columns in `league_games` Table

```sql
home_attendance_revenue INTEGER DEFAULT 0
home_sponsor_premium INTEGER DEFAULT 0
away_sponsor_premium INTEGER DEFAULT 0
home_merchandise_revenue INTEGER DEFAULT 0
away_merchandise_revenue INTEGER DEFAULT 0
home_prize_bonus INTEGER DEFAULT 0
away_prize_bonus INTEGER DEFAULT 0
home_total_earnings INTEGER DEFAULT 0
away_total_earnings INTEGER DEFAULT 0
```

## Integration

### Automatic Calculation

Financial data is automatically calculated when a CPU league game is simulated:

1. Game is simulated (`simulate_cpu_game`)
2. Scores and stats are saved
3. **Financial calculation is triggered**
4. Revenue components are calculated
5. Data is saved to `league_games` table
6. Team budgets are updated

### Manual Calculation

You can also calculate finances for existing games:

```python
from cpu_league_finances import process_game_finances

# Process finances for a specific game
finances = process_game_finances(game_id=123)
```

## Configuration

Base values can be adjusted in `cpu_league_finances.py`:

```python
BASE_ATTENDANCE_MULTIPLIER = 0.15  # 15% of team MV
BASE_SPONSOR_DIVISION_1 = 500000   # €500k
BASE_SPONSOR_DIVISION_2 = 300000   # €300k
BASE_SPONSOR_DIVISION_3 = 150000   # €150k
BASE_MERCHANDISE = 0.08            # 8% of team MV
STAR_PLAYER_BONUS = 50000          # €50k per star
STAR_PLAYER_THRESHOLD = 50000000   # €50M threshold
WIN_BONUS = 300000                 # €300k
DRAW_BONUS = 150000                # €150k (split)
```

## Example Scenarios

### Scenario 1: Top Team Home Win (Division 1)

**Home Team**: €200M MV, 1st/20 teams, 3 stars
**Away Team**: €80M MV, 0 stars
**Result**: 3-1 (Home Win)

**Home Earnings**:
- Attendance: €28.5M (1st place bonus)
- Sponsor: €500k
- Merchandise: €12.8M (3 stars)
- Prize: €300k
- **Total: €42.1M** ✅

**Away Earnings**:
- Sponsor: €500k
- Merchandise: €3.2M
- Prize: €0
- **Total: €3.7M**

### Scenario 2: Mid-Table Draw (Division 2)

**Home Team**: €100M MV, 10th/20 teams, 1 star
**Away Team**: €90M MV, 12th/20 teams, 0 stars
**Result**: 1-1 (Draw)

**Home Earnings**:
- Attendance: €10.5M (mid-table)
- Sponsor: €300k
- Merchandise: €4.8M (1 star)
- Prize: €75k
- **Total: €15.675M**

**Away Earnings**:
- Sponsor: €300k
- Merchandise: €3.6M
- Prize: €75k
- **Total: €3.975M**

### Scenario 3: Small Team Away Win (Cup)

**Home Team**: €50M MV, 4th/4 teams, 0 stars
**Away Team**: €60M MV, 0 stars
**Result**: 0-2 (Away Win)

**Home Earnings**:
- Attendance: €3.825M (last place)
- Sponsor: €150k
- Merchandise: €2M
- Prize: €0
- **Total: €5.975M**

**Away Earnings**:
- Sponsor: €150k
- Merchandise: €2.4M
- Prize: €300k
- **Total: €2.85M**

## Files

1. **cpu_league_finances.py** - Core financial calculation module
2. **add_cpu_league_financial_columns.py** - Database schema updater
3. **test_cpu_league_finances.py** - Test script
4. **app.py** - Integration into game simulation
5. **refresh_and_reimport.py** - Schema update in safe refresh
6. **CPU_LEAGUE_FINANCES.md** - This documentation

## Testing

Run the test script to verify calculations:

```bash
python3 test_cpu_league_finances.py
```

This will:
- Load a recent played game
- Calculate all financial components
- Display detailed breakdown
- Show revenue percentages

## Benefits

1. ✅ **Realistic**: Revenue tied to team quality and performance
2. ✅ **Balanced**: Multiple revenue streams
3. ✅ **Fair**: Home advantage (attendance) balanced by away travel
4. ✅ **Dynamic**: Position affects attendance
5. ✅ **Scalable**: Works for any division tier
6. ✅ **Automatic**: No manual intervention needed

## Future Enhancements

Potential additions for "official" leagues:
- TV rights revenue
- European competition bonuses
- Relegation/promotion bonuses
- Season-end prize money
- Transfer market fees
- Youth academy funding

## Notes

- Financial data is stored per game for historical tracking
- Team budgets are updated immediately after each game
- System works for both round-robin and knockout competitions
- Division tier is auto-detected from division name
- Star player threshold (€50M) can be adjusted
- All values are in Euros (€)
