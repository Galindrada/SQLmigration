# CPU Dump for Strength ✅

## Feature Overview

**Purpose:** Release surplus players from CPU teams that have more than 28 players, sending them to free agency.

## Rules

1. **Team Eligibility:** Only CPU teams with >28 players
2. **Position Surplus:** Release players from positions where team has more than ideal count
3. **Player Selection:** Choose weakest players (lowest overall) in surplus positions
4. **Player Restrictions:**
   - **Overall:** Only release players with overall < 77
   - **Market Value:** Only release players with market_value < €5,000,000
   - **Age:** Don't release youngsters <23 unless extremely weak (overall <55)
   - Older players can be released if they meet other criteria
5. **Exclusions:**
   - Blacklisted players (cannot be released)
   - Loaned players (loaned_by IS NOT NULL)
6. **Financial:**
   - Team pays 25% of player's salary as severance
   - Severance added to player's career_earnings
   - Severance deducted from team budget
7. **Release:** Player moved to free agency (club_id = 141)

## Ideal Position Counts

- GK (0): 3
- CWP (1): 2
- CBT (2): 4
- SB (3): 4
- DMF (4): 2
- WB (5): 2
- CMF (6): 4
- SMF (7): 2
- AMF (8): 2
- WF (9): 2
- SS (10): 2
- CF (11): 3

## Implementation

### Function: `cpu_dump_for_strength()`
**Location:** `cpu_ai.py`

**Process:**
1. Find CPU teams with >28 players
2. For each team:
   - Get all players (excluding loaned and blacklisted)
   - Group by position
   - Identify positions with surplus (current > ideal)
   - Sort players by overall (weakest first)
   - Apply restrictions:
     * Overall < 77
     * Market value < €5,000,000
     * Age restrictions (protect youngsters <23 unless overall <55)
   - Select players to release
3. For each selected player:
   - Calculate severance (25% of salary)
   - Update player: club_id = 141, career_earnings += severance
   - Update team: budget -= severance
4. Return summary

### Route: `/free_agency/cpu_dump_strength`
**Location:** `app.py`

**Method:** POST
**Access:** Login required

**Response:**
- Creates blog post with release details
- Returns JSON with success status and count

### UI Button
**Location:** `templates/free_agency.html`

**Button:** "💪 CPU Dump for Strength"
**Location:** Below "Process Expired Offers" button
**Confirmation:** Yes (confirms action before executing)

## Example

**Team:** Bayern München (30 players)
- Position: CMF (6 players, ideal: 4)
- Surplus: 2 players
- Selected: Weakest 2 CMF players
- Severance: 25% of each player's salary
- Result: 2 players released to free agency

## Blog Post Format

```
CPU Dump for Strength: Players Released

CPU Dump for Strength has been executed! 5 player(s) have been released to free agency:

Bayern München:
  • Player A (Overall: 65, Age: 28) - Severance: €250,000
  • Player B (Overall: 62, Age: 31) - Severance: €180,000

All released players have received 25% of their salary as severance, which has been added to their career earnings.
```

## Status

✅ Function implemented
✅ Route created
✅ UI button added
✅ Blog post integration
✅ Ready for testing
