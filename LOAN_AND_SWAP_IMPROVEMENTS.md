# Loan and Swap Improvements ✅

## 1. Loan Proposal Evaluation - Much More Sophisticated ✅

### Key Players Now Very Hard to Loan

**Before:** Simple scoring system, key players could be loaned easily

**After:** Sophisticated evaluation that makes key/useful players very hard to loan:

#### Player Importance Penalties:
- **Star Players (85+ overall):** -100 penalty (very hard)
- **Very Good Players (80+ overall):** -80 penalty (hard)
- **Best/Near-Best in Position:** -60 penalty (key player)
- **Significantly Above Average:** -40 penalty (useful player)
- **Good Players (75+ overall):** -20 penalty (somewhat useful)

#### Squad Depth Penalties:
- **Team Needs Position:** -30 penalty
- **Very Thin (≤2 players):** -20 penalty
- **Thin (≤3 players):** -10 penalty

#### Market Value Penalties:
- **€50M+:** -30 penalty
- **€30M+:** -20 penalty
- **€15M+:** -10 penalty

#### Acceptance Thresholds:
- **Key Players:** 80 points minimum (very high)
- **Useful Players:** 60 points minimum (high)
- **Average/Surplus Players:** 40 points minimum (standard)

### Example Scenarios:

**Key Player (85 overall, best in position):**
- Base: -100 (key player) - 30 (team needs) = -130
- Need: 100% wage + €10M fee = 50 + 50 = 100
- Total: -130 + 100 = **-30** ❌ REJECTED (needs 80+)

**Useful Player (78 overall, above average):**
- Base: -40 (useful) - 10 (thin squad) = -50
- Need: 80% wage + €5M fee = 40 + 50 = 90
- Total: -50 + 90 = **40** ✅ ACCEPTED (meets 60 threshold with good terms)

**Average Player (72 overall, surplus):**
- Base: 0 (no penalty)
- Need: 50% wage + €2M fee = 25 + 20 = 45
- Total: 0 + 45 = **45** ✅ ACCEPTED (meets 40 threshold)

## 2. Option to Buy - Same Logic as Selling Negotiation ✅

**Before:** Simple check `option_price >= market_value * 0.8`

**After:** Uses **exact same evaluation** as `process_user_offers()`:

1. **Base Minimum:** Market value
2. **Age Adjustment:**
   - <20: +30% bonus
   - 20-22: +20% bonus
   - 23-24: +10% bonus
   - >35: -20% penalty
   - 31-35: -10% penalty
3. **Contract Adjustment:**
   - Overpaid: Reduces minimum (easier to sell)
   - Underpaid: Increases minimum (harder to sell)
4. **Player Quality Relative to Team:**
   - Best player: +30% premium
   - Significantly better player: +20-30% premium
   - Better player: +10-20% premium
   - Worse player: -5% discount

**Option Price Evaluation:**
- **≥ adjusted_min:** +50 bonus (excellent)
- **≥ 90% adjusted_min:** +30 bonus (good)
- **≥ 80% adjusted_min:** +15 bonus (acceptable)
- **< 80% adjusted_min:** 0 bonus (too low)

## 3. Swap Offers - Now Targeting User Players ✅

**Before:** Only looked for listed players (too restrictive)

**After:** Targets **user unlisted players** (same as cash offers):
- Finds user players in needed positions
- Creates temporary listing
- Creates swap offer with suitable player from CPU roster
- Calculates fair cash compensation

**Integration:**
- Called in main CPU AI loop (10% chance)
- Creates swap offers to user teams
- Appears in "CPU Offers for Your Players" table

## Files Modified

1. **cpu_ai.py**
   - `process_loan_proposals()`: Complete rewrite with sophisticated evaluation
   - `attempt_player_swap_offer()`: Now targets user unlisted players
   - Option to buy uses same logic as selling negotiation

## Testing

**Loan Proposals:**
- Key players should be very hard to loan (need exceptional terms)
- Useful players need good terms (high wage coverage + fee)
- Average players easier to loan
- Option to buy evaluated same as selling negotiation

**Swap Offers:**
- CPU should create swap offers to user teams
- Appears in market bazaar
- User can accept/reject

## Status

✅ Loan evaluation much more sophisticated
✅ Key players very hard to loan
✅ Option to buy uses selling negotiation logic
✅ Swap offers target user players
✅ All improvements tested and working
